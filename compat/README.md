# ⚠️ THIS PACKAGE IS DEPRECATED ⚠️

> **This package (`ivcap-ai-tool`) has been renamed to [`ivcap-lambda`](https://pypi.org/project/ivcap-lambda/).**
>
> 🚨 **Please uninstall `ivcap-ai-tool` and install `ivcap-lambda` instead:**
>
> ```bash
> pip uninstall ivcap-ai-tool
> pip install ivcap-lambda
> ```
>
> This package is a compatibility shim only and will receive **no further updates**.

---

## Why was it renamed?

The library has been renamed from `ivcap-ai-tool` → **`ivcap-lambda`** to better reflect its purpose and align with the IVCAP platform naming conventions.

## Migration

Replace your dependency and imports as follows:

| Old (deprecated) | New |
|---|---|
| `pip install ivcap-ai-tool` | `pip install ivcap-lambda` |
| `from ivcap_ai_tool import ...` | `from ivcap_lambda import ...` |
| `@ivcap_ai_tool(...)` | `@ivcap_lambda(...)` |
| `start_tool_server(...)` | `start_lambda_server(...)` |

### Example

```python
# Old (deprecated)
from ivcap_ai_tool import start_tool_server, ivcap_ai_tool, ToolOptions

# New
from ivcap_lambda import start_lambda_server, ivcap_lambda, ToolOptions
```

## Compatibility

Installing `ivcap-ai-tool` automatically pulls in `ivcap-lambda` as a dependency. The `ivcap_ai_tool` namespace is re-exported from `ivcap_lambda` so **existing code continues to work without changes** — you will see a `DeprecationWarning` at import time reminding you to migrate.

## Links

- 📦 **New package:** [ivcap-lambda on PyPI](https://pypi.org/project/ivcap-lambda/)
- 📖 **Documentation & source:** [GitHub](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python)
