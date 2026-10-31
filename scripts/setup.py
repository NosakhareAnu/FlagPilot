#!/usr/bin/env python3
"""Create a local `.env` with freshly generated secrets (idempotent: never overwrites an existing .env).

Usage:  python scripts/setup.py            # create .env if missing
        python scripts/setup.py --show     # print the demo admin login from an existing .env

The generated .env is git-ignored. `.env.example` documents every variable with non-secret placeholders.
"""

from __future__ import annotations

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"

GENERATED = {
    "POSTGRES_PASSWORD": lambda: secrets.token_urlsafe(24),
    "ADMIN_PASSWORD": lambda: secrets.token_urlsafe(15),
    "BOOTSTRAP_API_KEY_DEVELOPMENT": lambda: f"fpk_development_{secrets.token_urlsafe(32)}",
    "BOOTSTRAP_API_KEY_PRODUCTION": lambda: f"fpk_production_{secrets.token_urlsafe(32)}",
}


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            values[k.strip()] = v.strip()
    return values


def create() -> None:
    lines = []
    for line in EXAMPLE.read_text(encoding="utf-8").splitlines():
        key, sep, _ = line.partition("=")
        if sep and key.strip() in GENERATED:
            line = f"{key.strip()}={GENERATED[key.strip()]()}"
        lines.append(line)
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Created {ENV_FILE} with generated local secrets (git-ignored).")


def main() -> int:
    if not EXAMPLE.exists():
        print(".env.example not found", file=sys.stderr)
        return 1
    if "--show" not in sys.argv:
        if ENV_FILE.exists():
            print(".env already exists - leaving it untouched.")
        else:
            create()
    if not ENV_FILE.exists():
        return 1
    env = read_env(ENV_FILE)
    print("\nDemo administrator login (local only):")
    print(f"  email:    {env.get('ADMIN_EMAIL')}")
    print(f"  password: {env.get('ADMIN_PASSWORD')}")
    print("\nDashboard: http://localhost:3000   API docs: http://localhost:8000/docs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
