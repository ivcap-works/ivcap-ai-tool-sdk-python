#
# Copyright (c) 2026 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
"""Tests for the --test-file and --test-without-sidecar CLI flags."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from ivcap_service import Service, ServiceContact, with_schema
from pydantic import BaseModel, Field

from ivcap_lambda import ToolOptions, ivcap_lambda
from ivcap_lambda import builder as builder_module
from ivcap_lambda import server as server_module

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples" / "test-tool"


@pytest.fixture(autouse=True)
def _clean_tool_registry():
    """`ivcap_lambda.builder.tools` is a module-level list; isolate tests."""
    saved = list(builder_module.tools)
    builder_module.tools.clear()
    yield
    builder_module.tools.clear()
    builder_module.tools.extend(saved)


@with_schema("urn:sd:schema:test-file.request.1")
class _Req(BaseModel):
    text: str = Field(..., description="text to echo")


@with_schema("urn:sd:schema:test-file.result.1")
class _Res(BaseModel):
    echo: str = Field(..., description="echoed text")


def _register_echo_tool():
    @ivcap_lambda("/echo", opts=ToolOptions(max_wait_time=5.0))
    def echo(req: _Req) -> _Res:
        """Echo the input text."""
        return _Res(echo=req.text)

    return echo


def _write_job(tmp_path, *, content_type="application/json", text="hello"):
    job = {
        "id": "urn:ivcap:job:1274df7e-6de4-4414-af83-897d3c8d8ad0",
        "in-content-type": content_type,
        "in-content": {"text": text},
    }
    path = tmp_path / "job.json"
    path.write_text(json.dumps(job))
    return str(path)


def test_run_test_file_executes_tool_and_prints_result(tmp_path, capsys):
    _register_echo_tool()
    path = _write_job(tmp_path, text="hello")

    server_module.run_test_file(path, builder_module.tools[0])

    out = json.loads(capsys.readouterr().out)
    assert out["echo"] == "hello"


def test_run_test_file_rejects_unsupported_content_type(tmp_path):
    _register_echo_tool()
    path = _write_job(tmp_path, content_type="text/plain")

    with pytest.raises(ValueError, match="cannot handle content-type"):
        server_module.run_test_file(path, builder_module.tools[0])


def test_test_file_flag_runs_tool_and_skips_server(tmp_path, monkeypatch, capsys):
    _register_echo_tool()
    path = _write_job(tmp_path, text="via cli")
    monkeypatch.setattr(server_module, "get_fast_app", FastAPI)
    monkeypatch.setattr(server_module, "otel_instrument", Mock())
    monkeypatch.setattr(server_module, "init_openobserve_from_env", Mock())
    monkeypatch.setattr(server_module, "set_event_reporter_factory", Mock())
    monkeypatch.setattr(server_module, "set_context", Mock())
    run_server = Mock()
    monkeypatch.setattr(server_module, "_bind_listen_socket", Mock())
    monkeypatch.setattr(server_module.uvicorn.Server, "run", run_server)

    service = Service(
        name="Test File",
        version="1.0.0",
        contact=ServiceContact(name="Test", email="test@example.com"),
    )
    server_module.start_lambda_server(
        service,
        custom_args=lambda parser: parser.parse_args(["--test-file", path]),
    )

    run_server.assert_not_called()
    out = json.loads(capsys.readouterr().out)
    assert out["echo"] == "via cli"


def test_test_without_sidecar_flag_disables_delivery(tmp_path, monkeypatch):
    _register_echo_tool()
    path = _write_job(tmp_path)
    disable = Mock()
    monkeypatch.setattr(server_module, "set_sidecar_delivery_disabled", disable)
    monkeypatch.setattr(server_module, "get_fast_app", FastAPI)
    monkeypatch.setattr(server_module, "otel_instrument", Mock())
    monkeypatch.setattr(server_module, "init_openobserve_from_env", Mock())
    monkeypatch.setattr(server_module, "set_event_reporter_factory", Mock())
    monkeypatch.setattr(server_module, "set_context", Mock())
    monkeypatch.setattr(server_module, "run_test_file", Mock())

    service = Service(
        name="Test File",
        version="1.0.0",
        contact=ServiceContact(name="Test", email="test@example.com"),
    )
    server_module.start_lambda_server(
        service,
        custom_args=lambda parser: parser.parse_args(
            ["--test-file", path, "--test-without-sidecar"]
        ),
    )

    disable.assert_called_once_with(True)


def _load_example_tool_module():
    """Import examples/test-tool/tool-service.py as a module (it is not a package)."""
    spec = importlib.util.spec_from_file_location(
        "test_tool_example", EXAMPLE_DIR / "tool-service.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def example_tool(monkeypatch):
    """Register the example's `tester` tool (and nothing else) and disable the sidecar."""
    monkeypatch.setattr(server_module, "set_sidecar_delivery_disabled", Mock())
    _load_example_tool_module()
    tool = next(t for t in builder_module.tools if t.name == "tester")
    return tool


def _example_job(tmp_path, payload, name="job.json"):
    job = {
        "id": "urn:ivcap:job:1274df7e-6de4-4414-af83-897d3c8d8ad0",
        "in-content-type": "application/json",
        "in-content": payload,
    }
    path = tmp_path / name
    path.write_text(json.dumps(job))
    return str(path)


def test_example_tool_echo_job_file(tmp_path, example_tool, capsys):
    path = _example_job(tmp_path, {"echo": "Hello World!"})

    server_module.run_test_file(path, example_tool)

    raw = capsys.readouterr().out
    out = json.loads(raw)
    assert out["echo"] == "Hello World!"
    assert out["request"]["method"] == "POST"
    assert '\n  "echo": "Hello World!"' in raw


def test_example_tool_consume_cpu_error_job_file(tmp_path, example_tool, capsys):
    """Mirrors examples/test-tool/tests/raise_error.json: the tool raises at the end."""
    payload = json.loads((EXAMPLE_DIR / "tests" / "raise_error.json").read_text())
    payload["consume_cpu"]["duration_seconds"] = 1
    path = _example_job(tmp_path, payload, name="raise_error.json")

    with pytest.raises(SystemExit) as exc:
        server_module.run_test_file(path, example_tool)

    assert exc.value.code == 1
    out = json.loads(capsys.readouterr().out)
    assert out["jschema"] == "urn:ivcap:schema.service.error.1"
    assert "Traceback" in out["traceback"]
