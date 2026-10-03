import pytest
from skeleton.automation.studio_evidence import canonical_bytes, chain, sha256_json

def test_canonical_mapping_order():
    assert canonical_bytes({"b":1,"a":2})==canonical_bytes({"a":2,"b":1})
def test_hash_deterministic():
    assert sha256_json({"x":1})==sha256_json({"x":1})
def test_chain_depends_on_previous():
    assert chain("a"*64,{"x":1})!=chain("b"*64,{"x":1})
def test_chain_rejects_bad_previous():
    with pytest.raises(ValueError): chain("bad",{"x":1})
