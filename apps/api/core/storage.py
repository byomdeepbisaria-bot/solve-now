import os
import logging
from typing import AsyncGenerator
from fastapi import UploadFile

logger = logging.getLogger(__name__)


class S3StorageProvider:
    """
    Production S3-compatible object storage provider.
    Works with AWS S3, Cloudflare R2, MinIO, and DigitalOcean Spaces.

    Initialization never raises — the provider detects configuration at
    startup and logs warnings. File operations raise a clear RuntimeError
    if called without S3 credentials in production, so the application
    can start and serve non-file routes while the storage error is surfaced
    only on actual upload/download/delete calls.

    S3 credentials (S3_ACCESS_KEY_ID + S3_SECRET_ACCESS_KEY) are REQUIRED
    for file upload functionality in production. Without them, file-related
    endpoints return 503. All other API endpoints are unaffected.
    """

    def __init__(self):
        self.endpoint_url = os.environ.get("S3_ENDPOINT_URL")
        self.access_key = os.environ.get("S3_ACCESS_KEY_ID")
        self.secret_key = os.environ.get("S3_SECRET_ACCESS_KEY")
        self.bucket = os.environ.get("S3_BUCKET_NAME", "solvenow-files")
        self.region = os.environ.get("S3_REGION", "us-east-1")
        self.presigned_expiry = int(os.environ.get("S3_PRESIGNED_URL_EXPIRY", "3600"))
        self.environment = os.environ.get("ENVIRONMENT", "development")

        if self.access_key and self.secret_key:
            self._init_s3()
            self.use_s3 = True
            logger.info(
                f"Storage: S3-compatible backend ({self.endpoint_url or 'AWS'}), "
                f"bucket={self.bucket}"
            )
        elif self.environment == "production":
            # Do NOT raise here — defer the error to first file operation.
            # This allows the application to start and serve all non-file routes.
            self.use_s3 = False
            self._unconfigured_production = True
            logger.warning(
                "Storage: S3 credentials not set. File upload/download endpoints "
                "will return 503 until S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY "
                "are configured. Set these in your Render environment variables."
            )
        else:
            # Development: local filesystem fallback
            self.use_s3 = False
            self._unconfigured_production = False
            self.local_base = "storage"
            os.makedirs(self.local_base, exist_ok=True)
            logger.warning(
                "Storage: Using LOCAL FILESYSTEM — for development only. "
                "Do not use in production."
            )

    def _init_s3(self):
        import boto3
        self._unconfigured_production = False
        kwargs = {
            "aws_access_key_id": self.access_key,
            "aws_secret_access_key": self.secret_key,
            "region_name": self.region,
        }
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url
        self._s3 = boto3.client("s3", **kwargs)

    def _require_storage(self):
        """Raise a clear error if called without storage configured in production."""
        if getattr(self, "_unconfigured_production", False):
            raise RuntimeError(
                "File storage is not configured. "
                "Set S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY in your "
                "Render environment variables to enable file upload/download."
            )

    async def upload(self, file: UploadFile, storage_key: str) -> str:
        """Upload a file to storage. Returns the storage key."""
        self._require_storage()
        await file.seek(0)

        if self.use_s3:
            content = await file.read()
            self._s3.put_object(
                Bucket=self.bucket,
                Key=storage_key,
                Body=content,
                # Private by default — no public ACL
                ContentType=file.content_type or "application/octet-stream",
                ServerSideEncryption="AES256",
            )
            logger.info(f"Uploaded {storage_key} to S3 bucket {self.bucket}")
        else:
            import aiofiles
            path = os.path.join(self.local_base, storage_key)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            async with aiofiles.open(path, "wb") as out:
                while chunk := await file.read(1024 * 1024):
                    await out.write(chunk)

        return storage_key

    def get_presigned_url(self, storage_key: str) -> str:
        """
        Generate a time-limited signed URL for private access.
        In local dev, returns a direct API download URL.
        """
        self._require_storage()
        if self.use_s3:
            url = self._s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": storage_key},
                ExpiresIn=self.presigned_expiry,
            )
            return url
        else:
            # Dev fallback: return key so the API can stream it
            return f"/api/v1/files/stream/{storage_key}"

    async def get_stream(self, storage_key: str) -> AsyncGenerator[bytes, None]:
        """Stream file content. Used for local dev fallback only."""
        self._require_storage()
        if self.use_s3:
            # In S3 mode, use presigned URLs — streaming is done client-side
            raise RuntimeError(
                "Use get_presigned_url() for S3-backed storage, not get_stream()"
            )

        import aiofiles
        path = os.path.join(self.local_base, storage_key)
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {storage_key}")

        async with aiofiles.open(path, "rb") as f:
            while chunk := await f.read(1024 * 1024):
                yield chunk

    def delete(self, storage_key: str) -> None:
        """Delete a file from storage."""
        self._require_storage()
        if self.use_s3:
            self._s3.delete_object(Bucket=self.bucket, Key=storage_key)
            logger.info(f"Deleted {storage_key} from S3 bucket {self.bucket}")
        else:
            path = os.path.join(self.local_base, storage_key)
            if os.path.exists(path):
                os.remove(path)

    def object_exists(self, storage_key: str) -> bool:
        """Check if an object exists in storage."""
        if getattr(self, "_unconfigured_production", False):
            return False
        if self.use_s3:
            try:
                self._s3.head_object(Bucket=self.bucket, Key=storage_key)
                return True
            except Exception:
                return False
        else:
            return os.path.exists(os.path.join(self.local_base, storage_key))


# Singleton — initialized once at startup.
# Never raises during import. File operations will raise RuntimeError
# if S3 is not configured in production.
storage = S3StorageProvider()
