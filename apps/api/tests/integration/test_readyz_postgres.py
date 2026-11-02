"""Integration: /v1/readyz against a real Postgres 16 (CI service / compose stack)."""

import pytest

from tests.conftest import ClientFactory

pytestmark = pytest.mark.integration


def test_readyz_ready_against_postgres(client_for: ClientFactory, postgres_url: str) -> None:
    res = client_for(postgres_url).get("/v1/readyz")
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "ready"
