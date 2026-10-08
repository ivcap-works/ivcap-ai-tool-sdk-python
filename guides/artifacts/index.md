# Working with Artifacts Guide

IVCAP artifacts are files or data objects stored on the platform. Lambda tools can download artifacts as input and upload results as new artifacts via the `JobContext.ivcap` client (provided by [`ivcap-service`](https://ivcap-works.github.io/ivcap-service-sdk-python/guides/artifacts/)).

## Downloading Artifacts

Accept an artifact URN as a request field and stream it in your tool:

```python
from pydantic import BaseModel, Field
from ivcap_service import JobContext, with_schema
from ivcap_lambda import ivcap_lambda, ToolOptions

@with_schema("urn:example:schema:analyse-file.request.1")
class AnalyseFileRequest(BaseModel):
    artifact_id: str = Field(..., description="IVCAP artifact URN of the file to analyse.")

@with_schema("urn:example:schema:analyse-file.1")
class AnalyseFileResult(BaseModel):
    size_bytes: int = Field(..., description="Size of the file in bytes.")
    line_count: int = Field(..., description="Number of lines in the file.")

@ivcap_lambda("/analyse-file")
def analyse_file(req: AnalyseFileRequest, jobCtxt: JobContext) -> AnalyseFileResult:
    """Analyse a text file artifact

    Downloads the specified artifact and counts its lines and bytes.
    """
    ivcap = jobCtxt.ivcap

    with jobCtxt.report.step("download", f"Downloading {req.artifact_id}") as step:
        artifact = ivcap.get_artifact(req.artifact_id)
        data = b"".join(artifact.as_stream(chunk_size=8192))
        step.finished(f"Downloaded {len(data)} bytes")

    line_count = data.decode("utf-8", errors="replace").count("\n")
    return AnalyseFileResult(size_bytes=len(data), line_count=line_count)
```

### Streaming to a Temporary File

For large files, stream to a local temporary file using `as_local_file()`:

```python
with jobCtxt.report.step("download", "Downloading image") as step:
    artifact = ivcap.get_artifact(req.artifact_id)
    with artifact.as_local_file() as path:
        # `path` is a `pathlib.Path` to a temporary file (auto-deleted on exit)
        image_bytes = path.read_bytes()
    step.finished(f"Loaded {len(image_bytes)} bytes")
```

## Uploading Artifacts

Upload results back to the IVCAP platform using `ivcap.upload_artifact()`:

```python
import io
from ivcap_service import JobContext
from ivcap_lambda import ivcap_lambda

@with_schema("urn:example:schema:transform.request.1")
class TransformRequest(BaseModel):
    artifact_id: str = Field(..., description="URN of the input artifact.")

@with_schema("urn:example:schema:transform.1")
class TransformResult(BaseModel):
    result_artifact_id: str = Field(..., description="URN of the output artifact.")
    bytes_written: int = Field(..., description="Size of the output artifact.")

@ivcap_lambda("/transform")
def transform(req: TransformRequest, jobCtxt: JobContext) -> TransformResult:
    """Transform an artifact

    Applies a transformation to the input artifact and uploads the result.
    """
    ivcap = jobCtxt.ivcap

    # Download
    with jobCtxt.report.step("download", "Downloading input") as step:
        artifact = ivcap.get_artifact(req.artifact_id)
        data = b"".join(artifact.as_stream())
        step.finished(f"Downloaded {len(data)} bytes")

    # Transform
    with jobCtxt.report.step("transform", "Applying transformation") as step:
        output = data.upper()  # Replace with real transformation
        step.finished("Transformation complete")

    # Upload
    with jobCtxt.report.step("upload", "Uploading result") as step:
        result_artifact = ivcap.upload_artifact(
            name="transformed-output.txt",
            io_stream=io.BytesIO(output),
            content_type="text/plain",
            content_size=len(output),
        )
        step.finished(f"Uploaded: {result_artifact.id}")

    return TransformResult(
        result_artifact_id=result_artifact.id,
        bytes_written=len(output),
    )
```

### Upload Parameters

| Parameter | Description |
|-----------|-------------|
| `name` | Human-readable filename for the artifact |
| `io_stream` | A file-like object (e.g. `io.BytesIO`) containing the data |
| `content_type` | MIME type of the content (e.g. `"image/jpeg"`, `"application/json"`) |
| `content_size` | Size of the content in bytes |
| `collection` | (optional) Collection URN to add the artifact to |

## Progress Reporting During Transfer

For large artifacts, report byte-level progress to the platform:

```python
from ivcap_service.events import GenericEvent

with jobCtxt.report.step("download", f"Streaming {artifact.id}") as step:
    bytes_received = 0
    chunks = []
    for chunk in artifact.as_stream(chunk_size=65536):
        chunks.append(chunk)
        bytes_received += len(chunk)
        if bytes_received % (1024 * 1024) == 0:  # every 1 MB
            step.info(GenericEvent(
                name="progress",
                options={"bytes": bytes_received}
            ))
    data = b"".join(chunks)
    step.finished(f"Downloaded {bytes_received} bytes")
```

## Working with JSON Artifacts

```python
import json
import io

# Download and parse JSON
artifact = ivcap.get_artifact(req.artifact_id)
raw = b"".join(artifact.as_stream())
payload = json.loads(raw.decode("utf-8"))

# Upload JSON
output = {"result": "value", "count": 42}
output_bytes = json.dumps(output, indent=2).encode("utf-8")
result_artifact = ivcap.upload_artifact(
    name="result.json",
    io_stream=io.BytesIO(output_bytes),
    content_type="application/json",
    content_size=len(output_bytes),
)
```

## Accessing Artifact Metadata

```python
artifact = ivcap.get_artifact(req.artifact_id)
logger.info(f"Name: {artifact.name}")
logger.info(f"Size: {artifact.size}")
logger.info(f"Content-type: {artifact.content_type}")
logger.info(f"ID: {artifact.id}")
```

## Converting Local File-Path Parameters to Artifact URNs

If you're turning an existing function into an IVCAP tool, it may have a parameter that assumed the caller had the file available on a local/shared filesystem, e.g. `fasta_path: str`. On IVCAP there is no shared filesystem between the caller and the service, so **any such parameter must become an artifact URN field** (`fasta_urn: str`), resolved lazily via `jobCtxt.ivcap.get_artifact(...)` instead of opened directly with `open(...)`:

```python
@with_schema("urn:example:schema:genome.request.1")
class GenomeRequest(BaseModel):
    fasta_urn: str = Field(
        ...,
        description="IVCAP artifact URN of the genome FASTA file (or a urn:file://... URN for local testing).",
    )

def _resolve_fasta(jobCtxt: JobContext, fasta_urn: str):
    """Resolve the genome FASTA artifact (existence-checked, not downloaded yet)."""
    return jobCtxt.ivcap.get_artifact(fasta_urn)

@ivcap_lambda("/analyse-genome")
def analyse_genome(req: GenomeRequest, jobCtxt: JobContext) -> GenomeResult:
    """Analyse a genome FASTA file."""
    artifact = _resolve_fasta(jobCtxt, req.fasta_urn)
    with artifact.as_local_file() as path:   # downloaded to a temp file on first use
        ...
```

- `get_artifact(urn)` is lazy — it only checks that the artifact exists, it doesn't download any bytes yet. Only `as_local_file()`/`as_stream()` actually pull data.
- **For local testing**, pass a local-file artifact URN such as `fasta_urn="urn:file://demo_data/sample.fasta"`. `jobCtxt.ivcap.get_artifact()` transparently resolves `urn:file://...` (and plain `file://...`) URNs to a `LocalFileArtifact` with no network call, so the exact same code path reads straight off disk — no test-only branching required.
- Full details on the local-mode/`urn:file://` scheme and the rest of the artifact API: [ivcap-client SDK AGENTS.md](https://github.com/ivcap-works/ivcap-client-sdk-python/blob/main/AGENTS.md) and the [Working with Artifacts guide](https://ivcap-works.github.io/ivcap-client-sdk-python/guides/artifacts/).

## See Also

- [ivcap-service Artifacts Guide](https://ivcap-works.github.io/ivcap-service-sdk-python/guides/artifacts/) — Full artifact client documentation
- [Tool Functions Guide](tool-functions.md) — Accessing `JobContext`
- [Observability Guide](observability.md) — Progress reporting
- [Best Practices](best-practices.md) — Efficient artifact handling
