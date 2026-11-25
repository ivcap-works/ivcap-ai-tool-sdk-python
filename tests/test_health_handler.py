#
# Copyright (c) 2026 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
"""Tests for the `/_healtz` endpoint and readiness helpers in ivcap_lambda.health_handler.

These tests cover:
 - service-level gates (`add_ready_handler`) controlling `/_healtz`
 - `@ivcap_health_info` results merged into the reply, with identity keys winning
 - `NotReadyYet` and `Retry-After` handling
 - per-tool checks (`check_tool_ready`)
"""

import asyncio

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from ivcap_lambda import health_handler as health_module
from ivcap_lambda.health_handler import (
    NotReadyYet,
    add_health_route,
    add_ready_handler,
    check_tool_ready,
    ivcap_health_info,
)


@pytest.fixture(autouse=True)
def _clean_registries():
    """Module-level registries; isolate tests."""
    saved_gates = list(health_module._ready_handlers)
    saved_info = list(health_module._health_info)
    health_module._ready_handlers.clear()
    health_module._health_info.clear()
    yield
    health_module._ready_handlers.clear()
    health_module._health_info.clear()
    health_module._ready_handlers.extend(saved_gates)
    health_module._health_info.extend(saved_info)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("VERSION", "1.2.3")
    app = FastAPI()
    add_health_route(app)
    return TestClient(app)


def _libs():
    return health_module._library_versions()


# --- service-level gates ----------------------------------------------------


def test_healtz_ok_without_gates(client):
    resp = client.get("/_healtz")
    assert resp.status_code == 200
    assert resp.json() == {"version": "1.2.3", "libraries": _libs()}


def test_healtz_ok_when_all_gates_ready(client):
    add_ready_handler(lambda: True)
    add_ready_handler(lambda: True)
    assert client.get("/_healtz").status_code == 200


def test_healtz_503_when_sync_gate_not_ready(client):
    add_ready_handler(lambda: False)
    assert client.get("/_healtz").status_code == 503


def test_healtz_503_when_async_gate_not_ready(client):
    async def not_ready() -> bool:
        return False

    add_ready_handler(not_ready)
    assert client.get("/_healtz").status_code == 503


def test_healtz_503_if_any_gate_not_ready(client):
    add_ready_handler(lambda: True)
    add_ready_handler(lambda: False)
    assert client.get("/_healtz").status_code == 503


def test_add_none_gate_is_ignored(client):
    add_ready_handler(None)
    assert health_module._ready_handlers == []
    assert client.get("/_healtz").status_code == 200


def test_not_ready_yet_gate_returns_503_without_retry_header(client):
    def not_yet() -> bool:
        raise NotReadyYet()

    add_ready_handler(not_yet)
    resp = client.get("/_healtz")
    assert resp.status_code == 503
    assert "Retry-After" not in resp.headers


def test_not_ready_yet_sets_retry_after_rounded_up(client):
    def loading() -> bool:
        raise NotReadyYet(retry_after=2.2)

    add_ready_handler(loading)
    resp = client.get("/_healtz")
    assert resp.status_code == 503
    assert resp.headers["Retry-After"] == "3"


def test_async_not_ready_yet_sets_retry_after(client):
    async def loading() -> bool:
        raise NotReadyYet(retry_after=10)

    add_ready_handler(loading)
    assert client.get("/_healtz").headers["Retry-After"] == "10"


def test_largest_retry_after_wins_across_gates(client):
    def short() -> bool:
        raise NotReadyYet(retry_after=5)

    def long() -> bool:
        raise NotReadyYet(retry_after=30)

    add_ready_handler(short)
    add_ready_handler(long)
    assert client.get("/_healtz").headers["Retry-After"] == "30"


# --- @ivcap_health_info ------------------------------------------------------


def test_health_info_dict_is_merged_into_reply(client):
    @ivcap_health_info
    def info() -> dict:
        return {"model": "m1"}

    assert client.get("/_healtz").json() == {
        "model": "m1",
        "version": "1.2.3",
        "libraries": _libs(),
    }


def test_health_info_empty_dict_is_fine(client):
    @ivcap_health_info
    def info() -> dict:
        return {}

    assert client.get("/_healtz").json() == {
        "version": "1.2.3",
        "libraries": _libs(),
    }


def test_health_info_merges_across_functions(client):
    @ivcap_health_info
    def a() -> dict:
        return {"model": "m1"}

    @ivcap_health_info
    def b() -> dict:
        return {"dataset": "d1"}

    body = client.get("/_healtz").json()
    assert body["model"] == "m1"
    assert body["dataset"] == "d1"


def test_health_info_later_function_wins_on_key_clash(client):
    @ivcap_health_info
    def a() -> dict:
        return {"model": "first"}

    @ivcap_health_info
    def b() -> dict:
        return {"model": "second"}

    assert client.get("/_healtz").json()["model"] == "second"


def test_identity_keys_win_over_info_keys(client):
    @ivcap_health_info
    def info() -> dict:
        return {"version": "spoofed", "libraries": "spoofed", "model": "m1"}

    body = client.get("/_healtz").json()
    assert body["version"] == "1.2.3"
    assert body["libraries"] == _libs()
    assert body["model"] == "m1"


def test_async_health_info_is_merged(client):
    @ivcap_health_info
    async def info() -> dict:
        return {"model": "async-model"}

    assert client.get("/_healtz").json()["model"] == "async-model"


class _ModelInfo(BaseModel):
    model: str
    weights_version: str = Field(..., alias="weightsVersion")


def test_pydantic_model_info_is_merged_with_alias(client):
    @ivcap_health_info
    def info() -> _ModelInfo:
        return _ModelInfo(model="resnet-50", weightsVersion="v2")

    assert client.get("/_healtz").json() == {
        "model": "resnet-50",
        "weightsVersion": "v2",
        "version": "1.2.3",
        "libraries": _libs(),
    }


def test_failing_info_function_is_left_out_but_reply_is_200(client):
    @ivcap_health_info
    def broken() -> dict:
        raise RuntimeError("probe failed")

    @ivcap_health_info
    def ok() -> dict:
        return {"model": "m1"}

    resp = client.get("/_healtz")
    assert resp.status_code == 200
    assert resp.json()["model"] == "m1"


def test_non_dict_info_is_ignored(client):
    @ivcap_health_info
    def info():
        return "not a dict"

    assert client.get("/_healtz").status_code == 200


def test_info_not_reported_while_gate_not_ready(client):
    calls = []

    @ivcap_health_info
    def info() -> dict:
        calls.append(1)
        return {"model": "m1"}

    add_ready_handler(lambda: False)
    assert client.get("/_healtz").status_code == 503
    assert calls == []


# --- per-tool checks ---------------------------------------------------------


def test_check_tool_ready_none_passes():
    asyncio.run(check_tool_ready(None))


def test_check_tool_ready_true_passes():
    asyncio.run(check_tool_ready(lambda: True))


def test_check_tool_ready_false_raises_not_ready():
    with pytest.raises(NotReadyYet):
        asyncio.run(check_tool_ready(lambda: False))


def test_check_tool_ready_not_ready_yet_propagates():
    def loading() -> bool:
        raise NotReadyYet(retry_after=7)

    with pytest.raises(NotReadyYet) as ex:
        asyncio.run(check_tool_ready(loading))
    assert ex.value.retry_after == 7


def test_check_tool_ready_async_false_raises():
    async def not_ready() -> bool:
        return False

    with pytest.raises(NotReadyYet):
        asyncio.run(check_tool_ready(not_ready))


def test_not_ready_http_error_sets_retry_after():
    err = health_module.not_ready_http_error(2.2)
    assert isinstance(err, HTTPException)
    assert err.status_code == 503
    assert err.headers == {"Retry-After": "3"}


# --- identity ----------------------------------------------------------------


def test_declared_version_used_when_env_unset(monkeypatch):
    monkeypatch.delenv("VERSION", raising=False)
    app = FastAPI()
    add_health_route(app, name="cas9-ivcap", version="0.1.0")
    resp = TestClient(app).get("/_healtz")
    assert resp.json() == {
        "name": "cas9-ivcap",
        "version": "0.1.0",
        "libraries": _libs(),
    }


def test_env_version_takes_priority_over_declared(monkeypatch):
    monkeypatch.setenv("VERSION", "env-version")
    app = FastAPI()
    add_health_route(app, name="cas9-ivcap", version="0.1.0")
    resp = TestClient(app).get("/_healtz")
    assert resp.json()["version"] == "env-version"


def test_unknown_version_when_neither_set(monkeypatch):
    monkeypatch.delenv("VERSION", raising=False)
    app = FastAPI()
    add_health_route(app, name="cas9-ivcap")
    resp = TestClient(app).get("/_healtz")
    assert resp.json()["version"] == "???"


def test_add_health_route_keeps_existing_route():
    app = FastAPI()

    @app.get("/_healtz")
    def custom():
        return {"custom": True}

    add_health_route(app)
    assert TestClient(app).get("/_healtz").json() == {"custom": True}
