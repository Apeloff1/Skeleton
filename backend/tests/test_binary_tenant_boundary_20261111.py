"""No live network/Mongo: adversarial HTTP artifact ownership boundaries."""
from __future__ import annotations

import asyncio
import io

import pytest
from fastapi import HTTPException

from routes import build_pipeline as api


def _user(owner: str, tenant: str, role: str = "editor"):
    return {"email": owner, "tenant_id": tenant, "role": role}


class FakeCollection:
    def __init__(self, rows=None):
        self.rows = [dict(row) for row in (rows or [])]
        self.queries = []

    async def find_one(self, query, projection=None):
        self.queries.append(dict(query))
        for row in self.rows:
            if all(row.get(key) == value for key, value in query.items()):
                return dict(row)
        return None

    async def update_one(self, query, update, *, upsert=False):
        self.queries.append(dict(query))
        matching = next(
            (row for row in self.rows if all(row.get(k) == v for k, v in query.items())),
            None,
        )
        if matching is None and upsert:
            self.rows.append(dict(update["$set"]))
        elif matching is not None:
            matching.update(update["$set"])

    def find(self, query, projection=None):
        self.queries.append(dict(query))
        self._results = [
            dict(row) for row in self.rows
            if all(row.get(k) == v for k, v in query.items())
        ]
        return self

    async def to_list(self, length):
        return self._results[:length]


class FakeDB:
    def __init__(self):
        self.galaxy_builds = FakeCollection([
            {"build_id": "same-build", "tenant_id": "blue", "owner_id": "a@example.test"},
            {"build_id": "same-build", "tenant_id": "red", "owner_id": "b@example.test"},
            {"build_id": "revoked", "tenant_id": "blue", "owner_id": "a@example.test", "revoked": True},
        ])
        self.build_artifacts = FakeCollection()


def test_artifact_namespace_is_stable_and_unique_across_tenants():
    a = api._storage_build_id("same-build", {"tenant_id": "blue", "owner_id": "a@example.test"})
    b = api._storage_build_id("same-build", {"tenant_id": "red", "owner_id": "b@example.test"})
    assert a != b
    assert a == api._storage_build_id(
        "same-build", {"tenant_id": "blue", "owner_id": "a@example.test"}
    )
    assert len(a) == 64 and a.isascii()
    assert "example" not in a and "same-build" not in a


@pytest.mark.parametrize("bad", ["..", "../other", "a/b", "ä", "", "x" * 129])
def test_artifact_namespace_rejects_untrusted_filenames(bad):
    with pytest.raises(ValueError):
        api._storage_build_id(bad, {"tenant_id": "a", "owner_id": "b"})


def test_private_binary_routes_fail_closed_on_anonymous_and_viewer():
    with pytest.raises(HTTPException) as error:
        api._private_build_identity(None)
    assert error.value.status_code == 401
    with pytest.raises(HTTPException) as error:
        api._private_build_identity(_user("v@example.test", "blue", "viewer"), mutate=True)
    assert error.value.status_code == 403


def test_owned_build_rejects_cross_tenant_and_revoked(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(api, "_db", lambda: db)
    identity = api._private_build_identity(_user("a@example.test", "blue"))
    build = asyncio.run(api._owned_binary_build("same-build", identity))
    assert build["owner_id"] == "a@example.test"
    with pytest.raises(HTTPException) as e:
        asyncio.run(api._owned_binary_build("revoked", identity))
    assert e.value.status_code == 404
    with pytest.raises(HTTPException) as e:
        asyncio.run(api._owned_binary_build(
            "same-build", {"tenant_id": "blue", "owner_id": "intruder@example.test"}
        ))
    assert e.value.status_code == 404
    assert all("owner_id" in q and "tenant_id" in q for q in db.galaxy_builds.queries)


def test_same_build_id_never_overwrites_other_tenants_artifacts(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(api, "_db", lambda: db)
    monkeypatch.setattr(api, "code_execution_enabled", lambda: True)
    calls = []

    async def package(build, kinds):
        calls.append(build["build_id"])
        return {"artifacts": [{
            "artifact_id": "zip_" + build["build_id"],
            "kind": "zip", "build_id": build["build_id"],
            "path": "/sensitive/internal/path.zip",
            "download_url": "/api/binary/download/" + build["build_id"] + "/zip",
            "size_bytes": 7,
        }], "errors": []}

    monkeypatch.setattr(api.binary_builder, "package_build", package)
    req = api.PackageReq(build_id="same-build", kinds=["zip"])
    alice = asyncio.run(api.binary_package(req, user=_user("a@example.test", "blue")))
    bob = asyncio.run(api.binary_package(req, user=_user("b@example.test", "red")))
    assert calls[0] != calls[1]
    assert len(db.build_artifacts.rows) == 2
    assert alice["artifacts"][0]["download_url"] == "/api/binary/download/same-build/zip"
    assert bob["artifacts"][0]["download_url"] == alice["artifacts"][0]["download_url"]
    assert "path" not in alice["artifacts"][0]
    assert "storage_build_id" not in alice["artifacts"][0]
    assert all("tenant_id" in q and "owner_id" in q for q in db.build_artifacts.queries)
    alice_list = asyncio.run(api.binary_artifacts(
        "same-build", user=_user("a@example.test", "blue")
    ))
    bob_list = asyncio.run(api.binary_artifacts(
        "same-build", user=_user("b@example.test", "red")
    ))
    assert alice_list["count"] == bob_list["count"] == 1
    assert alice_list["artifacts"][0]["artifact_id"] != bob_list["artifacts"][0]["artifact_id"]


def test_binary_download_pins_authorized_storage_namespace(monkeypatch):
    db = FakeDB()
    identity = {"tenant_id": "blue", "owner_id": "a@example.test"}
    storage = api._storage_build_id("same-build", identity)
    db.build_artifacts.rows.append({
        "build_id": "same-build", "storage_build_id": storage, "kind": "zip", **identity
    })
    monkeypatch.setattr(api, "_db", lambda: db)
    opened = []

    def open_file(physical_id, kind):
        opened.append((physical_id, kind))
        return io.BytesIO(b"private-artifact")

    monkeypatch.setattr(api.binary_builder, "open_artifact_for_download", open_file)
    response = asyncio.run(api.binary_download(
        "same-build", "zip", user=_user("a@example.test", "blue")
    ))

    async def consume():
        parts = []
        async for chunk in response.body_iterator:
            parts.append(chunk)
        return b"".join(parts)

    assert asyncio.run(consume()) == b"private-artifact"
    assert opened == [(storage, "zip")]
    assert response.headers["cache-control"] == "private, no-store"

    with pytest.raises(HTTPException) as e:
        asyncio.run(api.binary_download(
            "same-build", "zip", user=_user("b@example.test", "red")
        ))
    assert e.value.status_code == 404
    assert len(opened) == 1


def test_legacy_unowned_metadata_is_never_disclosed(monkeypatch):
    db = FakeDB()
    db.build_artifacts.rows.append({
        "build_id": "same-build", "kind": "zip", "path": "/legacy/secrets.zip"
    })
    monkeypatch.setattr(api, "_db", lambda: db)
    rows = asyncio.run(api.binary_artifacts(
        "same-build", user=_user("a@example.test", "blue")
    ))
    assert rows["artifacts"] == []


def test_http_tool_boundary_denies_unscoped_data_and_package_adapters(monkeypatch):
    for tool in ("mongo_query", "package_build"):
        with pytest.raises(HTTPException) as error:
            api._admit_http_tool(tool)
        assert error.value.status_code == 403
    captured = []

    async def fake_invoke(name, params, **kwargs):
        captured.append((name, kwargs))
        return {"ok": True}

    monkeypatch.setattr(api.tool_registry, "invoke", fake_invoke)
    result = asyncio.run(api.tools_invoke(
        api.ToolInvokeReq(tool="vault_query", params={"collection": "safe"}),
        user=_user("a@example.test", "blue"),
    ))
    assert result == {"ok": True}
    assert captured == [("vault_query", {"tenant_id": "blue"})]


def test_http_tool_catalog_excludes_internal_scopes(monkeypatch):
    monkeypatch.setattr(api.tool_registry, "describe", lambda: {
        "tools": [
            {"name": "vault_query"}, {"name": "mongo_query"},
            {"name": "package_build"}, {"name": "jeeves_consult"},
        ],
        "count": 4,
    })
    catalog = asyncio.run(api.tools_describe())
    assert [row["name"] for row in catalog["tools"]] == ["vault_query", "jeeves_consult"]
    assert catalog["count"] == 2
