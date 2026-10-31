# FlagPilot — Implementation Plan

Legend: `[ ]` todo · `[x]` done and verified

## M1 — Environment inspection and setup
- [x] Inspect OS, Python 3.13.1, Node 22.13, npm 11.4; Docker missing → install via winget (needs UAC approval)
- [x] Docker Desktop functional (`docker compose version`)
- [x] Ports 3000, 8000, 5432, 6379 free
- [x] `scripts/setup.py` generates `.env`
**Done when (verified):** `docker run hello-world` works and `.env` exists.

## M2 — Backend foundation and database schema
- [x] Config, logging, DB session, models, Alembic initial migration (envs seeded)
- [x] Health endpoints (live/ready with degraded state)
**Done when (verified):** `alembic upgrade head` succeeds on compose Postgres; `/health/ready` is 200.

## M3 — Authentication and flag management
- [x] Argon2 admin bootstrap, DB sessions, login/logout/me, CSRF + Origin checks
- [x] Flag CRUD, per-environment config, archive/restore, audit events
**Done when (verified):** vertical slice works over HTTP: login → create flag → list flags.

## M4 — Feature evaluation engine
- [x] Pure engine (SHA-256 bucket, precedence), unit tests
- [x] API keys (hashed, env-scoped), `POST /api/v1/evaluate`, admin playground evaluate
**Done when (verified):** evaluation tests pass incl. 0%/100%, monotonic rollout, inclusion/exclusion.

## M5 — Targeting, caching, security
- [x] Redis cache with TTL + invalidation + circuit breaker
- [x] Rate limiting (Redis + in-memory fallback), CORS, safe error responses
**Done when (verified):** invalidation, Redis-down and recovery, rate-limit tests pass.

## M6 — Dashboard
- [x] Login, overview, flags list, flag editor, audit, API keys pages
## M7 — Playground and demo
- [x] Evaluation playground (real backend), demo app page driven by FlagPilot
## M8 — Automated testing
- [x] pytest suite, frontend typecheck/lint/build, Playwright e2e, benchmark
## M9 — Full integration verification and bug fixing
- [x] `docker compose up --build` from clean, full suite green
## M10 — Documentation, screenshots, handoff
- [x] README, ARCHITECTURE, TEST_REPORT, PORTFOLIO_SUMMARY, screenshots in `portfolio/screenshots/`
