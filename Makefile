COMPOSE ?= docker compose
PYTEST ?= $(if $(wildcard .venv/bin/pytest),.venv/bin/pytest,pytest)
RUFF ?= $(if $(wildcard .venv/bin/ruff),.venv/bin/ruff,ruff)

.PHONY: up down logs test lint migrate

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f api

test:
	$(PYTEST) -q

lint:
	$(RUFF) check app tests

migrate:
	$(COMPOSE) exec api alembic upgrade head
