"""Employee roster — Excel-backed directory used by the Notification Email tab.

The roster lives in MongoDB (collection `employees`). At server boot, if the
collection is empty AND `EMPLOYEE_SEED_XLSX` (or the default seed file at
`backend/data/employees_seed.xlsx`) is present, we parse it and insert one
row per employee. HR can later replace the whole roster by uploading a new
`.xlsx` file via `POST /api/employees/import`.

Only the fields relevant to the Notification Email compose flow are kept —
name, email, department, team, designation. Everything else in the Excel
(DOB, salary, biometric id, etc.) is intentionally ignored so we don't
inadvertently persist sensitive PII beyond what the feature needs.
"""
from __future__ import annotations

import io
import logging
import os
import re
from pathlib import Path
from typing import Iterable

import openpyxl

logger = logging.getLogger(__name__)

# Column headers we look up in the source Excel. Matching is case-insensitive
# and tolerant of trailing whitespace / minor variants — HR can re-export the
# file from any HR system and it should still line up.
COL_ALIASES: dict[str, tuple[str, ...]] = {
    "name":        ("employee name", "name", "full name"),
    "email":       ("email", "email address", "work email"),
    "department":  ("department", "dept"),
    "team":        ("team",),
    "designation": ("designation", "role", "job title"),
}

DEFAULT_SEED = Path(__file__).parent / "data" / "employees_seed.xlsx"


# --- Excel parsing ---------------------------------------------------------

def _norm(s: object) -> str:
    return re.sub(r"\s+", " ", str(s or "").strip()).lower()


def _find_headers(header_row: Iterable[object]) -> dict[str, int]:
    """Map our logical field names → column index (0-based)."""
    headers = [_norm(v) for v in header_row]
    mapping: dict[str, int] = {}
    for field, aliases in COL_ALIASES.items():
        for i, h in enumerate(headers):
            if h in aliases:
                mapping[field] = i
                break
    missing = [f for f in ("name", "email", "department") if f not in mapping]
    if missing:
        raise ValueError(
            f"Excel is missing required column(s): {', '.join(missing)}. "
            f"Expected headers like 'Employee Name', 'Email', 'Department'."
        )
    return mapping


def parse_employees_xlsx(source: bytes | str | Path) -> list[dict]:
    """Return a list of employee dicts parsed from an .xlsx source."""
    if isinstance(source, (bytes, bytearray)):
        wb = openpyxl.load_workbook(io.BytesIO(source), data_only=True, read_only=True)
    else:
        wb = openpyxl.load_workbook(str(source), data_only=True, read_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    header_row = next(rows, None)
    if not header_row:
        raise ValueError("Excel file is empty (no header row).")
    col = _find_headers(header_row)

    out: list[dict] = []
    for r in rows:
        if not r:
            continue
        name  = (r[col["name"]] or "").strip() if col.get("name") is not None else ""
        email = (r[col["email"]] or "").strip() if col.get("email") is not None else ""
        dept  = (r[col["department"]] or "").strip() if col.get("department") is not None else ""
        team  = (r[col["team"]] or "").strip() if col.get("team") is not None else "" if "team" in col else ""
        role  = (r[col["designation"]] or "").strip() if col.get("designation") is not None else ""
        # Skip fully-empty spillover rows and any row missing an email/name.
        if not name or not email or "@" not in email:
            continue
        # Normalise HTML-escaped ampersands (source file uses "Business &amp; Product").
        dept = dept.replace("&amp;", "&").strip()
        team = team.replace("&amp;", "&").strip()
        out.append({
            "name":        name,
            "email":       email.lower(),
            "department":  dept,
            "team":        team,
            "designation": role,
        })
    return out


# --- MongoDB integration ----------------------------------------------------

async def bootstrap_employees_if_empty(db) -> int:
    """One-shot seed on first boot. Returns the number of rows inserted."""
    if await db.employees.estimated_document_count() > 0:
        return 0
    seed = Path(os.environ.get("EMPLOYEE_SEED_XLSX") or DEFAULT_SEED)
    if not seed.is_file():
        logger.info("employees: no seed file at %s, skipping bootstrap.", seed)
        return 0
    try:
        rows = parse_employees_xlsx(seed)
    except Exception as e:  # corrupt seed shouldn't block boot
        logger.warning("employees: failed to parse seed %s: %s", seed, e)
        return 0
    if not rows:
        return 0
    await db.employees.insert_many(rows)
    await db.employees.create_index("department")
    await db.employees.create_index("email", unique=True)
    logger.info("employees: seeded %d rows from %s", len(rows), seed)
    return len(rows)


async def replace_all_employees(db, rows: list[dict]) -> int:
    """Wholesale replace the roster with the given rows. Returns inserted count."""
    if not rows:
        raise ValueError("No valid employee rows found in the uploaded file.")
    await db.employees.delete_many({})
    await db.employees.insert_many(rows)
    # Ensure indexes exist even after a full rebuild. `email` MUST be unique
    # to match the bootstrap index (Mongo rejects same-name index with
    # different options with IndexKeySpecsConflict / 500 otherwise).
    await db.employees.create_index("department")
    await db.employees.create_index("email", unique=True)
    return len(rows)


async def list_employees(db, department: str | None = None) -> list[dict]:
    query: dict = {}
    if department and department.lower() != "all":
        query["department"] = department
    cursor = db.employees.find(query, {"_id": 0}).sort([("department", 1), ("name", 1)])
    return await cursor.to_list(length=5000)


async def list_departments(db) -> list[dict]:
    """Return distinct departments with their headcount, sorted alphabetically."""
    pipeline = [
        {"$group": {"_id": "$department", "count": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    out: list[dict] = []
    async for doc in db.employees.aggregate(pipeline):
        name = doc["_id"] or "Unassigned"
        out.append({"name": name, "count": doc["count"]})
    return out
