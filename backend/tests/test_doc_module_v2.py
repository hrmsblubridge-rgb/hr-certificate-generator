"""Iteration-8 extension tests for the Doc module.

Focus areas beyond the original 24 cases:
  * PAGE FILL: bottom-most drawn content per non-last page uses the safe area
    fully (leftover band <= 130pt) and no drawn content crosses y=765
  * NO UNNECESSARY BREAK: heading+paragraph that fits stays on page 1
  * PARAGRAPH INTEGRITY still holds across 3+ pages
  * DYNAMIC LINE HEIGHT: balanced middle page has line pitch >= last page
    and never breaches y=765
  * TABLE rules unchanged (40-row)
  * SIGNATURE STYLES: seal default / table / include_signature=false
  * DOCX FIDELITY: rich round-trip (bold/italic/underline/br/tab/
    sup/sub/strike/blank/lists/nested-format tables/alignment) with a
    "no source text dropped" invariant
  * LIST PARAGRAPH REGRESSION: styled "List Paragraph" without numbering
    stays a <p>, not <li>
  * PREVIEW == PDF page count parity for a 3+ page payload
"""
import io
import os
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

# Layout constants (must mirror doc_builder.py)
FOOTER_TOP = 801.0
CONTENT_BOTTOM = 763.0     # FOOTER_TOP - 38
FOOTER_CLEARANCE_HARD = 765.0
CONTENT_TOP = 108.0


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": "admin", "password": "pass123"})
    assert r.status_code == 200, r.text
    csrf = r.json().get("csrf_token") or s.cookies.get("hrcert_csrf")
    s.headers.update({"X-CSRF-Token": csrf})
    return s


def _blocks_by_page(pdf_bytes):
    """Return list-per-page of (y0, y1, text) tuples for TEXT blocks whose
    content includes our marker prefixes (so we ignore letterhead artefacts)."""
    out = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            page_blocks = []
            for b in page.get_text("blocks"):
                x0, y0, x1, y1, text, *_ = b
                page_blocks.append((y0, y1, (text or "").strip()))
            out.append(page_blocks)
    return out


# ---- PAGE FILL -----------------------------------------------------------
class TestPageFill:
    def test_no_unused_bottom_band_on_non_last_pages(self, sess):
        """Non-last pages should push content close to y=CONTENT_BOTTOM(763).
        We assert the last drawn marker-block's bottom y1 is >= 640 (i.e.
        leftover band <= ~125pt). No drawn content crosses y=765."""
        html = "".join(
            f"<p>MARK_{i} " + ("body text sample. " * 12) + "</p>"
            for i in range(1, 80)
        )
        r = sess.post(f"{BASE_URL}/api/doc/generate",
                      json={"name": "TEST_fill", "html": html,
                            "include_signature": False})
        assert r.status_code == 200
        pages = _blocks_by_page(r.content)
        assert len(pages) >= 2, "need multi-page for this test"

        for pi, blocks in enumerate(pages):
            marker_blocks = [(y0, y1, t) for (y0, y1, t) in blocks
                             if "MARK_" in t]
            # No content ever crosses the hard footer clearance (y=765)
            for y0, y1, t in marker_blocks:
                assert y1 <= FOOTER_CLEARANCE_HARD + 1.5, \
                    f"page {pi+1} content crosses footer: y1={y1} txt={t[:40]}"
            if pi == len(pages) - 1:
                continue  # last page can be short
            if not marker_blocks:
                continue
            last_y1 = max(y1 for _, y1, _ in marker_blocks)
            leftover = CONTENT_BOTTOM - last_y1
            # Requirement (2): no huge unused band (>130pt) on non-last pages
            assert leftover <= 130, \
                f"page {pi+1} wastes {leftover:.1f}pt at bottom (last y1={last_y1:.1f})"

    def test_no_unnecessary_break_heading_paragraph_pair(self, sess):
        """A H2 + short paragraph pair that fits in the remaining space of
        page 1 must NOT be pushed to page 2. Build a doc that's a single
        page in content and end with a heading+paragraph."""
        html = ("<p>" + ("intro text. " * 20) + "</p>") * 3
        html += "<h2>UNIQ_H8_STAYS</h2><p>UNIQ_H8_BODY should stay together on page 1.</p>"
        r = sess.post(f"{BASE_URL}/api/doc/generate",
                      json={"name": "TEST_nobreak", "html": html,
                            "include_signature": False})
        assert r.status_code == 200
        with fitz.open(stream=r.content, filetype="pdf") as doc:
            assert doc.page_count == 1, \
                f"expected 1 page, got {doc.page_count} (pair was pushed)"
            t = doc[0].get_text()
            assert "UNIQ_H8_STAYS" in t and "UNIQ_H8_BODY" in t


# ---- PARAGRAPH INTEGRITY ACROSS 3+ PAGES --------------------------------
class TestParagraphIntegrityMultiPage:
    def test_para_markers_same_page(self, sess):
        paragraphs = [f"P8_{i}_S " + ("filler " * 45) + f"P8_{i}_E"
                      for i in range(1, 40)]
        html = "".join(f"<p>{p}</p>" for p in paragraphs)
        r = sess.post(f"{BASE_URL}/api/doc/generate",
                      json={"name": "TEST_para3p", "html": html,
                            "include_signature": False})
        assert r.status_code == 200
        with fitz.open(stream=r.content, filetype="pdf") as doc:
            assert doc.page_count >= 3
            texts = [p.get_text() for p in doc]
            for i in range(1, 40):
                s = [pi for pi, t in enumerate(texts) if f"P8_{i}_S" in t]
                e = [pi for pi, t in enumerate(texts) if f"P8_{i}_E" in t]
                assert s == e, f"para {i} split s={s} e={e}"


# ---- DYNAMIC LINE HEIGHT --------------------------------------------------
class TestDynamicLineHeight:
    def test_balanced_page_line_pitch_ge_last_page(self, sess):
        """Generate a multi-page doc; measure the vertical pitch between
        consecutive text lines on the first (balanced) page vs the last
        (non-balanced) page. Balanced page pitch must be >= last-page pitch.
        Also verify no line crosses y=765."""
        html = "".join(f"<p>LN_{i} regular content sentence.</p>"
                       for i in range(1, 160))
        r = sess.post(f"{BASE_URL}/api/doc/generate",
                      json={"name": "TEST_lh", "html": html,
                            "include_signature": False})
        assert r.status_code == 200
        pages = _blocks_by_page(r.content)
        assert len(pages) >= 2

        def pitch(page_blocks):
            ys = sorted({round(y0, 1) for y0, _, t in page_blocks if "LN_" in t})
            if len(ys) < 6:
                return None
            diffs = [b - a for a, b in zip(ys[:-1], ys[1:]) if 4 < (b - a) < 40]
            diffs.sort()
            # median-ish
            return diffs[len(diffs) // 2] if diffs else None

        first_pitch = pitch(pages[0])
        last_pitch = pitch(pages[-1])
        assert first_pitch and last_pitch, \
            f"could not measure line pitch (first={first_pitch}, last={last_pitch})"
        # balanced page pitch >= last page pitch (allow tiny epsilon)
        assert first_pitch >= last_pitch - 0.15, \
            f"balanced page pitch {first_pitch} < last page pitch {last_pitch}"

        # And nothing crosses the hard footer clearance
        for pi, blocks in enumerate(pages):
            for y0, y1, t in blocks:
                if "LN_" in t:
                    assert y1 <= FOOTER_CLEARANCE_HARD + 1.5, \
                        f"page {pi+1} crossed footer (y1={y1})"


# ---- SIGNATURE STYLES ----------------------------------------------------
class TestSignatureStyles:
    def test_default_no_field_still_stamps_seal(self, sess):
        """Omit signature_style entirely — should default to 'seal' and
        embed an extra image beyond the letterhead's baseline image count."""
        with fitz.open("/app/backend/static/doc/Letterhead_Curve.pdf") as lh:
            ref_imgs = len(lh[0].get_images(full=True))
        r = sess.post(f"{BASE_URL}/api/doc/generate",
                      json={"name": "TEST_sig_default",
                            "html": "<p>Body.</p><p>More body.</p>",
                            "include_signature": True})
        assert r.status_code == 200
        with fitz.open(stream=r.content, filetype="pdf") as doc:
            has_extra = any(len(p.get_images(full=True)) > ref_imgs for p in doc)
            assert has_extra, "seal image not stamped when style omitted"

    def test_signature_table_renders_all_labels(self, sess):
        r = sess.post(f"{BASE_URL}/api/doc/generate", json={
            "name": "TEST_sig_table",
            "html": "<p>Agreement body content.</p>",
            "include_signature": True,
            "signature_style": "table",
            "sig_left":  {"label": "RECIPIENT / ADVISOR",
                          "name": "Jane Doe", "title": "Advisor"},
            "sig_right": {"label": "BLUBRIDGE TECHNOLOGIES PRIVATE LIMITED",
                          "name": "John Roe", "title": "Director"},
            "sig_date":  "01/01/2026",
        })
        assert r.status_code == 200
        with fitz.open(stream=r.content, filetype="pdf") as doc:
            all_text = "\n".join(p.get_text() for p in doc).replace("\xa0", " ")
            for needle in ["RECIPIENT / ADVISOR",
                           "BLUBRIDGE TECHNOLOGIES PRIVATE LIMITED",
                           "Signature:", "Name:", "Title:", "Date",
                           "Jane Doe", "John Roe", "01/01/2026"]:
                assert needle in all_text, f"missing signature-table field: {needle!r}"
            # Verify sig block sits on ONE page (find page with 'Jane Doe',
            # ensure 'John Roe' is on the same page).
            pages_with_left  = [pi for pi, p in enumerate(doc) if "Jane" in p.get_text()]
            pages_with_right = [pi for pi, p in enumerate(doc) if "John" in p.get_text()]
            assert pages_with_left == pages_with_right and len(pages_with_left) == 1, \
                f"signature block split: L={pages_with_left} R={pages_with_right}"

    def test_include_signature_false_stamps_neither(self, sess):
        with fitz.open("/app/backend/static/doc/Letterhead_Curve.pdf") as lh:
            ref_imgs = len(lh[0].get_images(full=True))
        r = sess.post(f"{BASE_URL}/api/doc/generate", json={
            "name": "TEST_sig_none",
            "html": "<p>Plain body.</p>",
            "include_signature": False,
            "signature_style": "table",
            "sig_left":  {"label": "RECIPIENT / ADVISOR",
                          "name": "N1", "title": "T1"},
            "sig_right": {"label": "BLUBRIDGE TECHNOLOGIES PRIVATE LIMITED",
                          "name": "N2", "title": "T2"},
        })
        assert r.status_code == 200
        with fitz.open(stream=r.content, filetype="pdf") as doc:
            for p in doc:
                assert len(p.get_images(full=True)) <= ref_imgs, \
                    "extra image stamped despite include_signature=false"
                t = p.get_text()
                assert "N1" not in t and "N2" not in t, \
                    "signature-table rendered despite include_signature=false"


# ---- DOCX FIDELITY -------------------------------------------------------
def _build_rich_docx() -> tuple[bytes, list[str]]:
    """Build a docx containing (i)..(vii). Returns (bytes, list of visible
    non-empty paragraph strings we assert must appear in the returned HTML)."""
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    d = Document()

    # (i) bold lead-in "4.7 Exclusivity." + normal continuation
    p = d.add_paragraph()
    r = p.add_run("4.7 Exclusivity."); r.bold = True
    p.add_run(" The Advisor shall not enter into any conflicting agreement.")

    # (ii) manual line break + tab
    p2 = d.add_paragraph()
    p2.add_run("LineOne")
    p2.add_run().add_break()
    p2.add_run("\tAfterTab")

    # (iii) superscript / subscript / strikethrough
    p3 = d.add_paragraph()
    r1 = p3.add_run("E=mc"); r2 = p3.add_run("2"); r2.font.superscript = True
    p3.add_run(" and H"); rsub = p3.add_run("2"); rsub.font.subscript = True
    p3.add_run("O plus ")
    rs = p3.add_run("STRIKE_ME"); rs.font.strike = True

    # (iv) blank paragraph between sections
    d.add_paragraph("Section A body.")
    d.add_paragraph("")   # blank
    d.add_paragraph("Section B body.")

    # (v) bullet + numbered list
    d.add_paragraph("BulletItemAlpha",  style="List Bullet")
    d.add_paragraph("BulletItemBeta",   style="List Bullet")
    d.add_paragraph("NumItemOne",       style="List Number")
    d.add_paragraph("NumItemTwo",       style="List Number")

    # (vi) 2x2 table with BOLD header cells
    tbl = d.add_table(rows=2, cols=2)
    for c, txt in zip(tbl.rows[0].cells, ["ColHdrX", "ColHdrY"]):
        cp = c.paragraphs[0]
        r = cp.add_run(txt); r.bold = True
    tbl.rows[1].cells[0].text = "RowCellA"
    tbl.rows[1].cells[1].text = "RowCellB"

    # (vii) centered + justified
    pc = d.add_paragraph("CenteredLine")
    pc.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pj = d.add_paragraph("JustifiedLine here filling the row.")
    pj.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    buf = io.BytesIO(); d.save(buf)

    # Non-empty visible strings that must appear in the returned HTML
    visible = [
        "4.7 Exclusivity.",
        "The Advisor shall not enter into any conflicting agreement.",
        "LineOne",
        "AfterTab",
        "E=mc",
        "STRIKE_ME",
        "Section A body.",
        "Section B body.",
        "BulletItemAlpha",
        "BulletItemBeta",
        "NumItemOne",
        "NumItemTwo",
        "ColHdrX",
        "ColHdrY",
        "RowCellA",
        "RowCellB",
        "CenteredLine",
        "JustifiedLine here filling the row.",
    ]
    return buf.getvalue(), visible


class TestDocxFidelity:
    def test_rich_docx_roundtrip(self, sess):
        data, visible = _build_rich_docx()
        r = sess.post(f"{BASE_URL}/api/doc/import",
                      files={"file": ("rich.docx", data,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
        assert r.status_code == 200, r.text
        html = r.json()["html"]

        # 1. Every non-empty source string must appear in the HTML
        for s in visible:
            assert s in html, f"missing source text in imported HTML: {s!r}"

        # 2. Formatting markers
        assert "<b>4.7 Exclusivity.</b>" in html or "<b>4.7 Exclusivity." in html, \
            "bold lead-in lost"
        assert "<br>" in html, "manual line break not preserved"
        assert "&#9;" in html or "\t" in html, "tab character not preserved"
        assert "<sup>2</sup>" in html, "superscript missing"
        assert "<sub>2</sub>" in html, "subscript missing"
        assert "<s>STRIKE_ME</s>" in html, "strikethrough missing"
        # blank paragraph spacer
        assert "&nbsp;" in html, "blank paragraph spacer missing"
        # lists
        assert "<ul>" in html and "BulletItemAlpha" in html
        assert "<ol>" in html and "NumItemOne" in html
        # table with bold headers
        assert "<table>" in html
        assert "<b>ColHdrX</b>" in html and "<b>ColHdrY</b>" in html, \
            "bold header cells lost"
        # alignment
        assert "text-align:center" in html, "centered alignment missing"
        assert "text-align:justify" in html, "justified alignment missing"

    def test_list_paragraph_no_numbering_stays_p(self, sess):
        """A paragraph with style 'List Paragraph' but NO real numPr must
        come back as <p>, never as <li>."""
        from docx import Document
        d = Document()
        # style exists in default templates; if not, add a paragraph and set style name
        p = d.add_paragraph("PlainIndentedText")
        try:
            p.style = d.styles["List Paragraph"]
        except KeyError:
            pytest.skip("List Paragraph style not present in default template")
        buf = io.BytesIO(); d.save(buf)
        r = sess.post(f"{BASE_URL}/api/doc/import",
                      files={"file": ("lp.docx", buf.getvalue(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
        assert r.status_code == 200
        html = r.json()["html"]
        assert "PlainIndentedText" in html
        # Must appear inside a <p>, never inside a <li>
        assert "<li>PlainIndentedText" not in html, \
            "List Paragraph without numbering was incorrectly converted to <li>"
        assert "<ul>" not in html and "<ol>" not in html, \
            "spurious list wrapper added for plain List Paragraph"


# ---- PREVIEW == PDF (3+ pages) -------------------------------------------
class TestPreviewPdfParityMulti:
    def test_page_count_matches_multi_page(self, sess):
        html = ("<h3>Section</h3>" + ("<p>" + "text. " * 40 + "</p>") * 4) * 8
        payload = {"name": "TEST_parity", "html": html,
                   "include_signature": True}
        p = sess.post(f"{BASE_URL}/api/doc/preview", json=payload).json()
        g = sess.post(f"{BASE_URL}/api/doc/generate", json=payload)
        assert g.status_code == 200
        with fitz.open(stream=g.content, filetype="pdf") as doc:
            assert doc.page_count == p["count"] >= 3, \
                f"parity/multipage failed: pdf={doc.page_count} preview={p['count']}"


# ---- TABLE regression 40 rows --------------------------------------------
class TestTable40NoCut:
    def test_40row_table_no_cut_header_repeats_footer_ok(self, sess):
        rows = "".join(f"<tr><td>R8_{i}A</td><td>R8_{i}B</td><td>R8_{i}C</td></tr>"
                       for i in range(1, 41))
        html = ("<h2>Big table v2</h2>"
                "<table><tr><th>HA</th><th>HB</th><th>HC</th></tr>"
                + rows + "</table>")
        r = sess.post(f"{BASE_URL}/api/doc/generate",
                      json={"name": "TEST_tbl2", "html": html,
                            "include_signature": False})
        assert r.status_code == 200
        pages = _blocks_by_page(r.content)
        with fitz.open(stream=r.content, filetype="pdf") as doc:
            texts = [p.get_text() for p in doc]
            for i in range(1, 41):
                on = [pi for pi, t in enumerate(texts)
                      if all(f"R8_{i}{c}" in t for c in ("A", "B", "C"))]
                assert len(on) == 1, f"row {i} cut/missing pages={on}"
            pages_with_body = [pi for pi, t in enumerate(texts) if "R8_" in t]
            for pi in pages_with_body:
                assert "HA" in texts[pi] and "HB" in texts[pi] and "HC" in texts[pi], \
                    f"header not repeated on page {pi+1}"
        # No content crosses y=765
        for pi, blocks in enumerate(pages):
            for y0, y1, t in blocks:
                if "R8_" in t or "HA" in t:
                    assert y1 <= FOOTER_CLEARANCE_HARD + 1.5, \
                        f"page {pi+1} table content crosses footer at y1={y1}"
