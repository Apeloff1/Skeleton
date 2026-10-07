from __future__ import annotations

from pathlib import Path

from scripts.check_ai_closure_evidence import EXPECTED_IMPLEMENTATION_STATES


ROOT = Path(__file__).resolve().parents[1]

VERIFIERS = (
    "scripts/verify_ai_accountability_closure_map.py",
    "scripts/verify_ai_phase_inheritance.py",
    "scripts/verify_context_compiler_closure.py",
    "scripts/verify_engine_application_boundary_closure.py",
    "scripts/verify_memory_authority_closure.py",
    "scripts/verify_provider_protocol_closure.py",
    "scripts/verify_streaming_protocol_closure.py",
    "scripts/verify_verification_evidence_closure.py",
    "scripts/verify_masterplan_completion.py",
)

FORBIDDEN_CLOSURE_STATE_ALIASES = (
    'get("implementation_state") != "closed"',
    '("implementation_state", "closed")',
    'closure_impl_state != "closed"',
)


def test_closure_implementation_state_vocabulary_is_not_closure_decision_vocabulary() -> None:
    assert "complete" in EXPECTED_IMPLEMENTATION_STATES
    assert "closed" not in EXPECTED_IMPLEMENTATION_STATES


def test_independent_verifiers_do_not_require_invalid_closed_implementation_state() -> None:
    offenders: list[str] = []
    for relative in VERIFIERS:
        source = (ROOT / relative).read_text(encoding="utf-8")
        for token in FORBIDDEN_CLOSURE_STATE_ALIASES:
            if token in source:
                offenders.append(f"{relative}: {token}")

    assert offenders == []
