from __future__ import annotations

from io import BytesIO
import shutil
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from app.core.config import get_settings


class StorageService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.local_root = self.settings.data_root / "uploads"
        self.local_root.mkdir(parents=True, exist_ok=True)

    def _client(self) -> Minio:
        return Minio(
            self.settings.minio_endpoint,
            access_key=self.settings.minio_access_key,
            secret_key=self.settings.minio_secret_key,
            secure=self.settings.minio_secure,
        )

    def ensure_bucket(self) -> None:
        try:
            client = self._client()
            if not client.bucket_exists(self.settings.minio_bucket):
                client.make_bucket(self.settings.minio_bucket)
        except Exception:
            self.local_root.mkdir(parents=True, exist_ok=True)

    def save_bytes(self, object_key: str, content_type: str, payload: bytes) -> str:
        self.ensure_bucket()
        try:
            client = self._client()
            client.put_object(
                self.settings.minio_bucket,
                object_key,
                BytesIO(payload),
                length=len(payload),
                content_type=content_type,
            )
            return object_key
        except Exception:
            target = self.local_root / object_key
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            return object_key

    def save_file(self, object_key: str, content_type: str, source_path: Path) -> str:
        self.ensure_bucket()
        try:
            client = self._client()
            client.fput_object(
                self.settings.minio_bucket,
                object_key,
                str(source_path),
                content_type=content_type,
            )
            return object_key
        except Exception:
            target = self.local_root / object_key
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, target)
            return object_key

    def read_bytes(self, object_key: str) -> bytes:
        try:
            client = self._client()
            response = client.get_object(self.settings.minio_bucket, object_key)
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except (Exception, S3Error):
            return (self.local_root / object_key).read_bytes()
