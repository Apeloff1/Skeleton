#!/usr/bin/env python3
"""Independent exact-head verifier for VOL-058 ADR Program.

This verifier does not import the canonical ADR-index validator. It binds the
machine ADR index to VOL-058, independently validates stable IDs, document/index
coverage, masterplan references, active governed-path impact, and supersession
lineage, then confirms ADR enforcement is a blocking architecture rule.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
MASTER = Path("machine/ai_master_plan.json")
INDEX = Path("machine/adr_index.json")
REGISTRY = Path("machine/architecture_rule_registry.json")
VALIDATOR = Path("scripts/check_architecture_adr_index.py")
TESTS = Path("tests/test_architecture_adr_index.py")
ADR_DIR = Path("docs/adr")
VOLUME = "VOL-058"
TITLE = "ADR Program"
REQUIRED_GAPS = {
    "create canonical ADR index schema",
    "bind cross-cutting changes to ADR check",
}
ADR_ID = re.compile(r"^ADR-[0-9]{4,}$")


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
    return pure.as_posix()


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
    if volume.get("completion_checkbox") is True:
        errors.append(f"{VOLUME} cannot self-sign from implementation evidence")
    gaps = set(volume.get("gaps") or [])
    missing = sorted(REQUIRED_GAPS - gaps)
    if missing:
        errors.append(f"{VOLUME} gap binding drift: {missing}")
    requirements = tuple(str(item) for item in volume.get("requirements") or [])
    for phrase in (
        "Use stable ADR IDs and immutable decision history",
        "Record context, considered alternatives, consequences, owner and affected contracts",
        "Model supersession/deprecation explicitly without rewriting history",
    ):
        if not any(phrase in requirement for requirement in requirements):
            errors.append(f"{VOLUME} requirement invariant lost: {phrase}")
    return {
        "key": volume.get("key"),
        "title": volume.get("title"),
        "implementation_status": volume.get("implementation_status"),
        "completion_checkbox": volume.get("completion_checkbox"),
        "gaps": sorted(gaps),
    }


def _verify_index(
    index: Mapping[str, Any],
    master: Mapping[str, Any],
    root: Path,
    errors: list[str],
) -> dict[str, Any]:
    if index.get("schema_version") != "skeleton.architecture.adr_index.v1":
        errors.append("ADR index schema drift")
    if index.get("status") != "active":
        errors.append("ADR index must remain active")

    binding = index.get("masterplan_binding")
    if not isinstance(binding, dict):
        errors.append("ADR masterplan binding missing")
    else:
        if binding.get("volume_ref") != VOLUME or binding.get("title") != TITLE:
            errors.append("ADR index volume/title binding drift")
        if set(binding.get("required_gap_texts") or []) != REQUIRED_GAPS:
            errors.append("ADR index gap binding drift")

    policy = index.get("policy")
    if not isinstance(policy, dict):
        errors.append("ADR policy missing")
        policy = {}
    statuses = policy.get("statuses")
    active_statuses = policy.get("active_statuses")
    if not isinstance(statuses, list) or not statuses:
        errors.append("ADR policy statuses missing")
        statuses = []
    if not isinstance(active_statuses, list) or not active_statuses:
        errors.append("ADR active status set missing")
        active_statuses = []
    if not set(active_statuses) <= set(statuses):
        errors.append("ADR active statuses escape allowed statuses")
    if policy.get("adr_directory") != "docs/adr":
        errors.append("ADR directory authority drift")
    if policy.get("indexed_filename_pattern") != "ADR-*.md":
        errors.append("ADR filename policy drift")
    if "indexed exactly once" not in str(policy.get("rule", "")):
        errors.append("ADR exact-index coverage policy lost")
    if "Superseded ADRs name a current replacement" not in str(
        policy.get("supersession_rule", "")
    ):
        errors.append("ADR supersession policy lost")

    governed = index.get("governed_path_patterns")
    if not isinstance(governed, list) or not governed:
        errors.append("ADR governed path set missing")
        governed = []
    if len(governed) != len(set(governed)):
        errors.append("ADR governed path set contains duplicates")

    volumes = {
        row.get("key")
        for row in master.get("volumes", [])
        if isinstance(row, dict) and isinstance(row.get("key"), str)
    }
    records = index.get("records")
    if not isinstance(records, list) or not records:
        errors.append("ADR records must be non-empty")
        records = []

    ids: set[str] = set()
    doc_paths: set[str] = set()
    record_by_id: dict[str, Mapping[str, Any]] = {}
    active_impact: set[str] = set()
    active_records = 0
    superseded_records = 0

    for raw in records:
        if not isinstance(raw, dict):
            errors.append("ADR record must be an object")
            continue
        adr_id = raw.get("id")
        if not isinstance(adr_id, str) or not ADR_ID.fullmatch(adr_id):
            errors.append(f"invalid ADR id: {adr_id!r}")
            continue
        if adr_id in ids:
            errors.append(f"duplicate ADR id: {adr_id}")
        ids.add(adr_id)
        record_by_id[adr_id] = raw

        status = raw.get("status")
        if status not in statuses:
            errors.append(f"{adr_id}: unsupported status {status!r}")
        if status in active_statuses:
            active_records += 1
        if status == "superseded":
            superseded_records += 1

        rel = _repo_path(raw.get("path"), label=f"{adr_id}.path", errors=errors)
        if rel is not None:
            if not rel.startswith("docs/adr/ADR-") or not rel.endswith(".md"):
                errors.append(f"{adr_id}: ADR document path contract drift")
            if rel in doc_paths:
                errors.append(f"duplicate ADR document path: {rel}")
            doc_paths.add(rel)
            if not (root / rel).is_file():
                errors.append(f"{adr_id}: ADR document missing: {rel}")

        refs = raw.get("masterplan_refs")
        if not isinstance(refs, list) or not refs:
            errors.append(f"{adr_id}: masterplan_refs missing")
        else:
            unknown = sorted(set(refs) - volumes)
            if unknown:
                errors.append(f"{adr_id}: unknown masterplan refs {unknown}")

        impacts = raw.get("impacted_paths")
        if not isinstance(impacts, list) or not impacts:
            errors.append(f"{adr_id}: impacted_paths missing")
            impacts = []
        if len(impacts) != len(set(impacts)):
            errors.append(f"{adr_id}: duplicate impacted paths")
        for impact in impacts:
            if impact not in governed:
                errors.append(f"{adr_id}: impact outside governed path set: {impact}")
        if status in active_statuses:
            active_impact.update(impact for impact in impacts if impact in governed)

        supersedes = raw.get("supersedes")
        if not isinstance(supersedes, list):
            errors.append(f"{adr_id}: supersedes must be a list")
            supersedes = []
        if adr_id in supersedes:
            errors.append(f"{adr_id}: cannot supersede itself")
        replacement = raw.get("superseded_by")
        if status == "superseded":
            if not isinstance(replacement, str) or not replacement:
                errors.append(f"{adr_id}: superseded record requires replacement")
        elif replacement is not None:
            errors.append(f"{adr_id}: active record cannot name superseded_by")

    for adr_id, record in record_by_id.items():
        for prior in record.get("supersedes", []):
            if prior not in record_by_id:
                errors.append(f"{adr_id}: supersedes unknown ADR {prior}")
        replacement = record.get("superseded_by")
        if replacement is not None and replacement not in record_by_id:
            errors.append(f"{adr_id}: replacement ADR does not exist: {replacement}")

    discovered = {
        path.relative_to(root).as_posix()
        for path in (root / ADR_DIR).glob("ADR-*.md")
        if path.is_file()
    }
    if discovered != doc_paths:
        errors.append(
            "ADR document/index coverage drift: "
            f"unindexed={sorted(discovered - doc_paths)} "
            f"missing={sorted(doc_paths - discovered)}"
        )
    uncovered = sorted(set(governed) - active_impact)
    if uncovered:
        errors.append(f"governed architecture paths lack active ADR impact: {uncovered}")

    identity = [
        {
            "id": row.get("id"),
            "path": row.get("path"),
            "status": row.get("status"),
            "supersedes": row.get("supersedes"),
            "superseded_by": row.get("superseded_by"),
            "masterplan_refs": row.get("masterplan_refs"),
            "impacted_paths": row.get("impacted_paths"),
        }
        for row in records
        if isinstance(row, dict)
    ]
    return {
        "record_count": len(records),
        "active_record_count": active_records,
        "superseded_record_count": superseded_records,
        "governed_pattern_count": len(governed),
        "document_count": len(discovered),
        "index_identity_digest": _digest_json(identity),
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
        if isinstance(rule, dict) and rule.get("id") == "ARCH-ADR-INDEX"
    ]
    if len(matches) != 1:
        errors.append("ARCH-ADR-INDEX must appear exactly once")
        return {}
    rule = matches[0]
    if rule.get("validator_path") != VALIDATOR.as_posix():
        errors.append("ARCH-ADR-INDEX validator path drift")
    if rule.get("severity") != "blocking":
        errors.append("ARCH-ADR-INDEX must remain blocking")
    if rule.get("change_requires_adr") is not True:
        errors.append("ARCH-ADR-INDEX changes must require ADR")
    policy = rule.get("waiver_policy")
    if not isinstance(policy, dict) or policy.get("allowed") is not False:
        errors.append("ARCH-ADR-INDEX must remain non-waivable")
    return {
        "rule_id": rule.get("id"),
        "severity": rule.get("severity"),
        "validator_path": rule.get("validator_path"),
        "waivable": policy.get("allowed") if isinstance(policy, dict) else None,
    }


def _verify_source_contract(root: Path, errors: list[str]) -> dict[str, str]:
    digests: dict[str, str] = {}
    for relative in (VALIDATOR, TESTS):
        path = root / relative
        if not path.is_file():
            errors.append(f"missing VOL-058 surface: {relative}")
            continue
        digests[relative.as_posix()] = _sha256(path)

    if (root / VALIDATOR).is_file():
        source = (root / VALIDATOR).read_text(encoding="utf-8")
        for token in (
            "ADR document/index coverage drift",
            "governed architecture paths lack active ADR coverage",
            "superseded record needs superseded_by",
            "active/non-superseded record cannot name superseded_by",
            "supersedes unknown ADR",
            "superseded_by references unknown ADR",
            "references unknown masterplan volumes",
        ):
            if token not in source:
                errors.append(f"VOL-058 ADR invariant missing: {token}")
    if (root / TESTS).is_file():
        tests = (root / TESTS).read_text(encoding="utf-8")
        for token in (
            "test_rejects_unindexed_adr_document",
            "test_rejects_governed_path_without_active_adr",
            "test_rejects_unknown_masterplan_reference",
            "test_rejects_stale_masterplan_gap_binding",
        ):
            if token not in tests:
                errors.append(f"VOL-058 ADR regression missing: {token}")
    return digests


def verify_repository(root: Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    master = _load(root / MASTER)
    index = _load(root / INDEX)
    registry = _load(root / REGISTRY)

    volume_binding = _verify_volume(master, errors)
    index_binding = _verify_index(index, master, root, errors)
    registry_binding = _verify_registry(registry, errors)
    source_digests = _verify_source_contract(root, errors)

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "verifier": "independent-vol058-adr-program-v1",
        "volume": VOLUME,
        "head_sha": (
            os.environ.get("EVIDENCE_HEAD_SHA", "").strip()
            or os.environ.get("GITHUB_SHA", "").strip()
            or "unknown"
        ),
        "volume_binding": volume_binding,
        "index_binding": index_binding,
        "registry_binding": registry_binding,
        "source_digests": source_digests,
        "index_digest": _sha256(root / INDEX),
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
            "verifier": "independent-vol058-adr-program-v1",
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
            "VOL-058 independent ADR-program verification: OK "
            f"({receipt['receipt_digest']})"
        )
    else:
        print("VOL-058 independent ADR-program verification: FAIL")
        for error in receipt.get("errors", []):
            print(f"- {error}")
    return 0 if receipt["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
