"""T-PHOTO-1, T-PHOTO-3, T-IDEM-1 (photos) over HTTP against Postgres + MinIO (FR-7.7, D10 M-9)."""

import hashlib
import io
import os
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import Connection, Engine, func, select, text
from sqlalchemy.orm import Session

from app.auth.tokens import issue_token
from app.contract.workorders import PhotoResponse
from app.db.models import Photo
from app.db.session import get_engine, get_sessionmaker
from app.main import create_app
from app.media import routes as media_routes
from app.media.routes import MAX_PHOTOS_PER_WO
from app.media.store import S3PhotoStore
from app.media.validate import MAX_UPLOAD_BYTES
from app.settings import normalize_database_url
from tests.conftest import TEST_JWT_SECRET, make_settings
from tests.integration.conftest import World, make_world
from tests.media import images

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)


@pytest.fixture
def api(migrated_db: None) -> Iterator[TestClient]:
    if not os.environ.get("S3_ENDPOINT_URL"):
        if os.environ.get("REQUIRE_INTEGRATION") == "1":
            pytest.fail("REQUIRE_INTEGRATION=1 but S3_ENDPOINT_URL is not set")
        pytest.skip("needs S3_ENDPOINT_URL (MinIO)")
    url = normalize_database_url(os.environ["DATABASE_URL"])
    with TestClient(create_app(make_settings(url, env="ci"))) as c:
        yield c
    media_routes._stores.clear()
    get_sessionmaker.cache_clear()
    get_engine.cache_clear()


@dataclass(frozen=True)
class Job:
    world: World
    second_contractor_id: uuid.UUID
    second_user_id: uuid.UUID
    second_wo_id: uuid.UUID  # bound to the second contractor


def _bind(
    conn: Connection, w: World, wo_id: uuid.UUID, contractor_id: uuid.UUID, state: str
) -> None:
    """Make `contractor_id` the candidate for `wo_id` in dispatch `state` (ACCEPTED or PENDING)."""
    cand = "ACCEPTED" if state == "ACCEPTED" else "OFFERED"
    conn.execute(
        text(
            "INSERT INTO dispatch_candidates (wo_id, contractor_id, tenant_id, rank, match_score, "
            "match_reason, state, offered_at, sla_deadline) "
            "VALUES (:wo, :c, :t, 1, 0.9, 'r', :cs, :at, :dl)"
        ),
        {
            "wo": wo_id,
            "c": contractor_id,
            "t": w.tenant_id,
            "cs": cand,
            "at": NOW,
            "dl": NOW + timedelta(hours=1),
        },
    )
    conn.execute(
        text(
            "INSERT INTO dispatch (wo_id, tenant_id, state, current_contractor_id, sla_minutes, "
            "sla_deadline) VALUES (:wo, :t, :s, :c, 60, :dl)"
        ),
        {
            "wo": wo_id,
            "t": w.tenant_id,
            "s": state,
            "c": contractor_id,
            "dl": NOW + timedelta(hours=1),
        },
    )


@pytest.fixture
def job(app_engine: Engine) -> Job:
    with app_engine.begin() as conn:
        w = make_world(conn)
        _bind(conn, w, w.wo_id, w.contractor_id, "ACCEPTED")
        tag = uuid.uuid4().hex[:8]
        c2 = conn.execute(
            text("INSERT INTO contractors (tenant_id, name) VALUES (:t, 'Ana') RETURNING id"),
            {"t": w.tenant_id},
        ).scalar_one()
        u2 = conn.execute(
            text(
                "INSERT INTO users (tenant_id, email, name, role, contractor_id) "
                "VALUES (:t, :e, 'Ana', 'contractor', :c) RETURNING id"
            ),
            {"t": w.tenant_id, "e": f"ana-{tag}@test.example", "c": c2},
        ).scalar_one()
        wo2 = conn.execute(
            text(
                "INSERT INTO workorders (tenant_id, asset_id, symptom) "
                "VALUES (:t, :a, 'y') RETURNING id"
            ),
            {"t": w.tenant_id, "a": w.asset_id},
        ).scalar_one()
        _bind(conn, w, wo2, c2, "ACCEPTED")
    return Job(w, c2, u2, wo2)


def _headers(engine: Engine, user_id: uuid.UUID, key: str | None = None) -> dict[str, str]:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT role, tenant_id, contractor_id, token_version FROM users WHERE id = :u"),
            {"u": user_id},
        ).one()
    token, _ = issue_token(
        user_id=user_id,
        role=row.role,
        tenant_id=row.tenant_id,
        contractor_id=row.contractor_id,
        token_version=row.token_version,
        secret=TEST_JWT_SECRET,
    )
    headers = {"Authorization": f"Bearer {token}"}
    if key:
        headers["Idempotency-Key"] = key
    return headers


def _post(
    api: TestClient,
    engine: Engine,
    user_id: uuid.UUID,
    wo_id: uuid.UUID,
    data: bytes,
    *,
    key: str | None = None,
    filename: str = "IMG_0042.jpg",
) -> httpx.Response:
    res: httpx.Response = api.post(
        f"/v1/workorders/{wo_id}/photos",
        files={"file": (filename, data, "image/jpeg")},
        headers=_headers(engine, user_id, key),
    )
    return res


def _stored(engine: Engine, photo_id: uuid.UUID) -> tuple[Photo, bytes]:
    with Session(engine) as s:
        photo = s.get_one(Photo, photo_id)
    store = S3PhotoStore(make_settings("sqlite://", env="ci"))
    body = store._client.get_object(Bucket=store._bucket, Key=photo.key)["Body"].read()
    return photo, body


def _photo_count(engine: Engine, wo_id: uuid.UUID) -> int:
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(Photo).where(Photo.wo_id == wo_id)) or 0


# --- T-PHOTO-1 -------------------------------------------------------------------------------


def test_T_PHOTO_1_bound_contractor_uploads_and_gps_is_stripped(
    api: TestClient, app_engine: Engine, job: Job
) -> None:
    upload = images.jpeg(size=(40, 20), orientation=6)
    res = _post(api, app_engine, job.world.contractor_user_id, job.world.wo_id, upload)
    assert res.status_code == 201, res.text
    photo_id = PhotoResponse.model_validate(res.json()).photo_id
    assert photo_id.version == 4

    photo, body = _stored(app_engine, photo_id)
    assert photo.key == f"wo/{job.world.wo_id}/{photo_id}"
    assert "IMG_0042" not in photo.key  # the client filename never reaches the key
    assert (photo.content_type, photo.bytes, photo.sha256) == (
        "image/jpeg",
        len(body),
        hashlib.sha256(body).hexdigest(),
    )
    assert photo.sha256 != hashlib.sha256(upload).hexdigest()  # only re-encoded bytes stored
    with Image.open(io.BytesIO(body)) as img:
        assert img.size == (20, 40)  # orientation applied
        assert dict(img.getexif()) == {}
    for marker in (b"Exif", b"GPS", images.SECRET, b"xmpmeta", b"Photoshop 3.0"):
        assert marker not in body


def test_T_PHOTO_1_over_10_mb_is_413(api: TestClient, app_engine: Engine, job: Job) -> None:
    big = images.jpeg() + b"\x00" * (MAX_UPLOAD_BYTES + 1)
    res = _post(api, app_engine, job.world.contractor_user_id, job.world.wo_id, big)
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
    assert _photo_count(app_engine, job.world.wo_id) == 0


@pytest.mark.parametrize(
    "data", [b"%PDF-1.7\n" + b"x" * 200, b"<html><script>x</script></html>", b"GIF89a" + b"0" * 50]
)
def test_T_PHOTO_1_non_image_is_415(
    api: TestClient, app_engine: Engine, job: Job, data: bytes
) -> None:
    res = _post(api, app_engine, job.world.contractor_user_id, job.world.wo_id, data)
    assert res.status_code == 415
    assert res.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert _photo_count(app_engine, job.world.wo_id) == 0


# --- T-PHOTO-3 -------------------------------------------------------------------------------


def test_T_PHOTO_3_bombs_and_oversized_heic_are_415(
    api: TestClient, app_engine: Engine, job: Job
) -> None:
    for data in (images.png_header_only(60_000, 60_000), images.heic(size=(8200, 64))):
        res = _post(api, app_engine, job.world.contractor_user_id, job.world.wo_id, data)
        assert res.status_code == 415
    assert _photo_count(app_engine, job.world.wo_id) == 0


def test_T_PHOTO_3_polyglot_is_stored_reencoded_only(
    api: TestClient, app_engine: Engine, job: Job
) -> None:
    upload = images.jpeg() + b"<html><script>alert(1)</script></html>PK\x03\x04zip"
    res = _post(api, app_engine, job.world.contractor_user_id, job.world.wo_id, upload)
    assert res.status_code == 201, res.text
    _, body = _stored(app_engine, uuid.UUID(res.json()["photo_id"]))
    assert hashlib.sha256(body).hexdigest() != hashlib.sha256(upload).hexdigest()
    assert b"<script>" not in body
    assert b"PK\x03\x04" not in body
    assert body.endswith(b"\xff\xd9")


def test_T_PHOTO_3_png_metadata_is_gone_after_upload(
    api: TestClient, app_engine: Engine, job: Job
) -> None:
    res = _post(
        api,
        app_engine,
        job.world.contractor_user_id,
        job.world.wo_id,
        images.png(),
        filename="x.png",
    )
    assert res.status_code == 201, res.text
    photo, body = _stored(app_engine, uuid.UUID(res.json()["photo_id"]))
    assert photo.content_type == "image/png"
    assert set(images.png_chunk_types(body)) <= {b"IHDR", b"IDAT", b"IEND"}


def test_T_PHOTO_3_anonymous_get_on_stored_object_is_403(
    api: TestClient, app_engine: Engine, job: Job
) -> None:
    res = _post(api, app_engine, job.world.contractor_user_id, job.world.wo_id, images.jpeg())
    photo, _ = _stored(app_engine, uuid.UUID(res.json()["photo_id"]))
    base = os.environ["S3_ENDPOINT_URL"].rstrip("/")
    with pytest.raises(urllib.error.HTTPError) as info:
        urllib.request.urlopen(f"{base}/{os.environ['S3_BUCKET']}/{photo.key}", timeout=5)  # noqa: S310
    assert info.value.code == 403


def test_T_PHOTO_3_two_file_parts_are_422(api: TestClient, app_engine: Engine, job: Job) -> None:
    res = api.post(
        f"/v1/workorders/{job.world.wo_id}/photos",
        files=[
            ("file", ("a.jpg", images.jpeg(), "image/jpeg")),
            ("file", ("b.jpg", images.jpeg(), "image/jpeg")),
        ],
        headers=_headers(app_engine, job.world.contractor_user_id),
    )
    assert res.status_code == 422
    assert _photo_count(app_engine, job.world.wo_id) == 0


def test_T_PHOTO_3_the_21st_photo_is_413(api: TestClient, app_engine: Engine, job: Job) -> None:
    for _ in range(MAX_PHOTOS_PER_WO):
        res = _post(api, app_engine, job.world.contractor_user_id, job.world.wo_id, images.jpeg())
        assert res.status_code == 201, res.text
    res = _post(api, app_engine, job.world.contractor_user_id, job.world.wo_id, images.jpeg())
    assert res.status_code == 413
    assert _photo_count(app_engine, job.world.wo_id) == MAX_PHOTOS_PER_WO


def test_T_PHOTO_3_only_the_bound_contractor_can_upload(
    api: TestClient, app_engine: Engine, job: Job
) -> None:
    w = job.world
    # Ana is a stranger to Marco's job (404), the owner can't act as a contractor (403).
    assert _post(api, app_engine, job.second_user_id, w.wo_id, images.jpeg()).status_code == 404
    assert _post(api, app_engine, w.owner_user_id, w.wo_id, images.jpeg()).status_code == 403
    # An offeree (offered, not accepted) can't upload either (403, plan §2.1 row 13).
    with app_engine.begin() as conn:
        wo3 = conn.execute(
            text(
                "INSERT INTO workorders (tenant_id, asset_id, symptom) VALUES (:t, :a, 'z') "
                "RETURNING id"
            ),
            {"t": w.tenant_id, "a": w.asset_id},
        ).scalar_one()
        _bind(conn, w, wo3, w.contractor_id, "PENDING")
    assert _post(api, app_engine, w.contractor_user_id, wo3, images.jpeg()).status_code == 403
    assert (
        _post(api, app_engine, w.contractor_user_id, uuid.uuid4(), images.jpeg()).status_code == 404
    )
    assert (
        api.post(f"/v1/workorders/{w.wo_id}/photos", files={"file": ("a", b"x")}).status_code == 401
    )
    assert _photo_count(app_engine, w.wo_id) == 0


# --- T-IDEM-1 (photos) -----------------------------------------------------------------------


def test_T_IDEM_1_photos_same_key_same_file_replays_without_a_second_photo(
    api: TestClient, app_engine: Engine, job: Job
) -> None:
    w, upload = job.world, images.jpeg()
    first = _post(api, app_engine, w.contractor_user_id, w.wo_id, upload, key="k-photo-1")
    again = _post(api, app_engine, w.contractor_user_id, w.wo_id, upload, key="k-photo-1")
    assert first.status_code == again.status_code == 201
    assert first.json()["photo_id"] == again.json()["photo_id"]
    assert _photo_count(app_engine, w.wo_id) == 1


def test_T_IDEM_1_photos_same_key_different_file_is_422_and_nothing_returned(
    api: TestClient, app_engine: Engine, job: Job
) -> None:
    w = job.world
    first = _post(api, app_engine, w.contractor_user_id, w.wo_id, images.jpeg(), key="k-photo-2")
    other = _post(api, app_engine, w.contractor_user_id, w.wo_id, images.png(), key="k-photo-2")
    assert first.status_code == 201
    assert other.status_code == 422
    assert other.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"
    assert first.json()["photo_id"] not in other.text
    assert _photo_count(app_engine, w.wo_id) == 1


def test_T_IDEM_1_photos_keys_are_scoped_per_user_and_per_work_order(
    api: TestClient, app_engine: Engine, job: Job
) -> None:
    w, upload = job.world, images.jpeg()
    marco = _post(api, app_engine, w.contractor_user_id, w.wo_id, upload, key="shared-key")
    # Ana reuses Marco's exact key on her own job: an independent upload, never Marco's photo.
    ana = _post(api, app_engine, job.second_user_id, job.second_wo_id, upload, key="shared-key")
    assert marco.status_code == ana.status_code == 201
    assert marco.json()["photo_id"] != ana.json()["photo_id"]
    # Marco reusing his key on a different job of his is independent too.
    with app_engine.begin() as conn:
        wo3 = conn.execute(
            text(
                "INSERT INTO workorders (tenant_id, asset_id, symptom) VALUES (:t, :a, 'z') "
                "RETURNING id"
            ),
            {"t": w.tenant_id, "a": w.asset_id},
        ).scalar_one()
        _bind(conn, w, wo3, w.contractor_id, "ACCEPTED")
    other_job = _post(api, app_engine, w.contractor_user_id, wo3, upload, key="shared-key")
    assert other_job.status_code == 201
    assert other_job.json()["photo_id"] != marco.json()["photo_id"]
    assert (_photo_count(app_engine, w.wo_id), _photo_count(app_engine, job.second_wo_id)) == (1, 1)
