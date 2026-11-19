"""Installed route integration for recovered local command owners."""
from __future__ import annotations

import ast
import configparser
import importlib
import sys
import tomllib
from pathlib import Path
from types import ModuleType

import pytest

from skeleton.__main__ import main

ROOT = Path(__file__).resolve().parents[2]
OWNERS = (
    ("game-archive", "skeleton.ai.game_builder.archive_cli"),
    ("studio-dual-runtime", "skeleton.ai.game_builder.dual_runtime_cli"),
    ("studio-dual-runtime-verify", "skeleton.ai.game_builder.dual_runtime_verify_cli"),
    ("studio-game-model", "skeleton.ai.game_builder.game_model_cli"),
    ("studio-game-workspace", "skeleton.ai.game_builder.game_workspace_cli"),
    ("studio-knowledge", "skeleton.ai.game_builder.knowledge_cli"),
    ("studio-living-story", "skeleton.ai.game_builder.living_story_blueprint_cli"),
    ("studio-npc-blueprint", "skeleton.ai.game_builder.npc_blueprint_cli"),
    ("studio-export-batch", "skeleton.ai.game_builder.offline_export_batch_cli"),
    ("studio-export-delta", "skeleton.ai.game_builder.offline_export_batch_delta_cli"),
    ("studio-export-prepare", "skeleton.ai.game_builder.offline_export_batch_prepare_cli"),
    ("studio-receipt-inspect", "skeleton.ai.game_builder.offline_receipt_inspect_cli"),
    ("studio-original-game", "skeleton.ai.game_builder.original_game_studio_cli"),
    ("studio-originality", "skeleton.ai.game_builder.plagiarism_cli"),
    ("studio-playable", "skeleton.ai.game_builder.playable_cli"),
    ("studio-progressive-port", "skeleton.ai.game_builder.progressive_port_cli"),
    ("studio-quest-director", "skeleton.ai.game_builder.quest_director_cli"),
    ("studio-build-qualification", "skeleton.ai.game_builder.studio_build_qualification_cli"),
    ("studio-campaign-assurance", "skeleton.ai.game_builder.studio_campaign_assurance_cli"),
    ("studio-campaign", "skeleton.ai.game_builder.studio_campaign_cli"),
    ("studio-dragon-lessons", "skeleton.ai.game_builder.studio_dragon_lessons_cli"),
    ("studio-execution-campaign", "skeleton.ai.game_builder.studio_execution_campaign_cli"),
    ("studio-system-editor", "skeleton.ai.game_builder.system_editor_cli"),
    ("studio-tiled-map", "skeleton.ai.game_builder.tiled_map_cli"),
    ("harbor-patrol", "skeleton.game.gameplay.harbor_crafting_patrol_cli"),
    ("harbor-salvage", "skeleton.game.gameplay.harbor_crafting_salvage_cli"),
    ("harbor-salvage-map", "skeleton.game.gameplay.harbor_crafting_salvage_map_cli"),
    ("harbor-salvage-choice", "skeleton.game.gameplay.harbor_crafting_salvage_season_choice_cli"),
    ("harbor-salvage-season", "skeleton.game.gameplay.harbor_crafting_salvage_season_cli"),
    ("harbor-salvage-story", "skeleton.game.gameplay.harbor_crafting_salvage_story_cli"),
    ("jeeves-adventure-game", "skeleton.jeeves.adventure_game_cli"),
    ("jeeves-full-game", "skeleton.jeeves.full_game_creation_cli"),
    ("jeeves-game-building", "skeleton.jeeves.game_building_cli"),
    ("game-learning", "skeleton.jeeves.game_learning_cli"),
    ("jeeves-studio-multifactor", "skeleton.jeeves.game_studio_multifactor_cli"),
    ("jeeves-studio-policy", "skeleton.jeeves.game_studio_policy_cli"),
    ("jeeves-studio-rule-training", "skeleton.jeeves.game_studio_rule_training_cli"),
    ("jeeves-studio-shadow", "skeleton.jeeves.game_studio_shadow_cli"),
    ("jeeves-console-capability", "skeleton.jeeves.local_model_console_capability_cli"),
    ("long-context", "skeleton.ai.model_runtime.long_context_cli"),
)


@pytest.mark.parametrize("command,module", OWNERS)
def test_root_dispatch_preserves_exact_arguments_and_status(monkeypatch, command, module):
    owner = ModuleType(module)
    received = []
    def execute(argv):
        received.append(argv)
        return 37
    owner.main = execute
    monkeypatch.setitem(sys.modules, module, owner)
    arguments = ["--opaque-owner-option", "value with spaces", "--", "literal"]
    assert main([command, *arguments]) == 37
    assert received == [arguments]


@pytest.mark.parametrize("command,module", OWNERS)
def test_console_metadata_binds_the_same_real_owner(command, module):
    if not (ROOT / "pyproject.toml").is_file():
        pytest.skip("source checkout metadata unavailable")
    modern = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    legacy = configparser.ConfigParser(interpolation=None)
    legacy.read(ROOT / "setup.cfg", encoding="utf-8")
    legacy_entries = dict(
        line.strip().split(" = ", 1)
        for line in legacy["options.entry_points"]["console_scripts"].splitlines()
        if line.strip()
    )
    script = "skeleton-" + command
    assert modern["project"]["scripts"][script] == module + ":main"
    assert legacy_entries[script] == module + ":main"
    owner = ROOT.joinpath(*module.split(".")).with_suffix(".py")
    syntax = ast.parse(owner.read_text(encoding="utf-8"))
    assert any(isinstance(node, ast.FunctionDef) and node.name == "main"
               and node.args.args and node.args.args[0].arg == "argv"
               for node in syntax.body)


@pytest.mark.parametrize("command,module", OWNERS)
def test_root_help_lists_each_recovered_command(command, module, capsys):
    assert main([]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert sum(line.strip().split(maxsplit=1)[0] == command
               for line in lines if line.strip()) == 1


@pytest.mark.parametrize("command", [
    "studio-dual-runtime-verify", "studio-export-batch", "studio-export-delta",
    "studio-export-prepare", "studio-receipt-inspect", "studio-original-game",
    "studio-system-editor", "studio-tiled-map", "long-context",
    "harbor-patrol", "harbor-salvage", "harbor-salvage-map",
])
def test_real_offline_owner_help_is_reachable(command, capsys):
    with pytest.raises(SystemExit) as error:
        main([command, "--help"])
    assert error.value.code == 0
    assert "usage:" in capsys.readouterr().out.lower()
