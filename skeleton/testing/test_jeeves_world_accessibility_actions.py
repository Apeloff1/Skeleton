"""Accessible choice disambiguation, branch coverage and landmark semantics."""
from __future__ import annotations

from copy import deepcopy

import pytest

from skeleton.jeeves.worlds.accessibility import (
    propose_accessibility, prove_accessibility, render_accessibility_html,
)
from skeleton.jeeves.worlds.world_canon import CanonError, propose, prove


def scenario():
    world = propose(world_id="harbor", premise="An original harbor council",
                    protagonist="Mara", region="Glass Bay", goal="Sign a treaty")
    world["scenes"].append({"id": "refusal", "title": "Refusal",
                            "narrative": "The council rejects the proposal."})
    world["choices"].append({"id": "refuse_goal", "from": "opening", "to": "refusal",
                             "label": "Reject treaty", "requires": [], "grants": []})
    world["endings"].append({"scene": "refusal", "label": "Treaty rejected"})
    prove(world)
    source = propose_accessibility(
        world, prompt="Accessible treaty negotiation",
        scenes=[{"id": row["id"], "summary": "Describe " + row["title"],
                 "landmark": "region"}
                for row in sorted(world["scenes"], key=lambda row: row["id"])],
        choices=[{"id": row["id"], "action": "Choose " + row["label"]}
                 for row in sorted(world["choices"], key=lambda row: row["id"])],
        endings=[{"scene": row["scene"], "summary": "Outcome " + row["label"]}
                 for row in sorted(world["endings"], key=lambda row: row["scene"])])
    return world, source


def test_branch_complete_actions_and_named_regions():
    world, source = scenario()
    proof = prove_accessibility(source, world)
    assert set(proof["ending_witnesses"]) == {"refusal", "resolution"}
    source["approved"] = True
    source["review_note"] = "Reviewed"
    page = render_accessibility_html(source, world)
    assert b'description.landmark === "region"' in page
    assert b'setAttribute("role", "region")' in page
    assert b"connect-src 'none'" in page


def test_duplicate_action_label_fails_closed():
    world, source = scenario()
    bad = deepcopy(source)
    bad["choices"][1]["action"] = bad["choices"][0]["action"]
    with pytest.raises(CanonError) as exc:
        prove_accessibility(bad, world)
    assert exc.value.code == "accessibility_ambiguous_action"


def test_world_revision_invalidates_accessibility():
    world, source = scenario()
    world["scenes"][0]["title"] = "Revised council"
    with pytest.raises(CanonError) as exc:
        prove_accessibility(source, world)
    assert exc.value.code == "accessibility_source_lease_mismatch"
