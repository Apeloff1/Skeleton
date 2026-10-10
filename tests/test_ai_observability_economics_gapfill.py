from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from scripts.check_ai_observability_economics_gapfill import (
    ObservabilityEconomicsCandidateError,
    validate,
)


ROOT=Path(__file__).resolve().parents[1]


def head()->str:
    return subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()


def test_current_candidate_is_exact_head_valid() -> None:
    result=validate(ROOT,head=head())
    assert result["volume_count"]==8
    assert result["primary_test_count"]==8
    assert result["mirror_pair_count"]==9
    assert result["queued_frontier_preserved"] is True
    assert result["completion_checkbox"] is False
    assert result["production_authority"] is False


def test_malformed_reported_head_is_rejected() -> None:
    with pytest.raises(ObservabilityEconomicsCandidateError,match="reported exact head malformed"):
        validate(ROOT,head="bad")


def test_other_exact_head_is_rejected() -> None:
    other="a"*40 if head()!="a"*40 else "b"*40
    with pytest.raises(ObservabilityEconomicsCandidateError,match="does not match checkout"):
        validate(ROOT,head=other)


def test_candidate_volume_set_remains_deferred() -> None:
    frontier=json.loads((ROOT/"machine/ai_masterplan_continuation_frontier.json").read_text())
    candidate=json.loads((ROOT/"machine/ai_observability_economics_gapfill_candidate.json").read_text())
    refs=set(candidate["volume_refs"])
    assert refs.issubset(set(frontier["next_tranche"]["queued_volume_refs"]))
    assert refs.isdisjoint(set(frontier["next_tranche"]["scheduled_volume_refs"]))
