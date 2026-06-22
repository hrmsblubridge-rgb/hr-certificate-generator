"""
Offer Letter PDF generator.

Bakes user-supplied values into the source Internship Offer Letter PDF without
touching anything else (font, size, weight, alignment, header, footer, layout).

Two rendering modes per replaced line:
  * left  – `insert_text` per-segment, exact baseline control. Used for headers,
            address block, the "Dear …" greeting, and last lines of paragraphs
            which were left-aligned in the original.
  * just  – `insert_htmlbox` with `text-align: justify` + `text-align-last:
            justify`, used for INTERIOR lines of a justified body paragraph so
            the new content stretches word spaces to fill exactly to the
            original right margin (x = 547pt).

A single input (e.g. `name`, `date`, `salary_amount`) can appear in MULTIPLE
lines — the user types it once and we re-emit it everywhere it occurs.
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Tuple
import html
import io

import pymupdf as fitz

STATIC_DIR = Path(__file__).parent / "static"
SOURCE_PDF = STATIC_DIR / "Offer_Letter_Original.pdf"

# Arial-metric font with identity rewritten to "Arial" in the name table.
# The underlying glyph data is Arimo (Google's Arial-metric equivalent under
# Apache 2.0), but the embedded font name in the generated PDFs reads as
# "ArialMT" / "Arial-BoldMT" — identical to the source PDF — so apps that
# inspect font metadata (Illustrator, Acrobat font panel, etc.) display
# "Arial Regular" / "Arial Bold" instead of "Arimo*".
ARIAL_REGULAR = STATIC_DIR / "fonts" / "ArialMT.ttf"
ARIAL_BOLD    = STATIC_DIR / "fonts" / "Arial-BoldMT.ttf"

FONT_SIZE      = 11
TEXT_COLOR     = (0, 0, 0)        # original is solid black (#000000)
LEFT_MARGIN    = 72.0             # body-text left margin
RIGHT_MARGIN   = 547.0            # body-text right margin (justified edge)

# Per-segment font lookup. PDF resource names must match what the original
# PDF uses so Illustrator's font panel reports the same name throughout.
_FONTS = {
    "reg":  ("ArialMT",       str(ARIAL_REGULAR), FONT_SIZE, TEXT_COLOR),
    "bold": ("Arial-BoldMT",  str(ARIAL_BOLD),    FONT_SIZE, TEXT_COLOR),
}

# Note: the htmlbox/archive helpers below are kept for completeness but are no
# longer used by the active justified renderer (which now does manual
# word-spacing via `_render_justified`).
_HTMLBOX_CSS = ""


def _make_archive() -> "fitz.Archive":
    a = fitz.Archive()
    a.add(str(ARIAL_REGULAR), "arimo-regular")
    a.add(str(ARIAL_BOLD),    "arimo-bold")
    return a


# A "LineReplacement" describes one redact+re-render operation.
#
#   page          - 0-based page index in the source PDF
#   redact_rect   - exact rect to white out (a single PDF line)
#   align         - "left"  -> insert_text at (x_start, baseline_y) per segment
#                   "just"  -> insert_htmlbox with justified text in the rect
#                              (left_margin, html_top, right_margin, html_top+H)
#                              html_top is calibrated so the rendered span_top
#                              lands on the original line's y_top.
#   baseline_y    - (left mode) y for insert_text
#   x_start       - (left mode) leftmost x
#   html_top      - (just mode) rect-top for insert_htmlbox (line y_top - 11.0)
#   segments      - list of (text_template, font_key); template uses {placeholders}
LineReplacement = Tuple[int, fitz.Rect, str, float, float, float, List[Tuple[str, str]]]


def _build_replacements(v: dict) -> List[LineReplacement]:
    """Compose all line replacements from a single dict of user inputs."""
    # ---- Sanitise the salary amount the user typed -------------------------
    # Strip leading currency symbols / spaces and trailing "/-" so we don't
    # double them up (e.g. user types "₹23000/-" -> we still render exactly
    # "₹<amount>/-").
    amt = v.get("salary_amount", "").strip()
    for prefix in ("\u20b9", "Rs.", "Rs", "INR", "rs.", "rs"):
        if amt.startswith(prefix):
            amt = amt[len(prefix):].lstrip()
    if amt.endswith("/-"):
        amt = amt[:-2].rstrip()
    v = {**v, "salary_amount": amt}

    return [
        # ---- PAGE 1, line y=153.21-165.50: Ref + Date (two blocks, same line)
        # Left block
        (0, fitz.Rect(72, 151, 280, 168), "left", 162.0, LEFT_MARGIN, 0.0,
            [("Ref: ", "bold"),
             (f'CHN/2026/INT/1-{v["ref_code"]}', "reg")]),
        # Right block
        (0, fitz.Rect(425, 151, 555, 168), "left", 162.0, 435.75, 0.0,
            [("    ", "reg"),
             ("Date: ", "bold"),
             (f'{v["date"]} ', "reg")]),

        # ---- PAGE 1 ADDRESS BLOCK ------------------------------------------
        (0, fitz.Rect(72, 178, 545, 194), "left", 188.5, LEFT_MARGIN, 0.0,
            [(f'{v["name"]} ,', "bold"), (" ", "reg")]),
        (0, fitz.Rect(72, 191, 545, 206), "left", 201.5, LEFT_MARGIN, 0.0,
            [(f'{v["addr1"]}', "reg")]),
        (0, fitz.Rect(72, 204, 545, 219), "left", 214.5, LEFT_MARGIN, 0.0,
            [(f'{v["addr2"]}', "reg")]),
        (0, fitz.Rect(72, 217, 545, 232), "left", 227.0, LEFT_MARGIN, 0.0,
            [(f'{v["addr3"]}', "reg")]),
        (0, fitz.Rect(72, 229, 545, 244), "left", 239.5, LEFT_MARGIN, 0.0,
            [(f'{v["phone"]} ', "reg")]),
        (0, fitz.Rect(72, 242, 545, 257), "left", 252.5, LEFT_MARGIN, 0.0,
            [(f'{v["email"]} ', "reg")]),

        # ---- PAGE 1, "Dear Mr. <name>," (left-aligned, paragraph header) ---
        (0, fitz.Rect(72, 283, 545, 298), "left", 293.5, LEFT_MARGIN, 0.0,
            [("Dear ", "reg"),
             (f'{v["name"]}, ', "bold")]),

        # ---- PAGE 1, designation line (LAST line of its paragraph -> LEFT) -
        (0, fitz.Rect(72, 361, 555, 376), "left", 372.0, LEFT_MARGIN, 0.0,
            [(f'as an {v["designation"]}, operating out of our Besant Nagar, '
              f'Chennai office. ', "reg")]),

        # ---- PAGE 1, salary line  (INTERIOR line -> JUSTIFY) ---------------
        # original y=387.77-400.06 → baseline ≈ 397.5
        (0, fitz.Rect(72, 386, 555, 401), "just", 397.5, LEFT_MARGIN, 0.0,
            [("Your monthly internship stipend shall be ", "reg"),
             (f'\u20b9{v["salary_amount"]}/- ', "bold"),
             (f'(Indian Rupees {v["salary_words"]} only). ', "reg")]),

        # ---- PAGE 1, commencement line  (INTERIOR -> JUSTIFY) --------------
        # original y=466.18-478.47 → baseline ≈ 475.5
        (0, fitz.Rect(72, 465, 555, 480), "just", 475.5, LEFT_MARGIN, 0.0,
            [(f'Your internship engagement shall commence on {v["date"]} '
              f'and shall continue until such time ', "reg")]),

        # ---- PAGE 3, annexure salary line  (INTERIOR -> JUSTIFY) -----------
        # original y=203.20-215.49 → baseline ≈ 212.5
        (2, fitz.Rect(72, 202, 555, 217), "just", 212.5, LEFT_MARGIN, 0.0,
            [(f'The Intern shall be paid a monthly stipend of '
              f'\u20b9{v["salary_amount"]}/-, payable on a pro-rata basis '
              f'subject to ', "reg")]),
    ]


def _tokenise(segments):
    """Break a list of (text, font_key) segments into a flat list of
    word/space tokens, suitable for manual justification.

    Returns list of dicts: {text, fkey, is_space, width}.
    Consecutive whitespace is collapsed to a single space token.  Leading and
    trailing whitespace is stripped.
    """
    tokens = []
    pending_space = False
    for text, fkey in segments:
        if not text:
            continue
        i = 0
        while i < len(text):
            if text[i] == " ":
                if not pending_space:
                    tokens.append({"text": " ", "fkey": "reg", "is_space": True})
                    pending_space = True
                i += 1
            else:
                j = i
                while j < len(text) and text[j] != " ":
                    j += 1
                tokens.append({"text": text[i:j], "fkey": fkey, "is_space": False})
                pending_space = False
                i = j
    while tokens and tokens[-1]["is_space"]:
        tokens.pop()
    for tok in tokens:
        _, ffile, fsize, _ = _FONTS[tok["fkey"]]
        tok["width"] = fitz.Font(fontfile=ffile).text_length(tok["text"], fsize)
    return tokens


def _render_left(page, baseline_y, x_start, segments):
    """Left-aligned line: place each segment using its native font width."""
    x = x_start
    for text, fkey in segments:
        if not text:
            continue
        name, file, size, color = _FONTS[fkey]
        page.insert_text(
            (x, baseline_y), text,
            fontname=name, fontfile=file, fontsize=size, color=color,
        )
        x += fitz.Font(fontfile=file).text_length(text, size)


def _render_justified(page, baseline_y, segments):
    """Justified line: stretch each inter-word space evenly so the rendered
    content ends exactly at the right margin (x = `RIGHT_MARGIN`).

    Single-line renderer. If the user-typed content is naturally wider than
    the column it will overflow past the right margin — by design, so the
    line does not wrap and collide with the next (un-redacted) original
    paragraph line below.
    """
    tokens = _tokenise(segments)
    if not tokens:
        return
    natural = sum(t["width"] for t in tokens)
    available = RIGHT_MARGIN - LEFT_MARGIN
    n_spaces = sum(1 for t in tokens if t["is_space"])
    extra_per_space = max(0.0, (available - natural) / n_spaces) if n_spaces else 0.0

    x = LEFT_MARGIN
    for tok in tokens:
        if not tok["is_space"]:
            name, file, size, color = _FONTS[tok["fkey"]]
            page.insert_text(
                (x, baseline_y), tok["text"],
                fontname=name, fontfile=file, fontsize=size, color=color,
            )
        x += tok["width"] + (extra_per_space if tok["is_space"] else 0.0)


def build_offer_letter(values: dict) -> bytes:
    """Generate the filled Offer Letter PDF as bytes."""
    replacements = _build_replacements(values)
    doc = fitz.open(str(SOURCE_PDF))

    # 1) Apply redactions per page (batched).
    by_page: dict = {}
    for entry in replacements:
        by_page.setdefault(entry[0], []).append(entry)
    for page_idx, entries in by_page.items():
        page = doc[page_idx]
        for _, rect, *_ in entries:
            page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    # 2) Re-render each line.
    for page_idx, entries in by_page.items():
        page = doc[page_idx]
        for _, _rect, align, baseline_y, x_start, _html_top, segments in entries:
            if align == "left":
                _render_left(page, baseline_y, x_start, segments)
            else:  # "just"
                _render_justified(page, baseline_y, segments)

    out = io.BytesIO()
    doc.save(out, garbage=4, deflate=True, clean=True)
    doc.close()
    return out.getvalue()
