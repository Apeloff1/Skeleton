"""Immutable per-batch optimizer cursor checkpoints for Jeeves candidate training.

A run writes its model snapshot and a commit marker after every bounded batch.
Crash between those writes leaves an orphan data file, not an admitted cursor.
The parent live checkpoint remains untouched; never resume from unverified
bytes, another curriculum, another model identity or another optimizer config.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .jeeves_production_game_train import (
    MAX_BYTES, ProductionCheckpointError, _strict_json,
)
from .jeeves_production_readiness import _canonical, _save_new_private

CURSOR_SCHEMA = "skeleton.jeeves.game_training_cursor.v1"
WEIGHTS_SCHEMA = "skeleton.jeeves.game_training_intermediate.v1"
_RUN_ID = re.compile(r"[a-z][a-z0-9_-]{2,47}")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CandidateProgress:
    """Owner of immutable on-disk candidate-only states for one training run."""

    def __init__(
        self, *, directory: Path, run_id: str, parent_sha256: str,
        config_digest: str, total_batches: int, parent_steps: int,
        selected_model_key: str,
    ) -> None:
        if not _RUN_ID.fullmatch(run_id):
            raise ProductionCheckpointError("invalid resumable run ID")
        if directory.is_symlink() or not directory.is_dir():
            raise ProductionCheckpointError("progress directory must be existing private folder")
        if not 1 <= total_batches <= 300:
            raise ProductionCheckpointError("resumable optimizer batch count outside budget")
        if not 0 <= parent_steps <= 10**12:
            raise ProductionCheckpointError("invalid native training cursor")
        if any(len(x) != 64 or not re.fullmatch(r"[0-9a-f]{64}", x)
               for x in (parent_sha256, config_digest)):
            raise ProductionCheckpointError("progress requires pinned content digests")
        if selected_model_key not in ("transformer", "neo_rms"):
            raise ProductionCheckpointError("invalid active production model key")
        self.directory = directory
        self.prefix = "jeeves-" + run_id
        self.parent_sha256 = parent_sha256
        self.config_digest = config_digest
        self.total_batches = total_batches
        self.parent_steps = parent_steps
        self.selected_model_key = selected_model_key

    def _paths(self, index: int) -> tuple[Path, Path]:
        if not 0 <= index <= self.total_batches:
            raise ProductionCheckpointError("resumable cursor out of range")
        suffix = f"{index:04d}.json"
        return (
            self.directory / (self.prefix + "-weights-" + suffix),
            self.directory / (self.prefix + "-progress-" + suffix),
        )

    def _read_weights(self, path: Path, expected_sha: str) -> dict[str, Any]:
        if path.is_symlink() or not path.is_file() or not 20 <= path.stat().st_size <= MAX_BYTES:
            raise ProductionCheckpointError("immutable training batch weights missing")
        raw = path.read_bytes()
        if _sha(raw) != expected_sha:
            raise ProductionCheckpointError("training batch weights have changed")
        envelope = _strict_json(raw)
        if envelope.get("schema_version") != WEIGHTS_SCHEMA:
            raise ProductionCheckpointError("resumable checkpoint schema mismatch")
        snapshot = envelope.get("model_snapshot")
        if not isinstance(snapshot, dict):
            raise ProductionCheckpointError("resumable checkpoint has no model weights")
        return snapshot

    def _validate_cursor(self, index: int) -> dict[str, Any]:
        weight_path, receipt_path = self._paths(index)
        if receipt_path.is_symlink() or not receipt_path.is_file() or receipt_path.stat().st_size > 8192:
            raise ProductionCheckpointError("committed training cursor missing")
        receipt = _strict_json(receipt_path.read_bytes())
        if receipt.get("schema_version") != CURSOR_SCHEMA:
            raise ProductionCheckpointError("training cursor schema mismatch")
        if any(receipt.get(key) != expected for key, expected in (
            ("run_prefix", self.prefix),
            ("batch_index", index),
            ("parent_checkpoint_sha256", self.parent_sha256),
            ("config_digest", self.config_digest),
            ("total_batches", self.total_batches),
            ("parent_steps", self.parent_steps),
            ("selected_model_key", self.selected_model_key),
        )):
            raise ProductionCheckpointError("training cursor is from another model, policy, or batch")
        if not isinstance(receipt.get("weights_sha256"), str):
            raise ProductionCheckpointError("training cursor weight digest missing")
        snapshot = self._read_weights(weight_path, receipt["weights_sha256"])
        cursor_steps = receipt.get("candidate_steps")
        if type(cursor_steps) is not int or cursor_steps < self.parent_steps:
            raise ProductionCheckpointError("training cursor optimizer steps invalid")
        if type(snapshot.get("steps")) is not int or snapshot["steps"] != cursor_steps:
            raise ProductionCheckpointError("training cursor does not match stored optimizer steps")
        if type(receipt.get("completed_updates")) is not int:
            raise ProductionCheckpointError("training cursor update count malformed")
        if receipt["completed_updates"] != cursor_steps - self.parent_steps:
            raise ProductionCheckpointError("training cursor and starting checkpoint disagree")
        return {"receipt": receipt, "snapshot": snapshot}

    def initial_snapshot(self) -> dict[str, Any]:
        """Inspect stage zero to compare it against reconstructed live parent."""
        return self._validate_cursor(0)["snapshot"]

    def latest(self, *, resume: bool) -> tuple[int, dict[str, Any]] | None:
        """Refuse accidental reuse; verify every committed stage and no gaps."""
        committed = sorted(self.directory.glob(self.prefix + "-progress-*.json"))
        if not committed:
            if resume:
                raise ProductionCheckpointError("requested resume has no committed optimizer cursor")
            return None
        if not resume:
            raise ProductionCheckpointError("resumable run ID already has optimizer progress")
        states: list[tuple[int, dict[str, Any]]] = []
        for path in committed:
            suffix = path.name.rsplit("-", 1)[-1]
            if not re.fullmatch(r"\d{4}\.json", suffix):
                raise ProductionCheckpointError("unexpected committed optimizer cursor filename")
            index = int(suffix[:-5])
            if index != len(states):
                raise ProductionCheckpointError("optimizer cursor stages are noncontiguous")
            states.append((index, self._validate_cursor(index)))
        if states[-1][0] > self.total_batches:
            raise ProductionCheckpointError("more training stages than the current run budget")
        return states[-1]

    def write(self, index: int, model_snapshot: dict[str, Any]) -> dict[str, Any]:
        """Publish weights before the corresponding immutable commit marker."""
        if type(model_snapshot.get("steps")) is not int:
            raise ProductionCheckpointError("checkpoint weight cursor missing")
        if index > 0:
            prev = self._validate_cursor(index - 1)
            if model_snapshot["steps"] <= prev["receipt"]["candidate_steps"]:
                raise ProductionCheckpointError("optimizer did not advance after its previous batch")
        weight_path, receipt_path = self._paths(index)
        weights = {
            "schema_version": WEIGHTS_SCHEMA,
            "model_snapshot": model_snapshot,
        }
        raw = _canonical(weights) + b"\n"
        digest = _sha(raw)
        if weight_path.exists():
            if weight_path.is_symlink() or _sha(weight_path.read_bytes()) != digest:
                raise ProductionCheckpointError("existing optimizer stage weights disagree")
        else:
            _save_new_private(weight_path, raw)
        receipt = {
            "schema_version": CURSOR_SCHEMA,
            "run_prefix": self.prefix,
            "batch_index": index,
            "total_batches": self.total_batches,
            "parent_checkpoint_sha256": self.parent_sha256,
            "config_digest": self.config_digest,
            "selected_model_key": self.selected_model_key,
            "parent_steps": self.parent_steps,
            "candidate_steps": model_snapshot["steps"],
            "completed_updates": model_snapshot["steps"] - self.parent_steps,
            "weights_sha256": digest,
            "production_weights_modified": False,
            "candidate_promoted": False,
        }
        marker = _canonical(receipt) + b"\n"
        if receipt_path.exists():
            if receipt_path.is_symlink() or receipt_path.read_bytes() != marker:
                raise ProductionCheckpointError("existing committed training cursor conflicts")
        else:
            _save_new_private(receipt_path, marker)
        return receipt


__all__ = ["CandidateProgress", "CURSOR_SCHEMA"]
