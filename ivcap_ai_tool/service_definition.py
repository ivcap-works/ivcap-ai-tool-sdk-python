#
# Copyright (c) 2023 Commonwealth Scientific and Industrial Research Organisation (CSIRO). All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file. See the AUTHORS file for names of contributors.
#
import os
from typing import Callable, List, Any, Optional, Union
from pydantic import BaseModel, Field

from ivcap_service import Service, IMAGE_PLACEHOLDER, Resources, ServiceDefinition
from ivcap_service import create_service_definition, find_resources_file, find_command

REST_CONTROLLER_SCHEMA = "urn:ivcap:schema.service.rest.1"

class RestController(BaseModel):
    jschema: str = Field(default=REST_CONTROLLER_SCHEMA, alias="$schema")
    image: str
    command: Union[List[str], str]
    resources: Resources = Field(default_factory=Resources)

def print_rest_service_definition(
    service_description: Service,
    fn: Callable[..., Any],
    service_id: Optional[str] = None,
):
    sd = create_rest_service_definition(
        service_description,
        fn,
        service_id=service_id,
    )
    print(sd.model_dump_json(indent=2, by_alias=True, exclude_none=True))

def create_rest_service_definition(
    service_description: Service,
    fn: Callable[..., Any],
    service_id: Optional[str] = None,
) -> ServiceDefinition:
    # controller
    image = os.getenv("DOCKER_IMG", IMAGE_PLACEHOLDER)

    command = find_command()
    resources = find_resources_file()
    controller = RestController(image=image, command=command, resources=resources)
    return create_service_definition(service_description, fn, REST_CONTROLLER_SCHEMA, controller, service_id)
