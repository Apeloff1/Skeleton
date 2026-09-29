"""Regression coverage for TREE-017 Frontier progression extraction."""

from __future__ import annotations

import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontier_legacy_progression_modules_reexport_canonical_symbols() -> None:
    checks = (
        ("achievements", "AchievementSpec"),
        ("quests", "QuestSpec"),
        ("reputation", "ReputationLevel"),
        ("season_pass", "SeasonPassSpec"),
        ("tournament", "TournamentSpec"),
        ("vip", "VIPState"),
        ("guild", "GuildState"),
    )
    for module_name, symbol in checks:
        legacy = importlib.import_module(f"skeleton.frontier.{module_name}")
        canonical = importlib.import_module(
            f"skeleton.frontier.progression.{module_name}"
        )
        assert getattr(legacy, symbol) is getattr(canonical, symbol)


def test_frontier_public_package_exports_canonical_progression_symbols() -> None:
    frontier = importlib.import_module("skeleton.frontier")
    achievements = importlib.import_module(
        "skeleton.frontier.progression.achievements"
    )
    quests = importlib.import_module("skeleton.frontier.progression.quests")
    reputation = importlib.import_module(
        "skeleton.frontier.progression.reputation"
    )

    assert frontier.AchievementSpec is achievements.AchievementSpec
    assert frontier.QuestSpec is quests.QuestSpec
    assert frontier.ReputationLevel is reputation.ReputationLevel


def test_canonical_progression_modules_do_not_import_flat_predecessors() -> None:
    progression_root = ROOT / "skeleton/frontier/progression"
    module_names = (
        "achievement_adapters",
        "achievements",
        "encyclopedia",
        "guild",
        "logbook",
        "lucky_wheel",
        "quests",
        "reputation",
        "season_pass",
        "tournament",
        "vip",
        "vip_daily",
    )

    for path in progression_root.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for module_name in module_names:
            assert f"skeleton.frontier.{module_name}" not in source, (
                path,
                module_name,
            )


def test_biotope_achievement_adapter_targets_canonical_progression() -> None:
    source = (
        ROOT / "skeleton/frontier/ecology/biotope_achievement_adapters.py"
    ).read_text(encoding="utf-8")

    assert "skeleton.frontier.progression.achievements" in source
    assert "skeleton.frontier.achievements" not in source
