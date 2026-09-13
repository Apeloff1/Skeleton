import pytest
from skeleton.frontier.gameforge_admission import Admission,decide

def test_admission_fails_closed():
 assert decide(background_allowed=True,read_only=True,active=0,limit=4,background=False) is Admission.READ_ONLY
 assert decide(background_allowed=False,read_only=False,active=0,limit=4,background=True) is Admission.SHED
 assert decide(background_allowed=True,read_only=False,active=4,limit=4,background=False) is Admission.SHED
 assert decide(background_allowed=True,read_only=False,active=0,limit=4,background=False) is Admission.ACCEPT

def test_admission_rejects_invalid_bounds():
 with pytest.raises(ValueError): decide(background_allowed=True,read_only=False,active=-1,limit=1,background=False)
 with pytest.raises(ValueError): decide(background_allowed=True,read_only=False,active=0,limit=0,background=False)
