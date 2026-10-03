import pytest
from scripts.check_p3t2_data_candidate import DataCandidateError,validate
def test_candidate_valid(): assert validate(head="a"*40)["volume_count"]==6
def test_bad_head_rejected():
 with pytest.raises(DataCandidateError): validate(head="bad")
