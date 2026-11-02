"""Request body limit (D10 M-8): JSON bodies ≤ 64 KB; multipart gets the photo limit."""

from collections.abc import Iterator

from fastapi.testclient import TestClient

from app.core.middleware import JSON_BODY_LIMIT
from app.main import create_app
from tests.conftest import authed_app, make_settings

WO = "6f1c1d2e-0000-4000-8000-000000000001"


def _client() -> TestClient:
    return TestClient(create_app(make_settings()))


def test_json_over_64kb_rejected_with_413_envelope() -> None:
    big = b'{"email":"' + b"a" * JSON_BODY_LIMIT + b'","password":"x"}'
    res = _client().post(
        "/v1/auth/login", content=big, headers={"content-type": "application/json"}
    )
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_chunked_json_over_limit_rejected_while_streaming() -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"email":"'
        for _ in range(20):
            yield b"a" * 4096
        yield b'","password":"x"}'

    res = _client().post(
        "/v1/auth/login", content=chunks(), headers={"content-type": "application/json"}
    )
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_garbage_content_length_rejected() -> None:
    res = _client().post(
        "/v1/auth/login",
        content=b"{}",
        headers={"content-type": "application/json", "content-length": "-1"},
    )
    assert res.status_code == 413


def test_small_json_and_large_multipart_pass_the_limit() -> None:
    c = TestClient(authed_app())
    ok = c.post(
        "/v1/workorders/" + WO + "/complete",
        json={
            "failure_code": "X",
            "actual_fault_matched": True,
            "labor_hours": 1,
            "technician_id": "M",
        },
    )
    assert ok.status_code == 501  # reaches the stub
    photo = c.post(
        f"/v1/workorders/{WO}/photos",
        files={"file": ("p.jpg", b"\xff\xd8" + b"0" * (2 * JSON_BODY_LIMIT), "image/jpeg")},
    )
    assert photo.status_code == 501
