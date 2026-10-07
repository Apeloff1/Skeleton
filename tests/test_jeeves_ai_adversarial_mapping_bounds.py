from collections.abc import Mapping

import pytest

from skeleton.jeeves.ai._canonical import MAX_ITEMS
from skeleton.jeeves.ai.contracts import ContractRecord
from skeleton.jeeves.ai.evaluation import EvalRecord
from skeleton.jeeves.ai.orchestration import OrchestrRecord


class _UnderreportedMapping(Mapping):
    """Mapping that lies about len() but emits an oversized unique item stream."""

    def __getitem__(self, key):
        if isinstance(key, str) and key.startswith("k"):
            return 1
        raise KeyError(key)

    def __iter__(self):
        return (f"k{index}" for index in range(MAX_ITEMS + 1))

    def __len__(self):
        return 1

    def items(self):
        return ((f"k{index}", 1) for index in range(MAX_ITEMS + 1))


@pytest.mark.parametrize("constructor", (ContractRecord, EvalRecord, OrchestrRecord))
def test_all_planes_enforce_mapping_item_bound_during_iteration(constructor):
    with pytest.raises(ValueError, match="too many JSON mapping items"):
        constructor("oversized-adversarial-map", payload=_UnderreportedMapping())


def test_normal_mapping_at_item_limit_remains_accepted():
    payload = {f"k{index}": index for index in range(MAX_ITEMS)}
    record = ContractRecord("bounded-map", payload=payload)
    assert len(record.payload) == MAX_ITEMS
