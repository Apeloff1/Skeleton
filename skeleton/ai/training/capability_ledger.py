"""Local, bounded capability-evaluation history with no training-data retention.

Receipts are aggregate-only: model identity, pinned source manifest and
per-mode correct/total counts. No prompts, ground-truth answers, predictions,
intermediate reasoning, tokens or external sources are persisted.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
from typing import Any, Mapping

from .offline_foundations import validate_curriculum
from .sparse_capability import CAPABILITIES, assess_heldout_capabilities

SCHEMA = "skeleton.offline_capability_ledger.v1"
MAX_REPORTS = 500
MODEL_TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_MODES = frozenset(
    family + ":" + mode
    for family, modes in CAPABILITIES.items() for mode in modes
)


class CapabilityLedgerError(ValueError):
    """Unsafe, forged, oversized or invalid capability evidence."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _admit_model_tag(name: str) -> str:
    if not isinstance(name, str) or MODEL_TAG.fullmatch(name) is None:
        raise CapabilityLedgerError("model tag must be 1-64 safe ASCII characters")
    return name


def _checked_scores(scores: Mapping[str, Any]) -> dict[str, dict[str, int]]:
    if not isinstance(scores, Mapping) or set(scores) != _MODES:
        raise CapabilityLedgerError("capability receipt must include exactly 36 modes")
    result: dict[str, dict[str, int]] = {}
    for mode in sorted(_MODES):
        item = scores[mode]
        if (
            not isinstance(item, Mapping) or set(item) != {"correct", "total"}
            or type(item["correct"]) is not int or type(item["total"]) is not int
            or not 0 <= item["correct"] <= item["total"] <= 12
            or item["total"] < 1
        ):
            raise CapabilityLedgerError("invalid capability-mode scored counts")
        result[mode] = {"correct": item["correct"], "total": item["total"]}
    return result


def _check_receipt(entry: Mapping[str, Any]) -> dict[str, Any]:
    expected_fields = {
        "schema_version", "model_tag", "source_manifest_sha256",
        "prediction_sha256", "split", "total", "correct",
        "per_mode", "promotion_authorized", "training_data_modified",
    }
    if not isinstance(entry, Mapping) or set(entry) != expected_fields:
        raise CapabilityLedgerError("capability receipt has an invalid schema")
    if (
        entry["schema_version"] != SCHEMA
        or entry["split"] != "validation"
        or entry["promotion_authorized"] is not False
        or entry["training_data_modified"] is not False
    ):
        raise CapabilityLedgerError("ledger accepts only unpromoted validation evidence")
    _admit_model_tag(entry["model_tag"])
    for label in ("source_manifest_sha256", "prediction_sha256"):
        val = entry[label]
        if (
            not isinstance(val, str) or len(val) != 64
            or any(char not in "0123456789abcdef" for char in val)
        ):
            raise CapabilityLedgerError("receipt digest is invalid")
    per_mode = _checked_scores(entry["per_mode"])
    count = sum(item["total"] for item in per_mode.values())
    correct = sum(item["correct"] for item in per_mode.values())
    if (
        type(entry["total"]) is not int or type(entry["correct"]) is not int
        or entry["total"] != count or entry["correct"] != correct
        or count != 108
        or any(item["total"] != 3 for item in per_mode.values())
    ):
        raise CapabilityLedgerError("capability receipt totals are inconsistent")
    return {**entry, "per_mode": per_mode}


def make_capability_receipt(
    directory: str | Path,
    prediction_file: str | Path,
    *,
    model_tag: str,
) -> dict[str, Any]:
    model_tag = _admit_model_tag(model_tag)
    admitted = validate_curriculum(directory)
    score = assess_heldout_capabilities(
        directory, prediction_file, split="validation",
    )
    return _check_receipt({
        "schema_version": SCHEMA,
        "model_tag": model_tag,
        "source_manifest_sha256": admitted["manifest_sha256"],
        "prediction_sha256": score["prediction_sha256"],
        "split": "validation",
        "total": score["heldout_total"],
        "correct": score["heldout_correct"],
        "per_mode": score["per_mode"],
        "promotion_authorized": False,
        "training_data_modified": False,
    })


class OfflineCapabilityLedger:
    """SQLite receipts and regression comparisons, no raw dataset storage."""

    def __init__(self, path: str | Path) -> None:
        db = Path(path).expanduser().absolute()
        if db.is_symlink() or not db.parent.is_dir() or (
            db.exists() and not db.is_file()
        ):
            raise CapabilityLedgerError("ledger requires a local regular SQLite file")
        # No user-selectable/redirected journal sidecar is admitted.
        from skeleton.app.offline_sqlite_safety import (
            UnsafeOfflineSqlitePath, check_sqlite_companion_paths,
        )
        try:
            check_sqlite_companion_paths(db)
        except UnsafeOfflineSqlitePath as exc:
            raise CapabilityLedgerError(str(exc)) from exc
        self.path = db
        self._lock = threading.RLock()
        was_present = db.exists()
        self._db = sqlite3.connect(
            str(db), timeout=10, isolation_level=None, check_same_thread=False,
        )
        try:
            if not was_present and os.name == "posix":
                os.chmod(db, 0o600)
            self._db.execute("PRAGMA busy_timeout=10000")
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS capability_reports ("
                "position INTEGER PRIMARY KEY AUTOINCREMENT,"
                "receipt_id TEXT NOT NULL UNIQUE,"
                "model_tag TEXT NOT NULL,"
                "source_manifest_sha256 TEXT NOT NULL,"
                "report_json TEXT NOT NULL)"
            )
            self._db.execute(
                "CREATE INDEX IF NOT EXISTS idx_capability_models "
                "ON capability_reports(model_tag,position)"
            )
        except BaseException:
            self._db.close()
            raise

    def __enter__(self) -> "OfflineCapabilityLedger":
        return self

    def __exit__(self, *_unused: object) -> None:
        self.close()

    def close(self) -> None:
        with self._lock:
            self._db.close()

    def _parse_stored(self, receipt_id: str, raw: str) -> dict[str, Any]:
        try:
            # Stored data is not inherently trusted even if it is local.
            data = json.loads(
                raw,
                object_pairs_hook=lambda pairs: self._unique_keys(pairs),
                parse_constant=lambda value: self._reject_constant(value),
            )
        except (ValueError, TypeError) as exc:
            raise CapabilityLedgerError("stored capability receipt is malformed") from exc
        receipt = _check_receipt(data)
        if _digest(receipt) != receipt_id:
            raise CapabilityLedgerError("stored capability receipt identity mismatch")
        return receipt

    @staticmethod
    def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise CapabilityLedgerError("duplicate capability receipt JSON key")
            out[key] = value
        return out

    @staticmethod
    def _reject_constant(value: str) -> None:
        raise CapabilityLedgerError("nonfinite capability receipt JSON value")

    def record(self, receipt: Mapping[str, Any]) -> str:
        checked = _check_receipt(receipt)
        receipt_id = _digest(checked)
        raw = _canonical(checked).decode("ascii")
        with self._lock:
            self._db.execute("BEGIN IMMEDIATE")
            try:
                old = self._db.execute(
                    "SELECT report_json FROM capability_reports WHERE receipt_id=?",
                    (receipt_id,),
                ).fetchone()
                if old is not None:
                    if old[0] != raw:
                        raise CapabilityLedgerError("duplicate receipt has inconsistent content")
                    self._db.execute("COMMIT")
                    return receipt_id
                count = self._db.execute(
                    "SELECT COUNT(*) FROM capability_reports"
                ).fetchone()[0]
                if count >= MAX_REPORTS:
                    raise CapabilityLedgerError("ledger has reached the report retention limit")
                self._db.execute(
                    "INSERT INTO capability_reports "
                    "(receipt_id,model_tag,source_manifest_sha256,report_json) "
                    "VALUES (?,?,?,?)",
                    (receipt_id, checked["model_tag"],
                     checked["source_manifest_sha256"], raw),
                )
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
        return receipt_id

    def latest(
        self, model_tag: str, *, source_manifest_sha256: str,
        limit: int = 10,
    ) -> tuple[dict[str, Any], ...]:
        model_tag = _admit_model_tag(model_tag)
        if (
            type(limit) is not int or not 1 <= limit <= MAX_REPORTS
            or not isinstance(source_manifest_sha256, str)
            or len(source_manifest_sha256) != 64
        ):
            raise CapabilityLedgerError("invalid capability report query")
        with self._lock:
            rows = self._db.execute(
                "SELECT receipt_id,report_json FROM capability_reports "
                "WHERE model_tag=? AND source_manifest_sha256=? "
                "ORDER BY position DESC LIMIT ?",
                (model_tag, source_manifest_sha256, limit),
            ).fetchall()
        return tuple(self._parse_stored(identity, raw) for identity, raw in rows)

    def compare(
        self, model_tag: str, *, source_manifest_sha256: str,
    ) -> dict[str, Any]:
        entries = self.latest(
            model_tag, source_manifest_sha256=source_manifest_sha256, limit=2,
        )
        if not entries:
            return {
                "schema_version": SCHEMA, "model_tag": model_tag,
                "evaluations": 0, "improved_modes": [], "regressed_modes": [],
                "unchanged_modes": [], "proficiency_claimed": False,
            }
        current = entries[0]
        previous = entries[1] if len(entries) > 1 else None
        improved: list[str] = []
        regressed: list[str] = []
        unchanged: list[str] = []
        if previous:
            for mode in sorted(_MODES):
                change = (
                    current["per_mode"][mode]["correct"]
                    - previous["per_mode"][mode]["correct"]
                )
                (improved if change > 0 else regressed if change < 0
                 else unchanged).append(mode)
        return {
            "schema_version": SCHEMA,
            "model_tag": model_tag,
            "evaluations": len(entries),
            "latest_correct": current["correct"],
            "latest_total": current["total"],
            "previous_correct": None if previous is None else previous["correct"],
            "improved_modes": improved,
            "regressed_modes": regressed,
            "unchanged_modes": unchanged,
            "last_prediction_sha256": current["prediction_sha256"],
            "training_samples_added": 0,
            "proficiency_claimed": False,
            "production_promotion_authorized": False,
        }


__all__ = [
    "SCHEMA", "MAX_REPORTS", "CapabilityLedgerError",
    "make_capability_receipt", "OfflineCapabilityLedger",
]
