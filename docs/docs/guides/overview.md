# Guides Overview

These guides provide deep dives into specific features and patterns for building IVCAP lambda services.

## Getting Started

If you're new to the SDK, start here:

1. **[Installation](../getting-started/installation.md)** — Set up the SDK
2. **[Quick Start](../getting-started/quick-start.md)** — 5-minute introduction
3. **[Your First Lambda Service](../getting-started/first-service.md)** — Build a real service

## Core Concepts

### [Tool Functions](tool-functions.md)

Learn how to define and register tools:
- Request/Result schemas with Pydantic
- The `@ivcap_lambda` decorator and `ToolOptions`
- Accessing `JobContext` and the FastAPI `Request`
- Async tool functions
- Try-later semantics for long-running calls

**Read this if:** You want to understand the fundamentals of building lambda tool handlers.

### [Working with Artifacts](artifacts.md)

Upload and download IVCAP artifacts:
- Downloading input artifacts
- Uploading results
- Handling file streams
- Working with collections

**Read this if:** Your tool processes or generates files.

### [MCP & Agent Integration](mcp.md)

Expose tools to AI agent frameworks:
- Enabling the MCP endpoint
- Using the `--with-mcp` flag
- Connecting MCP clients
- Tool description endpoints

**Read this if:** You want your tools to be directly callable by AI agents via the Model Context Protocol.

## Advanced Topics

### [Observability & Logging](observability.md)

Monitor your services:
- Structured logging with `getLogger` and `logging_init`
- Progress events and step reporting
- OpenObserve integration
- OpenTelemetry tracing with FastAPI

**Read this if:** You want comprehensive monitoring and debugging.

### [Error Handling](error-handling.md)

Build robust services:
- Exception handling patterns
- Reporting errors through the event system
- HTTP status codes returned
- Graceful degradation

**Read this if:** You need production-grade error handling.

### [Deployment](deployment.md)

Deploy to production:
- Docker containerization
- Environment configuration
- Service registration with IVCAP
- Kubernetes patterns

**Read this if:** You're ready to deploy your service.

### [Best Practices](best-practices.md)

Pro tips and patterns:
- Code organization
- Testing strategies
- Performance optimization
- Common pitfalls

**Read this if:** You want to write production-quality code.

## Learning Path

```
Installation
    ↓
Quick Start
    ↓
Your First Lambda Service
    ↓
Tool Functions
    ├→ Artifacts (if needed)
    ├→ MCP & Agent Integration (if needed)
    └→ Observability (if needed)
    ↓
Error Handling
    ↓
Deployment
    ↓
Best Practices
```

## Choose Your Own Path

- **I want to expose a tool to AI agents:** [Tool Functions](tool-functions.md) → [MCP & Agent Integration](mcp.md)
- **I need to process files:** [Artifacts](artifacts.md)
- **I want to monitor my service:** [Observability](observability.md)
- **I need robust error handling:** [Error Handling](error-handling.md)
- **I'm ready for production:** [Deployment](deployment.md) → [Best Practices](best-practices.md)

## See Also

- **[API Reference](../api/overview.md)** — Complete API documentation
- **[Examples](../examples/tool-service.md)** — Working code samples
- **[Reference](../reference/environment-variables.md)** — Configuration and schemas
