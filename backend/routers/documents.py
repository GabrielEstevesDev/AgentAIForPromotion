import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from fpdf import FPDF

from ..config import DOCS_DIR

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _title_from_filename(filename: str) -> str:
    """Derive a human-readable title from a docs filename."""
    stem = Path(filename).stem
    # Strip leading number prefix like "01-"
    stem = re.sub(r"^\d+-", "", stem)
    return stem.replace("-", " ").title()


def _validate_filename(filename: str) -> Path:
    """Validate filename and return the full path, or raise 404."""
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not filename.endswith(".md"):
        raise HTTPException(status_code=400, detail="Only .md files are supported")

    filepath = DOCS_DIR / filename
    if not filepath.is_file():
        raise HTTPException(status_code=404, detail=f"Document '{filename}' not found")
    return filepath


@router.get("")
def list_documents() -> list[dict]:
    """Return all markdown files in the docs directory."""
    if not DOCS_DIR.is_dir():
        return []

    results = []
    for f in sorted(DOCS_DIR.iterdir()):
        if f.suffix == ".md" and f.is_file():
            results.append(
                {
                    "filename": f.name,
                    "title": _title_from_filename(f.name),
                    "size": f.stat().st_size,
                }
            )
    return results


@router.get("/{filename}")
def get_document(filename: str) -> dict:
    """Return the markdown content of a specific document."""
    filepath = _validate_filename(filename)
    content = filepath.read_text(encoding="utf-8")
    return {
        "filename": filename,
        "title": _title_from_filename(filename),
        "content": content,
    }


@router.get("/{filename}/pdf")
def get_document_pdf(filename: str) -> Response:
    """Serve the pre-existing PDF file for a document, if available."""
    _validate_filename(filename)
    pdf_filename = Path(filename).stem + ".pdf"
    pdf_path = DOCS_DIR / pdf_filename

    if not pdf_path.is_file():
        raise HTTPException(status_code=404, detail=f"PDF file '{pdf_filename}' not found")

    pdf_bytes = pdf_path.read_bytes()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{pdf_filename}"'},
    )
