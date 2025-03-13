#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#

import inspect
import os
from typing import Any, Callable, Optional, get_type_hints
from typing import (
    Any,
    Callable,
    Optional,
    Tuple,
    Union,
)
from pydantic import BaseModel, Field

from .utils import _get_input_type
from .executor import ExecutionContext

TOOL_SCHEMA = "urn:sd-core:schema.ai-tool.1"

SERVICE_ID_PLACEHOLDER = "#SERVICE_ID#"

class ToolDefinition(BaseModel):
    jschema: str = Field(default=TOOL_SCHEMA, alias="$schema")
    id: str

    model_config = {
        "populate_by_name": True,
    }
    name: str
    service_id: str = Field(alias="service-id")
    description: str
    fn_signature: str
    fn_schema: dict

def print_tool_definition(
    fn: Callable[..., Any],
    *,
    service_id: Optional[str] = None,
    description: Optional[str] = None,
    id_prefix: str = "urn:sd-core:ai-tool",
) -> ToolDefinition:
    td = create_tool_definition(fn, service_id=service_id, description=description, id_prefix=id_prefix)
    print(td.model_dump_json(indent=2, by_alias=True))

def create_tool_definition(
    fn: Callable[..., Any], *,
    service_id: Optional[str] = None,
    description: Optional[str] = None,
    id_prefix: str = "urn:sd-core:ai-tool",
) -> ToolDefinition:
    name = fn.__name__
    signature, description = _generate_function_description(fn, name, exclude_types=[ExecutionContext])

    if service_id == None:
        service_id = os.getenv("IVCAP_SERVICE_ID")
    if service_id == None:
        service_id = SERVICE_ID_PLACEHOLDER

    #fn_sig = inspect.signature(fn)
    input_type, _ = _get_input_type(fn)

    td = ToolDefinition(
        id=f"{id_prefix}.{name}",
        name=name,
        service_id=service_id,
        description=description,
        fn_signature=signature,
        fn_schema=input_type.model_json_schema(),
    )
    return td

def _generate_function_description(func: Callable, name: Optional[str] = None, exclude_types: Optional[list] = None) -> Tuple[str, str]:
    """Generates a function description with argument descriptions and return values from a function with a Pydantic argument.

    The function description assumes that all fields in the Pydantic argument are provided as "normal" function arguments.
    This is useful for generating documentation for functions that use Pydantic models, as it makes the function signature
    more readable by showing the individual fields of the Pydantic model as separate arguments.

    Args:
        func: The function to generate a description for. The function should have at least one Pydantic model as an argument.
        name: Optional name to override the function's actual name.
        exclude_types: Optional list of types to exclude from the function description. Any subtypes of these types will also be excluded.

    Returns:
        A tuple containing:
        - The function signature as a string.
        - The rest of the function description, including the docstring, argument descriptions, and return type.
    """
    if exclude_types is None:
        exclude_types = []

    def is_excluded_type(param_type):
        """Check if a type should be excluded based on the exclude_types list."""
        if not exclude_types:
            return False

        # Check if the type is in the exclude_types list
        if param_type in exclude_types:
            return True

        # Check if the type is a subclass of any type in the exclude_types list
        for exclude_type in exclude_types:
            # Only check issubclass if both types are classes
            if (isinstance(param_type, type) and isinstance(exclude_type, type) and
                issubclass(param_type, exclude_type)):
                return True

        return False
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

    if not pydantic_model_class:
        error_msg = "Function does not have a Pydantic model as an argument."
        return ("", error_msg)

    model_schema = pydantic_model_class.schema()

    # Start with the function's docstring
    description = func.__doc__ or ""

    # Create a new function signature with the Pydantic fields as arguments
    function_name = name if name is not None else func.__name__
    new_signature = f"{function_name}("

    # Collect all parameters
    all_params = []

    # Add non-Pydantic parameters first
    for param_name, param in signature.parameters.items():
        if param_name != pydantic_param_name:
            param_type = type_hints.get(param_name, Any)
            # Skip if the type is in the exclude_types list or is a subtype of an excluded type
            if is_excluded_type(param_type) or param_name in exclude_types:
                continue
            param_type_name = param_type.__name__ if hasattr(param_type, '__name__') else str(param_type)
            all_params.append(f"{param_name}: {param_type_name}")

    # Add Pydantic fields
    for field_name, field_info in model_schema['properties'].items():
        # Skip if the field name is "$schema"
        if field_name == "$schema":
            continue
        # Skip if the field name is in the exclude_types list
        if field_name in exclude_types:
            continue
        # Get the correct type from the Pydantic model
        field_type = field_info.get('type', None)

        # If type is not available in the schema, try to get it from the model's __annotations__
        if field_type is None and hasattr(pydantic_model_class, '__annotations__'):
            annotation = pydantic_model_class.__annotations__.get(field_name)
            if annotation is not None:
                if hasattr(annotation, '__origin__') and annotation.__origin__ is Union:
                    # Handle Optional types (Union[type, NoneType])
                    args = annotation.__args__
                    if len(args) == 2 and args[1] is type(None):
                        field_type = args[0].__name__
                        is_optional = True
                    else:
                        field_type = str(annotation).replace('typing.', '')
                else:
                    field_type = annotation.__name__ if hasattr(annotation, '__name__') else str(annotation)
            else:
                field_type = 'Any'
        else:
            # Handle optional fields
            is_optional = False
            if 'default' in field_info or field_name not in model_schema.get('required', []):
                is_optional = True

            # Map JSON schema types to Python types
            if field_type == 'string':
                field_type = 'str'
            elif field_type == 'integer':
                field_type = 'int'
            elif field_type == 'number':
                field_type = 'float'
            elif field_type == 'boolean':
                field_type = 'bool'
            elif field_type == 'array':
                # Handle array types with their item types
                items = field_info.get('items', {})
                item_type = items.get('type', 'Any')
                # Map item type to Python types
                if item_type == 'string':
                    item_type = 'str'
                elif item_type == 'integer':
                    item_type = 'int'
                elif item_type == 'number':
                    item_type = 'float'
                elif item_type == 'boolean':
                    item_type = 'bool'
                field_type = f"array[{item_type}]"
            elif field_type is None:
                field_type = 'Any'

        # Add Optional[] for optional fields
        if is_optional and not field_type.startswith('Optional['):
            field_type = f"Optional[{field_type}]"

        all_params.append(f"{field_name}: {field_type}")

    # Join all parameters with commas
    new_signature += ", ".join(all_params)
    new_signature += ")"

    # Add return type
    return_type = type_hints.get('return', 'unknown')
    if hasattr(return_type, '__name__'):
        return_type_str = return_type.__name__
    else:
        return_type_str = str(return_type)
    new_signature += f" -> {return_type_str}"

    description = f"{new_signature}\n\n{description}\n\nArguments:\n"

    # Add non-Pydantic parameters first with their descriptions
    for param_name, param in signature.parameters.items():
        if param_name == "$schema":
            continue
        if param_name != pydantic_param_name:
            param_type = type_hints.get(param_name, Any)
            # Skip if the type is in the exclude_types list or is a subtype of an excluded type
            if is_excluded_type(param_type) or param_name in exclude_types:
                continue
            param_type_name = param_type.__name__ if hasattr(param_type, '__name__') else str(param_type)
            description += f"  {param_name}: {param_type_name}\n"

    # Add Pydantic fields with their descriptions
    for field_name, field_info in model_schema['properties'].items():
        if field_name == "$schema":
            continue
        # Skip if the field name is in the exclude_types list
        if field_name in exclude_types:
            continue
        # Get the correct type from the Pydantic model
        field_type = field_info.get('type', None)

        # If type is not available in the schema, try to get it from the model's __annotations__
        if field_type is None and hasattr(pydantic_model_class, '__annotations__'):
            annotation = pydantic_model_class.__annotations__.get(field_name)
            if annotation is not None:
                if hasattr(annotation, '__origin__') and annotation.__origin__ is Union:
                    # Handle Optional types (Union[type, NoneType])
                    args = annotation.__args__
                    if len(args) == 2 and args[1] is type(None):
                        field_type = args[0].__name__
                        is_optional = True
                    else:
                        field_type = str(annotation).replace('typing.', '')
                else:
                    field_type = annotation.__name__ if hasattr(annotation, '__name__') else str(annotation)
            else:
                field_type = 'Any'
        else:
            # Handle optional fields
            is_optional = False
            if 'default' in field_info or field_name not in model_schema.get('required', []):
                is_optional = True

            # Map JSON schema types to Python types
            if field_type == 'string':
                field_type = 'str'
            elif field_type == 'integer':
                field_type = 'int'
            elif field_type == 'number':
                field_type = 'float'
            elif field_type == 'boolean':
                field_type = 'bool'
            elif field_type == 'array':
                # Handle array types with their item types
                items = field_info.get('items', {})
                item_type = items.get('type', 'Any')
                # Map item type to Python types
                if item_type == 'string':
                    item_type = 'str'
                elif item_type == 'integer':
                    item_type = 'int'
                elif item_type == 'number':
                    item_type = 'float'
                elif item_type == 'boolean':
                    item_type = 'bool'
                field_type = f"array[{item_type}]"
            elif field_type is None:
                field_type = 'Any'

        # Add Optional[] for optional fields
        if is_optional and not field_type.startswith('Optional['):
            field_type = f"Optional[{field_type}]"

        description += f"  {field_name}: {field_type}"
        if 'description' in field_info:
            description += f" - {field_info['description']}"
        # Add default value information if available
        if 'default' in field_info:
            default_value = field_info['default']
            description += f" (Defaults to {default_value})"
        description += "\n"

    # Add a note about the return type
    description += f"\nReturns: {return_type_str}"

    # Split the description into signature and the rest
    signature_part = new_signature
    rest_part = description.replace(new_signature, "", 1).strip()

    return (signature_part, rest_part)

# def create_tool_definition(
#     fn: Callable[..., Any],
#     name: Optional[str] = None,
#     description: Optional[str] = None
# ) -> ToolDefinition:
#     fn_to_parse = fn
#     name = name or fn_to_parse.__name__
#     description = description or fn_to_parse.__doc__

#     fn_sig = inspect.signature(fn_to_parse)

#     # Handle FieldInfo defaults
#     def r(param):
#         if isinstance(param.default, FieldInfo):
#             return param.replace(default=inspect.Parameter.empty)
#         else:
#             return param
#     fn_sig = fn_sig.replace(parameters=[r(param) for param in fn_sig.parameters.values()])

#     fn_signature = f"{name}{fn_sig}"
#     fn_schema = create_schema_from_function(name, fn_to_parse)
#     return ToolDefinition(
#         id=f"urn:sd-core:ai-tool:{name}",
#         name=name,
#         description=description,
#         fn_signature=fn_signature,
#         fn_schema=fn_schema.model_json_schema(by_alias=False))

# def create_schema_from_function(
#     name: str,
#     func: Union[Callable[..., Any], Callable[..., Awaitable[Any]]],
#     additional_fields: Optional[
#         List[Union[Tuple[str, Type, Any], Tuple[str, Type]]]
#     ] = None,
#     ignore_fields: Optional[List[str]] = None,
# ) -> Type[BaseModel]:
#     """Create schema from function."""
#     fields = {}
#     ignore_fields = ignore_fields or []
#     params = inspect.signature(func).parameters
#     for param_name in params:
#         if param_name in ignore_fields:
#             continue

#         param_type = params[param_name].annotation
#         param_default = params[param_name].default
#         description = None

#         if get_origin(param_type) is typing.Annotated:
#             args = get_args(param_type)
#             param_type = args[0]
#             if isinstance(args[1], str):
#                 description = args[1]

#         if param_type is params[param_name].empty:
#             param_type = Any

#         if param_default is params[param_name].empty:
#             # Required field
#             fields[param_name] = (param_type, FieldInfo(description=description))
#         elif isinstance(param_default, FieldInfo):
#             # Field with pydantic.Field as default value
#             fields[param_name] = (param_type, param_default)
#         else:
#             fields[param_name] = (
#                 param_type,
#                 FieldInfo(default=param_default, description=description),
#             )

#     additional_fields = additional_fields or []
#     for field_info in additional_fields:
#         if len(field_info) == 3:
#             field_info = cast(Tuple[str, Type, Any], field_info)
#             field_name, field_type, field_default = field_info
#             fields[field_name] = (field_type, FieldInfo(default=field_default))
#         elif len(field_info) == 2:
#             # Required field has no default value
#             field_info = cast(Tuple[str, Type], field_info)
#             field_name, field_type = field_info
#             fields[field_name] = (field_type, FieldInfo())
#         else:
#             raise ValueError(
#                 f"Invalid additional field info: {field_info}. "
#                 "Must be a tuple of length 2 or 3."
#             )

#     return create_model(name, **fields)  # type: ignore
