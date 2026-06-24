# Lambda Tool Service Example

A complete, production-ready IVCAP lambda service with multiple tools, progress reporting, and artifact handling.

## Overview

This example demonstrates:

1. Multiple tools registered on a single service
2. Progress reporting with named steps
3. Artifact download and upload
4. Async tool function
5. `JobContext` injection
6. Custom `ToolOptions`

## Code

```python
import asyncio
import io
from pydantic import BaseModel, Field
from ivcap_service import (
    Service, ServiceContact, ServiceLicense,
    JobContext, getLogger, with_schema,
)
from ivcap_lambda import (
    start_lambda_server, ivcap_lambda, ToolOptions, logging_init,
)
from ivcap_lambda.executor import ExecutorOpts

# Initialize logging
logging_init()
logger = getLogger("tool_service")

# Define service metadata
service = Service(
    name="IVCAP Tool Service Example",
    contact=ServiceContact(name="Dev Team", email="dev@example.com"),
    license=ServiceLicense(name="MIT", url="https://opensource.org/license/MIT"),
)


# ── Tool 1: Echo ─────────────────────────────────────────────────────────────

@with_schema("urn:example:schema:echo.request.1")
class EchoRequest(BaseModel):
    message: str = Field(..., description="Message to echo back.")
    repeat: int = Field(1, description="Number of times to repeat the message.", ge=1, le=10)


@with_schema("urn:example:schema:echo.1")
class EchoResult(BaseModel):
    echo: str = Field(..., description="The echoed message.")
    length: int = Field(..., description="Total length of the echoed string.")


@ivcap_lambda("/echo", opts=ToolOptions(tags=["Utilities"], service_id="/echo"))
def echo(req: EchoRequest) -> EchoResult:
    """Echo a message back to the caller

    Returns the provided message repeated the requested number of times.
    Useful for testing connectivity and tool invocation patterns.
    """
    result = (req.message + " ") * req.repeat
    result = result.strip()
    return EchoResult(echo=result, length=len(result))


# ── Tool 2: Word Count (with JobContext) ─────────────────────────────────────

@with_schema("urn:example:schema:word-count.request.1")
class WordCountRequest(BaseModel):
    text: str = Field(..., description="Text to analyse.", min_length=1)


@with_schema("urn:example:schema:word-count.1")
class WordCountResult(BaseModel):
    words: int = Field(..., description="Number of words.")
    chars: int = Field(..., description="Number of characters.")
    lines: int = Field(..., description="Number of lines.")


@ivcap_lambda(
    "/word-count",
    opts=ToolOptions(
        tags=["Text Analysis"],
        service_id="/word-count",
        max_wait_time=10.0,
    ),
)
def word_count(req: WordCountRequest, jobCtxt: JobContext) -> WordCountResult:
    """Count words, characters, and lines in a piece of text

    Analyses the provided text and returns word, character, and line counts.
    Use this tool to understand the size and structure of text content.
    """
    logger.info(f"word_count job={jobCtxt.job_id}")

    with jobCtxt.report.step("analyse", "Analysing text...") as step:
        words = len(req.text.split())
        chars = len(req.text)
        lines = req.text.count("\n") + 1
        step.finished(f"Found {words} words, {chars} chars, {lines} lines")

    return WordCountResult(words=words, chars=chars, lines=lines)


# ── Tool 3: File Stats (artifact-based) ─────────────────────────────────────

@with_schema("urn:example:schema:file-stats.request.1")
class FileStatsRequest(BaseModel):
    artifact_id: str = Field(..., description="IVCAP artifact URN to inspect.")


@with_schema("urn:example:schema:file-stats.1")
class FileStatsResult(BaseModel):
    artifact_id: str = Field(..., description="URN of the inspected artifact.")
    size_bytes: int = Field(..., description="File size in bytes.")
    line_count: int = Field(..., description="Number of lines (for text files).")


@ivcap_lambda(
    "/file-stats",
    opts=ToolOptions(
        tags=["Files"],
        service_id="/file-stats",
        executor_opts=ExecutorOpts(max_workers=4, job_cache_size=500),
    ),
)
def file_stats(req: FileStatsRequest, jobCtxt: JobContext) -> FileStatsResult:
    """Get statistics for an IVCAP artifact

    Downloads the specified artifact and returns its size and line count.
    Works best with text files; binary files will have an approximate line count.
    """
    ivcap = jobCtxt.ivcap

    with jobCtxt.report.step("download", f"Downloading {req.artifact_id}") as step:
        artifact = ivcap.get_artifact(req.artifact_id)
        data = b"".join(artifact.as_stream(chunk_size=65536))
        step.finished(f"Downloaded {len(data)} bytes")

    line_count = data.decode("utf-8", errors="replace").count("\n") + 1

    return FileStatsResult(
        artifact_id=req.artifact_id,
        size_bytes=len(data),
        line_count=line_count,
    )


# ── Tool 4: Async Reverse ────────────────────────────────────────────────────

@with_schema("urn:example:schema:reverse.request.1")
class ReverseRequest(BaseModel):
    text: str = Field(..., description="Text to reverse.")


@with_schema("urn:example:schema:reverse.1")
class ReverseResult(BaseModel):
    reversed_text: str = Field(..., description="The reversed text.")


@ivcap_lambda("/reverse", opts=ToolOptions(tags=["Utilities"]))
async def reverse(req: ReverseRequest) -> ReverseResult:
    """Reverse a string asynchronously

    Returns the input string with its characters in reversed order.
    Demonstrates async tool function support.
    """
    await asyncio.sleep(0)  # yield to event loop
    return ReverseResult(reversed_text=req.text[::-1])


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    start_lambda_server(service)
```

## Testing

Start the server:

```bash
python tool_service.py --port 8090
```

Test each tool:

```bash
# Echo
curl -X POST http://localhost:8090/echo \
  -H "content-type: application/json" \
  -d '{"message": "Hello, IVCAP!", "repeat": 3}'

# Word count
curl -X POST http://localhost:8090/word-count \
  -H "content-type: application/json" \
  -d '{"text": "The quick brown fox\njumps over the lazy dog"}'

# Async reverse
curl -X POST http://localhost:8090/reverse \
  -H "content-type: application/json" \
  -d '{"text": "Hello!"}'
```

Test async (deferred) behaviour:

```bash
curl -i -X POST http://localhost:8090/word-count \
  -H "Prefer: respond-async" \
  -H "content-type: application/json" \
  -d '{"text": "some text"}'
# → 204 No Content + Location: /jobs/JOB_ID

curl http://localhost:8090/jobs/JOB_ID
# → 200 + result JSON
```

## Key Features

1. **Multiple tools** — four tools registered on a single service instance
2. **Optional `JobContext`** — tools accept it when they need it; omit it otherwise
3. **Async support** — `reverse` demonstrates an async tool
4. **Custom executor options** — `file-stats` uses a fixed thread pool and smaller cache
5. **Artifact access** — `file-stats` downloads an IVCAP artifact via `JobContext.ivcap`
6. **Progress steps** — `word-count` and `file-stats` report progress back to the platform

## See Also

- [Tool Functions Guide](../guides/tool-functions.md)
- [Artifacts Guide](../guides/artifacts.md)
- [Observability Guide](../guides/observability.md)
- [Advanced Patterns](advanced-patterns.md)
