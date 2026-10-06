# Agent Guide

This page is the machine-readable quick-reference for `ivcap-lambda`, designed for
AI coding assistants (Copilot, Cursor, Claude, Cline, …). It's split into a router
(`AGENTS.md` at the project root) plus three track-specific playbooks under
`docs/agents/`, so an agent working on one specific task only needs to load the
relevant file(s).

It is also available at the project root as
[`AGENTS.md`](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python/blob/main/AGENTS.md),
which routes to three track-specific files under `docs/agents/` in the source
repository ([Track A](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python/blob/main/docs/agents/track-a-ivcap-service.md),
[Track B](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python/blob/main/docs/agents/track-b-mcp-first.md),
[Track C](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python/blob/main/docs/agents/track-c-migrate-from-mcp.md))
for agents that scan repository metadata before writing code.

!!! tip "Also available in your repo"
    When you clone this repository, `AGENTS.md` is at the project root (with its
    linked files under `docs/agents/`) so your IDE and any context-scanning agents
    can find it automatically.

---

--8<-- "AGENTS.md"
