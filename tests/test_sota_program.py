from __future__ import annotations

import json

import pytest

from skeleton.application import (
    LANES,
    SOTA_PROGRAM_ISSUE,
    SOTA_PROGRAM_VERSION,
    get_lane,
    sota_program,
)
from skeleton.application.sota_program import _ALLOWED_EVIDENCE, _ALLOWED_STATUS


def test_sota_program_schema_and_law() -> None:
    payload = sota_program()
    assert payload["schema_version"] == SOTA_PROGRAM_VERSION == 1
    assert payload["issue"] == SOTA_PROGRAM_ISSUE == 807
    assert payload["law"] == "batch_complete_is_not_sota"
    assert payload["sota_ready"] is False
    assert payload["lane_count"] == 10
    assert payload["lanes_with_eval_evidence"] == 0


def test_lanes_cover_b001_through_b100_without_overlap() -> None:
    ids = [lane.id for lane in LANES]
    assert len(ids) == len(set(ids)) == 10
    batches: list[int] = []
    for lane in LANES:
        first = int(lane.first_batch[1:])
        last = int(lane.last_batch[1:])
        assert last - first == 9
        batches.extend(range(first, last + 1))
        assert lane.status in _ALLOWED_STATUS
        assert lane.evidence in _ALLOWED_EVIDENCE
        assert lane.module.startswith("skeleton.")
        assert lane.owner_issue > 0
    assert batches == list(range(1, 101))


def test_get_lane_lookup_and_fail_closed() -> None:
    assert get_lane(" gameplay ").id == "gameplay"
    assert get_lane("PLATFORM").owner_issue == 950
    with pytest.raises(KeyError, match="unknown sota lane"):
        get_lane("mega-branch")
    with pytest.raises(ValueError):
        get_lane("   ")
    with pytest.raises(TypeError):
        get_lane(807)  # type: ignore[arg-type]


def test_cli_sota_prints_the_same_payload(capsys: pytest.CaptureFixture[str]) -> None:
    from skeleton.__main__ import main

    assert main(["sota"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == sota_program()


def test_cli_sota_lane_filter(capsys: pytest.CaptureFixture[str]) -> None:
    from skeleton.__main__ import main

    assert main(["sota", "quality"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["id"] == "quality"
    assert printed["first_batch"] == "B071"
    assert main(["sota", "nope"]) == 2
