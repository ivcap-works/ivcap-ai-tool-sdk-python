# SERVICE_TITLE=AI tool to test various platform aspects
# SERVICE_NAME=test-tool

# TOOL_FILE=tool-service.py
# IVCAP_SERVICE_FILE=service.json
PROJECT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))


PORT=8095
SERVICE_URL=http://localhost:8099
HTTP_PROXY=http://localhost:9999
TIMEOUT=3

#include Makefile.common

run:
	env VERSION=$(VERSION) \
		PYTHONPATH="" \
		PORT=${PORT} \
		poetry ivcap run

run-from-source:
	env VERSION=$(VERSION) \
		PYTHONPATH=${PROJECT_DIR}/../.. \
		PORT=${PORT} \
		poetry ivcap run

run-with-proxy:
	env VERSION=$(VERSION) PYTHONPATH="" \
		PYTHONPATH=${PROJECT_DIR}/../../src \
		IVCAP_BASE_URL="http://ivcap.local" \
		http_proxy=${HTTP_PROXY} \
		PORT=${PORT} \
		poetry ivcap run

TEST_FILE=tests/test_job_load.json
run-test-as-service:
	env VERSION=$(VERSION) \
			PYTHONPATH=${PROJECT_DIR}/../.. \
			poetry run python tool-service.py \
			 --test-file ${TEST_FILE} \
			 --test-without-sidecar

run-litellm:
	env $(shell cat .env | xargs) litellm --port 4000 -m gpt-3.5-turbo -m gpt-4

test-echo:
	curl -i -X POST \
		-H "content-type: application/json" \
		-H "timeout:${TIMEOUT}" \
		 --data "{\"echo\": \"Hello World!\"}" \
		 http://localhost:${PORT}/

test-echo-with-sleep:
	curl -i -X POST -H "content-type: application/json" --data "{\"echo\": \"Hello World!\", \"sleep\":5}" http://localhost:${PORT}

JOB_ID=urn:ivcap:job:ef3cdd2a-ab66-4419-ac2c-acc14b3a5fa8
test-echo-with-auth:
	curl -i -X POST \
		-H "content-type: application/json" \
		-H "job-id: ${JOB_ID}" \
		-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
		--data "{\"echo\": \"Hello World!\"}" http://localhost:${PORT}/

test-error:
	curl -i -X POST \
		-H "content-type: application/json" \
		-H "job-id: ${JOB_ID}" \
		-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
		--data @${PROJECT_DIR}/tests/raise_error.json http://localhost:${PORT}/

DOWNLOAD_ARTIFACT=tests/download-artifact.json
test-download-artifact:
	curl -X POST \
		-H "content-type: application/json" \
		-H "Timeout: ${TIMEOUT}" \
		-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
		--data @${PROJECT_DIR}/${DOWNLOAD_ARTIFACT} http://localhost:${PORT} | jq

test-call-post:
	curl -X POST \
		-H "content-type: application/json" \
		-H "Timeout: ${TIMEOUT}" \
		-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
		--data @${PROJECT_DIR}/tests/call-post.json http://localhost:${PORT} | jq

test-call-post-async:
	curl -X POST -H "content-type: application/json" --data @${PROJECT_DIR}/tests/call-post.json http://localhost:${PORT}/async

test-call-get:
	curl -X POST \
		-H "content-type: application/json" \
		-H "Timeout: ${TIMEOUT}" \
		-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
		--data @${PROJECT_DIR}/tests/call-get.json http://localhost:${PORT} | jq

test-list-services:
	curl -X POST \
		-H "content-type: application/json" \
		-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
		--data @${PROJECT_DIR}/tests/list-services.json http://localhost:${PORT} | jq

test-list-services-ivcap:
	curl -X POST \
		-H "content-type: application/json" \
		-H "Authorization: Bearer $(shell ivcap --context gke-dev context get access-token --refresh-token)" \
		-H "Timeout: ${TIMEOUT}" \
		--data @${PROJECT_DIR}/tests/list-services.json \
		https://develop.ivcap.net/1/services2/${SERVICE_ID}/jobs | jq

test-list-tools:
	curl -X POST -H "content-type: application/json" --data @${PROJECT_DIR}/tests/list-tools.json http://localhost:${PORT} | jq

test-wordle:
	curl -X POST -H "content-type: application/json" --data @${PROJECT_DIR}/tests/wordle.json http://localhost:${PORT} | jq

test-oom-error:
	curl -i -H "Timeout: 20" -X POST -H "content-type: application/json" --data @${PROJECT_DIR}/tests/cause_oom_error.json http://localhost:${PORT}

test-events:
	curl -i -X POST \
		-H "content-type: application/json" \
		-H "Authorization: Bearer $(shell ivcap --context gke-dev context get access-token --refresh-token)" \
		-H "Timeout: ${TIMEOUT}" \
		--data @${PROJECT_DIR}/tests/events.json \
		http://localhost:${PORT}

test-llm:
	curl -X POST -H "content-type: application/json" \
	-H "Timeout: ${TIMEOUT}" \
	-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
	--data @${PROJECT_DIR}/tests/llm-hello.json http://localhost:${PORT} | jq

test-llm-with-auth:
	curl -i -X POST \
		-H "content-type: application/json" \
		-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
		-H "Timeout: ${TIMEOUT}" \
		--data @${PROJECT_DIR}/tests/llm-hello.json \
		http://localhost:${PORT}

MINIKUBE_URL=http://ivcap.minikube
test-llm-minikube:
	curl -i -X POST \
		-H "content-type: application/json" \
		-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
		-H "Timeout: ${TIMEOUT}" \
		--data @${PROJECT_DIR}/tests/llm-hello.json \
		http://ivcap.minikube/1/services2/$(shell poetry ivcap get-service-id)/jobs

test-echo-minikube:
	curl -i -X POST \
		-H "content-type: application/json" \
		-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
		-H "Timeout: ${TIMEOUT}" \
		-H 'origin: ${MINIKUBE_URL}' \
		--data @${PROJECT_DIR}/tests/echo.json \
		${MINIKUBE_URL}/1/services2/$(shell poetry ivcap get-service-id)/jobs

IVCAP_REQUEST=tests/echo.json
ivcap-run:
	ivcap job create \
		$(shell poetry ivcap get-service-id) \
		-f ${PROJECT_DIR}/${IVCAP_REQUEST} \
		--stream

ivcap-llm: IVCAP_REQUEST=tests/llm-hello.json
ivcap-llm: ivcap-run


REQUEST=echo.json
test-local-debug:
	curl -i -X POST \
		-H "content-type: application/json" \
		-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
		-H "Timeout: ${TIMEOUT}" \
		--data @${PROJECT_DIR}/tests/${REQUEST} \
		http://localhost:8088/1/services2/${SERVICE_ID}/jobs

# Build using the latest published ivcap-lambda / ivcap-service releases
DOCKER_TAG=test-tool:published
docker-build:
	docker build -f Dockerfile -t ${DOCKER_TAG} \
		--build-arg VERSION=$(or $(VERSION),dev) \
		${PROJECT_DIR}

# Build using the current ivcap-lambda and ivcap-service source trees
# (ivcap-lambda-sdk-python = build context, ivcap-service-sdk-python = named context 'ivcap_service')
DOCKER_TAG_LOCAL=test-tool:local-src
docker-build-local:
	docker build -f Dockerfile.local -t ${DOCKER_TAG_LOCAL} \
		--build-context ivcap_service=${PROJECT_DIR}/../../../ivcap-service-sdk-python \
		--build-arg VERSION=$(or $(VERSION),dev-local) \
		${PROJECT_DIR}/../..

docker-run-test-file: docker-build-local
	docker run --rm \
		-v ${PROJECT_DIR}/tests:/app/tests \
		${DOCKER_TAG_LOCAL} --test-file /app/tests/test_job_load.json --test-without-sidecar

mcp-inspector:
	npx @modelcontextprotocol/inspector --config mcp-inspector.config.json --server default
