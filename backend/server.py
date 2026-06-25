from fastapi import FastAPI, APIRouter, Depends, Request, Response, HTTPException
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import io
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Literal
import uuid
from datetime import datetime, timezone
import pymupdf as fitz

load_dotenv()
from auth import (
    hash_password, verify_password,
    create_access_token, set_session_cookies, clear_session_cookies,
    issue_csrf_token, require_auth, sanitize_text,
    bootstrap_admin_if_missing, change_user_password,
    assert_not_locked, register_failed_attempt, clear_failed_attempts,
    COOKIE_ACCESS, COOKIE_CSRF,
)

STATIC_DIR = Path(__file__).parent / "static"
TEMPLATE_PDF = STATIC_DIR / "Internship_Certificate_Template.pdf"
ORIGINAL_PDF = STATIC_DIR / "Aravind_Krishna_Original.pdf"

# Full Roboto fonts (bundled at backend/static/fonts/, sourced from
# fontsource / Google Fonts under Apache 2.0). We embed BOTH weights so the
# replaced paragraph reflows correctly with inline bold/regular mixing —
# matching the original document character-for-character in style.
ROBOTO_REGULAR_PATH = STATIC_DIR / "fonts" / "Roboto-Regular.ttf"
ROBOTO_BOLD_PATH    = STATIC_DIR / "fonts" / "Roboto-Bold.ttf"

# Body paragraph occupies these two original lines (left margin -> right
# margin where text wraps), and the original line spacing is 20pt.
PARA_REDACT_RECT = fitz.Rect(42.06, 207.0, 561.0, 252.0)
# Drawing rect: top adjusted so the first line baseline lands at exactly the
# original y (212.16) given line-height=20pt; bottom extended so the Story
# renderer never auto-shrinks the font below 10pt.
PARA_DRAW_RECT   = fitz.Rect(42.06, 198.43, 561.0, 398.43)
TEXT_COLOR_HEX   = "#231F20"   # original "rich black" of the body text
FONT_SIZE        = 10
LINE_HEIGHT_PT   = 20          # original line spacing (20pt between baselines)

# Original four values to redact out of the source PDF.
ORIG_VALUES = {
    "name":        "Mr. Aravind Krishna P M",
    "designation": "AI Research Analyst",
    "commenced":   "28.07.2025",
    "concluded":   "24.11.2025",
}
TEXT_COLOR = (0x23/255, 0x1F/255, 0x20/255)   # same #231F20 in RGB tuple


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore MongoDB's _id field
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Hello World"}


# ---------------------------------------------------------------------------
# Authentication endpoints (custom JWT + HttpOnly cookie + CSRF double-submit)
# ---------------------------------------------------------------------------
COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "auto").lower()


def _is_secure(request: Request) -> bool:
    if COOKIE_SECURE == "true":  return True
    if COOKIE_SECURE == "false": return False
    # auto: derive from request scheme / forwarded proto
    return request.url.scheme == "https" or \
           request.headers.get("x-forwarded-proto", "").lower() == "https"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)


@api_router.post("/auth/login")
async def login(req: LoginRequest, request: Request, response: Response):
    username = req.username.strip().lower()
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{username}"
    await assert_not_locked(db, identifier)

    user = await db.users.find_one({"_id": username})
    if not user or not verify_password(req.password, user["password_hash"]):
        await register_failed_attempt(db, identifier)
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    await clear_failed_attempts(db, identifier)
    token = create_access_token(username)
    csrf = issue_csrf_token()
    set_session_cookies(response, token, csrf, secure=_is_secure(request))
    return {"user": {"username": username, "role": user.get("role", "admin")},
            "csrf_token": csrf}


@api_router.post("/auth/logout")
async def logout(response: Response, _: dict = Depends(require_auth)):
    clear_session_cookies(response)
    return {"ok": True}


@api_router.get("/auth/me")
async def me(session: dict = Depends(require_auth)):
    return {"user": {"username": session["sub"], "role": "admin"}}


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password:     str = Field(min_length=8, max_length=200)


@api_router.post("/auth/change-password")
async def change_password(req: ChangePasswordRequest,
                          request: Request,
                          response: Response,
                          session: dict = Depends(require_auth)):
    """Authenticated admin rotates their own password. The new hash is
    written to MongoDB; the plain text never leaves this request scope.
    Brute-force lockout is applied per-IP+username on the current_password
    check so this endpoint can't be used as an oracle."""
    username = session["sub"]
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{username}:chpw"
    await assert_not_locked(db, identifier)
    try:
        await change_user_password(db, username, req.current_password, req.new_password)
    except HTTPException as e:
        if e.status_code == 401:
            await register_failed_attempt(db, identifier)
        raise
    await clear_failed_attempts(db, identifier)
    # Invalidate the current session so the user has to sign in with the
    # new password — this also forces any other open sessions to re-auth
    # after their JWT expires.
    clear_session_cookies(response)
    return {"ok": True}


@api_router.get("/template/download")
async def download_template(_: dict = Depends(require_auth)):
    """Download the editable Internship Certificate template PDF."""
    return FileResponse(
        path=str(TEMPLATE_PDF),
        media_type="application/pdf",
        filename="Internship_Certificate_Template.pdf",
    )


@api_router.get("/template/original")
async def download_original(_: dict = Depends(require_auth)):
    """Download the original (reference) certificate PDF."""
    return FileResponse(
        path=str(ORIGINAL_PDF),
        media_type="application/pdf",
        filename="Aravind_Krishna_Original.pdf",
    )


@api_router.get("/template/preview")
async def preview_template(_: dict = Depends(require_auth)):
    """Inline preview of the editable template PDF (for iframe rendering)."""
    return FileResponse(
        path=str(TEMPLATE_PDF),
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="Internship_Certificate_Template.pdf"'},
    )


class CertificateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    designation: str = Field(min_length=1, max_length=120)
    commenced: str = Field(min_length=1, max_length=40)
    concluded: str = Field(min_length=1, max_length=40)
    gender: Literal["male", "female"]


# ---- Static body lines that depend on gender ---------------------------------
# Lines 3-4 of the original PDF body — these stay verbatim for `male` (the
# original PDF already reads "During his ... he ... him ... him"), but when
# `gender == "female"` we redact those two lines and re-render them with
# `her / she / her / her` substituted. The y-coordinates were derived from
# `page.get_text()` against the source PDF — baselines at y=273 (para 2,
# first visual line), y=293 (para 2, wrapped), and y=326 (para 3).
STATIC_BODY_REDACT = fitz.Rect(42.06, 258.0, 561.0, 335.0)
# Draw rect tops are positioned 13.73pt above the desired first-baseline
# (same offset proven by PARA_DRAW_RECT, where top=198.43 → baseline=212.16).
# Original baselines: line-3 y=269, line-4 y=322 (from get_text on source PDF).
STATIC_PARA2_RECT  = fitz.Rect(42.06, 255.27, 561.0, 320.0)   # 2 visual lines
STATIC_PARA3_RECT  = fitz.Rect(42.06, 308.27, 561.0, 360.0)   # 1 visual line
# Note: para2.y1 (320) overlaps para3.y0 (308.27) by ~12pt in the rect
# bounding boxes, but the actual painted text glyphs land in non-overlapping
# vertical bands (para2 ends visually at y≈298, para3 starts at y≈322).
# Shrinking para2.y1 below 320 causes insert_htmlbox to drop the 2nd visual
# line ("initiatives.") because it conservatively reserves a full line-height
# of trailing padding.
STATIC_PARA2_FEMALE = (
    "During her internship, she demonstrated professionalism, enthusiasm, "
    "and valuable contributions to our research initiatives."
)
STATIC_PARA3_FEMALE = "We wish her all the best in her future endeavors."


def _build_filled_pdf(values: dict) -> bytes:
    """Bake the user-supplied values directly into the source PDF.

    Strategy: redact the ENTIRE two-line body paragraph, then re-render it from
    scratch using a Story-based HTML box with the two embedded Roboto weights.
    This guarantees:
      * No leftover blank space when the typed value is shorter than the
        original placeholder (the surrounding text reflows naturally).
      * Inline mixed bold/regular weight — exactly mirroring the original.
      * Same font (Roboto), size (10pt), color (#232369), line spacing (20pt),
        first-line baseline (y=212.16), and right margin.

    Gender handling:
      * `male`   — pronouns in the rebuilt top paragraph use "his"/"His"; the
        static lines 3-4 of the original PDF are NOT touched (zero pixel-level
        risk; output is byte-equivalent in layout to the pre-feature build).
      * `female` — pronouns in the rebuilt top paragraph use "her"/"Her"; the
        static lines 3-4 are also redacted and re-rendered with feminine
        pronouns at their original baselines.
    """
    import html as _html
    import re as _re
    gender      = (values.get("gender") or "male").strip().lower()
    pronoun_lo  = "her" if gender == "female" else "his"
    pronoun_up  = "Her" if gender == "female" else "His"
    title       = "Ms." if gender == "female" else "Mr."

    # Strip any user-typed leading title (Mr / Mrs / Ms / Miss with optional
    # period) so we never produce "Mr. Mr. Aravind". The cleaned name is then
    # prefixed with the gender-correct title inside the bold span.
    raw_name    = values["name"].strip()
    cleaned     = _re.sub(r"^(mr|mrs|ms|miss)\.?\s+", "", raw_name, flags=_re.I).strip()
    display_name = f"{title} {cleaned}" if cleaned else title

    doc = fitz.open(str(ORIGINAL_PDF))
    page = doc[0]

    # 1) Queue redactions in a single batch (one apply_redactions call).
    page.add_redact_annot(PARA_REDACT_RECT, fill=(1, 1, 1))
    if gender == "female":
        page.add_redact_annot(STATIC_BODY_REDACT, fill=(1, 1, 1))
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    # 2) Shared CSS + font archive used by every htmlbox below.
    css = (
        "@font-face { font-family:'R'; src:url(roboto-regular); }"
        "@font-face { font-family:'R'; font-weight:bold; src:url(roboto-bold); }"
        f"* {{ font-family:'R'; font-size:{FONT_SIZE}pt; color:{TEXT_COLOR_HEX};"
        f" line-height:{LINE_HEIGHT_PT}pt; margin:0; padding:0; }}"
    )
    arch = fitz.Archive()
    arch.add(str(ROBOTO_REGULAR_PATH), "roboto-regular")
    arch.add(str(ROBOTO_BOLD_PATH),    "roboto-bold")

    # 3) Rebuild the dynamic top paragraph (lines 1-2).
    e = _html.escape
    body_html = (
        f'<p>This is to certify that <b>{e(display_name)}</b> '
        f'has completed {pronoun_lo} internship as an '
        f'<b>{e(values["designation"].strip())}</b> with Blubridge '
        f'Technologies Pvt Ltd. {pronoun_up} internship tenure commenced on '
        f'<b>{e(values["commenced"].strip())}</b> and concluded on '
        f'<b>{e(values["concluded"].strip())}</b>.</p>'
    )
    # scale_low=1 disables auto-shrink so the font stays at 10pt.
    page.insert_htmlbox(PARA_DRAW_RECT, body_html, css=css, archive=arch, scale_low=1)

    # 4) Female-only: re-render static lines 3-4 with feminine pronouns
    #    at the same baselines as the original.
    if gender == "female":
        page.insert_htmlbox(STATIC_PARA2_RECT, f"<p>{STATIC_PARA2_FEMALE}</p>",
                            css=css, archive=arch, scale_low=1)
        page.insert_htmlbox(STATIC_PARA3_RECT, f"<p>{STATIC_PARA3_FEMALE}</p>",
                            css=css, archive=arch, scale_low=1)

    buf = io.BytesIO()
    doc.save(buf, garbage=4, deflate=True, clean=True)
    doc.close()
    return buf.getvalue()


@api_router.post("/template/generate")
async def generate_certificate(req: CertificateRequest, _: dict = Depends(require_auth)):
    payload = req.model_dump()
    for k in ("name", "designation", "commenced", "concluded"):
        payload[k] = sanitize_text(payload[k], field=k)
    pdf_bytes = _build_filled_pdf(payload)
    # Strip the user's typed title (if any) so the filename matches the
    # gender-correct title baked into the PDF.
    import re as _re
    bare = _re.sub(r"^(mr|mrs|ms|miss)\.?\s+", "", req.name, flags=_re.I).strip()
    title_prefix = "Ms" if req.gender == "female" else "Mr"
    safe_name = "".join(c for c in bare if c.isalnum() or c in " _-").strip() or "Certificate"
    filename = f"Internship_Certificate_{title_prefix}_{safe_name.replace(' ', '_')}.pdf"
    await _save_history("certificate", req.name, filename, pdf_bytes,
                        summary={"designation": req.designation,
                                 "commenced":   req.commenced,
                                 "concluded":   req.concluded,
                                 "gender":      req.gender})
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Internship Offer Letter generator
# ---------------------------------------------------------------------------
from offer_letter import build_offer_letter
from acknowledgement import build_acknowledgement
from offer_letter_email import render_offer_letter  # noqa: E402


class OfferRequest(BaseModel):
    ref_code:       str = Field(min_length=1, max_length=40)
    date:           str = Field(min_length=1, max_length=40)
    name:           str = Field(min_length=1, max_length=120)
    addr1:          str = Field(min_length=1, max_length=160)
    addr2:          str = Field(min_length=1, max_length=160)
    addr3:          str = Field(min_length=1, max_length=160)
    phone:          str = Field(min_length=1, max_length=40)
    email:          str = Field(min_length=1, max_length=120)
    designation:    str = Field(min_length=1, max_length=120)
    salary_amount:  str = Field(min_length=1, max_length=40)
    salary_words:   str = Field(min_length=1, max_length=120)


@api_router.post("/offer/generate")
async def generate_offer(req: OfferRequest, _: dict = Depends(require_auth)):
    payload = req.model_dump()
    for k in ("ref_code","date","name","addr1","addr2","addr3","phone","email",
              "designation","salary_amount","salary_words"):
        payload[k] = sanitize_text(payload[k], field=k)
    pdf_bytes = build_offer_letter(payload)
    safe_name = "".join(c for c in req.name if c.isalnum() or c in " _-").strip() or "Offer"
    filename = f"Offer_Letter_{safe_name.replace(' ', '_')}.pdf"
    await _save_history("offer", req.name, filename, pdf_bytes,
                        summary={"ref_code": req.ref_code,
                                 "date": req.date,
                                 "designation": req.designation,
                                 "salary_amount": req.salary_amount})
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Letter of Acknowledgement generator
# ---------------------------------------------------------------------------
class AckRequest(BaseModel):
    date:           str = Field(min_length=1, max_length=60)
    name:           str = Field(min_length=1, max_length=120)
    marksheet_type: str = Field(min_length=1, max_length=80)


@api_router.post("/ack/generate")
async def generate_ack(req: AckRequest, _: dict = Depends(require_auth)):
    payload = req.model_dump()
    for k in ("date","name","marksheet_type"):
        payload[k] = sanitize_text(payload[k], field=k)
    pdf_bytes = build_acknowledgement(payload)
    safe_name = "".join(c for c in req.name if c.isalnum() or c in " _-").strip() or "Acknowledgement"
    filename = f"Acknowledgement_{safe_name.replace(' ', '_')}.pdf"
    await _save_history("ack", req.name, filename, pdf_bytes,
                        summary={"date": req.date,
                                 "marksheet_type": req.marksheet_type})
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Offer Letter (Email) — multi-page HTML generator
# ---------------------------------------------------------------------------
# Produces a fully self-contained HTML offer letter (with embedded CSS) that
# can be previewed in an iframe today and sent via email in the next
# iteration. Only `standard` mode is wired in v1; the `mode` field is kept on
# the request so the FE can stay forward-compatible.

class OfferEmailRequest(BaseModel):
    title:            Literal["Mr.", "Ms.", "Mrs.", "Dr."]
    name:             str = Field(min_length=1, max_length=120)
    email:            str = Field(min_length=3, max_length=160)
    phone:            str = Field(min_length=1, max_length=40)
    date:             str = Field(min_length=1, max_length=40)   # joining date
    cur_date:         str = Field(min_length=1, max_length=40)   # letter date
    reference_number: str = Field(min_length=1, max_length=60)
    designation:      str = Field(min_length=1, max_length=120)
    address_line1:    str = Field(min_length=1, max_length=200)
    address_line2:    str = Field(default="",   max_length=200)
    address_line3:    str = Field(default="",   max_length=200)
    mode:             Literal["standard", "customized"] = "standard"
    ctc_yearly:       int = Field(gt=0, le=100_000_000)


@api_router.post("/offer-email/preview")
async def offer_email_preview(req: OfferEmailRequest,
                              _: dict = Depends(require_auth)):
    """Render the HTML offer letter for in-browser preview. Also persists the
    rendered HTML in history so the operator can revisit / re-send later."""
    if req.mode == "customized":
        raise HTTPException(
            status_code=400,
            detail="Customized mode will ship in the next iteration. "
                   "Use Standard mode for now.",
        )
    payload = req.model_dump()
    for k in ("name", "phone", "email", "designation", "reference_number",
              "address_line1", "address_line2", "address_line3"):
        payload[k] = sanitize_text(payload[k], field=k)
    try:
        html = render_offer_letter(payload)
    except (ValueError, RuntimeError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Persist for history (stored as bytes; filename matches the candidate).
    safe_name = "".join(c for c in req.name if c.isalnum() or c in " _-").strip() or "Offer"
    filename = f"Offer_Letter_Email_{safe_name.replace(' ', '_')}.html"
    history_id = await _save_history(
        "offer_email", req.name, filename, html.encode("utf-8"),
        summary={
            "designation":      req.designation,
            "reference_number": req.reference_number,
            "ctc_yearly":       req.ctc_yearly,
            "joining_date":     req.date,
        },
    )
    return {"html": html, "filename": filename, "history_id": history_id}


# ---------------------------------------------------------------------------
# Document generation history
# ---------------------------------------------------------------------------
# Each successful PDF generation is persisted in MongoDB so HR can later list
# what has been generated and re-download any previous document without
# re-entering the form data.

from bson.binary import Binary


async def _save_history(doc_type: str, name: str, filename: str,
                        pdf_bytes: bytes, summary: dict) -> str:
    """Persist a generated document. Returns the new history entry id."""
    entry = {
        "id":         str(uuid.uuid4()),
        "type":       doc_type,           # certificate | offer | ack
        "name":       name,
        "filename":   filename,
        "summary":    summary,
        "size_bytes": len(pdf_bytes),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "pdf":        Binary(pdf_bytes),  # store as BSON Binary
    }
    await db.history.insert_one(entry)
    return entry["id"]


@api_router.get("/history")
async def list_history(type: str | None = None, q: str | None = None, limit: int = 100,
                       _: dict = Depends(require_auth)):
    """List generated documents (newest first). Filter by `type` or `q` (name search)."""
    query: dict = {}
    if type:
        query["type"] = type
    if q:
        query["name"] = {"$regex": q, "$options": "i"}
    cursor = db.history.find(query, {"pdf": 0, "_id": 0}).sort("created_at", -1).limit(limit)
    items = await cursor.to_list(length=limit)
    return {"items": items, "count": len(items)}


@api_router.get("/history/{entry_id}/download")
async def download_history(entry_id: str, _: dict = Depends(require_auth)):
    """Re-download a previously-generated document. Content-type is inferred
    from the stored filename so PDF documents stream as application/pdf and
    HTML offer-letter emails stream as text/html."""
    entry = await db.history.find_one({"id": entry_id}, {"_id": 0})
    if not entry:
        return StreamingResponse(io.BytesIO(b""), status_code=404)
    blob = bytes(entry["pdf"])  # historical column name; may also hold HTML
    filename = entry.get("filename", f"document_{entry_id[:8]}.pdf")
    media_type = "text/html" if filename.lower().endswith(".html") else "application/pdf"
    return StreamingResponse(
        io.BytesIO(blob),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api_router.delete("/history/{entry_id}")
async def delete_history(entry_id: str, _: dict = Depends(require_auth)):
    """Remove a single history entry."""
    res = await db.history.delete_one({"id": entry_id})
    return {"deleted": res.deleted_count}

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    # Convert to dict and serialize datetime to ISO string for MongoDB
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    _ = await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    # Exclude MongoDB's _id field from the query results
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    # Convert ISO string timestamps back to datetime objects
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Security-headers middleware (Helmet-equivalent for FastAPI)
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # Prevent XSS via injected scripts in same-origin context.
        # 'unsafe-inline' on style-src is needed for the CRA build's inline
        # critical CSS; script-src stays strict to 'self'.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data: https:; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=()"
        )
        # HSTS only over HTTPS
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            response.headers["Strict-Transport-Security"] = \
                "max-age=31536000; includeSubDomains"
        return response


app.add_middleware(SecurityHeadersMiddleware)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def _on_startup():
    # One-shot bootstrap: if no admin row exists and HR_USERNAME/HR_PASSWORD
    # env vars are set, seed a single admin. Existing DB hashes are never
    # overwritten — the database is the sole source of truth thereafter.
    seeded = await bootstrap_admin_if_missing(db)
    if seeded:
        logger.warning(
            "Admin bootstrapped from env. Delete HR_USERNAME/HR_PASSWORD "
            "from your production environment now."
        )
    # Helpful indexes for the auth collections
    await db.users.create_index("created_at")
    await db.login_attempts.create_index("locked_until")
    logger.info("Auth ready (indexes ensured).")


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()


# ---------------------------------------------------------------------------
# Single-service deploy: serve the React frontend's static build from FastAPI
# ---------------------------------------------------------------------------
# When the React app is built into ../frontend/build (relative to this file),
# FastAPI mounts it at "/" and serves index.html for any unknown route so
# client-side routing keeps working on refresh.
#
# This block is a no-op during local development (where the React dev server
# runs separately on :3000 and there is no build/ folder yet).
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse as _FileResponse

_FRONTEND_BUILD = (Path(__file__).parent.parent / "frontend" / "build").resolve()

if _FRONTEND_BUILD.is_dir() and (_FRONTEND_BUILD / "index.html").is_file():
    # /static/* is the CRA output path (JS/CSS bundles, etc.).
    _cra_static = _FRONTEND_BUILD / "static"
    if _cra_static.is_dir():
        app.mount("/static", StaticFiles(directory=str(_cra_static)), name="cra-static")

    # SPA fallback: any non-API GET that doesn't match a real file returns
    # index.html so React Router can take over.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def _spa_fallback(full_path: str):
        # Never intercept API routes.
        if full_path.startswith("api/"):
            return _FileResponse(_FRONTEND_BUILD / "index.html", status_code=404)
        # Serve a real file from build/ if it exists (favicon, manifest, etc.).
        candidate = (_FRONTEND_BUILD / full_path).resolve()
        if candidate.is_file() and str(candidate).startswith(str(_FRONTEND_BUILD)):
            return _FileResponse(candidate)
        # Otherwise fall back to index.html.
        return _FileResponse(_FRONTEND_BUILD / "index.html")

    logger.info("Frontend build mounted from %s", _FRONTEND_BUILD)
else:
    logger.info("No frontend build at %s — backend only (dev mode).", _FRONTEND_BUILD)