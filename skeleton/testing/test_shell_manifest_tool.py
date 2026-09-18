from pathlib import Path
import json
import sys
import pytest

from skeleton.shells.capabilities import CapabilityGrant, ShellCapability
from skeleton.shells.executor import ShellExecutor
from skeleton.shells.manifest import MANIFEST_SCHEMA_VERSION, ManifestError, ManifestLimits, manifest_dict, parse_manifest
from skeleton.shells.redaction import SecretRedactor
from skeleton.shells.runner import ShellPolicy, ShellResult
from skeleton.shells.tool_adapter import ShellToolAdapter, ToolExecutionRequest


class ToolRunner:
    def __init__(self, tmp_path, stdout=b"ok", stderr=b""):
        self.policy = ShellPolicy(executables={"python": str(Path(sys.executable).resolve())}, cwd_roots=(tmp_path,))
        self.stdout = stdout
        self.stderr = stderr

    def run(self, command):
        return ShellResult(command.command, 0, self.stdout, self.stderr, accepted=True)


def manifest(**changes):
    payload = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "name": "build",
        "steps": [
            {
                "id": "compile",
                "command": "python",
                "args": ["-m", "compileall", "."],
                "depends_on": [],
                "allowed_returncodes": [0],
            }
        ],
    }
    payload.update(changes)
    return json.dumps(payload)


def test_manifest_parses_registered_style_logical_commands():
    spec = parse_manifest(manifest())
    assert spec.name == "build"
    assert spec.steps[0].command.command == "python"
    assert spec.steps[0].command.args == ("-m", "compileall", ".")


def test_manifest_rejects_wrong_schema_version():
    with pytest.raises(ManifestError):
        parse_manifest(manifest(schema_version=99))


def test_manifest_rejects_executable_path_field():
    raw = json.loads(manifest())
    raw["steps"][0]["executable"] = "/bin/sh"
    with pytest.raises(ManifestError):
        parse_manifest(json.dumps(raw))


def test_manifest_rejects_unknown_fields():
    raw = json.loads(manifest())
    raw["steps"][0]["shell"] = True
    with pytest.raises(ManifestError):
        parse_manifest(json.dumps(raw))


def test_manifest_bounds_step_count():
    raw = json.loads(manifest())
    raw["steps"] = raw["steps"] * 2
    raw["steps"][1]["id"] = "other"
    with pytest.raises(ManifestError):
        parse_manifest(json.dumps(raw), limits=ManifestLimits(max_steps=1))


def test_manifest_rejects_nul_argument():
    raw = json.loads(manifest())
    raw["steps"][0]["args"] = ["bad\x00arg"]
    with pytest.raises(ManifestError):
        parse_manifest(json.dumps(raw))


def test_manifest_rejects_duplicate_or_cyclic_steps_through_pipeline_validation():
    raw = json.loads(manifest())
    raw["steps"] = [
        {"id": "a", "command": "python", "depends_on": ["b"]},
        {"id": "b", "command": "python", "depends_on": ["a"]},
    ]
    with pytest.raises(ValueError):
        parse_manifest(json.dumps(raw))


def test_manifest_round_trip_dict_preserves_contract():
    spec = parse_manifest(manifest())
    restored = parse_manifest(json.dumps(manifest_dict(spec)))
    assert restored.steps[0].step_id == "compile"
    assert restored.steps[0].command.args == spec.steps[0].command.args


def test_manifest_retry_contract_is_parsed():
    raw = json.loads(manifest())
    raw["steps"][0]["retry"] = {"max_attempts": 3, "retry_returncodes": [75]}
    spec = parse_manifest(json.dumps(raw))
    assert spec.steps[0].retry.max_attempts == 3
    assert spec.steps[0].retry.retry_returncodes == frozenset({75})


def test_tool_adapter_default_response_omits_output(tmp_path):
    executor = ShellExecutor(ToolRunner(tmp_path))
    response = ShellToolAdapter(executor).execute(ToolExecutionRequest("python", cwd=str(tmp_path)))
    payload = response.to_dict()
    assert payload["ok"] is True
    assert "output" not in payload


def test_tool_adapter_bounded_output_is_redacted(tmp_path):
    runner = ToolRunner(tmp_path, stdout=b"Bearer very-secret-token")
    executor = ShellExecutor(runner)
    response = ShellToolAdapter(executor).execute(
        ToolExecutionRequest("python", cwd=str(tmp_path), include_output=True, max_output_chars=12)
    )
    assert response.output is not None
    rendered = response.output["stdout"]["text"]
    assert "very-secret-token" not in rendered


def test_tool_request_bounds_output_size_setting():
    with pytest.raises(ValueError):
        ToolExecutionRequest("python", include_output=True, max_output_chars=1_000_000)


def test_tool_adapter_env_requires_capability(tmp_path):
    executor = ShellExecutor(ToolRunner(tmp_path))
    with pytest.raises(Exception):
        ShellToolAdapter(executor).execute(ToolExecutionRequest("python", cwd=str(tmp_path), env={"MODE": "x"}))
