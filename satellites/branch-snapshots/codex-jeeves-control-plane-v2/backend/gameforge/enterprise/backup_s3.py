from __future__ import annotations
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("gameforge.backup_s3")


class S3BackupUploader:
    def __init__(self):
        self.bucket = os.getenv("GAMEFORGE_BACKUP_S3_BUCKET")
        self.prefix = os.getenv("GAMEFORGE_BACKUP_S3_PREFIX", "gameforge/backups/")
        self.region = os.getenv("GAMEFORGE_BACKUP_S3_REGION", "us-east-1")
        self.endpoint = os.getenv("GAMEFORGE_BACKUP_S3_ENDPOINT")
        self.access_key = os.getenv("GAMEFORGE_BACKUP_S3_ACCESS_KEY") or os.getenv("AWS_ACCESS_KEY_ID")
        self.secret_key = os.getenv("GAMEFORGE_BACKUP_S3_SECRET_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")

    @property
    def enabled(self) -> bool:
        return bool(self.bucket)

    def _client(self):
        import boto3

        kwargs = {"region_name": self.region}
        if self.endpoint:
            kwargs["endpoint_url"] = self.endpoint
        if self.access_key and self.secret_key:
            kwargs["aws_access_key_id"] = self.access_key
            kwargs["aws_secret_access_key"] = self.secret_key
        return boto3.client("s3", **kwargs)

    def upload_file(self, local_path: str, key: Optional[str] = None) -> dict:
        if not self.enabled:
            return {"uploaded": False, "reason": "GAMEFORGE_BACKUP_S3_BUCKET not set"}
        path = Path(local_path)
        if not path.exists():
            raise FileNotFoundError(local_path)
        key = key or f"{self.prefix.rstrip('/')}/{path.name}"
        client = self._client()
        client.upload_file(str(path), self.bucket, key)
        logger.info("Uploaded backup s3://%s/%s", self.bucket, key)
        return {
            "uploaded": True,
            "bucket": self.bucket,
            "key": key,
            "uri": f"s3://{self.bucket}/{key}",
        }
