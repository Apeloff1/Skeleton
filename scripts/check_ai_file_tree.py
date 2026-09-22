#!/usr/bin/env python3
"""Fail-closed validation for the canonical AI file-tree migration."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "machine" / "ai_file_tree.json"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
MIRROR_STATES = {"staged_mirror", "cutover_pending"}
ALLOWED_SIGNATURE_METHODS = {"github_identity", "git_gpg", "git_ssh", "sigstore", "ci_oidc"}


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _tree_files(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def _validate_facade(
    destination: Path,
    *,
    required_import: str,
    label: str,
) -> list[str]:
    errors: list[str] = []
    try:
        source = destination.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"{label}: cannot read compatibility facade: {exc}"]
    if required_import not in source:
        errors.append(f"{label}: compatibility facade missing required import {required_import!r}")
    forbidden_markers = (
        "OPENAI_API_KEY",
        "SKELETON_OPENAI_API_KEY",
        "api.openai.com",
        "from openai import",
        "import openai",
    )
    hits = [marker for marker in forbidden_markers if marker in source]
    if hits:
        errors.append(
            f"{label}: compatibility facade owns credential/provider markers: {', '.join(hits)}"
        )
    return errors


def _compare(
    source: Path,
    destination: Path,
    *,
    parity_exceptions: dict[str, dict[str, object]] | None = None,
) -> list[str]:
    if source.is_symlink() or destination.is_symlink():
        return [f"symlink mapping forbidden: {source} -> {destination}"]
    if source.is_file() != destination.is_file():
        return [f"mapping kind mismatch: {source} -> {destination}"]
    if source.is_file():
        return [] if _digest(source) == _digest(destination) else [
            f"file drift: {source.relative_to(ROOT)} != {destination.relative_to(ROOT)}"
        ]

    exceptions = parity_exceptions or {}
    src = _tree_files(source)
    dst = _tree_files(destination)
    if set(src) != set(dst):
        missing = sorted(set(src) - set(dst))
        extra = sorted(set(dst) - set(src))
        return [
            f"tree membership drift: {source.relative_to(ROOT)} -> {destination.relative_to(ROOT)} "
            f"missing={missing[:10]} extra={extra[:10]}"
        ]

    errors: list[str] = []
    for rel in sorted(src):
        exception = exceptions.get(rel)
        if exception:
            if exception.get("mode") != "compatibility_facade":
                errors.append(f"{source.relative_to(ROOT)}/{rel}: unknown parity exception mode")
                continue
            required_import = exception.get("facade_required_import")
            if not isinstance(required_import, str) or not required_import:
                errors.append(f"{source.relative_to(ROOT)}/{rel}: facade exception missing required import")
                continue
            errors.extend(
                _validate_facade(
                    dst[rel],
                    required_import=required_import,
                    label=f"{source.relative_to(ROOT)}/{rel}",
                )
            )
            continue
        if _digest(src[rel]) != _digest(dst[rel]):
            errors.append(f"tree content drift: {source.relative_to(ROOT)}/{rel}")
    return errors


def validate() -> list[str]:
    errors: list[str] = []
    required = [
        MANIFEST,
        ROOT / "docs/plan/AI_FILE_TREE_MIGRATION.md",
        ROOT / "skeleton/ai/__init__.py",
        ROOT / "skeleton/testing/test_ai_file_tree.py",
    ]
    for path in required:
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT)}")
    if errors:
        return errors

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1:
        errors.append("schema_version must equal 1")
    if data.get("status") not in MIRROR_STATES | {"cutover_complete"}:
        errors.append("unknown migration status")
    if data.get("canonical_root") != "skeleton/ai":
        errors.append("canonical_root must be skeleton/ai")
    if not FULL_SHA.fullmatch(str(data.get("baseline_git_sha", ""))):
        errors.append("baseline_git_sha must be a full SHA")

    for key, value in data.get("authorities", {}).items():
        if key == "validator":
            pass
        if not isinstance(value, str) or not (ROOT / value).exists():
            errors.append(f"authority missing or unresolved: {key}")

    mappings = data.get("mappings")
    if not isinstance(mappings, list) or len(mappings) < 10:
        return errors + ["mappings must contain the governed consolidation set"]

    seen_ids: set[str] = set()
    seen_destinations: set[str] = set()
    has_jeeves = False
    has_build = False
    for item in mappings:
        mid = item.get("id", "?")
        src = item.get("source")
        dst = item.get("destination")
        if not isinstance(mid, str) or not mid:
            errors.append("mapping missing id")
            continue
        if mid in seen_ids:
            errors.append(f"duplicate mapping id: {mid}")
        seen_ids.add(mid)
        if not isinstance(src, str) or not isinstance(dst, str):
            errors.append(f"{mid}: source/destination must be strings")
            continue
        if dst in seen_destinations:
            errors.append(f"{mid}: duplicate destination {dst}")
        seen_destinations.add(dst)
        if not dst.startswith("skeleton/ai/"):
            errors.append(f"{mid}: destination escapes skeleton/ai")
        if not FULL_SHA.fullmatch(str(item.get("source_git_object_sha", ""))):
            errors.append(f"{mid}: source_git_object_sha must be a full SHA")
        if not item.get("work_package_refs"):
            errors.append(f"{mid}: missing work_package_refs")

        source = ROOT / src
        destination = ROOT / dst
        if not source.exists():
            errors.append(f"{mid}: missing source {src}")
            continue
        if not destination.exists():
            errors.append(f"{mid}: missing destination {dst}")
            continue
        if data.get("status") in MIRROR_STATES:
            parity_mode = item.get("parity_mode", "exact")
            if parity_mode == "compatibility_facade":
                required_import = item.get("facade_required_import")
                if not isinstance(required_import, str) or not required_import:
                    errors.append(f"{mid}: compatibility facade missing required import contract")
                elif not destination.is_file():
                    errors.append(f"{mid}: compatibility facade destination must be a file")
                else:
                    errors.extend(
                        _validate_facade(
                            destination,
                            required_import=required_import,
                            label=mid,
                        )
                    )
            elif parity_mode == "exact":
                raw_exceptions = item.get("parity_exceptions", [])
                exceptions: dict[str, dict[str, object]] = {}
                if not isinstance(raw_exceptions, list):
                    errors.append(f"{mid}: parity_exceptions must be a list")
                else:
                    for exception in raw_exceptions:
                        if not isinstance(exception, dict):
                            errors.append(f"{mid}: parity exception must be an object")
                            continue
                        rel = exception.get("path")
                        if not isinstance(rel, str) or not rel or rel.startswith("/") or ".." in Path(rel).parts:
                            errors.append(f"{mid}: invalid parity exception path")
                            continue
                        if rel in exceptions:
                            errors.append(f"{mid}: duplicate parity exception {rel}")
                            continue
                        exceptions[rel] = exception
                errors.extend(_compare(source, destination, parity_exceptions=exceptions))
            else:
                errors.append(f"{mid}: unknown parity_mode {parity_mode!r}")

        has_jeeves |= src == "skeleton/jeeves" and dst == "skeleton/ai/agents/jeeves"
        has_build |= src == "core/shift_supervisor" and dst == "skeleton/ai/build/shift_supervisor"

    if not has_jeeves:
        errors.append("Jeeves engine mapping is mandatory")
    if not has_build:
        errors.append("shift-supervisor build/planning mapping is mandatory")

    forbidden = data.get("promotion_policy", {}).get("forbidden", [])
    if "marking AIQ/work-package completion from file relocation alone" not in forbidden:
        errors.append("relocation must not create completion authority")

    impl = data.get("implementation_signoff", {})
    if impl.get("signed"):
        if impl.get("signature_method") not in ALLOWED_SIGNATURE_METHODS:
            errors.append("implementation signoff uses an unbound signature method")
        if not FULL_SHA.fullmatch(str(impl.get("git_sha", ""))):
            errors.append("signed implementation requires full git SHA")
        for key in ("signer_id", "signed_at_utc", "evidence_refs", "statement"):
            if not impl.get(key):
                errors.append(f"signed implementation missing {key}")

    verification = data.get("verification_signoff", {})
    if verification.get("signed"):
        if verification.get("signature_method") not in ALLOWED_SIGNATURE_METHODS:
            errors.append("verification signoff uses an unbound signature method")
        if verification.get("signer_id") == impl.get("signer_id"):
            errors.append("independent verifier must differ from implementation signer")
    if data.get("status") == "cutover_complete" and not (
        impl.get("signed") and verification.get("signed")
    ):
        errors.append("cutover_complete requires implementation and independent verification signoffs")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("AI file tree: FAIL")
        for error in errors:
            print(f" - {error}")
        return 1
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    print(f"AI file tree: OK ({len(data['mappings'])} governed mappings, status={data['status']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
