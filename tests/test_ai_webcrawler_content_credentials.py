from skeleton.ai.webcrawler.content_credentials import CredentialObservation,credential_trust_delta
def test_absence_is_not_positive_authenticity_signal():
 assert credential_trust_delta(CredentialObservation("absent"))==0
 assert credential_trust_delta(CredentialObservation("unknown"))==0
def test_invalid_credential_is_negative_signal():
 assert credential_trust_delta(CredentialObservation("invalid"))<0
def test_verified_credential_is_small_bounded_signal():
 assert 0<credential_trust_delta(CredentialObservation("verified",issuer="issuer"))<=.05
def test_unknown_status_is_rejected():
 try:CredentialObservation("trusted")
 except ValueError:pass
 else:raise AssertionError("unknown credential state accepted")
