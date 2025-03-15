# Various "patches" to maiontain context between incoming requests
# and calls to external services within a "session"
#
import functools
from logging import Logger
from ivcap_fastapi import getLogger
import os
from typing import Any

from fastapi import FastAPI

def otel_instrument(app: FastAPI, logger: Logger):
    endpoint = os.environ.get('OTEL_EXPORTER_OTLP_ENDPOINT')
    if endpoint == None:
        logger.warning("requested --with-telemetry but exporter is not defined")
    if os.environ.get("PYTHONPATH") == None:
            os.environ["PYTHONPATH"] = ""
    import opentelemetry.instrumentation.auto_instrumentation.sitecustomize # force internal settings
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    logger.info(f"instrumenting for endpoint {endpoint}")
    FastAPIInstrumentor.instrument_app(app)

    # Also instrumemt
    try:
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        RequestsInstrumentor().instrument()
    except ImportError:
        pass
    try:
        import httpx # checks if httpx library is even used by this tool
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
    except ImportError:
        pass

def extend_requests():
    from requests import Session, PreparedRequest

    logger = getLogger("app.request")

    # Save original function
    wrapped_send = Session.send

    @functools.wraps(wrapped_send)
    def _send(
        self: Session, request: PreparedRequest, **kwargs: Any
    ):
        logger.info(f"Intercepting request to {request.url}")
        _modify_headers(request.headers, request.url)
        # Call original method
        return wrapped_send(self, request, **kwargs)

    # Apply wrapper
    Session.send = _send

def _modify_headers(headers, url):
    from .executor import Executor

    headers["ivcap-job-id"] = Executor.job_id()
    auth = Executor.job_authorization()
    if auth != None and url == "http://ivcap.local":
        headers["authorization"] = auth

def extend_httpx():
    try:
        import httpx
    except ImportError:
        return
    from .executor import Executor
    logger = getLogger("app.httpx")

    # Save original function
    wrapped_request = httpx.Client.request

    @functools.wraps(wrapped_request)
    def _request(self, method, url, **kwargs):
        logger.info(f"Intercepting request to {url}")

        # Modify headers
        if "headers" not in kwargs:
            kwargs["headers"] = {}
        _modify_headers(kwargs["headers"], url)

        # Call original method
        return wrapped_request(self, method, url, **kwargs)

    # Apply wrapper
    httpx.Client.request = _request

def set_context():
    extend_requests()
    extend_httpx()