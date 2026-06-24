# Your First Lambda Service

In this guide, we'll build a complete, production-ready lambda service that processes text and demonstrates artifact handling, progress reporting, and async tool semantics.

## Project Setup

Create a new directory for your service:

```bash
mkdir my-lambda-service
cd my-lambda-service
```

Create a `pyproject.toml`:

```toml
[tool.poetry]
name = "my-lambda-service"
version = "0.1.0"
description = "An IVCAP lambda service"

[tool.poetry.dependencies]
python = ">=3.11,<4.0"
ivcap-lambda = ">=0.7"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[tool.poetry-plugin-ivcap]
service-file = "my_service.py"
service-id   = "urn:ivcap:service:<your-uuid>"
service-type = "lambda"
port         = 8095
```

Install dependencies:

```bash
poetry install
```

## Step 1: Define the Service

Create `my_service.py`:

```python
import os
from pydantic import BaseModel, Field
from ivcap_service import (
    Service, ServiceContact, ServiceLicense,
    JobContext, getLogger, with_schema,
)
from ivcap_lambda import start_lambda_server, ivcap_lambda, ToolOptions, logging_init

# Initialize logging
logging_init()
logger = getLogger("my_service")

# Service metadata
service = Service(
    name="My Lambda Service",
    contact=ServiceContact(name="Your Name", email="you@example.com"),
    license=ServiceLicense(name="MIT", url="https://opensource.org/license/MIT"),
)
```

## Step 2: Define Request and Result Models

```python
@with_schema("urn:sd:schema:my-lambda-service.summarise.request.1")
class SummariseRequest(BaseModel):
    """Request to summarise a piece of text."""
    text: str = Field(..., description="Text to summarise")
    max_words: int = Field(50, description="Maximum words in the summary", ge=1, le=500)


@with_schema("urn:sd:schema:my-lambda-service.summarise.1")
class SummariseResult(BaseModel):
    """Result of a summarisation."""
    summary: str = Field(..., description="The generated summary")
    word_count: int = Field(..., description="Word count of the summary")
    original_word_count: int = Field(..., description="Word count of the input text")
```

## Step 3: Implement the Tool Function

```python
@ivcap_lambda("/summarise", opts=ToolOptions(tags=["Text"], service_id="/summarise"))
def summarise(req: SummariseRequest, jobCtxt: JobContext) -> SummariseResult:
    """Summarise a piece of text

    Returns a shortened version of the provided text, capped at the requested
    maximum number of words. Suitable for preprocessing text for downstream
    analysis or display.
    """
    logger.info(f"job_id={jobCtxt.job_id}: summarising {len(req.text)} chars")

    with jobCtxt.report.step("tokenise", "Tokenising input") as step:
        words = req.text.split()
        step.finished(f"Found {len(words)} words")

    with jobCtxt.report.step("summarise", "Generating summary") as step:
        summary_words = words[: req.max_words]
        if len(words) > req.max_words:
            summary_words.append("...")
        summary = " ".join(summary_words)
        step.finished(f"Summary: {len(summary_words)} words")

    return SummariseResult(
        summary=summary,
        word_count=len(summary_words),
        original_word_count=len(words),
    )
```

## Step 4: Add the Entry Point

```python
if __name__ == "__main__":
    start_lambda_server(service)
```

## Step 5: Test Locally

Start the server:

```bash
poetry run python my_service.py --port 8095
```

Test with `curl`:

```bash
curl -X POST http://localhost:8095/summarise \
  -H "content-type: application/json" \
  -d '{"text": "The quick brown fox jumps over the lazy dog. This is a longer sentence to demonstrate truncation.", "max_words": 5}'
```

Expected response:
```json
{
  "summary": "The quick brown fox jumps ...",
  "word_count": 6,
  "original_word_count": 18
}
```

View the tool description (for agents):

```bash
curl http://localhost:8095/summarise
```

Print the service description (for platform registration):

```bash
poetry run python my_service.py --print-service-description
```

## Step 6: Adding an Artifact-Based Tool

Tools can also accept and produce IVCAP artifacts:

```python
from ivcap_service.events import GenericEvent

@with_schema("urn:sd:schema:my-lambda-service.process-file.request.1")
class ProcessFileRequest(BaseModel):
    artifact_id: str = Field(..., description="IVCAP artifact URN to process")


@with_schema("urn:sd:schema:my-lambda-service.process-file.1")
class ProcessFileResult(BaseModel):
    result_artifact_id: str = Field(..., description="URN of the result artifact")
    bytes_processed: int = Field(..., description="Number of bytes read")


@ivcap_lambda("/process-file", opts=ToolOptions(tags=["Files"]))
def process_file(req: ProcessFileRequest, jobCtxt: JobContext) -> ProcessFileResult:
    """Process an IVCAP artifact

    Downloads the artifact identified by artifact_id, processes it, and
    uploads the result as a new artifact.
    """
    ivcap = jobCtxt.ivcap

    with jobCtxt.report.step("download", f"Downloading {req.artifact_id}") as step:
        artifact = ivcap.get_artifact(req.artifact_id)
        data = b"".join(artifact.as_stream())
        step.finished(f"Downloaded {len(data)} bytes")

    with jobCtxt.report.step("process", "Processing data") as step:
        # Replace with your processing logic
        processed = data.upper()
        step.finished("Processing complete")

    with jobCtxt.report.step("upload", "Uploading result") as step:
        import io
        result = ivcap.upload_artifact(
            name="processed-result.bin",
            io_stream=io.BytesIO(processed),
            content_type="application/octet-stream",
            content_size=len(processed),
        )
        step.finished(f"Uploaded: {result.id}")

    return ProcessFileResult(
        result_artifact_id=result.id,
        bytes_processed=len(data),
    )
```

## Step 7: Dockerize

Create a `Dockerfile`:

```dockerfile
FROM python:3.11-slim-bookworm
WORKDIR /app

COPY pyproject.toml ./
RUN pip install poetry \
  && poetry config virtualenvs.create false \
  && poetry install --no-root \
  && pip uninstall -y poetry

COPY my_service.py ./

ARG VERSION=dev
ENV VERSION=$VERSION
ENV PORT=80

ENTRYPOINT ["python", "/app/my_service.py"]
```

Build and run:

```bash
docker build -t my-lambda-service .
docker run -p 8095:80 my-lambda-service
```

## Step 8: Register with IVCAP

```bash
# Get the service description
python my_service.py --print-service-description > service.json

# Register with IVCAP
ivcap service register service.json
```

## Next Steps

- **[Tool Functions Guide](../guides/tool-functions.md)** — Deep dive into `@ivcap_lambda` options
- **[Artifacts Guide](../guides/artifacts.md)** — Uploading and downloading artifacts
- **[MCP Guide](../guides/mcp.md)** — Expose your tools to AI agents via MCP
- **[Deployment Guide](../guides/deployment.md)** — Production deployment patterns
- **[Best Practices](../guides/best-practices.md)** — Pro tips

## See Also

- [API Reference](../api/overview.md) — All classes and functions
- [Examples](../examples/tool-service.md) — More complete examples
