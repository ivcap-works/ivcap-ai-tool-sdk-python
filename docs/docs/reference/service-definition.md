# Service Definition Schema

Reference for the service definition structure used by `ivcap-lambda`.

## Service Class

The `Service` class (from `ivcap_service`) defines your service metadata. It is passed to `start_lambda_server` and used to populate the FastAPI application title, version, contact, and license.

```python
from ivcap_service import Service, ServiceContact, ServiceLicense

service = Service(
    name="My Lambda Service",
    contact=ServiceContact(name="Alice", email="alice@example.com"),
    license=ServiceLicense(name="MIT", url="https://opensource.org/license/MIT"),
)
```

## ServiceContact Class

```python
contact = ServiceContact(
    name="Alice Smith",
    email="alice@example.com",
    url="https://example.com/alice",   # optional
)
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | ✅ | Full name of the contact person |
| `email` | `str` | ✅ | Email address of the contact person |
| `url` | `str \| None` | ❌ | Optional URL (e.g. profile or team page) |

## ServiceLicense Class

```python
license = ServiceLicense(
    name="MIT",
    url="https://opensource.org/license/MIT",   # optional
)
```

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | ✅ | License name (e.g. MIT, Apache-2.0) |
| `url` | `str \| None` | ❌ | Optional URL pointing to the full license text |

## Service Fields

### Required
- **name** (`str`) — Human-readable service name

### Optional
- **contact** (`ServiceContact | None`) — Typed contact details
- **license** (`ServiceLicense | None`) — Typed license information
- **version** (`str | None`) — Service version; defaults to `VERSION` environment variable

## Generated Tool Description

When you run:

```bash
python my_service.py --print-tool-description
```

The SDK generates a JSON tool description like:

```json
{
  "name": "greet",
  "description": "Greet a person\n\nGenerates a personalised greeting...",
  "service_id": "https://example.com/greet",
  "input": {
    "$schema": "urn:example:schema:my-tool.request.1",
    "properties": {
      "name": {"type": "string", "description": "Name to greet."},
      "count": {"type": "integer", "description": "Repetitions.", "default": 1}
    }
  },
  "output": {
    "$schema": "urn:example:schema:my-tool.1",
    "properties": {
      "greeting": {"type": "string", "description": "The generated greeting."}
    }
  }
}
```

This is used by AI agents and the MCP endpoint to understand what the tool does and how to call it.

## Full Service Description

```bash
python my_service.py --print-service-description
```

Generates the full REST service definition (including OpenAPI spec) for registration with the IVCAP platform.

## pyproject.toml Integration

Use the `[tool.poetry-plugin-ivcap]` section to integrate with the `poetry-plugin-ivcap` tooling:

```toml
[tool.poetry-plugin-ivcap]
service-file = "my_service.py"
service-id   = "urn:ivcap:service:<uuid>"
service-type = "lambda"
port         = 8095
```

## See Also

- [Service API](https://ivcap-works.github.io/ivcap-service-sdk-python/api/service/) — `ivcap_service.Service` full reference
- [Tool Functions Guide](../guides/tool-functions.md) — `ToolOptions` and endpoint registration
- [Deployment Guide](../guides/deployment.md) — Registering with IVCAP
