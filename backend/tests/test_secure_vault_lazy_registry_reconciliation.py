"""The secure vault's filesystem guard must be an explicit lazy import.

No eager imports, arbitrary module-name interpretation or network calls.
"""
from core import lazy_registry


def test_secure_vault_filesystem_module_has_fixed_lazy_loader(monkeypatch):
    module_name = "core.vault_secure_fs"
    assert module_name in lazy_registry._LOADERS
    calls = []
    sentinel = object()

    def isolated_import(value):
        calls.append(value)
        assert value == module_name
        return sentinel

    monkeypatch.setattr(lazy_registry.importlib, "import_module", isolated_import)
    assert lazy_registry._LOADERS[module_name]() is sentinel
    assert calls == [module_name]
