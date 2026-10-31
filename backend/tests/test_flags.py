import pytest

BASE = "/api/v1/admin/flags"


def test_create_flag_creates_independent_default_configs(admin):
    r = admin.create_flag("new-dashboard", "New dashboard", "Redesign")
    assert r.status_code == 201
    flag = r.json()
    assert flag["key"] == "new-dashboard" and flag["archived"] is False
    assert set(flag["environments"]) == {"development", "production"}
    for env in flag["environments"].values():
        assert env["enabled"] is False and env["rollout_percentage"] == 0
        assert env["included_users"] == [] and env["excluded_users"] == [] and env["kill_switch"] is False


def test_duplicate_key_conflicts(admin):
    assert admin.create_flag("dup").status_code == 201
    r = admin.create_flag("dup", "Other name")
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"


@pytest.mark.parametrize("key", ["UPPER", "has space", "-lead", "trail-", "a" * 65, "emoji😀", "", "semi;colon", "slash/key"])
def test_invalid_keys_rejected(admin, key):
    assert admin.create_flag(key).status_code == 422


@pytest.mark.parametrize("key", ["a", "ab", "a-b_c", "x" * 64, "0day"])
def test_valid_keys_accepted(admin, key):
    assert admin.create_flag(key).status_code == 201


def test_name_validation(admin):
    assert admin.create_flag("n1", "").status_code == 422
    assert admin.create_flag("n2", "   ").status_code == 422
    assert admin.create_flag("n3", "x" * 121).status_code == 422
    assert admin.create_flag("n4", "ok", "d" * 1001).status_code == 422
    assert admin.post(BASE, {"key": "n5"}).status_code == 422  # name required
    assert admin.post(BASE, {"key": "n6", "name": "x", "bogus": 1}).status_code == 422  # unknown field


def test_malformed_json_returns_safe_error(admin):
    r = admin.http.post(
        BASE, content=b"{not json", headers={"Origin": "http://localhost:3000", "X-CSRF-Token": admin.csrf, "Content-Type": "application/json"}
    )
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_validation_errors_do_not_echo_submitted_values(admin):
    r = admin.post(BASE, {"key": "ok", "name": "x", "description": 12345})
    assert r.status_code == 422
    assert "12345" not in r.text


def test_get_flag_and_not_found(admin):
    admin.create_flag("exists")
    assert admin.get(f"{BASE}/exists").json()["key"] == "exists"
    r = admin.get(f"{BASE}/missing")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert admin.get(f"{BASE}/Bad Key").status_code == 422


def test_list_flags_and_search_and_archived_filter(admin):
    admin.create_flag("alpha-feature", "Alpha")
    admin.create_flag("beta-feature", "Beta thing")
    admin.create_flag("gamma", "Gamma")
    admin.post(f"{BASE}/gamma/archive")
    keys = lambda r: {f["key"] for f in r.json()["items"]}  # noqa: E731
    assert keys(admin.get(BASE)) == {"alpha-feature", "beta-feature"}
    assert keys(admin.get(BASE, params={"include_archived": True})) == {"alpha-feature", "beta-feature", "gamma"}
    assert keys(admin.get(BASE, params={"search": "BETA"})) == {"beta-feature"}
    assert keys(admin.get(BASE, params={"search": "thing"})) == {"beta-feature"}
    assert admin.get(BASE, params={"search": "%"}).json()["total"] == 0  # LIKE wildcards are escaped


def test_search_is_safe_against_sql_metacharacters(admin):
    admin.create_flag("safe-flag")
    r = admin.get(BASE, params={"search": "'; DROP TABLE flags; --"})
    assert r.status_code == 200 and r.json()["total"] == 0
    assert admin.get(BASE).json()["total"] == 1


def test_update_metadata_only(admin):
    admin.create_flag("meta", "Old", "old desc")
    r = admin.patch(f"{BASE}/meta", {"name": "New name"})
    assert r.status_code == 200 and r.json()["name"] == "New name" and r.json()["description"] == "old desc"
    assert admin.patch(f"{BASE}/meta", {}).status_code == 422
    assert admin.patch(f"{BASE}/missing", {"name": "x"}).status_code == 404


def test_flag_key_is_immutable(admin):
    admin.create_flag("keep-key")
    assert admin.patch(f"{BASE}/keep-key", {"key": "renamed"}).status_code == 422


def test_configure_environment_partially(admin):
    admin.create_flag("cfg")
    r = admin.configure("cfg", "development", enabled=True, rollout_percentage=40)
    assert r.status_code == 200
    dev = r.json()["environments"]["development"]
    assert dev["enabled"] is True and dev["rollout_percentage"] == 40 and dev["version"] == 2
    r = admin.configure("cfg", "development", included_users=["alice", "bob"])
    dev = r.json()["environments"]["development"]
    assert dev["enabled"] is True and dev["rollout_percentage"] == 40  # untouched fields survive a partial update
    assert dev["included_users"] == ["alice", "bob"]


def test_environments_are_independent(admin):
    admin.create_flag("iso")
    admin.configure("iso", "development", enabled=True, rollout_percentage=75, included_users=["a"], kill_switch=False)
    flag = admin.get(f"{BASE}/iso").json()
    prod = flag["environments"]["production"]
    assert (prod["enabled"], prod["rollout_percentage"], prod["included_users"], prod["version"]) == (False, 0, [], 1)
    admin.configure("iso", "production", enabled=True, rollout_percentage=5)
    dev = admin.get(f"{BASE}/iso").json()["environments"]["development"]
    assert (dev["enabled"], dev["rollout_percentage"], dev["included_users"]) == (True, 75, ["a"])


@pytest.mark.parametrize("pct", [-1, 101, 1000])
def test_rollout_range_validated(admin, pct):
    admin.create_flag("range")
    assert admin.configure("range", rollout_percentage=pct).status_code == 422


@pytest.mark.parametrize("pct", [0, 1, 50, 99, 100])
def test_rollout_boundaries_accepted(admin, pct):
    admin.create_flag("range")
    assert admin.configure("range", rollout_percentage=pct).status_code == 200


def test_rollout_must_be_integer(admin):
    admin.create_flag("types")
    assert admin.configure("types", rollout_percentage="fifty").status_code == 422
    assert admin.configure("types", rollout_percentage=12.5).status_code == 422
    assert admin.configure("types", enabled="yes-please").status_code == 422


def test_invalid_environment_and_unknown_flag(admin):
    admin.create_flag("envs")
    r = admin.patch(f"{BASE}/envs/environments/staging", {"enabled": True})
    assert r.status_code == 422
    assert admin.configure("ghost", enabled=True).status_code == 404


def test_empty_config_update_rejected(admin):
    admin.create_flag("empty")
    assert admin.configure("empty").status_code == 422


def test_user_lists_validation(admin):
    admin.create_flag("users")
    assert admin.configure("users", included_users=["a", "a"]).status_code == 422  # duplicates
    assert admin.configure("users", included_users=[""]).status_code == 422
    assert admin.configure("users", included_users=["x" * 257]).status_code == 422
    assert admin.configure("users", included_users=["bad\nid"]).status_code == 422
    assert admin.configure("users", included_users=[f"u{i}" for i in range(501)]).status_code == 422
    assert admin.configure("users", included_users=[1, 2]).status_code == 422


def test_user_cannot_be_included_and_excluded(admin):
    admin.create_flag("overlap")
    r = admin.configure("overlap", included_users=["a", "b"], excluded_users=["b"])
    assert r.status_code == 422 and "b" in r.json()["error"]["message"]
    admin.configure("overlap", included_users=["a"])
    r = admin.configure("overlap", excluded_users=["a"])  # conflicts with the stored list, not just the request
    assert r.status_code == 422


def test_noop_update_does_not_bump_version_or_audit(admin):
    admin.create_flag("noop")
    admin.configure("noop", enabled=True)
    before = admin.get(f"{BASE}/noop").json()["environments"]["development"]["version"]
    assert admin.configure("noop", enabled=True).status_code == 200
    after = admin.get(f"{BASE}/noop").json()["environments"]["development"]["version"]
    assert before == after
    events = admin.get("/api/v1/admin/audit", params={"flag_key": "noop"}).json()["items"]
    assert [e["action"] for e in events] == ["flag.enabled", "flag.created"]


def test_archive_and_restore(admin):
    admin.create_flag("arch")
    r = admin.post(f"{BASE}/arch/archive")
    assert r.status_code == 200 and r.json()["archived"] is True and r.json()["archived_at"]
    assert admin.post(f"{BASE}/arch/archive").status_code == 409
    assert admin.configure("arch", enabled=True).status_code == 409  # archived flags are read-only
    r = admin.post(f"{BASE}/arch/restore")
    assert r.status_code == 200 and r.json()["archived"] is False
    assert admin.post(f"{BASE}/arch/restore").status_code == 409
    assert admin.configure("arch", enabled=True).status_code == 200
    assert admin.post(f"{BASE}/ghost/archive").status_code == 404


def test_updated_at_reflects_latest_change(admin):
    flag = admin.create_flag("stamp").json()
    changed = admin.configure("stamp", enabled=True).json()
    assert changed["updated_at"] > flag["updated_at"]
    assert changed["environments"]["development"]["updated_at"] == changed["updated_at"]


def test_stats_reflect_real_data(admin):
    admin.create_flag("s1")
    admin.create_flag("s2")
    admin.create_flag("s3")
    admin.configure("s1", "development", enabled=True)
    admin.configure("s2", "development", enabled=True)
    admin.configure("s2", "production", enabled=True)
    admin.post(f"{BASE}/s3/archive")
    stats = admin.get("/api/v1/admin/stats").json()
    assert (stats["total_flags"], stats["active_flags"], stats["archived_flags"]) == (3, 2, 1)
    assert stats["environments"]["development"] == {"enabled": 2, "disabled": 0}
    assert stats["environments"]["production"] == {"enabled": 1, "disabled": 1}
    assert stats["recent_events"] and stats["recent_events"][0]["flag_key"] == "s3"


def test_unknown_route_and_method_use_error_shape(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = client.get("/api/v1/evaluate")
    assert r.status_code == 405 and r.json()["error"]["code"] == "method_not_allowed"
