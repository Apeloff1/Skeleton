"""Source-bound ending witness regression: actual quest engine, no forged eligibility."""
from __future__ import annotations

from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, replay_quest,
)
from skeleton.ai.game_builder.studio_quest_ending_witness import (
    FILENAME, compile_ending_witness, replay_ending_witness,
    publish_ending_witness, restore_ending_witness, render_ending_witness_html,
)


def docs():
    return {
        "quest": {
            "project_id": "original", "release_certified": False,
            "stage_graph": [
                {"id": "meet", "prerequisites": [], "alternatives": ["help", "ignore"],
                 "reward": "met", "choice_effects": {
                     "help": ["choice:meet:helped"]}},
                {"id": "return", "prerequisites": ["meet"],
                 "alternatives": ["stay", "leave"], "reward": "returned"},
            ],
        },
        "narrative": {
            "project_id": "original", "release_certified": False,
            "endings": [
                {"id": "kind", "requires": ["choice:meet:helped", "returned"]},
                {"id": "impossible", "requires": ["unobserved_world_evidence"]},
            ],
        },
    }


def params(source=None, actions=None, **changes):
    source = source or docs()
    actions = actions if actions is not None else []
    result = {
        "target_ending": "kind", "initial_actions": actions,
        "max_states": 128, "max_depth": 4, "authorized": True,
        "expected_source_digest": compile_quest_program(source).source_digest,
        "expected_initial_session_digest": replay_quest(
            source, actions, authorized=True).digest,
    }
    result.update(changes)
    return result


def test_finds_canonical_choice_effect_witness_and_replays():
    source = docs()
    options = params(source)
    receipt = compile_ending_witness(source, **options)
    assert receipt["status"] == "found"
    assert receipt["witness_actions"] == [["meet", "help"], ["return", "stay"]]
    assert receipt["playable_quest_replay_verified"]
    assert receipt["witness_progress"]["sandbox_endings_eligible"] == ["kind"]
    assert not receipt["native_gameplay_verified"]
    assert not receipt["release_certified"]
    assert replay_ending_witness(
        source, receipt, authorized=True,
        expected_source_digest=options["expected_source_digest"],
        expected_initial_session_digest=options["expected_initial_session_digest"]) == receipt


def test_unreachable_is_only_exhaustive_and_budget_is_inconclusive():
    source = docs()
    unreachable = compile_ending_witness(
        source, **params(source, target_ending="impossible"))
    assert unreachable["status"] == "unreachable"
    assert unreachable["search_exhaustive"]
    assert unreachable["witness_actions"] == []
    bounded = compile_ending_witness(
        source, **params(source, max_states=1))
    assert bounded["status"] == "inconclusive"
    assert not bounded["search_exhaustive"]
    depth = compile_ending_witness(
        source, **params(source, max_depth=1))
    assert depth["status"] == "inconclusive"


def test_prefix_is_replayed_and_source_session_leases_fail_closed():
    source = docs()
    prefix = [["meet", "help"]]
    receipt = compile_ending_witness(source, **params(source, prefix))
    assert receipt["witness_actions"][:1] == prefix
    with pytest.raises(PermissionError):
        compile_ending_witness(source, **params(source, authorized=False))
    with pytest.raises(StudioQuestError, match="stale"):
        compile_ending_witness(
            source, **params(source, expected_source_digest="0" * 64))
    with pytest.raises(StudioQuestError, match="stale"):
        compile_ending_witness(
            source, **params(source, expected_initial_session_digest="0" * 64))
    with pytest.raises(StudioQuestError):
        compile_ending_witness(source, **params(source, max_states=True))
    with pytest.raises(StudioQuestError):
        compile_ending_witness(source, **params(source, initial_actions=[["meet", "invented"]]))


def test_tampered_receipts_and_private_publication_are_rejected(tmp_path):
    source = docs()
    options = params(source)
    receipt = compile_ending_witness(source, **options)
    kwargs = {
        "authorized": True,
        "expected_source_digest": options["expected_source_digest"],
        "expected_initial_session_digest": options["expected_initial_session_digest"],
    }
    altered = deepcopy(receipt)
    altered["status"] = "unreachable"
    with pytest.raises(StudioQuestError, match="canonical replay"):
        replay_ending_witness(source, altered, **kwargs)
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    publish_ending_witness(source, receipt, private, **kwargs)
    assert restore_ending_witness(source, private, **kwargs) == receipt
    with pytest.raises(FileExistsError):
        publish_ending_witness(source, receipt, private, **kwargs)
    target = private / FILENAME
    target.write_text('{"schema":"one","schema":"two"}')
    target.chmod(0o600)
    with pytest.raises(StudioQuestError, match="duplicate"):
        restore_ending_witness(source, private, **kwargs)
    target.unlink()
    target.symlink_to(private / "missing")
    with pytest.raises(OSError):
        restore_ending_witness(source, private, **kwargs)


def test_jeeves_router_authority_and_cli_are_consistent(monkeypatch, capsys):
    import skeleton.ai.agents.jeeves.studio_quest_ending_witness_tool as adapter
    import scripts.studio_quest_ending_witness_cli as cli
    from skeleton.ai.agents.jeeves.studio_world_tool_router import route_world_tool
    source = docs()
    monkeypatch.setattr(adapter, "read_blueprint", lambda _: source)
    monkeypatch.setattr(cli, "read_blueprint", lambda _: source)
    options = params(source)
    request = {
        "schema": adapter.REQUEST_SCHEMA, "project_id": "original",
        **{key: value for key, value in options.items() if key != "authorized"},
    }
    direct = adapter.execute_quest_ending_witness_tool(request, authorized=True)
    with pytest.raises(PermissionError):
        route_world_tool(
            {"tool": "studio_original_quest_ending_witness",
             "arguments": request}, authorized=False)
    routed = route_world_tool(
        {"tool": "studio_original_quest_ending_witness",
         "arguments": request}, authorized=True)
    assert routed["result"] == direct
    assert not routed["file_write_performed"]
    assert cli.main([
        "--project", "original",
        "--expected-source", options["expected_source_digest"],
        "--expected-session", options["expected_initial_session_digest"],
        "--target-ending", "kind",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["witness"]["status"] == "found"
    html = render_ending_witness_html(
        source, direct["detail"], authorized=True,
        expected_source_digest=options["expected_source_digest"],
        expected_initial_session_digest=options["expected_initial_session_digest"])
    assert b"default-src 'none'" in html
    assert b"native gameplay and release not verified" in html
