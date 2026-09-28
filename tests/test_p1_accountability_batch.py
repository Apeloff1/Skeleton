from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "p1_accountability_batch.py"


def _module():
    spec = importlib.util.spec_from_file_location(
        "p1_accountability_batch_under_test",
        MODULE_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_normalize_record_ids_accepts_only_unique_p1_records() -> None:
    module = _module()

    assert module.normalize_record_ids(
        ("ACC-P1-EVID-01", "ACC-P1-INTEL-01")
    ) == ("ACC-P1-EVID-01", "ACC-P1-INTEL-01")

    with pytest.raises(SystemExit, match="ACC-P1"):
        module.normalize_record_ids(("ACC-VOL-254",))

    with pytest.raises(SystemExit, match="duplicate"):
        module.normalize_record_ids(
            ("ACC-P1-EVID-01", "ACC-P1-EVID-01")
        )


def test_signer_command_delegates_identity_evidence_and_dry_run() -> None:
    module = _module()
    command = module.signer_command(
        action="sign-verification",
        record_id="ACC-P1-INTEL-05",
        actor_id="github-actions:p1-plan-verification",
        actor_type="ci",
        role="independent-verifier",
        statement="exact-head verification passed",
        signature_method="ci_oidc",
        signature_ref="run:123/job:456",
        git_sha="a" * 40,
        evidence=("ci://run/123", "git://head/" + "a" * 40),
        dry_run=True,
    )

    assert command[:4] == [
        sys.executable,
        str(module.SIGNER),
        "sign-verification",
        "ACC-P1-INTEL-05",
    ]
    assert "--actor-id" in command
    assert "github-actions:p1-plan-verification" in command
    assert "--signature-ref" in command
    assert "run:123/job:456" in command
    assert command.count("--evidence") == 2
    assert command[-1] == "--dry-run"


def test_signer_command_rejects_non_governed_action() -> None:
    module = _module()

    with pytest.raises(SystemExit, match="unsupported"):
        module.signer_command(
            action="set-status",
            record_id="ACC-P1-EVID-01",
            actor_id="chatgpt:gpt-5.6-sol",
            actor_type="agent",
            role="implementer",
            statement="no bypass",
            signature_method="github_identity",
            signature_ref=None,
            git_sha="b" * 40,
            evidence=(),
            dry_run=True,
        )


def test_snapshot_restore_round_trip(monkeypatch, tmp_path: Path) -> None:
    module = _module()
    first = tmp_path / "first.json"
    second = tmp_path / "second.md"
    first.write_bytes(b'{"state":"before"}\n')
    second.write_bytes(b"before\n")
    monkeypatch.setattr(module, "CANONICAL_PATHS", (first, second))

    before = module.snapshot()
    first.write_bytes(b'{"state":"after"}\n')
    second.write_bytes(b"after\n")

    module.restore(before)

    assert first.read_bytes() == b'{"state":"before"}\n'
    assert second.read_bytes() == b"before\n"


def test_snapshot_fails_closed_when_canonical_surface_is_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _module()
    present = tmp_path / "present.json"
    missing = tmp_path / "missing.json"
    present.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(module, "CANONICAL_PATHS", (present, missing))
    monkeypatch.setattr(module, "ROOT", tmp_path)

    with pytest.raises(SystemExit, match="canonical accountability surface"):
        module.snapshot()



def _batch_argv(*, dry_run: bool) -> list[str]:
    argv = [
        str(MODULE_PATH),
        "start",
        "--record-id",
        "ACC-P1-EVID-01",
        "--record-id",
        "ACC-P1-INTEL-01",
        "--actor-id",
        "chatgpt:gpt-5.6-sol",
        "--actor-type",
        "agent",
        "--role",
        "implementer",
        "--statement",
        "begin governed implementation",
        "--signature-method",
        "github_identity",
        "--git-sha",
        "c" * 40,
    ]
    if dry_run:
        argv.append("--dry-run")
    return argv


def test_main_dry_run_preflights_every_record_without_apply(monkeypatch) -> None:
    module = _module()
    commands: list[list[str]] = []
    monkeypatch.setattr(module, "run_checked", lambda command: commands.append(command))
    monkeypatch.setattr(sys, "argv", _batch_argv(dry_run=True))

    assert module.main() == 0
    assert len(commands) == 2
    assert all(command[-1] == "--dry-run" for command in commands)
    assert "ACC-P1-EVID-01" in commands[0]
    assert "ACC-P1-INTEL-01" in commands[1]


def test_main_preflights_entire_batch_before_first_apply(monkeypatch) -> None:
    module = _module()
    commands: list[list[str]] = []
    monkeypatch.setattr(module, "run_checked", lambda command: commands.append(command))
    monkeypatch.setattr(module, "snapshot", lambda: {})
    monkeypatch.setattr(sys, "argv", _batch_argv(dry_run=False))

    assert module.main() == 0
    assert len(commands) == 5
    assert commands[0][-1] == "--dry-run"
    assert commands[1][-1] == "--dry-run"
    assert "--dry-run" not in commands[2]
    assert "--dry-run" not in commands[3]
    assert commands[4] == [sys.executable, str(module.VALIDATOR)]
    assert "ACC-P1-EVID-01" in commands[2]
    assert "ACC-P1-INTEL-01" in commands[3]
