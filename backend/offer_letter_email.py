"""Render the Blubridge multi-page offer letter HTML email.

This module loads the static template (`templates/offer_letter_source.htm`),
injects an embedded stylesheet (so the rendered output is fully self-contained
and previews correctly in an iframe / email client), substitutes every
`[placeholder]`, and — for `standard` mode — proportionally rebuilds the
Annexure-A compensation table from the operator-supplied yearly CTC.

Customized mode is intentionally NOT supported in v1 (per the user's chosen
defaults). The hook is documented at the bottom for the next iteration.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Dict

TEMPLATE_PATH = Path(__file__).parent / "templates" / "offer_letter_source.htm"

# --- Reference Annexure-A table (annual INR @ CTC = 660,000) -----------------
# Used to derive each component's ratio of total CTC. When the operator picks
# a different CTC in "standard" mode we multiply each ratio by the new CTC and
# round to the nearest rupee.
REFERENCE_CTC = 660_000
REFERENCE_COMPONENTS = [
    # (key,            label,                                  annual_inr)
    ("basic",          "Basic",                                  198_000),
    ("hra",            "HRA",                                     99_000),
    ("lta",            "Leave Travel Assistance*",                11_220),
    ("phone",          "Phone & Internet Reimbursement",          13_200),
    ("bonus",          "Bonus",                                   19_800),
    ("stay",           "Stay and Travel Allowance",               60_000),
    ("special",        "Special Allowance",                       81_144),
    ("food",           "Food Reimbursement",                      14_520),
    ("pf",             "PF - Company's Contribution",             21_600),
    ("gratuity",       "Gratuity**",                               9_516),
    ("variable",       "Variable Compensation (at 100%)",        132_000),
]
# Groupings drive the table layout. Each tuple = (heading, [component_keys]).
COMPONENT_GROUPS = [
    ("Base Components (A)",      ["basic", "hra"]),
    ("Basket of Allowances (B)", ["lta", "phone", "bonus", "stay", "special", "food"]),
    ("Retirement Benefits (C)",  ["pf", "gratuity"]),
]

# --- Tier auto-derivation (by monthly Fixed Compensation, per Annexure B) ----
TIER_BANDS = [
    # (min_monthly_fixed_INR, max_monthly_fixed_INR_exclusive, label)
    (100_001, float("inf"), "Tier 0"),
    ( 75_001,        100_001, "Tier 1"),
    ( 40_001,         75_001, "Tier 2"),
    ( 25_001,         40_001, "Tier 3"),
    ( 15_001,         25_001, "Tier 4"),
    ( 10_000,         15_001, "Tier 5"),
]


def derive_tier(annual_fixed_inr: int) -> str:
    monthly = annual_fixed_inr / 12
    for lo, hi, label in TIER_BANDS:
        if lo <= monthly < hi:
            return label
    return "Tier 5"


def scale_compensation(annual_ctc: int) -> dict:
    """Return scaled annual values for every Annexure-A line item plus
    derived totals. Each component's share of CTC is preserved."""
    if annual_ctc <= 0:
        raise ValueError("annual_ctc must be > 0")
    ratio = annual_ctc / REFERENCE_CTC
    scaled = {k: round(v * ratio) for k, _, v in REFERENCE_COMPONENTS}
    fixed_keys = [k for grp in COMPONENT_GROUPS for k in grp[1]]
    scaled["fixed_total"]    = sum(scaled[k] for k in fixed_keys)
    scaled["variable_total"] = scaled["variable"]
    scaled["ctc_total"]      = scaled["fixed_total"] + scaled["variable_total"]
    scaled["tier"]           = derive_tier(scaled["fixed_total"])
    return scaled


# --- Number formatting helpers ----------------------------------------------
def indian_format(n: int) -> str:
    """6,60,000 (Indian grouping) — not 660,000."""
    s = str(int(n))
    if len(s) <= 3:
        return s
    last3, rest = s[-3:], s[:-3]
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    return ",".join(groups) + "," + last3


_UNITS = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight",
          "Nine", "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen",
          "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
_TENS  = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy",
          "Eighty", "Ninety"]


def _below_hundred(n: int) -> str:
    if n < 20:
        return _UNITS[n]
    if n % 10 == 0:
        return _TENS[n // 10]
    return f"{_TENS[n // 10]} {_UNITS[n % 10]}"


def _below_thousand(n: int) -> str:
    if n < 100:
        return _below_hundred(n)
    rem = n % 100
    out = f"{_UNITS[n // 100]} Hundred"
    if rem:
        out += f" {_below_hundred(rem)}"
    return out


def indian_number_to_words(n: int) -> str:
    """660000 -> 'Six Lakh Sixty Thousand Only'."""
    if n == 0:
        return "Zero Only"
    if n < 0:
        return f"Minus {indian_number_to_words(-n)}"
    parts = []
    crore = n // 10_000_000
    n %= 10_000_000
    lakh = n // 100_000
    n %= 100_000
    thousand = n // 1_000
    hundred = n % 1_000
    if crore:
        parts.append(f"{_below_hundred(crore)} Crore")
    if lakh:
        parts.append(f"{_below_hundred(lakh)} Lakh")
    if thousand:
        parts.append(f"{_below_hundred(thousand)} Thousand")
    if hundred:
        parts.append(_below_thousand(hundred))
    return " ".join(parts) + " Only"


# --- Annexure-A table builder -----------------------------------------------
_TABLE_STYLE = ('width:100%; border-collapse:collapse; font-family:Arial,'
                'sans-serif; font-size:12px; color:#000; border:1px solid #000;')
_TH_STYLE    = 'padding:4px; font-weight:bold; text-align:center; font-size:12px;'
_TD_STYLE    = 'padding:4px;'
_TD_NUM      = 'padding:4px; text-align:center;'
_GROUP_STYLE = 'padding:8px; font-weight:bold; background:#f5f5f5;'


def build_annexure_a_table(comp: dict) -> str:
    f = indian_format
    rows = []
    rows.append(
        f'<tr><th style="padding:8px; font-weight:bold; text-align:left; '
        f'width:65%">&nbsp;</th>'
        f'<th style="{_TH_STYLE}">Per Month (in ₹)</th>'
        f'<th style="{_TH_STYLE}">Per Annum (in ₹)</th></tr>'
    )
    label_map = {k: lbl for k, lbl, _ in REFERENCE_COMPONENTS}
    for heading, keys in COMPONENT_GROUPS:
        rows.append(f'<tr><td colspan="3" style="{_GROUP_STYLE}">{heading}</td></tr>')
        for k in keys:
            annual = comp[k]
            monthly = round(annual / 12)
            rows.append(
                f'<tr><td style="{_TD_STYLE}">{label_map[k]}</td>'
                f'<td style="{_TD_NUM}">{f(monthly)}</td>'
                f'<td style="{_TD_NUM}">{f(annual)}</td></tr>'
            )
    # Fixed total
    rows.append(
        f'<tr style="font-weight:bold;">'
        f'<td style="{_TD_STYLE}">Fixed Compensation (A+B+C)</td>'
        f'<td style="{_TD_NUM}">{f(round(comp["fixed_total"] / 12))}</td>'
        f'<td style="{_TD_NUM}">{f(comp["fixed_total"])}</td></tr>'
    )
    # Variable
    rows.append(
        f'<tr style="font-weight:bold;">'
        f'<td style="{_TD_STYLE}">Variable Compensation (at 100%)<br>'
        f'Refer Annexure B for details</td>'
        f'<td style="{_TD_NUM}">{f(round(comp["variable_total"] / 12))}</td>'
        f'<td style="{_TD_NUM}">{f(comp["variable_total"])}</td></tr>'
    )
    # CTC
    rows.append(
        f'<tr style="font-weight:bold;">'
        f'<td style="padding:8px;">Cost to Company '
        f'(Fixed Compensation + Variable Compensation at 100%)</td>'
        f'<td style="{_TD_NUM}">{f(round(comp["ctc_total"] / 12))}</td>'
        f'<td style="{_TD_NUM}">{f(comp["ctc_total"])}</td></tr>'
    )
    return f'<table style="{_TABLE_STYLE}">{"".join(rows)}</table>'


# --- Embedded stylesheet (drop-in replacement for the missing ./css/style.css)
EMBEDDED_CSS = """<style>
  body { font-family: Arial, Helvetica, sans-serif; font-size: 12px;
         color: #000; margin: 0; padding: 0; line-height: 1.55; }
  .page { max-width: 600px; margin: 0 auto; padding: 30px 36px 48px;
          background: #fff; page-break-after: always; }
  .page + .page { border-top: 1px dashed #ccc; }
  table.top-row { width: 100%; border-collapse: collapse; margin-bottom: 12px; }
  table.top-row td { padding: 4px 0; vertical-align: middle; }
  table.top-row td.center { text-align: center; }
  table.top-row td.left   { text-align: left;  font-weight: bold; }
  table.top-row td.right  { text-align: right; font-weight: bold; }
  table.top-row img { max-height: 56px; }
  .address { margin: 20px 0 18px; line-height: 1.6; }
  h2, h3, h4 { color: #000; }
  h2.title { text-align: center; font-size: 14px; text-decoration: underline;
             margin: 24px 0 8px; }
  h3.sub-title, h3.subtitle { text-align: center; font-size: 12px;
                              text-decoration: underline; margin: 4px 0 14px; }
  h3 { font-size: 13px; margin: 18px 0 6px; }
  p { margin: 8px 0; }
  ol.list, ol.alpha-list { margin: 12px 0 12px 22px; padding: 0; }
  ol.list li, ol.alpha-list li { margin-bottom: 9px; line-height: 1.55; }
  ol.roman { list-style-type: lower-roman; margin: 8px 0 8px 22px; }
  ol.alpha-list { list-style-type: lower-alpha; }
  ul, ul.bullet { margin: 8px 0 8px 22px; padding: 0; }
  ul li { margin-bottom: 6px; }
  .encl { font-size: 11.5px; line-height: 1.6; margin-top: 14px; }
  .footer-sign { width: 100%; margin-top: 28px; border-collapse: collapse; }
  .footer-sign td { padding: 6px 0; }
  .info-table { width: 100%; border-collapse: collapse; margin: 6px 0 14px;
                font-size: 12px; }
  .info-table td { padding: 6px 8px; border: 1px solid #000; }
  .info-table td.value { font-weight: bold; }
  .insurance { margin-top: 14px; font-size: 12px; }
  .insurance ul li { margin-bottom: 4px; }
  .small-note, .small { font-size: 10.5px; color: #333; }
  .table-title { text-align: center; margin: 14px 0 4px; }
  .note { margin-top: 12px; }
  .sub-heading { font-style: italic; margin: 8px 0 4px; }
  .heading { font-weight: bold; margin-top: 12px; }
  .item, .indent  { margin-left: 22px; }
  .indent2 { margin-left: 44px; }
  .bullet  { list-style: disc; }
  .blue { color: #155cc2; text-decoration: underline; }
  .declaration-text { margin: 14px 0; line-height: 1.7; }
  .sign-table { width: 100%; border-collapse: collapse; margin-top: 18px; }
  .sign-table td { padding: 8px 0; border-bottom: 1px solid #000; }
  .sign-table td.label { width: 25%; border-bottom: none; font-weight: bold; }
  .line2 { border-top: 1px solid #000; margin: 18px 0; }
  img { max-width: 220px; }
  @media (max-width: 720px) {
    .page { padding: 20px 16px; }
    table.top-row img { max-height: 44px; }
    h2.title { font-size: 13px; }
  }
</style>"""


# --- Top-level renderer ------------------------------------------------------
PLACEHOLDERS = [
    "reference_number", "cur_date", "title", "name",
    "address_line1", "address_line2", "address_line3",
    "phone", "email", "date", "designation", "tier",
    "ruppe", "inr_ruppe_text",
]

# The original Annexure-A reference table appears between the
# Annexure-A `<table class="info-table">` and the `<div class="insurance">`.
# We swap that single fixed table for one scaled to the operator's CTC.
_REF_TABLE_RE = re.compile(
    r'<table[^>]*cellspacing="0"\s+border="1"[^>]*>.*?Cost to Company.*?</table>',
    flags=re.DOTALL,
)


def render_offer_letter(data: dict) -> str:
    """Substitute placeholders + (standard mode) rebuild the Annexure-A
    compensation table. Returns a complete self-contained HTML document."""
    html = TEMPLATE_PATH.read_text(encoding="utf-8")
    # Inject the embedded stylesheet (the original points to a missing CSS file).
    html = html.replace(
        '<link rel="stylesheet" href="./css/style.css">',
        EMBEDDED_CSS,
    )

    annual_ctc = int(data["ctc_yearly"])
    comp = scale_compensation(annual_ctc)

    # Rebuild Annexure-A compensation table.
    new_table = build_annexure_a_table(comp)
    # Replace exactly ONE occurrence (the reference table in Annexure A).
    html, n = _REF_TABLE_RE.subn(new_table, html, count=1)
    if n == 0:
        # Source template surprise — surface a clear error rather than ship
        # a silently-broken letter.
        raise RuntimeError(
            "Annexure-A reference table not found in source template; "
            "the placeholder substitution would emit stale numbers."
        )

    # Compute derived placeholder values.
    today_iso = data.get("cur_date") or date.today().strftime("%d.%m.%Y")
    bag = {
        "reference_number": data["reference_number"],
        "cur_date":         today_iso,
        "title":            data["title"],
        "name":             data["name"],
        "address_line1":    data["address_line1"],
        "address_line2":    data["address_line2"],
        "address_line3":    data["address_line3"],
        "phone":            data["phone"],
        "email":            data["email"],
        "date":             data["date"],
        "designation":      data["designation"],
        "tier":             comp["tier"],
        "ruppe":            indian_format(comp["ctc_total"]),
        "inr_ruppe_text":   indian_number_to_words(comp["ctc_total"]),
    }

    for key, val in bag.items():
        html = html.replace(f"[{key}]", str(val))

    # Also patch the hard-coded "Research Scientist" + "Besant Nagar, Chennai"
    # block in paragraph 1 of the body — the user wants the designation to be
    # configurable. The location is unchanged.
    html = html.replace(
        "<strong>Research Scientist</strong>",
        f"<strong>{data['designation']}</strong>",
    )

    return html


# --- Future hook: customized mode (line-item override) ----------------------
# When the user later opts in to "customized" mode, the form will supply each
# annual line-item value directly. The next-iteration patch is:
#   1. Accept `data["custom"]` dict with the same keys as REFERENCE_COMPONENTS.
#   2. Skip `scale_compensation` and feed `data["custom"]` straight into
#      `build_annexure_a_table` (after computing fixed/variable/ctc totals).
#   3. Derive tier from the customized fixed_total via `derive_tier`.
