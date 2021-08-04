# .EXPORT_ALL_VARIABLES:

net=10.20.30.1/24

poetry-build:
	poetry update
	poetry install
	poetry build
build:
	docker build . --tag docker-hoster --target prod
build-dind:
	docker build ./tests/dind/ --tag docker-hoster-dind
build-dev: poetry-build
	docker-compose build --progress=plain 
build-dev-nocache:
	# docker builder prune || 0
	docker-compose build --progress=plain --no-cache
test:
	poetry run tox --recreate
test-old:
	poetry run pytest --log-cli-level=DEBUG --cov=docker_hoster tests/
	# poetry run pytest --log-level=DEBUG --cov=docker_hoster tests/
tox:
	 poetry run tox
