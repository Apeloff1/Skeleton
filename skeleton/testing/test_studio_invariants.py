import pytest
from skeleton.automation.studio_invariants import require_hex_digest, require_subset, require_unique

def test_unique_rejects_duplicates():
    with pytest.raises(ValueError): require_unique(["a","a"],"tasks")
def test_subset_rejects_escape():
    with pytest.raises(ValueError): require_subset(["a","b"],["a"],"paths")
def test_digest_rejects_non_hex():
    with pytest.raises(ValueError): require_hex_digest("z"*64,"digest")
