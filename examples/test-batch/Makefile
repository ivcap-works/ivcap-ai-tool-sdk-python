SERVICE_TITLE=Batch service to test various platform aspects
SERVICE_NAME=test-batch

IVCAP_SERVICE_FILE=service.json

PORT=8095
SERVICE_URL=http://localhost:8099
HTTP_PROXY=http://localhost:9999
TIMEOUT=3

include Makefile.common

# fix service ID
SERVICE_ID=urn:ivcap:service:3678e5f1-8fb7-5ad6-b65b-8bd8c23c0948

run:
	env VERSION=$(VERSION) \
		PYTHONPATH="" \
		IVCAP_BASE_URL="http://ivcap.local" \
		python ${PROJECT_DIR}/batch_service.py --test-file ${PROJECT_DIR}/tests/load_1.json

run-with-proxy:
	env VERSION=$(VERSION) PYTHONPATH="" \
		PYTHONPATH=${PROJECT_DIR}/../../src \
		IVCAP_BASE_URL="http://ivcap.local" \
		http_proxy=${HTTP_PROXY} \
		python ${PROJECT_DIR}/batch_service.py

REQUEST_FILE=${PROJECT_DIR}/tests/req_1.json
IVCAP_URL=$(shell ivcap context get url)
test-ivcap:
	curl -X POST \
		-H "content-type: application/json" \
		-H "Authorization: Bearer $(shell ivcap context get access-token --refresh-token)" \
		-H "Timeout: ${TIMEOUT}" \
		--data @${REQUEST_FILE} \
		${IVCAP_URL}/1/services2/${SERVICE_ID}/jobs

install:
	pip install -r requirements.txt

docker-run: DOCKER_TAG=${DOCKER_NAME}_${TARGET_ARCH}:${DOCKER_VERSION}
docker-run: #docker-build
	docker run -it \
		-p ${PORT}:${PORT} \
		--user ${DOCKER_USER} \
		-e LITELLM_PROXY=http://192.168.68.103:4000 \
		-e IVCAP_BASE_URL="http://ivcap.local" \
		-e http_proxy=http://192.168.68.103:9999 \
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
