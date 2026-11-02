"""Gate wiring: `gated_router()` and the per-route `GateDependency` (D10 M-3, plan rule 2).

Every route under `/v1/contractor`, `/v1/me/*`, `/v1/workorders` and `/v1/dispatch` is declared on a
`GatedRouter`, whose `add_api_route` **requires** `action=` and injects exactly one
`GateDependency`. The dependency owns the `cid` / `wo` path parameters, loads the facts, calls
`policy.decide()` and either raises the decision's error or stores an `AuthorizedTarget` on the
request. Handlers take `target: Authorized` and never declare `cid` or `wo` themselves, so they
cannot re-load a resource by a raw client id (T-AUTH-14 checks all of this structurally).
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Any, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.auth.deps import get_principal
from app.auth.service import Principal
from app.clock import now
from app.contract.common import ErrorCode
from app.core.errors import ApiError
from app.db.models import Contractor, Dispatch, DispatchCandidate, WorkOrder
from app.db.session import get_db
from app.identity_gate.policy import (
    Action,
    Allow,
    AllowedAs,
    ContractorFacts,
    Decision,
    Deny403,
    Deny404,
    Unavailable409,
    WorkOrderFacts,
    decide,
    decide_path_cid,
)

F = TypeVar("F", bound=Callable[..., Any])

ME_PREFIX = "/v1/me/"
_STATE_KEY = "authorized_target"


@dataclass(frozen=True)
class AuthorizedTarget:
    """What a gated handler may act on: the principal, how it was allowed, and the resolved ids."""

    principal: Principal
    action: Action
    allowed_as: AllowedAs
    contractor_id: UUID | None  # resolved schedule/offer owner (token for contractors)
    wo: WorkOrderFacts | None


def raise_for(decision: Decision) -> None:
    """Fixed bodies per status: no variation between "why" (D10 M-1/M-2, T-AUTH-15)."""
    if isinstance(decision, Deny403):
        raise ApiError(403, ErrorCode.FORBIDDEN)
    if isinstance(decision, Deny404):
        raise ApiError(404, ErrorCode.NOT_FOUND)
    if isinstance(decision, Unavailable409):
        raise ApiError(409, ErrorCode.OFFER_UNAVAILABLE, reason=decision.reason)


def load_workorder(db: Session, wo_id: UUID, contractor_id: UUID | None) -> WorkOrderFacts | None:
    cand_join = and_(
        DispatchCandidate.wo_id == WorkOrder.id,
        DispatchCandidate.contractor_id == contractor_id,
    )
    row = db.execute(
        select(
            WorkOrder.id,
            WorkOrder.tenant_id,
            Dispatch.state,
            Dispatch.current_contractor_id,
            Dispatch.sla_deadline,
            DispatchCandidate.state,
        )
        .outerjoin(Dispatch, Dispatch.wo_id == WorkOrder.id)
        .outerjoin(DispatchCandidate, cand_join)
        .where(WorkOrder.id == wo_id)
    ).first()
    if row is None:
        return None
    return WorkOrderFacts(
        wo_id=row[0],
        tenant_id=row[1],
        dispatch_state=row[2],
        current_contractor_id=row[3],
        sla_deadline=row[4],
        candidate_state=row[5],
    )


def load_contractor(db: Session, contractor_id: UUID) -> ContractorFacts | None:
    row = db.execute(
        select(Contractor.id, Contractor.tenant_id).where(Contractor.id == contractor_id)
    ).first()
    return None if row is None else ContractorFacts(row[0], row[1])


class GateDependency:
    """One instance per gated route. Its signature exposes exactly the path's `cid` / `wo`."""

    def __init__(self, action: Action, path: str) -> None:
        self.action = action
        self.has_cid = "{cid}" in path
        self.has_wo = "{wo}" in path
        self.via_me = path.startswith(ME_PREFIX)
        params = [
            inspect.Parameter("request", inspect.Parameter.KEYWORD_ONLY, annotation=Request),
            inspect.Parameter(
                "principal",
                inspect.Parameter.KEYWORD_ONLY,
                annotation=Annotated[Principal, Depends(get_principal)],
            ),
            inspect.Parameter(
                "db", inspect.Parameter.KEYWORD_ONLY, annotation=Annotated[Session, Depends(get_db)]
            ),
        ]
        for name, present in (("cid", self.has_cid), ("wo", self.has_wo)):
            if present:
                params.append(
                    inspect.Parameter(
                        name, inspect.Parameter.KEYWORD_ONLY, annotation=Annotated[UUID, Path()]
                    )
                )
        self.__signature__ = inspect.Signature(params)

    def __call__(
        self,
        *,
        request: Request,
        principal: Principal,
        db: Session,
        cid: UUID | None = None,
        wo: UUID | None = None,
    ) -> AuthorizedTarget:
        at = now()
        target = self.authorize(principal, db, cid, wo, at)
        setattr(request.state, _STATE_KEY, target)
        return target

    def authorize(
        self,
        principal: Principal,
        db: Session,
        cid: UUID | None,
        wo: UUID | None,
        at: datetime,
    ) -> AuthorizedTarget:
        # Rows 2-3 are answered before any lookup, so neither the body nor the timing depends on
        # whether `cid` / `wo` exist (D10 M-1).
        early = decide_path_cid(principal, cid, self.via_me, self.action)
        if early is not None:
            raise_for(early)
        contractor = None
        if cid is not None and principal.contractor_id is None:
            contractor = load_contractor(db, cid)
        facts = load_workorder(db, wo, principal.contractor_id) if wo is not None else None
        decision = decide(
            principal,
            self.action,
            now=at,
            path_cid=cid,
            via_me=self.via_me,
            contractor=contractor,
            wo=facts,
            needs_wo=self.has_wo,
        )
        raise_for(decision)
        assert isinstance(decision, Allow)  # noqa: S101 — raise_for handled every other case
        resolved_cid = principal.contractor_id if principal.contractor_id is not None else cid
        return AuthorizedTarget(principal, self.action, decision.as_, resolved_cid, facts)


def authorized_target(request: Request) -> AuthorizedTarget:
    """Handler-side accessor. Fails closed if the gate didn't run for this route."""
    target = getattr(request.state, _STATE_KEY, None)
    if not isinstance(target, AuthorizedTarget):
        raise RuntimeError("gated handler reached without the identity gate")  # pragma: no cover
    return target


Authorized = Annotated[AuthorizedTarget, Depends(authorized_target)]


class GatedRouter(APIRouter):
    """`add_api_route` requires `action=`; every route gets exactly one `GateDependency`."""

    def add_api_route(
        self,
        path: str,
        endpoint: Callable[..., Any],
        *,
        action: Action | None = None,
        **kwargs: Any,
    ) -> None:
        if not isinstance(action, Action):
            raise TypeError(f"gated route {path} must declare action=")
        params = inspect.signature(endpoint).parameters
        if "cid" in params or "wo" in params:
            raise TypeError(f"gated handler for {path} must not declare cid/wo (use Authorized)")
        gate = GateDependency(action, self.prefix + path)
        kwargs["dependencies"] = [Depends(gate), *(kwargs.get("dependencies") or [])]
        super().add_api_route(path, endpoint, **kwargs)

    def api_route(
        self, path: str, *, action: Action | None = None, **kwargs: Any
    ) -> Callable[[F], F]:
        def decorator(func: F) -> F:
            self.add_api_route(path, func, action=action, **kwargs)
            return func

        return decorator

    def get(self, path: str, *, action: Action | None = None, **kwargs: Any) -> Callable[[F], F]:
        return self.api_route(path, action=action, methods=["GET"], **kwargs)

    def post(self, path: str, *, action: Action | None = None, **kwargs: Any) -> Callable[[F], F]:
        return self.api_route(path, action=action, methods=["POST"], **kwargs)


def gated_router(**kwargs: Any) -> GatedRouter:
    return GatedRouter(**kwargs)
