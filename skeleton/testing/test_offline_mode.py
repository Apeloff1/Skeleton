from __future__ import annotations
import hashlib,pytest
from skeleton.ai.providers.offline_mode import OfflineCapability,OfflineModeError,OfflineProfile
def d(x): return hashlib.sha256(x.encode()).hexdigest()
def test_offline_profile_requires_local_evidence_and_disables_egress():
    p=OfflineProfile("offline",(OfflineCapability("chat",True,True),),d("model"),d("storage"))
    assert p.egress_disabled is True and p.provider_calls_allowed is False and len(p.digest)==64
def test_missing_local_model_fails_closed():
    with pytest.raises(OfflineModeError,match="local model evidence"):
        OfflineProfile("o",(OfflineCapability("chat",True,False),),None,None)
def test_network_required_capability_is_forbidden():
    with pytest.raises(OfflineModeError,match="cannot require network"):
        OfflineCapability("web",False,False,True)
