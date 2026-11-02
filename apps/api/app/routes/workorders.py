"""Work-order routes (spec §5; FR-3, FR-6, FR-7). Stubs until M2-T2/T3/T5/T6."""

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.auth.deps import get_principal
from app.contract.common import IdempotencyKeyHeader, error_responses
from app.contract.workorders import (
    CompletionReport,
    CompletionResponse,
    OwnerWorkOrderDetail,
    PhotoResponse,
    TransitionRequest,
    TransitionResponse,
    WorkOrderDetail,
)
from app.routes import API_PREFIX
from app.routes._stub import not_implemented

router = APIRouter(prefix=API_PREFIX, tags=["workorders"], dependencies=[Depends(get_principal)])


@router.get(
    "/workorders/{wo}",
    operation_id="get_workorder",
    response_model=WorkOrderDetail | OwnerWorkOrderDetail,
    responses=error_responses(401, 403, 404, 422, 501),
)
def get_workorder(wo: UUID) -> JSONResponse:
    """Detail + packet. Contractor view omits `ranked_candidates`; owner/FM view has it (FR-3.5)."""
    return not_implemented()


@router.post(
    "/workorders/{wo}/transition",
    operation_id="transition_workorder",
    response_model=TransitionResponse,
    responses=error_responses(401, 403, 404, 409, 422, 501),
)
def transition_workorder(
    wo: UUID, body: TransitionRequest, idempotency_key: IdempotencyKeyHeader = None
) -> JSONResponse:
    """Advance EN_ROUTE → ARRIVED, or undo via a CORRECTION event (FR-6.1, FR-6.3, FR-6.4)."""
    return not_implemented()


@router.post(
    "/workorders/{wo}/photos",
    operation_id="upload_workorder_photo",
    status_code=201,
    response_model=PhotoResponse,
    responses=error_responses(401, 403, 404, 413, 415, 422, 501),
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
def upload_workorder_photo(wo: UUID, idempotency_key: IdempotencyKeyHeader = None) -> JSONResponse:
    """Upload one completion photo (FR-7.7). The body is streamed and parsed by the handler."""
    return not_implemented()


@router.post(
    "/workorders/{wo}/complete",
    operation_id="complete_workorder",
    response_model=CompletionResponse,
    responses=error_responses(401, 403, 404, 409, 422, 501),
)
def complete_workorder(
    wo: UUID, body: CompletionReport, idempotency_key: IdempotencyKeyHeader = None
) -> JSONResponse:
    """Submit the completion report; labels calibration (FR-7.4, FR-7.5)."""
    return not_implemented()
