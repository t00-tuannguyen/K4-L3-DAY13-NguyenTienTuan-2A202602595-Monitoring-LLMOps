from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx

from app import logging_config
from app.logging_config import scrub_event
from app.main import app

REQUEST_ID = re.compile(r"^req-[0-9a-f]{8}$")


def _post(headers: dict[str, str] | None = None, message: str = "Explain monitoring") -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/chat",
                headers=headers or {},
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": message,
                },
            )

    return asyncio.run(send())


def test_generates_correlation_id_and_response_headers(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")
    response = _post()
    assert REQUEST_ID.match(response.headers["x-request-id"])
    assert response.json()["correlation_id"] == response.headers["x-request-id"]
    assert int(response.headers["x-response-time-ms"]) >= 0


def test_reuses_valid_incoming_request_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")
    response = _post({"x-request-id": "req-deadbeef"})
    assert response.headers["x-request-id"] == "req-deadbeef"


def test_replaces_invalid_incoming_request_id(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(logging_config, "LOG_PATH", tmp_path / "logs.jsonl")
    response = _post({"x-request-id": "not-valid"})
    assert REQUEST_ID.match(response.headers["x-request-id"])


def test_logs_are_enriched_scrubbed_and_not_leaked(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)
    first = _post(message="My email is student@vinuni.edu.vn")
    second = _post()

    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    api_events = [e for e in events if e.get("service") == "api"]
    for event in api_events:
        assert {"correlation_id", "user_id_hash", "session_id", "feature", "model", "env"} <= event.keys()
        assert "student@vinuni.edu.vn" not in json.dumps(event)

    ids = {e["correlation_id"] for e in api_events}
    assert ids == {first.headers["x-request-id"], second.headers["x-request-id"]}


def test_scrub_event_covers_all_string_fields() -> None:
    out = scrub_event(None, "info", {"event": "x", "detail": "call 0901234567", "payload": {"n": ["a@b.vn"]}})
    assert "0901234567" not in json.dumps(out)
    assert "a@b.vn" not in json.dumps(out)
