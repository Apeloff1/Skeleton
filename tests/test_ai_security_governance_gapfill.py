from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from scripts.check_ai_security_governance_gapfill import (
    SecurityGovernanceCandidateError,
    validate,
)


ROOT=Path(__file__).resolve().parents[1]


def head()->str:
    return subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()


def test_current_candidate_is_exact_head_valid() -> None:
    result=validate(ROOT,head=head())
    assert result["volume_count"]==10
    assert result["queued_frontier_preserved"] is True
    assert result["completion_checkbox"] is False
    assert result["production_authority"] is False
    assert result["mirror_pair_count"]>=12


def test_malformed_reported_head_is_rejected() -> None:
    with pytest.raises(SecurityGovernanceCandidateError,match="reported exact head malformed"):
        validate(ROOT,head="bad")


def test_other_exact_head_is_rejected() -> None:
    other="a"*40 if head()!="a"*40 else "b"*40
    with pytest.raises(SecurityGovernanceCandidateError,match="does not match checkout"):
        validate(ROOT,head=other)


def test_candidate_preserves_frontier_membership_without_reintroduction() -> None:
    frontier=json.loads((ROOT/"machine/ai_masterplan_continuation_frontier.json").read_text())
    candidate=json.loads((ROOT/"machine/ai_security_governance_gapfill_candidate.json").read_text())
    refs=set(candidate["volume_refs"])
    source=set(frontier["continuation_source"]["volume_refs"])
    queued=set(frontier["next_tranche"]["queued_volume_refs"])
    scheduled=set(frontier["next_tranche"]["scheduled_volume_refs"])
    assert (refs & source).issubset(queued)
    assert (refs - source).isdisjoint(queued)
    assert refs.isdisjoint(scheduled)
