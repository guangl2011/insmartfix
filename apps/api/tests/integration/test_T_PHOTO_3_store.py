"""T-PHOTO-3 (storage half): photos land in a private bucket under a server-chosen key (M-9)."""

import os
import urllib.error
import urllib.request
import uuid

import pytest

from app.media.store import S3PhotoStore, photo_key
from app.settings import Settings

pytestmark = pytest.mark.integration


@pytest.fixture
def settings() -> Settings:
    if not os.environ.get("S3_ENDPOINT_URL"):
        if os.environ.get("REQUIRE_INTEGRATION") == "1":
            pytest.fail("REQUIRE_INTEGRATION=1 but S3_ENDPOINT_URL is not set")
        pytest.skip("needs S3_ENDPOINT_URL (MinIO)")
    return Settings(
        env="test",
        database_url="sqlite://",
        jwt_secret="test-only-jwt-secret-0123456789abcdef",
    )


def test_photo_key_is_server_generated() -> None:
    wo, photo = uuid.uuid4(), uuid.uuid4()
    assert photo_key(wo, photo) == f"wo/{wo}/{photo}"


def test_T_PHOTO_3_stored_object_is_private(settings: Settings) -> None:
    store = S3PhotoStore(settings)
    key = photo_key(uuid.uuid4(), uuid.uuid4())
    store.put(key, b"\xff\xd8\xff re-encoded bytes \xff\xd9", "image/jpeg")

    # The app's own credentials can read it back...
    obj = store._client.get_object(Bucket=settings.s3_bucket, Key=key)
    assert obj["ContentType"] == "image/jpeg"
    # ...but an anonymous GET is refused, as is listing the bucket.
    base = (settings.s3_endpoint_url or "").rstrip("/")
    for url in (f"{base}/{settings.s3_bucket}/{key}", f"{base}/{settings.s3_bucket}/"):
        with pytest.raises(urllib.error.HTTPError) as info:
            urllib.request.urlopen(url, timeout=5)  # noqa: S310 (test-controlled URL)
        assert info.value.code == 403
