"""Operator-gated SDK evidence and extension to Jeeves's existing multidomain trainer.

The canonical console catalog is not an installed-SDK census. Local SDK documents
must be explicitly enumerated, hash-pinned and rights-reviewed before any of
their content can be used for candidate training. This module never runs
compilers, crawls documentation or modifies model weights.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any

from .jeeves_multidomain import (
    SCHEMA as TRAIN_SCHEMA, _rows, _split_guard, _strict_object,
    generate_modules, load_multidomain_corpus,
)

SDK_SCHEMA = "skeleton.jeeves.sdk_sources.v1"
REVIEW_SCHEMA = "skeleton.jeeves.sdk_reviewed_example.v1"
REPORT_SCHEMA = "skeleton.jeeves.sdk_readiness.v1"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{2,127}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_REL = re.compile(r"[A-Za-z0-9_.\-/]{1,200}\Z")
_EXT = {".md", ".txt", ".rst", ".h", ".hpp", ".c", ".cpp", ".py", ".json"}
MAX_SDKS = 128
MAX_DOCS = 512
MAX_DOC_BYTES = 512 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_REVIEW = 2048
SDK_KINDS = frozenset(("console", "engine", "graphics", "audio", "mobile",
                       "web", "ai", "tooling", "desktop", "embedded", "other"))


class SDKStudyError(ValueError):
    """Malformed provenance, unavailable SDK or unadmitted training evidence."""


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise SDKStudyError(label + " must be a bounded stable identifier")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise SDKStudyError(label + " must be lowercase SHA-256")
    return value


def _document(path: Path, *, max_bytes: int) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise SDKStudyError("SDK document must be an existing regular file")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= max_bytes:
        raise SDKStudyError("SDK document size or type invalid")
    raw = path.read_bytes()
    if len(raw) != info.st_size:
        raise SDKStudyError("SDK document changed while inspecting")
    return raw


def _safe_under(root: Path, relative: Any) -> Path:
    if (not isinstance(relative, str) or not _REL.fullmatch(relative)
            or relative.startswith("/") or "\\" in relative
            or any(x in ("", ".", "..") or x.startswith(".")
                   for x in relative.split("/"))):
        raise SDKStudyError("SDK documentation path is unsafe")
    destination = root
    for part in relative.split("/"):
        destination = destination / part
        if destination.is_symlink():
            raise SDKStudyError("SDK documentation cannot traverse symlinks")
    if not destination.resolve().is_relative_to(root.resolve()):
        raise SDKStudyError("SDK documentation escapes installed root")
    if destination.suffix.lower() not in _EXT:
        raise SDKStudyError("SDK documentation format not in bounded text allowlist")
    return destination


def _root(raw: Any) -> Path:
    if not isinstance(raw, str) or not 2 <= len(raw) <= 1024:
        raise SDKStudyError("SDK installation root must be an absolute path")
    root = Path(raw)
    if not root.is_absolute() or not root.is_dir():
        raise SDKStudyError("SDK installation root does not exist")
    current = root
    while current != current.parent:
        if current.is_symlink():
            raise SDKStudyError("SDK installation root cannot traverse symlinks")
        current = current.parent
    return root


def target_inventory() -> dict[str, Any]:
    """Truthful complete canonical target census, without executing any SDK."""
    from skeleton.ai.webcrawler.dragon_native_targets import target_catalog

    targets = target_catalog()
    readiness: dict[str, dict[str, Any]] = {}
    error = None
    try:
        from skeleton.jeeves.game_console_build import console_build_catalog

        readiness = {row["target_id"]: row for row in console_build_catalog()}
    except (OSError, RuntimeError, ValueError, ImportError) as exc:
        error = type(exc).__name__
    rows = []
    for target in targets:
        probe = readiness.get(target["id"])
        rows.append({
            "target_id": target["id"],
            "family": target["family"],
            "target_status": target["status"],
            "declared_toolchain": target["toolchain"],
            "sdk_state": probe["state"] if probe is not None else "not_probed",
            "missing_dependencies": probe["missing_dependencies"] if probe is not None else [],
            "compile_verified": False,
            "rights_to_train_verified": False,
        })
    return {
        "schema_version": REPORT_SCHEMA,
        "canonical_target_count": len(rows),
        "build_adapter_probe": "available" if error is None else "unavailable",
        "probe_failure_type": error,
        "targets": rows,
        "sdk_documents_approved": 0,
        "training_executed": False,
        "production_weights_modified": False,
    }


def validate_sources(manifest_path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Check operator-selected local SDK docs by pinned bytes, not name alone."""
    raw = _document(manifest_path, max_bytes=1024 * 1024)
    data = _strict_object(raw)
    declarations = data.get("sdks")
    if (data.get("schema_version") != SDK_SCHEMA
            or not isinstance(declarations, list)
            or not 1 <= len(declarations) <= MAX_SDKS):
        raise SDKStudyError("SDK source manifest schema or SDK count invalid")
    from skeleton.ai.webcrawler.dragon_native_targets import target_catalog

    known_targets = {row["id"] for row in target_catalog()}
    entries: dict[str, dict[str, Any]] = {}
    sdk_ids: set[str] = set()
    total = 0
    for sdk in declarations:
        if not isinstance(sdk, dict):
            raise SDKStudyError("SDK descriptor must be an object")
        ident = _id(sdk.get("sdk_id"), "sdk_id")
        if ident in sdk_ids:
            raise SDKStudyError("duplicate SDK identity")
        sdk_ids.add(ident)
        version = sdk.get("version")
        if not isinstance(version, str) or not 1 <= len(version) <= 128:
            raise SDKStudyError("SDK version must be explicit")
        kind = sdk.get("sdk_kind", "console")
        if kind not in SDK_KINDS:
            raise SDKStudyError("unknown SDK family")
        targets = sdk.get("target_ids", [])
        if (not isinstance(targets, list)
                or (kind == "console" and not targets)
                or any(not isinstance(t, str) for t in targets)
                or len(targets) != len(set(targets))
                or any(t not in known_targets for t in targets)):
            raise SDKStudyError("declared console targets must be canonical; other SDKs may use an empty target list")
        root = _root(sdk.get("root"))
        rights = sdk.get("rights")
        if not isinstance(rights, dict):
            raise SDKStudyError("SDK rights declaration required even for inventory")
        admitted = rights.get("training_permitted") is True and rights.get("human_reviewed") is True
        if admitted:
            if (any(not isinstance(rights.get(k), str) or len(rights[k].strip()) < 5
                    for k in ("rights_holder", "rights_basis", "review_id"))
                    or not rights["rights_basis"].startswith(("license:", "original:", "public-domain:"))):
                raise SDKStudyError("SDK requires a documented training license and human review")
        docs = sdk.get("documents")
        if not isinstance(docs, list) or not 1 <= len(docs) <= MAX_DOCS:
            raise SDKStudyError("SDK document list absent or over capacity")
        seen_paths: set[str] = set()
        for doc in docs:
            if not isinstance(doc, dict) or set(doc) != {"path", "sha256"}:
                raise SDKStudyError("SDK document requires exact path and SHA-256")
            rel = doc["path"]
            if rel in seen_paths:
                raise SDKStudyError("SDK document repeated")
            seen_paths.add(rel)
            path = _safe_under(root, rel)
            content = _document(path, max_bytes=MAX_DOC_BYTES)
            total += len(content)
            if total > MAX_TOTAL_BYTES:
                raise SDKStudyError("SDK evidence exceeds total byte budget")
            expected = _digest(doc["sha256"], "SDK document digest")
            if _sha(content) != expected:
                raise SDKStudyError("SDK documentation changed since operator pin")
            if admitted:
                try:
                    document_text = content.decode("utf-8")
                except UnicodeDecodeError as exc:
                    raise SDKStudyError("training document must be UTF-8") from exc
                if ("-----BEGIN PRIVATE KEY-----" in document_text
                        or "\x00" in document_text):
                    raise SDKStudyError("SDK documentation contains prohibited secret/binary content")
            if expected in entries:
                raise SDKStudyError("SDK source digest reused across declarations")
            entries[expected] = {
                "sdk_id": ident, "sdk_kind": kind, "version": version,
                "document": rel, "source_project_id": "sdk." + ident,
                "rights": rights, "trainable": admitted,
                "target_ids": tuple(targets),
            }
    return {
        "schema_version": SDK_SCHEMA,
        "manifest_sha256": _sha(raw),
        "sdks": len(sdk_ids),
        "pinned_documents": len(entries),
        "admitted_documents": sum(bool(d["trainable"]) for d in entries.values()),
        "training_executed": False,
        "rights_declarations_not_independent_proof": True,
    }, entries


def _checked_rows(review_file: Path, sources: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    raw = _document(review_file, max_bytes=16 * 1024 * 1024)
    rows: list[dict[str, Any]] = []
    available = {m["module_id"]: m for m in generate_modules()}
    seen_ids: set[str] = set()
    for line in raw.splitlines():
        if not line or len(line) > 24000 or len(rows) >= MAX_REVIEW:
            raise SDKStudyError("SDK reviewed rows invalid or over capacity")
        row = _strict_object(line)
        if row.get("schema_version") != REVIEW_SCHEMA or row.get("quality_approved") is not True:
            raise SDKStudyError("SDK example requires human quality approval")
        reviewer, note = row.get("quality_reviewer_id"), row.get("quality_review_note")
        if (not isinstance(reviewer, str) or len(reviewer.strip()) < 3
                or not isinstance(note, str) or len(note.strip()) < 24):
            raise SDKStudyError("SDK quality review needs identifiable reviewer and evidence")
        identity = _id(row.get("id"), "example id")
        if identity in seen_ids:
            raise SDKStudyError("duplicate SDK example")
        seen_ids.add(identity)
        source = sources.get(_digest(row.get("source_sha256"), "source_sha256"))
        if source is None or not source["trainable"] or row.get("sdk_id") != source["sdk_id"]:
            raise SDKStudyError("SDK example source not admitted for training")
        module_id = row.get("module_id")
        if module_id not in available or available[module_id]["domain"] not in ("coding", "gaming"):
            raise SDKStudyError("SDK example must use a registered coding or gaming specialist")
        split = row.get("split")
        if split not in ("train", "heldout"):
            raise SDKStudyError("SDK example split must be train or heldout")
        for field, low, high in (("prompt", 24, 4096), ("answer", 24, 12000)):
            value = row.get(field)
            if (not isinstance(value, str) or not low <= len(value.strip()) <= high
                    or "\nJeeves:" in value or "\nUser:" in value):
                raise SDKStudyError("SDK reviewed prompt or answer outside safe limits")
        rights = source["rights"]
        rows.append({
            "id": identity,
            "source_project_id": source["source_project_id"],
            "split": split, "module_id": module_id,
            "prompt": row["prompt"].strip(),
            "answer": row["answer"].strip(),
            "rights": {
                "training_permitted": True,
                "human_reviewed": True,
                "source_ref": "sdk:" + source["sdk_id"] + ":" + row["source_sha256"],
                "rights_basis": rights["rights_basis"],
            },
        })
    if not rows:
        raise SDKStudyError("reviewed SDK dataset is empty")
    return rows


def _save_exclusive(path: Path, raw: bytes) -> None:
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def extend_multidomain(
    sources_manifest: Path, reviewed_file: Path, base_manifest: Path,
    destination: Path, *, prefix: str, review_id: str,
) -> dict[str, Any]:
    """Publish a new, validated corpus snapshot. Never change base or live model."""
    _id(prefix, "output prefix")
    _id(review_id, "rights review ID")
    if (destination.is_symlink() or not destination.is_dir()
            or any(p.is_symlink() for p in (sources_manifest, reviewed_file, base_manifest))):
        raise SDKStudyError("SDK input/output must be regular operator-owned paths")
    if destination.resolve() in {p.resolve().parent for p in (sources_manifest, reviewed_file, base_manifest)}:
        raise SDKStudyError("SDK output must be separate from source folders")
    # This call validates the entire base contract, including heldout separation.
    load_multidomain_corpus(base_manifest)
    source_receipt, source_map = validate_sources(sources_manifest)
    sdk_rows = _checked_rows(reviewed_file, source_map)
    base = _strict_object(_document(base_manifest, max_bytes=64 * 1024))
    source_root = base_manifest.parent
    original: dict[str, tuple[dict[str, Any], ...]] = {}
    for split in ("train", "heldout"):
        name = base[split + "_file"]
        original[split] = _rows(
            source_root / name, base[split + "_sha256"], split,
            {m["module_id"] for m in generate_modules()},
        )
    combined = {
        split: [*original[split], *(r for r in sdk_rows if r["split"] == split)]
        for split in ("train", "heldout")
    }
    _split_guard(tuple(combined["train"]), tuple(combined["heldout"]))
    if len(combined["train"]) > 4096 or len(combined["heldout"]) > 4096:
        raise SDKStudyError("SDK additions exceed multidomain split bounds")
    names = {
        "train": prefix + "-train.jsonl",
        "heldout": prefix + "-heldout.jsonl",
        "manifest": prefix + "-manifest.json",
    }
    for name in names.values():
        if (destination / name).exists() or (destination / name).is_symlink():
            raise SDKStudyError("SDK version already published; overwrite forbidden")
    reviewed_digest = _sha(_document(reviewed_file, max_bytes=16 * 1024 * 1024))
    with tempfile.TemporaryDirectory(prefix=".sdk-staging-", dir=destination) as temp:
        stage = Path(temp)
        digests = {}
        for split in ("train", "heldout"):
            blob = b"".join(
                (json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
                 + "\n").encode("utf-8") for row in combined[split]
            )
            digests[split] = _sha(blob)
            _save_exclusive(stage / names[split], blob)
        manifest = {
            "schema_version": TRAIN_SCHEMA,
            "rights_reviewed": True,
            "review_id": review_id,
            "train_file": names["train"],
            "train_sha256": digests["train"],
            "heldout_file": names["heldout"],
            "heldout_sha256": digests["heldout"],
            "parent_manifest_sha256": _sha(_document(base_manifest, max_bytes=64 * 1024)),
            "sdk_source_manifest_sha256": source_receipt["manifest_sha256"],
            "sdk_reviewed_examples_sha256": reviewed_digest,
        }
        _save_exclusive(stage / names["manifest"],
                        (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode())
        _, _, proof = load_multidomain_corpus(stage / names["manifest"])
        published: list[Path] = []
        try:
            # Exclusive hard links avoid replacing prior data after concurrent runs.
            # Manifest publishes LAST; consumers must start from its checksum.
            for split in ("train", "heldout", "manifest"):
                dst = destination / names[split]
                os.link(stage / names[split], dst)
                published.append(dst)
        except BaseException:
            for path in published:
                path.unlink(missing_ok=True)
            raise
    return {
        "status": "approved_sdk_corpus_published_candidate_only",
        "manifest": str((destination / names["manifest"]).resolve()),
        "manifest_sha256": _sha(_document(destination / names["manifest"], max_bytes=64 * 1024)),
        "sdk_sources": source_receipt,
        "sdk_reviewed_rows": len(sdk_rows),
        "training_examples": len(combined["train"]),
        "heldout_examples": len(combined["heldout"]),
        "validated_dataset_receipt": proof,
        "checkpoint_touched": False,
        "model_training_executed": False,
        "automatic_promotion": False,
    }
