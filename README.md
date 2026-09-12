# FinSight

Personal finance analytics API. This repository currently contains **Phase 1 only**: a FastAPI process, PostgreSQL, SQLAlchemy session wiring, and Alembic. There is no auth, no portfolios, no market data, and no frontend.

## Overview

Phase 1 is the backend foundation. The running stack exposes:

- `GET /health` → `{"status":"ok"}`
- `GET /docs` — FastAPI's interactive OpenAPI UI
- PostgreSQL 16 on the Compose network (published on host port `15432`)

The database engine is constructed at startup so later features can request a session. Schema changes go through Alembic, not `Base.metadata.create_all()`.

## Why I built this

I wanted a realistic place to practice a production-shaped backend: settings from the environment, structured logs, migrations as versioned code, and a Compose file that actually boots the API and the database together. FinSight's product idea is personal portfolio analytics; Phase 1 stops at the scaffolding so those domain pieces can land on a stable base instead of growing out of a single script.

## Architecture

### Current (Phase 1 — built)

```text
                   host :18421
                        │
                        ▼
              ┌─────────────────┐
   Client ──► │  FastAPI (api)  │  GET /health, GET /docs
              └────────┬────────┘
                       │ SQLAlchemy engine (wired, unused by /health)
                       ▼
              ┌─────────────────┐
              │ PostgreSQL (db) │  host :15432 → container :5432
              └─────────────────┘
                       ▲
                       │ alembic upgrade (manual)
              ┌────────┴────────┐
              │ Alembic (empty  │
              │ baseline only)  │
              └─────────────────┘
```

Compose puts `api` and `db` on one user-defined network. The API reaches Postgres at hostname `db` (the service name). On the host, the same database is `localhost:15432`. That is why `.env.example` uses `localhost` and `docker-compose.yml` overrides `DATABASE_URL` to `...@db:5432/...`.

### Planned (not built)

Later phases are expected to add, in this same modular monolith (not microservices):

| Phase idea | Status |
| --- | --- |
| Auth / users | Not built |
| Portfolios, holdings, transactions | Not built |
| Market data / prices | Not built |
| Analytics, screening | Not built |
| Redis, background jobs | Not built |
| AI features | Not built |
| Frontend | Not built |

```text
  [future] Browser UI ──► FastAPI routers ──► services ──► SQLAlchemy models
                              │                    │
                              │                    ├── Postgres (source of truth)
                              │                    └── Redis (cache / jobs)   ← not built
                              └── workers / market-data jobs                  ← not built
```

### What each piece solves

**FastAPI request flow.** An HTTP request hits Uvicorn, which calls the ASGI app. Middleware runs first (here: one structured access log). FastAPI then matches the path to a router, resolves `Depends(...)` callables (for example `get_db`), and invokes the handler. The handler should stay thin: validate input, call a service, return a response model. `/health` has no service layer because it only reports process liveness.

**Docker Compose networking.** Each service is reachable by its Compose service name on an isolated bridge network. `depends_on` with a Postgres healthcheck means the API container starts only after `pg_isready` succeeds. Publishing `18421:8000` is a host-port mapping; inside the container the app still listens on `8000`.

**SQLAlchemy vs Alembic.** SQLAlchemy is the runtime toolkit: engine, connection pool, sessions, and (later) ORM models. Alembic is the migration runner: it stores revision files and applies them in order. They share `Base.metadata`. SQLAlchemy does not replace Alembic.

**Why no `create_all` on startup.** `Base.metadata.create_all()` creates missing tables and then stops. It will not alter a column, drop a constraint, or record what changed. That is fine for a throwaway notebook and unsafe once any environment has data. Alembic revisions are reviewable, reversible, and the same in every environment.

## Tech Stack

| Piece | Why |
| --- | --- |
| Python 3.12+ | Language runtime |
| FastAPI + Pydantic | HTTP API and request/response schemas |
| Uvicorn | ASGI server |
| SQLAlchemy 2.x | Engine and session (models come later) |
| Alembic | Schema migrations |
| PostgreSQL 16 | Primary database |
| psycopg 3 | Postgres driver (`postgresql+psycopg://`) |
| pytest + httpx | API tests (`TestClient` uses httpx) |
| Ruff | Lint |
| Docker Compose | Local `api` + `db` |

No Redis. No Celery. No extra services.

## Running Locally

### Docker Compose (preferred)

```bash
docker compose up --build
# or: make up
```

Then:

- Health: http://127.0.0.1:18421/health
- OpenAPI: http://127.0.0.1:18421/docs

Stop with `make down` (or `docker compose down`). Apply the baseline migration with `make migrate` after the stack is up.

### Tests and lint (host)

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
make test
make lint
```

`/health` does not open a database connection, so pytest does not need Postgres.

### Environment variables

Copy `.env.example` to `.env` only if you run Uvicorn on the host against the published Postgres port. Compose injects `DATABASE_URL` for the `api` service and does not require a `.env` file. `.env` is gitignored.

| Variable | Purpose |
| --- | --- |
| `APP_NAME` | OpenAPI title |
| `ENVIRONMENT` | Logged on startup |
| `LOG_LEVEL` | Root log level |
| `DATABASE_URL` | SQLAlchemy / Alembic URL |

Local Compose credentials (`finsight` / `finsight`) are development defaults, not production secrets.

## Makefile

| Target | Action |
| --- | --- |
| `make up` | `docker compose up --build -d` |
| `make down` | `docker compose down` |
| `make logs` | Follow API logs |
| `make test` | pytest |
| `make lint` | Ruff |
| `make migrate` | `alembic upgrade head` inside the API container |
