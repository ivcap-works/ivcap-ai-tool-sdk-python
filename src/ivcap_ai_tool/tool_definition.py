#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#

import inspect
from typing import Any, Callable, Optional
from typing import (
    Any,
    Awaitable,
    Callable,
    List,
    Optional,
    Tuple,
    Type,
    Union,
    cast,
    get_origin,
    get_args,
)
import typing
from pydantic import BaseModel, Field, create_model
from pydantic.fields import FieldInfo


TOOL_SCHEMA = "urn:sd-core:schema:ai-tool.1"

class ToolDefinition(BaseModel):
    jschema: str = Field(default=TOOL_SCHEMA, alias="$schema")
    id: str
    name: str
    service_id: str = Field(default="#SERVICE_ID#", alias="service-id")
    description: str
    fn_signature: str
    fn_schema: dict

def print_tool_definition(fn: Callable[..., Any], *, name: Optional[str] = None, description: Optional[str] = None) -> ToolDefinition:
    td = create_tool_definition(fn, name, description)
    print(td.model_dump_json(indent=2, by_alias=True))

def create_tool_definition(fn: Callable[..., Any], name: Optional[str] = None, description: Optional[str] = None) -> ToolDefinition:
    fn_to_parse = fn
    name = name or fn_to_parse.__name__
    description = description or fn_to_parse.__doc__

    fn_sig = inspect.signature(fn_to_parse)

    # Handle FieldInfo defaults
    def r(param):
        if isinstance(param.default, FieldInfo):
            return param.replace(default=inspect.Parameter.empty)
        else:
            return param
    fn_sig = fn_sig.replace(parameters=[r(param) for param in fn_sig.parameters.values()])

    fn_signature = f"{name}{fn_sig}"
    fn_schema = create_schema_from_function(name, fn_to_parse)
    return ToolDefinition(
        id=f"urn:sd-core:ai-tool:{name}",
        name=name,
        description=description,
        fn_signature=fn_signature,
        fn_schema=fn_schema.model_json_schema(by_alias=False))

def create_schema_from_function(
    name: str,
    func: Union[Callable[..., Any], Callable[..., Awaitable[Any]]],
    additional_fields: Optional[
        List[Union[Tuple[str, Type, Any], Tuple[str, Type]]]
    ] = None,
    ignore_fields: Optional[List[str]] = None,
) -> Type[BaseModel]:
    """Create schema from function."""
    fields = {}
    ignore_fields = ignore_fields or []
    params = inspect.signature(func).parameters
    for param_name in params:
        if param_name in ignore_fields:
            continue

        param_type = params[param_name].annotation
        param_default = params[param_name].default
        description = None

        if get_origin(param_type) is typing.Annotated:
            args = get_args(param_type)
            param_type = args[0]
            if isinstance(args[1], str):
                description = args[1]

        if param_type is params[param_name].empty:
            param_type = Any

        if param_default is params[param_name].empty:
            # Required field
            fields[param_name] = (param_type, FieldInfo(description=description))
        elif isinstance(param_default, FieldInfo):
            # Field with pydantic.Field as default value
            fields[param_name] = (param_type, param_default)
        else:
            fields[param_name] = (
                param_type,
                FieldInfo(default=param_default, description=description),
            )

    additional_fields = additional_fields or []
    for field_info in additional_fields:
        if len(field_info) == 3:
            field_info = cast(Tuple[str, Type, Any], field_info)
            field_name, field_type, field_default = field_info
            fields[field_name] = (field_type, FieldInfo(default=field_default))
        elif len(field_info) == 2:
            # Required field has no default value
            field_info = cast(Tuple[str, Type], field_info)
            field_name, field_type = field_info
            fields[field_name] = (field_type, FieldInfo())
        else:
            raise ValueError(
                f"Invalid additional field info: {field_info}. "
                "Must be a tuple of length 2 or 3."
            )

    return create_model(name, **fields)  # type: ignore
