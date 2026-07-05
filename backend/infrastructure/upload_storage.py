from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.core.config import settings


class UploadStorage:
    async def save(self, file_bytes: bytes, original_filename: str) -> dict[str, str]:
        raise NotImplementedError


class LocalUploadStorage(UploadStorage):
    def __init__(self, upload_dir: str) -> None:
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, file_bytes: bytes, original_filename: str) -> dict[str, str]:
        from uuid import uuid4

        safe_name = Path(original_filename).name
        if not safe_name:
            raise ValueError("filename is required")

        suffix = Path(safe_name).suffix.lower()
        stored_name = f"{uuid4().hex}{suffix}"
        destination = (self.upload_dir / stored_name).resolve()
        if self.upload_dir.resolve() not in destination.parents and destination != self.upload_dir.resolve():
            raise ValueError("Invalid filename")

        destination.write_bytes(file_bytes)
        return {
            "filename": safe_name,
            "stored_as": stored_name,
            "stored_path": str(destination),
        }


class S3UploadStorage(UploadStorage):
    def __init__(self, bucket: str, region: str | None = None, access_key_id: str | None = None, secret_access_key: str | None = None, endpoint_url: str | None = None) -> None:
        import boto3

        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            endpoint_url=endpoint_url,
        )

    async def save(self, file_bytes: bytes, original_filename: str) -> dict[str, str]:
        from uuid import uuid4

        safe_name = Path(original_filename).name
        if not safe_name:
            raise ValueError("filename is required")

        suffix = Path(safe_name).suffix.lower()
        stored_name = f"{uuid4().hex}{suffix}"
        self.client.put_object(
            Bucket=self.bucket,
            Key=stored_name,
            Body=file_bytes,
        )
        return {
            "filename": safe_name,
            "stored_as": stored_name,
            "stored_path": f"s3://{self.bucket}/{stored_name}",
        }


class AzureBlobUploadStorage(UploadStorage):
    def __init__(self, connection_string: str, container: str) -> None:
        from azure.storage.blob import BlobServiceClient

        self.container = container
        self.client = BlobServiceClient.from_connection_string(
            connection_string)
        self.container_client = self.client.get_container_client(container)

    async def save(self, file_bytes: bytes, original_filename: str) -> dict[str, str]:
        from uuid import uuid4

        safe_name = Path(original_filename).name
        if not safe_name:
            raise ValueError("filename is required")

        suffix = Path(safe_name).suffix.lower()
        stored_name = f"{uuid4().hex}{suffix}"
        blob_client = self.container_client.get_blob_client(stored_name)
        blob_client.upload_blob(file_bytes, overwrite=True)
        return {
            "filename": safe_name,
            "stored_as": stored_name,
            "stored_path": f"azure://{self.container}/{stored_name}",
        }
