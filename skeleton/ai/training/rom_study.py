"""Rights-gated ROM fleet intake and replay-verified candidate training.

One explicitly approved local ROM at a time, using existing canonical emulator
and learning owners. Unsupported or unreviewed ROMs are reported, not silently
trained on a simulation. No ROM is copied to outputs and no production Jeeves
weights are loaded or changed.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Callable

SCHEMA = "skeleton.jeeves.rom_fleet_manifest.v1"
REPORT_SCHEMA = "skeleton.jeeves.rom_fleet_training.v1"
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,127}\Z")
_EXT = {
    ".gb": "game_boy", ".gbc": "game_boy_color",
    ".nes": "nes", ".sfc": "snes", ".smc": "snes",
    ".md": "genesis", ".gen": "genesis", ".smd": "genesis",
    ".sms": "master_system", ".gg": "game_gear",
    ".gba": "game_boy_advance", ".nds": "nintendo_ds",
    ".z64": "nintendo_64", ".n64": "nintendo_64", ".v64": "nintendo_64",
    ".lnx": "lynx", ".a78": "atari_7800", ".pbp": "psp",
}
MAX_FILES = 16384
MAX_DEPTH = 12
MAX_BLOB = 64 * 1024 * 1024
INLINE_ROM_BYTES = 2 * 1024 * 1024
MAX_MANIFEST = 8 * 1024 * 1024


class RomFleetError(ValueError):
    pass


def _digest(raw: bytes) -> str:
    return sha256(raw).hexdigest()


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode()


def _read(path: Path, cap: int) -> bytes:
    """No followed symlinks, device files, growing inputs or changed inode."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as f:
        before = os.fstat(f.fileno())
        if not stat.S_ISREG(before.st_mode) or not 1 <= before.st_size <= cap:
            raise RomFleetError("ROM/document is not a bounded regular file")
        data = f.read(cap + 1)
        after = os.fstat(f.fileno())
        current = os.stat(path, follow_symlinks=False)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if len(data) != before.st_size or identity(before) != identity(after) or identity(after) != identity(current):
            raise RomFleetError("ROM/document changed while being read")
        return data


def _root(directory: Path) -> Path:
    if not directory.is_absolute() or not directory.is_dir():
        raise RomFleetError("ROM root must be an explicit existing absolute directory")
    cursor = directory
    while cursor != cursor.parent:
        if cursor.is_symlink():
            raise RomFleetError("ROM root cannot traverse symlinks")
        cursor = cursor.parent
    return directory


def _safe(root: Path, rel: Any) -> Path:
    if (not isinstance(rel, str) or not 1 <= len(rel) <= 512
            or rel.startswith("/") or "\\" in rel
            or any(t in ("", ".", "..") or t.startswith(".") for t in rel.split("/"))):
        raise RomFleetError("ROM path must be an ordinary safe relative name")
    cur = root
    for part in rel.split("/"):
        cur = cur / part
        if cur.is_symlink():
            raise RomFleetError("ROM path traverses a symlink")
    if not cur.resolve().is_relative_to(root.resolve()):
        raise RomFleetError("ROM path escapes operator root")
    return cur


def _target(path: str) -> str | None:
    return _EXT.get(Path(path).suffix.casefold())


def discover(directory: Path) -> dict[str, Any]:
    """Scan every bounded eligible single-file ROM under the explicitly selected root.

    Archives and disc bundles are not silently extracted or truncated. They
    need the canonical streamed-content admission separately.
    """
    root = _root(directory)
    from skeleton.jeeves.game_emulator_catalog import canonical_targets

    known = canonical_targets()
    results: list[dict[str, Any]] = []
    queue = [(root, 0)]
    visited = 0
    while queue:
        folder, depth = queue.pop()
        if depth > MAX_DEPTH:
            raise RomFleetError("ROM directory depth exceeds scan capacity")
        with os.scandir(folder) as listing:
            entries = sorted(list(listing), key=lambda item: item.name)
        for entry in entries:
            visited += 1
            if visited > MAX_FILES:
                raise RomFleetError("ROM directory exceeds 16384 entries")
            if entry.is_symlink():
                raise RomFleetError("ROM directory contains symlink; explicit owner review required")
            if entry.is_dir(follow_symlinks=False):
                queue.append((Path(entry.path), depth + 1))
                continue
            if not entry.is_file(follow_symlinks=False):
                raise RomFleetError("ROM directory contains nonregular entries")
            relative = Path(entry.path).relative_to(root).as_posix()
            target = _target(relative)
            if target is None:
                continue
            size = entry.stat(follow_symlinks=False).st_size
            record: dict[str, Any] = {
                "rom_id": "rom." + _digest(relative.encode())[:20],
                "path": relative, "target_id": target,
                "bytes": size,
                "sha256": None,
                "eligibility": "unverified",
                "rights": {
                    "training_permitted": False,
                    "human_reviewed": False,
                },
            }
            if target not in known:
                record["eligibility"] = "unknown_canonical_target"
            elif not 1 <= size <= MAX_BLOB:
                record["eligibility"] = "oversized_or_empty"
            else:
                record["sha256"] = _digest(_read(_safe(root, relative), MAX_BLOB))
                record["eligibility"] = (
                    "eligible_for_rights_review"
                    if size <= INLINE_ROM_BYTES else "requires_streamed_content_adapter"
                )
            results.append(record)
    return {
        "schema_version": SCHEMA,
        "root": str(root),
        "roms": sorted(results, key=lambda x: x["path"]),
        "inventory_count": len(results),
        "training_executed": False,
        "production_jeeves_weights_modified": False,
        "note": "Operator must supply individual rights review; extension suffix is only a format hint.",
    }


def validate_manifest(manifest_path: Path) -> tuple[Path, list[dict[str, Any]], str]:
    source = _read(manifest_path, MAX_MANIFEST)
    try:
        data = json.loads(source.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise RomFleetError("ROM fleet manifest is not JSON") from exc
    from skeleton.jeeves.game_emulator_catalog import canonical_targets
    known = canonical_targets()
    rows = data.get("roms") if isinstance(data, dict) else None
    if (not isinstance(data, dict) or data.get("schema_version") != SCHEMA
            or not isinstance(rows, list) or len(rows) > MAX_FILES
            or data.get("training_executed") is not False
            or data.get("production_jeeves_weights_modified") is not False):
        raise RomFleetError("ROM fleet inventory is malformed or claims unproven training")
    root = _root(Path(data.get("root", "")))
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise RomFleetError("ROM row must be an object")
        relative = row.get("path")
        path = _safe(root, relative)
        target = row.get("target_id")
        if target not in known or target != _target(relative):
            raise RomFleetError("ROM type does not match canonical target")
        ident = row.get("rom_id")
        if (not isinstance(ident, str) or not _ID.fullmatch(ident) or ident in seen
                or relative in seen):
            raise RomFleetError("duplicate or invalid ROM identity")
        seen.update((ident, relative))
        digest = row.get("sha256")
        if digest is not None and (not isinstance(digest, str) or not _SHA.fullmatch(digest)):
            raise RomFleetError("invalid ROM SHA-256")
        rights = row.get("rights")
        if not isinstance(rights, dict):
            raise RomFleetError("ROM rights record missing")
        if rights.get("training_permitted") is True:
            if (rights.get("human_reviewed") is not True
                    or any(not isinstance(rights.get(k), str) or len(rights[k].strip()) < 5
                           for k in ("rights_holder", "rights_basis", "review_id"))
                    or not rights["rights_basis"].startswith(("original:", "license:", "public-domain:"))):
                raise RomFleetError("ROM train permission requires independent human rights review")
            if digest is None or not 1 <= row.get("bytes", 0) <= MAX_BLOB:
                raise RomFleetError("approved ROM requires fingerprinted bounded bytes")
        if not path.is_file():
            raise RomFleetError("ROM input vanished since catalog")
    return root, rows, _digest(source)


def _write_new(path: Path, payload: Any) -> None:
    if path.is_symlink() or path.exists() or not path.parent.is_dir():
        raise RomFleetError("output must be an unused regular path under an existing folder")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(_json_bytes(payload))
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def _request(row: dict[str, Any], rom: bytes, steps: int):
    from skeleton.jeeves.game_learning_parallel import GameEnvironmentRequest
    from skeleton.jeeves.game_emulator_catalog import GameEmulatorRegistry
    from skeleton.jeeves.game_rom_runtime import inspect_dmg_cartridge

    target = row["target_id"]
    filename = Path(row["path"]).name
    if target == "game_boy":
        try:
            inspect_dmg_cartridge(rom)
        except ValueError:
            pass  # An unsupported DMG mapper may still run on an approved real core.
        else:
            return GameEnvironmentRequest(
                target_id="game_boy", kind="builtin", rom_source=rom,
                max_steps=steps, filename=filename,
            )
    registry = GameEmulatorRegistry.from_environment()
    approved = registry.resolve(target)
    return GameEnvironmentRequest(
        target_id="emulator:" + target, kind="libretro", rom_source=rom,
        max_steps=steps, filename=filename,
        core_id=approved.core_id, registry_digest=registry.registry_digest,
    )


def _split_evidence(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Exactly the canonical CLI handoff to the neural trainer."""
    from skeleton.jeeves.game_learning import _digest as canonical_digest

    policy = result["policy_snapshot"]
    evidence = {key: value for key, value in result.items() if key != "policy_snapshot"}
    evidence["policy_snapshot_digest"] = policy["snapshot_digest"]
    evidence["evidence_digest"] = canonical_digest(evidence)
    return policy, evidence


def train_one(
    row: dict[str, Any], *, root: Path, seed: int,
    max_runs: int, steps: int, neural: bool,
    cancel: Callable[[], bool] | None = None,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None, dict[str, Any]]:
    """Actually run independent native Q training and optionally MLP SGD."""
    from skeleton.jeeves.game_emulator_training_lab import EmulatorLabConfig, run_emulator_training_lab
    from skeleton.jeeves.game_emulator_neural_world import NeuralWorldConfig, train_neural_world_from_evidence

    if row["rights"].get("training_permitted") is not True:
        raise RomFleetError("ROM training was not approved")
    raw = _read(_safe(root, row["path"]), INLINE_ROM_BYTES)
    if len(raw) != row["bytes"] or _digest(raw) != row["sha256"]:
        raise RomFleetError("ROM bytes changed after operator rights approval")
    request = _request(row, raw, steps)
    provenance = {
        "rights_acknowledged": True,
        "rights_review_id": row["rights"]["review_id"],
        "rights_basis": row["rights"]["rights_basis"],
        "source": "operator_approved_local_rom",
        "rom_digest": row["sha256"],
        "target_id": row["target_id"],
        "executable_core_kind": request.kind,
    }
    config = EmulatorLabConfig(
        max_runs=max_runs, steps_per_run=steps,
        stagnation_runs=10, checkpoint_stride=min(4, steps),
        counterfactual_actions=2, boomerang_interval=4,
        boomerang_retained=4, heldout_episodes=2, seed=seed,
    )
    report = run_emulator_training_lab(
        request, source_lineage=provenance, config=config,
        policy_id="rom-fleet-" + row["rom_id"].replace(".", "-"),
        cancel=cancel,
    )
    policy, evidence = _split_evidence(report)
    model, model_report = (None, None)
    if neural:
        model, model_report = train_neural_world_from_evidence(
            evidence, policy,
            config=NeuralWorldConfig(seed=seed, width=16, epochs=4),
            cancel=cancel,
        )
    summary = {
        "rom_id": row["rom_id"], "rom_sha256": row["sha256"],
        "target_id": row["target_id"], "status": "trained_candidate_only",
        "actual_q_updates": report["actual_q_table_updates"],
        "real_emulator_steps": report["actual_training_steps"],
        "audited_runs": report["run_count"],
        "report_digest": report["report_digest"],
        "neural_optimizer_steps": model["real_optimizer_steps"] if model is not None else 0,
        "neural_candidate_digest": model["model_digest"] if model is not None else None,
        "neural_qualified": model_report["candidate_status"] if model_report is not None else None,
        "production_jeeves_weight_updates": 0,
        "automatic_promotion": False,
    }
    return policy, evidence, model, {"summary": summary, "neural_report": model_report}


def train_all(manifest_path: Path, output_dir: Path, *,
              seed: int = 0, max_runs: int = 12, steps: int = 12,
              neural: bool = False, cancel: Callable[[], bool] | None = None) -> dict[str, Any]:
    if (type(seed) is not int or not 0 <= seed < 2**63
            or type(max_runs) is not int or not 10 <= max_runs <= 64
            or type(steps) is not int or not 4 <= steps <= 64
            or max_runs * steps > 4096):
        raise RomFleetError("fleet per-ROM training budget invalid")
    if output_dir.is_symlink() or not output_dir.is_dir():
        raise RomFleetError("outputs require an existing private directory")
    root, rows, manifest_sha = validate_manifest(manifest_path)
    if (output_dir.resolve().is_relative_to(root.resolve())
            or root.resolve().is_relative_to(output_dir.resolve())
            or manifest_path.resolve().parent == output_dir.resolve()):
        raise RomFleetError("training outputs must not overlap ROMs or rights manifest")
    results: list[dict[str, Any]] = []
    trained_digests: set[str] = set()
    for index, row in enumerate(rows):
        identity = row["rom_id"]
        if cancel is not None and cancel():
            raise RomFleetError("fleet cancelled before next ROM")
        if row["rights"].get("training_permitted") is not True:
            results.append({"rom_id": identity, "status": "not_authorized", "trained": False})
            continue
        if row["bytes"] > INLINE_ROM_BYTES:
            results.append({"rom_id": identity, "status": "streamed_adapter_required", "trained": False})
            continue
        if row["sha256"] in trained_digests:
            results.append({"rom_id": identity, "status": "duplicate_rom_covered_by_prior_candidate",
                            "trained": False, "covered": True})
            continue
        paths = {
            kind: output_dir / (identity + "-" + kind + ".json")
            for kind in ("policy", "evidence", "neural", "receipt")
        }
        if any(path.exists() or path.is_symlink() for path in paths.values()):
            results.append({"rom_id": identity, "status": "output_collision", "trained": False})
            continue
        try:
            policy, evidence, model, details = train_one(
                row, root=root, seed=(seed + index) % (2**63), max_runs=max_runs,
                steps=steps, neural=neural, cancel=cancel,
            )
            # Never write a success summary unless all its artifacts exist.
            _write_new(paths["policy"], policy)
            _write_new(paths["evidence"], evidence)
            if model is not None:
                _write_new(paths["neural"], model)
            receipt = details["summary"] | {
                "manifest_sha256": manifest_sha,
                "dataset_privacy": "local_only",
                "rom_bytes_exported": 0,
                "neural_report": details["neural_report"],
            }
            _write_new(paths["receipt"], receipt)
            trained_digests.add(row["sha256"])
            results.append({"rom_id": identity, "status": "candidate_written",
                            "trained": True, "covered": True,
                            "q_updates": receipt["actual_q_updates"],
                            "neural_steps": receipt["neural_optimizer_steps"],
                            "receipt": str(paths["receipt"])})
        except (OSError, ValueError, RuntimeError, ImportError) as exc:
            # Do not describe failures as trained or overwrite any partial
            # owner-controlled outputs. Operator reconciles partial results.
            results.append({"rom_id": identity, "status": "blocked",
                            "trained": False, "failure_type": type(exc).__name__,
                            "reason": str(exc)[:400]})
    return {
        "schema_version": REPORT_SCHEMA,
        "source_manifest_sha256": manifest_sha,
        "roms_discovered": len(rows),
        "roms_authorized": sum(r["rights"].get("training_permitted") is True for r in rows),
        "roms_trained": sum(r.get("trained") is True for r in results),
        "roms_covered": sum(r.get("covered") is True for r in results),
        "actual_q_updates": sum(r.get("q_updates", 0) for r in results),
        "actual_neural_steps": sum(r.get("neural_steps", 0) for r in results),
        "per_rom_results": results,
        "production_jeeves_weight_updates": 0,
        "production_promotion": False,
    }
