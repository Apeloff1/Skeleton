"""Public CLI and bounded interactive UI acceptance without external services."""
from __future__ import annotations

import json

from skeleton.game.gameplay.harbor_crafting_salvage_cli import main
from skeleton.game.gameplay.harbor_crafting_salvage_ui import play_salvage_live
from skeleton.testing.test_harbor_crafting_salvage import inputs, actions


def _run(capsys, *argv):
    code = main(list(argv))
    output = capsys.readouterr()
    assert code == 0, output.err
    return json.loads(output.out)


def test_cli_run_verify_export_and_contracts(tmp_path, capsys):
    source, board = inputs()
    action_path = tmp_path / "actions.json"
    action_path.write_text(json.dumps(actions()))
    report = _run(capsys, "run", "--actions", str(action_path), "--require-complete")
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report))
    assert _run(capsys, "verify", "--report", str(report_path))["complete"]
    hint = _run(capsys, "hint", "--report", str(report_path))
    hint_path = tmp_path / "hint.json"
    hint_path.write_text(json.dumps(hint))
    assert _run(capsys, "verify-hint", "--guidance", str(hint_path))["recommended"] is None
    contract = _run(capsys, "contract-run", "--report", str(report_path), "--require-all")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract))
    assert _run(capsys, "contract-verify", "--contract-report", str(contract_path),
                "--require-all")["score"] == 55
    package = _run(capsys, "package")
    package_path = tmp_path / "package.json"
    package_path.write_text(json.dumps(package))
    play = _run(capsys, "play", "--package", str(package_path),
                "--actions", str(action_path), "--require-complete")
    play_path = tmp_path / "play.json"
    play_path.write_text(json.dumps(play))
    assert _run(capsys, "verify-play", "--play", str(play_path),
                "--require-complete")["complete"]
    accepted = _run(capsys, "accept", "--actions", str(action_path))
    accepted_path = tmp_path / "acceptance.json"
    accepted_path.write_text(json.dumps(accepted))
    assert _run(capsys, "verify-accept", "--acceptance", str(accepted_path))["complete"]


def test_live_rejects_bad_commands_without_advancing_state():
    source, board = inputs()
    prompts = iter(["move diagonal", "move east", "gather", "gather",
                    "salvage wrecked_skiff", "quit"])
    output = []
    report = play_salvage_live(source, board, input_fn=lambda _: next(prompts),
                               output_fn=output.append)
    assert len(report["actions"]) == 4
    assert report["state"]["cargo"] == ["wrecked_skiff"]
    assert any(line.startswith("rejected:") for line in output)
