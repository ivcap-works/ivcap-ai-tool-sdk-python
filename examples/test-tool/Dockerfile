FROM python:3.10-slim-buster

RUN pip install poetry

WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false && poetry install --no-root

COPY tool-service.py wordle.py ./

# VERSION INFORMATION
ARG VERSION ???
ENV VERSION=$VERSION
ENV PORT=80

# Command to run
ENTRYPOINT ["python",  "/app/tool-service.py"]

# ARG BUILD_PLATFORM=linux/amd64
# FROM --platform=${BUILD_PLATFORM} python:3.12.9-slim-bookworm AS builder

# # RUN apt-get update && apt-get install -y \
# #   build-essential \
# #   python3-dev \
# #   python3-pip

# WORKDIR /app
# RUN pip install -U pip
# COPY requirements.txt ./
# RUN pip install -r requirements.txt

# # Get service files
# ADD tool-service.py  ./

# # VERSION INFORMATION
# ARG VERSION ???
# ENV VERSION=$VERSION

# # Command to run
# ENTRYPOINT ["python",  "/app/tool-service.py"]
