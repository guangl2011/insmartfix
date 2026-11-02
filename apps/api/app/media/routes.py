"""`POST /v1/workorders/{wo}/photos` (FR-7.7; D10 M-9, H-3). Bound contractor only (gate: photo).

Order of work:
1. Stream the single `file` part, enforcing 10 MB while reading (413), one part only (422).
2. Lock the work order row, so the per-WO cap and the idempotency lookup are race-free.
3. Scoped idempotency: (user, `POST /v1/workorders/{wo}/photos#<wo>`, key) hashed over the
   **upload** bytes. Same file → the original `photo_id`, no second photo; another file → 422.
4. Cap: the 21st photo on a work order → 413.
5. Validate and re-encode from pixels (415 on anything we can't safely decode).
6. Store only the re-encoded bytes at `wo/{wo}/{photo_id}`; record the row; commit.
"""

import uuid
from typing import Annotated

from fastapi import Depends, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clock import now
from app.contract.common import ErrorCode, IdempotencyKeyHeader, error_responses
from app.contract.workorders import PhotoResponse
from app.core.errors import ApiError
from app.core.idempotency import IdempotencyRequest, bytes_hash, idempotency_request
from app.db.models import IdempotencyRecord, Photo, WorkOrder
from app.db.session import get_db
from app.identity_gate.deps import Authorized, AuthorizedTarget, gated_router
from app.identity_gate.policy import Action
from app.media.store import PhotoStore, S3PhotoStore, photo_key
from app.media.upload import MalformedUploadError, UploadTooLargeError, read_single_file
from app.media.validate import MAX_UPLOAD_BYTES, UnsupportedImageError, clean
from app.routes import API_PREFIX
from app.settings import Settings, get_settings

MAX_PHOTOS_PER_WO = 20
ROUTE = "/v1/workorders/{wo}/photos"

router = gated_router(prefix=API_PREFIX, tags=["workorders"])


_stores: dict[tuple[str | None, str, str, str | None], S3PhotoStore] = {}


def get_photo_store(settings: Annotated[Settings, Depends(get_settings)]) -> PhotoStore:
    """One boto3 client per storage configuration, built from this app's settings."""
    key_id = settings.s3_access_key_id.get_secret_value() if settings.s3_access_key_id else None
    cache_key = (settings.s3_endpoint_url, settings.s3_bucket, settings.s3_region, key_id)
    store = _stores.get(cache_key)
    if store is None:
        store = _stores[cache_key] = S3PhotoStore(settings)
    return store


@router.post(
    "/workorders/{wo}/photos",
    action=Action.PHOTO,
    operation_id="upload_workorder_photo",
    status_code=201,
    response_model=PhotoResponse,
    responses=error_responses(401, 403, 404, 413, 415, 422),
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "properties": {
                            "file": {
                                "type": "string",
                                "format": "binary",
                                "description": "One JPEG, PNG or HEIC image, at most 10 MB.",
                            }
                        },
                    }
                }
            },
        }
    },
)
async def upload_workorder_photo(
    target: Authorized,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    store: Annotated[PhotoStore, Depends(get_photo_store)],
    idempotency_key: IdempotencyKeyHeader = None,
) -> PhotoResponse:
    """Upload one completion photo (FR-7.7). The body is streamed and parsed by the handler."""
    try:
        upload = await read_single_file(
            request.headers.get("content-type"),
            request.headers.get("content-length"),
            request.stream(),
            max_bytes=MAX_UPLOAD_BYTES,
        )
    except UploadTooLargeError as exc:
        raise ApiError(413, ErrorCode.PAYLOAD_TOO_LARGE) from exc
    except MalformedUploadError as exc:
        raise ApiError(422, ErrorCode.VALIDATION_ERROR) from exc
    photo_id = await run_in_threadpool(_save, db, store, target, upload, idempotency_key)
    return PhotoResponse(photo_id=photo_id, server_time=now())


def _save(
    db: Session,
    store: PhotoStore,
    target: AuthorizedTarget,
    upload: bytes,
    key: str | None,
) -> uuid.UUID:
    if target.wo is None:  # the photo gate always resolves a work order; never trust otherwise
        raise ApiError(404, ErrorCode.NOT_FOUND)
    wo_id, principal = target.wo.wo_id, target.principal
    wo = db.scalars(select(WorkOrder).where(WorkOrder.id == wo_id).with_for_update()).one()

    idem = idempotency_request(
        key=key,
        user_id=principal.user_id,
        method="POST",
        route_template=ROUTE,
        target_id=wo_id,
        request_hash=bytes_hash(upload),
    )
    if idem is not None:
        replay = _replay(db, idem)
        if replay is not None:
            db.rollback()
            return replay

    count = db.scalar(select(func.count()).select_from(Photo).where(Photo.wo_id == wo_id)) or 0
    if count >= MAX_PHOTOS_PER_WO:
        raise ApiError(413, ErrorCode.PAYLOAD_TOO_LARGE)

    try:
        image = clean(upload)
    except UnsupportedImageError as exc:
        raise ApiError(415, ErrorCode.UNSUPPORTED_MEDIA_TYPE) from exc

    photo_id = uuid.uuid4()
    object_key = photo_key(wo_id, photo_id)
    store.put(object_key, image.content, image.content_type)
    db.add(
        Photo(
            id=photo_id,
            tenant_id=wo.tenant_id,
            wo_id=wo_id,
            key=object_key,
            content_type=image.content_type,
            bytes=len(image.content),
            sha256=image.sha256,
            uploaded_by_user_id=principal.user_id,
            created_at=now(),
        )
    )
    if idem is not None:
        db.add(
            IdempotencyRecord(
                user_id=idem.user_id,
                scope=idem.scope,
                key=idem.key,
                request_hash=idem.request_hash,
                response_status=201,
                response_ref={"photo_id": str(photo_id)},
            )
        )
    db.commit()
    return photo_id


def _replay(db: Session, idem: IdempotencyRequest) -> uuid.UUID | None:
    """The original photo for this (user, scope, key), None if new; 422 if the file differs."""
    record = db.get(IdempotencyRecord, (idem.user_id, idem.scope, idem.key))
    if record is None or not idem.check(record.request_hash) or record.response_ref is None:
        return None
    return uuid.UUID(str(record.response_ref["photo_id"]))
