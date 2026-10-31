from tests.conftest import TEST_ADMIN_EMAIL

AUDIT = "/api/v1/admin/audit"


def actions(admin, **params):
    return [e["action"] for e in admin.get(AUDIT, params=params).json()["items"]]


def test_flag_lifecycle_is_audited_newest_first(admin):
    admin.create_flag("audited", "Audited", "desc")
    admin.configure("audited", "development", enabled=True)
    admin.configure("audited", "development", rollout_percentage=25)
    admin.configure("audited", "development", rollout_percentage=50)
    admin.configure("audited", "development", included_users=["a", "b"], excluded_users=["z"])
    admin.configure("audited", "development", kill_switch=True)
    admin.configure("audited", "development", kill_switch=False)
    admin.configure("audited", "development", enabled=False)
    admin.post("/api/v1/admin/flags/audited/archive")
    admin.post("/api/v1/admin/flags/audited/restore")
    assert actions(admin, flag_key="audited") == [
        "flag.restored",
        "flag.archived",
        "flag.disabled",
        "flag.kill_switch_cleared",
        "flag.kill_switch_activated",
        "flag.targeting_updated",
        "flag.rollout_changed",
        "flag.rollout_changed",
        "flag.enabled",
        "flag.created",
    ]


def test_audit_events_carry_actor_timestamp_environment_and_change_details(admin):
    admin.create_flag("detail")
    admin.configure("detail", "production", rollout_percentage=20)
    admin.configure("detail", "production", rollout_percentage=45)
    events = admin.get(AUDIT, params={"flag_key": "detail"}).json()["items"]
    latest = events[0]
    assert latest["actor"] == TEST_ADMIN_EMAIL
    assert latest["action"] == "flag.rollout_changed" and latest["environment"] == "production"
    assert latest["details"] == {"from": 20, "to": 45}
    assert latest["created_at"] and events[0]["created_at"] >= events[1]["created_at"]


def test_targeting_audit_details_show_added_and_removed_users(admin):
    admin.create_flag("tgt")
    admin.configure("tgt", included_users=["a", "b"])
    admin.configure("tgt", included_users=["b", "c"], excluded_users=["x"])
    e = admin.get(AUDIT, params={"flag_key": "tgt"}).json()["items"][0]
    assert e["details"] == {"included_added": ["c"], "included_removed": ["a"], "excluded_added": ["x"], "excluded_removed": []}


def test_one_request_changing_several_things_writes_several_events(admin):
    admin.create_flag("multi")
    admin.configure("multi", enabled=True, rollout_percentage=10, kill_switch=True)
    assert sorted(actions(admin, flag_key="multi")[:3]) == ["flag.enabled", "flag.kill_switch_activated", "flag.rollout_changed"]


def test_metadata_change_is_audited(admin):
    admin.create_flag("meta2", "Before")
    admin.patch("/api/v1/admin/flags/meta2", {"name": "After"})
    e = admin.get(AUDIT, params={"flag_key": "meta2"}).json()["items"][0]
    assert e["action"] == "flag.updated" and e["details"]["changes"]["name"] == {"from": "Before", "to": "After"}


def test_api_key_events_are_audited_without_secrets(admin):
    key = admin.post("/api/v1/admin/api-keys", {"name": "svc", "environment": "production"}).json()
    admin.delete(f"/api/v1/admin/api-keys/{key['id']}")
    events = admin.get(AUDIT).json()["items"]
    assert [e["action"] for e in events[:2]] == ["api_key.revoked", "api_key.created"]
    assert key["key"] not in str(events)


def test_failed_requests_leave_no_audit_trail(admin):
    admin.create_flag("clean")
    admin.create_flag("clean")  # 409
    admin.configure("clean", rollout_percentage=500)  # 422
    admin.configure("clean", enabled=True, included_users=["a"], excluded_users=["a"])  # 422 overlap
    assert actions(admin, flag_key="clean") == ["flag.created"]


def test_audit_pagination_and_filtering(admin):
    for i in range(7):
        admin.create_flag(f"flag-{i}")
    page = admin.get(AUDIT, params={"limit": 3, "offset": 0}).json()
    assert page["total"] == 7 and len(page["items"]) == 3 and page["limit"] == 3
    page2 = admin.get(AUDIT, params={"limit": 3, "offset": 3}).json()
    assert {e["id"] for e in page["items"]}.isdisjoint({e["id"] for e in page2["items"]})
    assert admin.get(AUDIT, params={"flag_key": "flag-2"}).json()["total"] == 1
    assert admin.get(AUDIT, params={"limit": 0}).status_code == 422
    assert admin.get(AUDIT, params={"limit": 1000}).status_code == 422
    assert admin.get(AUDIT, params={"offset": -1}).status_code == 422


def test_demo_seed_is_audited_as_system(app, settings, admin):
    from app.services.bootstrap import seed_demo_flags

    with app.state.session_factory() as db:
        seed_demo_flags(db, app.state.flag_cache)
    events = admin.get(AUDIT, params={"flag_key": "new-dashboard", "limit": 50}).json()["items"]
    assert events and {e["actor"] for e in events} == {"system"}
    # seeding is idempotent: a second run does nothing
    with app.state.session_factory() as db:
        seed_demo_flags(db, app.state.flag_cache)
    assert admin.get("/api/v1/admin/flags").json()["total"] == 3
