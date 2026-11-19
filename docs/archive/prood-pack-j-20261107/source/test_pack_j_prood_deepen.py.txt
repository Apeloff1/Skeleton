"""Smoke tests for Pack J Prood deepen ports."""
from __future__ import annotations

import importlib

import pytest

import skeleton.prood  # noqa: F401  — installs core.* shim

PACK_J = [
    "agent_mesh",
    "asset_forge",
    "autonomous_orchestrator",
    "build_vault",
    "collection_agents",
    "discourse_engine",
    "full_roster",
    "game_knowledge_vault",
    "lazy_registry",
    "playable_game",
    "provenance_ledger",
    "refine_gates",
    "runtime_health",
    "stage_builder",
    "stage_vault",
    "systems_forge",
    "systems_forge_ext",
    "text_gamefile",
    "tool_forge",
    "tunnel_watchdog",
    "unbulk",
    "universal_forge",
    "whisper_network",
]


@pytest.mark.parametrize("mod", PACK_J)
def test_pack_j_module_importable(mod):
    m = importlib.import_module(f"skeleton.prood.{mod}")
    pub = [n for n in dir(m) if not n.startswith("_")]
    assert pub, f"{mod} exported nothing"


def test_pack_j_covers_mass_build_surface():
    assert len(PACK_J) >= 20
