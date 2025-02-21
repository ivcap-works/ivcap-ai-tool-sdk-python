
ROOT_DIR:=$(shell dirname $(realpath $(firstword $(MAKEFILE_LIST))))
SRC_DIR:=${ROOT_DIR}/src

.PHONY: copyx

build: add-license
	cd ${ROOT_DIR}
	rm -rf ${ROOT_DIR}/dist/*
	poetry build

# https://www.digitalocean.com/community/tutorials/how-to-publish-python-packages-to-pypi-using-poetry-on-ubuntu-22-04
publish: build
	poetry publish

test:
	poetry run pytest ${ROOT_DIR}/tests/ --cov=ivcap_fastapi --cov-report=xml

add-license:
	licenseheaders -t .license.tmpl -y 2023 -f src/ivcap_ai_tool/*.py

clean:
	rm -rf *.egg-info
	rm -rf dist
	find ${ROOT_DIR} -name __pycache__ | xargs rm -r

.PHONY: docs
