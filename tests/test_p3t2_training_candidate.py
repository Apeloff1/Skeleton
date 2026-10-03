import pytest
from scripts.check_p3t2_training_candidate import TrainingCandidateError,validate
def test_candidate_valid(): assert validate(head="a"*40)["volume_count"]==7
def test_bad_head_rejected():
 with pytest.raises(TrainingCandidateError): validate(head="bad")
