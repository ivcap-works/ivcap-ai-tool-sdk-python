#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
import os
from collections.abc import Callable
from typing import Any

from ivcap_service import (
    IMAGE_PLACEHOLDER,
    Resources,
    Service,
    ServiceDefinition,
    create_service_definition,
    find_command,
    find_resources_file,
)
from pydantic import BaseModel, Field

REST_CONTROLLER_SCHEMA = "urn:ivcap:schema.service.rest.1"

class RestController(BaseModel):
    jschema: str = Field(default=REST_CONTROLLER_SCHEMA, alias="$schema")
    path: str | None = Field(default=None, description="internal path of this tool's endpoint")
    image: str
    command: list[str] | str
    resources: Resources = Field(default_factory=Resources)

def print_rest_service_definition(
    service_description: Service,
    fn: Callable[..., Any],
    service_id: str | None = None,
    name: str | None = None,
    path: str | None = None,
):
    sd = create_rest_service_definition(
        service_description,
        fn,
        service_id=service_id,
        name=name,
        path=path,
    )
    print(sd.model_dump_json(indent=2, by_alias=True, exclude_none=True))

def create_rest_service_definition(
    service_description: Service,
    fn: Callable[..., Any],
    service_id: str | None = None,
    name: str | None = None,
    path: str | None = None,
) -> ServiceDefinition:
    # controller
    image = os.getenv("DOCKER_IMG", IMAGE_PLACEHOLDER)

    command = find_command()
    resources = find_resources_file()
    controller = RestController(path=path, image=image, command=command, resources=resources)
    if name is not None:
        service_description = service_description.model_copy(update={"name": name})
    return create_service_definition(service_description, fn, REST_CONTROLLER_SCHEMA, controller, service_id)
