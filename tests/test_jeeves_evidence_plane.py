from skeleton.jeeves.evidence.ledger import LedgerEvidence, LedgerKind, validate_ledger

def test_evidence_fingerprint_is_stable():
    x=LedgerEvidence("r1",LedgerKind.OBSERVATION,"observed",0.9)
    assert x.fingerprint==x.fingerprint
    assert validate_ledger((x,))==(x.fingerprint,)

def test_duplicate_refs_rejected():
    x=LedgerEvidence("r1")
    try: validate_ledger((x,x))
    except ValueError as e: assert "duplicate" in str(e)
    else: raise AssertionError("duplicate accepted")
