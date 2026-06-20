"""
Backend tests for /api/auth/change-password and supporting auth flow.

CRITICAL: every test that mutates the admin password must restore it to
'pass1234' before exiting. Ordering matters — pytest runs tests inside
a class in declaration order.
"""
import os
import time
import pytest
import requests
from pathlib import Path

# Load REACT_APP_BACKEND_URL from frontend/.env if not in env
if not os.environ.get("REACT_APP_BACKEND_URL"):
    env_file = Path("/app/frontend/.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                os.environ["REACT_APP_BACKEND_URL"] = line.split("=", 1)[1].strip()

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
LOGIN_URL  = f"{BASE_URL}/api/auth/login"
CHPW_URL   = f"{BASE_URL}/api/auth/change-password"
ME_URL     = f"{BASE_URL}/api/auth/me"

ADMIN_USER = "admin"
ORIGINAL_PW = "pass1234"


# ------------------------- helpers -----------------------------------

def _login(session: requests.Session, password: str) -> requests.Response:
    return session.post(LOGIN_URL, json={"username": ADMIN_USER, "password": password})


def _authed_session(password: str = ORIGINAL_PW) -> requests.Session:
    s = requests.Session()
    r = _login(s, password)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    body = r.json()
    csrf = body.get("csrf_token") or s.cookies.get("hrcert_csrf")
    s.headers.update({"X-CSRF-Token": csrf})
    return s


def _change_password(session: requests.Session, current: str, new: str) -> requests.Response:
    return session.post(CHPW_URL, json={"current_password": current, "new_password": new})


# ---------- module-scoped safety net: always restore original pw ----------

@pytest.fixture(scope="module", autouse=True)
def _restore_password():
    yield
    # Try each candidate that an in-flight test might have left behind.
    candidates = [ORIGINAL_PW, "newpass9X!", "newpass9Y!", "newpass9Z!",
                  "tempPass12", "tempPass34", "tempPass56"]
    for pw in candidates:
        s = requests.Session()
        r = _login(s, pw)
        if r.status_code == 200:
            if pw == ORIGINAL_PW:
                return
            csrf = r.json().get("csrf_token") or s.cookies.get("hrcert_csrf")
            s.headers.update({"X-CSRF-Token": csrf})
            rr = _change_password(s, pw, ORIGINAL_PW)
            assert rr.status_code == 200, f"restore failed: {rr.status_code} {rr.text}"
            return
    pytest.fail("Could not restore admin password back to pass1234")


# ============================ tests ===================================

class TestLogin:
    def test_login_success_sets_cookies(self):
        s = requests.Session()
        r = _login(s, ORIGINAL_PW)
        assert r.status_code == 200
        body = r.json()
        assert body["user"]["username"] == "admin"
        assert "csrf_token" in body
        # HttpOnly access cookie
        assert "hrcert_session" in s.cookies
        assert "hrcert_csrf" in s.cookies

    def test_login_wrong_password(self):
        s = requests.Session()
        r = s.post(LOGIN_URL, json={"username": "admin", "password": "definitely-wrong-xx"})
        assert r.status_code == 401
        assert r.json().get("detail") == "Invalid username or password."


class TestChangePasswordGuards:
    def test_no_auth_cookie_returns_401(self):
        r = requests.post(CHPW_URL,
                          json={"current_password": ORIGINAL_PW, "new_password": "irrelevant9"})
        assert r.status_code == 401

    def test_missing_csrf_header_returns_403(self):
        s = requests.Session()
        r = _login(s, ORIGINAL_PW)
        assert r.status_code == 200
        # do NOT set X-CSRF-Token
        rr = s.post(CHPW_URL,
                    json={"current_password": ORIGINAL_PW, "new_password": "irrelevant9"})
        assert rr.status_code == 403
        assert "CSRF" in rr.json().get("detail", "")

    def test_wrong_current_password_returns_401(self):
        s = _authed_session()
        rr = _change_password(s, "wrong-current-xx", "uniqueNew9A!")
        assert rr.status_code == 401
        assert "Current password" in rr.json().get("detail", "")

    def test_short_new_password_returns_422(self):
        # Pydantic min_length=8 → 422, NOT counted as a failed-current attempt.
        s = _authed_session()
        rr = _change_password(s, ORIGINAL_PW, "short7x")  # 7 chars
        assert rr.status_code == 422

    def test_same_as_current_returns_400(self):
        s = _authed_session()
        rr = _change_password(s, ORIGINAL_PW, ORIGINAL_PW)
        assert rr.status_code == 400
        assert "differ" in rr.json().get("detail", "").lower()


class TestChangePasswordHappyPath:
    """Rotate pw → verify clears cookies, old pw fails, new pw works,
    then rotate back to pass1234."""

    def test_happy_path_and_restore(self):
        new_pw = "tempPass34"   # unique, >=8 chars, != current
        s = _authed_session()
        rr = _change_password(s, ORIGINAL_PW, new_pw)
        assert rr.status_code == 200, f"{rr.status_code} {rr.text}"
        assert rr.json() == {"ok": True}

        # Set-Cookie must clear both cookies (Max-Age=0 or expires in past).
        raw_set_cookies = rr.headers.get("set-cookie", "") + " " + \
                          " ".join(rr.raw.headers.getlist("Set-Cookie")
                                   if hasattr(rr.raw.headers, "getlist") else [])
        assert "hrcert_session" in raw_set_cookies
        assert "hrcert_csrf"    in raw_set_cookies
        # FastAPI's delete_cookie either uses Max-Age=0 or an expires=1970 date
        cleared = ("max-age=0" in raw_set_cookies.lower() or
                   "1970" in raw_set_cookies or
                   "expires=thu, 01 jan 1970" in raw_set_cookies.lower())
        assert cleared, f"cookies not cleared: {raw_set_cookies}"

        # Old password no longer works
        s2 = requests.Session()
        assert _login(s2, ORIGINAL_PW).status_code == 401

        # New password works
        s3 = requests.Session()
        r3 = _login(s3, new_pw)
        assert r3.status_code == 200

        # Persistence: re-login fresh and rotate back to pass1234
        csrf = r3.json().get("csrf_token") or s3.cookies.get("hrcert_csrf")
        s3.headers.update({"X-CSRF-Token": csrf})
        back = _change_password(s3, new_pw, ORIGINAL_PW)
        assert back.status_code == 200

        # And original works again
        s4 = requests.Session()
        assert _login(s4, ORIGINAL_PW).status_code == 200


class TestPersistenceAcrossRestart:
    """After supervisor restart, the env HR_PASSWORD must NOT overwrite the
    DB hash. We rotate, restart backend, log in with new pw, then rotate
    back to pass1234."""

    def test_db_authoritative_across_restart(self):
        import subprocess
        new_pw = "tempPass56"
        s = _authed_session()
        assert _change_password(s, ORIGINAL_PW, new_pw).status_code == 200

        # Restart backend
        subprocess.run(["sudo", "supervisorctl", "restart", "backend"], check=True)
        # wait until /api/auth/me responds (server back up)
        for _ in range(40):
            try:
                if requests.get(ME_URL, timeout=2).status_code in (401, 200):
                    break
            except Exception:
                pass
            time.sleep(0.5)

        # env HR_PASSWORD is 'pass123' — it must NOT be the live password.
        s_env = requests.Session()
        assert _login(s_env, "pass123").status_code == 401, \
            "REGRESSION: env HR_PASSWORD overwrote DB hash on restart"

        # New pw still works
        s_new = requests.Session()
        r = _login(s_new, new_pw)
        assert r.status_code == 200, "DB hash lost across restart"

        # Restore to pass1234
        csrf = r.json().get("csrf_token") or s_new.cookies.get("hrcert_csrf")
        s_new.headers.update({"X-CSRF-Token": csrf})
        assert _change_password(s_new, new_pw, ORIGINAL_PW).status_code == 200
