import pytest
from skeleton.security.experimental_features import *
def test_experiment_never_claims_production_capability():
 with pytest.raises(PermissionError):expose(ExperimentalFeature("x","s",True),"shadow",ExperimentKillSwitch(False))
def test_kill_switch_stops_exposure():assert not expose(ExperimentalFeature("x","s"),"synthetic",ExperimentKillSwitch(True)).active
