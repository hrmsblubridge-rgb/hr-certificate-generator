"""
Convert the Internship Certificate PDF into a reusable editable template.

Everything in the original document is preserved EXACTLY:
header, footer, logo, signature block, company details, fonts, sizes,
weights, alignment, spacing, margins and surrounding wording.

Only these four values become blank, manually-fillable AcroForm text widgets,
at the EXACT same position and size as the original values, rendered in the
SAME embedded Roboto-Bold font (bold, 10pt, original dark color) so that any
text typed by HR is visually identical to the original certificate values.

    1. Name                 -> "Mr. Aravind Krishna P M"
    2. Designation          -> "AI Research Analyst"
    3. Commenced on Date    -> "28.07.2025"
    4. Concluded on Date    -> "24.11.2025"
"""

import pymupdf as fitz

SRC = "/app/work/original.pdf"
DST = "/app/work/Internship_Certificate_Template.pdf"

FIELDS = [
    ("Name",            "Mr. Aravind Krishna P M"),
    ("Designation",     "AI Research Analyst"),
    ("CommencedOnDate", "28.07.2025"),
    ("ConcludedOnDate", "24.11.2025"),
]

doc  = fitz.open(SRC)
page = doc[0]

# ---- 1) locate the four original values and white-out their glyphs ----
locations = {}
for name, needle in FIELDS:
    hits = page.search_for(needle)
    if not hits:
        raise RuntimeError(f"Could not locate {needle!r}")
    locations[name] = hits[0]
    page.add_redact_annot(hits[0], fill=(1, 1, 1))

page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

# ---- 2) add a blank text widget at each original location ----
for name, _ in FIELDS:
    rect = locations[name]
    w = fitz.Widget()
    w.field_name      = name
    w.field_type      = fitz.PDF_WIDGET_TYPE_TEXT
    w.field_value     = ""
    w.rect            = rect
    w.text_font       = "HeBo"               # placeholder; we patch DA below
    w.text_fontsize   = 10
    w.text_color      = (0.137, 0.137, 0.231)
    w.fill_color      = None
    w.border_color    = None
    w.border_width    = 0
    w.field_flags     = 0
    page.add_widget(w)

# ---- 3) reuse the document's already-embedded Roboto-Bold for widget text ----
# Roboto-Bold is embedded on the page as resource name /TT1 (xref discovered
# via page.get_fonts()). We register the same font object under name "RobotoB"
# in the AcroForm default resources (/AcroForm/DR/Font) and patch every
# widget's /DA string to use it. Result: typed text is rendered in the exact
# same font/weight/size/color as the original bold values.
roboto_bold_xref = None
for f in page.get_fonts():
    if "Roboto-Bold" in f[3]:
        roboto_bold_xref = f[0]
        break
if roboto_bold_xref is None:
    raise RuntimeError("Roboto-Bold not found in page fonts")

# Get/create AcroForm dict and set DR/Font/RobotoB -> Roboto-Bold font xref.
acroform_xref = doc.pdf_catalog()
catalog_obj = doc.xref_object(acroform_xref, compressed=False)

# Ensure /AcroForm exists with DR pointing to our font.
# Easiest reliable path: set via xref_set_key.
doc.xref_set_key(
    acroform_xref,
    "AcroForm/DR/Font/RobotoB",
    f"{roboto_bold_xref} 0 R",
)
# Also set NeedAppearances so viewers regenerate widget appearance using DR.
doc.xref_set_key(acroform_xref, "AcroForm/NeedAppearances", "true")

# Patch each widget's /DA to reference /RobotoB at 10pt in the original color.
DA = "0.137 0.137 0.231 rg /RobotoB 10 Tf"
for w in page.widgets():
    doc.xref_set_key(w.xref, "DA", f"({DA})")

doc.save(DST, garbage=4, deflate=True, clean=True)
doc.close()
print("OK ->", DST)
