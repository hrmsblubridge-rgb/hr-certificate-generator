"""Backend tests for Internship Certificate gender feature.

Covers:
- 422 on missing gender / invalid gender
- 200 + valid PDF for male/female with pronoun text checks
- Female baselines for static rebuilt lines (y=269, y=289, y=322) within ±1pt
- GET /api/history reflects new entry with summary.gender
"""
import io
import os
import re
import pytest
import requests
import pymupdf as fitz

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://cert-hr-template.preview.emergentagent.com").rstrip("/")
ADMIN_USER = "admin"
ADMIN_PW = "pass123"


@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": ADMIN_USER, "password": ADMIN_PW},
               timeout=20)
    if r.status_code != 200:
        pytest.skip(f"Login failed: {r.status_code} {r.text}")
    data = r.json()
    s.headers.update({
        "Content-Type": "application/json",
        "X-CSRF-Token": data["csrf_token"],
    })
    return s


def _post_generate(session, payload):
    return session.post(f"{BASE_URL}/api/template/generate", json=payload, timeout=60)


# ---- Validation -----------------------------------------------------------
class TestValidation:
    def test_missing_gender_returns_422(self, auth_session):
        r = _post_generate(auth_session, {
            "name": "TEST_NoGender",
            "designation": "Intern",
            "commenced": "01.01.2025",
            "concluded": "02.02.2025",
        })
        assert r.status_code == 422, r.text

    def test_invalid_gender_other_returns_422(self, auth_session):
        r = _post_generate(auth_session, {
            "name": "TEST_OtherGender",
            "designation": "Intern",
            "commenced": "01.01.2025",
            "concluded": "02.02.2025",
            "gender": "other",
        })
        assert r.status_code == 422, r.text


# ---- Male PDF generation --------------------------------------------------
class TestMalePDF:
    def test_male_generates_valid_pdf_with_his_pronouns(self, auth_session):
        payload = {
            "name": "TEST_MaleUser",
            "designation": "AI Research Intern",
            "commenced": "28.07.2025",
            "concluded": "24.11.2025",
            "gender": "male",
        }
        r = _post_generate(auth_session, payload)
        assert r.status_code == 200, r.text
        assert r.content[:4] == b"%PDF"

        doc = fitz.open(stream=r.content, filetype="pdf")
        text = doc[0].get_text()
        doc.close()
        # normalize whitespace
        flat = re.sub(r"\s+", " ", text)

        assert "has completed his internship" in flat, f"Missing 'his internship'. Got: {flat[:400]}"
        assert "His internship tenure" in flat, "Missing 'His internship tenure'"
        assert "During his internship, he demonstrated" in flat, "Missing male para-2"
        # Para-3 typo is now corrected: "him future" → "his future"
        assert "We wish him all the best in his future endeavors." in flat, \
            f"Missing male para-3 (with 'his future' fix). Got: {flat}"


# ---- Female PDF generation ------------------------------------------------
class TestFemalePDF:
    @pytest.fixture(scope="class")
    def female_pdf_bytes(self, auth_session):
        payload = {
            "name": "TEST_FemaleUser",
            "designation": "AI Research Intern",
            "commenced": "28.07.2025",
            "concluded": "24.11.2025",
            "gender": "female",
        }
        r = _post_generate(auth_session, payload)
        assert r.status_code == 200, r.text
        assert r.content[:4] == b"%PDF"
        return r.content

    def test_female_pronouns_present(self, female_pdf_bytes):
        doc = fitz.open(stream=female_pdf_bytes, filetype="pdf")
        text = doc[0].get_text()
        doc.close()
        flat = re.sub(r"\s+", " ", text)
        assert "has completed her internship" in flat, f"Missing 'her internship'. Got: {flat[:400]}"
        assert "Her internship tenure" in flat
        assert "During her internship, she demonstrated" in flat
        assert "We wish her all the best in her future endeavors." in flat, \
            f"Missing female para-3. Got: {flat}"

    def test_female_baselines_match_original(self, female_pdf_bytes):
        """Verify static rebuilt lines at y=269 (line3), y=289 (initiatives.), y=322 (line4)
        match within ±1pt."""
        doc = fitz.open(stream=female_pdf_bytes, filetype="pdf")
        d = doc[0].get_text("dict")
        doc.close()
        # collect all line baseline-y positions and their text
        lines = []
        for block in d.get("blocks", []):
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                if not spans:
                    continue
                txt = "".join(s["text"] for s in spans).strip()
                # bbox top y (matches spec's "y=269 (line3), y=289, y=322")
                y = line["bbox"][1]
                lines.append((y, txt))

        def find_y(predicate):
            for y, t in lines:
                if predicate(t):
                    return y
            return None

        y_line3 = find_y(lambda t: t.startswith("During her internship") or "During her internship" in t)
        y_initiatives = find_y(lambda t: t == "initiatives." or t.endswith("initiatives."))
        y_line4 = find_y(lambda t: t.startswith("We wish her"))

        # debug print on failure
        assert y_line3 is not None, f"Line3 not found. Lines: {lines}"
        assert y_initiatives is not None, f"'initiatives.' not found. Lines: {lines}"
        assert y_line4 is not None, f"Line4 not found. Lines: {lines}"

        # Original baselines per spec
        assert abs(y_line3 - 269) <= 1.0, f"line3 baseline {y_line3} not within ±1 of 269"
        assert abs(y_initiatives - 289) <= 1.0, f"initiatives baseline {y_initiatives} not within ±1 of 289"
        assert abs(y_line4 - 322) <= 1.0, f"line4 baseline {y_line4} not within ±1 of 322"


# ---- History persistence ---------------------------------------------------
class TestHistory:
    def test_history_contains_gender(self, auth_session):
        # Create both male & female entries
        for g in ("male", "female"):
            r = _post_generate(auth_session, {
                "name": f"TEST_HistoryUser_{g}",
                "designation": "Intern",
                "commenced": "01.01.2025",
                "concluded": "02.02.2025",
                "gender": g,
            })
            assert r.status_code == 200

        r = auth_session.get(f"{BASE_URL}/api/history?type=certificate&limit=50", timeout=20)
        assert r.status_code == 200
        items = r.json().get("items", [])

        m = next((i for i in items if i.get("name") == "TEST_HistoryUser_male"), None)
        f = next((i for i in items if i.get("name") == "TEST_HistoryUser_female"), None)

        assert m is not None, "Male history entry missing"
        assert f is not None, "Female history entry missing"
        assert m["summary"]["gender"] == "male", f"Expected male, got {m['summary']}"
        assert f["summary"]["gender"] == "female", f"Expected female, got {f['summary']}"
