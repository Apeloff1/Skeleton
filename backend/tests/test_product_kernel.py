import pytest

from core.product_kernel import CAPABILITIES, Capability, ProductKernel, ProductPillar


def test_default_kernel_has_four_product_pillars():
    kernel = ProductKernel()
    assert {capability.pillar for capability in kernel.all()} == set(ProductPillar)


def test_critical_product_surfaces_are_explicit():
    kernel = ProductKernel()
    assert set(kernel.critical_ids()) == {"studio", "playables", "jeeves", "operations"}


def test_owner_for_path_uses_registered_prefixes():
    kernel = ProductKernel()
    assert kernel.owner_for_path("/api/gameforge-studio/build").id == "studio"
    assert kernel.owner_for_path("/api/godot-engine/status").id == "world-forge"
    assert kernel.owner_for_path("/api/governance/reports").id == "governance"
    assert kernel.owner_for_path("/api/unknown") is None


def test_pillar_lookup_accepts_enum_or_string():
    kernel = ProductKernel()
    assert kernel.for_pillar(ProductPillar.CREATE) == kernel.for_pillar("create")
    assert {c.id for c in kernel.for_pillar("learn")} == {"jeeves", "academy"}


def test_invalid_pillar_is_rejected():
    with pytest.raises(ValueError):
        ProductKernel().for_pillar("other")


def test_duplicate_capability_ids_are_rejected():
    duplicate = Capability("same", ProductPillar.CREATE, "A", ("/a",))
    with pytest.raises(ValueError, match="unique"):
        ProductKernel((duplicate, Capability("same", ProductPillar.PLAY, "B", ("/b",))))


def test_catalog_ids_and_prefixes_are_nonempty():
    for capability in CAPABILITIES:
        assert capability.id
        assert capability.title
        assert capability.api_prefixes
        assert all(prefix.startswith("/api/") for prefix in capability.api_prefixes)
