SERVICE_TITLE=AI tool to test various platform aspects
SERVICE_NAME=test-tool

TOOL_FILE=tool-service.py
IVCAP_SERVICE_FILE=service.json

PORT=8095
SERVICE_URL=http://localhost:8099
HTTP_PROXY=http://localhost:9999

include Makefile.common

run:
	env VERSION=$(VERSION) PYTHONPATH="" \
		python ${PROJECT_DIR}/tool-service.py --port ${PORT}

run-with-proxy:
	env VERSION=$(VERSION) PYTHONPATH="" \
		http_proxy=${HTTP_PROXY} \
		python ${PROJECT_DIR}/tool-service.py --port ${PORT}

run-litellm:
	env $(shell cat .env | xargs) litellm --port 4000 -m gpt-3.5-turbo -m gpt-4

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
	curl -X POST \
		-H "content-type: application/json" \
		-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
		--data @${PROJECT_DIR}/tests/list-services.json http://localhost:${PORT} | jq

test-list-services-ivcap:
	curl -X POST \
		-H "content-type: application/json" \
		-H "Authorization: Bearer $(shell ivcap --context gke-dev context get access-token --refresh-token)" \
		-H "Timeout: 60" \
		--data @${PROJECT_DIR}/tests/list-services.json \
		https://develop.ivcap.net/1/services2/${SERVICE_ID}/jobs | jq

test-list-tools:
	curl -X POST -H "content-type: application/json" --data @${PROJECT_DIR}/tests/list-tools.json http://localhost:${PORT} | jq

test-llm:
	curl -X POST -H "content-type: application/json" \
	-H "Timeout: 60" \
	-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
	--data @${PROJECT_DIR}/tests/llm-hello.json http://localhost:${PORT} | jq

test-llm-with-auth:
	curl -i -X POST \
		-H "content-type: application/json" \
		-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
		-H "Timeout: 60" \
		--data @${PROJECT_DIR}/tests/llm-hello.json \
		http://localhost:${PORT}

test-llm-minikube:
	curl -i -X POST \
		-H "content-type: application/json" \
		-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
		-H "Timeout: 10" \
		--data @${PROJECT_DIR}/tests/llm-hello.json \
		http://ivcap.minikube/1/services2/${SERVICE_ID}/jobs

test-llm-ivcap:
	curl -i -X POST \
		-H "content-type: application/json" \
		-H "Authorization: Bearer $(shell ivcap --context gke-dev context get access-token --refresh-token)" \
		-H "Timeout: 60" \
		--data @${PROJECT_DIR}/tests/llm-hello.json \
		https://develop.ivcap.net/1/services2/${SERVICE_ID}/jobs

REQUEST=echo.json
test-local-debug:
	curl -i -X POST \
		-H "content-type: application/json" \
		-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
		-H "Timeout: 60" \
		--data @${PROJECT_DIR}/tests/${REQUEST} \
		http://localhost:8088/1/services2/${SERVICE_ID}/jobs

print-tool-description:
	$(eval service_id:=urn:ivcap:service:$(shell python3 -c 'import uuid; print(uuid.uuid5(uuid.NAMESPACE_DNS, \
        "${SERVICE_NAME}" + "${account_id}"));'))
	env VERSION=$(VERSION) PYTHONPATH="" IVCAP_SERVICE_ID=${service_id} \
		python ${PROJECT_DIR}/tool-service.py --print-tool-description


install:
	pip install -r requirements.txt

docker-run: DOCKER_TAG=${DOCKER_NAME}_${TARGET_ARCH}:${DOCKER_VERSION}
docker-run: #docker-build
	docker run -it \
		-p ${PORT}:${PORT} \
		--user ${DOCKER_USER} \
		-e LITELLM_PROXY=http://192.168.68.104:4000 \
		--platform=${TARGET_PLATFORM} \
		--rm \
		${DOCKER_TAG} --port ${PORT}

docker-debug: #docker-build
	docker run -it \
		-p 8090:8090 \
		--user ${DOCKER_USER} \
		--platform=${TARGET_PLATFORM} \
		--entrypoint bash \
		${DOCKER_TAG_LOCAL}
