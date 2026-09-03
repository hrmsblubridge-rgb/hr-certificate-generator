"""Doc module — renders arbitrary rich content onto the official BluBridge
letterhead PDF.

The uploaded letterhead (`static/doc/Letterhead_Curve.pdf`) is used as-is: every
generated page is a stamp of that page (logo, watermark, footer, CIN, spacing
and colours untouched) with the document content drawn on top, strictly inside
the safe area between the header rule and the footer band.

Layout goals (in priority order):
  1. paragraphs stay intact — never split across pages,
  2. every page is filled as far down as the footer clearance allows,
  3. ~38pt (≈50px) of clear space is kept above the fixed footer,
  4. a heading always travels with the block that follows it,
  5. table rows are never cut; the header row repeats on continuation pages,
  6. when a page still has moderate leftover space, line-height / paragraph
     spacing is nudged up (1.15 → max 1.30) to balance the page instead of
     leaving a large blank band.

Pagination happens once, then the same page plan is rendered for the preview
images and the downloadable PDF — preview and download can never diverge.
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
# confidentiality strip) starts at y≈801pt. Content runs to 38pt (≈50px) above
# that band — no oversized reserved margin.
PAGE_W, PAGE_H = 595.276, 841.89
FOOTER_TOP = 801.0
FOOTER_CLEARANCE = 38.0
CONTENT_LEFT = 56.0
CONTENT_RIGHT = PAGE_W - 56.0
CONTENT_TOP = 108.0
CONTENT_BOTTOM = FOOTER_TOP - FOOTER_CLEARANCE      # 763pt
CONTENT_W = CONTENT_RIGHT - CONTENT_LEFT
CONTENT_H = CONTENT_BOTTOM - CONTENT_TOP

SIG_WIDTH = 200.0          # pt — keeps the seal's original aspect ratio
SIG_GAP_ABOVE = 26.0       # professional spacing above the seal

# Typography — compact professional defaults; the balancer may scale the
# vertical rhythm up to MAX_LINE_HEIGHT on pages with leftover space.
BASE_LINE_HEIGHT = 1.15
MAX_LINE_HEIGHT = 1.30
BASE_P_MARGIN = 6.0
BASE_H_MARGIN = 5.0
BALANCE_STEPS = (1.13, 1.09, 1.06, 1.03)
BALANCE_MIN_LEFTOVER = 22.0

_FONT_CSS = (
    '@font-face { font-family: bbdoc; src: url("ArialMT.ttf"); }\n'
    '@font-face { font-family: bbdoc; font-weight: bold; src: url("Arial-BoldMT.ttf"); }\n'
)

_ARCHIVE = fitz.Archive(str(FONT_DIR))
_STRIP_TAGS = {"script", "style", "iframe", "object", "embed", "link", "meta"}
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


def _css(mult: float = 1.0) -> str:
    lh = min(BASE_LINE_HEIGHT * mult, MAX_LINE_HEIGHT)
    pm = BASE_P_MARGIN * mult
    hm = BASE_H_MARGIN * mult
    return _FONT_CSS + f"""
body {{ font-family: bbdoc; font-size: 11px; line-height: {lh:.3f}; color: #000000; }}
p {{ font-family: bbdoc; margin: 0 0 {pm:.2f}px 0; text-align: left; }}
h1 {{ font-family: bbdoc; font-size: 15.5px; font-weight: bold; margin: 0 0 {hm:.2f}px 0; }}
h2 {{ font-family: bbdoc; font-size: 13.5px; font-weight: bold; margin: 0 0 {hm:.2f}px 0; }}
h3 {{ font-family: bbdoc; font-size: 12.5px; font-weight: bold; margin: 0 0 {hm:.2f}px 0; }}
h4, h5, h6 {{ font-family: bbdoc; font-size: 11.5px; font-weight: bold; margin: 0 0 {hm:.2f}px 0; }}
ul, ol {{ font-family: bbdoc; margin: 0 0 {pm:.2f}px 20px; }}
li {{ font-family: bbdoc; margin: 0 0 {max(pm - 2, 1):.2f}px 0; }}
blockquote {{ font-family: bbdoc; margin: 0 0 {pm:.2f}px 18px; }}
table {{ width: 100%; }}
th, td {{ font-family: bbdoc; font-size: 10.5px; border: 1px solid #999999;
         padding: 4px 6px; text-align: left; vertical-align: top; }}
th {{ font-weight: bold; }}
"""


_CSS_CACHE: dict[float, str] = {}


def _css_cached(mult: float) -> str:
    key = round(mult, 3)
    if key not in _CSS_CACHE:
        _CSS_CACHE[key] = _css(key)
    return _CSS_CACHE[key]


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
# Measurement / drawing — one renderer for measuring, preview and PDF
# --------------------------------------------------------------------------

_MEASURE_H = 13000.0
_measure_cache: dict[tuple[float, str], float] = {}


def _wrap(html_fragment: str) -> str:
    return f"<div>{html_fragment}</div>"


def _measure(html_fragment: str, mult: float = 1.0) -> float:
    key = (round(mult, 3), html_fragment)
    hit = _measure_cache.get(key)
    if hit is not None:
        return hit
    if len(_measure_cache) > 4000:
        _measure_cache.clear()
    scratch = fitz.open()
    page = scratch.new_page(width=PAGE_W, height=_MEASURE_H)
    spare, _scale = page.insert_htmlbox(fitz.Rect(0, 0, CONTENT_W, _MEASURE_H),
                                        _wrap(html_fragment),
                                        css=_css_cached(mult), archive=_ARCHIVE,
                                        scale_low=1)
    scratch.close()
    height = round(_MEASURE_H - max(spare, 0.0), 2)
    _measure_cache[key] = height
    return height


def _draw(page, html_fragment: str, top: float, height: float, mult: float = 1.0):
    bottom = min(top + height + 2.0, CONTENT_BOTTOM + 2.0)
    page.insert_htmlbox(fitz.Rect(CONTENT_LEFT, top, CONTENT_RIGHT, bottom),
                        _wrap(html_fragment), css=_css_cached(mult),
                        archive=_ARCHIVE, scale_low=1)


def _table_html(head: str, rows: list[str]) -> str:
    return "<table>" + head + "".join(rows) + "</table>"


# --------------------------------------------------------------------------
# Pagination — produces a page plan, nothing is drawn yet
# --------------------------------------------------------------------------

class _Layout:
    def __init__(self):
        self.pages: list[list[dict]] = [[]]
        self.y = CONTENT_TOP

    @property
    def remaining(self) -> float:
        return CONTENT_BOTTOM - self.y

    @property
    def at_page_top(self) -> bool:
        return self.y <= CONTENT_TOP + 0.01

    def new_page(self):
        self.pages.append([])
        self.y = CONTENT_TOP

    def ensure(self, height: float):
        # Only break when the block genuinely cannot fit in what is left.
        if height > self.remaining + 0.5 and not self.at_page_top:
            self.new_page()

    def add(self, html_fragment: str, height: float):
        self.pages[-1].append({"kind": "flow", "html": html_fragment, "h": height})
        self.y += height


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


def _place_flow(lay: _Layout, html_fragment: str, height: float):
    if height <= CONTENT_H:
        lay.ensure(height)
        lay.add(html_fragment, height)
        return
    for chunk in _split_oversized(html_fragment, lay.remaining):
        h = _measure(chunk)
        lay.ensure(h)
        lay.add(chunk, h)


def _place_list(lay: _Layout, block: dict):
    total = _measure(block["html"])
    if total <= CONTENT_H:
        _place_flow(lay, block["html"], total)
        return
    tag = block["tag"]
    items = block["items"]
    idx = 0
    while idx < len(items):
        start = idx + 1
        chunk: list[str] = []
        while idx < len(items):
            trial = f'<{tag} start="{start}">' + "".join(chunk + [items[idx]]) + f"</{tag}>"
            if _measure(trial) > lay.remaining and chunk:
                break
            chunk.append(items[idx])
            idx += 1
        html_chunk = f'<{tag} start="{start}">' + "".join(chunk) + f"</{tag}>"
        h = _measure(html_chunk)
        lay.ensure(h)
        lay.add(html_chunk, h)
        if idx < len(items):
            lay.new_page()


def _place_table(lay: _Layout, block: dict):
    head, rows = block["head"], block["rows"]
    full = _table_html(head, rows)
    total = _measure(full)
    if total <= lay.remaining:
        lay.add(full, total)
        return
    if total <= CONTENT_H:
        lay.new_page()
        lay.add(full, _measure(full))
        return
    i = 0
    while i < len(rows):
        chunk: list[str] = []
        while i < len(rows):
            h = _measure(_table_html(head, chunk + [rows[i]]))
            if h > lay.remaining and chunk:
                break
            if h > lay.remaining and not chunk and not lay.at_page_top:
                lay.new_page()
                continue
            chunk.append(rows[i])
            i += 1
        html_chunk = _table_html(head, chunk)
        h = _measure(html_chunk)
        lay.ensure(h)
        lay.add(html_chunk, h)
        if i < len(rows):
            lay.new_page()


def _signature_height() -> float:
    with fitz.open(str(SIGNATURE)) as img:
        iw, ih = img[0].rect.width, img[0].rect.height
    return SIG_WIDTH * ih / iw


def _place_seal(lay: _Layout):
    if not SIGNATURE.is_file():
        return
    sig_h = _signature_height()
    need = SIG_GAP_ABOVE + sig_h
    lay.ensure(need)
    lay.pages[-1].append({"kind": "seal", "h": need, "sig_h": sig_h})
    lay.y += need


def signature_table_html(left: dict, right: dict, date_str: str) -> str:
    """Two-column signature block: labels on top, then Signature / Name /
    Title / Date lines — mirrors the customer's contract layout."""
    def cell(party: dict) -> str:
        return (
            "<td>"
            f"<p><b>{_html.escape(party.get('label', ''))}</b></p>"
            "<p>&nbsp;</p><p>&nbsp;</p>"
            "<p>Signature:</p>"
            f"<p>Name: <b>{_html.escape(party.get('name', ''))}</b></p>"
            f"<p>Title: <b>{_html.escape(party.get('title', ''))}</b></p>"
            f"<p>Date : {_html.escape(date_str)}</p>"
            "</td>"
        )
    return "<table><tr>" + cell(left) + cell(right) + "</tr></table>"


def _paginate(blocks: list[dict]) -> _Layout:
    lay = _Layout()
    i = 0
    while i < len(blocks):
        b = blocks[i]
        if b["kind"] == "table":
            _place_table(lay, b)
            i += 1
            continue
        if b["kind"] == "list":
            _place_list(lay, b)
            i += 1
            continue

        h = _measure(b["html"])
        # A heading must never be orphaned — it travels with the next block,
        # but only break if the PAIR genuinely does not fit in what is left.
        if b.get("tag") in _HEADINGS and i + 1 < len(blocks):
            nxt = blocks[i + 1]
            nxt_html = (_table_html(nxt["head"], nxt["rows"])
                        if nxt["kind"] == "table" else nxt["html"])
            pair = h + _measure(nxt_html)
            if pair > lay.remaining + 0.5 and pair <= CONTENT_H and not lay.at_page_top:
                lay.new_page()
        _place_flow(lay, b["html"], h)
        i += 1
    return lay


# --------------------------------------------------------------------------
# Rendering the page plan
# --------------------------------------------------------------------------

def _balance_multiplier(items: list[dict]) -> float:
    """Nudge the vertical rhythm up so a page with leftover space looks
    balanced, never so far that content would be pushed off the page."""
    for mult in BALANCE_STEPS:
        total = sum(_measure(it["html"], mult) for it in items)
        if total <= CONTENT_H - 4:
            return mult
    return 1.0


def _render(lay: _Layout) -> bytes:
    doc = fitz.open()
    letterhead = fitz.open(str(LETTERHEAD))
    pages = [p for p in lay.pages if p] or [[]]
    for idx, items in enumerate(pages):
        page = doc.new_page(width=PAGE_W, height=PAGE_H)
        page.show_pdf_page(page.rect, letterhead, 0)

        flow_only = all(it["kind"] == "flow" for it in items)
        used = sum(it["h"] for it in items)
        mult = 1.0
        if (flow_only and items and idx < len(pages) - 1
                and CONTENT_H - used > BALANCE_MIN_LEFTOVER):
            mult = _balance_multiplier(items)

        y = CONTENT_TOP
        for it in items:
            if it["kind"] == "seal":
                top = y + SIG_GAP_ABOVE
                rect = fitz.Rect(CONTENT_LEFT, top,
                                 CONTENT_LEFT + SIG_WIDTH, top + it["sig_h"])
                page.insert_image(rect, filename=str(SIGNATURE), keep_proportion=True)
                y = rect.y1
                continue
            h = _measure(it["html"], mult) if mult != 1.0 else it["h"]
            _draw(page, it["html"], y, h, mult)
            y += h

    out = io.BytesIO()
    doc.save(out, garbage=3, deflate=True)
    doc.close()
    letterhead.close()
    return out.getvalue()


def build_pdf(html_content: str, include_signature: bool = True,
              signature_style: str = "seal",
              signature_table: dict | None = None) -> bytes:
    """Render `html_content` onto the official letterhead. Returns PDF bytes.

    `signature_style` is 'seal' (scanned seal + director signature image) or
    'table' (two-column signature block described by `signature_table`)."""
    _measure_cache.clear()
    blocks = html_to_blocks(html_content)
    if not blocks:
        raise ValueError("The document is empty — add some content first.")

    if include_signature and signature_style == "table":
        data = signature_table or {}
        blocks.append({
            "kind": "table",
            "head": "",
            "rows": [re.sub(r"^<table>|</table>$", "",
                            signature_table_html(
                                data.get("left") or {"label": "RECIPIENT / ADVISOR"},
                                data.get("right") or {
                                    "label": "BLUBRIDGE TECHNOLOGIES PRIVATE LIMITED"},
                                data.get("date") or ""))],
        })

    lay = _paginate(blocks)
    if include_signature and signature_style == "seal":
        _place_seal(lay)
    return _render(lay)


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
# Import: DOCX / PDF / TXT → editable HTML (content-faithful)
# --------------------------------------------------------------------------

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _run_html(run) -> str:
    """Serialise a Word run keeping text, tabs, manual line breaks, symbols
    and character formatting exactly as authored."""
    parts: list[str] = []
    for node in run._r:
        tag = node.tag.replace(_W, "")
        if tag == "t":
            parts.append(_html.escape(node.text or ""))
        elif tag == "tab":
            parts.append("&#9;&nbsp;&nbsp;")
        elif tag in ("br", "cr"):
            parts.append("<br>")
        elif tag == "noBreakHyphen":
            parts.append("&#8209;")
        elif tag == "softHyphen":
            parts.append("")
        elif tag == "sym":
            char = node.get(f"{_W}char")
            if char:
                try:
                    parts.append(f"&#{int(char, 16)};")
                except ValueError:
                    pass
    text = "".join(parts)
    if not text:
        return ""
    rpr = run._r.rPr
    if rpr is not None:
        if rpr.find(f"{_W}vertAlign") is not None:
            val = rpr.find(f"{_W}vertAlign").get(f"{_W}val")
            if val == "superscript":
                text = f"<sup>{text}</sup>"
            elif val == "subscript":
                text = f"<sub>{text}</sub>"
        if rpr.find(f"{_W}strike") is not None:
            text = f"<s>{text}</s>"
    if run.bold:
        text = f"<b>{text}</b>"
    if run.italic:
        text = f"<i>{text}</i>"
    if run.underline:
        text = f"<u>{text}</u>"
    return text


def _para_html(par) -> str:
    return "".join(_run_html(r) for r in par.runs)


_ALIGN = {0: "left", 1: "center", 2: "right", 3: "justify"}


def _alignment(par) -> str:
    val = getattr(par.alignment, "value", None)
    return _ALIGN.get(val if val is not None else 0, "left")


def _num_format(doc, par) -> str | None:
    """Return 'bullet' / 'decimal' / None for a paragraph, based on the real
    Word numbering definition (so plain indented text is never turned into a
    bullet list)."""
    ppr = par._p.pPr
    if ppr is None or ppr.numPr is None or ppr.numPr.numId is None:
        return None
    num_id = ppr.numPr.numId.val
    ilvl = ppr.numPr.ilvl.val if ppr.numPr.ilvl is not None else 0
    try:
        numbering = doc.part.numbering_part.element
    except Exception:
        return "bullet"
    for num in numbering.findall(f"{_W}num"):
        if num.get(f"{_W}numId") != str(num_id):
            continue
        abstract = num.find(f"{_W}abstractNumId")
        if abstract is None:
            return "bullet"
        abs_id = abstract.get(f"{_W}val")
        for anum in numbering.findall(f"{_W}abstractNum"):
            if anum.get(f"{_W}abstractNumId") != abs_id:
                continue
            for lvl in anum.findall(f"{_W}lvl"):
                if lvl.get(f"{_W}ilvl") != str(ilvl):
                    continue
                fmt = lvl.find(f"{_W}numFmt")
                val = fmt.get(f"{_W}val") if fmt is not None else "bullet"
                return "bullet" if val == "bullet" else "decimal"
    return "bullet"


def docx_to_html(data: bytes) -> str:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(io.BytesIO(data))
    parts: list[str] = []
    open_list: str | None = None
    blank_run = 0

    def close_list():
        nonlocal open_list
        if open_list:
            parts.append(f"</{open_list}>")
            open_list = None

    def cell_html(cell) -> str:
        chunks = []
        for p in cell.paragraphs:
            inner = _para_html(p)
            chunks.append(f"<p>{inner or '&nbsp;'}</p>")
        for t in cell.tables:                      # nested table
            chunks.append(_table_to_html(t))
        return "".join(chunks) or "<p>&nbsp;</p>"

    def _table_to_html(table) -> str:
        rows_html = []
        for row in table.rows:
            cells = "".join(f"<td>{cell_html(c)}</td>" for c in row.cells)
            rows_html.append(f"<tr>{cells}</tr>")
        return "<table>" + "".join(rows_html) + "</table>"

    for child in doc.element.body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            par = Paragraph(child, doc)
            style = (par.style.name or "").lower()
            text_html = _para_html(par)
            plain = par.text.strip()
            if not plain and "<br>" not in text_html:
                # keep authored blank lines (collapse long runs of them)
                blank_run += 1
                if blank_run <= 2:
                    close_list()
                    parts.append("<p>&nbsp;</p>")
                continue
            blank_run = 0
            num_fmt = _num_format(doc, par)
            if not num_fmt:
                # Word styles applied without an explicit numbering definition
                # (common in generated files). 'List Paragraph' alone is NOT a
                # list — it is plain indented text, so it stays a paragraph.
                if "list bullet" in style:
                    num_fmt = "bullet"
                elif "list number" in style:
                    num_fmt = "decimal"
            if style.startswith("heading"):
                close_list()
                digits = "".join(ch for ch in style if ch.isdigit()) or "2"
                lvl = min(max(int(digits), 1), 4)
                parts.append(f"<h{lvl}>{text_html}</h{lvl}>")
            elif num_fmt:
                want = "ul" if num_fmt == "bullet" else "ol"
                if open_list != want:
                    close_list()
                    parts.append(f"<{want}>")
                    open_list = want
                parts.append(f"<li>{text_html}</li>")
            else:
                close_list()
                align = _alignment(par)
                styles = [] if align == "left" else [f"text-align:{align}"]
                indent = par.paragraph_format.left_indent
                if indent and indent.pt > 2:
                    styles.append(f"margin-left:{min(indent.pt, 72):.0f}px")
                attr = f' style="{";".join(styles)}"' if styles else ""
                parts.append(f"<p{attr}>{text_html}</p>")
        elif tag == "tbl":
            close_list()
            blank_run = 0
            parts.append(_table_to_html(Table(child, doc)))
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
    paras = [p for p in re.split(r"\n\s*\n", raw) if p.strip()]
    return "".join(
        f"<p>{_html.escape(p.strip()).replace(chr(10), '<br>')}</p>" for p in paras
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
