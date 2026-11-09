import pytest
from skeleton.automation.studio_promotion import PromotionEvidence,require_promotable
def test_all_evidence_required():
 require_promotable(PromotionEvidence(True,True,True,True))
 with pytest.raises(ValueError): require_promotable(PromotionEvidence(True,True,False,True))
