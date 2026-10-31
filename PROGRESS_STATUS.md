# FlagPilot — Progress Status

_Last updated: pre-publication verification (2026-10-21). All milestones M1–M10 complete; verification fixes applied._

## Current milestone
Done. Only optional polish remains (see "Next steps").

## Completed (all verified by running them; details in TEST_REPORT.md)
- Docker Desktop installed via winget (user approved the UAC prompt). `docker.exe`: `C:\Program Files\Docker\Docker\resources\bin` (add to PATH in a fresh shell if `docker` is not found).
- `scripts/setup.py` generates `.env` (git-ignored); `docker-compose.yml` runs postgres, redis, backend (:8000), frontend (:3000) with health checks. Clean-slate `docker compose down -v` + `up --build -d` verified.
- Backend: config, JSON logging, models, Alembic 0001, pure evaluation engine, Redis cache (+ circuit breaker + recovery purge), rate limiter (Redis + in-memory fallback), Argon2 admin, DB sessions, CSRF/Origin, env-scoped hashed API keys, flag CRUD, audit, stats, playground evaluate, health (ok/degraded/unavailable), bootstrap + demo seed.
- Frontend: login, overview, flags list (quick toggles), flag editor, playground (real backend), audit log, API keys, public demo app + server route holding keys.
- Tests: backend 186 passed (incl. 2 live-stack); Vitest 9 passed; typecheck/lint/build pass; Playwright 11 passed.
- Benchmark: `benchmarks/bench_evaluate.py` (results in TEST_REPORT.md, `benchmarks/results/latest.json`).
- Screenshots: `portfolio/screenshots/01..05-*.png` (real app).
- Docs: README, ARCHITECTURE, TEST_REPORT, PORTFOLIO_SUMMARY, CLAUDE, IMPLEMENTATION_PLAN.

## Important decisions
- Sync SQLAlchemy 2 + psycopg 3; DB-backed sessions; Next.js rewrites `/api/v1/*` to the backend (same-origin cookies); demo API keys stay server-side.
- Bucket = SHA-256(flag \x1f env \x1f user)[:8] mod 10000; in iff bucket < pct*100.
- Redis guard: 5 s circuit breaker; recovery hook purges `fp:flag:*`.
- Evaluation failure = 503 (clients fail closed); unknown flag = 200 off `flag_not_found`.
- Tests/benchmarks use 127.0.0.1, not `localhost` (IPv6 resolution made every connection ~1–2 s slower on Windows).
- Playwright `getByRole("alert")` collides with Next's route announcer; scope alerts to dialogs/text.

## Known bugs / limitations
- No open bugs. Limitations are listed in README.md and TEST_REPORT.md (demo-grade auth, bounded stale-cache race, `npm audit` advisories needing breaking upgrades, Chromium-only e2e).
- Found and fixed during build: wrong `raw or` falsy-dict test helper; `slugify` kept combining accents (caught by a Vitest test); Redis recovery could serve entries whose invalidation was skipped (fixed with recovery purge).

## Blockers
None.

## Next steps (optional)
1. Firefox/WebKit Playwright projects; mobile viewport screenshots.
2. Versioned cache keys to remove the documented stale-SET race.
3. GitHub Actions workflow running the suites (the owner will create the repo; no Git was used).
4. Re-run `npm audit` and bump Next when a patched release is available.

## Restart commands
```powershell
$env:Path += ";C:\Program Files\Docker\Docker\resources\bin"
cd <project folder>
python scripts/setup.py --show        # prints demo login (creates .env if missing)
docker compose up --build -d
cd backend; .\.venv\Scripts\python -m pytest -q            # needs postgres+redis running
cd ..\frontend; npm run typecheck; npm run lint; npm test; npm run build; npm run e2e
```

## Pre-publication verification (2026-10-21)
Backend 192 passed, Vitest 9, Playwright 11 (twice back-to-back), typecheck/lint/build clean. Fixed: login rate-limit bypass via spoofed X-Forwarded-For (`TRUSTED_PROXY_HOPS`, default 0), stale API-key cache after Redis outage, broken Mermaid diagram, non-repeatable e2e, sharp upgraded + `/_next/image` disabled. Full detail: TEST_REPORT.md. Remaining: 7 npm advisories needing a Next 16 major / ESLint downgrade; no LICENSE or CI workflow yet (owner decisions).
