PYTHON ?= python

.PHONY: lint test migrate up

lint:
	$(PYTHON) -m ruff check backend tests

test:
	$(PYTHON) -m pytest -q

migrate:
	$(PYTHON) -m alembic upgrade head

up:
	docker compose up --build
