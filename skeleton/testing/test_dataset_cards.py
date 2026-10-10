from __future__ import annotations
import hashlib,pytest
from skeleton.ai.governance.cards import DatasetCard,GovernanceCardError
def d(x): return hashlib.sha256(x.encode()).hexdigest()
def test_dataset_card_binds_registry_lineage_license_and_deletion():
    card=DatasetCard("c","ds","b"*40,d("registry"),d("lineage"),"CC-BY-4.0",("training",),("personal-data",),"delete-v2")
    assert len(card.digest)==64 and card.deletion_policy_id=="delete-v2"
def test_dataset_card_requires_allowed_use():
    with pytest.raises(GovernanceCardError,match="allowed_use"):
        DatasetCard("c","ds","b"*40,d("r"),d("l"),"lic",(),(),"del")
def test_dataset_card_cannot_promote():
    with pytest.raises(GovernanceCardError,match="cannot grant"):
        DatasetCard("c","ds","b"*40,d("r"),d("l"),"lic",("x",),(),"del",True)
