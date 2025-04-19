ARG BUILD_PLATFORM=linux/amd64
FROM --platform=${BUILD_PLATFORM} python:3.12.9-slim-bookworm AS builder

# RUN apt-get update && apt-get install -y \
#   build-essential \
#   python3-dev \
#   python3-pip

WORKDIR /app
RUN pip install -U pip
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Get service files
ADD batch_service.py  ./
ADD server.py  ivcap.py ./

# VERSION INFORMATION
ARG VERSION ???
ENV VERSION=$VERSION

# Command to run
ENTRYPOINT ["python",  "/app/batch_service.py"]
