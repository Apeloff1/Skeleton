"""Real JWT/ASGI admission for restored legacy build routes, with no shadow store."""
from copy import deepcopy
import hashlib
import importlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.tests.test_project_alias_privacy import private_app
from core import gameforge_artifact_builder as builder
from routes import gameforge_build as route


class Cursor(list):
    def sort(self, *args):
        return self
    def limit(self, count):
        return Cursor(self[:count])


class Collection:
    def __init__(self, rows=()):
        self.rows, self.queries, self.writes = list(deepcopy(rows)), [], []
    def find(self, query, projection=None):
        self.queries.append(deepcopy(query))
        return Cursor(deepcopy([row for row in self.rows if all(row.get(k) == v for k, v in query.items())]))
    def find_one(self, query, projection=None):
        return next(iter(self.find(query, projection)), None)
    def update_one(self, query, update, **kwargs):
        self.writes.append((deepcopy(query), deepcopy(update)))
        row = self.find_one(query)
        if row is None:
            self.rows.append({**deepcopy(query), **deepcopy(update.get("$set", {}))})
        return SimpleNamespace(matched_count=1)


@pytest.fixture
def build_app(private_app, monkeypatch):
    client, headers, _, users = private_app
    owner = {"tenant_id": "tenant-a", "owner_id": "owner@example.test"}
    foreign = {**owner, "owner_id": "foreign@example.test"}
    other = {**owner, "tenant_id": "tenant-b"}
    source_rows = [{**scope, "game_name": name, "filename": "main.html", "content": marker}
                   for scope, name, marker in [(owner, "Owned", "OWNED CANARY"), (foreign, "Foreign", "FOREIGN CANARY"),
                                              (other, "Other", "OTHER TENANT CANARY"), ({}, "Legacy", "LEGACY CANARY")]]
    source_rows += [{**owner, "game_name": "Revoked", "filename": "revoked", "content": "REVOKED CANARY", "rights_revoked": True}]
    payload = b"OWNED GOVERNED BYTES"
    builds = [{**scope, "build_id": bid, "game_name": name, "kind": "source", "source_ref": "artifact://existing/" + bid,
               "sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload), "built_at": 1, "path": "/private/internal/path"}
              for scope, bid, name in [(owner, "own-build", "Owned"), (foreign, "foreign-build", "Foreign"),
                                       (other, "other-build", "Other"), ({}, "legacy-build", "Legacy"),
                                       (owner, "stale-build", "Foreign")]]
    database = {"gameforge_gamefiles": Collection(source_rows), "gameforge_builds": Collection(builds)}
    monkeypatch.setattr(route, "_db", lambda: database)
    monkeypatch.setattr(builder, "database", lambda: database)
    client.app.include_router(route.router)
    return client, headers, database, users, payload


@pytest.mark.parametrize("method,path,body", [("GET", "/toolchains", None), ("GET", "/list", None),
    ("GET", "/download/own-build", None), ("POST", "/web", {"game_name": "Owned"}),
    ("POST", "/source", {"game_name": "Owned"}), ("POST", "/desktop", {"game_name": "Owned"}),
    ("POST", "/godot", {"game_name": "Owned"})])
def test_entire_build_surface_requires_actual_authentication(build_app, method, path, body):
    client, _, db, _, _ = build_app
    response = client.request(method, "/api/gameforge/build" + path, json=body)
    assert response.status_code == 401
    assert not db["gameforge_gamefiles"].queries and not db["gameforge_builds"].queries


def test_toolchain_projection_reports_governed_delivery_unavailable(build_app):
    client, headers, _, _, _ = build_app
    response = client.get("/api/gameforge/build/toolchains", headers=headers["owner"])
    assert response.status_code == 200 and response.headers["cache-control"] == "private, no-store"
    result = response.json()
    assert result["artifact_delivery"] == {"available": False, "code": "artifact_owner_unavailable"}
    assert result["toolchains"]["web"] is False and result["toolchains"]["source_zip"] is False
    assert "Studio project source export" in result["note"]


@pytest.mark.parametrize("kind", ["web", "source", "desktop", "godot"])
def test_viewer_cannot_build_even_when_development_auth_enforcement_is_off(build_app, monkeypatch, kind):
    client, headers, _, _, _ = build_app
    monkeypatch.setenv("GAMEFORGE_AUTH_ENFORCE", "false")
    response = client.post("/api/gameforge/build/" + kind, headers=headers["viewer"], json={"game_name": "Owned"})
    assert response.status_code == 403


@pytest.mark.parametrize("name", ["Foreign", "Other", "Legacy", "Revoked"])
@pytest.mark.parametrize("kind", ["web", "source", "desktop", "godot"])
def test_source_identity_and_lifecycle_are_required_before_any_export(build_app, name, kind):
    client, headers, db, users, _ = build_app
    users["owner@example.test"]["role"] = "admin"
    response = client.post("/api/gameforge/build/" + kind, headers=headers["owner"], json={"game_name": name})
    assert response.status_code == 404 and "CANARY" not in response.text
    assert not db["gameforge_builds"].writes


@pytest.mark.parametrize("kind", ["web", "source", "desktop", "godot"])
def test_owned_source_fails_closed_without_canonical_artifact_delivery(build_app, kind):
    client, headers, db, _, _ = build_app
    response = client.post("/api/gameforge/build/" + kind, headers=headers["owner"], json={"game_name": "Owned"})
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "artifact_owner_unavailable"
    assert not db["gameforge_builds"].writes


def test_metadata_lists_and_binary_aliases_check_exact_owner_tenant_and_current_source(build_app, monkeypatch):
    client, headers, _, users, payload = build_app
    calls = []
    class Store:
        def read_bytes(self, tenant_id, artifact_id):
            calls.append((tenant_id, artifact_id))
            return payload
    monkeypatch.setattr(route, "_governed_store", lambda: Store())
    listed = client.get("/api/gameforge/build/list", headers=headers["owner"])
    assert listed.status_code == 200 and [row["build_id"] for row in listed.json()["builds"]] == ["own-build"]
    assert "internal/path" not in listed.text
    for bid in ["foreign-build", "other-build", "legacy-build", "stale-build"]:
        denied = client.get("/api/gameforge/build/download/" + bid, headers=headers["owner"])
        assert denied.status_code == 404
    assert calls == []
    own = client.get("/api/gameforge/build/download/own-build", headers=headers["owner"])
    assert own.status_code == 200 and own.content == payload
    assert own.headers["cache-control"] == "private, no-store"
    users["owner@example.test"]["tenant_id"] = "tenant-b"
    assert client.get("/api/gameforge/build/download/own-build", headers=headers["owner"]).status_code == 404


def test_real_module_import_never_attempts_a_runtime_directory_write(monkeypatch):
    def readonly(*args, **kwargs):
        raise OSError(30, "Read-only file system")
    monkeypatch.setattr(os, "makedirs", readonly)
    monkeypatch.setattr(Path, "mkdir", readonly)
    assert importlib.reload(route).router.prefix == "/api/gameforge/build"


def test_assembly_staging_is_a_sibling_of_the_existing_build_vault(monkeypatch):
    assert builder.DEFAULT_ARTIFACTS_ROOT.name == "gameforge-staging"
    assert builder.DEFAULT_ARTIFACTS_ROOT.parent == Path(os.environ.get("GALAXY_BUILDS_VAULT_DIR", "/app/data/builds_vault")).parent
