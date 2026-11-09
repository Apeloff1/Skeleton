"""Export original Pareto game instruction pairs for an operator-controlled SFT job.

The exporter only creates versioned datasets. It never contacts a model provider,
modifies weights, executes a training job, or promotes an artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from .game_pareto_train import plan

SCHEMA = "skeleton.game_pareto_chat_dataset.v1"


def _pair(text: str) -> dict[str, Any]:
    """Parse only the explicitly authored 'User: ... Jeeves: ...' lesson format."""
    if not isinstance(text, str) or not text.startswith("User: "):
        raise ValueError("original game lesson lacks expected user prefix")
    prompt, separator, answer = text[len("User: ") :].partition(" Jeeves: ")
    if not separator or not prompt.strip() or not answer.strip():
        raise ValueError("original game lesson lacks expected assistant completion")
    return {
        "messages": [
            {"role": "user", "content": prompt.strip()},
            {"role": "assistant", "content": answer.strip()},
        ]
    }


def _jsonl(cases: tuple[str, ...]) -> bytes:
    return "".join(
        json.dumps(
            _pair(case), sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        ) + "\n"
        for case in cases
    ).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _paths(train_path: Path, eval_path: Path, manifest_path: Path) -> tuple[Path, ...]:
    paths = (train_path.expanduser(), eval_path.expanduser(), manifest_path.expanduser())
    if len(set(path.resolve() for path in paths)) != len(paths):
        raise ValueError("training, evaluation, and manifest outputs must be separate")
    for path in paths:
        if path.exists() or path.is_symlink():
            raise ValueError("refusing to overwrite a dataset output: " + str(path))
        if not path.parent.is_dir():
            raise ValueError("dataset output parent directory does not exist")
    return paths


def _create_exclusive(path: Path, contents: bytes) -> None:
    """Write the temp file then hard-link it to its *new* destination atomically."""
    name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".game-pareto-", suffix=".tmp",
            dir=path.parent, delete=False
        ) as stream:
            name = Path(stream.name)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, 0o600)
        os.link(name, path)  # Link is exclusive and fails if destination exists.
    finally:
        if name is not None:
            name.unlink(missing_ok=True)


def export(train_path: Path, eval_path: Path, manifest_path: Path) -> dict[str, object]:
    destinations = _paths(train_path, eval_path, manifest_path)
    summary, training, heldout = plan()
    if set(training).intersection(heldout):
        raise ValueError("held-out examples leaked into training")
    train_data = _jsonl(training)
    eval_data = _jsonl(heldout)
    manifest: dict[str, object] = {
        "schema_version": SCHEMA,
        "source": "original_synthetic_in_repo",
        "training_sft_records": len(training),
        "evaluation_records": len(heldout),
        "training_sha256": _sha(train_data),
        "evaluation_sha256": _sha(eval_data),
        "curriculum_digest": summary["curriculum_digest"],
        "train_schedule_digest": summary["train_schedule_digest"],
        "heldout_digest": summary["heldout_digest"],
        "family_exposures": summary["family_exposures"],
        "training_format": "jsonl_chat_messages",
        "heldout_excluded_from_training": True,
        "external_training_executed": False,
        "production_promotion": False,
    }
    manifest_data = (json.dumps(
        manifest, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False
    ) + "\n").encode("utf-8")
    created: list[Path] = []
    try:
        # The manifest is linked LAST: it serves as the complete-export marker.
        for path, content in zip(destinations, (train_data, eval_data, manifest_data)):
            _create_exclusive(path, content)
            created.append(path)
    except OSError:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return {**manifest, "train_path": str(destinations[0].resolve()),
            "eval_path": str(destinations[1].resolve()),
            "manifest_path": str(destinations[2].resolve())}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new training JSONL path")
    parser.add_argument("--eval-output", type=Path, help="held-out JSONL path")
    parser.add_argument("--manifest-output", type=Path, help="new JSON receipt path")
    args = parser.parse_args(argv)
    target: Path = args.output
    evaluation = args.eval_output or target.with_name(target.stem + "-eval.jsonl")
    manifest = args.manifest_output or target.with_name(target.stem + "-manifest.json")
    try:
        report = export(target, evaluation, manifest)
        print(json.dumps(report, sort_keys=True, ensure_ascii=False, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)[:500]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
