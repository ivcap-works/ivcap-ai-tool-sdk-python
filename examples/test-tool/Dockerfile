ARG BUILD_PLATFORM=linux/amd64
FROM --platform=${BUILD_PLATFORM} python:3.11-slim-bookworm

WORKDIR /app
COPY pyproject.toml ./
# Install poetry, patch local dev dep → PyPI version, install deps, then remove poetry
RUN pip install poetry \
  && sed -i 's|ivcap-lambda = {path = "../..", develop = true}|ivcap-lambda = ">=0.7.22,<0.8.0"|' pyproject.toml \
  && poetry config virtualenvs.create false \
  && poetry install --no-root \
  && pip uninstall -y poetry

COPY tool-service.py wordle.py ./

# VERSION INFORMATION
ARG VERSION=???
ENV VERSION=$VERSION
ENV PORT=80

# Command to run
ENTRYPOINT ["python",  "/app/tool-service.py"]
