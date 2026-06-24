#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
from typing import Optional, Dict, Tuple

def get_title_from_path(path: str) -> Tuple[str, str]:
    """Extracts a title from a path string.

    Args:
        path: A string potentially formatted as a directory path (separated by '/').

    Returns:
        A tuple containing:
        - The processed string with the first character in lowercase.
        - The processed string with the first character in uppercase.
    """
    # Extract the last element of the path
    last_element = path.split('/')[-1]

    # Convert to singular form if plural
    singular = last_element
    if singular.endswith('ies'):
        singular = singular[:-3] + 'y'
    elif singular.endswith('es'):
        singular = singular[:-2]
    elif singular.endswith('ss'):
        pass
    elif singular.endswith('s'):
        singular = singular[:-1]

    # Replace underscores with spaces
    singular = singular.replace('_', ' ')

    # Create lowercase and uppercase versions
    if singular:
        lowercase = singular[0].lower() + singular[1:] if len(singular) > 1 else singular.lower()
        uppercase = singular[0].upper() + singular[1:] if len(singular) > 1 else singular.upper()
    else:
        lowercase = ""
        uppercase = ""

    return (lowercase, uppercase)

def find_first(iterable, condition):
    """
    Returns the first item in the iterable for which the condition is True.
    If no such item is found, returns None.
    """
    for item in iterable:
        if condition(item):
            return item
    return None

from fastapi import Request
from typing import Optional, Dict, Tuple


def get_public_url_prefix(req: Request) -> str:
    """Return the public url prefix for `req`.

    First checks for a `Forwarded` http header and if
    absent uses the request's `base_ur;` variable.

    Args:
        req (Request): A FastAPI request instance

    Returns:
        str: A url as string
    """
    fw = get_forwarded_header(req)
    if fw != None:
        prefix = f"{fw.get('proto', 'http')}:://{fw.get('for')}"
    else:
        prefix = str(req.base_url).rstrip("/")
    return prefix


def get_forwarded_header(request: Request) -> Optional[Dict[str, str]]:
    """
    Parses the "Forwarded" HTTP header according to RFC 7239.
    Returns a dictionary containing the parsed header values, or None if the header is missing.
    """
    header_value = request.headers.get("Forwarded")
    if not header_value:
        return None

    parsed_values: Dict[str, str] = {}
    for element in header_value.split(";"):
        parts = element.split("=", 1)
        if len(parts) == 2:
            key = parts[0].strip()
            value = parts[1].strip()
            # Remove quotes if present
            if value.startswith('"') and value.endswith('"'):
                value = value[1:-1]
            parsed_values[key] = value

    return parsed_values
