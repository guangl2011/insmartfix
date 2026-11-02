"""The checked-in route → action map (D10 M-3). T-AUTH-14 fails if a route under a gated prefix is
missing here, or if its gate's action differs. Adding a gated route means adding it here."""

from app.identity_gate.policy import Action

GATED_PREFIXES = ("/v1/contractor", "/v1/me/", "/v1/workorders", "/v1/dispatch")

ROUTE_ACTIONS: dict[tuple[str, str], Action] = {
    ("GET", "/v1/contractor/{cid}/schedule"): Action.SCHEDULE,
    ("GET", "/v1/me/schedule"): Action.SCHEDULE,
    ("POST", "/v1/contractor/{cid}/accept/{wo}"): Action.ACCEPT,
    ("POST", "/v1/me/accept/{wo}"): Action.ACCEPT,
    ("POST", "/v1/contractor/{cid}/decline/{wo}"): Action.DECLINE,
    ("POST", "/v1/me/decline/{wo}"): Action.DECLINE,
    ("GET", "/v1/workorders/{wo}"): Action.GET_WO,
    ("POST", "/v1/workorders/{wo}/transition"): Action.TRANSITION,
    ("POST", "/v1/workorders/{wo}/photos"): Action.PHOTO,
    ("POST", "/v1/workorders/{wo}/complete"): Action.COMPLETE,
    ("POST", "/v1/dispatch/workorders"): Action.DISPATCH_CREATE,
}

# Routes that need no token at all. Everything else must depend on `get_principal`.
PUBLIC_ROUTES = frozenset(
    {("POST", "/v1/auth/login"), ("GET", "/v1/healthz"), ("GET", "/v1/readyz")}
)
