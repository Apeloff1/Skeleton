"""Unified STU-TOOLS reporting — aggregate cards for CI / Merge Manager."""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

from skeleton.developer.gate_catalog import catalog_dict, catalog_fingerprint
from skeleton.developer.gate_verdict import gate_table
from skeleton.developer.stu_tools_pipeline import run_stu_tools_pipeline


def build_merge_card(pipeline_result: Mapping[str, Any]) -> Dict[str, Any]:
    """Compact card for Lana / Merge Manager fail-closed review."""
    verdict = pipeline_result.get("verdict") or {}
    sections = pipeline_result.get("sections") or {}
    section_ok = {name: int((payload or {}).get("ok") or 0) for name, payload in sections.items()}
    return {
        "kind": "stu-tools-merge-card",
        "ok": int(pipeline_result.get("ok") or 0),
        "banner": pipeline_result.get("banner"),
        "paths": list(pipeline_result.get("paths") or []),
        "section_ok": section_ok,
        "blocking": list(verdict.get("blocking") or []),
        "fingerprint": verdict.get("fingerprint"),
        "catalog_fp": catalog_fingerprint(),
        "stored_prose": int(pipeline_result.get("stored_prose") or 0),
        "duration_ms": pipeline_result.get("duration_ms"),
    }


def build_coverage_card() -> Dict[str, Any]:
    cat = catalog_dict()
    return {
        "kind": "stu-tools-coverage-card",
        "gate_count": cat["count"],
        "sev1": cat["sev1"],
        "sev2": cat["sev2"],
        "paths": sorted(cat["by_path"].keys()),
        "catalog_fp": catalog_fingerprint(),
        "stored_prose": 0,
    }


def run_stu_tools_ci_bundle(
    *,
    paths: Optional[List[str]] = None,
    doctor_card: Optional[Mapping[str, Any]] = None,
    artefacts: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """One-shot bundle: pipeline + merge card + coverage + gate table."""
    started = time.time()
    pipeline = run_stu_tools_pipeline(
        paths=paths,
        doctor_card=doctor_card,
        artefacts=artefacts,
    )
    # Optionally include cockpit path by reusing doctor cockpit knobs
    from skeleton.developer.cockpit_gates import run_cockpit_gates
    from skeleton.developer.doctor_cockpit_bridge import run_doctor_cockpit_bridge
    from skeleton.developer.gate_verdict import merge_verdicts
    from skeleton.developer.stu_tools_pipeline import _verdict_from_dict

    cockpit = run_cockpit_gates()
    bridge = run_doctor_cockpit_bridge(doctor_card=doctor_card)
    merged = merge_verdicts(
        "stu-tools-ci-bundle",
        [
            _verdict_from_dict(pipeline.get("verdict") or {}),
            _verdict_from_dict(cockpit.get("verdict") or {}),
            _verdict_from_dict(bridge.get("verdict") or {}),
        ],
    )
    ok = 1 if merged.ok and pipeline.get("ok") and cockpit.get("ok") and bridge.get("ok") else 0
    bundle = {
        "kind": "stu-tools-ci-bundle",
        "ok": ok,
        "banner": merged.banner if ok else merged.banner,
        "pipeline": pipeline,
        "cockpit": cockpit,
        "bridge": bridge,
        "merge_card": build_merge_card(pipeline),
        "coverage": build_coverage_card(),
        "gate_table": gate_table(merged),
        "verdict": merged.to_dict(),
        "duration_ms": round((time.time() - started) * 1000, 3),
        "stored_prose": 0,
    }
    return bundle


def render_ci_bundle(bundle: Mapping[str, Any]) -> str:
    lines = [
        "STU-TOOLS CI Bundle",
        f"  ok={bundle.get('ok')}  {bundle.get('banner')}",
        f"  catalog_fp={((bundle.get('coverage') or {}).get('catalog_fp'))}",
        f"  duration_ms={bundle.get('duration_ms')}",
    ]
    mc = bundle.get("merge_card") or {}
    lines.append(f"  merge_blocking={mc.get('blocking')}")
    return "\n".join(lines)


__all__ = [
    "build_merge_card",
    "build_coverage_card",
    "run_stu_tools_ci_bundle",
    "render_ci_bundle",
]
