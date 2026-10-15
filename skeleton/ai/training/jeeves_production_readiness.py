"""Production Jeeves game-training custody and readiness.

Three boundaries:
* A running app can attest its *already loaded* Jeeves cortex. A separate CLI
  never manufactures a serving-runtime attestation from a copied file.
* Operators can inspect a pinned checkpoint and bound resource requirements
  without training it.
* Only a matching, recent in-process attestation permits the offline candidate
  trainer to run. There is no scratch fallback or implicit model promotion.

No network, model downloads, background jobs, or GitHub Actions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from .jeeves_production_game_train import (
    ProductionCheckpointError,
    _active_snapshot,
    _production_source,
    _strict_json,
    _texts,
    _token_coverage,
)

SCHEMA = "skeleton.jeeves.production_training_attestation.v1"
READINESS_SCHEMA = "skeleton.jeeves.production_training_readiness.v1"
MAX_ATTESTATION_BYTES = 32 * 1024
MAX_ATTESTATION_AGE_SECONDS = 3600
MIN_FREE_BYTES = 512 * 1024 * 1024


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _save_new_private(path: Path, data: bytes) -> None:
    """No clobber, and no partial destination on interruption."""
    if path.exists() or path.is_symlink() or not path.parent.is_dir():
        raise ProductionCheckpointError("output must be a new path in an existing folder")
    if path.parent.is_symlink():
        raise ProductionCheckpointError("refusing symlink output folder")
    staged = None
    try:
        with tempfile.NamedTemporaryFile(
            prefix=".jeeves-training-", suffix=".tmp",
            mode="wb", dir=path.parent, delete=False,
        ) as stream:
            staged = Path(stream.name)
            os.chmod(staged, 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(staged, path)  # atomic and exclusive; race cannot overwrite
        if os.name == "posix":
            fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)


def _verified_runtime_snapshot(
    cortex: Any, snapshot: dict[str, Any],
) -> tuple[str, str, str]:
    """Require in-memory speaking weights to equal the persisted parent tensors."""
    from skeleton.cortex.neocortex import JeevesCortex
    if not isinstance(cortex, JeevesCortex):
        raise ProductionCheckpointError("serving object must be JeevesCortex")
    key, saved, mouth = _active_snapshot(snapshot)
    if cortex.speaking_name().strip().lower() != mouth:
        raise ProductionCheckpointError("serving mouth differs from persisted checkpoint")
    serving = cortex.speaking_lm()
    if not hasattr(serving, "snapshot"):
        raise ProductionCheckpointError("current serving model has no weight snapshot")
    live_weights = serving.snapshot()
    if key == "neo_rms" and serving is not cortex.neo_rms:
        raise ProductionCheckpointError("serving RMS mouth is not the saved RMS model")
    if key == "transformer" and serving is not cortex.transformer:
        raise ProductionCheckpointError("serving native mouth differs from saved transformer")
    # device/resident flags reflect runtime placement and are not weight data.
    ignored = {"device", "resident"}
    a = {k: v for k, v in saved.items() if k not in ignored}
    b = {k: v for k, v in live_weights.items() if k not in ignored}
    if _sha(_canonical(a)) != _sha(_canonical(b)):
        raise ProductionCheckpointError("in-memory speaking weights differ from saved checkpoint")
    if not isinstance(snapshot.get("bpe"), dict):
        raise ProductionCheckpointError("persisted production tokenizer missing")
    if _sha(_canonical(cortex.bpe.snapshot())) != _sha(_canonical(snapshot["bpe"])):
        raise ProductionCheckpointError("live tokenizer differs from saved tokenizer")
    return key, mouth, _sha(_canonical(a))


def attest_running_cortex(cortex: Any, destination: Path) -> dict[str, Any]:
    """Call INSIDE the serving app, not in a newly started CLI process.

    Requires the process-lived cortex singleton and a successfully restored
    configured checkpoint. This fails on fresh genesis or copied scratch data.
    """
    from skeleton.cortex import live
    with live._LOCK:
        if live._live_cortex is not cortex:
            raise ProductionCheckpointError("only in-process serving Jeeves may attest production weights")
        if not live._LAST_LOAD.get("loaded") or not live.persistence_configured():
            raise ProductionCheckpointError("live Jeeves did not restore configured production weights")
        source = live.configured_own_path()
        if source is None or source.is_symlink() or not source.is_file():
            raise ProductionCheckpointError("configured serving checkpoint unavailable")
        raw = source.read_bytes()
        checkpoint_hash = _sha(raw)
        verified_path, blob, checked_digest = _production_source(source, checkpoint_hash)
        key, mouth, tensor_digest = _verified_runtime_snapshot(cortex, blob)
        if _sha(verified_path.read_bytes()) != checked_digest:
            raise ProductionCheckpointError("checkpoint changed during runtime attestation")
        if destination.resolve() == verified_path.resolve():
            raise ProductionCheckpointError("attestation must not overwrite production checkpoint")
        receipt: dict[str, Any] = {
            "schema_version": SCHEMA,
            "source": "in_process_live_jeeves",
            "production_restored": True,
            "pid": os.getpid(),
            "created_unix": int(time.time()),
            "checkpoint_path": str(verified_path.resolve()),
            "checkpoint_sha256": checked_digest,
            "active_speaking_key": key,
            "active_mouth": mouth,
            "serving_weight_digest": tensor_digest,
            "tokenizer_sha256": _sha(_canonical(blob["bpe"])),
            "training_started": False,
            "candidate_promoted": False,
        }
        receipt["receipt_sha256"] = _sha(_canonical(receipt))
        _save_new_private(destination, _canonical(receipt) + b"\n")
        return receipt


def _load_attestation(path: Path, *, maximum_age_seconds: int) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ProductionCheckpointError("in-process runtime attestation missing")
    if path.stat().st_size > MAX_ATTESTATION_BYTES:
        raise ProductionCheckpointError("runtime attestation exceeds size bound")
    payload = _strict_json(path.read_bytes())
    if payload.get("schema_version") != SCHEMA or payload.get("source") != "in_process_live_jeeves":
        raise ProductionCheckpointError("only in-process production attestations are accepted")
    claimed = payload.get("receipt_sha256")
    unsealed = {k: v for k, v in payload.items() if k != "receipt_sha256"}
    if not isinstance(claimed, str) or claimed != _sha(_canonical(unsealed)):
        raise ProductionCheckpointError("runtime attestation was modified")
    created = payload.get("created_unix")
    now = int(time.time())
    if type(created) is not int or not 0 <= now - created <= maximum_age_seconds:
        raise ProductionCheckpointError("runtime attestation is expired or in the future")
    if payload.get("production_restored") is not True:
        raise ProductionCheckpointError("runtime did not restore production checkpoint")
    if type(payload.get("pid")) is not int or payload["pid"] <= 0:
        raise ProductionCheckpointError("runtime attestation lacks a serving PID")
    return payload


def inspect(
    *,
    attestation: Path | None,
    candidate_directory: Path,
    maximum_age_seconds: int = 900,
    minimum_free_bytes: int = MIN_FREE_BYTES,
    require_attestation: bool = True,
    allow_vocabulary_expansion: bool = False,
) -> dict[str, Any]:
    """Read-only preflight with actionable blockers; never trains or copies weights."""
    from skeleton.cortex.bpe import BytePairEncoder
    from skeleton.cortex.transformer import TinyTransformer

    if type(allow_vocabulary_expansion) is not bool:
        raise ValueError("vocabulary expansion must be an explicit boolean")
    if not 1 <= maximum_age_seconds <= MAX_ATTESTATION_AGE_SECONDS:
        raise ValueError("attestation maximum age must be between 1 and 3600 seconds")
    if type(minimum_free_bytes) is not int or not 0 <= minimum_free_bytes <= 2**40:
        raise ValueError("minimum free bytes invalid")
    if candidate_directory.is_symlink() or not candidate_directory.is_dir():
        raise ProductionCheckpointError("candidate directory must be an existing regular directory")

    blockers: list[str] = []
    source = os.environ.get("SKELETON_OWN", "").strip()
    receipt: dict[str, Any] | None = None
    if require_attestation:
        if attestation is None:
            blockers.append("missing_in_process_serving_attestation")
        else:
            try:
                receipt = _load_attestation(attestation, maximum_age_seconds=maximum_age_seconds)
            except (ProductionCheckpointError, OSError, ValueError) as exc:
                blockers.append("invalid_in_process_attestation:" + str(exc)[:120])
    elif attestation is not None:
        try:
            receipt = _load_attestation(attestation, maximum_age_seconds=maximum_age_seconds)
        except (ProductionCheckpointError, OSError, ValueError) as exc:
            blockers.append("invalid_in_process_attestation:" + str(exc)[:120])

    diagnostics: dict[str, Any] = {}
    if not source:
        blockers.append("SKELETON_OWN_not_configured")
    else:
        path = Path(source).expanduser()
        if path.is_symlink() or not path.is_file():
            blockers.append("production_cortex_file_missing")
        else:
            try:
                raw = path.read_bytes()
                live_hash = _sha(raw)
                if receipt is not None:
                    if (receipt.get("checkpoint_sha256") != live_hash or
                            receipt.get("checkpoint_path") != str(path.resolve())):
                        blockers.append("checkpoint_or_path_differs_from_live_attestation")
                _, data, _ = _production_source(path, live_hash)
                key, snap, mouth = _active_snapshot(data)
                is_torch = snap.get("kind") == "torch-stack"
                if is_torch:
                    from skeleton.cortex.torch_lm import TorchTransformer
                    model = TorchTransformer.from_snapshot(snap)
                    if model.snapshot().get("state") != snap.get("state"):
                        blockers.append("torch_weight_restore_mismatch")
                else:
                    model = TinyTransformer.from_snapshot(snap)
                    model.bpe = BytePairEncoder.from_snapshot(data["bpe"])
                    if model.snapshot().get("E") != snap.get("E"):
                        blockers.append("native_weight_restore_mismatch")
                train, heldout = _texts()
                all_cases = train + tuple(case for examples in heldout.values() for case in examples)
                coverage = _token_coverage(model, all_cases)
                planned_new_tokens = 0
                effective_coverage = coverage
                if coverage < 0.80:
                    if allow_vocabulary_expansion:
                        # Simulate token expansion on this private restored
                        # CLONE, using training examples only. Never build
                        # a token dictionary from held-out reference strings.
                        from hashlib import sha256 as _hash
                        seed_digest = _hash(_canonical(snap)).hexdigest()
                        if is_torch:
                            from .jeeves_torch_game_vocabulary import expand_torch_game_words
                            changed = expand_torch_game_words(
                                model, train, expected_snapshot_digest=seed_digest,
                            )
                        else:
                            from .jeeves_game_vocabulary import expand_native_game_pieces
                            changed = expand_native_game_pieces(
                                model, train, expected_snapshot_digest=seed_digest,
                            )
                        planned_new_tokens = changed["new_tokens"]
                        effective_coverage = _token_coverage(model, all_cases)
                        if effective_coverage < 0.80:
                            blockers.append("vocabulary_still_below_80_percent_after_train_only_growth")
                    else:
                        blockers.append("game_curriculum_vocabulary_coverage_below_80_percent")
                diagnostics.update({
                    "checkpoint_path": str(path.resolve()),
                    "checkpoint_sha256": live_hash,
                    "checkpoint_bytes": len(raw),
                    "model_kind": "torch-stack" if is_torch else "TinyTransformer",
                    "active_model_key": key,
                    "active_mouth": mouth,
                    "training_steps": snap["steps"],
                    "training_examples": len(train),
                    "evaluation_examples": sum(map(len, heldout.values())),
                    "vocabulary_coverage": round(coverage, 6),
                    "predicted_coverage_after_train_only_growth": round(effective_coverage, 6),
                    "heldout_tokens_used_for_vocabulary_growth": False,
                    "vocabulary_expansion_requested": allow_vocabulary_expansion,
                    "vocabulary_new_token_budget": planned_new_tokens,
                    "existing_weights_must_be_preserved": True,
                })
                if receipt is not None:
                    weight_hash = _sha(_canonical({
                        k: v for k, v in snap.items() if k not in {"device", "resident"}
                    }))
                    if (receipt.get("active_speaking_key") != key or
                            receipt.get("active_mouth") != mouth or
                            receipt.get("serving_weight_digest") != weight_hash or
                            receipt.get("tokenizer_sha256") != _sha(_canonical(data["bpe"]))):
                        blockers.append("attestation_model_or_tokenizer_mismatch")
            except (OSError, ValueError, TypeError, KeyError, RuntimeError, OverflowError) as exc:
                blockers.append("production_checkpoint_validation_failed:" + str(exc)[:150])
    disk = shutil.disk_usage(candidate_directory)
    if disk.free < minimum_free_bytes:
        blockers.append("insufficient_free_space_for_checkpoint_and_reports")
    return {
        "schema_version": READINESS_SCHEMA,
        "status": "ready_for_operator_training" if not blockers else "blocked",
        "production_training_executed": False,
        "candidate_promoted": False,
        "attestation_verified": receipt is not None,
        "candidate_directory": str(candidate_directory.resolve()),
        "free_bytes": disk.free,
        "minimum_free_bytes": minimum_free_bytes,
        "blockers": blockers,
        **diagnostics,
    }


def prepare_training_copy(
    *,
    attestation: Path,
    candidate_directory: Path,
    copy_destination: Path,
    maximum_age_seconds: int = 900,
    allow_vocabulary_expansion: bool = False,
) -> dict[str, Any]:
    """Create an immutable, checksum-bound backup before any training.

    The active serving checkpoint stays unchanged and must match attestation.
    The prepared copy is not itself production proof and never becomes a
    replacement parent for the existing trainer requiring SKELETON_OWN.
    """
    receipt = inspect(
        attestation=attestation,
        candidate_directory=candidate_directory,
        maximum_age_seconds=maximum_age_seconds,
        allow_vocabulary_expansion=allow_vocabulary_expansion,
    )
    if receipt["status"] != "ready_for_operator_training":
        raise ProductionCheckpointError("preflight blocked: " + ";".join(receipt["blockers"]))
    source = Path(receipt["checkpoint_path"])
    copy_destination = copy_destination.expanduser()
    if copy_destination.resolve() == source.resolve():
        raise ProductionCheckpointError("cannot copy over live production checkpoint")
    if copy_destination.parent.resolve() != candidate_directory.resolve():
        raise ProductionCheckpointError("backup must reside in the preflighted candidate directory")
    raw = source.read_bytes()
    if _sha(raw) != receipt["checkpoint_sha256"]:
        raise ProductionCheckpointError("live checkpoint changed during backup")
    _save_new_private(copy_destination, raw)
    if _sha(copy_destination.read_bytes()) != receipt["checkpoint_sha256"]:
        raise ProductionCheckpointError("production checkpoint backup failed integrity check")
    return {
        "status": "checkpoint_backup_prepared",
        "parent_sha256": receipt["checkpoint_sha256"],
        "backup_path": str(copy_destination.resolve()),
        "backup_bytes": len(raw),
        "production_weights_modified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("preflight", help="Read-only production training admission scan")
    scan.add_argument("--attestation", type=Path)
    scan.add_argument("--candidate-directory", type=Path, required=True)
    scan.add_argument("--max-age-seconds", type=int, default=900)
    scan.add_argument("--min-free-bytes", type=int, default=MIN_FREE_BYTES)
    scan.add_argument("--allow-unattested-inspection", action="store_true")
    scan.add_argument("--allow-vocabulary-expansion", action="store_true")
    backup = sub.add_parser("backup", help="Exclusive verified backup of active production checkpoint")
    backup.add_argument("--attestation", type=Path, required=True)
    backup.add_argument("--candidate-directory", type=Path, required=True)
    backup.add_argument("--output", type=Path, required=True)
    backup.add_argument("--max-age-seconds", type=int, default=900)
    backup.add_argument("--allow-vocabulary-expansion", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "preflight":
            result = inspect(
                attestation=args.attestation,
                candidate_directory=args.candidate_directory,
                maximum_age_seconds=args.max_age_seconds,
                minimum_free_bytes=args.min_free_bytes,
                require_attestation=not args.allow_unattested_inspection,
                allow_vocabulary_expansion=args.allow_vocabulary_expansion,
            )
        else:
            result = prepare_training_copy(
                attestation=args.attestation,
                candidate_directory=args.candidate_directory,
                copy_destination=args.output,
                maximum_age_seconds=args.max_age_seconds,
                allow_vocabulary_expansion=args.allow_vocabulary_expansion,
            )
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        return 0 if result["status"] != "blocked" else 3
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:400]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
