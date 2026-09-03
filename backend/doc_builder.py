"""Doc module — renders arbitrary rich content onto the official BluBridge
letterhead PDF.

The uploaded letterhead (`static/doc/Letterhead_Curve.pdf`) is used as-is: every
generated page is a byte-for-byte stamp of that page (logo, watermark, footer,
CIN, spacing and colours untouched) with the document content drawn on top,
strictly inside the safe area between the header rule and the footer band.

Pagination is block-level with "keep lines together" semantics:
  * a paragraph is never split across pages (unless it is taller than a whole
    page on its own),
  * a heading always travels with the block that follows it,
  * a table row is never cut in half — the header row repeats on continuation
    pages,
  * the signature / seal block moves whole to the next page if it does not fit.

Preview and download share this exact code path: the preview images are simply
rasterised pages of the same PDF, so what you see is what you get.
"""
from __future__ import annotations

import html as _html
import io
import re
from pathlib import Path

import pymupdf as fitz
from lxml import html as LH

STATIC = Path(__file__).parent / "static"
DOC_DIR = STATIC / "doc"
FONT_DIR = STATIC / "fonts"
LETTERHEAD = DOC_DIR / "Letterhead_Curve.pdf"
SIGNATURE = DOC_DIR / "director_signature.png"

# --- Safe content area (derived from the letterhead itself) -----------------
# Header artwork/rule ends at y≈88pt; the footer band (CIN / phone / e-mail /
# confidentiality strip) starts at y≈801pt. Body text lives between them with
# professional breathing room and 56pt side margins.
PAGE_W, PAGE_H = 595.276, 841.89
CONTENT_LEFT = 56.0
CONTENT_RIGHT = PAGE_W - 56.0
CONTENT_TOP = 112.0
CONTENT_BOTTOM = 786.0
CONTENT_W = CONTENT_RIGHT - CONTENT_LEFT
CONTENT_H = CONTENT_BOTTOM - CONTENT_TOP

SIG_WIDTH = 200.0          # pt — keeps the seal's original aspect ratio
SIG_GAP_ABOVE = 34.0       # professional spacing above the seal

USER_CSS = """
@font-face { font-family: bbdoc; src: url("ArialMT.ttf"); }
@font-face { font-family: bbdoc; font-weight: bold; src: url("Arial-BoldMT.ttf"); }
body { font-family: bbdoc; font-size: 11px; line-height: 1.28; color: #000000; }
p { font-family: bbdoc; margin: 0 0 9px 0; text-align: left; }
h1 { font-family: bbdoc; font-size: 16px; font-weight: bold; margin: 0 0 8px 0; }
h2 { font-family: bbdoc; font-size: 14px; font-weight: bold; margin: 0 0 8px 0; }
h3 { font-family: bbdoc; font-size: 12.5px; font-weight: bold; margin: 0 0 7px 0; }
h4, h5, h6 { font-family: bbdoc; font-size: 11.5px; font-weight: bold; margin: 0 0 7px 0; }
ul, ol { font-family: bbdoc; margin: 0 0 9px 20px; }
li { font-family: bbdoc; margin: 0 0 5px 0; }
blockquote { font-family: bbdoc; margin: 0 0 9px 18px; }
table { width: 100%; }
th, td { font-family: bbdoc; font-size: 10.5px; border: 1px solid #999999;
         padding: 4px 6px; text-align: left; }
th { font-weight: bold; background-color: #eeeeee; }
"""

_ARCHIVE = fitz.Archive(str(FONT_DIR))
_STRIP_TAGS = {"script", "style", "iframe", "object", "embed", "link", "meta"}


# --------------------------------------------------------------------------
# HTML → block list
# --------------------------------------------------------------------------

def _serialize(el) -> str:
    return LH.tostring(el, encoding="unicode", with_tail=False)


def _clean(raw: str) -> str:
    """Drop dangerous tags / inline handlers before we parse into blocks."""
    raw = re.sub(r"<!--.*?-->", "", raw or "", flags=re.S)
    frag = LH.fragment_fromstring(raw or "<p></p>", create_parent="div")
    for el in frag.iter():
        tag = str(el.tag).lower() if isinstance(el.tag, str) else ""
        if tag in _STRIP_TAGS:
            el.getparent().remove(el)
            continue
        for attr in list(el.attrib):
            if attr.lower().startswith("on") or attr.lower() in ("srcdoc",):
                del el.attrib[attr]
    return LH.tostring(frag, encoding="unicode")


def _text_block(text: str) -> dict:
    return {"kind": "flow", "tag": "p",
            "html": f"<p>{_html.escape(text.strip())}</p>"}


def _table_block(el) -> dict:
    """Split a table into a repeatable header + individual rows."""
    rows = el.xpath(".//tr")
    head_html = ""
    body_rows: list[str] = []
    for i, tr in enumerate(rows):
        cells = tr.xpath("./th|./td")
        is_head = bool(tr.xpath("./th")) or (i == 0 and tr.getparent() is not None
                                             and str(tr.getparent().tag).lower() == "thead")
        html_row = _serialize(tr)
        if is_head and not head_html and not body_rows:
            # normalise to <th> so the repeated header keeps its styling
            html_row = re.sub(r"<(/?)td", r"<\1th", html_row, flags=re.I)
            head_html = html_row
        elif cells:
            body_rows.append(html_row)
    return {"kind": "table", "head": head_html, "rows": body_rows}


def html_to_blocks(raw_html: str) -> list[dict]:
    frag = LH.fragment_fromstring(_clean(raw_html), create_parent="div")
    return _children_to_blocks(frag)


def _children_to_blocks(frag) -> list[dict]:
    blocks: list[dict] = []
    if frag.text and frag.text.strip():
        blocks.append(_text_block(frag.text))
    for el in frag:
        tag = str(el.tag).lower() if isinstance(el.tag, str) else ""
        if tag == "table":
            blocks.append(_table_block(el))
        elif tag in ("ul", "ol"):
            blocks.append({"kind": "list", "tag": tag, "html": _serialize(el),
                           "items": [_serialize(li) for li in el.xpath("./li")]})
        elif tag == "br":
            pass
        elif tag in ("div", "section", "article", "body") and len(el):
            blocks.extend(_children_to_blocks(el))
        elif tag == "hr":
            blocks.append({"kind": "flow", "tag": "hr", "html": "<p></p>"})
        elif tag:
            inner = re.sub(r"^<\w+[^>]*>|</\w+>$", "", _serialize(el)).strip()
            if inner or tag.startswith("h"):
                blocks.append({"kind": "flow", "tag": tag, "html": _serialize(el)})
        if el.tail and el.tail.strip():
            blocks.append(_text_block(el.tail))
    return [b for b in blocks if b.get("kind") != "flow" or b.get("html")]


# --------------------------------------------------------------------------
# Story helpers — measurement and drawing use the identical layout engine
# --------------------------------------------------------------------------

_MEASURE_H = 13000.0
_measure_cache: dict[str, float] = {}


def _wrap(html_fragment: str) -> str:
    return f"<div>{html_fragment}</div>"


def _measure(html_fragment: str) -> float:
    """Height this fragment needs at the document content width. Uses the very
    same renderer (`insert_htmlbox`) as the final draw, so measured height and
    drawn height always agree."""
    key = html_fragment
    hit = _measure_cache.get(key)
    if hit is not None:
        return hit
    scratch = fitz.open()
    page = scratch.new_page(width=PAGE_W, height=_MEASURE_H)
    rect = fitz.Rect(0, 0, CONTENT_W, _MEASURE_H)
    spare, _scale = page.insert_htmlbox(rect, _wrap(html_fragment),
                                        css=USER_CSS, archive=_ARCHIVE,
                                        scale_low=1)
    scratch.close()
    height = round(_MEASURE_H - max(spare, 0.0), 2)
    _measure_cache[key] = height
    return height


def _draw(page, html_fragment: str, top: float, height: float) -> float:
    bottom = min(top + height + 2.0, CONTENT_BOTTOM)
    rect = fitz.Rect(CONTENT_LEFT, top, CONTENT_RIGHT, bottom)
    page.insert_htmlbox(rect, _wrap(html_fragment), css=USER_CSS,
                        archive=_ARCHIVE, scale_low=1)
    return height


def _table_html(head: str, rows: list[str]) -> str:
    return "<table>" + head + "".join(rows) + "</table>"


# --------------------------------------------------------------------------
# PDF assembly
# --------------------------------------------------------------------------

class _Canvas:
    """Appends letterhead-stamped A4 pages on demand."""

    def __init__(self):
        self.doc = fitz.open()
        self.letterhead = fitz.open(str(LETTERHEAD))
        self.page = None
        self.y = CONTENT_TOP
        self.new_page()

    def new_page(self):
        self.page = self.doc.new_page(width=PAGE_W, height=PAGE_H)
        self.page.show_pdf_page(self.page.rect, self.letterhead, 0)
        self.y = CONTENT_TOP

    @property
    def remaining(self) -> float:
        return CONTENT_BOTTOM - self.y

    def ensure(self, height: float):
        if height > self.remaining and self.y > CONTENT_TOP:
            self.new_page()


def _split_oversized(html_fragment: str, first_space: float) -> list[str]:
    """A single block taller than a whole page must be broken. Split on
    sentence boundaries (the only safe place inside a paragraph) so lines are
    never cut in half."""
    text = re.sub(r"<[^>]+>", " ", html_fragment)
    text = _html.unescape(re.sub(r"\s+", " ", text)).strip()
    sentences = re.split(r"(?<=[.!?;:])\s+", text) or [text]
    chunks: list[str] = []
    current: list[str] = []
    space = first_space
    for sentence in sentences:
        trial = f"<p>{_html.escape(' '.join(current + [sentence]))}</p>"
        if current and _measure(trial) > space:
            chunks.append(f"<p>{_html.escape(' '.join(current))}</p>")
            current = [sentence]
            space = CONTENT_H
        else:
            current.append(sentence)
    if current:
        chunks.append(f"<p>{_html.escape(' '.join(current))}</p>")
    return chunks


def _place_flow(cv: _Canvas, html_fragment: str, height: float):
    """Place a paragraph/heading/list. Never split unless it is taller than a
    full empty page."""
    if height <= CONTENT_H:
        cv.ensure(height)
        _draw(cv.page, html_fragment, cv.y, height)
        cv.y += height
        return
    for chunk in _split_oversized(html_fragment, cv.remaining):
        h = _measure(chunk)
        cv.ensure(h)
        _draw(cv.page, chunk, cv.y, h)
        cv.y += h


def _place_list(cv: _Canvas, block: dict):
    total = _measure(block["html"])
    if total <= CONTENT_H:
        _place_flow(cv, block["html"], total)
        return
    # Long list: break between items, never inside one.
    tag = block["tag"]
    idx = 0
    items = block["items"]
    while idx < len(items):
        chunk: list[str] = []
        while idx < len(items):
            trial = f"<{tag} start=\"{idx + 1}\">" + "".join(chunk + [items[idx]]) + f"</{tag}>"
            h = _measure(trial)
            if h > cv.remaining and chunk:
                break
            chunk.append(items[idx])
            idx += 1
            if h > cv.remaining:
                break
        html_chunk = f"<{tag} start=\"{idx - len(chunk) + 1}\">" + "".join(chunk) + f"</{tag}>"
        h = _measure(html_chunk)
        cv.ensure(h)
        _draw(cv.page, html_chunk, cv.y, h)
        cv.y += h
        if idx < len(items):
            cv.new_page()


def _place_table(cv: _Canvas, block: dict):
    head, rows = block["head"], block["rows"]
    full = _table_html(head, rows)
    total = _measure(full)
    if total <= cv.remaining:
        _draw(cv.page, full, cv.y, total)
        cv.y += total
        return
    if total <= CONTENT_H:
        cv.new_page()
        _draw(cv.page, full, cv.y, total)
        cv.y += total
        return
    # Chunk row-wise; a row is never cut and the header repeats.
    i = 0
    while i < len(rows):
        chunk: list[str] = []
        while i < len(rows):
            h = _measure(_table_html(head, chunk + [rows[i]]))
            if h > cv.remaining and chunk:
                break
            if h > cv.remaining and not chunk:
                # single row taller than the space left → next page
                if cv.y > CONTENT_TOP:
                    cv.new_page()
                    continue
            chunk.append(rows[i])
            i += 1
        html_chunk = _table_html(head, chunk)
        h = _measure(html_chunk)
        cv.ensure(h)
        _draw(cv.page, html_chunk, cv.y, h)
        cv.y += h
        if i < len(rows):
            cv.new_page()


def _place_signature(cv: _Canvas):
    if not SIGNATURE.is_file():
        return
    with fitz.open(str(SIGNATURE)) as img:
        iw, ih = img[0].rect.width, img[0].rect.height
    sig_h = SIG_WIDTH * ih / iw
    need = SIG_GAP_ABOVE + sig_h
    cv.ensure(need)
    top = cv.y + SIG_GAP_ABOVE
    rect = fitz.Rect(CONTENT_LEFT, top, CONTENT_LEFT + SIG_WIDTH, top + sig_h)
    cv.page.insert_image(rect, filename=str(SIGNATURE), keep_proportion=True)
    cv.y = rect.y1


_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def build_pdf(html_content: str, include_signature: bool = True) -> bytes:
    """Render `html_content` onto the official letterhead. Returns PDF bytes."""
    blocks = html_to_blocks(html_content)
    if not blocks:
        raise ValueError("The document is empty — add some content first.")
    _measure_cache.clear()

    cv = _Canvas()
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b["kind"] == "table":
            _place_table(cv, b)
            i += 1
            continue
        if b["kind"] == "list":
            _place_list(cv, b)
            i += 1
            continue

        h = _measure(b["html"])
        # Keep a heading with the block that follows it.
        if b.get("tag") in _HEADINGS and i + 1 < len(blocks):
            nxt = blocks[i + 1]
            nxt_html = (_table_html(nxt["head"], nxt["rows"])
                        if nxt["kind"] == "table" else nxt["html"])
            pair = h + _measure(nxt_html)
            if pair > cv.remaining and pair <= CONTENT_H and cv.y > CONTENT_TOP:
                cv.new_page()
        _place_flow(cv, b["html"], h)
        i += 1

    if include_signature:
        _place_signature(cv)

    out = io.BytesIO()
    cv.doc.save(out, garbage=3, deflate=True)
    cv.doc.close()
    cv.letterhead.close()
    return out.getvalue()


def render_preview(pdf_bytes: bytes, dpi: int = 110) -> list[str]:
    """Rasterise every page of the produced PDF for the on-screen preview."""
    import base64
    pages: list[str] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            pages.append("data:image/jpeg;base64," +
                         base64.b64encode(pix.tobytes("jpeg", jpg_quality=88)).decode())
    return pages


# --------------------------------------------------------------------------
# Import: DOCX / PDF / TXT → editable HTML
# --------------------------------------------------------------------------

def _runs_to_html(par) -> str:
    out = []
    for run in par.runs:
        txt = _html.escape(run.text or "")
        if not txt.strip() and not txt:
            continue
        if run.bold:
            txt = f"<b>{txt}</b>"
        if run.italic:
            txt = f"<i>{txt}</i>"
        if run.underline:
            txt = f"<u>{txt}</u>"
        out.append(txt)
    return "".join(out) or _html.escape(par.text or "")


_ALIGN = {0: "left", 1: "center", 2: "right", 3: "justify"}


def docx_to_html(data: bytes) -> str:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(io.BytesIO(data))
    body = doc.element.body
    parts: list[str] = []
    open_list: str | None = None

    def close_list():
        nonlocal open_list
        if open_list:
            parts.append(f"</{open_list}>")
            open_list = None

    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            par = Paragraph(child, doc)
            style = (par.style.name or "").lower()
            text_html = _runs_to_html(par)
            if not par.text.strip():
                continue
            if style.startswith("heading"):
                close_list()
                lvl = "".join(ch for ch in style if ch.isdigit()) or "2"
                lvl = min(max(int(lvl), 1), 4)
                parts.append(f"<h{lvl}>{text_html}</h{lvl}>")
            elif "list bullet" in style or "list paragraph" in style:
                want = "ul"
                if open_list != want:
                    close_list()
                    parts.append(f"<{want}>")
                    open_list = want
                parts.append(f"<li>{text_html}</li>")
            elif "list number" in style:
                want = "ol"
                if open_list != want:
                    close_list()
                    parts.append(f"<{want}>")
                    open_list = want
                parts.append(f"<li>{text_html}</li>")
            else:
                close_list()
                align = _ALIGN.get(getattr(par.alignment, "value", None) or 0, "left")
                style_attr = f' style="text-align:{align}"' if align != "left" else ""
                parts.append(f"<p{style_attr}>{text_html}</p>")
        elif tag == "tbl":
            close_list()
            table = Table(child, doc)
            rows_html = []
            for r_i, row in enumerate(table.rows):
                cell_tag = "th" if r_i == 0 else "td"
                cells = "".join(
                    f"<{cell_tag}>{_html.escape(c.text.strip())}</{cell_tag}>"
                    for c in row.cells
                )
                rows_html.append(f"<tr>{cells}</tr>")
            parts.append("<table>" + "".join(rows_html) + "</table>")
    close_list()
    return "".join(parts) or "<p></p>"


def pdf_to_html(data: bytes) -> str:
    parts: list[str] = []
    with fitz.open(stream=data, filetype="pdf") as doc:
        for page in doc:
            for block in page.get_text("blocks"):
                text = (block[4] or "").strip()
                if not text:
                    continue
                text = re.sub(r"-\n(\w)", r"\1", text)
                text = re.sub(r"\s*\n\s*", " ", text)
                parts.append(f"<p>{_html.escape(text)}</p>")
    return "".join(parts) or "<p></p>"


def text_to_html(data: bytes) -> str:
    raw = data.decode("utf-8", errors="replace")
    paras = [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]
    return "".join(
        f"<p>{_html.escape(p).replace(chr(10), '<br>')}</p>" for p in paras
    ) or "<p></p>"


def import_to_html(filename: str, data: bytes) -> str:
    ext = Path(filename or "").suffix.lower()
    if ext == ".docx":
        return docx_to_html(data)
    if ext == ".pdf":
        return pdf_to_html(data)
    if ext in (".txt", ".text", ".md"):
        return text_to_html(data)
    raise ValueError("Unsupported file type. Upload a .docx, .pdf or .txt file.")
