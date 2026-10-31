"""VaultItem list/dict defaults must not be shared between instances."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from routes.sorting_vault import VaultItem, VaultType  # noqa: E402


def _item(i):
    return VaultItem(id=str(i), name="n", vault_type=list(VaultType)[0], category="c",
                     size_bytes=0, created_at="t", modified_at="t")


def test_defaults_not_shared():
    a, b = _item(1), _item(2)
    a.tags.append("x"); a.metadata["k"] = 1
    assert b.tags == [] and b.metadata == {}
    assert VaultItem.model_fields["tags"].default_factory is list
    assert VaultItem.model_fields["metadata"].default_factory is dict
