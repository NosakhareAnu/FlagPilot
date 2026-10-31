#!/usr/bin/env python3
"""Reproducible, lightweight benchmark of POST /api/v1/evaluate: Redis-cache hit vs forced miss (PostgreSQL path).

Prerequisites (the default EVAL_RATE_LIMIT of 600/min would otherwise throttle the run):
    $env:EVAL_RATE_LIMIT = "1000000"; docker compose up -d backend
    backend\\.venv\\Scripts\\python benchmarks\\bench_evaluate.py [--requests 1500] [--concurrency 8]

Everything runs on ONE developer machine with client, API, PostgreSQL and Redis competing for the same CPU, so the
numbers are only useful for comparing the two paths against each other, not as capacity claims.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import redis

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip()
    return values


def pct(sorted_ms: list[float], p: float) -> float:
    return sorted_ms[min(len(sorted_ms) - 1, int(len(sorted_ms) * p))]


def summarize(name: str, latencies: list[float], wall: float, headers: list[str]) -> dict:
    ms = sorted(x * 1000 for x in latencies)
    out = {
        "scenario": name,
        "requests": len(ms),
        "wall_seconds": round(wall, 3),
        "throughput_rps": round(len(ms) / wall, 1),
        "latency_ms": {
            "mean": round(statistics.fmean(ms), 2),
            "p50": round(pct(ms, 0.50), 2),
            "p95": round(pct(ms, 0.95), 2),
            "p99": round(pct(ms, 0.99), 2),
            "max": round(ms[-1], 2),
        },
        "cache_header_counts": {h: headers.count(h) for h in sorted(set(headers))},
    }
    print(f"{name:34s} n={out['requests']:5d}  {out['throughput_rps']:8.1f} req/s  "
          f"p50={out['latency_ms']['p50']:6.2f}ms p95={out['latency_ms']['p95']:6.2f}ms p99={out['latency_ms']['p99']:6.2f}ms  "
          f"cache={out['cache_header_counts']}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--requests", type=int, default=1500)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--redis", default="redis://127.0.0.1:6379/0")
    args = ap.parse_args()

    env = load_env()
    key = env["BOOTSTRAP_API_KEY_DEVELOPMENT"]
    auth = {"Authorization": f"Bearer {key}"}
    r = redis.Redis.from_url(args.redis, decode_responses=True)
    cache_key = "fp:flag:development:new-dashboard"
    body = lambda i: {"flag_key": "new-dashboard", "user_id": f"bench-user-{i}"}  # noqa: E731

    client = httpx.Client(base_url=args.url, headers=auth, timeout=10)
    probe = client.post("/api/v1/evaluate", json=body(0))
    if probe.status_code != 200:
        print(f"probe failed: {probe.status_code} {probe.text}", file=sys.stderr)
        return 1
    if probe.headers.get("x-ratelimit-limit") and int(probe.headers["x-ratelimit-limit"]) < args.requests * 3:
        print(f"WARNING: rate limit is {probe.headers['x-ratelimit-limit']}/min; restart backend with EVAL_RATE_LIMIT=1000000 "
              "or results will contain 429s", file=sys.stderr)

    results = []

    def sequential(name: str, before=None) -> dict:
        lat, hdr = [], []
        start = time.perf_counter()
        for i in range(args.requests):
            if before:
                before()
            t = time.perf_counter()
            resp = client.post("/api/v1/evaluate", json=body(i))
            lat.append(time.perf_counter() - t)
            if resp.status_code != 200:
                print(f"non-200 during run: {resp.status_code}", file=sys.stderr)
                sys.exit(2)
            hdr.append(resp.headers.get("x-flagpilot-cache", "?"))
        return summarize(name, lat, time.perf_counter() - start, hdr)

    # warm-up (JIT-free, but primes connection pools, API-key cache and the flag cache)
    for i in range(100):
        client.post("/api/v1/evaluate", json=body(i))

    # floor: a request that touches neither Redis nor PostgreSQL (client + Docker port-forward + framework overhead)
    lat, start = [], time.perf_counter()
    for _ in range(args.requests):
        t = time.perf_counter()
        client.get("/health/live")
        lat.append(time.perf_counter() - t)
    results.append(summarize("baseline GET /health/live (no deps)", lat, time.perf_counter() - start, ["n/a"]))

    results.append(sequential("sequential, cache HIT"))
    results.append(sequential("sequential, forced cache MISS (DB)", before=lambda: r.delete(cache_key)))

    def concurrent(name: str) -> dict:
        lat, hdr = [], []

        clients = [httpx.Client(base_url=args.url, headers=auth, timeout=10) for _ in range(args.concurrency)]

        def worker(idx: int):
            c = clients[idx]
            l, h = [], []
            for i in range(args.requests // args.concurrency):
                t = time.perf_counter()
                resp = c.post("/api/v1/evaluate", json=body(idx * 100000 + i))
                l.append(time.perf_counter() - t)
                h.append(resp.headers.get("x-flagpilot-cache", f"HTTP{resp.status_code}"))
            return l, h

        start = time.perf_counter()
        with ThreadPoolExecutor(args.concurrency) as pool:
            for l, h in pool.map(worker, range(args.concurrency)):
                lat += l
                hdr += h
        wall = time.perf_counter() - start
        for c in clients:
            c.close()
        return summarize(name, lat, wall, hdr)

    results.append(concurrent(f"concurrent x{args.concurrency}, cache HIT"))

    report = {
        "date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "machine": f"{platform.system()} {platform.release()}, Python {platform.python_version()}",
        "setup": "FastAPI (1 uvicorn worker) + PostgreSQL 16 + Redis 7 in Docker Desktop; client on the same host",
        "requests_per_scenario": args.requests,
        "results": results,
    }
    out_dir = ROOT / "benchmarks" / "results"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved {out_dir / 'latest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
