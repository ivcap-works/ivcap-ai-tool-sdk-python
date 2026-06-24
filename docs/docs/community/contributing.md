# Contributing

We welcome contributions to the IVCAP Lambda SDK!

## Getting Started

### 1. Fork and Clone

```bash
git clone https://github.com/YOUR_USERNAME/ivcap-ai-tool-sdk-python.git
cd ivcap-ai-tool-sdk-python
```

### 2. Set Up Development Environment

```bash
poetry install --with dev
```

### 3. Create a Branch

```bash
git checkout -b feature/my-feature
```

## Development Workflow

### Running Tests

```bash
poetry run pytest
poetry run pytest --cov=ivcap_lambda --cov-report=xml
```

### Code Quality

```bash
# Format code
poetry run ruff format .

# Lint
poetry run ruff check . --fix

# Type checking
poetry run mypy ivcap_lambda
```

### Building Documentation

```bash
cd docs
pip install -r requirements-docs.txt
mkdocs serve
```

Visit `http://localhost:8000` to preview the docs.

## Making Changes

### Code Changes

1. Make your changes in a feature branch
2. Add tests for new functionality
3. Ensure all tests pass: `poetry run pytest`
4. Update documentation as needed

### Documentation Changes

1. Edit files in `docs/docs/`
2. Test locally: `cd docs && mkdocs serve`
3. Check formatting and links
4. Submit pull request

## Commit Messages

Use clear, descriptive commit messages:

```
✨ feat: add new feature
🐛 fix: resolve bug
📝 docs: update documentation
🧪 test: add unit tests
🔨 chore: refactor code
```

## Pull Request Process

1. Update documentation
2. Add/update tests
3. Ensure CI passes
4. Create clear PR description
5. Link related issues

## Code Style

We use:

- **Ruff** — Linting and formatting
- **Mypy** — Type checking
- **Pytest** — Testing

### Style Guide

```python
# Docstrings follow Google style
def process(req: MyRequest, jobCtxt: JobContext) -> MyResult:
    """Process a request.

    Args:
        req: The request to process.
        jobCtxt: Job context for progress reporting.

    Returns:
        The processing result.

    Raises:
        ValueError: If validation fails.
    """
    pass

# Type hints required everywhere
def add(a: int, b: int) -> int:
    return a + b
```

## Testing

Write tests for new features:

```python
# tests/test_feature.py
import pytest
from ivcap_lambda import ivcap_lambda

def test_my_tool():
    from my_service import my_tool, MyRequest
    req = MyRequest(text="hello")
    result = my_tool(req)
    assert result.output == "HELLO"
```

## Documentation Guidelines

1. **Be clear** — Write for developers new to the SDK
2. **Include examples** — Every concept should have a code example
3. **Link between pages** — Use relative links
4. **Update mkdocs.yml** — If adding new pages

## Reporting Issues

### Bug Reports

Include:
- Minimal reproducible example
- Expected vs actual behavior
- Python version and `ivcap-lambda` version
- Traceback (if applicable)

### Feature Requests

Include:
- Use case and motivation
- Proposed API/syntax
- Any alternatives considered

## License

By contributing, you agree that your contributions will be licensed under the same [BSD License](https://github.com/ivcap-works/ivcap-ai-tool-sdk-python/blob/main/LICENSE) as the project.

---

Thank you for contributing to IVCAP! 🚀
