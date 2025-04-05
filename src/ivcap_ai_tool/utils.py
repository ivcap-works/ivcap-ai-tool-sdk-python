#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
import inspect
import os
import re
from typing import Optional, Type, Callable, TypeVar, Any, get_type_hints, Union, Dict, Tuple

from pydantic import BaseModel, HttpUrl


def _get_title_from_path(path: str) -> Tuple[str, str]:
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


def _get_input_type(func: Callable) -> Tuple[Optional[Type[BaseModel]], Dict[str, Any]]:
    """Gets the input type of a function.

    Args:
        func: The function to get the input type for.

    Returns:
        A tuple containing:
        - The first function parameter which is a derived class of a pydantic BaseModel, or None if no such parameter exists.
        - A dictionary of all additional parameters, where the key is the parameter name and the value is the type.
    """
    signature = inspect.signature(func)
    type_hints = get_type_hints(func)

    # Get the Pydantic model class
    pydantic_model_class = None
    pydantic_param_name = None
    for param_name, param in signature.parameters.items():
        if hasattr(param.annotation, '__mro__') and BaseModel in param.annotation.__mro__:
            pydantic_model_class = param.annotation
            pydantic_param_name = param_name
            break

    # Get all additional parameters
    additional_params = {}
    for param_name, param in signature.parameters.items():
        if param_name != pydantic_param_name:
            param_type = type_hints.get(param_name, Any)
            additional_params[param_name] = param_type

    return pydantic_model_class, additional_params

def _get_function_return_type(func):
    """Extracts the return type from a function."""
    type_hints = get_type_hints(func)
    # param_types = {k: v for k, v in type_hints.items() if k != 'return'}
    return_type = type_hints.get('return')
    # return param_types, return_type
    return return_type


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
from typing import Optional, Type, Callable, TypeVar, Any, get_type_hints, Union, Dict, Tuple
from urllib.parse import unquote, urlparse

from pydantic import BaseModel

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

def get_ivcap_url() -> HttpUrl:
    """
    Returns the sidecar URL from the request headers.
    """
    return urlparse(os.getenv("IVCAP_BASE_URL"))
