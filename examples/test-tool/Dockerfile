FROM python:3.11-slim-bookworm

# Install the latest published ivcap-lambda and ivcap-service releases (see
# Dockerfile.local for building from the current source tree instead).
RUN pip install --no-cache-dir \
  "ivcap-lambda[mcp]>=0.8.3,<0.9.0" \
  "ivcap-service>=0.7.0,<0.8.0" \
  "openai>=1.95.1,<2.0.0"

WORKDIR /app
COPY tool-service.py ./

# VERSION INFORMATION
ARG VERSION=???
ENV VERSION=$VERSION
ENV PORT=80

# Command to run
ENTRYPOINT ["python",  "/app/tool-service.py"]
