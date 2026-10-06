#
# Copyright (c) 2026 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
"""Tests for the MCP adapter (ivcap_lambda.mcp).

Uses the official `mcp` SDK's in-memory `Client(mcp_server)` transport, so no
network sockets are opened. Each test builds its own fresh FastAPI app and
tool registry to avoid cross-test pollution of the module-level `tools` list.
"""

import asyncio

import pytest
from fastapi import FastAPI
from ivcap_service import JobContext, with_schema
from pydantic import BaseModel, Field

from ivcap_lambda import ToolOptions, ivcap_lambda
from ivcap_lambda import builder as builder_module

mcp = pytest.importorskip("mcp", reason="the optional 'mcp' extra is not installed")


@pytest.fixture(autouse=True)
def _clean_tool_registry():
    """`ivcap_lambda.builder.tools` is a module-level list; isolate tests."""
    saved = list(builder_module.tools)
    builder_module.tools.clear()
    yield
    builder_module.tools.clear()
    builder_module.tools.extend(saved)


@with_schema("urn:sd:schema:mcp-test.request.1")
class _Req(BaseModel):
    text: str = Field(..., description="text to process")


@with_schema("urn:sd:schema:mcp-test.1")
class _Res(BaseModel):
    output: str = Field(..., description="the result")


def _build_app():
    app = FastAPI()
    builder_module.tools.clear()
    return app


def test_register_mcp_requires_sdk(monkeypatch):
    """register_mcp() raises a clear ImportError if the 'mcp' extra isn't
    installed - simulated here by patching the availability flag."""
    from ivcap_lambda import mcp as mcp_module

    app = _build_app()
    monkeypatch.setattr(mcp_module, "_MCP_SDK_AVAILABLE", False)
    with pytest.raises(ImportError, match="ivcap-lambda\\[mcp\\]"):
        mcp_module.register_mcp(app)


def test_mcp_tool_list_and_call_roundtrip():
    """A tool registered via @ivcap_lambda is exposed over MCP with the same
    Pydantic input/output schema, and a call returns the structured result."""
    from ivcap_lambda.mcp import register_mcp

    app = _build_app()

    @ivcap_lambda("/process", opts=ToolOptions(tags=["Test"]))
    def process(req: _Req, jobCtxt: JobContext) -> _Res:
        """Process text

        Uppercases the input text, reporting progress along the way.
        """
        with jobCtxt.report.step("work", "starting") as step:
            step.finished("done")
        return _Res(output=req.text.upper())

    mcp_server = register_mcp(app, "/mcp")

    async def run():
        async with mcp.Client(mcp_server) as client:
            tool_list = await client.list_tools()
            assert [t.name for t in tool_list.tools] == ["process"]
            tool = tool_list.tools[0]
            assert tool.output_schema is not None
            assert tool.output_schema["required"] == ["output"]

            progress_events = []

            async def progress_cb(progress, total, message):
                progress_events.append((progress, total, message))

            result = await client.call_tool(
                "process",
                {"req": {"text": "hi"}},
                progress_callback=progress_cb,
            )
            assert result.structured_content["output"] == "HI"
            # jobCtxt.report.step(...) was bridged to MCP progress notifications
            assert len(progress_events) == 2
            assert progress_events[0][2] == "starting"
            assert progress_events[1][2] == "done"

    asyncio.run(run())


def test_run_mcp_stdio_builds_server_and_runs_stdio_transport(monkeypatch):
    """run_mcp_stdio() registers every tool (via the same _build_mcp_server
    helper used by register_mcp) and starts the stdio transport."""
    from ivcap_lambda import mcp as mcp_module

    _build_app()

    @ivcap_lambda("/process", opts=ToolOptions(tags=["Test"]))
    def process(req: _Req, jobCtxt: JobContext) -> _Res:
        """Process text"""
        return _Res(output=req.text.upper())

    captured = {}

    class _FakeMCPServer:
        def __init__(self, name, version=""):
            captured["name"] = name
            captured["version"] = version
            self.tools = []

        def add_tool(self, fn, name=None, description=None):
            self.tools.append(name)

        def run(self, transport="stdio"):
            captured["transport"] = transport

    monkeypatch.setattr(mcp_module, "MCPServer", _FakeMCPServer)

    mcp_module.run_mcp_stdio("My Service", "1.2.3")

    assert captured["name"] == "My Service"
    assert captured["version"] == "1.2.3"
    assert captured["transport"] == "stdio"


def test_mcp_tool_call_error_propagation():
    """A ValueError raised by a tool surfaces as an MCP tool error
    (is_error=True) rather than crashing the call."""
    from ivcap_lambda.mcp import register_mcp

    app = _build_app()

    @ivcap_lambda("/fail", opts=ToolOptions(tags=["Test"]))
    def fail(req: _Req, jobCtxt: JobContext) -> _Res:
        """Always fails"""
        raise ValueError(f"bad input: {req.text}")

    mcp_server = register_mcp(app, "/mcp")

    async def run():
        async with mcp.Client(mcp_server) as client:
            result = await client.call_tool("fail", {"req": {"text": "hi"}})
            assert result.is_error is True
            assert "bad input: hi" in result.content[0].text

    asyncio.run(run())
