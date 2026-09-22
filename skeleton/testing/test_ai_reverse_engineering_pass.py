from __future__ import annotations

import json

from scripts import check_ai_reverse_engineering_pass as checker


def _reverse() -> dict:
    return json.loads(checker.REVERSE.read_text(encoding="utf-8"))


def test_reverse_engineering_passes_validator() -> None:
    assert checker.validate() == []


def test_all_terminal_chains_have_independent_commit_bound_proof() -> None:
    reverse = _reverse()
    for chain in reverse["terminal_chains"]:
        assert "full_git_sha" in chain["minimum_proof_bundle"]
        assert "independent_verification" in chain["minimum_proof_bundle"]


def test_all_build_waves_are_reverse_covered() -> None:
    reverse = _reverse()
    sequence = json.loads(checker.SEQUENCE.read_text(encoding="utf-8"))
    expected = {wave["id"] for wave in sequence["waves"]}
    covered = {
        ref
        for chain in reverse["terminal_chains"]
        for ref in chain["required_wave_refs"]
    }
    assert covered == expected


def test_reverse_pass_does_not_create_completion_authority() -> None:
    scope = _reverse()["scope_policy"]
    assert scope["adds_top_level_architecture"] is False
    assert scope["creates_completion_authority"] is False
    assert scope["completion_remains_derived_from_accountability"] is True


def test_every_chain_has_negative_space_and_shortcut_detection() -> None:
    negative_modes = {
        "negative_test","fault_injection","restart_test","rollback_test",
        "adversarial","incident_drill","privacy_test","deletion_test",
    }
    for chain in _reverse()["terminal_chains"]:
        assert negative_modes.intersection(chain["required_evidence_modes"])
        assert len(chain["failure_oracles"]) >= 3
        assert len(chain["forbidden_shortcuts"]) >= 3


def test_reverse_constraints_are_complete_and_ordered() -> None:
    ids = [item["id"] for item in _reverse()["global_reverse_constraints"]]
    assert ids == [f"RC-{i:02d}" for i in range(1, 9)]


def test_reverse_checker_main_success_path() -> None:
    assert checker.main() == 0
