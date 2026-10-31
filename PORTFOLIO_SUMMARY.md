# FlagPilot — Portfolio Summary

## Title
**FlagPilot: ship behind a flag, release when you're ready** — a self-hosted feature-flag platform with deterministic rollouts, a cached evaluation API and an interactive playground.

## Short description (business-focused)
FlagPilot lets a software team release new functionality gradually and safely. Engineers create a flag, turn it on for their own testers, expand it to 5 %, 20 %, 50 % of users, keep production untouched while development is open, and shut a problematic feature off in seconds, with no redeploy and a full history of who changed what.

## The problem it solves
Shipping a feature to everyone at once is the riskiest way to release. Teams need remote on/off control, gradual exposure, per-environment configuration, an emergency stop, and an audit trail. FlagPilot provides that through a dashboard for people and an API for applications.

## Engineering challenges addressed
* **Deterministic bucketing**: designing a SHA-256 based assignment so a user always lands in the same bucket (no process-dependent `hash()`), roll-outs are monotonic (raising 20 % → 50 % never removes anyone) and environments roll out independently.
* **Evaluation precedence** (kill switch → disabled → exclude → include → percentage → default) implemented as a pure, exhaustively tested function.
* **Cache correctness**: Redis cache-aside with invalidation after commit, TTL as a staleness ceiling, negative caching, and a documented read/write race.
* **Graceful degradation**: a circuit breaker so a dead Redis costs no latency, automatic recovery with a cache purge, `degraded` vs `unavailable` health states, and fail-closed API semantics.
* **Security**: Argon2id, server-side sessions, CSRF token + Origin checks, hashed environment-scoped API keys, rate limiting with in-memory fallback, safe error bodies, log-hygiene tests.
* **Testing against real infrastructure**: 192 backend tests on PostgreSQL + Redis (including outage/recovery simulations), 11 Playwright end-to-end tests on the real Docker stack.

## Technologies
Python, FastAPI, SQLAlchemy 2, Alembic, Pydantic, PostgreSQL, Redis, Next.js (App Router), TypeScript, Tailwind CSS, Docker Compose, pytest, Vitest, Playwright.

## Recommended screenshot captions (files in `portfolio/screenshots/`)
1. `03-evaluation-playground.png`: *"The evaluation playground runs the real backend engine: user 'bob' lands in bucket 181 of 10 000, inside a 50 % rollout, while the sample cohort shows included, excluded and bucketed users side by side."*
2. `02-feature-flags.png`: *"Every flag has an independent development and production configuration, with one-click toggles and rollout percentages at a glance."*
3. `05-demo-app.png` (or `01-overview.png`): *"A fictional customer app asks FlagPilot's API which dashboard to show; changing the flag in FlagPilot changes the page within seconds, with no redeploy."*

## Resume bullet candidates (each grounded in verified work)
* Built **FlagPilot**, a full-stack feature-flag platform (FastAPI, PostgreSQL, Redis, Next.js/TypeScript) with deterministic SHA-256 percentage rollouts, user targeting, environment-scoped API keys and an audit log; verified by 192 backend tests against real PostgreSQL/Redis and 11 Playwright end-to-end tests.
* Implemented a Redis cache-aside layer with post-commit invalidation, TTLs, a circuit breaker and recovery purge so the evaluation API stays correct when Redis fails; measured cache-hit vs database-path latency with a reproducible benchmark (≈9.8 ms vs ≈14.7 ms p50 on a single local machine).
* Designed a secure admin and API surface (Argon2id, server-side sessions, CSRF + Origin validation, hashed per-environment keys, Redis-backed rate limiting) and documented the threat assumptions and limitations in an architecture write-up with Mermaid diagrams.

## How to explain it in an interview (≈60 seconds)
"FlagPilot is a feature-flag service I built to understand how gradual releases work. A flag has a separate configuration per environment. When an app asks whether user X gets a feature, the backend checks a fixed order: kill switch, whether the flag is on, an exclusion list, an inclusion list, then a percentage rollout. The percentage part hashes flag, environment and user with SHA-256 into one of 10,000 buckets, so the same user always gets the same answer and raising the percentage only adds users. Reads come from a Redis cache that I invalidate after each database commit, with a TTL as a safety net, and if Redis dies the service falls back to Postgres through a circuit breaker. Admins use a session cookie with CSRF protection; applications use hashed, environment-scoped API keys. I tested it against real Postgres and Redis, including simulated outages, and with Playwright through the real UI. Known limits: it's a demo-scale auth model, exact-user targeting only, and my benchmark is a single-machine comparison, not a capacity claim."

*Nothing here claims real users, customers, production deployment or production-scale performance; the project has only been run locally.*
