
ROOT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
SRC_DIR:=${ROOT_DIR}/src

.PHONY: copyx test check

build: add-license
	cd ${ROOT_DIR}
	rm -rf ${ROOT_DIR}/dist/*
	poetry build

# https://www.digitalocean.com/community/tutorials/how-to-publish-python-packages-to-pypi-using-poetry-on-ubuntu-22-04
publish: build
	poetry publish

test:
	poetry run pytest ${ROOT_DIR}/tests/ --cov=ivcap_lambda --cov-report=xml

check: test
	poetry run ruff check .
	poetry run mypy ivcap_lambda

add-license:
	poetry run licenseheaders -t .license.tmpl -y $(shell date +%Y) -f ivcap_lambda/*.py -f tests/*.py

clean:
	rm -rf *.egg-info
	rm -rf dist
	find ${ROOT_DIR} -name __pycache__ | xargs rm -r

.PHONY: docs docs-serve docs-build docs-install

docs-install:
	poetry run pip install -q -r ${ROOT_DIR}/docs/requirements-docs.txt

docs-serve: docs-install
	cd ${ROOT_DIR}/docs && \
	DOCS_PORT=$$(python3 -c "import socket; s=socket.socket(); s.bind(('',0)); p=s.getsockname()[1]; s.close(); print(p)") && \
	echo "Serving docs at http://localhost:$$DOCS_PORT" && \
	poetry run mkdocs serve --dev-addr=localhost:$$DOCS_PORT

docs-build: docs-install
	cd ${ROOT_DIR}/docs && poetry run mkdocs build

docs: docs-build
