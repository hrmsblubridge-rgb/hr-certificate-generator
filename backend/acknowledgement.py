"""
Letter of Acknowledgement of Original Document — PDF generator.

Bakes user-supplied values into the source acknowledgement PDF without
touching anything else (font, size, weight, alignment, header, footer,
signature block, layout).

Editable fields:
  * date           – e.g. "Jan 09, 2026"
  * name           – appears in TWO places (address block + "Dear …,")
  * marksheet_type – e.g. "10th", "12th", "Bachelor's Degree", etc. — slots
                     into the body sentence "...your original <X> Mark Sheet."
"""
from __future__ import annotations
from pathlib import Path
from typing import List, Tuple
import io

import pymupdf as fitz

STATIC_DIR  = Path(__file__).parent / "static"
SOURCE_PDF  = STATIC_DIR / "Acknowledgement_Original.pdf"

# Fonts: the same bundled Roboto family the certificate uses (the source PDF
# embeds subsetted Roboto-Regular / Roboto-Bold). Full-Latin TTFs ensure we
# have every glyph HR might type (e.g. apostrophe in "Bachelor's").
ROBOTO_REGULAR = STATIC_DIR / "fonts" / "Roboto-Regular.ttf"
ROBOTO_BOLD    = STATIC_DIR / "fonts" / "Roboto-Bold.ttf"

FONT_SIZE     = 10
SUP_FONT_SIZE = 5.83        # superscript "th"/"st"/"nd"/"rd" — matches source
SUP_BASELINE_RISE = 3.0     # raise baseline by 3pt for the superscript (per source PDF)
TEXT_COLOR    = (0x23/255, 0x1F/255, 0x20/255)   # #231F20, the source colour
LEFT_MARGIN   = 42.06       # body-text left margin
RIGHT_MARGIN  = 560.17      # body-text right margin (justified edge)

_FONTS = {
    "reg":  ("RobR", str(ROBOTO_REGULAR), FONT_SIZE,     TEXT_COLOR),
    "bold": ("RobB", str(ROBOTO_BOLD),    FONT_SIZE,     TEXT_COLOR),
    "sup":  ("RobR", str(ROBOTO_REGULAR), SUP_FONT_SIZE, TEXT_COLOR),
}


def _split_ordinal(text: str):
    """If `text` is an ordinal like '10th', '12th', '1st', '2nd', '3rd',
    return (digits, suffix). Otherwise return (text, None).

    The suffix is what should be rendered as superscript.
    """
    import re
    m = re.match(r'^(\d+)(st|nd|rd|th)$', text.strip(), flags=re.IGNORECASE)
    if not m:
        return text, None
    return m.group(1), m.group(2).lower()

# LineReplacement (page, redact_rect, align, baseline_y, x_start, segments)
LineReplacement = Tuple[int, fitz.Rect, str, float, float, List[Tuple[str, str]]]


def _build_replacements(v: dict) -> List[LineReplacement]:
    """Compose all line replacements from a single dict of user inputs."""
    name = v["name"].strip()
    date = v["date"].strip()
    marksheet = v["marksheet_type"].strip()

    # Auto-format the marksheet input. If user typed an ordinal like "10th"
    # or "12th", split into digit + suffix so the suffix can be rendered as
    # superscript (matching the source PDF's "10ᵗʰ" styling). For non-ordinal
    # values like "Bachelor's Degree" we just emit a single regular segment.
    digits, suffix = _split_ordinal(marksheet)
    if suffix:
        marksheet_segments = [(digits, "reg"), (suffix, "sup")]
    else:
        marksheet_segments = [(marksheet, "reg")]

    return [
        # ---- Date line (y=184.0-197.3) ------------------------------------
        (0, fitz.Rect(40, 183, 300, 199), "left", 194.5, LEFT_MARGIN,
            [(date, "reg")]),

        # ---- Name in address block (y=206.0-219.3, bold) ------------------
        (0, fitz.Rect(40, 205, 400, 221), "left", 216.5, LEFT_MARGIN,
            [(name, "bold")]),

        # ---- "Dear <name>," greeting (y=289.1-302.4, mixed) ----------------
        (0, fitz.Rect(40, 288, 400, 304), "left", 299.5, LEFT_MARGIN,
            [("Dear ", "reg"),
             (name, "bold"),
             (",", "reg")]),

        # ---- Body line containing marksheet (y=315.0-328.3, JUSTIFY) -------
        # Original: "...of your original 10ᵗʰ Mark Sheet. We understand that the "
        # The "th" in the original is rendered as a 5.83pt superscript; we
        # reproduce that styling automatically for ordinal inputs.
        (0, fitz.Rect(40, 314, 565, 330), "just", 325.5, LEFT_MARGIN,
            [("Blubridge Technologies Pvt Ltd acknowledges the receipt of your original ", "reg"),
             *marksheet_segments,
             (" Mark Sheet. We understand that the ", "reg")]),
    ]


# --- Tokenisation + renderers (essentially the same primitives the offer ---
# --- letter uses; tuned for THIS document's margins).                    ---

def _tokenise(segments):
    """Flatten (text, font_key) segments into word/space tokens with widths."""
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
    x = x_start
    for text, fkey in segments:
        if not text:
            continue
        name, file, size, color = _FONTS[fkey]
        # Superscript segments render with their baseline raised.
        seg_baseline = baseline_y - (SUP_BASELINE_RISE if fkey == "sup" else 0.0)
        page.insert_text((x, seg_baseline), text,
                         fontname=name, fontfile=file, fontsize=size, color=color)
        x += fitz.Font(fontfile=file).text_length(text, size)


def _render_justified(page, baseline_y, segments):
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
            seg_baseline = baseline_y - (SUP_BASELINE_RISE if tok["fkey"] == "sup" else 0.0)
            page.insert_text((x, seg_baseline), tok["text"],
                             fontname=name, fontfile=file, fontsize=size, color=color)
        x += tok["width"] + (extra_per_space if tok["is_space"] else 0.0)


def build_acknowledgement(values: dict) -> bytes:
    """Generate the filled Acknowledgement PDF as bytes."""
    replacements = _build_replacements(values)
    doc = fitz.open(str(SOURCE_PDF))
    page = doc[0]

    # 1) Redactions
    for _, rect, *_ in replacements:
        page.add_redact_annot(rect, fill=(1, 1, 1))
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    # 2) Re-render each line
    for _, _rect, align, baseline_y, x_start, segments in replacements:
        if align == "left":
            _render_left(page, baseline_y, x_start, segments)
        else:
            _render_justified(page, baseline_y, segments)

    out = io.BytesIO()
    doc.save(out, garbage=4, deflate=True, clean=True)
    doc.close()
    return out.getvalue()
