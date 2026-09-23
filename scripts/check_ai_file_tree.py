#!/usr/bin/env python3
"""Fail-closed validation for the canonical AI file-tree migration."""
from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "machine" / "ai_file_tree.json"
MASTER_PLAN = ROOT / "machine" / "ai_master_plan.json"
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
    """Return governed source members without runtime/generated filesystem noise.

    Repository migration parity is defined over Git-tracked source objects, not
    transient files produced by imports/tests such as __pycache__/*.pyc.
    Temporary paths outside the repository use a filtered filesystem fallback.
    """
    try:
        relative_root = root.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return {
            path.relative_to(root).as_posix(): path
            for path in root.rglob("*")
            if (
                path.is_file()
                and not path.is_symlink()
                and "__pycache__" not in path.parts
                and path.suffix not in {".pyc", ".pyo"}
            )
        }

    try:
        tracked = subprocess.run(
            ["git", "ls-files", "-z", "--", relative_root],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(
            f"cannot enumerate tracked migration tree {relative_root}: {exc}"
        ) from exc

    result: dict[str, Path] = {}
    root_prefix = relative_root.rstrip("/") + "/"
    for repo_relative in tracked.split("\0"):
        if not repo_relative or repo_relative == relative_root:
            continue
        if not repo_relative.startswith(root_prefix):
            continue
        path = ROOT / repo_relative
        if not path.is_file() or path.is_symlink():
            continue
        rel = repo_relative[len(root_prefix):]
        result[rel] = path
    return result


def _python_semantically_equal(source: Path, destination: Path) -> bool:
    try:
        source_tree = ast.parse(source.read_text(encoding="utf-8"))
        destination_tree = ast.parse(destination.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return False
    return ast.dump(source_tree, include_attributes=False) == ast.dump(
        destination_tree,
        include_attributes=False,
    )


def _content_equivalent(source: Path, destination: Path) -> bool:
    if _digest(source) == _digest(destination):
        return True
    if source.suffix == ".py" and destination.suffix == ".py":
        return _python_semantically_equal(source, destination)
    return False


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
    overlay_children: set[str] | None = None,
) -> list[str]:
    if source.is_symlink() or destination.is_symlink():
        return [f"symlink mapping forbidden: {source} -> {destination}"]
    if source.is_file() != destination.is_file():
        return [f"mapping kind mismatch: {source} -> {destination}"]
    if source.is_file():
        return [] if _content_equivalent(source, destination) else [
            f"file semantic/content drift: {source.relative_to(ROOT)} != {destination.relative_to(ROOT)}"
        ]

    exceptions = parity_exceptions or {}
    overlays = overlay_children or set()
    src = _tree_files(source)
    dst = _tree_files(destination)
    governed_dst = {
        rel: path
        for rel, path in dst.items()
        if not any(rel == overlay or rel.startswith(overlay + "/") for overlay in overlays)
    }
    if set(src) != set(governed_dst):
        missing = sorted(set(src) - set(governed_dst))
        extra = sorted(set(governed_dst) - set(src))
        return [
            f"tree membership drift: {source.relative_to(ROOT)} -> {destination.relative_to(ROOT)} "
            f"missing={missing[:10]} extra={extra[:10]} overlays={sorted(overlays)}"
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
        if not _content_equivalent(src[rel], governed_dst[rel]):
            errors.append(f"tree semantic/content drift: {source.relative_to(ROOT)}/{rel}")
    return errors



def _planned_implementation_sources(value: object, key_path: tuple[str, ...] = ()) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            result.update(_planned_implementation_sources(child, key_path + (str(key),)))
        return result
    if isinstance(value, list):
        for child in value:
            result.update(_planned_implementation_sources(child, key_path))
        return result
    if (
        isinstance(value, str)
        and "implementation_paths" in key_path
        and value.startswith("planned:skeleton/")
    ):
        result.add(value.removeprefix("planned:").rstrip("/"))
    return result


def _source_exists(relative: str) -> bool:
    path = ROOT / relative
    return path.exists()


def validate() -> list[str]:
    errors: list[str] = []
    required = [
        MANIFEST,
        ROOT / "docs/plan/AI_FILE_TREE_MIGRATION.md",
        ROOT / "skeleton/ai/__init__.py",
        ROOT / "skeleton/testing/test_ai_file_tree.py",
        ROOT / "machine/ai_master_plan.json",
        ROOT / "machine/ai_app_construction.json",
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

    move_tag_contract = data.get("move_tag_contract")
    if not isinstance(move_tag_contract, dict):
        errors.append("move_tag_contract must be an object")
    else:
        if move_tag_contract.get("global_state") != "prepared_not_cutover_authorized":
            errors.append("move_tag_contract global_state must remain prepared_not_cutover_authorized")
        required_tags = move_tag_contract.get("required_tags")
        if required_tags != ["ai-tree:mapped", "migration:staged-mirror"]:
            errors.append("move_tag_contract required_tags drifted")
        cutover_tags = move_tag_contract.get("cutover_tags")
        if not isinstance(cutover_tags, dict) or set(cutover_tags) != {
            "cutover:parity-ready",
            "cutover:owner-sensitive",
            "cutover:quarantine",
            "cutover:merge-required",
        }:
            errors.append("move_tag_contract cutover tag set drifted")
        batches = move_tag_contract.get("batches")
        if not isinstance(batches, dict) or set(batches) != {
            "B1-core-runtime",
            "B2-domain-build",
            "B3-owner-sensitive",
            "B3-compat-convergence",
            "B4-research-quarantine",
        }:
            errors.append("move_tag_contract batch set drifted")

    try:
        master_plan = json.loads(MASTER_PLAN.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot parse AI master plan for file-tree coverage: {exc}")
        master_plan = {}

    mapped_sources = {
        item.get("source")
        for item in mappings
        if isinstance(item, dict) and isinstance(item.get("source"), str)
    }
    for planned_source in sorted(_planned_implementation_sources(master_plan)):
        if _source_exists(planned_source) and planned_source not in mapped_sources:
            errors.append(
                "extant planned implementation path is not governed by AI file tree: "
                f"{planned_source}"
            )

    declared_destinations = {
        item.get("destination")
        for item in mappings
        if isinstance(item, dict) and isinstance(item.get("destination"), str)
    }

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

        move_tags = item.get("move_tags")
        if not isinstance(move_tags, list) or len(move_tags) != 3:
            errors.append(f"{mid}: move_tags must contain exactly three governed tags")
            move_tags = []
        if "ai-tree:mapped" not in move_tags or "migration:staged-mirror" not in move_tags:
            errors.append(f"{mid}: missing mandatory AI-tree migration tags")
        cutover = [
            tag for tag in move_tags
            if isinstance(tag, str) and tag.startswith("cutover:")
        ]
        if len(cutover) != 1:
            errors.append(f"{mid}: exactly one cutover tag is required")
            cutover_tag = None
        else:
            cutover_tag = cutover[0]
        parity_sensitive = (
            item.get("parity_mode") == "compatibility_facade"
            or bool(item.get("parity_exceptions"))
        )
        quarantine = dst.startswith("skeleton/ai/research/")
        compat_convergence = dst.startswith("skeleton/ai/compat/")
        expected_cutover = (
            "cutover:quarantine"
            if quarantine
            else "cutover:merge-required"
            if compat_convergence
            else "cutover:owner-sensitive"
            if parity_sensitive
            else "cutover:parity-ready"
        )
        if cutover_tag != expected_cutover:
            errors.append(
                f"{mid}: cutover tag {cutover_tag!r} does not match expected {expected_cutover!r}"
            )
        expected_batch = (
            "B4-research-quarantine"
            if quarantine
            else "B3-compat-convergence"
            if compat_convergence
            else "B3-owner-sensitive"
            if parity_sensitive
            else "B2-domain-build"
            if (
                dst.startswith("skeleton/ai/build/")
                or dst.startswith("skeleton/ai/simulation/")
                or dst.startswith("skeleton/ai/forge/")
            )
            else "B1-core-runtime"
        )
        if item.get("move_batch") != expected_batch:
            errors.append(
                f"{mid}: move_batch {item.get('move_batch')!r} does not match {expected_batch!r}"
            )
        if not isinstance(item.get("source_disposition"), str) or not item.get("source_disposition"):
            errors.append(f"{mid}: source_disposition is required")

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
                raw_overlays = item.get("overlay_children", [])
                overlays: set[str] = set()
                if not isinstance(raw_overlays, list):
                    errors.append(f"{mid}: overlay_children must be a list")
                else:
                    for overlay in raw_overlays:
                        if (
                            not isinstance(overlay, str)
                            or not overlay
                            or overlay.startswith("/")
                            or ".." in Path(overlay).parts
                        ):
                            errors.append(f"{mid}: invalid overlay child")
                            continue
                        if overlay in overlays:
                            errors.append(f"{mid}: duplicate overlay child {overlay}")
                            continue
                        full_destination = f"{dst}/{overlay}"
                        if full_destination not in declared_destinations:
                            errors.append(
                                f"{mid}: overlay child is not a governed mapping destination: "
                                f"{full_destination}"
                            )
                            continue
                        overlays.add(overlay)
                errors.extend(
                    _compare(
                        source,
                        destination,
                        parity_exceptions=exceptions,
                        overlay_children=overlays,
                    )
                )
            else:
                errors.append(f"{mid}: unknown parity_mode {parity_mode!r}")

        has_jeeves |= src == "skeleton/jeeves" and dst == "skeleton/ai/agents/jeeves"
        has_build |= src == "core/shift_supervisor" and dst == "skeleton/ai/build/shift_supervisor"

    if not has_jeeves:
        errors.append("Jeeves engine mapping is mandatory")
    if not has_build:
        errors.append("shift-supervisor build/planning mapping is mandatory")

    audit = data.get("planned_path_audit")
    if not isinstance(audit, dict):
        errors.append("planned_path_audit must be an object")
    else:
        def _root(path_value: object) -> str | None:
            if not isinstance(path_value, str) or not path_value.startswith("skeleton/"):
                return None
            suffix = path_value[len("skeleton/"):].split("/", 1)[0]
            return f"skeleton/{suffix}" if suffix else None

        mapped_by_id = {
            item.get("id"): item
            for item in mappings
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        classified_roots: set[str] = {str(data.get("canonical_root", "skeleton/ai"))}
        for item in mappings:
            if isinstance(item, dict):
                root = _root(item.get("source"))
                if root:
                    classified_roots.add(root)

        external = audit.get("intentionally_external", [])
        if not isinstance(external, list):
            errors.append("planned_path_audit.intentionally_external must be a list")
            external = []
        for item in external:
            if not isinstance(item, dict):
                errors.append("planned-path external entry must be an object")
                continue
            path_value = item.get("path")
            root = _root(path_value)
            if root:
                classified_roots.add(root)
            if not isinstance(path_value, str) or not (ROOT / path_value).exists():
                errors.append(f"planned external path missing: {path_value!r}")
            if not item.get("owner") or not item.get("reason"):
                errors.append(f"planned external path lacks owner/reason: {path_value!r}")

        aliases = audit.get("covered_aliases", [])
        if not isinstance(aliases, list):
            errors.append("planned_path_audit.covered_aliases must be a list")
            aliases = []
        for item in aliases:
            if not isinstance(item, dict):
                errors.append("planned-path alias entry must be an object")
                continue
            planned_path = item.get("planned_path")
            implemented_path = item.get("implemented_path")
            mapping_id = item.get("mapping_id")
            root = _root(planned_path)
            if root:
                classified_roots.add(root)
            mapping = mapped_by_id.get(mapping_id)
            if not isinstance(mapping, dict):
                errors.append(f"planned-path alias references unknown mapping: {mapping_id!r}")
            elif mapping.get("source") != implemented_path:
                errors.append(
                    f"planned-path alias implementation drift: {planned_path!r} -> {implemented_path!r}"
                )
            if not isinstance(implemented_path, str) or not (ROOT / implemented_path).exists():
                errors.append(f"planned-path alias implementation missing: {implemented_path!r}")

        absent = audit.get("planned_but_absent", [])
        if not isinstance(absent, list):
            errors.append("planned_path_audit.planned_but_absent must be a list")
            absent = []
        for path_value in absent:
            root = _root(path_value)
            if root:
                classified_roots.add(root)
            if not isinstance(path_value, str) or not path_value.startswith("skeleton/"):
                errors.append(f"invalid planned-but-absent path: {path_value!r}")
            elif (ROOT / path_value).exists():
                errors.append(
                    f"planned-but-absent engine path now exists and requires migration/classification: {path_value}"
                )

        exclusions = audit.get("non_engine_root_exclusions", [])
        if not isinstance(exclusions, list):
            errors.append("planned_path_audit.non_engine_root_exclusions must be a list")
            exclusions = []
        for path_value in exclusions:
            root = _root(path_value)
            if root:
                classified_roots.add(root)

        planned_roots: set[str] = set()
        for contract_path in (
            ROOT / "machine/ai_master_plan.json",
            ROOT / "machine/ai_app_construction.json",
        ):
            try:
                contract = json.loads(contract_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                errors.append(f"cannot parse planned-path authority {contract_path.name}: {exc}")
                continue
            serialized = json.dumps(contract, ensure_ascii=False)
            planned_roots.update(
                re.findall(r"\bskeleton/[A-Za-z0-9_.-]+", serialized)
            )

        unclassified = sorted(planned_roots - classified_roots)
        if unclassified:
            errors.append(
                "masterplan/construction skeleton roots lack AI-tree disposition: "
                + ", ".join(unclassified)
            )

    assignments = data.get("next_move_assignments")
    if not isinstance(assignments, list):
        errors.append("next_move_assignments must be a list")
        assignments = []

    allowed_actions = {"mirror_then_cutover", "split_then_mirror", "merge_into_existing_owner", "quarantine_then_characterize"}
    mapped_sources = {
        item.get("source")
        for item in mappings
        if isinstance(item, dict) and isinstance(item.get("source"), str)
    }
    pending_ids: set[str] = set()
    pending_sources: set[str] = set()
    pending_destinations: set[str] = set()
    required_pending_sources = {
        "skeleton/state",
        "skeleton/network",
        "skeleton/kv",
        "skeleton/swarm",
        "skeleton/foundation",
        "skeleton/build",
        "skeleton/repo_machine",
        "skeleton/application",
        "skeleton/core",
        "skeleton/data",
        "skeleton/genesis.py",
        "skeleton/galaxy",
        "skeleton/mesh",
        "skeleton/overseer",
        "skeleton/pr_automation",
        "skeleton/chronicle",
    } - mapped_sources
    if required_pending_sources and len(assignments) < len(required_pending_sources):
        errors.append(
            "next_move_assignments must contain every still-unmapped plan-derived source"
        )
    for item in assignments:
        if not isinstance(item, dict):
            errors.append("pending move assignment must be an object")
            continue
        aid = item.get("id")
        source = item.get("source")
        destination = item.get("destination")
        action = item.get("action")
        priority = item.get("priority")
        if not isinstance(aid, str) or not aid.startswith("AIFT-NEXT-"):
            errors.append(f"pending move has invalid id: {aid!r}")
            continue
        if aid in pending_ids:
            errors.append(f"duplicate pending move id: {aid}")
        pending_ids.add(aid)
        if not isinstance(source, str) or not source:
            errors.append(f"{aid}: pending source must be a non-empty string")
            continue
        if source in pending_sources:
            errors.append(f"{aid}: duplicate pending source {source}")
        pending_sources.add(source)
        if source in mapped_sources:
            errors.append(f"{aid}: source is already a governed mirror and must leave the pending queue: {source}")
        if not FULL_SHA.fullmatch(str(item.get("source_git_object_sha", ""))):
            errors.append(f"{aid}: pending source_git_object_sha must be a full SHA")
        if not (ROOT / source).exists():
            errors.append(f"{aid}: pending source missing: {source}")
        if not isinstance(destination, str) or not destination.startswith("skeleton/ai/"):
            errors.append(f"{aid}: pending destination must stay under skeleton/ai")
        elif destination in pending_destinations or destination in seen_destinations:
            errors.append(f"{aid}: duplicate/occupied pending destination {destination}")
        else:
            pending_destinations.add(destination)
        if action not in allowed_actions:
            errors.append(f"{aid}: unsupported pending action {action!r}")
        if priority not in {1, 2, 3}:
            errors.append(f"{aid}: priority must be 1, 2, or 3")
        refs = item.get("work_package_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{aid}: pending assignment missing work_package_refs")
        elif any(not isinstance(ref, str) or not re.fullmatch(r"WP-W(?:0[0-9]|[12][0-9]|30)", ref) for ref in refs):
            errors.append(f"{aid}: invalid work_package_refs")
        volume_refs = item.get("volume_refs", [])
        if not isinstance(volume_refs, list) or any(
            not isinstance(ref, str) or not re.fullmatch(r"VOL-\d{3}", ref) for ref in volume_refs
        ):
            errors.append(f"{aid}: invalid volume_refs")
        if not isinstance(item.get("rationale"), str) or not item.get("rationale"):
            errors.append(f"{aid}: missing rationale")
        preconditions = item.get("preconditions")
        if not isinstance(preconditions, list) or not preconditions:
            errors.append(f"{aid}: missing migration preconditions")

    missing_required_pending = sorted(required_pending_sources - pending_sources)
    if missing_required_pending:
        errors.append(
            "required plan-derived pending AI moves missing: " + ", ".join(missing_required_pending)
        )


    retained = data.get("retained_outside_ai_tree")
    if not isinstance(retained, list) or not retained:
        errors.append("retained_outside_ai_tree must classify non-move top-level skeleton surfaces")
        retained = []
    retained_paths: set[str] = set()
    for item in retained:
        if not isinstance(item, dict):
            errors.append("retained-outside entry must be an object")
            continue
        path_value = item.get("path")
        if not isinstance(path_value, str) or not path_value.startswith("skeleton/"):
            errors.append(f"invalid retained-outside path: {path_value!r}")
            continue
        if path_value in retained_paths:
            errors.append(f"duplicate retained-outside path: {path_value}")
        retained_paths.add(path_value)
        if not (ROOT / path_value).exists():
            errors.append(f"retained-outside path missing: {path_value}")
        if not item.get("owner") or not item.get("reason"):
            errors.append(f"retained-outside path lacks owner/reason: {path_value}")

    def _first_level(path_value: object) -> str | None:
        if not isinstance(path_value, str) or not path_value.startswith("skeleton/"):
            return None
        parts = Path(path_value).parts
        return path_value if len(parts) == 2 else None

    classified_top_level: set[str] = {"skeleton/ai"}
    for item in mappings:
        if isinstance(item, dict):
            root = _first_level(item.get("source"))
            if root:
                classified_top_level.add(root)
    for item in assignments:
        if isinstance(item, dict):
            root = _first_level(item.get("source"))
            if root:
                classified_top_level.add(root)
    if isinstance(audit, dict):
        for item in audit.get("intentionally_external", []):
            if isinstance(item, dict):
                root = _first_level(item.get("path"))
                if root:
                    classified_top_level.add(root)
        for path_value in audit.get("non_engine_root_exclusions", []):
            root = _first_level(path_value)
            if root:
                classified_top_level.add(root)
    classified_top_level.update(retained_paths)

    try:
        tracked = subprocess.run(
            ["git", "ls-files", "-z", "skeleton"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        ).stdout.decode("utf-8").split("\0")
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as exc:
        errors.append(f"cannot enumerate git-tracked skeleton paths for classification audit: {exc}")
        tracked = []

    tracked_top_level = {
        "/".join(Path(path_value).parts[:2])
        for path_value in tracked
        if path_value and len(Path(path_value).parts) >= 2
    }
    unclassified_live = sorted(tracked_top_level - classified_top_level)
    if unclassified_live:
        errors.append(
            "git-tracked top-level skeleton paths lack AI-tree move/retain classification: "
            + ", ".join(unclassified_live)
        )

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
