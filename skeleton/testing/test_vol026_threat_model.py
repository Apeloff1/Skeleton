import hashlib

import pytest

from skeleton.contracts.canonical import canonical_json_bytes
from skeleton.security.contracts import SecurityContractError
from skeleton.security.threat_model import Threat,ThreatModel,canonical_vol026_threat_model
def test_canonical_model_covers_required_security_boundaries():
 m=canonical_vol026_threat_model()
 assert {t.asset for t in m.threats}=={"tool-authority","secrets","filesystem","network-egress","supply-chain"}
 assert all(t.validation for t in m.threats)
def test_model_digest_is_deterministic_under_order():
 m=canonical_vol026_threat_model()
 assert m.digest==ThreatModel(tuple(reversed(m.threats))).digest
def test_missing_required_boundary_fails_closed():
 m=canonical_vol026_threat_model()
 with pytest.raises(SecurityContractError):ThreatModel(tuple(t for t in m.threats if t.asset!="secrets"))
def test_duplicate_threat_identity_rejected():
 m=canonical_vol026_threat_model();t=m.threats[0]
 with pytest.raises(SecurityContractError):ThreatModel(m.threats+(t,))
def test_empty_mitigation_or_validation_rejected():
 with pytest.raises(SecurityContractError):Threat("x","tool-authority","boundary","","test")



def test_threat_model_identity_uses_shared_canonical_bytes():
 m=canonical_vol026_threat_model()
 payload={"version":m.model_version,"threats":[{"id":t.threat_id,"asset":t.asset,"boundary":t.boundary,"mitigation":t.mitigation,"validation":t.validation} for t in m.threats]}
 assert m.digest==hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def test_threat_model_source_and_ai_mirror_are_byte_identical():
 from pathlib import Path
 root=Path(__file__).resolve().parents[2]
 assert (root/"skeleton/security/threat_model.py").read_bytes()==(root/"skeleton/ai/runtime/security/threat_model.py").read_bytes()
