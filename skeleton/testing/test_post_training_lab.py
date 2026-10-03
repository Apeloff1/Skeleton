import pytest
from skeleton.learning.post_training_lab import *
def test_post_training_candidate_is_experimental_and_cannot_self_promote():
 lab=PostTrainingLab(); run=PostTrainingRun("r","a"*64,"b"*64,"preference","dpo","c"*64); lab.register(run); c=lab.candidate(run_id="r",model_digest="d"*64,evaluation_receipt_digest="e"*64); assert c.promotion_authorized is False
 with pytest.raises(PostTrainingError): lab.register(PostTrainingRun("r","f"*64,"b"*64,"other","dpo","c"*64))
