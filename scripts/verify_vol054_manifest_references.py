#!/usr/bin/env python3
"""Independent exact-head verifier for VOL-054 Machine Architecture Manifests.

The canonical manifest-reference validator remains the behavioral authority.
This verifier independently validates the policy schema, current masterplan
qualification binding, repository-reference resolution, exact Git-blob
document bindings, and the blocking/non-waivable architecture rule.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
POLICY = Path("machine/manifest_reference_policy.json")
REGISTRY = Path("machine/architecture_rule_registry.json")
VALIDATOR = Path("scripts/check_architecture_manifest_references.py")
TESTS = Path("tests/test_architecture_manifest_references.py")
VOLUME = "VOL-054"
TITLE = "Machine Architecture Manifests"
QUALIFICATION_GAP = (
    "independent manifest-reference drift, schema-downgrade, "
    "and doc-digest verification remains pending"
)


class VerificationError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"cannot load {path}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{path} must contain an object")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _digest_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _repo_path(value: object, *, label: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value or "\\" in value:
        errors.append(f"{label}: invalid repository path")
        return None
    pure = PurePosixPath(value)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        errors.append(f"{label}: repository path must be canonical and relative")
        return None
    if pure.as_posix() != value:
        errors.append(f"{label}: repository path normalization drift")
        return None
    return value


def _pointer(payload: Any, pointer: object, *, label: str, errors: list[str]) -> Any:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        errors.append(f"{label}: invalid JSON pointer")
        return None
    current = payload
    for raw in pointer.split("/")[1:]:
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                errors.append(f"{label}: JSON pointer missing key {token!r}")
                return None
            current = current[token]
        elif isinstance(current, list):
            try:
                index = int(token)
            except ValueError:
                errors.append(f"{label}: JSON pointer list token is not integer")
                return None
            if not 0 <= index < len(current):
                errors.append(f"{label}: JSON pointer index out of range")
                return None
            current = current[index]
        else:
            errors.append(f"{label}: JSON pointer traverses scalar")
            return None
    return current


def _find_volume(master: Mapping[str, Any]) -> Mapping[str, Any]:
    volumes = master.get("volumes")
    if not isinstance(volumes, list):
        raise VerificationError("masterplan volumes must be a list")
    for volume in volumes:
        if isinstance(volume, dict) and volume.get("key") == VOLUME:
            return volume
    raise VerificationError(f"masterplan missing {VOLUME}")


def _verify_volume(master: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    volume = _find_volume(master)
    if volume.get("title") != TITLE:
        errors.append(f"{VOLUME} title drift")
    if volume.get("scope") != "canonical-plan":
        errors.append(f"{VOLUME} scope drift")
    if volume.get("implementation_status") not in {"implemented", "hardened", "verified"}:
        errors.append(f"{VOLUME} implementation maturity below implemented")
    if volume.get("completion_checkbox") is True:
        errors.append(f"{VOLUME} cannot self-sign before independent verification")
    gaps = list(volume.get("gaps") or [])
    if gaps != [QUALIFICATION_GAP]:
        errors.append(f"{VOLUME} qualification-gap state drift")
    requirements = tuple(str(item) for item in volume.get("requirements") or [])
    for phrase in (
        "Represent roots, capabilities, contracts, ownership and construction status",
        "Version manifest schemas and reject unknown/ambiguous references",
        "Cross-check manifests against repository paths and canonical documents",
    ):
        if not any(phrase in requirement for requirement in requirements):
            errors.append(f"{VOLUME} requirement invariant lost: {phrase}")
    return {
        "key": volume.get("key"),
        "title": volume.get("title"),
        "implementation_status": volume.get("implementation_status"),
        "completion_checkbox": volume.get("completion_checkbox"),
        "gaps": gaps,
    }


def _verify_policy(
    policy: Mapping[str, Any],
    root: Path,
    errors: list[str],
) -> dict[str, Any]:
    if policy.get("schema_version") != "skeleton.architecture.manifest_reference_policy.v1":
        errors.append("manifest-reference schema downgrade/drift")
    if policy.get("status") != "active":
        errors.append("manifest-reference policy must remain active")

    binding = policy.get("masterplan_binding")
    if not isinstance(binding, dict):
        errors.append("manifest-reference masterplan binding missing")
    else:
        if binding.get("volume_ref") != VOLUME or binding.get("title") != TITLE:
            errors.append("manifest-reference volume/title binding drift")
        if binding.get("required_gap_texts") != [QUALIFICATION_GAP]:
            errors.append("manifest-reference qualification-gap binding drift")

    policy_rules = policy.get("policy")
    if not isinstance(policy_rules, dict):
        errors.append("manifest-reference policy rules missing")
        policy_rules = {}
    if "normalized repository-relative path" not in str(policy_rules.get("reference_rule", "")):
        errors.append("manifest-reference path normalization rule lost")
    if "exactly one machine-git-blob marker" not in str(policy_rules.get("digest_rule", "")):
        errors.append("manifest-reference exact doc-digest rule lost")
    if "does not promote capability maturity" not in str(policy_rules.get("anti_shortcut", "")):
        errors.append("manifest-reference anti-shortcut boundary lost")

    groups = policy.get("reference_groups")
    if not isinstance(groups, list) or not groups:
        errors.append("manifest-reference groups missing")
        groups = []
    seen_ids: set[str] = set()
    checked_references = 0
    for group in groups:
        if not isinstance(group, dict):
            errors.append("manifest-reference group must be an object")
            continue
        gid = group.get("id")
        if not isinstance(gid, str) or not gid:
            errors.append("manifest-reference group id missing")
            continue
        if gid in seen_ids:
            errors.append(f"duplicate manifest-reference group: {gid}")
        seen_ids.add(gid)

        manifest_rel = _repo_path(
            group.get("manifest"),
            label=f"{gid}.manifest",
            errors=errors,
        )
        if manifest_rel is None:
            continue
        manifest_path = root / manifest_rel
        if not manifest_path.is_file():
            errors.append(f"{gid}: manifest missing: {manifest_rel}")
            continue
        manifest = _load(manifest_path)
        value = _pointer(
            manifest,
            group.get("json_pointer"),
            label=gid,
            errors=errors,
        )
        kind = group.get("kind")
        if kind == "repo_path":
            values = [value]
        elif kind == "repo_path_map":
            if not isinstance(value, dict) or not value:
                errors.append(f"{gid}: pointer must resolve to non-empty map")
                values = []
            else:
                values = list(value.values())
        else:
            errors.append(f"{gid}: unsupported reference kind {kind!r}")
            values = []

        for raw in values:
            rel = _repo_path(raw, label=f"{gid}.reference", errors=errors)
            if rel is None:
                continue
            checked_references += 1
            if not (root / rel).exists():
                errors.append(f"{gid}: reference target missing: {rel}")

    bindings = policy.get("doc_bindings")
    if not isinstance(bindings, list) or not bindings:
        errors.append("manifest-reference doc bindings missing")
        bindings = []
    seen_sources: set[str] = set()
    seen_docs: set[str] = set()
    digest_rows: list[dict[str, str]] = []
    for item in bindings:
        if not isinstance(item, dict):
            errors.append("manifest-reference doc binding must be an object")
            continue
        source = _repo_path(
            item.get("source"),
            label="doc_binding.source",
            errors=errors,
        )
        doc = _repo_path(
            item.get("doc"),
            label="doc_binding.doc",
            errors=errors,
        )
        if source is None or doc is None:
            continue
        if source in seen_sources:
            errors.append(f"duplicate manifest doc-binding source: {source}")
        if doc in seen_docs:
            errors.append(f"duplicate manifest doc-binding document: {doc}")
        seen_sources.add(source)
        seen_docs.add(doc)

        source_path = root / source
        doc_path = root / doc
        if not source_path.is_file():
            errors.append(f"manifest doc-binding source missing: {source}")
            continue
        if not doc_path.is_file():
            errors.append(f"manifest doc-binding document missing: {doc}")
            continue
        digest = _git_blob_sha(source_path)
        marker = f"<!-- machine-git-blob: {source}@{digest} -->"
        text = doc_path.read_text(encoding="utf-8")
        if text.count(marker) != 1:
            errors.append(f"{doc}: exact current machine-git-blob marker missing/duplicated")
        prefix = f"<!-- machine-git-blob: {source}@"
        if text.count(prefix) != 1:
            errors.append(f"{doc}: stale/duplicate machine-git-blob marker present")
        digest_rows.append({"source": source, "doc": doc, "git_blob_sha": digest})

    return {
        "reference_group_count": len(groups),
        "checked_reference_count": checked_references,
        "doc_binding_count": len(bindings),
        "doc_binding_digest": _digest_json(digest_rows),
    }


def _verify_registry(
    registry: Mapping[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    rules = registry.get("rules")
    if not isinstance(rules, list):
        errors.append("architecture rule registry rules missing")
        return {}
    matches = [
        rule
        for rule in rules
        if isinstance(rule, dict) and rule.get("id") == "ARCH-MANIFEST-REFERENCES"
    ]
    if len(matches) != 1:
        errors.append("ARCH-MANIFEST-REFERENCES must appear exactly once")
        return {}
    rule = matches[0]
    if rule.get("validator_path") != VALIDATOR.as_posix():
        errors.append("ARCH-MANIFEST-REFERENCES validator path drift")
    if rule.get("severity") != "blocking":
        errors.append("ARCH-MANIFEST-REFERENCES must remain blocking")
    if rule.get("change_requires_adr") is not True:
        errors.append("ARCH-MANIFEST-REFERENCES changes must require ADR")
    waiver = rule.get("waiver_policy")
    if not isinstance(waiver, dict) or waiver.get("allowed") is not False:
        errors.append("ARCH-MANIFEST-REFERENCES must remain non-waivable")
    return {
        "rule_id": rule.get("id"),
        "severity": rule.get("severity"),
        "validator_path": rule.get("validator_path"),
        "waivable": waiver.get("allowed") if isinstance(waiver, dict) else None,
    }


def _verify_source_contract(root: Path, errors: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for relative in (VALIDATOR, TESTS):
        path = root / relative
        if not path.is_file():
            errors.append(f"missing VOL-054 surface: {relative}")
            continue
        digests[relative.as_posix()] = _sha256(path)

    if (root / VALIDATOR).is_file():
        source = (root / VALIDATOR).read_text(encoding="utf-8")
        for token in (
            "def _pointer",
            "def _git_blob_sha",
            "references missing path",
            "must contain exactly one current digest marker",
            "contains stale/duplicate digest markers",
            "masterplan gap drift",
        ):
            if token not in source:
                errors.append(f"VOL-054 validator invariant missing: {token}")
    if (root / TESTS).is_file():
        tests = (root / TESTS).read_text(encoding="utf-8")
        for token in (
            "test_rejects_missing_manifest_reference",
            "test_rejects_stale_doc_digest",
            "test_rejects_stale_masterplan_gap_binding",
        ):
            if token not in tests:
                errors.append(f"VOL-054 regression missing: {token}")
    return digests


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    master = _load(root / MASTER)
    policy = _load(root / POLICY)
    registry = _load(root / REGISTRY)

    volume_binding = _verify_volume(master, errors)
    policy_binding = _verify_policy(policy, root, errors)
    registry_binding = _verify_registry(registry, errors)
    source_digests = _verify_source_contract(root, errors)

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "verifier": "independent-vol054-manifest-references-v1",
        "volume": VOLUME,
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "volume_binding": volume_binding,
        "policy_binding": policy_binding,
        "registry_binding": registry_binding,
        "source_digests": source_digests,
        "policy_digest": _sha256(root / POLICY),
        "registry_digest": _sha256(root / REGISTRY),
        "errors": sorted(set(errors)),
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
    except VerificationError as exc:
        receipt = {
            "schema_version": 1,
            "verifier": "independent-vol054-manifest-references-v1",
            "volume": VOLUME,
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
        args.evidence_out.write_text(rendered + "\n", encoding="utf-8")
    if args.print_evidence:
        print(rendered)
    elif receipt["valid"]:
        print(
            "VOL-054 independent manifest-reference verification: OK "
            f"({receipt['receipt_digest']})"
        )
    else:
        print("VOL-054 independent manifest-reference verification: FAIL")
        for error in receipt.get("errors", []):
            print(f"- {error}")
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
