"""HTTP routes. Every router carries the `/v1` prefix itself, so route objects know their full
template (access logs, idempotency scope, T-AUTH-14 route-table walk)."""

API_PREFIX = "/v1"
