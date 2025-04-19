import os
from typing import Optional, Dict
from http import HTTPStatus
import httpx

def file_to_http_response(
    file_path: str,
    headers: Optional[Dict[str, str]] = None,
    status_code: int = 200,
) -> httpx.Response:
    """
    Reads data from a file and returns it as an httpx.Response object.

    Args:
        file_path: The path to the file to read.
        headers: Optional dictionary of HTTP headers to include in the response.
        status_code: The HTTP status code to return (e.g., 200, 404, 500).
        status_message: Optional HTTP status message. If None, the default
            message for the status_code is used.

    Returns:
        An httpx.Response object containing the file data and response information.
    """
    # Sanity checks
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    if not os.path.isfile(file_path):
        raise ValueError(f"Not a file: {file_path}")
    if status_code < 100 or status_code > 599:
        raise ValueError(f"Invalid HTTP status code: {status_code}")

    # Default headers
    default_headers = {
        "Content-Type": "application/octet-stream",  # Default content type
        "Content-Length": str(os.path.getsize(file_path)),
    }

    # Combine default and user-provided headers
    combined_headers = default_headers.copy()
    if headers:
        combined_headers.update(headers) # Use update for simpler merging

    # Read the file data
    try:
        with open(file_path, "rb") as file:
            file_data = file.read()
    except Exception as e:
        raise IOError(f"Error reading file: {file_path}: {e}")

    # Create an httpx.Response object
    response = httpx.Response(
        status_code=status_code,
        content=file_data,
        headers=combined_headers,
    )

    return response