#!/usr/bin/env python3
"""Compile exact-head evidence candidates for every unbound P1 volume obligation.

This compiler is intentionally non-authoritative. It binds each canonical
volume risk/gap identity to:
* its exact obligation digest;
* its single owning P1 lane and required evidence modes;
* tracked, materialized implementation/test/evaluation surfaces;
* the volume's existing git/GitHub evidence provenance; and
* the exact candidate git head.

It never writes the governed registry, accepts risk, deletes source risks/gaps,
or promotes maturity. Adversarial-axis obligations are deliberately excluded
and remain a separate closure lane.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reconcile_p1_risk_evidence import (  # noqa: E402
    ADVERSARIAL,
    MASTER,
    P1_MAP,
    POLICY,
    REGISTRY,
    ROOT,
    RiskKind,
    derive_obligations,
    retired_gap_owner_from_id,
)

_SHA40_RE = re.compile(r"^[0-9a-f]{40}$")
BATCH_ID = "p1-bulk-volume-obligation-evidence"
CATEGORY = "p1_volume_obligation_evidence"
EXPECTED_PRIMARY_VOLUMES = 107
EXPECTED_VOLUME_RISKS = 281
EXPECTED_VOLUME_GAPS = 174
EXPECTED_VOLUME_OBLIGATIONS = EXPECTED_VOLUME_RISKS + EXPECTED_VOLUME_GAPS
EXPECTED_EXISTING_BINDINGS = 455
EXPECTED_CANDIDATES = 0
EXPECTED_CANDIDATE_RISKS = 0
EXPECTED_CANDIDATE_GAPS = 0


class BulkVolumeEvidenceError(RuntimeError):
    """Bulk P1 volume evidence inputs are malformed or incomplete."""


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BulkVolumeEvidenceError(f"cannot read {path}") from exc
    if not isinstance(value, dict):
        raise BulkVolumeEvidenceError(f"{path} must contain an object")
    return value


def _digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_digest(value: object) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _safe_relative(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BulkVolumeEvidenceError(f"{field} contains an invalid path")
    if value.startswith("planned:"):
        raise BulkVolumeEvidenceError(f"{field} contains planned surface: {value}")
    posix = PurePosixPath(value)
    if posix.is_absolute() or ".." in posix.parts:
        raise BulkVolumeEvidenceError(f"{field} contains unsafe path: {value}")
    return value


def _git_manifest(
    root: Path,
    relative: str,
    cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    cached = cache.get(relative)
    if cached is not None:
        return dict(cached)

    has_glob = any(token in relative for token in ("*", "?", "["))
    if has_glob:
        matches = sorted(
            Path(item)
            for item in glob.glob(str(root / relative), recursive=True)
        )
        if not matches:
            raise BulkVolumeEvidenceError(
                f"materialized surface glob matched nothing: {relative}"
            )
        tracked_args = [
            str(path.relative_to(root))
            for path in matches
            if path.exists() and not path.is_symlink()
        ]
        if not tracked_args:
            raise BulkVolumeEvidenceError(
                f"materialized surface glob has no safe matches: {relative}"
            )
        kind = "pathspec"
    else:
        path = root / relative
        if not path.exists():
            raise BulkVolumeEvidenceError(
                f"materialized surface is missing: {relative}"
            )
        if path.is_symlink():
            raise BulkVolumeEvidenceError(
                f"materialized surface must not be symlinked: {relative}"
            )
        tracked_args = [relative]
        kind = "file" if path.is_file() else "directory"

    result = subprocess.run(
        ["git", "ls-files", "-s", "-z", "--", *tracked_args],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise BulkVolumeEvidenceError(
            f"cannot enumerate tracked evidence surface: {relative}"
        )
    raw = result.stdout
    entries = [item for item in raw.split(b"\0") if item]
    if not entries:
        raise BulkVolumeEvidenceError(
            f"evidence surface has no tracked files: {relative}"
        )

    manifest = {
        "path": relative,
        "kind": kind,
        "tracked_entry_count": len(entries),
        "tracked_manifest_digest": hashlib.sha256(raw).hexdigest(),
    }
    cache[relative] = manifest
    return dict(manifest)


def _primary_volume_owners(p1_map: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lanes = p1_map.get("lanes")
    if not isinstance(lanes, list) or not lanes:
        raise BulkVolumeEvidenceError("P1 execution lanes must be a non-empty list")

    owners: dict[str, dict[str, Any]] = {}
    duplicates: set[str] = set()
    for lane in lanes:
        if not isinstance(lane, dict):
            raise BulkVolumeEvidenceError("P1 lane must be an object")
        lane_id = lane.get("id")
        refs = lane.get("primary_volume_refs")
        modes = lane.get("required_evidence_modes")
        if not isinstance(lane_id, str) or not lane_id:
            raise BulkVolumeEvidenceError("P1 lane id is missing")
        if not isinstance(refs, list):
            raise BulkVolumeEvidenceError(f"{lane_id}: primary_volume_refs must be a list")
        if not isinstance(modes, list) or not modes:
            raise BulkVolumeEvidenceError(f"{lane_id}: required_evidence_modes must be non-empty")
        for ref in refs:
            if not isinstance(ref, str) or not ref:
                raise BulkVolumeEvidenceError(f"{lane_id}: invalid primary volume ref")
            if ref in owners:
                duplicates.add(ref)
                continue
            owners[ref] = lane

    if duplicates:
        raise BulkVolumeEvidenceError(
            "P1 primary volume has multiple lane owners: " + ",".join(sorted(duplicates))
        )
    if len(owners) != EXPECTED_PRIMARY_VOLUMES:
        raise BulkVolumeEvidenceError(
            f"expected {EXPECTED_PRIMARY_VOLUMES} primary volumes, got {len(owners)}"
        )
    return owners


def _validate_provenance(volume: dict[str, Any]) -> dict[str, list[str]]:
    raw = volume.get("evidence")
    key = volume.get("key", "<unknown>")
    if not isinstance(raw, list) or not raw:
        raise BulkVolumeEvidenceError(f"{key}: volume evidence must be non-empty")
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise BulkVolumeEvidenceError(f"{key}: volume evidence contains invalid entry")
        if item.startswith("planned:"):
            raise BulkVolumeEvidenceError(f"{key}: planned evidence is not materialized")
        values.append(item)

    groups = {
        "git_head": [item for item in values if item.startswith("git-head:")],
        "github_actions_job": [
            item for item in values if item.startswith("github-actions-job:")
        ],
        "github_actions_run": [
            item
            for item in values
            if "github.com/" in item and "/actions/runs/" in item
        ],
        "github_commit": [
            item for item in values if "github.com/" in item and "/commit/" in item
        ],
    }
    missing = [name for name, refs in groups.items() if not refs]
    if missing:
        raise BulkVolumeEvidenceError(
            f"{key}: missing required provenance classes: " + ",".join(missing)
        )
    groups["all"] = values
    return groups


def _surface_group(
    root: Path,
    volume: dict[str, Any],
    field: str,
    cache: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    values = volume.get(field)
    key = volume.get("key", "<unknown>")
    if not isinstance(values, list) or not values:
        raise BulkVolumeEvidenceError(f"{key}: {field} must be non-empty")
    manifests: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in values:
        relative = _safe_relative(raw, field=f"{key}.{field}")
        if relative in seen:
            continue
        seen.add(relative)
        manifests.append(_git_manifest(root, relative, cache))
    if not manifests:
        raise BulkVolumeEvidenceError(f"{key}: {field} has no materialized surfaces")
    return manifests


def build_bulk_volume_evidence(
    root: Path = ROOT,
    *,
    expected_head: str,
) -> dict[str, Any]:
    if not _SHA40_RE.fullmatch(expected_head):
        raise BulkVolumeEvidenceError(
            "expected_head must be lowercase 40-character git SHA"
        )

    canonical_paths = {
        "master_plan": root / MASTER,
        "p1_execution_map": root / P1_MAP,
        "adversarial_closure": root / ADVERSARIAL,
        "risk_policy": root / POLICY,
        "risk_registry": root / REGISTRY,
    }
    before = {name: _digest_file(path) for name, path in canonical_paths.items()}

    master = _load(canonical_paths["master_plan"])
    p1_map = _load(canonical_paths["p1_execution_map"])
    adversarial = _load(canonical_paths["adversarial_closure"])
    policy = _load(canonical_paths["risk_policy"])
    registry = _load(canonical_paths["risk_registry"])

    owners = _primary_volume_owners(p1_map)
    volumes_raw = master.get("volumes")
    if not isinstance(volumes_raw, list):
        raise BulkVolumeEvidenceError("masterplan volumes must be a list")
    volume_by_key = {
        row.get("key"): row
        for row in volumes_raw
        if isinstance(row, dict) and isinstance(row.get("key"), str)
    }
    if set(owners) - set(volume_by_key):
        raise BulkVolumeEvidenceError(
            "P1 execution map references missing primary volumes: "
            + ",".join(sorted(set(owners) - set(volume_by_key)))
        )

    obligations = derive_obligations(master, p1_map, adversarial, policy)
    known_ids = {item.obligation_id for item in obligations}

    raw_records = registry.get("records")
    if not isinstance(raw_records, list):
        raise BulkVolumeEvidenceError("risk registry records must be a list")
    bound_ids: set[str] = set()
    for index, row in enumerate(raw_records):
        if not isinstance(row, dict):
            raise BulkVolumeEvidenceError(
                f"risk registry record {index} must be an object"
            )
        obligation_id = row.get("obligation_id")
        if not isinstance(obligation_id, str) or not obligation_id:
            raise BulkVolumeEvidenceError(
                f"risk registry record {index} has invalid obligation_id"
            )
        if obligation_id in bound_ids:
            raise BulkVolumeEvidenceError(
                f"duplicate governed binding identity: {obligation_id}"
            )
        bound_ids.add(obligation_id)
    unknown: list[str] = []
    for row in raw_records:
        obligation_id = row["obligation_id"]
        if obligation_id in known_ids:
            continue
        expected_owner = retired_gap_owner_from_id(obligation_id)
        if (
            expected_owner is None
            or row.get("owner_id") != expected_owner
            or row.get("disposition") != "evidence"
            or not row.get("evidence")
            or row.get("accepted_risk") is not None
        ):
            unknown.append(obligation_id)
    if unknown:
        raise BulkVolumeEvidenceError(
            "risk registry references unknown obligations: " + ",".join(sorted(unknown))
        )

    volume_obligations = [
        item
        for item in obligations
        if item.kind in {RiskKind.RISK, RiskKind.GAP}
        and item.source_ref.split(":", 1)[0] in owners
    ]
    if len(volume_obligations) != EXPECTED_VOLUME_OBLIGATIONS:
        raise BulkVolumeEvidenceError(
            f"expected {EXPECTED_VOLUME_OBLIGATIONS} P1 volume obligations, "
            f"got {len(volume_obligations)}"
        )

    manifest_cache: dict[str, dict[str, Any]] = {}
    volume_evidence: dict[str, dict[str, Any]] = {}
    for volume_key in sorted(owners):
        volume = volume_by_key[volume_key]
        lane = owners[volume_key]
        accountability_id = volume.get("accountability_id")
        if accountability_id != "ACC-" + volume_key:
            raise BulkVolumeEvidenceError(
                f"{volume_key}: accountability identity drift: {accountability_id!r}"
            )
        if volume.get("signing_required") is not True:
            raise BulkVolumeEvidenceError(f"{volume_key}: signing_required must remain true")

        implementations = _surface_group(
            root, volume, "implementation_paths", manifest_cache
        )
        tests = _surface_group(root, volume, "tests", manifest_cache)
        evaluations = _surface_group(root, volume, "evaluations", manifest_cache)
        provenance = _validate_provenance(volume)
        modes = lane.get("required_evidence_modes")
        assert isinstance(modes, list)

        volume_packet = {
            "volume_key": volume_key,
            "title": volume.get("title"),
            "accountability_id": accountability_id,
            "lane_id": lane.get("id"),
            "lane_name": lane.get("name"),
            "target_maturity": lane.get("target_maturity"),
            "required_evidence_modes": list(modes),
            "implementation_surfaces": implementations,
            "test_surfaces": tests,
            "evaluation_surfaces": evaluations,
            "declared_provenance": provenance["all"],
            "provenance_classes": {
                key: len(value)
                for key, value in provenance.items()
                if key != "all"
            },
        }
        volume_packet["volume_packet_digest"] = _canonical_digest(volume_packet)
        volume_evidence[volume_key] = volume_packet

    records: list[dict[str, Any]] = []
    for obligation in sorted(volume_obligations, key=lambda item: item.obligation_id):
        volume_key = obligation.source_ref.split(":", 1)[0]
        kind = obligation.kind.value
        if kind not in {"risk", "gap"}:
            raise BulkVolumeEvidenceError(
                f"unexpected volume obligation kind: {kind}"
            )
        packet = {
            "batch_id": BATCH_ID,
            "expected_head": expected_head,
            "volume_key": volume_key,
            "kind": kind,
            "statement": obligation.statement,
            "obligation_id": obligation.obligation_id,
            "obligation_digest": obligation.obligation_digest,
            "source_ref": obligation.source_ref,
            "owner_id": "ACC-" + volume_key,
            "recommended_severity": "high",
            "recommended_disposition": "evidence",
            "volume_evidence": volume_evidence[volume_key],
            "binding_present": obligation.obligation_id in bound_ids,
            "non_authoritative": True,
            "creates_binding": False,
            "accepts_risk": False,
            "lowers_severity": False,
            "clears_source_obligation": False,
            "promotes_maturity": False,
        }
        packet["packet_digest"] = _canonical_digest(packet)
        packet["candidate_evidence_ref"] = {
            "source": (
                f"p1:bulk-volume-obligation-evidence:"
                f"{obligation.obligation_id}:{expected_head}"
            ),
            "digest": packet["packet_digest"],
            "category": CATEGORY,
        }
        records.append(packet)

    already_bound = [row for row in records if row["binding_present"]]
    candidates = [row for row in records if not row["binding_present"]]
    candidate_risks = [row for row in candidates if row["kind"] == "risk"]
    candidate_gaps = [row for row in candidates if row["kind"] == "gap"]

    if len(already_bound) != EXPECTED_EXISTING_BINDINGS:
        raise BulkVolumeEvidenceError(
            f"expected {EXPECTED_EXISTING_BINDINGS} existing volume bindings, "
            f"got {len(already_bound)}"
        )
    if len(candidates) != EXPECTED_CANDIDATES:
        raise BulkVolumeEvidenceError(
            f"expected {EXPECTED_CANDIDATES} unbound volume candidates, "
            f"got {len(candidates)}"
        )
    if len(candidate_risks) != EXPECTED_CANDIDATE_RISKS:
        raise BulkVolumeEvidenceError(
            f"expected {EXPECTED_CANDIDATE_RISKS} risk candidates, "
            f"got {len(candidate_risks)}"
        )
    if len(candidate_gaps) != EXPECTED_CANDIDATE_GAPS:
        raise BulkVolumeEvidenceError(
            f"expected {EXPECTED_CANDIDATE_GAPS} gap candidates, "
            f"got {len(candidate_gaps)}"
        )

    after = {name: _digest_file(path) for name, path in canonical_paths.items()}
    if before != after:
        raise BulkVolumeEvidenceError(
            "canonical P1 evidence sources changed during compilation"
        )

    report = {
        "schema_version": 1,
        "engine": "p1-bulk-volume-obligation-evidence-v1",
        "batch_id": BATCH_ID,
        "expected_head": expected_head,
        "category": CATEGORY,
        "covered_volume_count": len(volume_evidence),
        "covered_obligation_count": len(records),
        "covered_risk_count": sum(row["kind"] == "risk" for row in records),
        "covered_gap_count": sum(row["kind"] == "gap" for row in records),
        "already_bound_count": len(already_bound),
        "candidate_binding_count": len(candidates),
        "candidate_risk_count": len(candidate_risks),
        "candidate_gap_count": len(candidate_gaps),
        "adversarial_axis_count": 0,
        "non_authoritative": True,
        "creates_bindings": False,
        "accepts_risk": False,
        "lowers_severity": False,
        "clears_source_obligations": False,
        "promotes_maturity": False,
        "canonical_source_digests": before,
        "unique_materialized_surface_count": len(manifest_cache),
        "volume_evidence": volume_evidence,
        "records": records,
    }
    report["report_digest"] = _canonical_digest(report)
    return report


def _render(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--print-summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        report = build_bulk_volume_evidence(
            ROOT,
            expected_head=args.expected_head,
        )
    except BulkVolumeEvidenceError as exc:
        print(f"P1 bulk volume evidence: rejected: {exc}", file=sys.stderr)
        return 2

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(_render(report), encoding="utf-8")

    if args.print_summary:
        print(json.dumps({
            key: report[key]
            for key in (
                "batch_id",
                "expected_head",
                "covered_volume_count",
                "covered_obligation_count",
                "already_bound_count",
                "candidate_binding_count",
                "candidate_risk_count",
                "candidate_gap_count",
                "unique_materialized_surface_count",
                "report_digest",
            )
        }, indent=2, sort_keys=True))

    print(
        "P1 bulk volume evidence: OK "
        f"({report['candidate_binding_count']} candidates: "
        f"{report['candidate_risk_count']} risks + "
        f"{report['candidate_gap_count']} gaps)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
