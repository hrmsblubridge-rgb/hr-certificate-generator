"""Backend tests for the Doc module (letterhead PDF renderer + importer).

Covers:
- Auth gating on all /api/doc/* endpoints (401 unauthenticated)
- POST /api/doc/preview  (single page + count)
- POST /api/doc/generate (single & multi-page, signature block)
- Programmatic PDF inspection with PyMuPDF:
    * Paragraph keep-together (no paragraph split across pages)
    * Heading keep-with-next (heading+next para on same page)
    * Long table (no row cut, header repeats)
    * Signature placement (image bbox y1 <= CONTENT_BOTTOM)
    * 5+ page: every page has letterhead artwork (drawings/images)
    * preview == PDF (page counts match)
    * Content stays inside safe area (y >= 112 top, y <= 786 bottom)
- POST /api/doc/import   (docx/pdf/txt supported, xlsx rejected 415)
- History integration: 'doc' entries appear and can be downloaded
- REGRESSION: certificate/offer/ack/offer-email preview endpoints still 200
"""
import io
import os
import zipfile
from pathlib import Path

import pytest
import pymupdf as fitz
import requests

if not os.environ.get("REACT_APP_BACKEND_URL"):
    env_file = Path("/app/frontend/.env")
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                os.environ["REACT_APP_BACKEND_URL"] = line.split("=", 1)[1].strip()

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")

LETTERHEAD_PATH = Path("/app/backend/static/doc/Letterhead_Curve.pdf")
CONTENT_TOP = 112.0
CONTENT_BOTTOM = 786.0


# ---- session fixture -----------------------------------------------------
@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"username": "admin", "password": "pass123"})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    csrf = r.json().get("csrf_token") or s.cookies.get("hrcert_csrf")
    s.headers.update({"X-CSRF-Token": csrf})
    return s


# ---- Auth gating ---------------------------------------------------------
class TestAuth:
    def test_import_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/doc/import",
                          files={"file": ("a.txt", b"hi", "text/plain")})
        assert r.status_code == 401

    def test_preview_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/doc/preview",
                          json={"html": "<p>hi</p>"})
        assert r.status_code == 401

    def test_generate_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/doc/generate",
                          json={"html": "<p>hi</p>"})
        assert r.status_code == 401


# ---- Basic preview/generate ---------------------------------------------
class TestPreviewGenerate:
    def test_single_page_preview(self, sess):
        r = sess.post(f"{BASE_URL}/api/doc/preview",
                      json={"html": "<h1>Test</h1><p>Small content.</p>",
                            "include_signature": False})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["count"] == 1
        assert len(body["pages"]) == 1
        assert body["pages"][0].startswith("data:image/jpeg;base64,")

    def test_generate_returns_pdf(self, sess):
        r = sess.post(f"{BASE_URL}/api/doc/generate",
                      json={"name": "TEST_QA", "html": "<p>Hello world</p>",
                            "include_signature": False})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert "TEST_QA" in r.headers.get("content-disposition", "")
        # Parseable
        with fitz.open(stream=r.content, filetype="pdf") as doc:
            assert doc.page_count == 1

    def test_generate_empty_html_400(self, sess):
        r = sess.post(f"{BASE_URL}/api/doc/generate",
                      json={"html": "<p></p>", "include_signature": False})
        assert r.status_code == 400

    def test_filename_fallback(self, sess):
        r = sess.post(f"{BASE_URL}/api/doc/generate",
                      json={"name": "", "html": "<p>Fallback</p>",
                            "include_signature": False})
        assert r.status_code == 200
        cd = r.headers.get("content-disposition", "")
        assert "BluBridge_Document" in cd

    def test_preview_matches_generate_page_count(self, sess):
        html = "<h2>Long doc</h2>" + ("<p>" + "Filler paragraph. " * 40 + "</p>") * 12
        payload = {"html": html, "include_signature": True, "name": "TEST_match"}
        p = sess.post(f"{BASE_URL}/api/doc/preview", json=payload).json()
        g = sess.post(f"{BASE_URL}/api/doc/generate", json=payload)
        assert g.status_code == 200
        with fitz.open(stream=g.content, filetype="pdf") as doc:
            assert doc.page_count == p["count"], (doc.page_count, p["count"])


# ---- Letterhead & safe area on every page --------------------------------
def _letterhead_signature() -> tuple[int, int]:
    """Reference (drawings_count, images_count) from the letterhead itself."""
    with fitz.open(str(LETTERHEAD_PATH)) as d:
        page = d[0]
        return len(page.get_drawings()), len(page.get_images(full=True))


class TestLetterheadOnEveryPage:
    def test_5_plus_pages_letterhead_present(self, sess):
        # Make sure we generate 5+ pages
        big_html = "".join(
            f"<h3>Section {i}</h3>" + ("<p>" + "Sentence body content. " * 30 + "</p>") * 3
            for i in range(1, 20)
        )
        r = sess.post(f"{BASE_URL}/api/doc/generate",
                      json={"name": "TEST_5page", "html": big_html,
                            "include_signature": True})
        assert r.status_code == 200
        ref_draws, ref_imgs = _letterhead_signature()
        with fitz.open(stream=r.content, filetype="pdf") as doc:
            assert doc.page_count >= 5, f"expected >=5 pages, got {doc.page_count}"
            for i, page in enumerate(doc):
                # Every page must carry the letterhead artwork. Because the
                # implementation uses show_pdf_page(), the vector drawings
                # from the letterhead appear on every page.
                # Signature page may add 1 extra image (director signature).
                n_imgs = len(page.get_images(full=True))
                n_draws = len(page.get_drawings())
                assert n_draws >= ref_draws * 0.5, \
                    f"page {i+1} missing letterhead drawings ({n_draws} < {ref_draws})"
                assert n_imgs >= ref_imgs, \
                    f"page {i+1} letterhead images missing ({n_imgs} < {ref_imgs})"


# ---- Paragraph keep-together ---------------------------------------------
class TestKeepTogether:
    def test_no_paragraph_split_across_pages(self, sess):
        # Multiple paragraphs with recognisable markers.
        paragraphs = [f"PARA_{i}_START " + ("filler " * 30) + f"PARA_{i}_END"
                      for i in range(1, 25)]
        html = "".join(f"<p>{p}</p>" for p in paragraphs)
        r = sess.post(f"{BASE_URL}/api/doc/generate",
                      json={"html": html, "include_signature": False,
                            "name": "TEST_keep"})
        assert r.status_code == 200
        with fitz.open(stream=r.content, filetype="pdf") as doc:
            # For each paragraph, START & END markers must be on same page.
            page_texts = [p.get_text() for p in doc]
            for i in range(1, 25):
                start_pages = [pi for pi, t in enumerate(page_texts)
                               if f"PARA_{i}_START" in t]
                end_pages = [pi for pi, t in enumerate(page_texts)
                             if f"PARA_{i}_END" in t]
                assert start_pages == end_pages, \
                    f"paragraph {i} split: start={start_pages} end={end_pages}"

    def test_content_within_safe_area(self, sess):
        html = "".join(f"<p>Line {i} " + ("x " * 20) + "</p>" for i in range(1, 80))
        r = sess.post(f"{BASE_URL}/api/doc/generate",
                      json={"html": html, "include_signature": False,
                            "name": "TEST_safe"})
        assert r.status_code == 200
        with fitz.open(stream=r.content, filetype="pdf") as doc:
            for pi, page in enumerate(doc):
                blocks = page.get_text("blocks")
                for b in blocks:
                    x0, y0, x1, y1, text, *_ = b
                    txt = (text or "").strip()
                    # skip letterhead artefacts by matching our own "Line N" markers
                    if not txt.startswith("Line "):
                        continue
                    assert y0 >= CONTENT_TOP - 2, \
                        f"page {pi+1}: block starts above safe area at y={y0}: {txt[:40]}"
                    assert y1 <= CONTENT_BOTTOM + 4, \
                        f"page {pi+1}: block ends below safe area at y={y1}: {txt[:40]}"


# ---- Heading keep-with-next ----------------------------------------------
class TestHeadingKeepWithNext:
    def test_heading_with_following_paragraph_same_page(self, sess):
        # Fill page 1 near bottom, then heading + paragraph.
        filler = "<p>" + ("filler content. " * 22) + "</p>"
        html = (filler * 24) + "<h2>UNIQUE_HEADING_XYZ</h2>" + \
               "<p>UNIQUE_BODY_XYZ follows the heading and must stay with it.</p>"
        r = sess.post(f"{BASE_URL}/api/doc/generate",
                      json={"html": html, "include_signature": False,
                            "name": "TEST_head"})
        assert r.status_code == 200
        with fitz.open(stream=r.content, filetype="pdf") as doc:
            head_page = body_page = None
            for pi, p in enumerate(doc):
                t = p.get_text()
                if "UNIQUE_HEADING_XYZ" in t:
                    head_page = pi
                if "UNIQUE_BODY_XYZ" in t:
                    body_page = pi
            assert head_page is not None and body_page is not None
            assert head_page == body_page, \
                f"heading orphaned: head p{head_page}, body p{body_page}"


# ---- Long table ----------------------------------------------------------
class TestLongTable:
    def test_table_rows_not_cut_header_repeats(self, sess):
        rows_html = "".join(
            f"<tr><td>ROW_{i}_A</td><td>ROW_{i}_B</td><td>ROW_{i}_C</td></tr>"
            for i in range(1, 41)
        )
        html = ("<h2>Big table</h2>"
                "<table><tr><th>H_ALPHA</th><th>H_BETA</th><th>H_GAMMA</th></tr>"
                + rows_html + "</table>")
        r = sess.post(f"{BASE_URL}/api/doc/generate",
                      json={"html": html, "include_signature": False,
                            "name": "TEST_table"})
        assert r.status_code == 200
        with fitz.open(stream=r.content, filetype="pdf") as doc:
            assert doc.page_count >= 2, "table should span >=2 pages"
            page_texts = [p.get_text() for p in doc]
            # each row's 3 cells on exactly one page
            for i in range(1, 41):
                on = [pi for pi, t in enumerate(page_texts)
                      if all(f"ROW_{i}_{c}" in t for c in ("A", "B", "C"))]
                assert len(on) == 1, f"row {i} cut or missing (pages={on})"
            # header repeats on every page that has body rows
            pages_with_rows = [pi for pi, t in enumerate(page_texts) if "ROW_" in t]
            assert len(pages_with_rows) >= 2
            for pi in pages_with_rows:
                t = page_texts[pi]
                assert "H_ALPHA" in t and "H_BETA" in t and "H_GAMMA" in t, \
                    f"header not repeated on page {pi+1}"


# ---- Signature block -----------------------------------------------------
class TestSignature:
    def test_signature_within_content_area(self, sess):
        html = ("<p>" + ("filler " * 30) + "</p>") * 20
        r = sess.post(f"{BASE_URL}/api/doc/generate",
                      json={"html": html, "include_signature": True,
                            "name": "TEST_sig"})
        assert r.status_code == 200
        ref_img_count = _letterhead_signature()[1]
        with fitz.open(stream=r.content, filetype="pdf") as doc:
            # Find image bboxes on every page; the signature adds one extra
            found = False
            for pi, page in enumerate(doc):
                imgs = page.get_images(full=True)
                if len(imgs) > ref_img_count:
                    # get image bboxes
                    for img in imgs:
                        xref = img[0]
                        try:
                            rects = page.get_image_rects(xref)
                        except Exception:
                            rects = []
                        for rect in rects:
                            if rect.y1 <= CONTENT_BOTTOM + 1 and rect.y0 >= CONTENT_TOP - 1:
                                found = True
            assert found, "signature image not found within safe content area"


# ---- Import (.docx/.pdf/.txt/.xlsx) -------------------------------------
def _build_minimal_docx() -> bytes:
    """Build a tiny in-memory .docx with a heading, bold/italic run, and
    a bullet list. Uses raw XML to avoid python-docx dependency for tests
    (which lives on the backend anyway, but keeps this self-contained)."""
    from docx import Document
    doc = Document()
    doc.add_heading("HEADING_ONE", level=1)
    p = doc.add_paragraph()
    p.add_run("plain ")
    p.add_run("bold").bold = True
    p.add_run(" ")
    p.add_run("italic").italic = True
    p.add_run(" ")
    r = p.add_run("underline"); r.underline = True
    doc.add_paragraph("Bullet A", style="List Bullet")
    doc.add_paragraph("Bullet B", style="List Bullet")
    doc.add_paragraph("Number 1", style="List Number")
    tbl = doc.add_table(rows=2, cols=2)
    tbl.rows[0].cells[0].text = "TblHdrA"
    tbl.rows[0].cells[1].text = "TblHdrB"
    tbl.rows[1].cells[0].text = "TblRow1A"
    tbl.rows[1].cells[1].text = "TblRow1B"
    buf = io.BytesIO(); doc.save(buf); return buf.getvalue()


class TestImport:
    def test_import_docx(self, sess):
        data = _build_minimal_docx()
        r = sess.post(f"{BASE_URL}/api/doc/import",
                      files={"file": ("test.docx", data,
                                      "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
        assert r.status_code == 200, r.text
        html = r.json()["html"]
        assert "HEADING_ONE" in html
        assert "<h1>" in html
        assert "<b>bold</b>" in html
        assert "<i>italic</i>" in html
        assert "<u>underline</u>" in html
        assert "<ul>" in html and "Bullet A" in html
        assert "<ol>" in html and "Number 1" in html
        assert "<table>" in html and "TblHdrA" in html and "TblRow1A" in html

    def test_import_txt(self, sess):
        r = sess.post(f"{BASE_URL}/api/doc/import",
                      files={"file": ("plain.txt", b"First para.\n\nSecond para.", "text/plain")})
        assert r.status_code == 200
        html = r.json()["html"]
        assert "First para." in html and "Second para." in html
        assert "<p>" in html

    def test_import_pdf(self, sess):
        # build a tiny PDF with a known string
        with fitz.open() as d:
            p = d.new_page()
            p.insert_text((72, 100), "PDF_IMPORT_MARKER text here.")
            data = d.tobytes()
        r = sess.post(f"{BASE_URL}/api/doc/import",
                      files={"file": ("t.pdf", data, "application/pdf")})
        assert r.status_code == 200
        assert "PDF_IMPORT_MARKER" in r.json()["html"]

    def test_import_unsupported_xlsx_415(self, sess):
        # build a minimal xlsx blob
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("dummy", "x")
        r = sess.post(f"{BASE_URL}/api/doc/import",
                      files={"file": ("bad.xlsx", buf.getvalue(),
                                      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 415


# ---- History integration -------------------------------------------------
class TestHistory:
    def test_doc_appears_in_history_and_downloads(self, sess):
        r = sess.post(f"{BASE_URL}/api/doc/generate",
                      json={"name": "TEST_hist_doc", "html": "<p>History test</p>",
                            "include_signature": False})
        assert r.status_code == 200
        hist = sess.get(f"{BASE_URL}/api/history?type=doc").json()
        assert any(i.get("name") == "TEST_hist_doc" for i in hist["items"])
        entry = next(i for i in hist["items"] if i.get("name") == "TEST_hist_doc")
        d = sess.get(f"{BASE_URL}/api/history/{entry['id']}/download")
        assert d.status_code == 200
        assert d.headers["content-type"] == "application/pdf"
        assert d.content[:4] == b"%PDF"


# ---- Regression: other modules still work --------------------------------
class TestRegression:
    def test_certificate_generate(self, sess):
        r = sess.post(f"{BASE_URL}/api/template/generate", json={
            "name": "TEST User", "designation": "AI Analyst",
            "commenced": "01.01.2026", "concluded": "31.01.2026", "gender": "male"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"

    def test_offer_generate(self, sess):
        r = sess.post(f"{BASE_URL}/api/offer/generate", json={
            "ref_code": "REF1", "date": "2026-01-01", "name": "TEST User",
            "addr1": "L1", "addr2": "L2", "addr3": "L3",
            "phone": "1234567890", "email": "t@e.com",
            "designation": "Engineer", "salary_amount": "100000",
            "salary_words": "One lakh"})
        assert r.status_code == 200

    def test_ack_generate(self, sess):
        r = sess.post(f"{BASE_URL}/api/ack/generate", json={
            "date": "2026-01-01", "name": "TEST User",
            "marksheet_type": "Original Marksheet"})
        assert r.status_code == 200

    def test_offer_email_preview(self, sess):
        r = sess.post(f"{BASE_URL}/api/offer-email/preview", json={
            "title": "Mr.", "name": "TEST User", "email": "t@e.com",
            "phone": "9999999999", "date": "2026-01-15", "cur_date": "2026-01-01",
            "reference_number": "REF1", "designation": "Engineer",
            "address_line1": "L1", "address_line2": "L2", "address_line3": "L3",
            "mode": "standard", "ctc_yearly": 500000})
        assert r.status_code == 200

    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200
