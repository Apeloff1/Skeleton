import json

from skeleton.__main__ import main


def test_frontier_command_lists_actual_adapters(capsys):
    assert main(["frontier", "agents"]) == 0
    agents = json.loads(capsys.readouterr().out)["agents"]
    assert {agent["name"] for agent in agents} == {"gameforge.npc", "gameforge.logic", "jeeves.review"}


def test_memory_cli_retains_records_between_invocations(tmp_path, capsys):
    args = ["frontier", "--state-root", str(tmp_path), "memory"]
    assert main([*args, "put", "retained knowledge", "--id", "observation"]) == 0
    capsys.readouterr()
    assert main([*args, "search", "knowledge"]) == 0
    assert json.loads(capsys.readouterr().out)["items"][0]["id"] == "observation"
    assert main([*args, "delete", "observation"]) == 0
    capsys.readouterr()
    assert main([*args, "search", "knowledge"]) == 0
    assert json.loads(capsys.readouterr().out)["items"] == []


def test_cli_runs_real_npc_pipeline_and_reports_failures(tmp_path, capsys):
    args = ["frontier", "--state-root", str(tmp_path), "run", "gameforge.npc", "a merchant"]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["succeeded"] and result["output"]["dialogue_tree"]
    assert main([*args, "--context", '{"dialogue_beats":false}']) == 1
    assert not json.loads(capsys.readouterr().out)["succeeded"]


def test_cli_invalid_context_returns_nonzero_without_dispatch(tmp_path, capsys):
    assert main(["frontier", "--state-root", str(tmp_path), "run", "jeeves.review", "code", "--context", "[]"]) == 2
    assert "JSON options" in capsys.readouterr().err
