from typing import AsyncGenerator, Dict, Optional, Tuple
from fastapi import FastAPI, Path, Request, Header, Response
from fastapi.responses import JSONResponse, StreamingResponse
import json
import os
import uvicorn
import httpx

app = FastAPI()

TEST_LOAD_PATH = os.path.join(os.path.dirname(__file__), "test_request.json")

from fastapi import Header

@app.middleware("http")
async def decode_path(request: Request, call_next):
    path = request.url.path
    if path.startswith("//ivcap.minikube"):
        p = path[len('//ivcap.minikube'):]
        request.scope["path"] = p
    response = await call_next(request)
    return response

@app.get("/next_job")
async def next_job():
    try:
        with open(TEST_LOAD_PATH, "r") as f:
            content = json.load(f)
        headers = {"job-id": "0000-0000", "Authorization": "Bearer xxxxx"}
        return JSONResponse(content, headers=headers)
    except FileNotFoundError:
        return JSONResponse({"error": "test_load.json not found"}, status_code=404)

@app.post("/results/{job_id}")
async def results(job_id: str, request: Request):
    data = await request.json()
    print(f"Received results for job_id: {job_id}")
    print("Headers:")
    for key, value in request.headers.items():
        print(f"  {key}: {value}")
    print("Data:")
    print(json.dumps(data, indent=4))
    return {"status": "received"}

SAFE_HEADERS = {
    "content-type",
    "content-encoding",
    "content-length",
    "etag",
    "cache-control",
    "last-modified",
    "expires",
    "vary"
}

@app.get("/proxy")
async def proxy_get(request: Request, ivcap_forward_url: str = Header(None), ivcap_job_id: str = Header(None)):
    """
    Proxies a GET request to the URL specified in the X-Proxy-Url header.
    """
    if not ivcap_forward_url:
        return JSONResponse({"error": "Ivcap-Forward-Url header is required"}, status_code=400)

    headers_to_forward = {}
    for key, value in request.headers.items():
        if key.lower() not in ("ivcap-forward-url", "ivcap-job-id", "host"):
            headers_to_forward[key] = value

    print(f"Proxying request for {ivcap_job_id} to: '{ivcap_forward_url}' with headers: {headers_to_forward}")

    async with httpx.AsyncClient() as client:
        async with client.stream("GET", ivcap_forward_url, headers=headers_to_forward) as upstream:
            # ⚠️ this bypasses automatic decompression
            content = b"".join([chunk async for chunk in upstream.aiter_raw()])
            # Filter headers
            headers = {
                k: v for k, v in upstream.headers.items()
                if k.lower() in SAFE_HEADERS
            }

            return Response(content=content, headers=headers, status_code=upstream.status_code)

@app.post("/proxy")
async def proxy_post(request: Request, ivcap_forward_url: str = Header(None), ivcap_job_id: str = Header(None)):
    """
    Proxies a GET request to the URL specified in the X-Proxy-Url header.
    """
    if not ivcap_forward_url:
        return JSONResponse({"error": "Ivcap-Forward-Url header is required"}, status_code=400)

    headers_to_forward = {}
    for key, value in request.headers.items():
        if key.lower() not in ("ivcap-forward-url", "ivcap-job-id", "host"):
            headers_to_forward[key] = value

    print(f"Proxying request for {ivcap_job_id} to: '{ivcap_forward_url}' with headers: {headers_to_forward}")
    body = await request.body()  # Await the body and store it
    async with httpx.AsyncClient() as client:
        async with client.stream("POST", ivcap_forward_url, data=body, headers=headers_to_forward) as upstream:
            # ⚠️ this bypasses automatic decompression
            content = b"".join([chunk async for chunk in upstream.aiter_raw()])
            # Filter headers
            headers = {
                k: v for k, v in upstream.headers.items()
                if k.lower() in SAFE_HEADERS
            }

            return Response(content=content, headers=headers, status_code=upstream.status_code)

#app.get("/proxy")(proxy)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9999)
