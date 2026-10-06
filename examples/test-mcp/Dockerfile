ARG BUILD_PLATFORM=linux/amd64
FROM --platform=${BUILD_PLATFORM} python:3.11-slim-bookworm

WORKDIR /app
COPY pyproject.toml ./
# Install poetry, patch local dev deps → PyPI versions, install deps, then remove poetry
RUN pip install poetry \
  && sed -i 's|ivcap-lambda = {path = "../..", develop = true, extras = \["mcp"\]}|ivcap-lambda = {version = ">=0.7.22,<0.8.0", extras = ["mcp"]}|' pyproject.toml \
  && sed -i '/^ivcap-service = {path = /d' pyproject.toml \
  && poetry config virtualenvs.create false \
  && poetry install --no-root \
  && pip uninstall -y poetry

COPY mcp-service.py ./

# VERSION INFORMATION
ARG VERSION=???
ENV VERSION=$VERSION
ENV PORT=80

# Command to run
ENTRYPOINT ["python",  "/app/mcp-service.py"]
