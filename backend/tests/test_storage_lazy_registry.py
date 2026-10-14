"""Storage diagnostics remain available without importing deferred seeds."""
from concurrent.futures import ThreadPoolExecutor
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
