"""Storage diagnostics remain available without importing deferred seeds."""
from concurrent.futures import ThreadPoolExecutor
import importlib
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from core import lazy_registry
from routes.storage import router


@pytest.fixture
def storage_client(monkeypatch):
    monkeypatch.setattr(lazy_registry, "_proxies", {})
    monkeypatch.setattr(lazy_registry, "_noncore_proxies", {})
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        yield client


@pytest.mark.parametrize("path", ["/api/storage/modules?top=8", "/api/storage/lazy"])
def test_storage_diagnostics_return_real_inventory_without_loading_seeds(storage_client, path):
    before = {name for name in sys.modules if name.startswith("seeds.")}
    response = storage_client.get(path)
    assert response.status_code == 200
    payload = response.json()
    status = payload["lazy"] if "modules" in path else payload
    assert status["core"]["total"] > 0
    assert status["core"]["loaded"] + status["core"]["deferred"] == status["core"]["total"]
    assert status["seeds"]["total"] > 0
    if "modules" in path:
        assert payload["module_count"] > 0
        assert len(payload["biggest"]) == 8
    assert {name for name in sys.modules if name.startswith("seeds.")} == before


def test_wrapping_storage_modules_does_not_execute_them(storage_client):
    before = {name for name in sys.modules if name.startswith(("core.", "seeds."))}
    response = storage_client.post("/api/storage/lazy/wrap")
    assert response.status_code == 200
    payload = response.json()
    assert payload["wrapped_core"] > 0
    assert payload["wrapped_noncore"] > 0
    assert payload["status"]["wrapped_proxies"]["core"] == payload["wrapped_core"]
    assert {name for name in sys.modules if name.startswith(("core.", "seeds."))} == before


def test_first_concurrent_proxy_access_imports_target_once(tmp_path, monkeypatch):
    name = "storage_lazy_fixture"
    marker = tmp_path / "imports.txt"
    (tmp_path / f"{name}.py").write_text(
        f"with open({str(marker)!r}, 'a') as stream:\n    stream.write('loaded\\n')\nVALUE = 73\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setitem(lazy_registry._LOADERS, name, lambda: importlib.import_module(name))
    sys.modules.pop(name, None)
    proxy = lazy_registry.lazy_import(name)
    assert name not in sys.modules and not marker.exists()
    assert name in repr(proxy)
    assert not marker.exists()
    try:
        with ThreadPoolExecutor(max_workers=8) as workers:
            values = list(workers.map(lambda _: proxy.VALUE, range(24)))
        assert values == [73] * 24
        assert marker.read_text() == "loaded\n"
    finally:
        sys.modules.pop(name, None)


@pytest.mark.parametrize("name", ["os", "asyncio", "../../os", "core.unregistered_module", "seeds.unknown"])
def test_proxy_rejects_unregistered_import_paths(name):
    before = set(sys.modules)
    with pytest.raises(ValueError, match="not registered"):
        lazy_registry.lazy_import(name)
    assert set(sys.modules) == before


def test_literal_loader_inventory_matches_declared_repository_modules():
    expected = {"core." + name for name in lazy_registry.module_names()}
    expected.update("seeds." + name for name in lazy_registry._pkg_module_names("seeds"))
    assert set(lazy_registry._LOADERS) == expected


def test_public_exception_route_literal_loader_uses_reviewed_import(monkeypatch):
    """A newly added redaction route stays in the explicit lazy allowlist."""
    name = "core.public_exception_route"
    assert "public_exception_route" in lazy_registry.module_names()
    assert name in lazy_registry._LOADERS
    sentinel = object()
    calls = []

    def recorded_import(module_name):
        calls.append(module_name)
        return sentinel

    monkeypatch.setattr(lazy_registry.importlib, "import_module", recorded_import)
    assert lazy_registry._LOADERS[name]() is sentinel
    assert calls == [name]


def test_registry_has_no_runtime_selected_python_imports():
    from pathlib import Path
    from scripts.check_dynamic_import_safety import violations
    assert violations(Path(lazy_registry.__file__)) == []


def test_flagged_wrapper_uses_only_reviewed_seed_loaders(monkeypatch):
    """A recursive size inventory must not authorize new import targets."""
    from core import unbulk

    known = next(name for name in lazy_registry._LOADERS if name.startswith("seeds."))

    class HostilePath(str):
        def replace(self, *_args, **_kwargs):
            raise AssertionError("untrusted inventory path method executed")

    monkeypatch.setattr(lazy_registry, "_noncore_proxies", {})

    def inventory(top=25):
        assert top == 10_000
        return {"biggest": [
            {"module": "seeds/deep/unregistered.py", "lazy_eligible": True},
            {"module": "routes/foreign.py", "lazy_eligible": True},
            {"module": HostilePath("seeds/hostile.py"), "lazy_eligible": True},
            {"module": object(), "lazy_eligible": True},
            {"module": known.replace(".", "/") + ".py", "lazy_eligible": True},
            {"module": "seeds/not_flagged.py", "lazy_eligible": False},
        ]}

    monkeypatch.setattr(unbulk, "module_inventory", inventory)
    before = set(sys.modules)
    wrapped = lazy_registry.wrap_flagged()
    assert set(wrapped) == {known}
    assert wrapped[known] is lazy_registry._noncore_proxies[known]
    assert set(sys.modules) == before


def test_storage_wrap_survives_unregistered_nested_seed_inventory(storage_client, monkeypatch):
    """The public endpoint stays usable while nested seeds remain deferred."""
    from core import unbulk

    original_inventory = unbulk.module_inventory

    def inventory(top=25):
        result = original_inventory(top=top)
        result["biggest"].insert(
            0, {"module": "seeds/deep/unregistered.py", "lazy_eligible": True}
        )
        return result

    monkeypatch.setattr(unbulk, "module_inventory", inventory)
    before = {name for name in sys.modules if name.startswith("seeds.")}
    response = storage_client.post("/api/storage/lazy/wrap")
    assert response.status_code == 200
    payload = response.json()
    assert payload["wrapped_core"] > 0
    assert payload["wrapped_noncore"] > 0
    assert "seeds.deep.unregistered" not in lazy_registry._noncore_proxies
    assert {name for name in sys.modules if name.startswith("seeds.")} == before


def test_lazy_import_rejects_str_subclass_without_hashing():
    """Reject hostile names before invoking dictionary hash/equality hooks."""

    class HostileModuleName(str):
        def __hash__(self):
            raise AssertionError("untrusted name hashed")

        def __eq__(self, other):
            raise AssertionError("untrusted name compared")

    before = set(sys.modules)
    with pytest.raises(ValueError, match="not registered"):
        lazy_registry.lazy_import(HostileModuleName("core.public_exception_route"))
    assert set(sys.modules) == before



def test_telemetry_privacy_is_reviewed_literal_loader_without_eager_import(monkeypatch):
    """The privacy boundary is never discovered through a dynamic import path."""
    name = "core.telemetry_privacy"
    assert "telemetry_privacy" in lazy_registry.module_names()
    assert name in lazy_registry._LOADERS
    before = {key for key in sys.modules if key.startswith("core.")}
    sentinel = object()
    calls = []

    def controlled(module_name):
        calls.append(module_name)
        return sentinel

    monkeypatch.setattr(lazy_registry.importlib, "import_module", controlled)
    assert lazy_registry._LOADERS[name]() is sentinel
    assert calls == [name]
    assert {key for key in sys.modules if key.startswith("core.")} == before


def test_storage_wrap_includes_telemetry_privacy_without_import(storage_client):
    """The full inventory and public wrap endpoint agree on the new module."""
    before = set(sys.modules)
    response = storage_client.post("/api/storage/lazy/wrap")
    assert response.status_code == 200
    assert response.json()["wrapped_core"] == len(lazy_registry.module_names())
    assert "core.telemetry_privacy" in lazy_registry._LOADERS
    assert "core.telemetry_privacy" not in set(sys.modules) - before
