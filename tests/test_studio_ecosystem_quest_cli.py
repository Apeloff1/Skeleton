"""The operator CLI exposes real bounded, reproducible quest choice execution."""
import json
import pytest
from scripts.studio_ecosystem_cli import main
from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import compile_quest_program


def test_three_stage_actual_source_replay(capsys):
    pid = "studio_arena_fighting_glacial_fjord"
    program = compile_quest_program(read_blueprint(pid))
    actions = [[stage.key, stage.alternatives[0]] for stage in program.stages]
    assert main(["--play-quest", "--project", pid,
                 "--quest-actions", json.dumps(actions)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["progress"]["stage_completed"] == 3
    assert report["receipt"]["release_certified"] is False
    assert not report["progress"]["external_evidence_verified"]


def test_initial_quest_lists_available_stage(capsys):
    assert main(["--play-quest", "--project",
                 "studio_puzzle_expedition_copper_mesa"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["progress"]["available"] == ["survey"]


@pytest.mark.parametrize("arguments", [
    ["--play-quest"], ["--quest-actions", "[]"],
    ["--play-quest", "--project", "studio_arena_fighting_glacial_fjord", "--quest-actions", "bad"],
    ["--play-quest", "--project", "studio_arena_fighting_glacial_fjord", "--search", "arena"],
    ["--play-quest", "--project", "studio_arena_fighting_glacial_fjord",
     "--quest-actions", "x" * 17000],
])
def test_invalid_inputs_reject(arguments):
    with pytest.raises(SystemExit) as exc:
        main(arguments)
    assert exc.value.code == 2
