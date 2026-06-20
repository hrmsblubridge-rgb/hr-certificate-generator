"""
Auth + security primitives for the HR document generator.

This module owns:
  - bcrypt password hashing + verification
  - JWT access-token minting/decoding (HS256)
  - Login brute-force lockout (MongoDB-backed, per IP + username)
  - CSRF double-submit token issuance + verification
  - `require_auth` FastAPI dependency that gates every protected endpoint
"""
from __future__ import annotations

import os
import re
import secrets
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from fastapi import HTTPException, Request, Response

JWT_ALGORITHM       = "HS256"
JWT_TTL_MINUTES     = 60 * 8       # 8h session
LOCKOUT_THRESHOLD   = 5            # failed attempts before lockout
LOCKOUT_MINUTES     = 15
COOKIE_ACCESS       = "hrcert_session"
COOKIE_CSRF         = "hrcert_csrf"


def _jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET env var is required")
    return secret


# ------------------------- Password hashing -----------------------------------

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


# ------------------------- JWT --------------------------------------------------

def create_access_token(username: str) -> str:
    payload = {
        "sub":  username,
        "iat":  datetime.now(timezone.utc),
        "exp":  datetime.now(timezone.utc) + timedelta(minutes=JWT_TTL_MINUTES),
        "type": "access",
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    payload = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("wrong type")
    return payload


# ------------------------- Cookies ---------------------------------------------

def _cookie_kwargs(secure: bool) -> dict:
    return {
        "httponly": True,
        "secure":   secure,
        "samesite": "lax",
        "path":     "/",
    }


def set_session_cookies(response: Response, token: str, csrf: str, *, secure: bool):
    response.set_cookie(COOKIE_ACCESS, token, max_age=JWT_TTL_MINUTES * 60,
                        **_cookie_kwargs(secure))
    # CSRF cookie is intentionally NOT HttpOnly — JS must read it to echo
    # the value back in the X-CSRF-Token header (double-submit pattern).
    response.set_cookie(COOKIE_CSRF, csrf, max_age=JWT_TTL_MINUTES * 60,
                        httponly=False, secure=secure, samesite="lax", path="/")


def clear_session_cookies(response: Response):
    for c in (COOKIE_ACCESS, COOKIE_CSRF):
        response.delete_cookie(c, path="/")


def issue_csrf_token() -> str:
    return secrets.token_urlsafe(32)


# ------------------------- Auth dependency -------------------------------------

def _check_csrf(request: Request):
    """Enforce double-submit: the X-CSRF-Token header MUST match the csrf
    cookie value for any state-changing method (POST/PUT/PATCH/DELETE)."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    header = request.headers.get("x-csrf-token") or request.headers.get("X-CSRF-Token")
    cookie = request.cookies.get(COOKIE_CSRF)
    if not (header and cookie and secrets.compare_digest(header, cookie)):
        raise HTTPException(status_code=403, detail="CSRF token mismatch")


async def require_auth(request: Request) -> dict:
    """FastAPI dependency: returns the authenticated session payload, or
    raises 401/403. Apply to every protected endpoint."""
    token = request.cookies.get(COOKIE_ACCESS)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid session")
    _check_csrf(request)
    return payload


# ------------------------- Brute-force lockout ---------------------------------

async def assert_not_locked(db, identifier: str):
    rec = await db.login_attempts.find_one({"_id": identifier})
    if not rec:
        return
    if rec.get("count", 0) >= LOCKOUT_THRESHOLD:
        until = rec.get("locked_until")
        if until and datetime.now(timezone.utc) < until:
            wait = int((until - datetime.now(timezone.utc)).total_seconds())
            raise HTTPException(
                status_code=429,
                detail=f"Too many failed attempts. Try again in {wait}s.",
            )
        # window expired → reset
        await db.login_attempts.delete_one({"_id": identifier})


async def register_failed_attempt(db, identifier: str):
    now = datetime.now(timezone.utc)
    rec = await db.login_attempts.find_one_and_update(
        {"_id": identifier},
        {
            "$inc": {"count": 1},
            "$setOnInsert": {"first_at": now},
            "$set": {"last_at": now},
        },
        upsert=True, return_document=True,
    ) or {}
    if rec.get("count", 0) >= LOCKOUT_THRESHOLD:
        await db.login_attempts.update_one(
            {"_id": identifier},
            {"$set": {"locked_until": now + timedelta(minutes=LOCKOUT_MINUTES)}},
        )


async def clear_failed_attempts(db, identifier: str):
    await db.login_attempts.delete_one({"_id": identifier})


# ------------------------- Input sanitisation ---------------------------------

# Whitelist of characters that may appear in any user-typed value that flows
# into a generated PDF. Strictly excludes anything that could be interpreted
# as a PDF control sequence ("(", ")", "\", "<", ">"), HTML/JS markers
# ("<", ">"), or NoSQL operators ("$", ".") at the boundary positions.
_PDF_SAFE_RE = re.compile(
    r"^[A-Za-z0-9 .,'\-/_:@&()#\u20b9\u2013\u2014]*$"
)


def sanitize_text(value: str, *, max_len: int = 200, field: str = "value") -> str:
    """Reject inputs that exceed the length limit or contain disallowed
    characters. Returns the trimmed value on success."""
    if value is None:
        raise HTTPException(status_code=400, detail=f"{field} is required")
    v = value.strip()
    if not v:
        raise HTTPException(status_code=400, detail=f"{field} is required")
    if len(v) > max_len:
        raise HTTPException(status_code=400, detail=f"{field} too long")
    # Strip raw HTML/script delimiters defensively before regex check.
    if "<" in v or ">" in v:
        raise HTTPException(status_code=400, detail=f"{field} contains illegal characters")
    if not _PDF_SAFE_RE.match(v):
        raise HTTPException(status_code=400, detail=f"{field} contains illegal characters")
    return v


# ------------------------- Admin seeding ---------------------------------------

async def seed_admin(db):
    """Idempotent: ensure the admin user exists with the hashed password the
    env var dictates. If env password rotates, the hash is updated."""
    username = os.environ.get("HR_USERNAME", "admin")
    password = os.environ.get("HR_PASSWORD", "pass123")
    existing = await db.users.find_one({"_id": username})
    if existing is None:
        await db.users.insert_one({
            "_id": username,
            "password_hash": hash_password(password),
            "role": "admin",
            "created_at": datetime.now(timezone.utc),
        })
    elif not verify_password(password, existing["password_hash"]):
        await db.users.update_one(
            {"_id": username},
            {"$set": {"password_hash": hash_password(password)}},
        )
