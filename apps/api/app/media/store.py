"""Private object storage for photos (FR-7.7, D10 M-9).

Keys are server-generated, `wo/{wo_id}/{photo_id}` with a fresh UUIDv4; the client's filename is
never used. Objects are written without an ACL, so they inherit the bucket's private default.
No environment's init sets an anonymous policy, and v1 has no photo-read route.
"""

import uuid
from typing import Protocol

import boto3
from botocore.config import Config

from app.settings import Settings


def photo_key(wo_id: uuid.UUID, photo_id: uuid.UUID) -> str:
    return f"wo/{wo_id}/{photo_id}"


class PhotoStore(Protocol):
    def put(self, key: str, content: bytes, content_type: str) -> None: ...


class S3PhotoStore:
    def __init__(self, settings: Settings) -> None:
        self._bucket = settings.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=(
                settings.s3_access_key_id.get_secret_value() if settings.s3_access_key_id else None
            ),
            aws_secret_access_key=(
                settings.s3_secret_access_key.get_secret_value()
                if settings.s3_secret_access_key
                else None
            ),
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=3,
                read_timeout=10,
            ),
        )

    def put(self, key: str, content: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=content, ContentType=content_type
        )
