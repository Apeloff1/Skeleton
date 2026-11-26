"""Original faction social rules replay through CLI and typed Jeeves."""
from copy import deepcopy
import json

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_faction_reputation import (
    REPUTATION_SCHEMA, simulate_faction_reputation,
)
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    FACTION_REPUTATION_REQUEST_SCHEMA, execute_faction_reputation_tool,
)

PROJECT = "studio_arena_fighting_glacial_fjord"
DECISIONS = ["publish_ledger", "neutral_audit"]


def test_original_faction_reputation_is_deterministic_and_source_bound():
    source = read_blueprint(PROJECT)
    original = deepcopy(source)
    digest = audit_canon_source(source, authorized=True)["source_digest"]
    result = simulate_faction_reputation(
        source, DECISIONS, expected_source_digest=digest, authorized=True)
    assert source == original
    assert result == simulate_faction_reputation(
        source, deepcopy(DECISIONS), expected_source_digest=digest, authorized=True)
    assert result["schema"] == REPUTATION_SCHEMA
    assert result["initial_reputation"] == {
        "claimants": 0, "operators": 0, "residents": 0}
    assert result["final_reputation"] == {
        "claimants": -1, "operators": 3, "residents": 3}
    assert result["steps"][0]["after_digest"] == result["steps"][1]["before_digest"]
    assert result["decision_count"] == 2
    assert result["external_evidence_verified"] is False
    assert result["release_certified"] is False


def test_reputation_rejects_forgery_repetition_and_stale_source():
    source = read_blueprint(PROJECT)
    with pytest.raises(PermissionError):
        simulate_faction_reputation(source, DECISIONS, authorized=False)
    for decisions in (["unknown"], ["publish_ledger", "publish_ledger"],
                      ["publish_ledger"] * 33, [True], "publish_ledger"):
        with pytest.raises(StudioQuestError):
            simulate_faction_reputation(source, decisions, authorized=True)
    with pytest.raises(StudioQuestError, match="stale"):
        simulate_faction_reputation(source, DECISIONS, authorized=True,
                                    expected_source_digest="0" * 64)
    malformed = deepcopy(source)
    malformed["cast"]["social_rules"][0]["reputation_delta"]["residents"] = True
    with pytest.raises(StudioQuestError, match="deltas"):
        simulate_faction_reputation(malformed, DECISIONS, authorized=True)
    overflow = deepcopy(source)
    overflow["cast"]["factions"][0]["reputation"] = 100
    with pytest.raises(StudioQuestError, match="bounded"):
        simulate_faction_reputation(overflow, ["publish_ledger"], authorized=True)


def test_reputation_cli_and_jeeves_share_receipts(capsys):
    from scripts.studio_ecosystem_cli import main
    source = read_blueprint(PROJECT)
    digest = audit_canon_source(source, authorized=True)["source_digest"]
    request = {
        "schema": FACTION_REPUTATION_REQUEST_SCHEMA,
        "project_id": PROJECT,
        "expected_source_digest": digest,
        "decisions": DECISIONS,
    }
    with pytest.raises(PermissionError):
        execute_faction_reputation_tool(request, authorized=False)
    typed = execute_faction_reputation_tool(request, authorized=True)
    assert typed["detail"]["decision_count"] == 2
    assert typed["file_write_performed"] is False
    assert main(["--project", PROJECT, "--faction-reputation",
                 "--faction-decisions", json.dumps(DECISIONS),
                 "--faction-expected-digest", digest]) == 0
    assert json.loads(capsys.readouterr().out) == typed["detail"]
    with pytest.raises(StudioQuestError):
        execute_faction_reputation_tool({**request, "unexpected": True},
                                        authorized=True)
    with pytest.raises(SystemExit):
        main(["--project", PROJECT, "--faction-decisions", "[]"])
