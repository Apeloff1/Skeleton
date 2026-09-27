from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "emit_p1_promotion_evidence.py"
HEAD = "a" * 40


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "emit_p1_promotion_evidence_under_test",
        SCRIPT,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _args(tmp_path: Path, *, expected_head: str | None = HEAD):
    evidence_file = tmp_path / "evidence.json"
    evidence_file.write_text(
        json.dumps(
            [
                {
                    "source": "pytest:test-a",
                    "digest": "1" * 64,
                    "category": "test",
                },
                {
                    "source": "pytest:test-b",
                    "digest": "2" * 64,
                    "category": "test",
                },
            ]
        ),
        encoding="utf-8",
    )
    args = [
        "--repository",
        "Apeloff1/Skeleton",
        "--commit-sha",
        HEAD,
        "--task-id",
        "P1-EVID-01",
        "--accountability-id",
        "ACC-P1-EVID-01",
        "--configuration-digest",
        "b" * 64,
        "--environment-digest",
        "c" * 64,
        "--verifier-id",
        "ci:p1-evidence",
        "--verifier-digest",
        "d" * 64,
        "--test-manifest-digest",
        "e" * 64,
        "--run-id",
        "36300000000",
        "--run-attempt",
        "1",
        "--observed-at",
        "2026-09-27T16:00:00Z",
        "--evidence-file",
        str(evidence_file),
    ]
    if expected_head is not None:
        args.extend(["--expected-head", expected_head])
    return args


def test_emitter_produces_canonical_exact_head_receipt(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_module()

    assert module.main(_args(tmp_path)) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["commit_sha"] == HEAD
    assert payload["task_id"] == "P1-EVID-01"
    assert payload["accountability_id"] == "ACC-P1-EVID-01"
    assert len(payload["subject_digest"]) == 64
    assert len(payload["evidence_digest"]) == 64
    assert len(payload["receipt_digest"]) == 64
    assert len(payload["evidence"]) == 2


def test_emitter_rejects_stale_head(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_module()

    assert module.main(_args(tmp_path, expected_head="f" * 40)) == 1

    assert "does not match expected exact head" in capsys.readouterr().out


def test_emitter_writes_same_canonical_payload_to_file(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_module()
    out = tmp_path / "receipt.json"
    args = _args(tmp_path) + ["--out", str(out)]

    assert module.main(args) == 0

    stdout = capsys.readouterr().out.strip()
    assert out.read_text(encoding="utf-8").strip() == stdout


def test_emitter_rejects_unknown_evidence_fields(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_module()
    args = _args(tmp_path)
    evidence_file = tmp_path / "evidence.json"
    evidence_file.write_text(
        json.dumps(
            [
                {
                    "source": "pytest:test-a",
                    "digest": "1" * 64,
                    "category": "test",
                    "payload": "forbidden",
                }
            ]
        ),
        encoding="utf-8",
    )

    assert module.main(args) == 1

    assert "unknown fields" in capsys.readouterr().out


def test_emitter_rejects_non_array_evidence(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _load_module()
    args = _args(tmp_path)
    evidence_file = tmp_path / "evidence.json"
    evidence_file.write_text("{}", encoding="utf-8")

    assert module.main(args) == 1

    assert "JSON array" in capsys.readouterr().out
