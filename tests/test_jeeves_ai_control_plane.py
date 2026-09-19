from skeleton.jeeves.ai.contracts import ContractRecord, ContractState, validate_contract
from skeleton.jeeves.ai.orchestration import OrchestrRecord, validate_orchestr
from skeleton.jeeves.ai.evaluation import EvalRecord, validate_eval

def test_contract_record_is_deterministic():
    r=ContractRecord("policy",ContractState.READY,{"scope":"repo"},("e1",))
    assert r.digest==r.digest
    assert validate_contract((r,))==(r.digest,)

def test_orchestration_rejects_duplicates():
    a=OrchestrRecord("plan")
    assert validate_orchestr((a,))==(a.digest,)

def test_evaluation_rejects_duplicate_names():
    a=EvalRecord("case")
    try:
        validate_eval((a,a))
    except ValueError as exc:
        assert "duplicate" in str(exc)
    else:
        raise AssertionError("duplicate accepted")

def test_state_surface_is_explicit():
    assert {x.value for x in ContractState}=={"new","ready","running","blocked","done","failed"}
