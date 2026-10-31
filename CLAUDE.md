# CLAUDE.md — FlagPilot project instructions

## Purpose
FlagPilot is a self-hosted feature flag management platform (dashboard + evaluation API) built as a
portfolio-quality backend/full-stack engineering project. Teams create flags, configure per-environment
(development / production) rollouts and user targeting, and consuming applications ask the evaluation API
whether a user should get a feature — without redeploying.

## Hard rules
1. **NEVER use Git.** No `git init/status/add/commit/push/clone/...`. The owner publishes the repo themself.
2. Work only inside the project directory except for installing dev tools.
3. No paid services, no external AI APIs, no cloud deployment.
4. PostgreSQL and Redis run through Docker Compose, not installed on the host.
5. Never claim something works unless it was executed and verified. Never disable failing tests.
6. Never commit/print real secrets. `.env` holds generated local secrets and is git-ignored; `.env.example` has placeholders.
7. Keep scope appropriate: no microservices, no Kubernetes, no enterprise extras.

## Stack
- Backend: Python 3.12 (container) / 3.13 (host venv), FastAPI, SQLAlchemy 2 (sync), Alembic, Pydantic v2, psycopg 3, PostgreSQL 16, Redis 7.
- Frontend: Next.js (App Router) + TypeScript + Tailwind CSS, hand-written small component system.
- Infra: Docker, Docker Compose, health checks, `.env` configuration.
- Tests: pytest (real Postgres + Redis), Playwright (real stack), tsc, ESLint, `next build`.

## Layout
```
backend/app/
  main.py            app factory, middleware, exception handlers, lifespan (bootstrap)
  config.py          pydantic-settings
  db.py              engine/session
  models/            SQLAlchemy models
  schemas/           Pydantic request/response models
  repositories/      DB access (only place that builds queries)
  services/          business logic (flags, audit, auth, api keys, evaluation, stats, bootstrap)
  engine/            PURE evaluation logic (bucketing + precedence) — no I/O
  cache/             Redis cache wrapper w/ circuit breaker, rate limiter
  auth/              password hashing, sessions, CSRF/origin, API-key auth dependencies
  api/               FastAPI routers (auth, admin, evaluate, health)
backend/alembic/     migrations
backend/tests/       pytest suite (unit + integration)
frontend/            Next.js dashboard, evaluation playground, demo app, Playwright e2e (frontend/e2e)
benchmarks/          reproducible evaluation benchmark
scripts/             setup.py (generates .env secrets), helpers
```

## Evaluation precedence (must stay in sync with docs + tests)
1. flag disabled in env, or kill switch → disabled (`flag_disabled` / `kill_switch`)
2. user in excluded list → disabled (`user_excluded`)
3. user in included list → enabled (`user_included`)
4. SHA-256 percentage bucket < rollout → enabled (`percentage_rollout`)
5. else disabled (`default_disabled`)
Unknown flag → 200 disabled `flag_not_found`; archived → `flag_archived`; infra failure → 503 (clients fail closed).

## Coding standards
- Type hints everywhere; Pydantic models for all I/O; ORM only (no string SQL with user input).
- Routers thin → services → repositories. Evaluation engine is pure and exhaustively unit-tested.
- Structured (JSON) logging; never log API keys, passwords, session tokens.
- Frontend: strict TypeScript, no `any`, consistent components in `frontend/src/components/ui`.

## Security requirements
Argon2 password hashing; server-side sessions (hashed token in DB) in HttpOnly SameSite cookie; CSRF token header +
Origin check on session-authenticated mutations; environment-scoped hashed API keys for evaluation; rate limiting
(Redis, in-memory fallback); strict CORS; safe error bodies; no secrets in source or logs.

## Development commands (Windows / PowerShell; Docker Desktop required)
```powershell
python scripts/setup.py            # first time: creates .env with generated secrets
docker compose up --build -d       # postgres, redis, backend (:8000), frontend (:3000)
docker compose logs -f backend
# backend tests (venv at backend/.venv, uses compose postgres/redis on localhost)
cd backend; .\.venv\Scripts\python -m pytest -q
# frontend
cd frontend; npm run typecheck; npm run lint; npm run build; npm run e2e
# benchmark
backend\.venv\Scripts\python benchmarks/bench_evaluate.py
```

## Testing requirements
Backend tests hit real PostgreSQL and Redis (database `flagpilot_test`, Redis db 15). Playwright e2e uses the real
running stack. Record exact commands/results in `TEST_REPORT.md` only after executing them.

## Resuming interrupted work
1. Read `PROGRESS_STATUS.md` (current milestone, next steps, restart commands) and `IMPLEMENTATION_PLAN.md`.
2. Inspect the real files — docs are a continuity aid, not truth.
3. `docker compose ps` / `docker version` to see whether the stack is up; rerun tests to establish a baseline.
4. Continue at the first unchecked task; update `PROGRESS_STATUS.md` after each milestone.
