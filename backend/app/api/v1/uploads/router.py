from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.contracts.uploads_contracts import UploadResponse
from backend.core.config import settings
from backend.core.security.dependencies import get_current_active_user
from backend.database.session import get_db
from backend.domain.uploads.model import UploadRecord
from backend.domain.users.model import User
from backend.infrastructure.upload_storage import UploadStorage
from backend.observability.tracing import trace_span

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".pdf", ".txt", ".csv"}
_MAGIC_BYTES: dict[str, tuple[bytes, ...]] = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".pdf": (b"%PDF-",),
    # .txt / .csv are free-form text; no reliable magic bytes to check.
}


def _validate_filename(original_filename: str) -> str:
    safe_name = Path(original_filename).name
    if not safe_name:
        raise HTTPException(status_code=400, detail="filename is required")
    suffix = Path(safe_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="File type not allowed")
    return safe_name


def _validate_content_matches_extension(suffix: str, contents: bytes) -> None:
    signatures = _MAGIC_BYTES.get(suffix)
    if not signatures:
        return
    if not any(contents.startswith(sig) for sig in signatures):
        raise HTTPException(
            status_code=400,
            detail="File content does not match its declared type",
        )


@router.post("/", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    original_name = _validate_filename(file.filename)
    contents = await file.read()
    _validate_content_matches_extension(
        Path(original_name).suffix.lower(), contents)

    with trace_span("upload.create"):
        storage = request.app.state.upload_storage
        if not isinstance(storage, UploadStorage):
            raise HTTPException(
                status_code=500, detail="Upload storage not configured")
        result = await storage.save(
            contents,
            original_name,
            content_type=file.content_type,
        )
        db.add(UploadRecord(
            stored_name=result["stored_as"],
            original_filename=original_name,
            owner_id=current_user.id,
        ))
        await db.flush()
        return result


@router.get("/{stored_name}")
async def download_file(
    stored_name: str,
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    upload_record = await db.scalar(
        select(UploadRecord).where(
            UploadRecord.stored_name == stored_name
        )
    )

    if upload_record is None:
        raise HTTPException(
            status_code=404,
            detail="File not found",
        )

    if (
        upload_record.owner_id != current_user.id
        and not current_user.is_superuser
    ):
        raise HTTPException(
            status_code=403,
            detail="Not authorized to access this file",
        )

    if settings.upload_backend != "local":
        raise HTTPException(
            status_code=501,
            detail=(
                "Download proxying for remote storage backends is not implemented; "
                "issue a short-lived signed URL from the storage provider instead."
            ),
        )

    safe_name = Path(stored_name).name  # Defense in depth against traversal.
    file_path = (Path(settings.upload_dir) / safe_name).resolve()
    upload_root = Path(settings.upload_dir).resolve()

    if upload_root not in file_path.parents:
        raise HTTPException(status_code=404, detail="File not found")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        file_path,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
        },
    )
