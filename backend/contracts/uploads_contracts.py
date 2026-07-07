from __future__ import annotations

from pydantic import BaseModel


class UploadResponse(BaseModel):
    """Contract for upload responses."""

    filename: str
    stored_as: str
    stored_path: str
    content_type: str
