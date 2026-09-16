from __future__ import annotations

from dataclasses import dataclass

from .prompts import AUTONOMOUS_ENGINEERING_CONSTITUTION, PROMPT_CONTRACT_VERSION, ROLE_CONTRACTS


@dataclass(frozen=True, slots=True)
class PromptContractEvaluation:
    version: str
    passed: bool
    missing_constitution_invariants: tuple[str, ...]
    missing_role_invariants: tuple[str, ...]


_CONSTITUTION_INVARIANTS: dict[str, tuple[str, ...]] = {
    "canonical_plan": ("canonical plan", "executable source"),
    "four_agent_squad": ("exactly one", "four-agent squad", "researcher", "lead implementer", "adversarial reviewer", "verifier"),
    "anti_swarm": ("one task has one active squad lease", "one worker belongs to at most one active squad"),
    "conflict_domains": ("conflict-domain", "independent tasks"),
    "evidence_completion": ("evidence wins over consensus", "completion requires durable evidence"),
    "failure_durability": ("failure is durable data", "expired leases"),
    "secret_boundary": ("credentials/secrets", "least privilege"),
    "untrusted_input": ("untrusted data", "higher-priority instructions"),
    "bounded_reasoning": ("bounded objectives and stop conditions", "avoid repeated model calls"),
    "traceability": ("prompt contracts are versioned", "reconstructable"),
}

_ROLE_INVARIANTS: dict[str, tuple[str, ...]] = {
    "supervisor": ("single canonical executable plan", "safe squad capacity"),
    "shift_manager": ("capacity truth", "never emit direct worker assignments"),
    "secretary": ("plan completeness", "never dispatch workers"),
    "researcher": ("evidence", "do not independently implement"),
    "lead": ("implementation artifact", "reviewer/verifier findings"),
    "reviewer": ("independent adversarial", "do not rubber-stamp"),
    "verifier": ("own proof", "do not mark completion from confidence alone"),
}


def evaluate_prompt_contract() -> PromptContractEvaluation:
    constitution = AUTONOMOUS_ENGINEERING_CONSTITUTION.casefold()
    missing_constitution = tuple(
        name
        for name, fragments in _CONSTITUTION_INVARIANTS.items()
        if not all(fragment.casefold() in constitution for fragment in fragments)
    )

    missing_roles: list[str] = []
    for role, fragments in _ROLE_INVARIANTS.items():
        value = ROLE_CONTRACTS.get(role, "").casefold()
        if not all(fragment.casefold() in value for fragment in fragments):
            missing_roles.append(role)

    return PromptContractEvaluation(
        version=PROMPT_CONTRACT_VERSION,
        passed=not missing_constitution and not missing_roles,
        missing_constitution_invariants=missing_constitution,
        missing_role_invariants=tuple(missing_roles),
    )


def assert_prompt_contract() -> None:
    result = evaluate_prompt_contract()
    if not result.passed:
        raise RuntimeError(
            "prompt contract evaluation failed: "
            f"constitution={result.missing_constitution_invariants}, "
            f"roles={result.missing_role_invariants}"
        )
