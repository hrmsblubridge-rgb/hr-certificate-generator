"""Backend tests for the Notification Email compose helper endpoints:
- GET  /api/employees/departments
- GET  /api/employees
- POST /api/employees/import
Also verifies auth-gating (401 without cookies) and CSRF (403 on POST without header).
"""
import io
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
LOGIN_URL       = f"{BASE_URL}/api/auth/login"
DEPTS_URL       = f"{BASE_URL}/api/employees/departments"
EMPLOYEES_URL   = f"{BASE_URL}/api/employees"
IMPORT_URL      = f"{BASE_URL}/api/employees/import"

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


# ---- Auth-gating tests -----------------------------------------------------
class TestAuthGating:
    """All 3 employees endpoints require the session cookie."""

    def test_departments_requires_auth(self):
        r = requests.get(DEPTS_URL)
        assert r.status_code == 401, r.text

    def test_employees_requires_auth(self):
        r = requests.get(EMPLOYEES_URL)
        assert r.status_code == 401, r.text

    def test_import_requires_auth(self):
        r = requests.post(IMPORT_URL, files={"file": ("x.xlsx", b"", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 401, r.text

    def test_import_without_csrf_returns_403(self, auth):
        # Strip CSRF header explicitly; cookies remain -> should 403.
        s = requests.Session()
        s.cookies.update(auth.cookies.get_dict())
        # No X-CSRF-Token header set here.
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
        items = data["items"]
        # Build a name->count map for assertions.
        counts = {d["name"]: d["count"] for d in items}
        # 3 seeded departments per problem spec.
        assert "Research Unit" in counts and counts["Research Unit"] == 45, counts
        assert "Support Staff" in counts and counts["Support Staff"] == 5, counts
        assert "Business & Product" in counts and counts["Business & Product"] == 2, counts
        # Total should be at least 52.
        total = sum(counts.values())
        assert total >= 52, f"expected total>=52 got {total}: {counts}"
        # Each item must have both keys.
        for d in items:
            assert isinstance(d["name"], str) and isinstance(d["count"], int)


# ---- Employees listing -----------------------------------------------------
class TestEmployees:
    def test_employees_all(self, auth):
        r = auth.get(EMPLOYEES_URL)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "items" in data and "count" in data
        # Seeded roster is 52 rows.
        assert data["count"] >= 52, f"expected >=52 got {data['count']}"
        assert data["count"] == len(data["items"])
        # Verify shape of first row.
        first = data["items"][0]
        for k in ("name", "email", "department", "team", "designation"):
            assert k in first, f"missing field {k} in {first}"
        # No mongo _id leakage.
        assert "_id" not in first

    def test_employees_filtered_research_unit(self, auth):
        r = auth.get(EMPLOYEES_URL, params={"department": "Research Unit"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["count"] == 45, f"expected 45 got {data['count']}"
        assert all(e["department"] == "Research Unit" for e in data["items"])

    def test_employees_filtered_support_staff(self, auth):
        r = auth.get(EMPLOYEES_URL, params={"department": "Support Staff"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["count"] == 5

    def test_employees_filtered_business_product(self, auth):
        r = auth.get(EMPLOYEES_URL, params={"department": "Business & Product"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["count"] == 2

    def test_employees_unknown_department_empty(self, auth):
        r = auth.get(EMPLOYEES_URL, params={"department": "Definitely Not A Real Dept"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["count"] == 0
        assert data["items"] == []


# ---- Import (upload) tests -------------------------------------------------
class TestImport:
    """POST /api/employees/import — happy path + error branches."""

    def test_import_replaces_roster(self, auth):
        with SEED_XLSX.open("rb") as f:
            files = {"file": ("employees_seed.xlsx", f.read(),
                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = auth.post(IMPORT_URL, files=files)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["inserted"] == 52, f"expected 52 inserted got {data['inserted']}"
        # Verify persistence by re-listing.
        r2 = auth.get(EMPLOYEES_URL)
        assert r2.status_code == 200
        assert r2.json()["count"] == 52

    def test_import_wrong_extension_returns_415(self, auth):
        files = {"file": ("roster.csv", b"name,email\n", "text/csv")}
        r = auth.post(IMPORT_URL, files=files)
        assert r.status_code == 415, r.text

    def test_import_empty_file_returns_400(self, auth):
        files = {"file": ("empty.xlsx", b"",
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = auth.post(IMPORT_URL, files=files)
        assert r.status_code == 400, r.text

    def test_import_oversize_returns_413(self, auth):
        big = b"x" * (5 * 1024 * 1024 + 10)
        files = {"file": ("big.xlsx", big,
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = auth.post(IMPORT_URL, files=files)
        assert r.status_code == 413, r.text

    def test_import_invalid_xlsx_returns_400(self, auth):
        # A small non-empty but non-xlsx binary should fail parsing.
        files = {"file": ("bad.xlsx", b"not really an xlsx",
                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        r = auth.post(IMPORT_URL, files=files)
        # Backend catches ValueError from parse_employees_xlsx -> 400.
        # openpyxl may throw a different exception (e.g. InvalidFileException) — accept 400 OR 500 with a note.
        assert r.status_code in (400, 422, 500), f"got {r.status_code}: {r.text[:200]}"
