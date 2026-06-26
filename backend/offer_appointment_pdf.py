"""Render the Offer-of-Appointment PDF by substituting dynamic values
directly into the operator-supplied 22-page reference PDF.

This bypasses LibreOffice entirely — we open the source PDF, find each
candidate-specific text fragment via PyMuPDF's search, redact it (white
fill at its exact bbox), and re-insert the operator-supplied value at
the same baseline using the page's existing font properties. Output is
byte-faithful to the source layout — same 22 pages, same alignment,
same fonts everywhere except the substituted text spans.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import pymupdf as fitz

from offer_letter_email import (
    indian_format,
    indian_number_to_words,
    scale_compensation,
)

SOURCE_PDF = Path(__file__).parent / "templates" / "offer_of_appointment_source.pdf"

# Default rendering style for the substituted text. The source PDF uses
# Arial / Calibri — Helvetica (PyMuPDF built-in "helv") is the closest
# visual match without bundling a custom TTF.
DEFAULT_FONT = "helv"
DEFAULT_FONT_BOLD = "hebo"   # Helvetica-Bold
DEFAULT_FONT_SIZE = 9
DEFAULT_COLOR     = (0, 0, 0)


def _get_font_at(page, rect):
    """Inspect the span at `rect` and return (fontname, size, color, is_bold).
    Falls back to DEFAULT_FONT if the span can't be inspected reliably."""
    try:
        d = page.get_text("dict", clip=rect)
        for b in d.get("blocks", []):
            for l in b.get("lines", []):
                for s in l.get("spans", []):
                    fname = s.get("font", "")
                    size  = s.get("size", DEFAULT_FONT_SIZE)
                    bold  = "Bold" in fname or s.get("flags", 0) & 16
                    return (fname, size, bold)
    except Exception:
        pass
    return ("", DEFAULT_FONT_SIZE, False)


def _replace_text_pdf(page, old: str, new: str, *, max_hits: int = 999,
                      page_filter_fn=None) -> int:
    """Find each occurrence of `old` on `page` and replace with `new`.

    Uses redact-annot + insert_text. Preserves the y-baseline so the new
    text lands exactly where the old text was. `page_filter_fn(rect)` can
    veto specific bbox hits (used to scope the global "Tier 2" replacement
    to the Annexure-A header only, not the tier-bands reference table).
    """
    rects = page.search_for(old)
    if not rects:
        return 0
    if page_filter_fn:
        rects = [r for r in rects if page_filter_fn(r)]
    if not rects:
        return 0
    placements = []
    for r in rects[:max_hits]:
        _, size, bold = _get_font_at(page, r)
        font = DEFAULT_FONT_BOLD if bold else DEFAULT_FONT
        placements.append((fitz.Rect(r), font, size))
        page.add_redact_annot(r, fill=(1, 1, 1))
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
    for r, font, size in placements:
        # PyMuPDF places text with the baseline AT the y-coordinate, so we
        # use r.y1 minus a small descent margin (~0.2 * size) to align.
        baseline_y = r.y1 - 0.18 * size
        page.insert_text(
            (r.x0, baseline_y),
            new,
            fontname=font,
            fontsize=size,
            color=DEFAULT_COLOR,
        )
    return len(placements)


def render_pdf(data: dict) -> bytes:
    """Open the source PDF, substitute every dynamic value, return PDF bytes."""
    title       = data["title"].strip()
    name        = data["name"].strip()
    full_name   = f"{title} {name}".strip()
    designation = data["designation"].strip()
    cur_date    = data["cur_date"].strip()
    joining     = data["date"].strip()
    ref_number  = data["reference_number"].strip()
    addr1       = data["address_line1"].strip()
    addr2       = data["address_line2"].strip()
    addr3       = data["address_line3"].strip()
    phone       = data["phone"].strip()
    email       = data["email"].strip()
    annual_ctc  = int(data["ctc_yearly"])
    comp        = scale_compensation(annual_ctc)
    tier_label  = comp["tier"]
    ctc_str     = indian_format(annual_ctc)
    ctc_words   = indian_number_to_words(annual_ctc).replace(" Only", "")

    doc = fitz.open(str(SOURCE_PDF))

    # ---- Global per-page substitutions (longest patterns first to avoid
    #      partial overlaps like "Revathi" matching inside "Ms. Revathi"). --
    global_mappings: List[Tuple[str, str]] = [
        ("Ms. Revathi Thiruppathi", full_name),
        ("Dear Revathi Thiruppathi", f"Dear {full_name}"),
        ("Revathi Thiruppathi", name),
        ("CHN/2025/Res/1-026", ref_number),
        ("2/162 E, Nethaji Nagar, 3rd cross,", addr1),
        ("Kanagamutlu(post),",                 addr2),
        ("Krishnagiri - 635001",               addr3),
        ("Phone: 8300233625", f"Phone: {phone}"),
        ("8300233625",        phone),
        ("revathitdgrs@gmail.com", email),
        ("Research Scientist", designation),
        # Joining-date phrase first, so the remaining "08-June-2026"
        # occurrences get the LETTER date.
        ("join on 08-June-2026", f"join on {joining}"),
        ("08-June-2026", cur_date),
        # CTC figures + words
        ("Rs 660,000", f"Rs {ctc_str}"),
        ("Indian Rupees Six Lakh Sixty Thousand",
         f"Indian Rupees {ctc_words}"),
        # Compensation table values (Annexure A, page 3) — reference values
        # @ CTC=660,000 get rescaled.
        ("2,97,000", indian_format(comp["basic"] + comp["hra"])),
        ("1,98,000", indian_format(comp["basic"])),
        ("99,000",   indian_format(comp["hra"])),
        ("1,99,884", indian_format(comp["lta"] + comp["phone"] + comp["bonus"]
                                  + comp["stay"] + comp["special"] + comp["food"])),
        ("11,220",   indian_format(comp["lta"])),
        ("13,200",   indian_format(comp["phone"])),
        ("19,800",   indian_format(comp["bonus"])),
        ("60,000",   indian_format(comp["stay"])),
        ("81,144",   indian_format(comp["special"])),
        ("14,520",   indian_format(comp["food"])),
        ("31,116",   indian_format(comp["pf"] + comp["gratuity"])),
        ("21,600",   indian_format(comp["pf"])),
        ("9,516",    indian_format(comp["gratuity"])),
        ("5,28,000", indian_format(comp["fixed_total"])),
        ("1,32,000", indian_format(comp["variable"])),
        ("6,60,000", indian_format(comp["ctc_total"])),
    ]

    # "Tier 2" replacement is page-scoped to page 3 only (Annexure A header
    # cell). Page 4 has the tier-bands reference table where "Tier 2" must
    # remain as a static bracket label.
    for p_idx in range(doc.page_count):
        page = doc[p_idx]
        for old, new in global_mappings:
            if old != new and old:
                _replace_text_pdf(page, old, new)
        # Page-scoped: Annexure A "Tier:  Tier 2" (page 3 only).
        if p_idx == 2:   # page 3 (0-indexed)
            _replace_text_pdf(page, "Tier 2", tier_label)

    out = doc.tobytes(garbage=4, deflate=True, clean=True)
    doc.close()
    return out
