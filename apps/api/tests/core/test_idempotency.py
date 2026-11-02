"""Scoped idempotency primitives (D10 H-3, C-2; D12). Supports T-IDEM-1."""

from uuid import uuid4

import pytest

from app.contract.common import ErrorCode
from app.contract.schedule import DeclineRequest
from app.core.errors import ApiError
from app.core.idempotency import bytes_hash, canonical_hash, idempotency_request, scope_for

MARCO, ANA = uuid4(), uuid4()
WO_X, WO_Y = uuid4(), uuid4()
ROUTE = "/v1/workorders/{wo}/transition"


def test_canonical_hash_ignores_key_order_and_formatting() -> None:
    assert canonical_hash({"a": 1, "b": [1, 2]}) == canonical_hash({"b": [1, 2], "a": 1})
    assert canonical_hash({"a": 1}) != canonical_hash({"a": 2})
    model = DeclineRequest.model_validate({"reason": "too_far"})
    assert canonical_hash(model) == canonical_hash({"reason": "too_far", "note": None})
    assert len(bytes_hash(b"photo")) == 64


def test_scope_includes_method_route_template_and_target() -> None:
    assert scope_for("post", ROUTE, WO_X) == f"POST {ROUTE}#{WO_X}"
    assert scope_for("POST", ROUTE, WO_X) != scope_for("POST", ROUTE, WO_Y)
    assert scope_for("POST", ROUTE, WO_X) != scope_for("POST", "/v1/workorders/{wo}/complete", WO_X)


def _req(user: object = MARCO, wo: object = WO_X, body: object = None) -> object:
    return idempotency_request(
        key="key-00000001",
        user_id=user,  # type: ignore[arg-type]
        method="POST",
        route_template=ROUTE,
        target_id=wo,  # type: ignore[arg-type]
        request_hash=canonical_hash(body or {"action": "advance"}),  # type: ignore[arg-type]
    )


def test_no_key_means_no_idempotency() -> None:
    assert (
        idempotency_request(
            key=None,
            user_id=MARCO,
            method="POST",
            route_template=ROUTE,
            target_id=WO_X,
            request_hash="h",
        )
        is None
    )


def test_fresh_replay_and_reused_key_with_different_body() -> None:
    req = idempotency_request(
        key="key-00000001",
        user_id=MARCO,
        method="POST",
        route_template=ROUTE,
        target_id=WO_X,
        request_hash=canonical_hash({"action": "advance"}),
    )
    assert req is not None
    assert req.check(None) is False
    assert req.check(req.request_hash) is True
    with pytest.raises(ApiError) as exc:
        req.check(canonical_hash({"action": "undo"}))
    assert (exc.value.status_code, exc.value.code) == (422, ErrorCode.IDEMPOTENCY_KEY_REUSED)


def test_record_identity_differs_per_user_and_target() -> None:
    marco, ana, marco_y = _req(), _req(user=ANA), _req(wo=WO_Y)
    ident = {(r.user_id, r.scope, r.key) for r in (marco, ana, marco_y)}  # type: ignore[attr-defined]
    assert len(ident) == 3
