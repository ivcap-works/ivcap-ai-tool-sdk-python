# MCP & Agent Integration Guide

Lambda services can expose a [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) endpoint that makes your tools directly callable by AI agent frameworks such as Claude, Cursor, Copilot, and others.

## What is MCP?

The Model Context Protocol is an open standard that lets AI models discover and call tools via a standardised interface. By enabling the MCP endpoint, your IVCAP lambda service becomes a first-class tool provider for any MCP-compatible agent framework.

## Enabling the MCP Endpoint

Pass `--with-mcp` when starting the server:

```bash
python my_service.py --with-mcp --port 8090
```

This registers a `/mcp` endpoint on the running FastAPI app. The endpoint speaks the MCP protocol and exposes all registered `@ivcap_lambda` tools automatically.

## Tool Description Endpoints

Even without `--with-mcp`, each tool has a `GET` endpoint that returns a description:

```bash
# Get tool description at the tool's path
curl http://localhost:8090/greet
```

This returns a JSON description suitable for agent frameworks that consume OpenAPI-style tool definitions. The description is generated from the function's docstring, Pydantic model fields, and `ToolOptions`.

## Configuring the Service ID

When AI agents call your tool, they need a stable service ID to identify where to send follow-up requests. Set `service_id` in `ToolOptions` to a path; the server will prepend the public URL prefix automatically:

```python
@ivcap_lambda("/greet", opts=ToolOptions(tags=["Greeter"], service_id="/greet"))
def greet(req: GreetRequest) -> GreetResult:
    """Greet a person

    Generates a personalised greeting.
    """
    ...
```

If the service is running behind a reverse proxy with the `X-Forwarded-For` or `X-Forwarded-Proto` headers, the public URL is detected automatically.

## Writing Good Tool Descriptions

AI agents use the docstring to decide when and how to call your tool. Follow these conventions for maximum agent compatibility:

```python
@ivcap_lambda("/analyse-sentiment", opts=ToolOptions(tags=["NLP"]))
def analyse_sentiment(req: SentimentRequest) -> SentimentResult:
    """Analyse the sentiment of a piece of text

    Given an input string, this tool returns a sentiment label
    (positive, negative, or neutral) and a confidence score between 0 and 1.

    Use this tool when you need to determine the emotional tone of user-provided
    text, product reviews, social media posts, or any other natural-language input.

    The tool processes text in English only. For multilingual text, pre-translate
    to English first.
    """
    ...
```

Key points:
- **First paragraph** — one-line summary (used as the OpenAPI endpoint summary)
- **Body** — detailed description of what the tool does, when to use it, and any constraints
- **Field descriptions** — every request and result field must have a clear `description` in `Field()`

## Connecting an MCP Client

### Claude Desktop

Add to your Claude Desktop configuration (`~/.claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "my-lambda-service": {
      "command": "python",
      "args": ["my_service.py", "--with-mcp"]
    }
  }
}
```

### MCP Inspector (for development)

The [MCP Inspector](https://github.com/modelcontextprotocol/inspector) lets you test MCP endpoints interactively:

```bash
npx @modelcontextprotocol/inspector http://localhost:8090/mcp
```

### Custom MCP Client

Connect to the MCP endpoint via HTTP SSE:

```python
from mcp import ClientSession
from mcp.client.sse import sse_client

async def run():
    async with sse_client("http://localhost:8090/mcp") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(tools)
```

## Example: MCP-Ready Service

```python
from pydantic import BaseModel, Field
from ivcap_service import Service, ServiceContact, with_schema
from ivcap_lambda import start_lambda_server, ivcap_lambda, ToolOptions, logging_init

logging_init()

service = Service(
    name="NLP Tools",
    contact=ServiceContact(name="Dev Team", email="dev@example.com"),
)


@with_schema("urn:example:schema:word-count.request.1")
class WordCountRequest(BaseModel):
    text: str = Field(..., description="The text to count words in.")


@with_schema("urn:example:schema:word-count.1")
class WordCountResult(BaseModel):
    word_count: int = Field(..., description="Number of words in the text.")
    char_count: int = Field(..., description="Number of characters in the text.")


@ivcap_lambda("/word-count", opts=ToolOptions(tags=["NLP"], service_id="/word-count"))
def word_count(req: WordCountRequest) -> WordCountResult:
    """Count words and characters in a piece of text

    Returns the word count and character count of the provided text.
    Use this tool when you need to check text length constraints or
    estimate reading time for a given piece of content.
    """
    return WordCountResult(
        word_count=len(req.text.split()),
        char_count=len(req.text),
    )


if __name__ == "__main__":
    start_lambda_server(service)
```

Start with MCP enabled:

```bash
python my_service.py --with-mcp --port 8090
```

## See Also

- [Tool Functions Guide](tool-functions.md) — Writing good tool functions
- [Best Practices](best-practices.md) — Docstring and naming conventions
- [MCP Protocol Specification](https://modelcontextprotocol.io/specification)
- [`start_lambda_server` API](../api/server.md)
