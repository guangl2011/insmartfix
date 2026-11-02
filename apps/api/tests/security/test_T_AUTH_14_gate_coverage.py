"""T-AUTH-14 (A): structural gate coverage over the full route table (D10 M-3, plan rule 2).

Walks every effective route. Under `/v1/contractor`, `/v1/me/*` (except exactly `GET /v1/me`),
`/v1/workorders` and `/v1/dispatch`, each route must have exactly one `GateDependency` whose action
matches the checked-in `ROUTE_ACTIONS`; a route missing from the map fails. No gated handler may
declare `cid` / `wo`. Every route not in `PUBLIC_ROUTES` depends on `get_principal`.
M2-T7 re-runs this over the implemented routes.
"""

import inspect
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant

from app.auth.deps import get_principal
from app.core.routes import iter_http_routes
from app.identity_gate.deps import GateDependency, GatedRouter
from app.identity_gate.policy import Action
from app.identity_gate.routes import GATED_PREFIXES, PUBLIC_ROUTES, ROUTE_ACTIONS
from app.main import create_app

DOC_ROUTES = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _calls(dep: Dependant) -> Iterator[Any]:
    for sub in dep.dependencies:
        yield sub.call
        yield from _calls(sub)


def _api_routes(app: FastAPI) -> list[tuple[str, str, Any]]:
    out = []
    for rc in iter_http_routes(app):
        path = rc.path or ""
        if path in DOC_ROUTES:
            continue
        for method in sorted((rc.methods or set()) - {"HEAD"}):
            out.append((method, path, rc))
    return out


def _is_gated(method: str, path: str) -> bool:
    if (method, path) == ("GET", "/v1/me"):
        return False
    return path.startswith(GATED_PREFIXES)


@pytest.fixture(scope="module")
def routes() -> list[tuple[str, str, Any]]:
    return _api_routes(create_app(schema_only=True))


def test_T_AUTH_14_every_gated_route_has_exactly_one_matching_gate(
    routes: list[tuple[str, str, Any]],
) -> None:
    gated = [(m, p, rc) for m, p, rc in routes if _is_gated(m, p)]
    assert gated, "no gated routes found"
    seen = set()
    for method, path, rc in gated:
        assert (method, path) in ROUTE_ACTIONS, f"{method} {path} missing from ROUTE_ACTIONS"
        gates = [c for c in _calls(rc.dependant) if isinstance(c, GateDependency)]
        assert len(gates) == 1, f"{method} {path}: {len(gates)} gate dependencies"
        assert gates[0].action is ROUTE_ACTIONS[(method, path)], f"{method} {path}"
        params = inspect.signature(rc.endpoint).parameters
        assert "cid" not in params, f"{method} {path} declares cid"
        assert "wo" not in params, f"{method} {path} declares wo"
        seen.add((method, path))
    assert seen == set(ROUTE_ACTIONS), "ROUTE_ACTIONS lists a route that doesn't exist"


def test_T_AUTH_14_every_non_public_route_depends_on_get_principal(
    routes: list[tuple[str, str, Any]],
) -> None:
    for method, path, rc in routes:
        has_principal = get_principal in set(_calls(rc.dependant))
        if (method, path) in PUBLIC_ROUTES:
            assert not has_principal, f"{method} {path} is public but authenticates"
        else:
            assert has_principal, f"{method} {path} does not depend on get_principal"


def test_T_AUTH_14_no_ungated_route_hides_under_a_gated_prefix(
    routes: list[tuple[str, str, Any]],
) -> None:
    ungated = [
        (m, p)
        for m, p, rc in routes
        if not any(isinstance(c, GateDependency) for c in _calls(rc.dependant))
    ]
    assert all(not _is_gated(m, p) for m, p in ungated), ungated


def test_T_AUTH_14_gated_router_refuses_missing_action_or_raw_ids() -> None:
    router = GatedRouter(prefix="/v1")

    def ok() -> None: ...

    def raw_wo(wo: str) -> None: ...

    def raw_cid(cid: str) -> None: ...

    with pytest.raises(TypeError, match="action"):
        router.add_api_route("/workorders/{wo}", ok)
    with pytest.raises(TypeError, match="cid/wo"):
        router.add_api_route("/workorders/{wo}", raw_wo, action=Action.GET_WO)
    with pytest.raises(TypeError, match="cid/wo"):
        router.add_api_route("/contractor/{cid}/schedule", raw_cid, action=Action.SCHEDULE)
    router.add_api_route("/workorders/{wo}", ok, action=Action.GET_WO, methods=["GET"])
