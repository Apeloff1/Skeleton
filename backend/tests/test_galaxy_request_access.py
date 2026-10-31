"""Real ASGI Galaxy dispatch enforces shared roles and private record scope."""
from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI, Request
import httpx
import pytest

from core import build_vault as vault
from routes import galaxy_studio as galaxy
from routes import gameforge_auth as auth
from routes import galaxy_studio_state as state


@pytest.fixture
def galaxy_http(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "_enforced", lambda: True)
    monkeypatch.setattr(vault, "BUILDS_ROOT", tmp_path)
    users = {
        "owner": {"email": "owner@example.com", "role": "editor", "tenant_id": "tenant-a"},
        "other": {"email": "other@example.com", "role": "editor", "tenant_id": "tenant-a"},
        "viewer": {"email": "owner@example.com", "role": "viewer", "tenant_id": "tenant-a"},
        "admin": {"email": "admin@example.com", "role": "admin", "tenant_id": "tenant-a"},
        "foreign-admin": {"email": "admin@example.com", "role": "admin", "tenant_id": "tenant-b"},
        "install-admin": {"email": "install@example.com", "role": "admin"},
    }

    def authenticated(request: Request):
        return users.get(request.headers.get("x-test-account"))

    app = FastAPI()
    from core.routes_registry import register_routes
    report = register_routes(app, [("routes.galaxy_studio", "router"), ("routes.build_ledger", "router"), ("routes.galaxy_studio_axes", "router"), ("routes.final_build", "router"), ("routes.swarm_planner", "router"), ("routes.text_gamefile", "router"), ("routes.swarm_hub", "router"), ("routes.swarm_cold_legion", "router")])
    assert report["skipped"] == 0
    app.dependency_overrides[auth.get_current_user] = authenticated
    persisted = {}

    async def save(build):
        persisted[build["build_id"]] = dict(build)
        return True

    real_save = galaxy._save_build
    monkeypatch.setattr(galaxy, "_save_build", save)
    previous_builds = dict(galaxy._builds)
    previous_entries = dict(galaxy._vault_entries)
    galaxy._builds.clear()
    galaxy._vault_entries.clear()
    build = galaxy._create_build("Private source", "rpg", "", "Private build", target_files=3)
    build.update(tenant_id="tenant-a", owner_id="owner@example.com", files={"private.txt": "owner source"})
    legacy = galaxy._create_build("Legacy installation build", "rpg", "", "Unowned legacy", target_files=3)
    entry = {"vault_id": "private-artifact", "type": "zip", "build_id": build["build_id"],
             "title": "Private bundle", "filename": "private.zip", "size_human": "1 B", "size_bytes": 1,
             "created_at": "2026-10-23T00:00:00", "tenant_id": "tenant-a", "owner_id": "owner@example.com"}
    galaxy._vault_entries[entry["vault_id"]] = entry

    async def entries():
        return galaxy._vault_entries

    monkeypatch.setattr(state, "get_all_vault_entries", entries)
    import routes.galaxy_studio_vault as vault_routes
    monkeypatch.setattr(vault_routes, "get_all_vault_entries", entries)
    yield SimpleNamespace(app=app, build=build, legacy=legacy, persisted=persisted, users=users, real_save=real_save)
    galaxy._builds.clear()
    galaxy._builds.update(previous_builds)
    galaxy._vault_entries.clear()
    galaxy._vault_entries.update(previous_entries)


async def request(h, method, path, account=None, **kwargs):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=h.app), base_url="http://galaxy.test") as client:
        return await client.request(method, "/api/galaxy-studio" + path,
                                    headers={"x-test-account": account} if account else {}, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize("method,path", [("POST", "/create"), ("GET", "/my-builds"), ("GET", "/vault")])
async def test_anonymous_private_dispatch_requires_authentication(galaxy_http, method, path):
    response = await request(galaxy_http, method, path, json={"title": "Forbidden", "genre": "rpg"} if method == "POST" else None)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_viewer_cannot_create_or_start_and_no_metadata_is_written(galaxy_http):
    h = galaxy_http
    before = set(galaxy._builds)
    for path, body in [("/create", {"title": "Forbidden", "genre": "rpg"}),
                       ("/start-build", {"build_id": h.build["build_id"], "build_duration_minutes": 1})]:
        response = await request(h, "POST", path, "viewer", json=body)
        assert response.status_code == 403
    assert set(galaxy._builds) == before and h.persisted == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("account", ["owner", "admin"])
async def test_authorized_creation_binds_durable_identity_and_ignores_client_ownership(galaxy_http, account):
    h = galaxy_http
    response = await request(h, "POST", "/create", account, json={"title": "Owned build", "genre": "rpg", "target_files": 3,
                                                                 "owner_id": "other@example.com", "tenant_id": "tenant-b"})
    assert response.status_code == 200, response.text
    saved = h.persisted[response.json()["build_id"]]
    assert saved["owner_id"] == h.users[account]["email"] and saved["tenant_id"] == "tenant-a"


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/status/{id}", "/files/{id}", "/file/{id}/private.txt", "/diagnose/{id}", "/build/{id}/ml-config"])
async def test_cross_account_and_cross_tenant_private_reads_are_hidden(galaxy_http, path):
    h = galaxy_http
    for account in ["other", "foreign-admin"]:
        response = await request(h, "GET", path.format(id=h.build["build_id"]), account)
        assert response.status_code == 404, response.text
        assert "owner source" not in response.text and "Private source" not in response.text


@pytest.mark.asyncio
async def test_owning_viewer_and_same_tenant_admin_can_read_and_scope_never_leaks(galaxy_http):
    h = galaxy_http
    for account in ["viewer", "admin"]:
        response = await request(h, "GET", f'/file/{h.build["build_id"]}/private.txt', account)
        assert response.status_code == 200 and "owner source" in response.text
    anonymous = await request(h, "GET", f'/status/{h.build["build_id"]}')
    assert anonymous.status_code == 401
    assert await galaxy._load_build(h.build["build_id"]) is h.build  # request context was released


@pytest.mark.asyncio
async def test_foreign_body_mutation_is_denied_before_starting_work(galaxy_http):
    h = galaxy_http
    response = await request(h, "POST", "/start-build", "other", json={"build_id": h.build["build_id"], "build_duration_minutes": 1})
    assert response.status_code == 404
    assert not galaxy._build_has_live_work(h.build["build_id"])
    assert not h.persisted


@pytest.mark.asyncio
async def test_independently_mounted_galaxy_routers_share_the_same_admission(galaxy_http):
    h = galaxy_http
    assert (await request(h, "GET", "/axes/stats")).status_code == 200
    assert (await request(h, "POST", "/axes/derive", json={})).status_code == 401
    assert (await request(h, "POST", "/axes/derive", "viewer", json={})).status_code == 403
    assert (await request(h, "POST", "/axes/derive", "owner", json={"build_id": h.build["build_id"]})).status_code == 200
    assert (await request(h, "POST", "/axes/derive", "other", json={"build_id": h.build["build_id"]})).status_code == 404
    assert (await request(h, "GET", f'/builds/{h.build["build_id"]}/context', "other")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("content_type", [None, "application/json", "Application/JSON", "application/vnd.galaxy+json; charset=utf-8"])
async def test_query_identity_cannot_mask_a_foreign_json_body(galaxy_http, monkeypatch, content_type):
    h = galaxy_http
    from core import build_ledger
    writes = []
    monkeypatch.setattr(build_ledger, "log", lambda *args, **kwargs: writes.append(args))
    own = await request(h, "POST", "/create", "other", json={"title": "Other own build", "genre": "rpg", "target_files": 3})
    own_id = own.json()["build_id"]
    # The query is authorized but the handler consumes the foreign body ID.
    import json
    headers = {"x-test-account": "other"}
    if content_type:
        headers["content-type"] = content_type
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=h.app), base_url="http://galaxy.test") as client:
        response = await client.post("/api/galaxy-studio/axes/derive?build_id=" + own_id,
                                     headers=headers,
                                     content=json.dumps({"build_id": h.build["build_id"]}))
    assert response.status_code == 404
    assert writes == []


@pytest.mark.asyncio
async def test_text_source_prune_always_requires_one_authorized_explicit_build(galaxy_http, monkeypatch):
    h = galaxy_http
    from core import text_gamefile
    deletions = []
    monkeypatch.setattr(text_gamefile, "prune_gamefiles", lambda build_id: deletions.append(build_id) or {"scope": build_id})
    for body in [None, {}, {"build_id": None}, {"build_id": ""}]:
        for account in ["owner", "admin"]:
            response = await request(h, "POST", "/text-gamefile/prune", account, json=body)
            assert response.status_code in {404, 422}, response.text
    assert (await request(h, "POST", "/text-gamefile/prune", "other", json={"build_id": h.build["build_id"]})).status_code == 404
    assert deletions == []
    own = await request(h, "POST", "/text-gamefile/prune", "owner", json={"build_id": h.build["build_id"]})
    assert own.status_code == 200 and deletions == [h.build["build_id"]]


@pytest.mark.asyncio
async def test_private_lists_filter_records_before_returning_them(galaxy_http, monkeypatch):
    h = galaxy_http
    from core import build_ledger
    monkeypatch.setattr(build_ledger, "list_builds", lambda **kwargs: {"count": 2, "builds": [
        {"build_id": h.build["build_id"], "secret": "own"},
        {"build_id": h.legacy["build_id"], "secret": "legacy"},
    ]})
    own = await request(h, "GET", "/builds", "viewer")
    foreign = await request(h, "GET", "/builds", "other")
    assert own.json() == {"count": 1, "builds": [{"build_id": h.build["build_id"], "secret": "own"}]}
    assert foreign.json() == {"count": 0, "builds": []}


@pytest.mark.asyncio
async def test_library_and_active_jobs_keep_foreign_and_legacy_records_private(galaxy_http, monkeypatch):
    h = galaxy_http
    from services import database
    queries = []

    class Collection:
        def find(self, query, *args):
            queries.append(query)
            return self

        def sort(self, *args):
            return self

        def limit(self, *args):
            return self

        async def to_list(self, *args, **kwargs):
            # Exercise the final scope check even if an adapter returns
            # records outside its requested database scope.
            return [dict(h.build), dict(h.legacy)]

    monkeypatch.setattr(database, "db", SimpleNamespace(galaxy_builds=Collection()))
    own = await request(h, "GET", "/my-builds", "viewer")
    foreign = await request(h, "GET", "/my-builds", "other")
    assert [item["build_id"] for item in own.json()["builds"]] == [h.build["build_id"]]
    assert foreign.json()["builds"] == []
    assert queries[0] == {"tenant_id": "tenant-a", "owner_id": "owner@example.com"}
    galaxy._active_runners.add(h.build["build_id"])
    try:
        assert (await request(h, "GET", "/jobs/active", "viewer")).json()["count"] == 1
        assert (await request(h, "GET", "/jobs/active", "other")).json()["count"] == 0
    finally:
        galaxy._active_runners.discard(h.build["build_id"])


@pytest.mark.asyncio
async def test_packaging_and_planner_job_status_use_the_canonical_build_scope(galaxy_http, monkeypatch):
    h = galaxy_http
    from routes import final_build
    from core import swarm_scheduler
    job = {"job_id": "owned-job", "build_id": h.build["build_id"]}
    monkeypatch.setattr(final_build, "_JOBS", {"owned-job": job})
    monkeypatch.setattr(swarm_scheduler, "get_job", lambda _job_id: job)
    for path in ["/final-build/job/owned-job", "/swarm/planner/job/owned-job"]:
        assert (await request(h, "GET", path, "viewer")).status_code == 200
        for account in ["other", "foreign-admin"]:
            assert (await request(h, "GET", path, account)).status_code == 404
    assert (await request(h, "GET", "/swarm/planner/preview?build_id=" + h.build["build_id"], "other")).status_code == 404


@pytest.mark.asyncio
async def test_public_catalog_stays_public_and_maintenance_requires_admin(galaxy_http):
    assert (await request(galaxy_http, "GET", "/genres")).status_code == 200
    for account in ["viewer", "owner"]:
        response = await request(galaxy_http, "POST", "/admin/vault/prune", account)
        assert response.status_code == 403
    assert (await request(galaxy_http, "GET", "/admin/vault/stats", "admin")).status_code == 403
    assert (await request(galaxy_http, "GET", "/admin/vault/stats", "install-admin")).status_code == 200


@pytest.mark.asyncio
async def test_legacy_unowned_builds_are_visible_only_to_installation_admin(galaxy_http):
    h = galaxy_http
    for account in ["owner", "viewer", "admin"]:
        assert (await request(h, "GET", f'/status/{h.legacy["build_id"]}', account)).status_code == 404
    assert (await request(h, "GET", f'/status/{h.legacy["build_id"]}', "install-admin")).status_code == 200


@pytest.mark.asyncio
async def test_vault_listing_and_download_do_not_expose_foreign_artifacts(galaxy_http):
    h = galaxy_http
    for account, count in [("owner", 1), ("other", 0), ("foreign-admin", 0)]:
        response = await request(h, "GET", "/vault", account)
        assert response.status_code == 200
        assert response.json()["total_entries"] == count
    assert (await request(h, "GET", "/vault/download/private-artifact", "other")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/download/{id}", "/download-apk/{id}"])
async def test_viewer_download_alias_cannot_start_artifact_preparation(galaxy_http, path):
    h = galaxy_http
    response = await request(h, "GET", path.format(id=h.build["build_id"]), "viewer")
    assert response.status_code == 403
    assert not galaxy._build_has_live_work(h.build["build_id"])


@pytest.mark.asyncio
async def test_mixed_build_log_aliases_filter_canonical_private_scope(galaxy_http, monkeypatch):
    h = galaxy_http
    from routes import swarm_hub, swarm_cold_legion
    rows = [{"build_id": h.build["build_id"], "private": "owner"}, {"build_id": h.legacy["build_id"], "private": "legacy"}]
    monkeypatch.setattr(swarm_hub, "discourse_latest", lambda *_args: rows)
    monkeypatch.setattr(swarm_cold_legion.ledger, "notebook", lambda *_args: rows)
    monkeypatch.setattr(swarm_cold_legion.whispers, "recent", lambda *_args: rows)
    for path, key in [("/swarm/discourse/latest", "logs"), ("/swarm/ledger/notebook/agent", "entries"), ("/swarm/whispers/recent/agent", "whispers")]:
        own = await request(h, "GET", path, "viewer")
        foreign = await request(h, "GET", path, "other")
        assert own.json()[key] == [rows[0]]
        assert foreign.json()[key] == []


@pytest.mark.asyncio
async def test_global_cold_storage_requires_installation_administrator(galaxy_http, monkeypatch):
    h = galaxy_http
    from routes import swarm_cold_legion
    effects = []
    monkeypatch.setattr(swarm_cold_legion.cs, "freeze", lambda *args, **kwargs: effects.append(args))
    monkeypatch.setattr(swarm_cold_legion.cs, "cold_query", lambda *args, **kwargs: effects.append(args))
    for account in ["viewer", "owner", "admin", "foreign-admin"]:
        freeze = await request(h, "POST", "/swarm/cold/freeze", account, json={"name": "galaxy_builds", "force": True, "drop_after": True})
        query = await request(h, "GET", "/swarm/cold/query/galaxy_builds", account)
        assert freeze.status_code == query.status_code == 403
    assert effects == []


@pytest.mark.asyncio
async def test_bson_fallback_reload_preserves_identity_ceiling_and_durable_paths(galaxy_http, monkeypatch):
    h = galaxy_http
    from services import database
    from core import cold_storage
    import copy
    monkeypatch.setattr(cold_storage, "heat_touch", lambda *args, **kwargs: None)

    class Collection:
        calls = 0
        document = None

        async def update_one(self, query, update, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ValueError("BSON document too large")
            self.document = copy.deepcopy(update["$set"])
            return SimpleNamespace(acknowledged=True)

        async def find_one(self, *args, **kwargs):
            return copy.deepcopy(self.document)

    collection = Collection()
    monkeypatch.setattr(database, "db", SimpleNamespace(galaxy_builds=collection))
    vault.append_files(h.build["build_id"], {"retained-a": "first", "retained-b": "second"})
    h.build.update(files={}, _vault_active=True, _vault_file_count=2, file_count=2)
    assert await h.real_save(h.build) is True
    assert collection.calls == 2 and collection.document["_minimal_save"] is True
    galaxy._builds.pop(h.build["build_id"])
    assert (await request(h, "GET", f'/status/{h.build["build_id"]}', "other")).status_code == 404
    own = await request(h, "GET", f'/status/{h.build["build_id"]}', "viewer")
    assert own.status_code == 200 and own.json()["target_files"] == 3
    restored = galaxy._builds[h.build["build_id"]]
    assert restored["owner_id"] == "owner@example.com" and restored["tenant_id"] == "tenant-a"
    assert restored["scale_info"]["explicit_target_files"] == 3 and restored["_vault_active"] is True
    files = galaxy._new_phase_files(restored)
    files["third"] = "third"
    with pytest.raises(galaxy.GalaxyBuildStopped, match="artifact_file_budget_exhausted"):
        files["fourth"] = "must not enter pending output"
    assert len(restored["_file_budget_owner"]["paths"]) == 3
