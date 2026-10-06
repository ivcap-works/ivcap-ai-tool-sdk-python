PROJECT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))

PORT=8096
MCP_URL=http://localhost:${PORT}/mcp

# Default: run with the MCP endpoint mounted - this is an MCP example, so
# that's the mode you want by default. Use 'run-rest-only' for the plain
# REST endpoints without MCP.
run: run-with-mcp

run-with-mcp:
	env VERSION=$(VERSION) \
		PYTHONPATH="" \
		poetry run python mcp-service.py --port ${PORT} --with-mcp

run-rest-only:
	env VERSION=$(VERSION) \
		PYTHONPATH="" \
		PORT=${PORT} \
		poetry ivcap run

run-mcp-stdio:
	poetry run python mcp-service.py --with-mcp-stdio

# --- MCP tests (require the server running with --with-mcp, i.e. 'make run') ---
# Uses tests/mcp-call.sh, a small curl-only MCP (streamable-HTTP) client:
# it does 'initialize' -> 'notifications/initialized' -> 'tools/call' and
# prints every SSE event (progress notifications + the final result).

test-wordle:
	MCP_URL=${MCP_URL} ${PROJECT_DIR}/tests/mcp-call.sh wordle ${PROJECT_DIR}/tests/wordle.json

test-compute:
	MCP_URL=${MCP_URL} ${PROJECT_DIR}/tests/mcp-call.sh compute ${PROJECT_DIR}/tests/compute.json

test-compute-with-exception:
	MCP_URL=${MCP_URL} ${PROJECT_DIR}/tests/mcp-call.sh compute ${PROJECT_DIR}/tests/compute-with-exception.json

# WARNING: this actually exhausts memory and gets the server process
# OOM-killed by the OS - the curl call will error out ('transfer closed')
# once that happens, and the server must be restarted ('make run') afterwards.
# Deliberately excluded from 'test-all' for that reason.
test-compute-with-oom:
	MCP_URL=${MCP_URL} ${PROJECT_DIR}/tests/mcp-call.sh compute ${PROJECT_DIR}/tests/compute-with-oom.json

# 'echo' is defined with 'async def' (not plain 'def') - this exercises
# ivcap-lambda's support for async tool functions over MCP.
test-echo:
	MCP_URL=${MCP_URL} ${PROJECT_DIR}/tests/mcp-call.sh echo ${PROJECT_DIR}/tests/echo.json

test-all: test-wordle test-compute test-compute-with-exception test-echo

mcp-inspector:
	npx @modelcontextprotocol/inspector --config mcp-inspector.config.json --server default
