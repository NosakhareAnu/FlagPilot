"""Pure feature-flag evaluation: no database, no cache, no network.

Precedence (first match wins) — keep in sync with ARCHITECTURE.md:
  1. flag disabled in this environment, or kill switch on  -> disabled
  2. user in excluded list                                  -> disabled
  3. user in included list                                  -> enabled
  4. SHA-256 bucket < rollout percentage                    -> enabled
  5. otherwise                                              -> disabled (default)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

BUCKET_COUNT = 10_000  # basis points: 1 bucket == 0.01 % of users


class Reason(StrEnum):
    FLAG_DISABLED = "flag_disabled"
    KILL_SWITCH = "kill_switch"
    USER_EXCLUDED = "user_excluded"
    USER_INCLUDED = "user_included"
    PERCENTAGE_ROLLOUT = "percentage_rollout"
    DEFAULT_DISABLED = "default_disabled"
    FLAG_ARCHIVED = "flag_archived"
    FLAG_NOT_FOUND = "flag_not_found"


@dataclass(frozen=True, slots=True)
class FlagRuleSet:
    """Everything the evaluator needs about one flag in one environment (JSON-serialisable for caching)."""

    flag_key: str
    environment: str
    enabled: bool
    kill_switch: bool
    rollout_percentage: int
    included_users: frozenset[str]
    excluded_users: frozenset[str]
    archived: bool = False
    version: int = 1


@dataclass(frozen=True, slots=True)
class EvaluationResult:
    enabled: bool
    reason: Reason
    bucket: int | None = None  # only computed when the percentage step is reached


def compute_bucket(flag_key: str, environment: str, user_id: str) -> int:
    """Deterministic bucket in [0, 10000) for (flag, environment, user).

    Uses SHA-256 (not Python's per-process randomised ``hash()``), so every process, restart and language
    runtime agrees. The first 8 bytes of the digest are read as an unsigned big-endian integer and reduced modulo
    BUCKET_COUNT. Modulo bias is negligible: 2**64 is ~1.8e15 times larger than 10 000.
    """
    # \x1f (ASCII unit separator) keeps ("a","bc","d") and ("ab","c","d") from hashing the same bytes.
    material = f"{flag_key}\x1f{environment}\x1f{user_id}".encode()
    digest = hashlib.sha256(material).digest()
    return int.from_bytes(digest[:8], "big") % BUCKET_COUNT


def evaluate(rules: FlagRuleSet, user_id: str) -> EvaluationResult:
    if rules.archived:
        return EvaluationResult(False, Reason.FLAG_ARCHIVED)
    # 1. disabled / kill switch (reported separately so operators can tell why)
    if rules.kill_switch:
        return EvaluationResult(False, Reason.KILL_SWITCH)
    if not rules.enabled:
        return EvaluationResult(False, Reason.FLAG_DISABLED)
    # 2. exclusion beats inclusion
    if user_id in rules.excluded_users:
        return EvaluationResult(False, Reason.USER_EXCLUDED)
    # 3. explicit inclusion
    if user_id in rules.included_users:
        return EvaluationResult(True, Reason.USER_INCLUDED)
    # 4. percentage rollout — a user is in iff bucket < pct*100, so raising pct only ever ADDS users
    bucket = compute_bucket(rules.flag_key, rules.environment, user_id)
    if bucket < rules.rollout_percentage * (BUCKET_COUNT // 100):
        return EvaluationResult(True, Reason.PERCENTAGE_ROLLOUT, bucket)
    # 5. default
    return EvaluationResult(False, Reason.DEFAULT_DISABLED, bucket)
