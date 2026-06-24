# Server: `start_lambda_server`

This page documents `start_lambda_server` — the function that configures and starts the FastAPI/uvicorn HTTP server for your lambda service.

::: ivcap_lambda.server.start_lambda_server

---

## `get_fast_app`

Returns the shared FastAPI application instance. Useful when you need to add custom routes or middleware:

::: ivcap_lambda.server.get_fast_app

---

## Deprecated: `start_tool_server`

::: ivcap_lambda.server.start_tool_server
