"""Source-replayed cross-feature character experience acceptance."""
from __future__ import annotations

import copy
import json
import os
import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from skeleton.ai.game_builder.studio_quest_branch_review import (
    PROMPT as BRANCH_PROMPT, propose_quest_branch_review,
    compile_quest_branch_review,
)
from skeleton.ai.game_builder.studio_quest_npc_relationships import (
    PROMPT as NPC_PROMPT, propose_quest_npc_relationships,
    compile_quest_npc_relationships,
)
from skeleton.ai.game_builder.studio_quest_dialogue import (
    PROMPT as DIALOGUE_PROMPT, propose_quest_dialogue, compile_quest_dialogue,
)
from skeleton.ai.game_builder.studio_quest_character_experience import (
    FILENAME, compile_quest_character_experience,
    compile_quest_character_experience_handoff,
    render_quest_character_walkthrough_html,
    publish_quest_character_experience,
    restore_quest_character_experience,
)
from tests.test_studio_quest_experience_handoff import fixture as experience_fixture


def fixture():
    docs, loc, awards, pacing, advisories = experience_fixture()
    program = compile_quest_program(docs)
    initial = start_quest(docs, authorized=True)
    leases = {"authorized": True, "expected_source_digest": program.source_digest,
              "expected_initial_session_digest": initial.digest}
    branch_plan = propose_quest_branch_review(
        docs, BRANCH_PROMPT, [["first", "help"]], [["first", "leave"]],
        "good", **leases)
    branch_plan["reviewed"] = True
    branch = compile_quest_branch_review(docs, branch_plan, **leases)
    npc_plan = propose_quest_npc_relationships(
        docs, NPC_PROMPT, ["guide"], [["first", "help"]], "good", **leases)
    npc_plan["actors"][0]["reviewed"] = True
    npc_plan["effects"] = [{
        "stage_id": "first", "choice": "help", "actor_id": "guide",
        "delta": 5, "reason": "The guide observed kindness", "reviewed": True,
    }]
    npc = compile_quest_npc_relationships(docs, npc_plan, **leases)
    dialogue_plan = propose_quest_dialogue(
        docs, npc, DIALOGUE_PROMPT, **leases)
    dialogue_plan["lines"][0].update({
        "speaker": "guide", "text": "An original welcome", "reviewed": True,
    })
    dialogue = compile_quest_dialogue(docs, npc, dialogue_plan, **leases)
    return (docs, branch, npc, dialogue, loc, awards, pacing, advisories,
            ["loud_audio"])


def test_full_canonical_character_experience_handoff():
    parts = fixture()
    result = compile_quest_character_experience(*parts, authorized=True)
    assert result["event_count"] == 1
    assert result["events"][0]["dialogue"][0]["text"] == "An original welcome"
    assert result["events"][0]["npc_trust_effects"][0]["after"] == 5
    assert result["final_trust"] == [{"actor_id": "guide", "trust": 5}]
    assert result["canonical_quest_replay_verified"] is True
    assert result["native_gameplay_verified"] is False
    handoff = compile_quest_character_experience_handoff(
        *parts, authorized=True)
    assert handoff["character_experience_digest"] == result["character_experience_digest"]
    assert handoff["target_ending"] == "good"
    assert handoff["release_certified"] is False


def test_mixed_branch_session_and_missing_consent_fail_closed():
    parts = list(fixture())
    docs = parts[0]
    program = compile_quest_program(docs)
    initial = start_quest(docs, authorized=True)
    leases = {"authorized": True, "expected_source_digest": program.source_digest,
              "expected_initial_session_digest": initial.digest}
    plan = propose_quest_branch_review(
        docs, BRANCH_PROMPT, [["first", "help"]], [["first", "leave"]],
        "good", **leases)
    plan["reviewed"] = True
    plan["selected"] = "right"
    parts[1] = compile_quest_branch_review(docs, plan, **leases)
    with pytest.raises(StudioQuestError, match="diverged"):
        compile_quest_character_experience(*parts, authorized=True)
    parts = list(fixture())
    parts[-1] = []
    with pytest.raises(StudioQuestError):
        compile_quest_character_experience(*parts, authorized=True)


def test_tampered_npc_and_dialogue_receipts_fail_closed():
    parts = list(fixture())
    forged = copy.deepcopy(parts[2])
    forged["final_trust"][0]["trust"] = 100
    parts[2] = forged
    with pytest.raises(StudioQuestError):
        compile_quest_character_experience(*parts, authorized=True)
    parts = list(fixture())
    forged = copy.deepcopy(parts[3])
    forged["authoring"]["lines"][0]["text"] = "Forged text"
    parts[3] = forged
    with pytest.raises(StudioQuestError):
        compile_quest_character_experience(*parts, authorized=True)


def test_private_publish_restore_and_symlink(tmp_path):
    parts = fixture()
    result = publish_quest_character_experience(
        *parts, tmp_path, authorized=True)
    assert result["file_write_performed"] is True
    restored = restore_quest_character_experience(
        *parts, tmp_path, authorized=True)
    assert restored["character_experience_digest"] == result["character_experience_digest"]
    with pytest.raises(FileExistsError):
        publish_quest_character_experience(*parts, tmp_path, authorized=True)
    (tmp_path / FILENAME).unlink()
    (tmp_path / FILENAME).symlink_to(tmp_path / "missing")
    with pytest.raises((StudioQuestError, OSError)):
        restore_quest_character_experience(
            *parts, tmp_path, authorized=True)


def test_html_and_cli_acceptance(tmp_path, capsys, monkeypatch):
    from scripts import studio_quest_character_experience_cli as cli
    parts = fixture()
    html = render_quest_character_walkthrough_html(
        *parts, authorized=True)
    assert b"connect-src 'none'" in html
    assert b"Next event" in html
    assert b"native gameplay" in html
    monkeypatch.setattr(cli, "read_blueprint", lambda _: parts[0])
    fields = ("branch", "npc", "dialogue", "localization", "achievements",
              "pacing", "advisories")
    args = ["--project", "original_demo"]
    for field, payload in zip(fields, parts[1:-1]):
        path = tmp_path / (field + ".json")
        path.write_text(json.dumps(payload))
        os.chmod(path, 0o600)
        args.extend(["--" + field + "-file", str(path)])
    args.extend(["--accept-topic", "loud_audio", "--handoff"])
    assert cli.main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["playable_handoff"]["events"][0]["dialogue"][0]["speaker"] == "guide"
