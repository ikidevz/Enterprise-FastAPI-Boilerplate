from pathlib import Path
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from backend.common.dependencies import get_current_active_user
from backend.common.tracing import trace_span
from backend.domain.users.model import User
from backend.infrastructure.upload_storage import UploadStorage

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf", ".txt", ".csv"}


def _validate_filename(original_filename: str) -> str:
    safe_name = Path(original_filename).name
    if not safe_name:
        raise HTTPException(status_code=400, detail="filename is required")

    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="File type not allowed")

    return safe_name


@router.post("/", response_model=dict[str, str], status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
) -> dict[str, str]:
    original_name = _validate_filename(file.filename)
    contents = await file.read()

    with trace_span("upload.create"):
        storage = request.app.state.upload_storage
        if not isinstance(storage, UploadStorage):
            raise HTTPException(
                status_code=500, detail="Upload storage not configured")
        result = await storage.save(contents, original_name)
        result["content_type"] = file.content_type or "application/octet-stream"
        return result
