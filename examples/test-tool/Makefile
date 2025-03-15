SERVICE_TITLE=AI tool to test various platform aspects
SERVICE_NAME=test-tool

TOOL_FILE=tool-service.py
IVCAP_SERVICE_FILE=service.json

GIT_COMMIT := $(shell git rev-parse --short HEAD)
GIT_TAG := $(shell git describe --abbrev=0 --tags ${TAG_COMMIT} 2>/dev/null || true)
VERSION="${GIT_TAG}|${GIT_COMMIT}|$(shell date -Iminutes)"

DOCKER_USER="$(shell id -u):$(shell id -g)"
DOCKER_DOMAIN=$(shell echo ${PROVIDER_NAME} | sed -E 's/[-:]/_/g')
DOCKER_NAME=$(shell echo ${SERVICE_NAME} | sed -E 's/-/_/g')
DOCKER_VERSION=${GIT_COMMIT}
DOCKER_TAG=${DOCKER_NAME}:${DOCKER_VERSION}
DOCKER_TAG_LOCAL=${DOCKER_NAME}:latest

PROJECT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
TARGET_PLATFORM := linux/$(shell go env GOARCH)
PORT=8095
SERVICE_URL=http://localhost:8099
HTTP_PROXY=http://localhost:9999

run:
	env VERSION=$(VERSION) PYTHONPATH="" \
		python ${PROJECT_DIR}/tool-service.py --port ${PORT}

run-with-proxy:
	env VERSION=$(VERSION) PYTHONPATH="" \
		http_proxy=${HTTP_PROXY} \
		python ${PROJECT_DIR}/tool-service.py --port ${PORT}

test-echo:
	curl -i -X POST -H "content-type: application/json" --data "{\"echo\": \"Hello World!\"}" http://localhost:${PORT}/

test-echo-with-sleep:
	curl -i -X POST -H "content-type: application/json" --data "{\"echo\": \"Hello World!\", \"sleep\":5}" http://localhost:${PORT}

test-echo-with-auth:
	curl -i -X POST \
		-H "content-type: application/json" \
		-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
		--data "{\"echo\": \"Hello World!\"}" http://localhost:${PORT}/

test-call-post:
	curl -X POST \
		-H "content-type: application/json" \
		-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
		--data @${PROJECT_DIR}/tests/call-post.json http://localhost:${PORT} | jq

test-call-post-async:
	curl -X POST -H "content-type: application/json" --data @${PROJECT_DIR}/tests/call-post.json http://localhost:${PORT}/async

test-list-services:
	curl -X POST -H "content-type: application/json" --data @${PROJECT_DIR}/tests/list-services.json http://localhost:${PORT} | jq

test-list-tools:
	curl -X POST -H "content-type: application/json" --data @${PROJECT_DIR}/tests/list-tools.json http://localhost:${PORT} | jq

print-tool-description:
	$(eval service_id:=urn:ivcap:service:$(shell python3 -c 'import uuid; print(uuid.uuid5(uuid.NAMESPACE_DNS, \
        "${SERVICE_NAME}" + "${account_id}"));'))
	env VERSION=$(VERSION) PYTHONPATH="" IVCAP_SERVICE_ID=${service_id} \
		python ${PROJECT_DIR}/tool-service.py --print-tool-description


install:
	pip install -r requirements.txt

docker-run: #docker-build
	docker run -it \
		-p ${PORT}:${PORT} \
		--user ${DOCKER_USER} \
		--platform=${TARGET_PLATFORM} \
		--rm \
		${DOCKER_TAG_LOCAL} --port ${PORT}

docker-debug: #docker-build
	docker run -it \
		-p 8090:8090 \
		--user ${DOCKER_USER} \
		--platform=${TARGET_PLATFORM} \
		--entrypoint bash \
		${DOCKER_TAG_LOCAL}

docker-build:
	@echo "Building docker image '${DOCKER_NAME}' for '${TARGET_PLATFORM}'"
	docker build \
		-t ${DOCKER_TAG_LOCAL} \
		--platform=${TARGET_PLATFORM} \
		--build-arg VERSION=${VERSION} \
		-f ${PROJECT_DIR}/Dockerfile \
		${PROJECT_DIR} ${DOCKER_BILD_ARGS}
	@echo "\nFinished building docker image ${DOCKER_NAME}\n"

SERVICE_IMG := ${DOCKER_DEPLOY}
PUSH_FROM := ""

service-register: # tool-register # docker-publish
	$(eval account_id=$(shell ivcap context get account-id))
	@if [[ ${account_id} != urn:ivcap:account:* ]]; then echo "ERROR: No IVCAP account found"; exit -1; fi
	@$(eval service_id:=urn:ivcap:service:$(shell python3 -c 'import uuid; print(uuid.uuid5(uuid.NAMESPACE_DNS, \
        "${SERVICE_NAME}" + "${account_id}"));'))
	@$(eval image:=$(shell ivcap --context gke-dev package list ${DOCKER_TAG}))
	@if [[ -z "${image}" ]]; then echo "ERROR: No uploaded docker image '${DOCKER_TAG}' found"; exit -1; fi
	@echo "ServiceID: ${service_id}"
	cat ${PROJECT_DIR}/${IVCAP_SERVICE_FILE} \
	| sed 's|#DOCKER_IMG#|${image}|' \
	| sed 's|#SERVICE_ID#|${service_id}|' \
  | ivcap aspect update ${service_id} -f - --timeout 600

tool-register: #docker-publish
	$(eval account_id=$(shell ivcap context get account-id))
	@if [[ ${account_id} != urn:ivcap:account:* ]]; then echo "ERROR: No IVCAP account found"; exit -1; fi
	$(eval service_id:=urn:ivcap:service:$(shell python3 -c 'import uuid; print(uuid.uuid5(uuid.NAMESPACE_DNS, \
        "${SERVICE_NAME}" + "${account_id}"));'))
	$(eval tool_id:=$(shell docker run --rm ${DOCKER_NAME} --print-tool-description  2>/dev/null | grep "\"id\":" | cut -d\" -f 4 ))
	@echo "DEBUG: ToolID: ${tool_id} ServiceID: ${service_id} - ${DOCKER_NAME}"
	@if [[ -z "${tool_id}" ]]; then echo "ERROR: No Tool ID found"; exit -1; fi
	docker run --rm ${DOCKER_NAME} --print-tool-description  2>/dev/null \
	| sed 's|#SERVICE_ID#|${service_id}|' \
	| ivcap aspect update ${service_id} -f - --timeout 600

docker-publish: TARGET_PLATFORM=linux/amd64
docker-publish: docker-build
	@echo "INFO: Publishing docker image '${DOCKER_TAG}' for '${TARGET_PLATFORM}'"
	docker tag ${DOCKER_NAME} ${DOCKER_TAG}
	$(eval size:=$(shell docker inspect ${DOCKER_NAME} --format='{{.Size}}' | tr -cd '0-9'))
	$(eval imageSize:=$(shell expr ${size} + 0 ))
	@echo "... imageSize is ${imageSize}"
	@$(MAKE) PUSH_FROM="--local " docker-publish-common

docker-publish-common:
	$(eval log:=$(shell ivcap --context gke-dev package push --force ${PUSH_FROM}${DOCKER_TAG} | tee /dev/tty))
	$(eval SERVICE_IMG := $(shell echo ${log} | sed -E "s/.*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}.*) pushed/\1/"))
	@if [ "${SERVICE_IMG}" == "" ] || [ "${SERVICE_IMG}" == "${DOCKER_TAG}" ]; then \
		echo "service package push failed"; \
		exit 1; \
	fi
	@echo "INFO: Successfully published '${DOCKER_TAG}' as '${SERVICE_IMG}'"


FORCE:
