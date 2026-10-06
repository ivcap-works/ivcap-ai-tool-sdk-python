#!/usr/bin/env bash
#
# Minimal MCP (streamable-HTTP) client using only curl - no 'mcp' SDK or
# node/npm tooling required.
#
# Does the three required request/response steps of the MCP streamable-HTTP
# transport (https://modelcontextprotocol.io/specification):
#   1. POST .../mcp  method=initialize        -> captures 'Mcp-Session-Id'
#   2. POST .../mcp  method=notifications/initialized
#   3. POST .../mcp  method=tools/call         -> prints every SSE event
#      (progress notifications as well as the final tool result) as JSON.
#
# Usage:
#   mcp-call.sh <tool-name> <path-to-json-file-with-args>
#
# Example:
#   ./mcp-call.sh wordle wordle.json
#   ./mcp-call.sh compute compute.json
#
set -euo pipefail

MCP_URL="${MCP_URL:-http://localhost:8096/mcp}"
TOOL="${1:?usage: mcp-call.sh <tool-name> <args-json-file>}"
ARGS_FILE="${2:?usage: mcp-call.sh <tool-name> <args-json-file>}"

HEADERS_FILE=$(mktemp)
trap 'rm -f "$HEADERS_FILE"' EXIT

# 1. initialize - the session id returned here must be sent on every
#    subsequent request for this MCP session.
curl -sS -D "$HEADERS_FILE" -o /dev/null -X POST "$MCP_URL" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"1.0"}}}'

SESSION_ID=$(grep -i '^mcp-session-id:' "$HEADERS_FILE" | tr -d '\r' | awk '{print $2}')
if [ -z "$SESSION_ID" ]; then
  echo "error: no Mcp-Session-Id returned by $MCP_URL - is the server running with --with-mcp?" >&2
  exit 1
fi

# 2. notifications/initialized - required handshake step before any other
#    call is accepted on this session.
curl -sS -o /dev/null -X POST "$MCP_URL" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'

# 3. tools/call - the response is a Server-Sent-Events stream: zero or more
#    'notifications/progress' events (if the tool reports progress) followed
#    by one final response event carrying the tool's result.
REQ_JSON=$(cat "$ARGS_FILE")
curl -sS -N -X POST "$MCP_URL" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H "Mcp-Session-Id: $SESSION_ID" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"$TOOL\",\"arguments\":{\"req\":$REQ_JSON},\"_meta\":{\"progressToken\":\"mcp-call-sh\"}}}" \
  | sed -n 's/^data: //p' \
  | if command -v jq >/dev/null 2>&1; then jq .; else cat; fi
