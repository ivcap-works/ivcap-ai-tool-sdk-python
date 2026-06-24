# Environment Variables Reference

Complete reference of all environment variables used by `ivcap-lambda` and the underlying `ivcap-service`.

## Server Configuration

### HOST
- **Type**: String
- **Default**: `0.0.0.0`
- **Description**: Bind address for the uvicorn server
- **Example**: `127.0.0.1`
- **CLI equivalent**: `--host`

### PORT
- **Type**: Integer
- **Default**: `8090`
- **Description**: Port the uvicorn server listens on
- **Example**: `8095`
- **CLI equivalent**: `--port`

### VERSION
- **Type**: String
- **Default**: `???`
- **Description**: Service version, returned by `/_healtz` and the Swagger UI
- **Example**: `1.2.3`

## IVCAP Platform

### IVCAP_BASE_URL
- **Type**: String
- **Description**: Base URL for the IVCAP platform (used by the sidecar reporter and IVCAP client)
- **Example**: `https://ivcap.example.com`

## OpenObserve Integration

### OPENOBSERVE_URL
- **Type**: String
- **Description**: Base URL for the OpenObserve instance
- **Example**: `https://observe.example.com`

### OPENOBSERVE_ORG
- **Type**: String
- **Description**: OpenObserve organisation name
- **Example**: `production`

### OPENOBSERVE_USERNAME
- **Type**: String
- **Description**: OpenObserve username for authentication
- **Example**: `service@example.com`

### OPENOBSERVE_TOKEN
- **Type**: String
- **Description**: OpenObserve API token
- **Example**: `zo_prod_...`

### OPENOBSERVE_ENABLE_LOGS
- **Type**: Boolean
- **Default**: `true`
- **Description**: Enable log export to OpenObserve
- **Values**: `true`, `false`, `1`, `0`

### OPENOBSERVE_ENABLE_METRICS
- **Type**: Boolean
- **Default**: `true`
- **Description**: Enable metrics export to OpenObserve
- **Values**: `true`, `false`, `1`, `0`

## OpenTelemetry Configuration

### OTEL_EXPORTER_OTLP_ENDPOINT
- **Type**: String
- **Description**: Custom OTLP endpoint for metrics and traces
- **Example**: `http://otel-collector:4318`

### OTEL_EXPORTER_OTLP_HEADERS
- **Type**: String
- **Description**: Custom headers for OTLP exports (comma-separated key=value pairs)
- **Example**: `Authorization=Bearer <token>,x-scope=service`

## Logging

### IVCAP_LOG_LEVEL
- **Type**: String
- **Default**: `INFO`
- **Description**: Global log level
- **Values**: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`

## Setting Variables

### Docker

```dockerfile
ENV VERSION="1.2.3"
ENV PORT="80"
ENV OPENOBSERVE_URL="https://observe.example.com"
```

### Docker Compose

```yaml
services:
  my-lambda-service:
    environment:
      VERSION: "1.2.3"
      PORT: "80"
      OPENOBSERVE_URL: https://observe.example.com
      OPENOBSERVE_ORG: production
```

### Kubernetes

```yaml
containers:
- name: my-lambda-service
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
```

### Command Line / Shell

```bash
export PORT=8095
export VERSION=dev
python my_service.py
```

## See Also

- [Deployment Guide](../guides/deployment.md)
- [Observability Guide](../guides/observability.md)
