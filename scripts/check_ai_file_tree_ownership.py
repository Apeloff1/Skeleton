#!/usr/bin/env python3
"""Independent ownership-graph verification for the governed AI file tree.

VOL-051 Repository Architecture requires one machine-readable ownership graph
and a relocation parity gate. The canonical migration manifest already owns
the relocation topology; this verifier derives a deterministic ownership graph
from that manifest without importing the parity validator, then proves every
tracked file under skeleton/ai has exactly one effective governed owner.

The existing scripts/check_ai_file_tree.py remains the relocation/parity
authority and is executed separately by the VOL-051 workflow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = Path("machine/ai_file_tree.json")
ARCHITECTURE = Path("machine/architecture.json")
CANONICAL_ROOT = "skeleton/ai"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class OwnershipVerificationError(RuntimeError):
    """Raised when an ownership authority cannot be loaded or inspected."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OwnershipVerificationError(f"cannot load {path}") from exc
    if not isinstance(value, dict):
        raise OwnershipVerificationError(f"{path} must contain an object")
    return value


def _digest_json(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_repo_path(value: object, *, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label}: path must be a non-empty string")
        return None
    if "\\" in value:
        errors.append(f"{label}: repository path must use POSIX separators")
        return None
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or ".." in candidate.parts or "." in candidate.parts:
        errors.append(f"{label}: repository path must be normalized and relative")
        return None
    normalized = candidate.as_posix().rstrip("/")
    if normalized != value.rstrip("/"):
        errors.append(f"{label}: repository path is not normalized")
        return None
    return normalized


def _within(path_value: str, root_value: str) -> bool:
    root = root_value.rstrip("/")
    return path_value == root or path_value.startswith(root + "/")


def _overlay_paths(mapping: Mapping[str, Any]) -> set[str]:
    destination = mapping.get("destination")
    overlays = mapping.get("overlay_children")
    if not isinstance(destination, str) or not isinstance(overlays, list):
        return set()
    result: set[str] = set()
    for value in overlays:
        if (
            isinstance(value, str)
            and value
            and not value.startswith("/")
            and ".." not in PurePosixPath(value).parts
        ):
            result.add(f"{destination.rstrip('/')}/{value.rstrip('/')}")
    return result


def validate_manifest_structure(
    manifest: Mapping[str, Any],
    *,
    root: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Validate ownership declarations and return normalized owner sets."""
    errors: list[str] = []
    repository_root = ROOT if root is None else root

    if manifest.get("schema_version") != 1:
        errors.append("AI file-tree schema_version must equal 1")
    if manifest.get("canonical_root") != CANONICAL_ROOT:
        errors.append(f"canonical_root must equal {CANONICAL_ROOT}")
    if not FULL_SHA.fullmatch(str(manifest.get("baseline_git_sha", ""))):
        errors.append("baseline_git_sha must be a full Git SHA")

    raw_mappings = manifest.get("mappings")
    if not isinstance(raw_mappings, list) or not raw_mappings:
        errors.append("mappings must be a non-empty list")
        raw_mappings = []

    raw_native = manifest.get("native_ai_owners")
    if not isinstance(raw_native, list) or not raw_native:
        errors.append("native_ai_owners must be a non-empty list")
        raw_native = []

    mappings: list[dict[str, Any]] = []
    native: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_destinations: set[str] = set()
    seen_native_paths: set[str] = set()

    for raw in raw_mappings:
        if not isinstance(raw, dict):
            errors.append("mapping declaration must be an object")
            continue
        owner_id = raw.get("id")
        if not isinstance(owner_id, str) or not owner_id.startswith("AIFT-"):
            errors.append(f"invalid mapping id: {owner_id!r}")
            continue
        if owner_id in seen_ids:
            errors.append(f"duplicate ownership id: {owner_id}")
        seen_ids.add(owner_id)

        source = _normalize_repo_path(
            raw.get("source"),
            label=f"{owner_id}.source",
            errors=errors,
        )
        destination = _normalize_repo_path(
            raw.get("destination"),
            label=f"{owner_id}.destination",
            errors=errors,
        )
        if source is None or destination is None:
            continue
        if not _within(destination, CANONICAL_ROOT) or destination == CANONICAL_ROOT:
            errors.append(f"{owner_id}: destination must be below {CANONICAL_ROOT}")
        if destination in seen_destinations:
            errors.append(f"duplicate mapping destination: {destination}")
        seen_destinations.add(destination)

        kind = raw.get("kind")
        if kind not in {"file", "tree"}:
            errors.append(f"{owner_id}: kind must be file or tree")
            continue
        if not isinstance(raw.get("source_disposition"), str) or not raw.get("source_disposition"):
            errors.append(f"{owner_id}: source_disposition is required")
        if not FULL_SHA.fullmatch(str(raw.get("source_git_object_sha", ""))):
            errors.append(f"{owner_id}: source_git_object_sha must be a full SHA")
        if root is not None:
            if kind == "file":
                if not (repository_root / source).is_file():
                    errors.append(f"{owner_id}: source file missing: {source}")
                if not (repository_root / destination).is_file():
                    errors.append(f"{owner_id}: destination file missing: {destination}")
            else:
                if not (repository_root / source).is_dir():
                    errors.append(f"{owner_id}: source tree missing: {source}")
                if not (repository_root / destination).is_dir():
                    errors.append(f"{owner_id}: destination tree missing: {destination}")

        mappings.append(
            {
                "id": owner_id,
                "source": source,
                "destination": destination,
                "kind": kind,
                "parity_mode": raw.get("parity_mode", "exact"),
                "source_disposition": raw.get("source_disposition"),
                "overlay_paths": sorted(_overlay_paths(raw)),
            }
        )

    for raw in raw_native:
        if not isinstance(raw, dict):
            errors.append("native ownership declaration must be an object")
            continue
        owner_id = raw.get("id")
        if not isinstance(owner_id, str) or not owner_id.startswith("AIFT-NATIVE-"):
            errors.append(f"invalid native owner id: {owner_id!r}")
            continue
        if owner_id in seen_ids:
            errors.append(f"duplicate ownership id: {owner_id}")
        seen_ids.add(owner_id)

        path_value = _normalize_repo_path(
            raw.get("path"),
            label=f"{owner_id}.path",
            errors=errors,
        )
        if path_value is None:
            continue
        if not _within(path_value, CANONICAL_ROOT):
            errors.append(f"{owner_id}: native path escapes {CANONICAL_ROOT}")
        if path_value in seen_native_paths:
            errors.append(f"duplicate native owner path: {path_value}")
        seen_native_paths.add(path_value)

        kind = raw.get("kind")
        if kind not in {"file", "tree"}:
            errors.append(f"{owner_id}: kind must be file or tree")
            continue
        if raw.get("ownership_mode") != "canonical_native":
            errors.append(f"{owner_id}: ownership_mode must be canonical_native")
        if not isinstance(raw.get("residual_only"), bool):
            errors.append(f"{owner_id}: residual_only must be bool")
        if root is not None:
            target = repository_root / path_value
            if kind == "file" and not target.is_file():
                errors.append(f"{owner_id}: native file missing: {path_value}")
            if kind == "tree" and not target.is_dir():
                errors.append(f"{owner_id}: native tree missing: {path_value}")

        native.append(
            {
                "id": owner_id,
                "path": path_value,
                "kind": kind,
                "residual_only": bool(raw.get("residual_only")),
            }
        )

    for owner in native:
        native_path = owner["path"]
        for mapping in mappings:
            destination = mapping["destination"]
            if not _within(native_path, destination):
                continue
            if any(
                _within(native_path, overlay)
                for overlay in mapping["overlay_paths"]
            ):
                continue
            errors.append(
                f"{owner['id']}: native owner overlaps mapping {mapping['id']} "
                "without an explicit overlay"
            )

    return mappings, native, errors


def _mapping_matches(path_value: str, owner: Mapping[str, Any]) -> bool:
    destination = str(owner["destination"])
    if owner["kind"] == "file":
        return path_value == destination
    return _within(path_value, destination)


def _native_matches(path_value: str, owner: Mapping[str, Any]) -> bool:
    root = str(owner["path"])
    if owner["kind"] == "file":
        return path_value == root
    return _within(path_value, root)


def effective_owner(
    path_value: str,
    mappings: Sequence[Mapping[str, Any]],
    native: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Return the unique most-specific owner for one AI-tree path."""
    candidates: list[tuple[int, int, str, dict[str, Any]]] = []
    for owner in mappings:
        if _mapping_matches(path_value, owner):
            root_value = str(owner["destination"])
            candidates.append((len(root_value), 0, str(owner["id"]), dict(owner)))
    for owner in native:
        if _native_matches(path_value, owner):
            root_value = str(owner["path"])
            candidates.append((len(root_value), 1, str(owner["id"]), dict(owner)))
    if not candidates:
        return None, [f"unowned AI-tree path: {path_value}"]

    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    best = candidates[0]
    tied = [item for item in candidates if item[:2] == best[:2]]
    if len(tied) > 1:
        ids = ", ".join(sorted(item[2] for item in tied))
        return None, [f"ambiguous ownership for {path_value}: {ids}"]
    result = best[3]
    result["owner_kind"] = "native" if best[1] == 1 else "mapping"
    result["owner_root"] = result.get("path") or result.get("destination")
    return result, []


def build_ownership_graph(
    manifest: Mapping[str, Any],
    tracked_paths: Iterable[str],
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    mappings, native, errors = validate_manifest_structure(manifest, root=root)
    rows: list[dict[str, str]] = []
    owner_file_counts: dict[str, int] = {}

    normalized_paths: list[str] = []
    for raw_path in tracked_paths:
        local_errors: list[str] = []
        normalized = _normalize_repo_path(
            raw_path,
            label="tracked_path",
            errors=local_errors,
        )
        errors.extend(local_errors)
        if normalized is None:
            continue
        if not _within(normalized, CANONICAL_ROOT):
            errors.append(f"tracked path escapes {CANONICAL_ROOT}: {normalized}")
            continue
        normalized_paths.append(normalized)

    for path_value in sorted(set(normalized_paths)):
        owner, owner_errors = effective_owner(path_value, mappings, native)
        errors.extend(owner_errors)
        if owner is None:
            continue
        owner_id = str(owner["id"])
        owner_file_counts[owner_id] = owner_file_counts.get(owner_id, 0) + 1
        rows.append(
            {
                "path": path_value,
                "owner_id": owner_id,
                "owner_kind": str(owner["owner_kind"]),
                "owner_root": str(owner["owner_root"]),
            }
        )

    for owner in mappings:
        owner_id = str(owner["id"])
        if owner_file_counts.get(owner_id, 0) == 0:
            errors.append(
                f"declared mapping owns no tracked AI-tree files: {owner_id}"
            )
    for owner in native:
        owner_id = str(owner["id"])
        if (
            owner_file_counts.get(owner_id, 0) == 0
            and not owner.get("residual_only")
        ):
            errors.append(
                f"declared native owner owns no tracked AI-tree files: {owner_id}"
            )

    direct_roots = sorted(
        {
            "/".join(row["path"].split("/")[:3])
            for row in rows
            if row["path"].startswith(CANONICAL_ROOT + "/")
        }
    )
    graph_identity = [
        (row["path"], row["owner_kind"], row["owner_id"], row["owner_root"])
        for row in rows
    ]
    unique_errors = sorted(set(errors))
    return {
        "tracked_file_count": len(set(normalized_paths)),
        "owned_file_count": len(rows),
        "mapping_owner_count": len(mappings),
        "native_owner_count": len(native),
        "direct_ai_roots": direct_roots,
        "owner_file_counts": dict(sorted(owner_file_counts.items())),
        "graph_digest": _digest_json(graph_identity),
        "errors": unique_errors,
        "valid": not unique_errors,
    }


def _tracked_ai_files(root: Path) -> list[str]:
    try:
        output = subprocess.run(
            ["git", "ls-files", "-z", "--", CANONICAL_ROOT],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise OwnershipVerificationError(
            "cannot enumerate tracked AI-tree files"
        ) from exc
    return sorted(path for path in output.split("\0") if path)


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    manifest_path = root / MANIFEST
    architecture_path = root / ARCHITECTURE
    manifest = _load_json(manifest_path)
    architecture = _load_json(architecture_path)
    tracked = _tracked_ai_files(root)
    graph = build_ownership_graph(manifest, tracked, root=root)
    errors = list(graph["errors"])

    sources = architecture.get("sources")
    if (
        not isinstance(sources, dict)
        or sources.get("ai_file_tree") != MANIFEST.as_posix()
    ):
        errors.append(
            "architecture authority does not bind machine/ai_file_tree.json"
        )
    objectives = architecture.get("objectives")
    if (
        not isinstance(objectives, list)
        or "machine-readable ownership and change routing" not in objectives
    ):
        errors.append(
            "architecture objectives lost machine-readable ownership routing"
        )

    authorities = manifest.get("authorities")
    if (
        not isinstance(authorities, dict)
        or authorities.get("validator") != "scripts/check_ai_file_tree.py"
    ):
        errors.append("AI file-tree parity validator authority drifted")

    errors = sorted(set(errors))
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "verifier": "independent-ai-file-tree-ownership-v1",
        "volume": "VOL-051",
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "manifest_path": MANIFEST.as_posix(),
        "manifest_digest": _digest_file(manifest_path),
        "architecture_digest": _digest_file(architecture_path),
        "canonical_root": CANONICAL_ROOT,
        "tracked_file_count": graph["tracked_file_count"],
        "owned_file_count": graph["owned_file_count"],
        "mapping_owner_count": graph["mapping_owner_count"],
        "native_owner_count": graph["native_owner_count"],
        "direct_ai_roots": graph["direct_ai_roots"],
        "owner_file_counts": graph["owner_file_counts"],
        "ownership_graph_digest": graph["graph_digest"],
        "parity_validator": "scripts/check_ai_file_tree.py",
        "errors": errors,
        "valid": not errors,
    }
    receipt["receipt_digest"] = _digest_json(receipt)
    return receipt


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-out", type=Path)
    parser.add_argument("--print-evidence", action="store_true")
    args = parser.parse_args(argv)

    try:
        receipt = verify_repository(ROOT)
    except OwnershipVerificationError as exc:
        receipt = {
            "schema_version": 1,
            "verifier": "independent-ai-file-tree-ownership-v1",
            "volume": "VOL-051",
            "head_sha": (
                os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
                or os.environ.get("GITHUB_SHA", "").strip()
                or "unknown"
            ),
            "errors": [str(exc)],
            "valid": False,
        }
        receipt["receipt_digest"] = _digest_json(receipt)

    rendered = json.dumps(receipt, sort_keys=True, indent=2)
    if args.evidence_out is not None:
        args.evidence_out.parent.mkdir(parents=True, exist_ok=True)
        args.evidence_out.write_text(rendered + "\n", encoding="utf-8")
    if args.print_evidence:
        print(rendered)
    elif receipt["valid"]:
        print(
            "VOL-051 AI file-tree ownership verification: OK "
            f"({receipt['receipt_digest']})"
        )
    else:
        print("VOL-051 AI file-tree ownership verification: FAIL")
        for error in receipt.get("errors", []):
            print(f"- {error}")

    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
