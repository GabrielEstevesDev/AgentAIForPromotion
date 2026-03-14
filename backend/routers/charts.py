from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import CHARTS_DIR

router = APIRouter(prefix="/api/charts", tags=["charts"])


@router.get("/{filename}")
async def get_chart(filename: str) -> FileResponse:
    # Prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    path = CHARTS_DIR / filename
    if not path.exists() or path.suffix != ".png":
        raise HTTPException(status_code=404, detail="Chart not found.")

    return FileResponse(path, media_type="image/png")
