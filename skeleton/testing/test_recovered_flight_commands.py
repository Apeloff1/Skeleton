"""Installed recovery of explicit local flight, boot and research owners."""
from __future__ import annotations

import ast
import configparser
from pathlib import Path
import sys
import tomllib
from types import ModuleType

import pytest

from skeleton.__main__ import main

ROOT = Path(__file__).resolve().parents[2]
OWNERS = (
    ("local-ai-boot", "skeleton.ai.runtime.operational_ai.deployment.boot.cli", "main"),
    ("local-ai-bootstrap", "skeleton.ai.runtime.operational_ai.deployment.bootstrap.cli", "main"),
    ("local-durable-worker", "skeleton.ai.runtime.operational_ai.durable_jobs.worker_cli", "main"),
    ("local-flight-events", "skeleton.ai.runtime.operational_ai.transport.flight.event_stream.cli", "main"),
    ("local-flight-outbox", "skeleton.ai.runtime.operational_ai.transport.flight.outbox_delivery.cli", "main"),
    ("local-flight-control", "skeleton.ai.runtime.operational_ai.orchestration.flight_control.cli", "main"),
    ("local-flight-metrics", "skeleton.ai.runtime.operational_ai.orchestration.flight_control.daemon.operator_cli", "main"),
    ("local-laptop-client", "skeleton.ai.runtime.operational_ai.laptop_runtime.client_cli", "main"),
    ("local-laptop-runtime", "skeleton.ai.runtime.operational_ai.laptop_runtime.cli", "main"),
    ("dragon-research-game", "skeleton.ai.webcrawler.game_builder_cli", "run"),
    ("era-source-validate", "skeleton.ai.simulation.era.scripting.cli", "main"),
)


@pytest.mark.parametrize("command,module,attribute", OWNERS)
def test_explicit_invocation_only(monkeypatch, command, module, attribute):
    calls = []
    owner = ModuleType(module)
    def action(argv):
        calls.append(tuple(argv))
        return 23
    setattr(owner, attribute, action)
    monkeypatch.setitem(sys.modules, module, owner)
    argv = ["--explicit-owner-option", "literal"]
    assert main([command, *argv]) == 23
    assert calls == [tuple(argv)]


@pytest.mark.parametrize("command,module,attribute", OWNERS)
def test_package_metadata_and_owner(command, module, attribute):
    if not (ROOT / "pyproject.toml").is_file():
        pytest.skip("source checkout metadata unavailable")
    py = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    cfg = configparser.ConfigParser(interpolation=None)
    cfg.read(ROOT / "setup.cfg", encoding="utf-8")
    legacy = dict(line.strip().split(" = ", 1) for line in
                  cfg["options.entry_points"]["console_scripts"].splitlines() if line.strip())
    entry = "skeleton-" + command
    assert py["project"]["scripts"][entry] == legacy[entry] == module + ":" + attribute
    syntax = ast.parse(ROOT.joinpath(*module.split(".")).with_suffix(".py").read_bytes())
    owner = [node for node in syntax.body if isinstance(node, ast.FunctionDef)
             and node.name == attribute]
    assert len(owner) == 1
    assert owner[0].args.args[0].arg in {"args", "argv"}
    assert owner[0].args.defaults


@pytest.mark.parametrize("command", ["local-ai-boot", "local-flight-events",
    "local-flight-metrics", "local-flight-outbox", "era-source-validate"])
def test_actual_help_is_nonexecuting(command, capsys):
    with pytest.raises(SystemExit) as exc:
        main([command, "--help"])
    assert exc.value.code == 0
    assert "usage:" in capsys.readouterr().out.lower()
