# FlagPilot — Test Report

All results below were produced by actually running the commands on **2026-10-20** on the development machine
(Windows 11, 15 GB RAM, Docker Desktop 29.9.1 / Compose 5.6, Python 3.13.1 host venv, Node 22.13). Before the final run the
stack was rebuilt from a clean slate: `docker compose down -v`, `.env` deleted and regenerated with `python scripts/setup.py`,
`docker compose up --build -d`.

## Summary

| Suite | Command | Result |
|---|---|---|
| Backend unit + integration (real PostgreSQL & Redis) + live HTTP | `cd backend; $env:FLAGPILOT_LIVE_URL="http://127.0.0.1:8000"; .\.venv\Scripts\python -m pytest -q` | **192 passed** in 113 s (re-run 2026-10-21 after the fixes below) |
| Frontend type check | `cd frontend; npm run typecheck` | pass (0 errors) |
| Frontend lint | `npm run lint` | pass (0 errors, 0 warnings) |
| Frontend unit/component tests (Vitest) | `npm test` | **9 passed** (2 files) |
| Frontend production build | `npm run build` | pass (10 routes) |
| Browser end-to-end (Playwright, Chromium, real stack) | `npm run e2e` (`npx playwright test e2e/flagpilot.spec.ts`) | **11 passed** in 25 s |
| Screenshots | `npx playwright test e2e/screenshots.spec.ts` | passed; 5 PNGs in `portfolio/screenshots/` |
| Benchmark | `backend\.venv\Scripts\python benchmarks\bench_evaluate.py` | see below |

Backend tests per file: engine 32 · flags 44 · evaluate (API + API keys + playground) 37 · auth 17 · cache/Redis outage 15 · health/schema/constraints 13 · rate limit + DB failure + safe errors + log hygiene 13 · audit 9 · bootstrap 4 · live-stack 2.

## What is covered

**Backend (pytest, no mocks of PostgreSQL/Redis).** The schema is built by running the real Alembic migration into a dedicated `flagpilot_test` database; Redis logical DB 15 is flushed per test. `alembic check` verifies models and migrations agree.
* Flag creation/editing/archiving, key and field validation, unknown fields, malformed JSON, SQL-metacharacter search, 404/409/422 shapes.
* Database constraints enforced by inserting invalid rows directly (bad key, blank name, rollout −1/101, duplicate key, non-array targeting).
* Authentication: Argon2 hash in DB, hashed session token, cookie flags, wrong password vs unknown email indistinguishable, expired/garbage/stolen-after-logout cookies, every admin route 401 when anonymous, CSRF token required, foreign/absent Origin rejected, evaluation key cannot act as dashboard credential, login rate limit.
* Evaluation: key auth failures, **environment isolation** (key decides environment; body cannot override; changing prod does not affect dev), 0 %/100 %, determinism and monotonic rollout over HTTP, inclusion/exclusion/kill-switch precedence, unknown/archived flags, 10 invalid request shapes.
* Engine unit tests: SHA-256 algorithm re-implemented independently, stability across processes with different `PYTHONHASHSEED`, uniform distribution, monotonicity for raising the rollout in steps of 5 % over 5 000 users, full precedence matrix.
* Redis: first request MISS then HIT, TTL present, per-environment keys, invalidation only for the changed environment, every kind of change visible immediately after invalidation, archive/restore, negative caching + creation invalidation, TTL bound when invalidation is lost, corrupt entry treated as miss, **Redis outage** (200 from PostgreSQL, `BYPASS`, circuit open without per-request penalty, health `degraded`, admin writes still work), **recovery** (cache repopulates), invalidations skipped during outage reconciled on recovery.
* Rate limiting: 429 + `Retry-After`/`X-RateLimit-*`, per-key budgets, in-memory fallback with Redis down, repeated bad credentials throttled, admin limit.
* Database failure: safe 503 body without stack trace/driver names, readiness 503 while liveness 200, cached flags still served during a database outage, recovery after the database returns.
* Audit: each action type recorded with actor/environment/details, ordering, pagination, filtering, no audit rows for failed requests, no secrets in audit data.
* Log hygiene: API keys, passwords and CSRF tokens never appear in captured logs.
* Live tests (`test_live_stack.py`): HTTP calls against the running containers: health, create → enable → evaluate → cache HIT → invalidate → prod isolation → 401.

**Browser E2E (Playwright, real stack, no mocked responses).** 1) protected routes redirect when signed out and protected API returns 401; 2) wrong-password message; 3) login; 4) create a flag (and duplicate-key rejection); 5) configure rollout, evaluate in the playground (`default_disabled`), change rollout to 100 % from the playground and observe `percentage_rollout`, exclude a user (`user_excluded`), kill switch (`kill_switch`), production still `flag_disabled`; 6) audit log shows the real events; 7) flags table independent environments and quick toggle; 8) API key create (secret shown once) → works → revoke → 401; 9) the public demo app switches from the new to the legacy dashboard within seconds of a kill switch in the dashboard (no reload) and back; 10) logout, session dead, protected routes inaccessible, back button does not expose content; 11) cleanup.

## Performance measurements (benchmark)

`benchmarks/bench_evaluate.py`: 1 500 requests per scenario after 100 warm-up requests; FastAPI with **one** uvicorn worker, PostgreSQL 16 and Redis 7 in Docker Desktop, load generator (`httpx`, Python) on the same Windows host, `EVAL_RATE_LIMIT` raised to 1 000 000 for the run (restored afterwards). Raw output: `benchmarks/results/latest.json`.

| Scenario | Throughput | p50 | p95 | p99 | Cache header counts |
|---|---|---|---|---|---|
| Baseline `GET /health/live` (no dependencies) | 237 req/s | 4.09 ms | 5.17 ms | 6.18 ms | n/a |
| Evaluate, sequential, **cache hit** | 101 req/s | 9.79 ms | 11.44 ms | 12.63 ms | HIT 1500 |
| Evaluate, sequential, **forced cache miss** (key deleted before each request → PostgreSQL) | 61 req/s | 14.71 ms | 16.75 ms | 18.50 ms | MISS 1500 |
| Evaluate, 8 concurrent clients, cache hit | 119 req/s | 65.85 ms | 78.45 ms | 92.28 ms | HIT 1496 |

Reading the numbers honestly: on this machine a cache hit is ~5 ms (≈33 %) faster at p50 than the PostgreSQL path, and the ~4 ms baseline shows how much of every request is client + Docker-Desktop-for-Windows port-forwarding + framework overhead. Absolute latencies are dominated by that overhead (each Redis/PostgreSQL round trip crosses the Docker VM boundary); the concurrent run is limited by the single Python worker and the load generator sharing the CPU. **These are local, single-machine measurements for comparing the two code paths. They do not predict production capacity.** An earlier run before a small optimisation (skipping a Redis failure-counter lookup for already-cached valid keys) measured a hit p50 of ≈10.2 ms vs 9.8 ms now, within run-to-run noise.

## Integration verification checklist
* PostgreSQL migrations apply from an empty volume; Redis and Postgres healthy; backend healthy; frontend healthy (`docker compose ps`).
* Frontend → backend through the Next.js proxy verified by Playwright and curl (login cookie is `HttpOnly; SameSite=Lax`).
* Admin changes affect subsequent evaluations (pytest + live + Playwright demo test).

## Remaining limitations / not tested
* Only Chromium was tested in Playwright; no Firefox/WebKit, no mobile-device emulation (layout is responsive by CSS but was only inspected at desktop size).
* No load testing beyond the lightweight benchmark; no multi-worker/multi-replica test (the in-memory rate-limit fallback is per process).
* The cache race described in ARCHITECTURE.md (stale `SET` after `DEL`) is documented and bounded by TTL, but not reproduced by a deterministic test.
* No HTTPS test (`COOKIE_SECURE=true`); no accessibility audit tooling was run.
* `npm audit` still reports 7 advisories after the `sharp` fix (see the 2026-10-21 section). They need a Next 16 major upgrade or a nonsensical ESLint-config downgrade, so they were left and are recorded here rather than hidden.

## Final acceptance checklist

| Criterion | Status | Evidence |
|---|---|---|
| Complete app exists locally | ✅ | repo tree |
| Documented setup works | ✅ | clean-slate `setup.py` + `docker compose up --build -d` |
| PostgreSQL and Redis operate | ✅ | health `ok`; tests |
| Backend starts and responds | ✅ | live tests |
| Frontend communicates with backend | ✅ | Playwright |
| Auth works, protected endpoints enforce access | ✅ | auth tests, e2e |
| Flags can be created and managed | ✅ | flags tests, e2e |
| Dev/prod independent | ✅ | isolation tests, e2e |
| Percentage rollout correct | ✅ | engine tests |
| Targeting rules correct | ✅ | engine + API tests |
| Redis caching + invalidation | ✅ | cache tests |
| Playground calls real backend | ✅ | e2e (asserts engine reasons) |
| Demo app responds to flag changes | ✅ | e2e test 9 |
| Audit history records real changes | ✅ | audit tests, e2e |
| Backend + integration tests pass | ✅ | 192 passed |
| Frontend checks + build pass | ✅ | typecheck, lint, vitest, build |
| E2E browser workflows pass | ✅ | 11 passed |
| Limitations documented | ✅ | this file, ARCHITECTURE.md, README |
| README + architecture complete | ✅ | |
| Portfolio material prepared | ✅ | `PORTFOLIO_SUMMARY.md`, `portfolio/screenshots/` |
| No Git operations | ✅ | none were run |

## Pre-publication verification (2026-10-21)

Re-ran everything against the stack rebuilt with the fixes. Results: backend **192 passed**; `npm run typecheck` exit 0; `npm run lint` clean; Vitest **9 passed**; `npm run build` ok; Playwright **11 passed**, run twice back-to-back to prove repeatability; all six Mermaid diagrams validated with the real Mermaid 11 parser.

**Defects found and fixed in this pass**
1. **Login rate limit bypass (security, high).** The API trusted the *first* `X-Forwarded-For` entry, which a client controls. Reproduced: 13 failed logins with a different spoofed header each returned 401 each time (via the frontend and directly). Measured that Next.js rewrites forward the client header unchanged and add no client address, so the header is untrustworthy behind this proxy. Fix: `TRUSTED_PROXY_HOPS` (default 0 = ignore the header; N = use the N-th entry from the right). After the fix the same probe gives 401 ×10 then 429 ×3 both ways. 5 new tests in `tests/test_client_ip.py`. Trade-off documented: dashboard logins now share one bucket.
2. **Revoked API key could stay valid after a Redis outage (security, medium).** If Redis was unreachable during revocation, the cached "valid" entry survived and the recovery purge only cleared flag entries. Fix: purge `fp:apikey:*` too. Regression test added; confirmed it fails without the fix and passes with it.
3. **Broken Mermaid diagram** in ARCHITECTURE.md (an unescaped `;` broke the authentication sequence diagram). Fixed and re-validated.
4. **e2e not repeatable**: a hard-coded API-key name matched several rows on a used stack, and each run consumed most of the 10/minute login budget. Fixed with a per-run name and by reusing one UI login session across tests (the wrong-password test and the logout test still exercise real login/logout).
5. `sharp` upgraded 0.34.5 → 0.35.5 (patched) via `npm audit fix`; `images.unoptimized` disables the unused `/_next/image` endpoint (404 verified).

**npm advisories (8 → 7).** Remaining: `postcss <=8.5.22` inside `next/node_modules` (1 moderate + 3 high advisories: XSS via `</style>` in stringified CSS, `sourceMappingURL` arbitrary `.map` file read; all require attacker-controlled CSS input, which this app never processes; fix needs Next 16, a major upgrade) and the `eslint-config-next` → `fast-glob` → `micromatch` → `braces` chain (ReDoS-style stack exhaustion on attacker-supplied glob patterns; dev tooling only, never shipped; "fix" is a downgrade to eslint-config-next 14). Neither is reachable by a remote user of the running app.

**Concurrency probe (live stack):** 20 simultaneous creates of one key → exactly 1×201 and 19×409 (no 500s); 40 simultaneous rollout PATCHes → 40×200, stored version/rollout consistent with the audit trail, evaluation correct afterwards.

**Secret scan:** every secret value in `.env` was searched for in all files outside `node_modules/.next/.venv`: no occurrences. No `fpk_…` key-shaped literals in source. `.env` is git-ignored; `.env.example` holds placeholders only. Generated Playwright traces/reports (which can contain typed credentials) are git-ignored and were deleted.
