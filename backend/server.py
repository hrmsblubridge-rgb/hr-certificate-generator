from fastapi import FastAPI, APIRouter
from fastapi.responses import FileResponse, StreamingResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import io
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List
import uuid
from datetime import datetime, timezone
import pymupdf as fitz

STATIC_DIR = Path(__file__).parent / "static"
TEMPLATE_PDF = STATIC_DIR / "Internship_Certificate_Template.pdf"
ORIGINAL_PDF = STATIC_DIR / "Aravind_Krishna_Original.pdf"

# Full Roboto fonts (bundled at backend/static/fonts/, sourced from
# fontsource / Google Fonts under Apache 2.0). We embed BOTH weights so the
# replaced paragraph reflows correctly with inline bold/regular mixing —
# matching the original document character-for-character in style.
ROBOTO_REGULAR_PATH = STATIC_DIR / "fonts" / "Roboto-Regular.ttf"
ROBOTO_BOLD_PATH    = STATIC_DIR / "fonts" / "Roboto-Bold.ttf"

# Body paragraph occupies these two original lines (left margin -> right
# margin where text wraps), and the original line spacing is 20pt.
PARA_REDACT_RECT = fitz.Rect(42.06, 207.0, 561.0, 252.0)
# Drawing rect: top adjusted so the first line baseline lands at exactly the
# original y (212.16) given line-height=20pt; bottom extended so the Story
# renderer never auto-shrinks the font below 10pt.
PARA_DRAW_RECT   = fitz.Rect(42.06, 198.43, 561.0, 398.43)
TEXT_COLOR_HEX   = "#231F20"   # original "rich black" of the body text
FONT_SIZE        = 10
LINE_HEIGHT_PT   = 20          # original line spacing (20pt between baselines)

# Original four values to redact out of the source PDF.
ORIG_VALUES = {
    "name":        "Mr. Aravind Krishna P M",
    "designation": "AI Research Analyst",
    "commenced":   "28.07.2025",
    "concluded":   "24.11.2025",
}
TEXT_COLOR = (0x23/255, 0x1F/255, 0x20/255)   # same #231F20 in RGB tuple


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")


# Define Models
class StatusCheck(BaseModel):
    model_config = ConfigDict(extra="ignore")  # Ignore MongoDB's _id field
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StatusCheckCreate(BaseModel):
    client_name: str

# Add your routes to the router instead of directly to app
@api_router.get("/")
async def root():
    return {"message": "Hello World"}


@api_router.get("/template/download")
async def download_template():
    """Download the editable Internship Certificate template PDF."""
    return FileResponse(
        path=str(TEMPLATE_PDF),
        media_type="application/pdf",
        filename="Internship_Certificate_Template.pdf",
    )


@api_router.get("/template/original")
async def download_original():
    """Download the original (reference) certificate PDF."""
    return FileResponse(
        path=str(ORIGINAL_PDF),
        media_type="application/pdf",
        filename="Aravind_Krishna_Original.pdf",
    )


@api_router.get("/template/preview")
async def preview_template():
    """Inline preview of the editable template PDF (for iframe rendering)."""
    return FileResponse(
        path=str(TEMPLATE_PDF),
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="Internship_Certificate_Template.pdf"'},
    )


class CertificateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    designation: str = Field(min_length=1, max_length=120)
    commenced: str = Field(min_length=1, max_length=40)
    concluded: str = Field(min_length=1, max_length=40)


def _build_filled_pdf(values: dict) -> bytes:
    """Bake the four user-supplied values directly into the source PDF.

    Strategy: redact the ENTIRE two-line body paragraph, then re-render it from
    scratch using a Story-based HTML box with the two embedded Roboto weights.
    This guarantees:
      * No leftover blank space when the typed value is shorter than the
        original placeholder (the surrounding text reflows naturally).
      * Inline mixed bold/regular weight — exactly mirroring the original.
      * Same font (Roboto), size (10pt), color (#232369), line spacing (20pt),
        first-line baseline (y=212.16), and right margin.
    """
    import html as _html
    doc = fitz.open(str(ORIGINAL_PDF))
    page = doc[0]

    # 1) Redact the original body paragraph (covers both lines, nothing else).
    page.add_redact_annot(PARA_REDACT_RECT, fill=(1, 1, 1))
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    # 2) Rebuild the paragraph with the user-supplied values.
    e = _html.escape
    body_html = (
        f'<p>This is to certify that <b>{e(values["name"].strip())}</b> '
        f'has completed his internship as an '
        f'<b>{e(values["designation"].strip())}</b> with Blubridge '
        f'Technologies Pvt Ltd. His internship tenure commenced on '
        f'<b>{e(values["commenced"].strip())}</b> and concluded on '
        f'<b>{e(values["concluded"].strip())}</b></p>'
    )
    css = (
        "@font-face { font-family:'R'; src:url(roboto-regular); }"
        "@font-face { font-family:'R'; font-weight:bold; src:url(roboto-bold); }"
        f"* {{ font-family:'R'; font-size:{FONT_SIZE}pt; color:{TEXT_COLOR_HEX};"
        f" line-height:{LINE_HEIGHT_PT}pt; margin:0; padding:0; }}"
    )
    arch = fitz.Archive()
    arch.add(str(ROBOTO_REGULAR_PATH), "roboto-regular")
    arch.add(str(ROBOTO_BOLD_PATH),    "roboto-bold")

    # scale_low=1 disables auto-shrink so the font stays at 10pt.
    page.insert_htmlbox(PARA_DRAW_RECT, body_html, css=css, archive=arch, scale_low=1)

    buf = io.BytesIO()
    doc.save(buf, garbage=4, deflate=True, clean=True)
    doc.close()
    return buf.getvalue()


@api_router.post("/template/generate")
async def generate_certificate(req: CertificateRequest):
    pdf_bytes = _build_filled_pdf(req.model_dump())
    safe_name = "".join(c for c in req.name if c.isalnum() or c in " _-").strip() or "Certificate"
    filename = f"Internship_Certificate_{safe_name.replace(' ', '_')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@api_router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_dict = input.model_dump()
    status_obj = StatusCheck(**status_dict)
    
    # Convert to dict and serialize datetime to ISO string for MongoDB
    doc = status_obj.model_dump()
    doc['timestamp'] = doc['timestamp'].isoformat()
    
    _ = await db.status_checks.insert_one(doc)
    return status_obj

@api_router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    # Exclude MongoDB's _id field from the query results
    status_checks = await db.status_checks.find({}, {"_id": 0}).to_list(1000)
    
    # Convert ISO string timestamps back to datetime objects
    for check in status_checks:
        if isinstance(check['timestamp'], str):
            check['timestamp'] = datetime.fromisoformat(check['timestamp'])
    
    return status_checks

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()