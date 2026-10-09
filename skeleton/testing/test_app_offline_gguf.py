"""Offline GGUF desktop and CLI integration, without provider or Docker dependencies."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import struct

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.local_ai import OfflineAIError, OfflineGGUFSession


_RUNTIME = r'''#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
import sys

for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "HTTPS_PROXY", "ALL_PROXY"):
    if os.environ.get(key):
        raise SystemExit("provider environment leaked: " + key)

parser = argparse.ArgumentParser(add_help=False)
parser.add_argument("-f")
parser.add_argument("-m")
parser.add_argument("-n")
args, _ = parser.parse_known_args()
if not args.f or not args.m:
    raise SystemExit("missing local model or prompt file")
text = Path(args.f).read_text(encoding="utf-8")
if "REJECT_REQUEST" in text:
    raise SystemExit(17)
print("offline GGUF desktop answer")
'''


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def local_deployment(tmp_path: Path) -> tuple[Path, Path, Path]:
    if os.name == "nt":
        pytest.skip("executable shebang fixture is POSIX-only")
    executable = tmp_path / "llama-cli"
    executable.write_text(_RUNTIME, encoding="utf-8")
    executable.chmod(0o755)
    weights = tmp_path / "model.gguf"
    weights.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 1, 0) + b"fixture-weights")
    manifest = tmp_path / "deployment.json"
    manifest.write_text(json.dumps({
        "schema_version": "skeleton.local_model.deployment.v1",
        "runtime_kind": "llama.cpp-cli",
        "model_id": "offline-demo",
        "executable_path": "llama-cli",
        "executable_sha256": _sha(executable),
        "model_path": "model.gguf",
        "model_sha256": _sha(weights),
        "config": {
            "timeout_seconds": 5.0,
            "max_output_bytes": 16384,
            "max_stderr_bytes": 8192,
            "context_size": 2048,
        },
    }, sort_keys=True), encoding="utf-8")
    return manifest, executable, weights


@pytest.mark.asyncio
async def test_desktop_gguf_two_turns_are_local_and_receipted(
    local_deployment: tuple[Path, Path, Path], monkeypatch
) -> None:
    manifest, _, weights = local_deployment
    monkeypatch.setenv("OPENAI_API_KEY", "never-forward-this")
    monkeypatch.setenv("HTTPS_PROXY", "http://not-a-provider.invalid")
    session = OfflineGGUFSession(manifest)
    first = await session.ask("Hello", max_output_tokens=8)
    second = await session.ask("Follow up", max_output_tokens=8)
    assert first.text == "offline GGUF desktop answer"
    assert second.text == first.text
    assert first.model_digest == _sha(weights)
    assert len(first.execution_receipt_digest) == 64
    assert len(session.history) == 4
    session.clear()
    assert session.history == ()


@pytest.mark.asyncio
async def test_failed_inference_does_not_commit_history(
    local_deployment: tuple[Path, Path, Path]
) -> None:
    session = OfflineGGUFSession(local_deployment[0])
    await session.ask("Initial", max_output_tokens=8)
    before = session.history
    with pytest.raises(Exception):
        await session.ask("REJECT_REQUEST", max_output_tokens=8)
    assert session.history == before


def test_gguf_deployment_rejects_tampered_model(
    local_deployment: tuple[Path, Path, Path]
) -> None:
    manifest, _, weights = local_deployment
    weights.write_bytes(weights.read_bytes() + b"tampered")
    with pytest.raises(RuntimeError, match="digest mismatch"):
        OfflineGGUFSession(manifest)


@pytest.mark.asyncio
async def test_artifacts_rechecked_before_every_inference(
    local_deployment: tuple[Path, Path, Path]
) -> None:
    manifest, executable, _ = local_deployment
    session = OfflineGGUFSession(manifest)
    executable.write_text(_RUNTIME + "\n# mutation\n", encoding="utf-8")
    with pytest.raises(Exception, match="artifact"):
        await session.ask("Hello", max_output_tokens=8)
    assert session.history == ()


def test_request_is_bounded_before_dispatch(
    local_deployment: tuple[Path, Path, Path]
) -> None:
    session = OfflineGGUFSession(local_deployment[0])
    with pytest.raises(OfflineAIError, match="4096"):
        session._request("x" * 4097, 8)
    with pytest.raises(OfflineAIError, match="budget"):
        session._request("valid", 2048)
    with pytest.raises(OfflineAIError, match="budget"):
        session._request("valid", True)
    assert session.history == ()


def test_headless_cli_runs_gguf_and_reports_bound_receipt(
    local_deployment: tuple[Path, Path, Path], capsys
) -> None:
    manifest, _, _ = local_deployment
    assert run_app_cli([
        "local-ai", "--deployment", str(manifest), "--prompt", "Hello",
        "--max-output-tokens", "8", "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["text"] == "offline GGUF desktop answer"
    assert len(payload["execution_receipt_digest"]) == 64


def test_cli_refuses_ambiguous_or_missing_model_selection(
    local_deployment: tuple[Path, Path, Path], capsys
) -> None:
    manifest, _, _ = local_deployment
    assert run_app_cli(["local-ai", "--model", "native.json",
                        "--deployment", str(manifest), "--prompt", "hi"]) == 2
    assert run_app_cli(["local-ai", "--deployment", str(manifest)]) == 2
    assert run_app_cli(["local-ai", "--prompt", "hi"]) == 2
    assert "exactly one" in capsys.readouterr().out
