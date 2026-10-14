"""The mission-ranked registry must resolve exactly twenty real operations."""
import pytest

from skeleton.ai.webcrawler.dragon_mission_catalog import (
    CAPABILITY_CATALOG, describe_mission_capabilities, resolve_mission_capability,
)


def test_all_twenty_mission_capabilities_are_implemented_callables():
    assert len(CAPABILITY_CATALOG)==20
    assert [x.rank for x in CAPABILITY_CATALOG]==list(range(1,21))
    assert len({x.name for x in CAPABILITY_CATALOG})==20
    assert all(x.outcome and x.fail_closed_on and x.mission_stage
               for x in CAPABILITY_CATALOG)
    for row in CAPABILITY_CATALOG:
        operation=resolve_mission_capability(row.rank)
        assert callable(operation)
        assert operation.__name__==row.name
        assert operation.__module__.endswith(row.module)


def test_catalog_is_deterministic_and_prioritizes_native_tokenization():
    assert describe_mission_capabilities() is CAPABILITY_CATALOG
    assert CAPABILITY_CATALOG[0].name=="encode_verified_tokens"
    assert CAPABILITY_CATALOG[1].name=="require_training_grant"
    assert CAPABILITY_CATALOG[-1].name=="decide_mission_stop"
    assert describe_mission_capabilities()==describe_mission_capabilities()


@pytest.mark.parametrize("invalid",[0,21,-1,True,1.2,"01",None])
def test_unrecognized_rank_is_never_executed(invalid):
    with pytest.raises(ValueError,match="unknown"):
        resolve_mission_capability(invalid)


def test_public_namespace_supports_all_ranked_capabilities_without_eager_import():
    from skeleton.ai import webcrawler
    for capability in CAPABILITY_CATALOG:
        operation=getattr(webcrawler,capability.name)
        assert callable(operation)
        assert operation is resolve_mission_capability(capability.rank)
    assert webcrawler.CAPABILITY_CATALOG==CAPABILITY_CATALOG
