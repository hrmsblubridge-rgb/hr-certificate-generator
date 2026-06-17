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

# Full Roboto-Bold font (bundled at /app/backend/static/fonts/Roboto-Bold.ttf,
# sourced from fontsource/Google Fonts under Apache 2.0). Has full Latin glyph
# coverage so HR can type any character (slashes, hyphens, accents, etc.).
# We deliberately use this instead of the source PDF's *subsetted* Roboto-Bold,
# which lacks glyphs the original certificate never used (e.g. "/").
ROBOTO_BOLD_PATH = STATIC_DIR / "fonts" / "Roboto-Bold.ttf"

# Original bounding boxes of the four values in the source PDF.
# (Pre-computed via page.search_for; encoded here to avoid recomputing per request.)
FIELD_RECTS = {
    "name":        fitz.Rect(134.9945, 212.1071, 242.9505, 225.4271),
    "designation": fitz.Rect(401.7945, 212.1071, 491.9446, 225.4271),
    "commenced":   fitz.Rect(307.4645, 232.1071, 359.3846, 245.4271),
    "concluded":   fitz.Rect(443.6996, 232.1071, 495.6197, 245.4271),
}
# The four ORIGINAL values to redact out of the source PDF.
ORIG_VALUES = {
    "name":        "Mr. Aravind Krishna P M",
    "designation": "AI Research Analyst",
    "commenced":   "28.07.2025",
    "concluded":   "24.11.2025",
}
TEXT_COLOR = (0.137, 0.137, 0.231)   # original dark navy
FONT_SIZE  = 10


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

    No form fields, no editing chrome. Original document is preserved exactly;
    only the four target value strings are redacted out and re-drawn at the
    same baseline using the embedded Roboto-Bold font (same size, weight,
    color) so the result is visually indistinguishable from an original-issue
    certificate.
    """
    doc = fitz.open(str(ORIGINAL_PDF))
    page = doc[0]

    # 1) White-out the four original values (and ONLY those).
    for key, needle in ORIG_VALUES.items():
        hits = page.search_for(needle)
        if hits:
            page.add_redact_annot(hits[0], fill=(1, 1, 1))
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

    # 2) Draw the user's values at the exact same positions using Roboto-Bold.
    for key, rect in FIELD_RECTS.items():
        text = values[key].strip()
        if not text:
            continue
        page.insert_text(
            (rect.x0, rect.y1 - 3),     # baseline aligned to original
            text,
            fontname="RobotoBold",
            fontfile=str(ROBOTO_BOLD_PATH),
            fontsize=FONT_SIZE,
            color=TEXT_COLOR,
        )

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