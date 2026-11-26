"""Regressions for the real defects surfaced by the repo-wide Ruff correctness floor.

Each test exercises a code path that previously raised NameError/SyntaxError or
silently dropped a value (duplicate dict keys, always-true asserts).
"""
from __future__ import annotations

import importlib
import math
try:
    import tomllib
except ImportError:
    import tomli as tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_root_ruff_floor_keeps_every_correctness_family() -> None:
    config = tomllib.loads((ROOT / "ruff.toml").read_text(encoding="utf-8"))
    selected = set(config["lint"]["select"])
    assert {"E9", "F63", "F7", "F82", "F50", "F52", "F60", "F62", "F70", "PLE"} <= selected
    # Only the stdlib-logging arity checks are excluded (non-stdlib loggers).
    assert set(config["lint"].get("ignore", [])) <= {"PLE1205", "PLE1206"}
    # backend keeps its own floor; the root file must not replace it.
    assert (ROOT / "backend" / "ruff.toml").is_file()


def test_studio_native_replay_telemetry_imports_regex_module() -> None:
    module = importlib.import_module("skeleton.ai.game_builder.studio_native_replay_telemetry")
    assert module._LINE.pattern


def test_trace_context_child_links_to_parent_span() -> None:
    from skeleton.kernel.trace import TraceContext

    root = TraceContext.root()
    child = root.child()
    assert type(child) is TraceContext
    assert child.trace_id == root.trace_id
    assert child.parent_span_id == root.span_id
    assert child.span_id != root.span_id


def test_decade_profile_enforces_decade_boundary() -> None:
    from skeleton.ai.training.temporal_intelligence import DecadeProfile, TemporalSignalError

    fields = dict(subject="s", signal_count=1, source_count=1, primary_count=1,
                  support_ppm=1, oppose_ppm=0, neutral_ppm=0, diversity_ppm=0, corroboration_ppm=0)
    assert DecadeProfile(decade=1990, **fields).decade == 1990
    with pytest.raises(TemporalSignalError):
        DecadeProfile(decade=1995, **fields)


def test_multilanguage_gate_raises_contract_violation() -> None:
    from skeleton.ai.runtime.operational_ai.authority.canonical import ContractViolation
    from skeleton.ai.runtime.operational_ai.laptop_runtime.desktop_source_qualification import (
        MultiLanguageGate,
    )

    gate = MultiLanguageGate()
    assert gate.qualify_sql(b"select 1;", "q.sql")["status"] == "read-only-admitted"
    with pytest.raises(ContractViolation):
        gate.qualify_sql(b"DROP TABLE users;", "q.sql")
    with pytest.raises(ContractViolation):
        gate.qualify_yaml(b"!!python/object x\n", "a.yaml")
    with pytest.raises(ContractViolation):
        gate.qualify_html(b"<script>x</script>", "a.html")


def test_builder_plane_lazy_repair_exports_resolve() -> None:
    plane = importlib.import_module("skeleton.automation.builder_plane")
    receipts = importlib.import_module("skeleton.automation.builder_repair_receipts")
    for name in ("BuilderRepairReceipt", "compile_builder_repair_receipt", "validate_builder_repair_receipt"):
        assert name in plane.__all__
        assert getattr(plane, name) is getattr(receipts, name)


def test_string_only_all_exports() -> None:
    skeleton = importlib.import_module("skeleton")
    assert {"__version__", "Ranker", "TestScaffold"} <= set(skeleton.__all__)
    ops = importlib.import_module("skeleton.ubuntu.operations")
    assert all(isinstance(name, str) for name in ops.__all__)
    assert set(ops._DOMAIN_EXPORTS) <= set(ops.__all__)
    assert set(ops._COMPAT_CONTRACT_NAMES) <= set(ops.__all__)


def test_duplicate_lazy_keys_keep_effective_owner() -> None:
    training = importlib.import_module("skeleton.ai.training")
    assert training.ShadowWeightError.__module__.endswith(".shadow_weights")
    assert training.SourceAttestation.__module__.endswith(".shadow_weights")
    builder = importlib.import_module("skeleton.ai.game_builder")
    assert builder.TrustedReviewer.__module__.endswith(".consumer_release_assurance")


def test_memory_game_surprise_floor_matches_normaliser() -> None:
    from skeleton.jeeves.agent import memory_game

    assert math.isclose(-math.log(memory_game._EPS), 27.631021115928547)


def test_parallel_latent_thoughts_engine_is_importable_module() -> None:
    legacy = importlib.import_module("skeleton.ai.research.legacy.gameforge.reasoning.parallel_latent_thoughts_engine")
    assert legacy.PARALLEL_LATENT_THOUGHTS_ENGINE
    source = (ROOT / "backend/gameforge/reasoning/parallel_latent_thoughts_engine.py").read_bytes()
    assert source == (ROOT / "skeleton/ai/research/legacy/gameforge/reasoning/parallel_latent_thoughts_engine.py").read_bytes()
