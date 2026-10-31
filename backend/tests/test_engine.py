"""Unit tests for the pure evaluation engine (no services needed)."""

import hashlib
import os
import subprocess
import sys

import pytest

from app.engine import BUCKET_COUNT, FlagRuleSet, Reason, compute_bucket, evaluate


def rules(**overrides) -> FlagRuleSet:
    base = dict(
        flag_key="new-dashboard",
        environment="development",
        enabled=True,
        kill_switch=False,
        rollout_percentage=0,
        included_users=frozenset(),
        excluded_users=frozenset(),
    )
    base.update(overrides)
    return FlagRuleSet(**base)


USERS = [f"user-{i}" for i in range(5000)]


# ---------- bucketing ----------


def test_bucket_is_in_range():
    for u in USERS[:500]:
        assert 0 <= compute_bucket("f", "development", u) < BUCKET_COUNT


def test_bucket_is_deterministic():
    assert compute_bucket("f", "production", "alice") == compute_bucket("f", "production", "alice")


def test_bucket_is_stable_across_processes_with_different_hash_seeds():
    """Proves we do not depend on Python's randomised hash()."""
    expected = compute_bucket("new-dashboard", "development", "alice")
    code = "from app.engine import compute_bucket;print(compute_bucket('new-dashboard','development','alice'))"
    for seed in ("1", "12345", "random"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
        assert int(out.stdout.strip()) == expected


@pytest.mark.parametrize(
    "flag,env,user",
    [("new-dashboard", "development", "alice"), ("x", "production", "ü-ñ-user"), ("a-b", "production", "")],
)
def test_bucket_matches_documented_algorithm(flag, env, user):
    """Re-implements the documented algorithm independently: sha256(flag US env US user)[:8] % 10000."""
    digest = hashlib.sha256(f"{flag}\x1f{env}\x1f{user}".encode()).digest()
    assert compute_bucket(flag, env, user) == int.from_bytes(digest[:8], "big") % 10000


def test_bucket_depends_on_environment_and_flag():
    differing_env = sum(
        compute_bucket("f", "development", u) != compute_bucket("f", "production", u) for u in USERS[:200]
    )
    assert differing_env > 190
    differing_flag = sum(compute_bucket("f", "development", u) != compute_bucket("g", "development", u) for u in USERS[:200])
    assert differing_flag > 190


def test_field_separator_prevents_ambiguity():
    assert compute_bucket("ab", "c", "d") != compute_bucket("a", "bc", "d")
    assert compute_bucket("a", "b", "c") != compute_bucket("a", "bc", "")


def test_bucket_distribution_is_roughly_uniform():
    n = 20000
    buckets = [compute_bucket("flag", "production", f"u{i}") for i in range(n)]
    for pct in (10, 25, 50, 90):
        share = sum(b < pct * 100 for b in buckets) / n
        assert abs(share - pct / 100) < 0.015, (pct, share)


# ---------- percentage rollout ----------


def test_zero_percent_includes_nobody():
    r = rules(rollout_percentage=0)
    results = [evaluate(r, u) for u in USERS]
    assert not any(x.enabled for x in results)
    assert {x.reason for x in results} == {Reason.DEFAULT_DISABLED}


def test_hundred_percent_includes_everybody():
    r = rules(rollout_percentage=100)
    results = [evaluate(r, u) for u in USERS]
    assert all(x.enabled for x in results)
    assert {x.reason for x in results} == {Reason.PERCENTAGE_ROLLOUT}


@pytest.mark.parametrize("pct", [1, 5, 20, 50, 75, 99])
def test_rollout_share_approximates_percentage(pct):
    r = rules(rollout_percentage=pct)
    share = sum(evaluate(r, u).enabled for u in USERS) / len(USERS)
    assert abs(share - pct / 100) < 0.03


def test_raising_rollout_never_removes_users():
    previous: set[str] = set()
    for pct in range(0, 101, 5):
        current = {u for u in USERS if evaluate(rules(rollout_percentage=pct), u).enabled}
        assert previous <= current, f"users lost when raising to {pct}%"
        previous = current
    assert len(previous) == len(USERS)


def test_lowering_rollout_only_removes_users():
    hi = {u for u in USERS if evaluate(rules(rollout_percentage=60), u).enabled}
    lo = {u for u in USERS if evaluate(rules(rollout_percentage=30), u).enabled}
    assert lo <= hi


def test_same_user_same_result_repeatedly():
    r = rules(rollout_percentage=37)
    first = evaluate(r, "carol")
    assert all(evaluate(r, "carol") == first for _ in range(50))


def test_environments_roll_out_independently():
    dev = rules(environment="development", rollout_percentage=50)
    prod = rules(environment="production", rollout_percentage=50)
    differing = sum(evaluate(dev, u).enabled != evaluate(prod, u).enabled for u in USERS[:500])
    assert differing > 100


# ---------- precedence ----------


def test_disabled_flag_wins_over_everything():
    r = rules(enabled=False, rollout_percentage=100, included_users=frozenset({"a"}))
    res = evaluate(r, "a")
    assert (res.enabled, res.reason) == (False, Reason.FLAG_DISABLED)


def test_kill_switch_wins_over_inclusion_and_rollout():
    r = rules(kill_switch=True, rollout_percentage=100, included_users=frozenset({"a"}))
    res = evaluate(r, "a")
    assert (res.enabled, res.reason) == (False, Reason.KILL_SWITCH)


def test_kill_switch_reported_even_when_flag_disabled():
    assert evaluate(rules(kill_switch=True, enabled=False), "a").reason == Reason.KILL_SWITCH


def test_exclusion_beats_inclusion():
    r = rules(rollout_percentage=100, included_users=frozenset({"a"}), excluded_users=frozenset({"a"}))
    res = evaluate(r, "a")
    assert (res.enabled, res.reason) == (False, Reason.USER_EXCLUDED)


def test_exclusion_beats_rollout():
    r = rules(rollout_percentage=100, excluded_users=frozenset({"a"}))
    assert evaluate(r, "a").reason == Reason.USER_EXCLUDED
    assert evaluate(r, "b").enabled is True


def test_inclusion_beats_zero_percent_rollout():
    r = rules(rollout_percentage=0, included_users=frozenset({"vip"}))
    res = evaluate(r, "vip")
    assert (res.enabled, res.reason) == (True, Reason.USER_INCLUDED)
    assert evaluate(r, "someone-else").enabled is False


def test_percentage_applies_to_remaining_users_only():
    r = rules(rollout_percentage=100, included_users=frozenset({"vip"}), excluded_users=frozenset({"banned"}))
    assert evaluate(r, "vip").reason == Reason.USER_INCLUDED
    assert evaluate(r, "banned").reason == Reason.USER_EXCLUDED
    assert evaluate(r, "regular").reason == Reason.PERCENTAGE_ROLLOUT


def test_default_disabled_reports_bucket():
    res = evaluate(rules(rollout_percentage=0), "x")
    assert res.reason == Reason.DEFAULT_DISABLED and res.bucket is not None


def test_archived_flag_is_disabled_even_with_inclusion():
    res = evaluate(rules(archived=True, rollout_percentage=100, included_users=frozenset({"a"})), "a")
    assert (res.enabled, res.reason) == (False, Reason.FLAG_ARCHIVED)


def test_user_ids_are_case_sensitive_and_exact():
    r = rules(included_users=frozenset({"Alice"}))
    assert evaluate(r, "Alice").enabled
    assert not evaluate(r, "alice").enabled
    assert not evaluate(r, "Alice ").enabled


def test_unusual_user_ids_do_not_crash():
    r = rules(rollout_percentage=50)
    for u in ["", "ユーザー", "😀", "a" * 256, "with space", "x\ty"]:
        evaluate(r, u)
