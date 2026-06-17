"""
Offer Letter PDF generator.

Bakes user-supplied values into the source Internship Offer Letter PDF without
touching anything else (font, size, weight, alignment, header, footer, layout).

Strategy per editable line:
  1. White-out the exact line area in the source PDF.
  2. Re-render the line from a sequence of (text, font_key) segments using the
     same font (Arimo, an Arial-metric equivalent), size (11pt) and color (#000)
     so the output is visually indistinguishable from the original document.

A single input (e.g. `name`, `date`, `salary_amount`) can appear in MULTIPLE
lines — the user types it once and we re-emit it everywhere it occurs.
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Tuple
import io

import pymupdf as fitz

STATIC_DIR = Path(__file__).parent / "static"
SOURCE_PDF = STATIC_DIR / "Offer_Letter_Original.pdf"

# Arial-metric-equivalent open fonts (Apache 2.0, full Latin + currency symbols).
ARIMO_REGULAR = STATIC_DIR / "fonts" / "Arimo-Regular.ttf"
ARIMO_BOLD    = STATIC_DIR / "fonts" / "Arimo-Bold.ttf"

FONT_SIZE = 11
TEXT_COLOR = (0, 0, 0)               # original is solid black (#000000)
LEFT_MARGIN = 72.0                   # original body-text left margin

# Font registry handed to `_render_segments`.
_FONTS = {
    "reg":  ("ArimoR", str(ARIMO_REGULAR), FONT_SIZE, TEXT_COLOR),
    "bold": ("ArimoB", str(ARIMO_BOLD),    FONT_SIZE, TEXT_COLOR),
}

# A "LineReplacement" describes one redact+re-render operation.
#
#   page          - 0-based page index in the source PDF
#   redact_rect   - exact rect to white out (a single PDF line)
#   baseline_y    - y-coordinate to anchor the new text's baseline at
#   x_start       - leftmost x to begin emitting text
#   segments      - list of (text_template, font_key); template uses {placeholders}
LineReplacement = Tuple[int, fitz.Rect, float, float, List[Tuple[str, str]]]


def _build_replacements(v: dict) -> List[LineReplacement]:
    """Compose all line replacements from a single dict of user inputs."""
    # Baselines are calibrated from the original PDF: each line has span
    # y_top/y_bottom; baseline ≈ y_bottom - descent (~3pt for 11pt Arimo).
    return [
        # ---- PAGE 1, line y=153.21-165.50: Ref + Date (two blocks, same line) -----
        # Left block: "Ref: " (bold) + "CHN/2026/INT/1-XXX\u200b" (regular)
        (
            0, fitz.Rect(72, 151, 280, 168), 162.0, LEFT_MARGIN,
            [
                ("Ref: ", "bold"),
                (f'CHN/2026/INT/1-{v["ref_code"]}\u200b', "reg"),
            ],
        ),
        # Right block: 4 spaces + "Date: " (bold) + "DD-MM-YYYY " (regular)
        (
            0, fitz.Rect(425, 151, 555, 168), 162.0, 435.75,
            [
                ("    ", "reg"),
                ("Date: ", "bold"),
                (f'{v["date"]} ', "reg"),
            ],
        ),

        # ---- PAGE 1 ADDRESS BLOCK ------------------------------------------------
        # y=179.75-192.04: "Mr. <name> ," in bold + trailing space in regular
        (
            0, fitz.Rect(72, 178, 545, 194), 188.5, LEFT_MARGIN,
            [
                (f'{v["name"]} ,', "bold"),
                (" ", "reg"),
            ],
        ),
        # y=192.40-204.69: address line 1
        (
            0, fitz.Rect(72, 191, 545, 206), 201.5, LEFT_MARGIN,
            [(f'{v["addr1"]}', "reg")],
        ),
        # y=205.05-217.34: address line 2
        (
            0, fitz.Rect(72, 204, 545, 219), 214.5, LEFT_MARGIN,
            [(f'{v["addr2"]}', "reg")],
        ),
        # y=217.70-229.99: address line 3
        (
            0, fitz.Rect(72, 217, 545, 232), 227.0, LEFT_MARGIN,
            [(f'{v["addr3"]}', "reg")],
        ),
        # y=230.35-242.64: phone
        (
            0, fitz.Rect(72, 229, 545, 244), 239.5, LEFT_MARGIN,
            [(f'{v["phone"]} ', "reg")],
        ),
        # y=243.00-255.29: email
        (
            0, fitz.Rect(72, 242, 545, 257), 252.5, LEFT_MARGIN,
            [(f'{v["email"]} ', "reg")],
        ),

        # ---- PAGE 1, line y=284.10-296.38: "Dear Mr. <name>," --------------------
        (
            0, fitz.Rect(72, 283, 545, 298), 293.5, LEFT_MARGIN,
            [
                ("Dear ", "reg"),
                (f'{v["name"]}, ', "bold"),
            ],
        ),

        # ---- PAGE 1, line y=362.49-374.78: "as an <designation>, operating ..." --
        (
            0, fitz.Rect(72, 361, 555, 376), 372.0, LEFT_MARGIN,
            [(
                f'as an {v["designation"]}, operating out of our Besant Nagar, Chennai office. ',
                "reg",
            )],
        ),

        # ---- PAGE 1, line y=387.77-400.06: salary in full (amount + words) -------
        (
            0, fitz.Rect(72, 386, 555, 401), 397.5, LEFT_MARGIN,
            [
                ("Your monthly internship stipend shall be ", "reg"),
                (f'\u20b9{v["salary_amount"]}/- ', "bold"),
                (f'(Indian Rupees {v["salary_words"]} only). ', "reg"),
            ],
        ),

        # ---- PAGE 1, line y=466.18-478.47: joining date in commencement sentence -
        (
            0, fitz.Rect(72, 465, 555, 480), 475.5, LEFT_MARGIN,
            [(
                f'Your internship engagement shall commence on {v["date"]} '
                f'and shall continue until such time ',
                "reg",
            )],
        ),

        # ---- PAGE 3, line y=203.20-215.49: salary amount in annexure clause 1 ----
        (
            2, fitz.Rect(72, 202, 555, 217), 213.0, LEFT_MARGIN,
            [(
                f'The Intern shall be paid a monthly stipend of \u20b9{v["salary_amount"]}/-, '
                f'payable on a pro-rata basis subject to ',
                "reg",
            )],
        ),
    ]


def _render_segments(page, baseline_y: float, x_start: float, segments):
    """Place each (text, font_key) segment at the calculated cursor position."""
    x = x_start
    for text, fkey in segments:
        if not text:
            continue
        name, file, size, color = _FONTS[fkey]
        page.insert_text(
            (x, baseline_y),
            text,
            fontname=name,
            fontfile=file,
            fontsize=size,
            color=color,
        )
        # Advance cursor by the rendered width of the segment in its own font.
        x += fitz.Font(fontfile=file).text_length(text, size)


def build_offer_letter(values: dict) -> bytes:
    """Generate the filled Offer Letter PDF as bytes."""
    replacements = _build_replacements(values)

    doc = fitz.open(str(SOURCE_PDF))

    # 1) Apply redactions, batched per page (apply_redactions is per-page).
    by_page = {}
    for page_idx, rect, baseline_y, x_start, segments in replacements:
        by_page.setdefault(page_idx, []).append((rect, baseline_y, x_start, segments))
    for page_idx, items in by_page.items():
        page = doc[page_idx]
        for rect, _, _, _ in items:
            page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    # 2) Re-render the new content for each replaced line.
    for page_idx, items in by_page.items():
        page = doc[page_idx]
        for _rect, baseline_y, x_start, segments in items:
            _render_segments(page, baseline_y, x_start, segments)

    out = io.BytesIO()
    doc.save(out, garbage=4, deflate=True, clean=True)
    doc.close()
    return out.getvalue()
