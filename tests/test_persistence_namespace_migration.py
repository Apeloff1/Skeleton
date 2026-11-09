from __future__ import annotations

import importlib
from types import ModuleType

import pytest


@pytest.mark.parametrize(
    "module_name",
    ["capabilities", "cards", "engine", "law", "store", "verify"],
)
def test_persist_legacy_modules_cover_canonical_exports(module_name: str) -> None:
    canonical = importlib.import_module(f"skeleton.persistence.core.{module_name}")
    legacy = importlib.import_module(f"skeleton.persist.{module_name}")
    exported = tuple(
        getattr(
            canonical,
            "__all__",
            tuple(name for name in vars(canonical) if not name.startswith("_")),
        )
    )
    assert exported
    assert all(hasattr(legacy, name) for name in exported)


def test_persist_package_is_compatibility_facade() -> None:
    import skeleton.persist as legacy
    import skeleton.persistence.core as canonical

    canonical_public = set(canonical.__all__)
    assert canonical_public
    assert canonical_public.issubset(set(vars(legacy)))
    for name in canonical_public:
        exported = getattr(legacy, name)
        # Importing legacy.capabilities installs that submodule on its parent.
        # Its public callable must still be the canonical implementation.
        if isinstance(exported, ModuleType):
            exported = getattr(exported, name)
        assert exported is getattr(canonical, name)
