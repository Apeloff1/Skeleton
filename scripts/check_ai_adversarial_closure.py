#!/usr/bin/env python3
"""Validate the adversarial masterplan closure overlay.

Dependency-free and fail-closed. This pass preserves the Volume 420 breadth
freeze while ensuring every W00-W30 work package has cross-condition and
compound-fault proof obligations.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOSURE = ROOT / "machine" / "ai_adversarial_closure.json"
MASTER = ROOT / "machine" / "ai_master_plan.json"
HUMAN = ROOT / "docs" / "plan" / "ADVERSARIAL_CLOSURE_PASS.md"
PLAN = ROOT / "docs" / "plan" / "MASTER_PLAN.md"
INDEX = ROOT / "docs" / "plan" / "MASTER_INDEX.md"
ARCH_INDEX = ROOT / "docs" / "ARCHITECTURE_INDEX.md"
BUILD_PLAN = ROOT / "docs" / "BUILD_PLAN.md"

EXPECTED_WPS = [f"WP-W{i:02d}" for i in range(31)]
EXPECTED_AXES = {f"AC-{i:02d}" for i in range(1, 25)}
EXPECTED_CAMPAIGNS = {f"CCF-{i:02d}" for i in range(1, 13)}
REQUIRED_EVIDENCE_FIELDS = {
    "git_sha", "artifact_digest", "config_digest", "environment_digest",
    "fault_manifest_digest", "work_package_refs", "axis_refs", "campaign_refs",
    "result", "raw_evidence_refs", "started_at_utc", "completed_at_utc",
    "verifier_identity", "signoff_ref",
}


def _load(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name} root must be an object")
    return data


def validate() -> list[str]:
    errors: list[str] = []
    for path in (CLOSURE, MASTER, HUMAN, PLAN, INDEX, ARCH_INDEX, BUILD_PLAN):
        if not path.is_file():
            errors.append(f"missing {path.relative_to(ROOT)}")
    if errors:
        return errors

    try:
        closure = _load(CLOSURE)
        master = _load(MASTER)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return [f"cannot parse adversarial closure inputs: {exc}"]

    if closure.get("schema_version") != 1:
        errors.append("closure schema_version must equal 1")
    if closure.get("status") != "active":
        errors.append("closure status must be active")
    scope = closure.get("scope", {})
    if scope.get("adds_top_level_volumes") is not False:
        errors.append("adversarial closure must preserve breadth freeze")
    if master.get("breadth_freeze", {}).get("last_top_level_volume") != 420:
        errors.append("master plan breadth freeze must remain at Volume 420")

    axes = closure.get("closure_axes")
    if not isinstance(axes, list):
        errors.append("closure_axes must be a list")
        axes = []
    axis_ids = [a.get("id") for a in axes if isinstance(a, dict)]
    if set(axis_ids) != EXPECTED_AXES or len(axis_ids) != len(EXPECTED_AXES):
        errors.append("closure axes must contain AC-01..AC-24 exactly once")

    known_wps = set(EXPECTED_WPS)
    for item in axes:
        if not isinstance(item, dict):
            errors.append("every closure axis must be an object")
            continue
        aid = item.get("id", "?")
        for field in ("name", "gap", "stop_condition"):
            if not str(item.get(field, "")).strip():
                errors.append(f"{aid}: {field} must be non-empty")
        for field in ("applicable_work_packages", "adversarial_questions", "required_evidence_modes"):
            value = item.get(field)
            if not isinstance(value, list) or not value:
                errors.append(f"{aid}: {field} must be non-empty")
        for wp in item.get("applicable_work_packages", []):
            if wp not in known_wps:
                errors.append(f"{aid}: unknown work package {wp}")

    coverage = closure.get("work_package_coverage")
    if not isinstance(coverage, dict):
        errors.append("work_package_coverage must be an object")
        coverage = {}
    if set(coverage) != known_wps:
        errors.append("work_package_coverage must cover WP-W00..WP-W30 exactly")
    minimum = closure.get("minimum_axis_count_per_work_package")
    if not isinstance(minimum, int) or minimum < 6:
        errors.append("minimum_axis_count_per_work_package must be >= 6")
        minimum = 6
    for wp in EXPECTED_WPS:
        refs = coverage.get(wp)
        if not isinstance(refs, list) or len(refs) < minimum:
            errors.append(f"{wp}: insufficient adversarial axis coverage")
            continue
        if any(ref not in EXPECTED_AXES for ref in refs):
            errors.append(f"{wp}: unknown axis reference")
        derived = sorted(a["id"] for a in axes if isinstance(a, dict) and wp in a.get("applicable_work_packages", []))
        if sorted(refs) != derived:
            errors.append(f"{wp}: coverage map disagrees with axis applicability")

    campaigns = closure.get("compound_campaigns")
    if not isinstance(campaigns, list):
        errors.append("compound_campaigns must be a list")
        campaigns = []
    campaign_ids = [c.get("id") for c in campaigns if isinstance(c, dict)]
    if set(campaign_ids) != EXPECTED_CAMPAIGNS or len(campaign_ids) != len(EXPECTED_CAMPAIGNS):
        errors.append("compound campaigns must contain CCF-01..CCF-12 exactly once")
    for campaign in campaigns:
        if not isinstance(campaign, dict):
            errors.append("every compound campaign must be an object")
            continue
        cid = campaign.get("id", "?")
        axes_ref = campaign.get("axes")
        if not isinstance(axes_ref, list) or len(axes_ref) < 3:
            errors.append(f"{cid}: compound campaign must combine at least three axes")
        elif any(ref not in EXPECTED_AXES for ref in axes_ref):
            errors.append(f"{cid}: unknown axis reference")
        wps = campaign.get("work_packages")
        if not isinstance(wps, list) or not wps:
            errors.append(f"{cid}: work_packages must be non-empty")
        elif any(wp not in known_wps for wp in wps):
            errors.append(f"{cid}: unknown work package")
        if not str(campaign.get("oracle", "")).strip():
            errors.append(f"{cid}: oracle must be non-empty")

    fields = closure.get("evidence_bundle_required_fields")
    if not isinstance(fields, list) or not REQUIRED_EVIDENCE_FIELDS.issubset(set(fields)):
        errors.append("evidence bundle required fields are incomplete")

    gates = closure.get("promotion_gates")
    gate_ids = [g.get("id") for g in gates if isinstance(g, dict)] if isinstance(gates, list) else []
    if gate_ids != [f"ADV-E{i}" for i in range(6)]:
        errors.append("promotion gates must be ADV-E0..ADV-E5 in order")

    signoff = closure.get("signoff_policy", {})
    if signoff.get("implementation_and_verification_must_be_distinct") is not True:
        errors.append("signoff must require distinct implementation and verification identities")
    if signoff.get("retroactive_signature_fabrication_forbidden") is not True:
        errors.append("retroactive signature fabrication must be forbidden")

    master_ref = master.get("adversarial_closure")
    if not isinstance(master_ref, dict):
        errors.append("machine master plan must reference adversarial_closure")
    else:
        if master_ref.get("machine_contract") != "machine/ai_adversarial_closure.json":
            errors.append("machine master plan adversarial contract path drifted")
        if master_ref.get("human_contract") != "docs/plan/ADVERSARIAL_CLOSURE_PASS.md":
            errors.append("machine master plan adversarial human path drifted")
        if master_ref.get("required_for_promotion") != ["verified", "hardened", "production"]:
            errors.append("adversarial closure must gate verified/hardened/production maturity")

    human = HUMAN.read_text(encoding="utf-8")
    for marker in (
        "Adversarial findings", "Cross-condition laws", "Canonical compound-fault campaigns",
        "Promotion gates", "Evidence bundle", "Forbidden shortcuts", "AC-24", "CCF-12",
    ):
        if marker not in human:
            errors.append(f"adversarial document missing marker: {marker}")

    plan = PLAN.read_text(encoding="utf-8")
    for marker in (
        "## 21.6 Adversarial cross-condition closure overlay",
        "machine/ai_adversarial_closure.json",
        "docs/plan/ADVERSARIAL_CLOSURE_PASS.md",
    ):
        if marker not in plan:
            errors.append(f"master plan missing adversarial marker: {marker}")

    index = INDEX.read_text(encoding="utf-8")
    if "ADVERSARIAL_CLOSURE_PASS.md" not in index or "ai_adversarial_closure.json" not in index:
        errors.append("master index must link adversarial human and machine contracts")

    arch_index = ARCH_INDEX.read_text(encoding="utf-8")
    for marker in ("Program-plan authority bridge", "plan/MASTER_PLAN.md", "plan/ADVERSARIAL_CLOSURE_PASS.md"):
        if marker not in arch_index:
            errors.append(f"architecture index missing program authority marker: {marker}")

    build_plan = BUILD_PLAN.read_text(encoding="utf-8")
    for marker in ("Program masterplan:", "plan/MASTER_PLAN.md", "plan/ADVERSARIAL_CLOSURE_PASS.md", "subordinate to `docs/plan/MASTER_PLAN.md`"):
        if marker not in build_plan:
            errors.append(f"frontier build plan missing program authority marker: {marker}")

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print("Masterplan adversarial closure: FAIL")
        for error in errors:
            print(f" - {error}")
        return 1
    data = _load(CLOSURE)
    print(
        "Masterplan adversarial closure: OK "
        f"({len(data['closure_axes'])} axes, "
        f"{len(data['compound_campaigns'])} compound campaigns, "
        f"{len(data['work_package_coverage'])} work packages)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
