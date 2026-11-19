# Module 0: Skeleton

Proves that Postgres, Qdrant, Gemini and storage can all be reached from the backend, and that the frontend can show their status. It contains no business logic. It also freezes the shared schemas that every later module uses.

## Setup

```bash
git clone <repo-url> && cd alien-prags
cp .env.example .env          # then edit .env: set GEMINI_API_KEY and the two model names
docker compose up --build -d
docker compose exec backend alembic upgrade head    # the only manual step
```

Then open:

- Frontend status page: http://localhost:3001
- Health endpoint: http://localhost:8000/api/v1/health

Host ports are set in `.env` (`POSTGRES_HOST_PORT`, `QDRANT_HOST_PORT`, `BACKEND_HOST_PORT`, `FRONTEND_HOST_PORT`). Change them if they clash with something else on your machine. If you change `FRONTEND_HOST_PORT`, update `CORS_ORIGINS` to match. If you change `BACKEND_HOST_PORT`, update `NEXT_PUBLIC_API_URL` and rebuild the frontend (`docker compose up --build -d frontend`), because that URL is baked in at build time.

### Running the backend outside Docker

```bash
cd backend
uv sync
uv run pytest                                  # tests need no services or API key
uv run uvicorn app.main:app --reload           # needs Postgres and Qdrant running (docker compose up -d postgres qdrant)
```

`.env` is read from `backend/` or the repo root. The default `DATABASE_URL` and `QDRANT_URL` point at `localhost` on the host ports above.

## What each file does

| File | Purpose |
|---|---|
| `.env.example` | Every setting with placeholder values. Copy to `.env` (never commit `.env`). |
| `docker-compose.yml` | Runs postgres, qdrant, backend, frontend. Backend waits for healthy postgres and qdrant. |
| `backend/app/main.py` | Builds the app: startup checks, CORS, middleware, error handlers, routes. |
| `backend/app/api/health.py` | `GET /api/v1/health`: runs the four service checks and builds the response. |
| `backend/app/core/config.py` | The one `Settings` class that reads `.env`. |
| `backend/app/core/db.py` | Postgres engine, session factory, `check_db()`. |
| `backend/app/core/providers.py` | Interfaces (LLM, embeddings, vector store, storage), their Gemini/Qdrant/local implementations, and the `get_*()` factories. |
| `backend/app/core/errors.py` | Turns every error (including 422) into `{"error": {"code", "message", "details"}}`. |
| `backend/app/core/logging.py` | JSON log formatter. |
| `backend/app/core/middleware.py` | Request ID plus one log line per request; sets `X-Request-ID`. |
| `backend/app/schemas/` | Shared models: `Document`, `Chunk`, `RetrievedChunk`, `Citation`, `Answer`, `DomainConfig`. Import from `app.schemas`. |
| `backend/alembic/` | Migrations. One empty placeholder migration (`0001`). The DB URL comes from Settings. |
| `backend/tests/` | Schema round-trips, error envelope, health (mocked), storage. |
| `frontend/app/page.tsx` | Status page: fetches `/api/v1/health`, one card per service, Refresh button, "backend unreachable" banner. |
| `domains/`, `storage/` | Empty (`.gitkeep`). Domain packs arrive in Module 1; `storage/` holds local files. |

## Notes

- Gemini is checked once at startup and the result is cached. Use `/api/v1/health?deep=true` to force a fresh check (this makes two small Gemini calls).
- Only Postgres being down stops the backend from starting (it logs `postgres_unreachable` at CRITICAL and exits non-zero). Other failures show up in `/health` instead.
- The `_healthcheck` collection in Qdrant is created by the health check and is safe to leave.
