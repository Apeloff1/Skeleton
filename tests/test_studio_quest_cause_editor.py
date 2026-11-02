"""Offline causal plan editor has strict source lease and CSP escaping."""
from __future__ import annotations

import copy
import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_quest_cause_editor import (
    render_quest_cause_editor,
)
from tests.test_studio_quest_cause_trace import prepared


def test_offline_review_editor_exposes_source_lease_and_no_network():
    documents, program, initial, plan = prepared()
    html = render_quest_cause_editor(documents, plan, authorized=True)
    assert b"Content-Security-Policy" in html
    assert b"connect-src 'none'" in html
    assert b"Export reviewed plan" in html
    assert b"canonical CLI replay still required" in html
    assert program.source_digest.encode() in html
    assert initial.digest.encode() in html
    assert b"fetch(" not in html


def test_editor_rejects_authority_forgery_and_stale_source():
    documents, program, initial, plan = prepared()
    with pytest.raises(PermissionError):
        render_quest_cause_editor(documents, plan, authorized=False)
    for key, value in (
        ("source_digest", "0" * 64),
        ("final_session_digest", "0" * 64),
        ("target_endings", ["unknown"]),
        ("target_endings", []),
        ("target_endings", [plan["target_endings"][0]] * 2),
        ("reviewed", 1),
    ):
        changed = copy.deepcopy(plan)
        changed[key] = value
        with pytest.raises(StudioQuestError):
            render_quest_cause_editor(documents, changed, authorized=True)
    documents["quest"]["stage_graph"][0]["reward"] = "changed"
    with pytest.raises(StudioQuestError):
        render_quest_cause_editor(documents, plan, authorized=True)
