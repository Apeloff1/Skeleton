"""Recovered installed operator surfaces with explicit owner authority."""
from __future__ import annotations

import ast
import configparser
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

from skeleton.__main__ import main

ROOT = Path(__file__).resolve().parents[2]
OWNERS = (
    ("jeeves-native-chat", "skeleton.jeeves.agent.native_cli", "main"),
    ("jeeves-native-acceptance", "skeleton.jeeves.agent.native_acceptance_cli", "main"),
    ("jeeves-native-batch", "skeleton.jeeves.agent.native_batch_cli", "main"),
    ("jeeves-native-durable-batch", "skeleton.jeeves.agent.native_durable_batch_cli", "run"),
    ("jeeves-native-eval", "skeleton.jeeves.agent.native_eval_cli", "main"),
    ("jeeves-native-operator-session", "skeleton.jeeves.agent.native_operator_session_cli", "main"),
    ("jeeves-native-session", "skeleton.jeeves.agent.native_session_cli", "main"),
    ("world-reviewed-delivery", "skeleton.jeeves.worlds.world_delivery_cli", "run"),
    ("world-reviewed-edit", "skeleton.jeeves.worlds.world_edit_cli", "run"),
    ("world-reviewed-handoff", "skeleton.jeeves.worlds.world_handoff_cli", "run"),
    ("world-reviewed-session", "skeleton.jeeves.worlds.world_session_cli", "run"),
    ("original-foundation", "skeleton.game.generation.original_foundation_cli", "main"),
    ("original-world-campaign", "skeleton.game.generation.original_world_campaign_cli", "main"),
    ("original-world", "skeleton.game.generation.original_world_cli", "main"),
    ("original-world-era", "skeleton.game.generation.original_world_era_cli", "main"),
    ("original-world-frontier", "skeleton.game.generation.original_world_frontier_cli", "main"),
    ("original-world-living", "skeleton.game.generation.original_world_living_10x_cli", "main"),
    ("original-world-million", "skeleton.game.generation.original_world_million_cli", "main"),
    ("original-world-play", "skeleton.game.generation.original_world_play_cli", "main"),
    ("original-world-product", "skeleton.game.generation.original_world_product_cli", "main"),
    ("original-world-tenfold", "skeleton.game.generation.original_world_tenfold_cli", "main"),
    ("local-knowledge-plane", "skeleton.ai.runtime.operational_ai.context.knowledge_plane.cli", "main"),
    ("local-repository-index", "skeleton.ai.runtime.operational_ai.context.knowledge_plane.repository.cli", "main"),
    ("local-model-admission", "skeleton.ai.runtime.operational_ai.model.admission.cli", "main"),
    ("local-gguf-prepare", "skeleton.ai.runtime.operational_ai.model.gguf.prepare_cli", "main"),
    ("local-gguf-probe", "skeleton.ai.runtime.operational_ai.model.gguf.probe_cli", "main"),
    ("local-gguf-endurance", "skeleton.ai.runtime.operational_ai.model.qualification.cli", "main"),
    ("local-native-candidate", "skeleton.ai.runtime.operational_ai.native_candidate.cli", "main"),
    ("local-native-genesis", "skeleton.ai.runtime.operational_ai.native_genesis.cli", "main"),
    ("local-native-qualification", "skeleton.ai.runtime.operational_ai.native_qualification.cli", "main"),
    ("local-native-supervised", "skeleton.ai.runtime.operational_ai.native_supervised.cli", "main"),
    ("local-grounded-turn", "skeleton.ai.runtime.operational_ai.offline_cognition.grounded_cli", "run"),
)


@pytest.mark.parametrize("command,module,attribute", OWNERS)
def test_dispatch_is_transparent(monkeypatch, command, module, attribute):
    owner = ModuleType(module)
    calls = []
    def execute(argv):
        calls.append(tuple(argv))
        return 19
    setattr(owner, attribute, execute)
    monkeypatch.setitem(sys.modules, module, owner)
    argv = ["--owner-only-approval", "--tenant", "local tenant", "--", "literal"]
    assert main([command, *argv]) == 19
    assert calls == [tuple(argv)]


@pytest.mark.parametrize("command,module,attribute", OWNERS)
def test_installed_entrypoint_matches_declared_source(command, module, attribute):
    if not (ROOT / "pyproject.toml").is_file():
        pytest.skip("source checkout metadata unavailable")
    modern = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    legacy = configparser.ConfigParser(interpolation=None)
    legacy.read(ROOT / "setup.cfg", encoding="utf-8")
    legacy_commands = dict(line.strip().split(" = ", 1) for line in
                           legacy["options.entry_points"]["console_scripts"].splitlines()
                           if line.strip())
    entry = "skeleton-" + command
    assert modern["project"]["scripts"][entry] == module + ":" + attribute
    assert legacy_commands[entry] == module + ":" + attribute
    source = ROOT.joinpath(*module.split(".")).with_suffix(".py")
    tree = ast.parse(source.read_text(encoding="utf-8"))
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef)
               and node.name == attribute]
    assert len(matches) == 1
    assert matches[0].args.args[0].arg == "argv"
    assert matches[0].args.defaults


@pytest.mark.parametrize("command,module,attribute", OWNERS)
def test_help_lists_unique_installed_route(command, module, attribute, capsys):
    assert main([]) == 0
    output = capsys.readouterr().out
    assert sum(line.strip().split(maxsplit=1)[0] == command
               for line in output.splitlines() if line.strip()) == 1


@pytest.mark.parametrize("command", [
    "jeeves-native-acceptance", "jeeves-native-eval", "jeeves-native-session",
    "world-reviewed-edit", "world-reviewed-delivery", "world-reviewed-handoff",
    "world-reviewed-session", "original-foundation", "original-world-play",
    "original-world-frontier", "local-gguf-prepare", "local-model-admission",
])
def test_real_help_does_not_request_or_grant_authority(command, capsys):
    with pytest.raises(SystemExit) as error:
        main([command, "--help"])
    assert error.value.code == 0
    assert "usage:" in capsys.readouterr().out.lower()


def test_recovered_routes_do_not_insert_approval_flags(monkeypatch):
    for command, module, attribute in OWNERS:
        owner = ModuleType(module)
        def denied(argv):
            assert argv == []
            return 2
        setattr(owner, attribute, denied)
        monkeypatch.setitem(sys.modules, module, owner)
        assert main([command]) == 2
