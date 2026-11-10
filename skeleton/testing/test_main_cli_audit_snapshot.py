"""Regression coverage for the import-free main CLI help/dispatch audit."""

from __future__ import annotations

import json

import pytest

from skeleton.__main__ import main
from skeleton.application import (
    CAPABILITY_MANIFEST_VERSION,
    MAIN_CLI_AUDIT_KIND,
    capability_manifest,
    get_main_cli_audit_row,
    main_cli_audit_snapshot,
)


_ROW_KEYS = {"command", "in_help", "in_dispatch", "runtime_present"}
_COMMANDS = [
    "app",
    "ready",
    "product",
    "health",
    "next",
    "wiki",
    "seed",
    "caps",
    "lattice",
    "pulse",
    "orch",
    "season",
    "scoreboard",
    "hot",
    "coverage",
    "decade",
    "bank",
    "switch",
    "witness",
    "gov",
    "cage",
    "rot",
    "fieldcov",
    "enact",
    "day",
    "week",
    "calendar",
    "conductor",
    "ctx",
    "live",
    "observe",
    "stacks",
    "mix",
    "satellites",
    "path",
    "bound",
    "fieldwalk",
    "dump",
    "orgwalk",
    "sleep",
    "forget",
    "helix",
    "recall",
    "run",
    "scene-author",
    "scene-circuit",
    "scene-circuit-solve",
    "scene-circuit-author",
    "scene-circuit-accept",
    "scene-patrol-solve",
    "scene-patrol-author",
    "scene-patrol",
    "scene-accept",
    "scene-travel",
    "scene-survival-campaign",
    "scene-survival-campaign-author",
    "scene-survival-campaign-route",
    "scene-survival-campaign-play",
    "scene-survival-campaign-accept",
    "scene-survival-play",
    "scene-survival-author",
    "scene-survival-route",
    "scene-survival",
    "scene-weather",
    "scene-weather-author",
    "scene-weather-play",
    "scene-weather-board",
    "scene-weather-route",
    "scene-weather-accept",
    "scene-market-fork-play",
    "scene-market-fork-author",
    "scene-market-fork-accept",
    "scene-market-fork",
    "scene-market-hours",
    "scene-market-hours-play",
    "scene-market-hours-accept",
    "scene-market-contract-play",
    "scene-market-contract-accept",
    "scene-market-contract",
    "scene-market-contract-author",
    "scene-market-contract-route",
    "scene-market-route-accept",
    "scene-market-route",
    "scene-market-board",
    "scene-market-accept",
    "scene-market-play",
    "scene-market-author",
    "scene-evacuation",
    "scene-evacuation-board",
    "scene-evacuation-author",
    "scene-evacuation-accept",
    "scene-evacuation-solve",
    "scene-evacuation-play",
    "scene-market-party",
    "scene-market-party-author",
    "scene-market-party-play",
    "scene-market-party-board",
    "scene-market-party-route",
    "scene-market-party-accept",
    "scene-market-party-timeline",
    "scene-market-party-league",
    "scene-market-party-league-author",
    "scene-market-party-compare",
    "scene-market-party-portfolio",
    "scene-market-party-handoff",
    "scene-market-party-balance",
    "scene-market-party-vault",
    "scene-market-party-vault-history",
    "scene-market",
    "scene-tiles",
    "scene-push",
    "scene-push-play",
    "scene-push-accept",
    "scene-tiles-route",
    "scene-achievements",
    "scene-npc",
    "scene-npc-solve",
    "scene-npc-play",
    "scene-atlas",
    "scene-consequences",
    "scene-mission",
    "scene-mission-play",
    "scene-mission-board",
    "scene-mission-author",
    "scene-mission-route",
    "scene-mission-assist",
    "scene-mission-liveness",
    "scene-mission-accept",
    "scene-mission-timeline",
    "scene-mission-league",
    "scene-mission-league-author",
    "scene-escort",
    "scene-escort-author",
    "scene-escort-solve",
    "scene-escort-play",
    "game",
    "forge",
    "test",
    "dev",
    "eras",
    "generations",
    "plan",
    "cockpit",
    "walk",
    "doctor",
    "creator",
    "contracts",
    "capabilities",
    "combat",
    "combat-contract",
    "combat-contract-author",
    "combat-contract-play",
    "combat-contract-solve",
    "combat-delivery-accept",
    "combat-contract-package",
    "arena-terrain",
    "combat-arena",
    "quest-factions-accept",
    "quest-factions-play",
    "quest-factions-author",
    "quest-factions-route",
    "quest-factions",
    "quest-author",
    "quest-expedition",
    "quest-expedition-play",
    "quest-inventory",
    "quest-decisions",
    "quest-checkpoints",
    "quest-expedition-route",
    "quest-campaign-play",
    "quest-campaign-route",
    "quest-campaign-accept",
    "game-vertical-accept",
    "quest-campaign",
    "quest-campaign-author",
    "arena-forge-author",
    "arena-forge-solve",
    "arena-forge",
    "combat-checkpoints",
    "combat-expedition-playbook",
    "combat-expedition-audit",
    "combat-expedition-solve",
    "combat-expedition",
    "tournament-author",
    "combat-league-author",
    "combat-career-roadmap",
    "combat-career-advice",
    "combat-career-author",
    "combat-career",
    "combat-league",
    "combat-tournament",
    "combat-campaign-timeline",
    "combat-campaign-player",
    "combat-campaign",
    "combat-balance",
    "combat-drill-solve",
    "combat-stamina",
    "combat-drill",
    "combat-inspect",
    "campaign",
    "world-laptop",
    "world-canon",
    "world-assets",
    "world-timeline",
    "world-bundle",
    "world-plan",
    "world-editor",
    "world-route",
    "world-cast",
    "world-experience",
    "world-revision",
    "world-assurance",
    "world-invariants",
    "world-scenario",
    "world-choice-impact",
    "world-playtest",
    "world-migrate",
    "world-field-journal",
    "world-weather",
    "world-advisories",
    "world-epilogues",
    "world-fork",
    "world-session",
    "world-quest",
    "world-counterfactual",
    "world-lore",
    "world-factions",
    "world-evidence",
    "world-integrated",
    "world-context",
    "world-promises",
    "world-knowledge",
    "world-studio-engine",
    "world-studio",
    "world-director",
    "world-chapters",
    "world-cinematics",
    "world-pacing",
    "world-accessibility",
    "world-localization",
    "world-rumors",
    "world-testimony",
    "world-relationships",
    "world-events",
    "world-puzzles",
    "world-inventory",
    "world-npc-schedule",
    "world-portals",
    "world-atlas",
    "world-dialogue-locales",
    "world-dialogue-transcript",
    "world-interaction",
    "world-dialogue",
    "world-character-arcs",
    "world-economy",
    "world-tools",
    "quest",
    "invoke",
    "command",
    "status",
    "config",
    "help",
]


def test_main_cli_audit_is_import_free(monkeypatch) -> None:
    called = False

    def should_not_import(_module_name: str):
        nonlocal called
        called = True
        raise AssertionError("main CLI audit must not import genesis")

    monkeypatch.setattr(
        "skeleton.application.capability_runtime.import_module",
        should_not_import,
    )
    payload = main_cli_audit_snapshot()
    assert called is False
    assert payload["schema_version"] == CAPABILITY_MANIFEST_VERSION == 1
    assert payload["kind"] == MAIN_CLI_AUDIT_KIND == "main_cli_audit"


def test_main_cli_audit_locks_help_dispatch_parity_and_help_aliases() -> None:
    payload = main_cli_audit_snapshot()
    assert [row["command"] for row in payload["commands"]] == _COMMANDS
    assert payload["aliases"] == ["-h", "--help"]
    assert payload["missing_from_help"] == []
    assert payload["missing_from_dispatch"] == []
    for row in payload["commands"]:
        assert set(row) == _ROW_KEYS
        assert row["in_help"] is True
        assert row["in_dispatch"] is True
        assert row["runtime_present"] is True


def test_capabilities_cli_main_cli_audit_matches_python_api(capsys) -> None:
    assert main(["capabilities", "--main-cli-audit"]) == 0
    assert json.loads(capsys.readouterr().out) == main_cli_audit_snapshot()


def test_http_main_cli_audit_matches_cli_payload() -> None:
    import asyncio

    from fastapi import HTTPException

    from skeleton.api import routes

    snapshot = main_cli_audit_snapshot()
    assert asyncio.run(routes.application_main_cli_audit()) == snapshot
    row = asyncio.run(routes.application_main_cli_audit_row(" Capabilities "))
    assert row == get_main_cli_audit_row("capabilities")
    with pytest.raises(HTTPException) as missing:
        asyncio.run(routes.application_main_cli_audit_row("missing"))
    assert missing.value.status_code == 404


def test_shared_command_main_cli_audit_matches_snapshot_and_stays_fail_closed() -> None:
    from skeleton.application import build_runtime_command_service

    class _State:
        genesis = None

        def is_healthy(self):
            return {"overall": True}

    service = build_runtime_command_service(_State())
    identity = service.execute("capabilities")
    assert identity.ok is True
    assert identity.to_payload()["data"] == capability_manifest()

    audit = service.execute("capabilities", {"main_cli_audit": True})
    assert audit.ok is True
    assert audit.to_payload()["data"] == main_cli_audit_snapshot()

    invalid = service.execute("capabilities", {"main_cli_audit": 1})
    assert invalid.ok is False
    both = service.execute("capabilities", {"main_cli_audit": True, "cli_audit": True})
    assert both.ok is False
