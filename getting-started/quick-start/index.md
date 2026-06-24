# Quick Start

Get a working IVCAP lambda service running in 5 minutes.

## 1. Install the SDK

```bash
pip install ivcap-lambda
```

## 2. Create Your Service

Save this as `my_service.py`:

```python
from pydantic import BaseModel, Field
from ivcap_service import Service, ServiceContact, ServiceLicense, JobContext, getLogger, with_schema
from ivcap_lambda import start_lambda_server, ivcap_lambda, ToolOptions, logging_init

# Initialize logging
logging_init()
logger = getLogger("my_service")

# Define your service
service = Service(
    name="My First Lambda Service",
    contact=ServiceContact(name="Your Name", email="you@example.com"),
    license=ServiceLicense(name="MIT", url="https://opensource.org/license/MIT"),
)


# Define request schema
@with_schema("urn:sd:schema:my_service.request.1")
class GreetRequest(BaseModel):
    name: str = Field(description="Name to greet")
    count: int = Field(1, description="Number of times to repeat the greeting", ge=1)


# Define result schema
@with_schema("urn:sd:schema:my_service.1")
class GreetResult(BaseModel):
    greeting: str = Field(description="The generated greeting")


# Register the tool
@ivcap_lambda("/greet", opts=ToolOptions(tags=["Greeter"]))
def greet(req: GreetRequest) -> GreetResult:
    """Greet a person

    Generates a personalised greeting the requested number of times.
    """
    logger.info(f"Greeting {req.name} x{req.count}")
    return GreetResult(greeting=(f"Hello, {req.name}! " * req.count).strip())


# Start the server
if __name__ == "__main__":
    start_lambda_server(service)
```

## 3. Run It

```bash
python my_service.py --port 8090
```

The server starts listening on port 8090. You can now:

- Call `POST /greet` to submit a job
- Call `GET /greet` to get the tool description
- Open `http://localhost:8090/api` for the interactive Swagger UI

## 4. Test It

Submit a request with `curl`:

```bash
curl -X POST http://localhost:8090/greet \
  -H "content-type: application/json" \
  -d '{"name": "IVCAP", "count": 2}'
```

Expected response:
```json
{"greeting": "Hello, IVCAP! Hello, IVCAP!"}
```

Get the tool description (for AI agents):

```bash
curl http://localhost:8090/greet
```

## 5. View the Swagger UI

Open [http://localhost:8090/api](http://localhost:8090/api) in your browser to explore the API interactively.

## 6. Print Service/Tool Descriptions

```bash
# Print the tool description (for agent registration)
python my_service.py --print-tool-description

# Print the full service description (for IVCAP platform registration)
python my_service.py --print-service-description
```

## Next Steps

- **[Your First Lambda Service](first-service.md)** — Build a more complete example with `JobContext`
- **[Tool Functions Guide](../guides/tool-functions.md)** — Learn advanced patterns
- **[Examples](../examples/tool-service.md)** — See production-ready code
- **[API Reference](../api/overview.md)** — Complete class/function documentation

## Common Patterns

### Accepting a JobContext

Access the job ID and event reporter:

```python
from ivcap_service import JobContext

@ivcap_lambda("/process")
def process(req: GreetRequest, jobCtxt: JobContext) -> GreetResult:
    logger.info(f"job_id={jobCtxt.job_id}")
    with jobCtxt.report.step("work", "Processing...") as step:
        result = do_work(req)
        step.finished("Done!")
    return GreetResult(greeting=result)
```

### Async Tools

Async functions are fully supported:

```python
import asyncio

@ivcap_lambda("/async-greet")
async def async_greet(req: GreetRequest) -> GreetResult:
    """Async greeting tool"""
    await asyncio.sleep(0)  # yield
    return GreetResult(greeting=f"Hello, {req.name}!")
```

### Controlling Async Behaviour

Force a response immediately or wait for a specific timeout:

```bash
# Respond immediately (204 + Location if not done)
curl -i -X POST http://localhost:8090/greet \
  -H "Prefer: respond-async" \
  -H "content-type: application/json" \
  -d '{"name": "IVCAP"}'

# Custom timeout (seconds)
curl -i -X POST http://localhost:8090/greet \
  -H "Timeout: 10" \
  -H "content-type: application/json" \
  -d '{"name": "IVCAP"}'

# Poll for a deferred result
curl http://localhost:8090/jobs/JOB_ID
```

## Troubleshooting

### "No tools have been registered"

Make sure you have at least one `@ivcap_lambda` decorated function **before** calling `start_lambda_server()`.

### Port already in use

Change the port:
```bash
python my_service.py --port 8091
```

Or set the `PORT` environment variable:
```bash
PORT=8091 python my_service.py
```
