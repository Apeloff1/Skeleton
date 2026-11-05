"""Restart and custody regression for the original lighthouse authoring path.

These checks exercise durable state through independent flow instances, rather
than trusting in-memory objects returned by the initial authoring operation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from skeleton.jeeves.worlds.laptop_flow import LaptopFlow
from skeleton.jeeves.worlds.world_canon import CanonError

SAMPLES = Path(__file__).resolve().parents[2] / "examples" / "jeeves"


def _sample(name: str):
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


def _compiled(root: Path):
    author = LaptopFlow(root)
    proposal = author.propose(_sample("lighthouse_brief.json"))
    reviewed = author.review(
        "lighthouse", proposal["source_digest"],
        _sample("lighthouse_review.json"),
        "Approve the original rescue branch and its ending consequences.",
    )
    return author.compile("lighthouse", reviewed["source_digest"])


def test_restart_preserves_reviewed_handoff_and_save(tmp_path):
    receipt = _compiled(tmp_path)
    first = LaptopFlow(tmp_path)
    started = first.create_session("lighthouse", "save")
    advanced = first.choose(
        "lighthouse", "save", "rescue", started["session_digest"]
    )
    portable = first.export_session("lighthouse", "save")

    reopened = LaptopFlow(tmp_path)
    assert reopened.verify("lighthouse") == receipt
    assert reopened.inspect("lighthouse")["reviewed"] is True
    assert reopened.inspect_session("lighthouse", "save")["session_digest"] == advanced["session_digest"]
    preflight = reopened.preflight_restore("lighthouse", portable)
    assert isinstance(preflight, dict)
    restored = reopened.create_session("lighthouse", "restored", imported=portable)
    assert restored["session_digest"] == advanced["session_digest"]

    again = LaptopFlow(tmp_path)
    with pytest.raises(CanonError) as exc:
        again.create_session("lighthouse", "restored", imported=portable)
    assert exc.value.code == "session_already_exists"


def test_restart_detects_builder_corruption_before_session_mutation(tmp_path):
    receipt = _compiled(tmp_path)
    first = LaptopFlow(tmp_path)
    initial = first.create_session("lighthouse", "save")
    builder = tmp_path / receipt["builder_file"]
    builder.write_bytes(builder.read_bytes() + b" ")

    reopened = LaptopFlow(tmp_path)
    with pytest.raises(CanonError) as exc:
        reopened.choose("lighthouse", "save", "rescue", initial["session_digest"])
    assert exc.value.code == "laptop_builder_mismatch"
    # The failed operation must not advance the persisted session.
    assert LaptopFlow(tmp_path).sessions.inspect("lighthouse", "save")["session_digest"] == initial["session_digest"]
