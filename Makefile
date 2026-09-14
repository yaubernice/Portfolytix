COMPOSE ?= docker compose
PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)
PYTEST ?= $(if $(wildcard .venv/bin/pytest),.venv/bin/pytest,pytest)
RUFF ?= $(if $(wildcard .venv/bin/ruff),.venv/bin/ruff,ruff)
ALEMBIC ?= $(if $(wildcard .venv/bin/alembic),.venv/bin/alembic,alembic)

.PHONY: up down logs test lint migrate migrate-host seed seed-host

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f api

test:
	$(PYTEST) -q

lint:
	$(RUFF) check app tests scripts

migrate:
	$(COMPOSE) exec api alembic upgrade head

migrate-host:
	$(ALEMBIC) upgrade head

seed:
	$(COMPOSE) exec api python scripts/seed_database.py

seed-host:
	$(PYTHON) scripts/seed_database.py
