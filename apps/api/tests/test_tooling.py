import json
from pathlib import Path

import pytest

from app import export_openapi, seed


def test_export_openapi_writes_deterministic_document(tmp_path: Path) -> None:
    out = tmp_path / "openapi.json"
    assert export_openapi.main([str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert text == export_openapi.render()
    doc = json.loads(text)
    assert {"/v1/healthz", "/v1/readyz"} <= set(doc["paths"])
    assert "ErrorEnvelope" in doc["components"]["schemas"]


def test_export_openapi_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert export_openapi.main([]) == 2
    assert "usage" in capsys.readouterr().err


def test_seed_stub_runs(capsys: pytest.CaptureFixture[str]) -> None:
    assert seed.main() == 0
    assert "M1" in capsys.readouterr().err
