"""Fail-closed typed Jeeves tool discovery, dispatch and offline CLI."""
import io
import json
import sys

import pytest

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_canon_proof import audit_canon_source
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.agents.jeeves.studio_walk_tool import (
    ENDING_ATLAS_REQUEST_SCHEMA, execute_ending_atlas_tool,
)
from skeleton.ai.agents.jeeves.studio_world_tool_router import (
    ROUTER_SCHEMA, route_world_tool, world_tool_catalog,
)

PROJECT = "studio_arena_fighting_glacial_fjord"


def fixture():
    docs = read_blueprint(PROJECT)
    source = audit_canon_source(docs, authorized=True)["source_digest"]
    return {
        "tool": "studio_authored_ending_atlas",
        "arguments": {
            "schema": ENDING_ATLAS_REQUEST_SCHEMA, "project_id": PROJECT,
            "expected_source_digest": source, "actions": [],
        },
    }


def test_catalog_is_stable_and_contains_original_world_capabilities():
    first = world_tool_catalog()
    assert first == world_tool_catalog()
    assert first["schema"] == ROUTER_SCHEMA
    assert first["tool_count"] >= 20
    names = [item["name"] for item in first["tools"]]
    assert len(names) == len(set(names))
    assert "studio_authored_ending_atlas" in names
    assert "studio_authored_choice_impact" in names
    assert "studio_original_objective_board" in names
    assert all(item["descriptor"]["parameters"]["properties"]["schema"]["const"]
               for item in first["tools"])


def test_router_matches_exact_typed_jeeves_result():
    request = fixture()
    direct = execute_ending_atlas_tool(request["arguments"], authorized=True)
    routed = route_world_tool(request, authorized=True)
    assert routed["result"] == direct
    assert routed["result_digest"]
    assert routed["file_write_performed"] is False
    assert routed["release_certified"] is False
    assert routed == route_world_tool(request, authorized=True)


@pytest.mark.parametrize("mutation", [
    {"tool": "__import__('os').system('true')"},
    {"tool": "studio_authored_ending_atlas", "arguments": {"schema": "forged"}},
    {"extra": True},
    {"arguments": {"authorized": True}},
    {"arguments": {"allow_authoring": True}},
    {"arguments": []},
])
def test_untrusted_dispatch_and_authority_fields_fail_closed(mutation):
    request = fixture()
    request.update(mutation)
    with pytest.raises((StudioQuestError, PermissionError)):
        route_world_tool(request, authorized=True)


def test_authoring_requires_separate_out_of_band_opt_in():
    catalog = world_tool_catalog()
    authored = next(item for item in catalog["tools"]
                    if item["explicit_authoring_permission_required"])
    request = {
        "tool": authored["name"],
        "arguments": {
            "schema": authored["descriptor"]["parameters"]["properties"]["schema"]["const"],
        },
    }
    with pytest.raises(PermissionError):
        route_world_tool(request, authorized=True)
    with pytest.raises(PermissionError):
        route_world_tool(fixture(), authorized=False)


def test_cli_catalog_and_typed_stdin_round_trip(monkeypatch, capsys):
    from scripts.studio_world_tool_cli import main
    assert main(["--catalog"]) == 0
    catalog = json.loads(capsys.readouterr().out)
    assert catalog == world_tool_catalog()
    request = fixture()
    stream = io.TextIOWrapper(
        io.BytesIO(json.dumps(request).encode("utf-8")), encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", stream)
    assert main(["--execute-stdin"]) == 0
    assert json.loads(capsys.readouterr().out) == route_world_tool(
        request, authorized=True)
    with pytest.raises(SystemExit):
        main(["--catalog", "--allow-authoring"])


def test_cli_rejects_duplicate_keys_and_forged_schema(monkeypatch):
    from scripts.studio_world_tool_cli import main
    for raw in (b'{"tool":"a","tool":"b","arguments":{}}',
                b'{"tool":"a","arguments":{"schema":NaN}}',
                b'{"tool":"a","arguments":{},"extra":1}'):
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(
            io.BytesIO(raw), encoding="utf-8"))
        with pytest.raises(SystemExit):
            main(["--execute-stdin"])
