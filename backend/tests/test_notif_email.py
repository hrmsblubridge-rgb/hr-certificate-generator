"""Backend tests for the Notification Email feature (v2 — one-click send).

Covers:
- GET  /api/employees/departments (auth-gated)
- GET  /api/employees              (auth-gated + department filter)
- POST /api/employees/import       (auth + CSRF gated)
- POST /api/notification/send      (auth + CSRF gated, per-recipient dispatch)
- GET  /api/history?type=notification  (batch persisted after send)

The `/notification/send` tests use safe placeholder addresses
(`qa1@example.com`, `qa2@example.com`, `invalid@example.invalid`) — SendGrid
returns 202 for any syntactically-valid email without actually delivering.
"""
import os
import pytest
import requests
from pathlib import Path

# ---- BASE_URL discovery ----------------------------------------------------
if not os.environ.get("REACT_APP_BACKEND_URL"):
    env_file = Path("/app/frontend/.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                os.environ["REACT_APP_BACKEND_URL"] = line.split("=", 1)[1].strip()

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
LOGIN_URL      = f"{BASE_URL}/api/auth/login"
DEPTS_URL      = f"{BASE_URL}/api/employees/departments"
EMPLOYEES_URL  = f"{BASE_URL}/api/employees"
IMPORT_URL     = f"{BASE_URL}/api/employees/import"
NOTIF_URL      = f"{BASE_URL}/api/notification/send"
HISTORY_URL    = f"{BASE_URL}/api/history"

ADMIN_USER = "admin"
_PW_CANDIDATES = ["pass123", "pass1234"]
SEED_XLSX = Path("/app/backend/data/employees_seed.xlsx")


# ---- Fixtures --------------------------------------------------------------
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


# ---- Auth-gating tests (roster endpoints) ---------------------------------
class TestAuthGating:
    def test_departments_requires_auth(self):
        r = requests.get(DEPTS_URL)
        assert r.status_code == 401, r.text

    def test_employees_requires_auth(self):
        r = requests.get(EMPLOYEES_URL)
        assert r.status_code == 401, r.text

    def test_import_requires_auth(self):
        r = requests.post(IMPORT_URL, files={"file": ("x.xlsx", b"",
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 401, r.text

    def test_import_without_csrf_returns_403(self, auth):
        s = requests.Session()
        s.cookies.update(auth.cookies.get_dict())
        with SEED_XLSX.open("rb") as f:
            r = s.post(IMPORT_URL, files={"file": ("employees_seed.xlsx", f.read(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"


# ---- Departments listing ---------------------------------------------------
class TestDepartments:
    def test_departments_shape_and_counts(self, auth):
        r = auth.get(DEPTS_URL)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and isinstance(data["items"], list)
        counts = {d["name"]: d["count"] for d in data["items"]}
        assert counts.get("Research Unit") == 45, counts
        assert counts.get("Support Staff") == 5, counts
        assert counts.get("Business & Product") == 2, counts


# ---- Employees listing -----------------------------------------------------
class TestEmployees:
    def test_employees_all(self, auth):
        r = auth.get(EMPLOYEES_URL)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["count"] >= 52
        assert data["count"] == len(data["items"])
        first = data["items"][0]
        for k in ("name", "email", "department", "team", "designation"):
            assert k in first
        assert "_id" not in first

    def test_employees_filtered_business_product(self, auth):
        r = auth.get(EMPLOYEES_URL, params={"department": "Business & Product"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["count"] == 2
        assert all(e["department"] == "Business & Product" for e in data["items"])

    def test_employees_unknown_department_empty(self, auth):
        r = auth.get(EMPLOYEES_URL, params={"department": "Not A Real Dept"})
        assert r.status_code == 200, r.text
        assert r.json()["count"] == 0


# ---- POST /api/notification/send — auth + CSRF ----------------------------
class TestNotifSendAuthGating:
    def test_notif_send_requires_auth(self):
        r = requests.post(NOTIF_URL, json={
            "subject": "x", "html": "<p>x</p>",
            "recipients": [{"email": "qa1@example.com", "name": "QA1"}],
        })
        assert r.status_code == 401, r.text

    def test_notif_send_without_csrf_returns_403(self, auth):
        s = requests.Session()
        s.cookies.update(auth.cookies.get_dict())
        r = s.post(NOTIF_URL, json={
            "subject": "x", "html": "<p>x</p>",
            "recipients": [{"email": "qa1@example.com", "name": "QA1"}],
        })
        assert r.status_code == 403, f"expected 403 got {r.status_code}: {r.text[:200]}"


# ---- POST /api/notification/send — validation -----------------------------
class TestNotifSendValidation:
    def test_notif_send_empty_subject_422(self, auth):
        r = auth.post(NOTIF_URL, json={
            "subject": "", "html": "<p>hello</p>",
            "recipients": [{"email": "qa1@example.com", "name": "QA1"}],
        })
        assert r.status_code == 422, r.text

    def test_notif_send_empty_recipients_422(self, auth):
        r = auth.post(NOTIF_URL, json={
            "subject": "hi", "html": "<p>hello</p>",
            "recipients": [],
        })
        assert r.status_code == 422, r.text

    def test_notif_send_empty_html_422(self, auth):
        r = auth.post(NOTIF_URL, json={
            "subject": "hi", "html": "",
            "recipients": [{"email": "qa1@example.com", "name": "QA1"}],
        })
        assert r.status_code == 422, r.text


# ---- POST /api/notification/send — happy path -----------------------------
class TestNotifSendHappyPath:
    """Batch of 3 recipients. Expects sent=3 total=3 failed=0 and a history row."""

    def test_notif_send_batch_of_three(self, auth):
        recipients = [
            {"email": "qa1@example.com", "name": "QA One"},
            {"email": "qa2@example.com", "name": "QA Two"},
            {"email": "qa3@example.com", "name": "QA Three"},
        ]
        r = auth.post(NOTIF_URL, json={
            "subject":    "TEST_notif batch of 3",
            "html":       "<p>Hi {name}, this is a notification test.</p>",
            "recipients": recipients,
            "cc":         ["owner1@blubridge.com"],
            "department": "Business & Product",
        })
        assert r.status_code == 200, r.text
        j = r.json()
        # Contract shape
        for k in ("ok", "sent", "failed", "total", "details", "history_id"):
            assert k in j, f"missing key {k} in {j}"
        assert j["total"] == 3
        assert j["sent"] == 3, f"expected sent=3 got {j['sent']} — details={j['details']}"
        assert j["failed"] == 0
        assert j["ok"] is True
        assert len(j["details"]["sent"]) == 3
        assert len(j["details"]["failed"]) == 0
        # Each successful send should carry the SendGrid message_id (may be
        # empty string if SendGrid didn't set the header — but the key must exist).
        for s in j["details"]["sent"]:
            assert "email" in s
            assert "message_id" in s
        history_id = j["history_id"]
        assert isinstance(history_id, str) and len(history_id) > 0

        # Now verify the history entry exists and has the right shape.
        h = auth.get(HISTORY_URL, params={"type": "notification"})
        assert h.status_code == 200
        items = h.json()["items"]
        assert any(it["id"] == history_id for it in items), \
            f"history_id {history_id} not present in {[i['id'] for i in items[:5]]}"
        entry = next(it for it in items if it["id"] == history_id)
        assert entry["type"] == "notification"
        summary = entry["summary"]
        assert summary["subject"] == "TEST_notif batch of 3"
        assert summary["department"] == "Business & Product"
        assert summary["sent"] == 3
        assert summary["failed"] == 0
        assert summary["total"] == 3
        assert sorted(summary["recipients"]) == sorted([r["email"] for r in recipients])


# ---- POST /api/notification/send — mixed valid + invalid ------------------
class TestNotifSendInvalidEmails:
    """Invalid-email addresses should be sorted into failed[] with a helpful message."""

    def test_notif_send_invalid_email_goes_to_failed(self, auth):
        r = auth.post(NOTIF_URL, json={
            "subject":    "TEST_notif invalid mixed",
            "html":       "<p>Hi {name}</p>",
            "recipients": [
                {"email": "qa_valid@example.com", "name": "V"},
                {"email": "not-an-email",         "name": "X"},   # no @
            ],
        })
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["total"] == 2
        assert j["failed"] >= 1, j
        failed_emails = [f["email"] for f in j["details"]["failed"]]
        assert "not-an-email" in failed_emails
        # The failure record must include a helpful error string
        for f in j["details"]["failed"]:
            assert f.get("error"), f
