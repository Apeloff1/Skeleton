from __future__ import annotations
import hashlib,pytest
from skeleton.ai.runtime.security.air_gap import AirGapInstallProfile,AirGapProfileError,TrustedPackage
def d(x): return hashlib.sha256(x.encode()).hexdigest()
def pkg():
    return TrustedPackage("pkg",d("artifact"),d("sbom"),d("prov"),d("sig"))
def test_air_gap_profile_binds_package_trust_and_media_scan():
    p=AirGapInstallProfile("airgap",d("root"),(pkg(),),d("scan"))
    assert p.network_disabled is True and p.online_update_allowed is False and len(p.digest)==64
def test_duplicate_package_ids_rejected():
    with pytest.raises(AirGapProfileError,match="package ids"):
        AirGapInstallProfile("a",d("r"),(pkg(),pkg()),d("s"))
def test_airgap_cannot_enable_network_updates():
    with pytest.raises(AirGapProfileError,match="disable network"):
        AirGapInstallProfile("a",d("r"),(pkg(),),d("s"),False,True)
