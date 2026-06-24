# Deployment Guide

Deploy your IVCAP lambda service to production.

## Docker Containerization

Create a minimal `Dockerfile`:

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
docker build --build-arg VERSION=1.2.3 -t my-lambda-service:1.2.3 .
docker run -p 8090:80 my-lambda-service:1.2.3
```

## Environment Configuration

### Local Development

```bash
# Port (can also be set with --port)
export PORT=8095

# Optional: OpenObserve integration
export OPENOBSERVE_URL="http://localhost:5080"
export OPENOBSERVE_ORG="myorg"
export OPENOBSERVE_USERNAME="admin@example.com"
export OPENOBSERVE_TOKEN="<token>"

# Run the service
python my_service.py
```

### Production Environment

```bash
# Service version
export VERSION="1.2.3"

# Server binding
export HOST="0.0.0.0"
export PORT="80"

# Observability
export OPENOBSERVE_URL="https://observe.example.com"
export OPENOBSERVE_ORG="production"
export OPENOBSERVE_USERNAME="service@example.com"
export OPENOBSERVE_TOKEN="<production-token>"

# Distributed tracing
export OTEL_EXPORTER_OTLP_ENDPOINT="http://otel-collector:4318"
```

## Service Registration

Print the service description (for IVCAP registration):

```bash
docker run my-lambda-service:latest --print-service-description > service.json
```

Register with IVCAP:

```bash
ivcap service register service.json
```

## CLI Flags

`start_lambda_server` provides these built-in CLI flags:

```
--host HOST                  Bind address (default: 0.0.0.0 / $HOST)
--port PORT                  Port to listen on (default: 8090 / $PORT)
--with-telemetry             Initialise OpenTelemetry tracing
--with-mcp                   Expose an MCP endpoint at /mcp
--print-tool-description     Print the tool description JSON and exit
--print-service-description  Print the full service description JSON and exit
```

## Custom CLI Flags

Add your own command-line flags via `custom_args`:

```python
import argparse
import os

def custom_args(parser: argparse.ArgumentParser) -> argparse.Namespace:
    parser.add_argument("--model-path", type=str, help="Path to the model file")
    parser.add_argument("--batch-size", type=int, default=32, help="Inference batch size")
    args = parser.parse_args()
    if args.model_path:
        os.environ["MODEL_PATH"] = args.model_path
    if args.batch_size:
        os.environ["BATCH_SIZE"] = str(args.batch_size)
    return args

if __name__ == "__main__":
    start_lambda_server(service, custom_args=custom_args)
```

## Kubernetes Deployment

Create a `deployment.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-lambda-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: my-lambda-service
  template:
    metadata:
      labels:
        app: my-lambda-service
    spec:
      containers:
      - name: my-lambda-service
        image: my-lambda-service:1.2.3
        ports:
        - containerPort: 80
        env:
        - name: VERSION
          value: "1.2.3"
        - name: OPENOBSERVE_URL
          value: "https://observe.example.com"
        - name: OPENOBSERVE_TOKEN
          valueFrom:
            secretKeyRef:
              name: observability
              key: token
        resources:
          requests:
            memory: "256Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /_healtz
            port: 80
          initialDelaySeconds: 10
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /_healtz
            port: 80
          initialDelaySeconds: 5
          periodSeconds: 10
```

Deploy:

```bash
kubectl apply -f deployment.yaml
```

## Scalability Patterns

Lambda services are stateless by design — each tool invocation is independent. The IVCAP platform can route requests to any instance.

### Thread Pool Sizing

Configure the thread pool for CPU-intensive tools:

```python
from ivcap_lambda import ExecutionContext
from ivcap_lambda.executor import ExecutorOpts

@ivcap_lambda(
    "/analyse",
    opts=ToolOptions(
        tags=["ML"],
        executor_opts=ExecutorOpts(
            max_workers=4,          # Fixed thread pool of 4
            job_cache_size=1000,    # Cache up to 1000 job results
            job_cache_ttl=3600,     # Cache results for 1 hour
        )
    )
)
def analyse(req: AnalyseRequest) -> AnalyseResult:
    ...
```

### Resource Requirements

Set resource requirements in your service definition (IVCAP platform uses this for scheduling):

```python
from ivcap_service import Service, ResourceRequirements

service = Service(
    name="GPU Inference Service",
    resources=ResourceRequirements(cpu=2, memory="4Gi", gpu=1),
    ...
)
```

## Troubleshooting

### Container Won't Start

Check logs:
```bash
docker logs my-lambda-service
```

Print service description to verify configuration:
```bash
docker run my-lambda-service:latest --print-service-description
```

### Jobs Timing Out

Increase `max_wait_time` in `ToolOptions`:
```python
@ivcap_lambda("/slow-tool", opts=ToolOptions(max_wait_time=30.0))
def slow_tool(req: SlowRequest) -> SlowResult:
    ...
```

Or encourage clients to use the async pattern:
```bash
curl -X POST http://localhost:8090/slow-tool \
  -H "Prefer: respond-async" \
  ...
```

### High Memory Usage

Check `job_cache_size` and `job_cache_ttl` in `ExecutorOpts`. The job result cache holds completed job results in memory; reduce its size if needed.

## See Also

- [Best Practices](best-practices.md) — Production patterns
- [Observability](observability.md) — Monitoring setup
- [Error Handling](error-handling.md) — Robust error handling
- [Environment Variables Reference](../reference/environment-variables.md)
