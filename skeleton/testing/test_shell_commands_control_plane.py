from pathlib import Path
import sys

from skeleton.shells.arguments import ArgumentPolicy
from skeleton.shells.capabilities import CapabilityGrant, ShellCapability
from skeleton.shells.commands import CommandCatalog, CommandDefinition
from skeleton.shells.control_plane import ShellControlPlane
from skeleton.shells.environment import EnvironmentPolicy
from skeleton.shells.registry import ExecutableSpec
from skeleton.shells.runner import ShellCommand, ShellPolicy


def build(tmp_path):
    path = str(Path(sys.executable).resolve())
    spec = ExecutableSpec("python", path, tags=frozenset({"runtime", "safe"}))
    definition = CommandDefinition(
        spec,
        ArgumentPolicy.allow_any(max_total_args=4),
        environment=EnvironmentPolicy.empty(),
        description="bounded Python runtime",
    )
    catalog = CommandCatalog([definition])
    policy = ShellPolicy(executables={"python": path}, cwd_roots=(tmp_path,))
    return ShellControlPlane(policy=policy, catalog=catalog), catalog, policy


def test_command_definition_always_requires_execute(tmp_path):
    _, catalog, _ = build(tmp_path)
    assert ShellCapability.EXECUTE in catalog.get("python").required_capabilities


def test_command_catalog_by_tag_and_to_dict(tmp_path):
    _, catalog, _ = build(tmp_path)
    assert catalog.by_tag("runtime")[0].name == "python"
    payload = catalog.to_dict()["python"]
    assert payload["description"] == "bounded Python runtime"
    assert payload["environment_keys"] == []


def test_control_plane_inspect_allows_valid_command(tmp_path):
    plane, _, _ = build(tmp_path)
    decision = plane.inspect(ShellCommand("python", ("a",), cwd=tmp_path), CapabilityGrant.execution_only())
    assert decision.allowed


def test_control_plane_inspect_denies_unknown_command(tmp_path):
    plane, _, _ = build(tmp_path)
    decision = plane.inspect(ShellCommand("shell", cwd=tmp_path), CapabilityGrant.execution_only())
    assert not decision.allowed


def test_control_plane_rate_limit_applies_after_admission(tmp_path):
    plane, _, _ = build(tmp_path)
    command = ShellCommand("python", cwd=tmp_path)
    grant = CapabilityGrant.execution_only()
    for _ in range(10):
        assert plane.admit_with_rate_limit(command, grant, rate_key="worker").allowed
    denied = plane.admit_with_rate_limit(command, grant, rate_key="worker")
    assert not denied.allowed
    assert denied.reason == "rate limit exceeded"


def test_control_plane_preflight_multiple_items(tmp_path):
    plane, _, _ = build(tmp_path)
    report = plane.preflight_commands(
        [("a", ShellCommand("python", cwd=tmp_path)), ("b", ShellCommand("bad", cwd=tmp_path))],
        CapabilityGrant.execution_only(),
    )
    assert not report.allowed
    assert len(report.items) == 2


def test_control_plane_explain_registered_command(tmp_path):
    plane, _, _ = build(tmp_path)
    payload = plane.explain("python", CapabilityGrant.execution_only())
    assert payload["registered"] is True
    assert payload["executable_authorized"] is True
    assert payload["required_capabilities"] == ["execute"]


def test_control_plane_explain_unknown_command(tmp_path):
    plane, _, _ = build(tmp_path)
    payload = plane.explain("missing", CapabilityGrant.execution_only())
    assert payload["registered"] is False
    assert "no registered definition" in payload["description"]
