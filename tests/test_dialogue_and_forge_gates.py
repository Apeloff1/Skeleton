"""A dialogue edge must land, and an empty forge project is not a pass."""

import pytest

from skeleton.intelligence.dialogue_verifier import DialogueVerifier
from skeleton.intelligence.forge_verifier import ForgeVerifier


def _tree():
    return {
        "entry": "root",
        "nodes": {
            "root": {"line": "The merchant waits", "edges": [{"target": "end"}]},
            "end": {"line": "Done", "terminal": True, "edges": []},
        },
    }


def test_a_dialogue_without_a_description_or_a_real_edge_is_refused() -> None:
    verifier = DialogueVerifier(accept_at=0.7)
    refused = verifier.verify(_tree())
    assert refused.accepted is False
    assert any(issue.startswith("hard:") for issue in refused.issues)
    broken = _tree()
    broken["nodes"]["root"]["edges"] = [{"target": "missing"}]
    assert verifier.verify(broken, description="merchant waits").accepted is False
    accepted = verifier.verify(_tree(), description="merchant waits")
    assert accepted.accepted is True
    with pytest.raises(ValueError):
        DialogueVerifier(accept_at=0)


def test_an_empty_forge_project_is_not_accepted() -> None:
    verifier = ForgeVerifier(accept_at=0.7)
    empty = verifier.verify({})
    assert empty.accepted is False
    assert empty.score == 0.0
    assert empty.reason == "no_scripts"
    unsafe = verifier.verify({"player.gd": "extends Node\nfunc run():\n    eval('1')\n"})
    assert unsafe.accepted is False
    assert any("unsafe" in issue for issue in unsafe.file_reports[0].hard_issues)
