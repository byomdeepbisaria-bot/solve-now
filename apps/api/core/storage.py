import os
import uuid
import logging
from typing import AsyncGenerator, Optional
from fastapi import UploadFile

logger = logging.getLogger(__name__)


class S3StorageProvider:
    """
    Production S3-compatible object storage provider.
    Works with AWS S3, Cloudflare R2, MinIO, and DigitalOcean Spaces.

    Falls back to local filesystem only when S3_ENDPOINT_URL is not configured
    (development only). In production, missing config raises ValueError on startup.
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
            logger.info(f"Storage: S3-compatible backend ({self.endpoint_url or 'AWS'}), bucket={self.bucket}")
        elif self.environment == "production":
            raise ValueError(
                "S3 storage credentials are required in production. "
                "Set S3_ACCESS_KEY_ID and S3_SECRET_ACCESS_KEY environment variables."
            )
        else:
            self.use_s3 = False
            self.local_base = "storage"
            os.makedirs(self.local_base, exist_ok=True)
            logger.warning("Storage: Using LOCAL FILESYSTEM — for development only. Do not use in production.")

    def _init_s3(self):
        import boto3
        kwargs = {
            "aws_access_key_id": self.access_key,
            "aws_secret_access_key": self.secret_key,
            "region_name": self.region,
        }
        if self.endpoint_url:
            kwargs["endpoint_url"] = self.endpoint_url

        self._s3 = boto3.client("s3", **kwargs)

    async def upload(self, file: UploadFile, storage_key: str) -> str:
        """Upload a file to storage. Returns the storage key."""
        await file.seek(0)

        if self.use_s3:
            import io
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
        if self.use_s3:
            # In S3 mode, use presigned URLs — streaming is done client-side
            raise RuntimeError("Use get_presigned_url() for S3-backed storage, not get_stream()")

        import aiofiles
        path = os.path.join(self.local_base, storage_key)
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {storage_key}")

        async with aiofiles.open(path, "rb") as f:
            while chunk := await f.read(1024 * 1024):
                yield chunk

    def delete(self, storage_key: str) -> None:
        """Delete a file from storage."""
        if self.use_s3:
            self._s3.delete_object(Bucket=self.bucket, Key=storage_key)
            logger.info(f"Deleted {storage_key} from S3 bucket {self.bucket}")
        else:
            path = os.path.join(self.local_base, storage_key)
            if os.path.exists(path):
                os.remove(path)

    def object_exists(self, storage_key: str) -> bool:
        """Check if an object exists in storage."""
        if self.use_s3:
            try:
                self._s3.head_object(Bucket=self.bucket, Key=storage_key)
                return True
            except Exception:
                return False
        else:
            return os.path.exists(os.path.join(self.local_base, storage_key))


# Singleton — initialized once at startup
storage = S3StorageProvider()
