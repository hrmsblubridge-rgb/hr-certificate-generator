"""Deployment fix verification (iteration_6).

Verifies:
1. requirements.txt pins openpyxl==3.1.5 and python-multipart==0.0.32
2. Clean venv can import server + employees (no ModuleNotFoundError)
3. GET /api/employees/departments returns 3 seeded departments (proves openpyxl parsed the .xlsx at boot)
4. POST /api/employees/import re-uploads the seed xlsx and returns HTTP 200 with inserted=52 (proves python-multipart is wired)
5. Regression: POST /api/notification/send with valid recipients still returns ok=true
6. Regression: /var/log/supervisor/backend.err.log has no new missing-package errors
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import requests


def _read_backend_url() -> str:
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    # Fallback: read from /app/frontend/.env (same value the browser uses).
    env_path = Path("/app/frontend/.env")
    if env_path.is_file():
        for line in env_path.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().rstrip("/")
    raise RuntimeError("REACT_APP_BACKEND_URL not set and not found in frontend/.env")


BASE_URL = _read_backend_url()
REQ_FILE = Path("/app/backend/requirements.txt")
SEED_XLSX = Path("/app/backend/data/employees_seed.xlsx")

ADMIN_USER = "admin"
ADMIN_PASS = "pass123"


# --- 1. requirements.txt pinning -------------------------------------------
class TestRequirementsPinning:
    def test_openpyxl_pinned_exact(self):
        content = REQ_FILE.read_text()
        assert re.search(r"^openpyxl==3\.1\.5\b", content, re.MULTILINE), \
            "openpyxl==3.1.5 not pinned in requirements.txt"

    def test_python_multipart_pinned_exact(self):
        content = REQ_FILE.read_text()
        assert re.search(r"^python-multipart==0\.0\.32\b", content, re.MULTILINE), \
            "python-multipart==0.0.32 not pinned in requirements.txt"


# --- 2. Clean venv smoke test ----------------------------------------------
class TestCleanVenvImport:
    def test_clean_venv_imports_server_and_employees(self):
        """Reproduce the Render build: fresh venv, install requirements.txt only, import."""
        venv = "/tmp/verify_venv"
        # venv is already built by the shell command in the wrapper; ensure it works
        # If it doesn't exist, build it now.
        if not Path(f"{venv}/bin/python").exists():
            subprocess.run(["python3", "-m", "venv", venv], check=True)
            subprocess.run(
                [f"{venv}/bin/pip", "install", "-q", "-r", str(REQ_FILE)],
                check=True,
            )
        result = subprocess.run(
            [
                f"{venv}/bin/python",
                "-c",
                "import server, employees; from server import app; print(len(app.routes))",
            ],
            cwd="/app/backend",
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"import failed:\nSTDOUT:{result.stdout}\nSTDERR:{result.stderr}"
        )
        # Expect 28 routes per the review request
        assert "28" in result.stdout, f"expected 28 routes, got:\n{result.stdout}"
        # No ModuleNotFoundError or ImportError anywhere in stderr
        assert "ModuleNotFoundError" not in result.stderr
        assert "ImportError" not in result.stderr


# --- 3-5. Runtime API verification -----------------------------------------
@pytest.fixture(scope="module")
def auth_session():
    """Log in as admin and return a requests.Session with cookie + CSRF header wired."""
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
        timeout=15,
    )
    if r.status_code != 200:
        pytest.skip(f"Login failed: {r.status_code} {r.text[:200]}")
    csrf = s.cookies.get("hrcert_csrf")
    if csrf:
        s.headers.update({"X-CSRF-Token": csrf})
    return s


class TestDepartmentsEndpoint:
    """Proves openpyxl parsed employees_seed.xlsx at server boot."""

    def test_departments_returns_three_seeded_departments(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/employees/departments", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        # API shape is {"items": [{name, count}, ...]}
        data = body["items"] if isinstance(body, dict) and "items" in body else body
        assert isinstance(data, list) and len(data) >= 3, data
        by_name = {d["name"]: d["count"] for d in data}
        assert by_name.get("Research Unit") == 45, by_name
        assert by_name.get("Support Staff") == 5, by_name
        assert by_name.get("Business & Product") == 2, by_name


class TestEmployeesImport:
    """Proves python-multipart is wired (FastAPI UploadFile at runtime)."""

    def test_import_seed_xlsx_returns_ok_and_inserted_52(self, auth_session):
        assert SEED_XLSX.is_file(), f"seed file missing at {SEED_XLSX}"
        with SEED_XLSX.open("rb") as fh:
            files = {
                "file": (
                    "employees_seed.xlsx",
                    fh,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            }
            r = auth_session.post(
                f"{BASE_URL}/api/employees/import",
                files=files,
                timeout=30,
            )
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        body = r.json()
        assert body.get("ok") is True, body
        assert body.get("inserted") == 52, body


class TestNotificationSendRegression:
    """Regression: notification/send still works with valid recipients."""

    def test_notif_send_two_valid_recipients(self, auth_session):
        payload = {
            "subject": "TEST_iter6 deployment fix regression — please ignore",
            "html": "<p>Hello {name}, this is a deployment-fix regression test.</p>",
            "recipients": [
                {"name": "QA One", "email": "qa1@example.com"},
                {"name": "QA Two", "email": "qa2@example.com"},
            ],
            "department": "Business & Product",
        }
        r = auth_session.post(
            f"{BASE_URL}/api/notification/send",
            json=payload,
            timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
        data = r.json()
        assert data.get("ok") is True, data
        assert data.get("total") == 2, data
        assert data.get("sent") == 2, data
        assert data.get("failed") == 0, data


# --- 6. Supervisor log regression ------------------------------------------
class TestSupervisorLogClean:
    def test_no_missing_package_errors_in_backend_err_log(self):
        log_path = "/var/log/supervisor/backend.err.log"
        if not Path(log_path).is_file():
            pytest.skip("backend.err.log missing")
        with open(log_path, "rb") as fh:
            # tail last ~200 lines
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 60_000))
            tail = fh.read().decode("utf-8", errors="replace")
        lines = tail.splitlines()[-200:]
        joined = "\n".join(lines)
        # These strings indicate the exact bug class we just fixed
        forbidden = [
            "ModuleNotFoundError: No module named 'openpyxl'",
            "ModuleNotFoundError: No module named 'multipart'",
            "Form data requires \"python-multipart\" to be installed",
        ]
        for msg in forbidden:
            assert msg not in joined, (
                f"Found forbidden error in backend.err.log tail: {msg}"
            )
