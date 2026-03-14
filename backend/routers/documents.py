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
    """Return a PDF rendering of a markdown document."""
    filepath = _validate_filename(filename)
    content = filepath.read_text(encoding="utf-8")
    title = _title_from_filename(filename)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)

    lines = content.split("\n")
    in_code_block = False

    for line in lines:
        # Code block toggle
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            if in_code_block:
                pdf.ln(2)
                pdf.set_font("Courier", "", 9)
            else:
                pdf.set_font("Helvetica", "", 11)
                pdf.ln(2)
            continue

        if in_code_block:
            pdf.set_font("Courier", "", 9)
            pdf.set_x(15)
            pdf.multi_cell(0, 5, line)
            continue

        stripped = line.strip()

        # Headers
        if stripped.startswith("### "):
            pdf.ln(4)
            pdf.set_font("Helvetica", "B", 13)
            pdf.multi_cell(0, 7, stripped[4:])
            pdf.ln(2)
        elif stripped.startswith("## "):
            pdf.ln(5)
            pdf.set_font("Helvetica", "B", 15)
            pdf.multi_cell(0, 8, stripped[3:])
            pdf.ln(2)
        elif stripped.startswith("# "):
            pdf.ln(6)
            pdf.set_font("Helvetica", "B", 18)
            pdf.multi_cell(0, 10, stripped[2:])
            pdf.ln(3)
        # Bullet lists
        elif stripped.startswith("- ") or stripped.startswith("* "):
            pdf.set_font("Helvetica", "", 11)
            pdf.set_x(15)
            bullet_text = stripped[2:]
            # Handle bold markers in text
            bullet_text = bullet_text.replace("**", "")
            pdf.multi_cell(0, 6, f"  \u2022  {bullet_text}")
        # Empty line
        elif stripped == "":
            pdf.ln(3)
        # Normal paragraph
        else:
            pdf.set_font("Helvetica", "", 11)
            # Strip markdown bold/italic markers for plain text rendering
            clean = stripped.replace("**", "").replace("*", "")
            pdf.multi_cell(0, 6, clean)

    pdf_bytes = pdf.output()
    return Response(
        content=bytes(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{Path(filename).stem}.pdf"'},
    )
