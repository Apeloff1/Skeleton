from core.shift_supervisor.prompt_eval import assert_prompt_contract, evaluate_prompt_contract
from core.shift_supervisor.prompts import PROMPT_CONTRACT_VERSION, ROLE_CONTRACTS, compose_role_prompt


def test_prompt_contract_eval_is_green() -> None:
    result = evaluate_prompt_contract()
    assert result.version == PROMPT_CONTRACT_VERSION
    assert result.passed is True
    assert result.missing_constitution_invariants == ()
    assert result.missing_role_invariants == ()
    assert_prompt_contract()


def test_all_execution_roles_have_distinct_contracts() -> None:
    expected = {"supervisor", "shift_manager", "secretary", "researcher", "lead", "reviewer", "verifier"}
    assert set(ROLE_CONTRACTS) == expected
    rendered = {role: compose_role_prompt(role) for role in expected}
    assert len(set(rendered.values())) == len(expected)


def test_role_prompt_can_narrow_but_keeps_canonical_role_contract() -> None:
    prompt = compose_role_prompt("verifier", "Validate malformed plan rejection with focused tests.")
    assert "Own proof" in prompt
    assert "TASK-SPECIFIC ROLE DETAIL" in prompt
    assert "malformed plan rejection" in prompt
