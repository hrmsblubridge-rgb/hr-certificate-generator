"""Backend tests for /api/offer-email/preview (Offer Letter Email feature)."""
import os
import re
import pytest
import requests
from pathlib import Path

if not os.environ.get("REACT_APP_BACKEND_URL"):
    env_file = Path("/app/frontend/.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                os.environ["REACT_APP_BACKEND_URL"] = line.split("=", 1)[1].strip()

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
LOGIN_URL  = f"{BASE_URL}/api/auth/login"
PREVIEW_URL = f"{BASE_URL}/api/offer-email/preview"
HISTORY_URL = f"{BASE_URL}/api/history"

ADMIN_USER = "admin"
# Try both candidate passwords (iteration_2 says pass123 is live).
_PW_CANDIDATES = ["pass123", "pass1234"]


def _login_session():
    last_err = None
    for pw in _PW_CANDIDATES:
        s = requests.Session()
        r = s.post(LOGIN_URL, json={"username": ADMIN_USER, "password": pw})
        if r.status_code == 200:
            csrf = r.json().get("csrf_token") or s.cookies.get("hrcert_csrf")
            s.headers.update({"X-CSRF-Token": csrf})
            return s
        last_err = (r.status_code, r.text)
    pytest.skip(f"login failed for all candidates: {last_err}")


@pytest.fixture(scope="module")
def auth():
    return _login_session()


def _payload(**over):
    base = {
        "title": "Mr.",
        "name": "TEST Aravind Krishna",
        "email": "test@example.com",
        "phone": "9999999999",
        "cur_date": "25.06.2026",
        "date": "15.03.2026",
        "reference_number": "CHN/2025/Res/1-001",
        "designation": "Research Scientist",
        "address_line1": "12 Test Street",
        "address_line2": "Adyar",
        "address_line3": "Chennai 600020",
        "mode": "standard",
        "ctc_yearly": 660000,
    }
    base.update(over)
    return base


class TestPreviewHappyPath:
    def test_660k_full_render(self, auth):
        r = auth.post(PREVIEW_URL, json=_payload())
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(["html", "filename", "history_id"]).issubset(body.keys())
        html = body["html"]
        assert len(html) > 50000, f"html too short: {len(html)}"
        assert "Ref: CHN/2025/Res/1-001" in html
        assert "Date: 25.06.2026" in html
        assert "<strong>Mr. Aravind Krishna</strong>".replace("Aravind", "TEST Aravind") in html or \
               "<strong>Mr. TEST Aravind Krishna</strong>" in html
        assert "Phone: 9999999999" in html
        assert "<strong>15.03.2026</strong>" in html
        assert "6,60,000" in html
        assert "Six Lakh Sixty Thousand" in html
        assert "Tier 2" in html
        for ann in ["ANNEXURE A", "ANNEXURE B", "ANNEXURE C", "ANNEXURE D", "ANNEXURE I"]:
            assert ann in html, f"missing {ann}"
        # No leftover bracketed lower_snake placeholders
        leftovers = re.findall(r"\[[a-z_]+\]", html)
        assert not leftovers, f"leftover placeholders: {leftovers[:5]}"

    def test_1_5m_tier1(self, auth):
        r = auth.post(PREVIEW_URL, json=_payload(ctc_yearly=1_500_000))
        assert r.status_code == 200, r.text
        assert "Tier 1" in r.json()["html"]

    def test_300k_tier4(self, auth):
        r = auth.post(PREVIEW_URL, json=_payload(ctc_yearly=300_000))
        assert r.status_code == 200, r.text
        assert "Tier 4" in r.json()["html"]


class TestValidationErrors:
    def test_customized_mode_returns_400(self, auth):
        r = auth.post(PREVIEW_URL, json=_payload(mode="customized"))
        assert r.status_code == 400
        assert "next iteration" in r.json().get("detail", "").lower()

    def test_no_auth_returns_401(self):
        r = requests.post(PREVIEW_URL, json=_payload())
        assert r.status_code == 401

    def test_missing_csrf_returns_403(self):
        s = requests.Session()
        for pw in _PW_CANDIDATES:
            r = s.post(LOGIN_URL, json={"username": ADMIN_USER, "password": pw})
            if r.status_code == 200:
                break
        else:
            pytest.skip("login failed")
        # Don't set X-CSRF-Token header
        rr = s.post(PREVIEW_URL, json=_payload())
        assert rr.status_code == 403

    def test_ctc_zero_returns_422(self, auth):
        r = auth.post(PREVIEW_URL, json=_payload(ctc_yearly=0))
        assert r.status_code == 422

    def test_invalid_title_returns_422(self, auth):
        r = auth.post(PREVIEW_URL, json=_payload(title="Captain"))
        assert r.status_code == 422


class TestHistoryIntegration:
    def test_history_lists_and_downloads(self, auth):
        # Create one
        r = auth.post(PREVIEW_URL, json=_payload(name="TEST OfferEmail History"))
        assert r.status_code == 200
        history_id = r.json()["history_id"]

        # List
        lr = auth.get(HISTORY_URL, params={"type": "offer_email"})
        assert lr.status_code == 200
        items = lr.json()["items"]
        assert any(it["id"] == history_id for it in items)
        target = next(it for it in items if it["id"] == history_id)
        assert target["name"] == "TEST OfferEmail History"
        assert target["summary"]["ctc_yearly"] == 660000

        # Download — must be text/html, not pdf
        dr = auth.get(f"{HISTORY_URL}/{history_id}/download")
        assert dr.status_code == 200
        ctype = dr.headers.get("content-type", "")
        assert "text/html" in ctype, f"expected text/html, got {ctype}"
        assert b"ANNEXURE A" in dr.content
