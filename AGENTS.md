# AGENTS.md: Building Services with `ivcap-lambda`

This document routes AI coding agents to the right playbook for building services with the `ivcap-lambda` library. There are three entry points, each in its own self-contained file under `docs/agents/` — read only the one matching the developer's goal; cross-references between them are explicit where needed.

## Overview

`ivcap-lambda` turns a plain Python function into:

- A set of **IVCAP-compatible HTTP endpoints** (REST, with async "try-later" semantics), and/or
- A **spec-compliant MCP (Model Context Protocol) server** (Streamable-HTTP or stdio transport)

...from the *same* tool-function code, using the *same* Pydantic request/result models and docstrings. It extends [`ivcap-service`](https://github.com/ivcap-works/ivcap-service-sdk-python) (base primitives shared by all IVCAP services) and adds FastAPI/uvicorn HTTP scaffolding plus the MCP adapter.

**Key distinction from `ivcap-service`:**
- `ivcap-service` — batch services that poll a job queue (long-running workers)
- `ivcap-lambda` — lambda/HTTP/MCP services that respond to individual tool invocations

## Which Track Do I Need?

| Your primary goal | Read this |
|---|---|
| Build a service to deploy on the IVCAP platform (REST tool/agent endpoint); MCP is optional or not needed | **[Track A: IVCAP Lambda Service](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python/blob/main/docs/agents/track-a-ivcap-service.md)** |
| Build an MCP server (for Claude Desktop, Cursor, Cline, etc.); the ability to *also* run on IVCAP is a bonus, not the focus | **[Track B: MCP-First Server](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python/blob/main/docs/agents/track-b-mcp-first.md)** |
| Both — ship a service that's a first-class IVCAP tool *and* a first-class MCP server | Read Track A fully, then skim Track B for what changes when MCP is the primary interface |
| Already have a server built directly on the plain `mcp` Python SDK and want to move it onto `ivcap-lambda` (keeping it a working MCP server, and gaining a clean IVCAP service for free) | **[Track C: Converting an Existing Plain `mcp` SDK Server](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python/blob/main/docs/agents/track-c-migrate-from-mcp.md)** — self-contained, no need to read Track A/B first |

All three tracks share the same core building blocks (`@ivcap_lambda`, `ToolOptions`, `JobContext`, `@with_schema`) — see [Shared Reference](#shared-reference) below for the full symbol table and best practices, applicable regardless of which track you read.

## Architecture

```
ivcap-service  (batch + base primitives)
      │
      └── ivcap-lambda  (lambda / HTTP / MCP)
                │
                └── Your Tool Function
                        │
                        ├── POST /tool          ← submit job (REST)
                        ├── GET  /tool          ← tool description (agents)
                        ├── GET  /jobs/{id}     ← poll deferred result (REST)
                        └── /mcp or stdio       ← MCP tools/call (--with-mcp[-stdio])
```

---

# Shared Reference

## Best Practices (All Tracks)

1. **Always use `@with_schema`** on request/result models
2. **Write comprehensive docstrings** — both AI agents (IVCAP) and MCP hosts/models use these to decide when and how to call your tool
3. **Describe every field** with `Field(description="...")`
4. **Accept `JobContext`** when you need progress reporting or artifact access
5. **Use steps** for long operations: `with jobCtxt.report.step("name", "msg") as step:`
6. **Raise `ValueError`** for user input errors, other exceptions for system errors
7. **Call `logging_init()` once** at module level before any loggers
8. **Don't mutate module-level state** per job — tools may run concurrently (true for both REST and MCP invocations)
9. **Convert local file-path parameters to artifact URNs.** Any request field that assumed the calling user had a file available on a shared/local filesystem (e.g. `fasta_path: str`) must be renamed to an artifact URN field (`fasta_urn: str`) and resolved via `jobCtxt.ivcap.get_artifact(fasta_urn)` — not opened directly. See [Track A §9a](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python/blob/main/docs/agents/track-a-ivcap-service.md#9a-converting-local-file-path-parameters-to-artifact-urns) for the pattern, including a `urn:file://demo_data/...` fallback that still works for local testing without a platform connection. Full artifact API: [ivcap-client SDK AGENTS.md](https://github.com/ivcap-works/ivcap-client-sdk-python/blob/main/AGENTS.md) / [Working with Artifacts guide](https://ivcap-works.github.io/ivcap-client-sdk-python/guides/artifacts/).

## Key Symbols Summary

| Symbol | Package | Description | Track |
|--------|---------|-------------|-------|
| `ivcap_lambda` | `ivcap_lambda` | Decorator to register a tool function | All |
| `start_lambda_server` | `ivcap_lambda` | Start the HTTP server, or the MCP server over stdio with `--with-mcp-stdio` | All |
| `ToolOptions` | `ivcap_lambda` | Per-tool configuration | All (some fields REST-only, see Track B) |
| `ExecutorOpts` | `ivcap_lambda.executor` | Thread-pool and cache configuration | All |
| `logging_init` | `ivcap_lambda` | Initialise structured logging | All |
| `get_event_reporter` | `ivcap_lambda` | Get `EventReporter` for current thread | All |
| `get_job_id` | `ivcap_lambda` | Get job ID for current thread | All |
| `register_mcp` | `ivcap_lambda.mcp` | Mount the MCP Streamable-HTTP server onto a FastAPI app programmatically | MCP |
| `run_mcp_stdio` | `ivcap_lambda.mcp` | Run the MCP server over stdio programmatically | MCP |
| `Service` | `ivcap_service` | Service metadata | All (minimal for MCP-only) |
| `ServiceContact` | `ivcap_service` | Contact details model | IVCAP-focused |
| `ServiceLicense` | `ivcap_service` | License model | IVCAP-focused |
| `JobContext` | `ivcap_service` | Per-job context | All |
| `with_schema` | `ivcap_service` | Add `$schema` URN to a Pydantic model | All |
| `getLogger` | `ivcap_service` | Structured logger | All |
| `GenericEvent` | `ivcap_service.events` | Named progress event | All |
| `GenericErrorEvent` | `ivcap_service.events` | Error event | All |

## Related Documentation

- [Track A: IVCAP Lambda Service](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python/blob/main/docs/agents/track-a-ivcap-service.md)
- [Track B: MCP-First Server](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python/blob/main/docs/agents/track-b-mcp-first.md)
- [Track C: Converting an Existing Plain `mcp` SDK Server](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python/blob/main/docs/agents/track-c-migrate-from-mcp.md)
- [Full docs](https://ivcap-works.github.io/ivcap-ai-tool-sdk-python/)
- [MCP & Agent Integration guide](https://ivcap-works.github.io/ivcap-ai-tool-sdk-python/guides/mcp/) — full MCP walkthrough including all three paths
- [DESIGN.md](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python/blob/main/DESIGN.md) — internal architecture, for anyone extending `ivcap-lambda` itself
- [ivcap-service SDK](https://ivcap-works.github.io/ivcap-service-sdk-python/) — base library
- [Template repository](https://github.com/ivcap-works/ivcap-python-ai-tool-template) — ready-to-clone starter
- [IVCAP Platform](https://ivcap.works)
- [Pydantic Docs](https://docs.pydantic.dev/)
- [MCP Specification](https://modelcontextprotocol.io/specification)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) — the upstream SDK `ivcap-lambda`'s MCP support is built on
