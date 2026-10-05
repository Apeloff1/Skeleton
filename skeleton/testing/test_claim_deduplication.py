import pytest
from skeleton.ai.claim_deduplication import *
def test_scope_or_time_difference_prevents_merge():
 a=fingerprint("same","us","2026");b=fingerprint("same","eu","2026")
 with pytest.raises(ValueError):merge_claims((("1",a),("2",b)))
def test_merge_preserves_original_lineage():
 f=fingerprint("A claim","us","2026");assert merge_claims((("1",f),("2",f))).lineage==("1","2")

def test_nfkc_equivalent_claims_share_fingerprint():assert fingerprint("Ａ","s","t")==fingerprint("A","s","t")
def test_empty_merge_rejected():
 import pytest
 with pytest.raises(ValueError):merge_claims(())
