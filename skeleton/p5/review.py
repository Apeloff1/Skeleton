"""Whole-system adversarial review. Open findings stay open."""
from __future__ import annotations

from typing import Any

from skeleton.p3.foundation import P3Reject, admit as admit_p3
from skeleton.p4.production import P4Reject, admit as admit_p4
from skeleton.volumes.wave4.engine import VolumeReject, admit as admit_wave4, volume_ids

OPEN_FINDINGS = (
    {
        "id": "P5-P3-FOUNDATION-OPEN",
        "severity": "high",
        "plane": "p3",
        "detail": "six P3 foundation tasks remain landed_unpromoted",
    },
    {
        "id": "P5-P3-ENGINEERING-OPEN",
        "severity": "high",
        "plane": "p3",
        "detail": "six P3 engineering tasks remain landed_unpromoted",
    },
    {
        "id": "P5-P3T2-LIFECYCLE-OPEN",
        "severity": "high",
        "plane": "p3",
        "detail": "P3T2-LIFECYCLE-01 is in_progress; five sibling tasks are landed_unpromoted",
    },
    {
        "id": "P5-TRACE-CATALOGUE-DRIFT",
        "severity": "medium",
        "plane": "p2",
        "detail": "state-domain catalogue drift still fails the trace projection",
    },
    {
        "id": "P5-REPO-EDGE-STATUS",
        "severity": "medium",
        "plane": "p2",
        "detail": "BL-EDGE-HIST-SYS-019 status drift evidence_pending != planned",
    },
)


class ReviewReject(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def run_review() -> dict[str, Any]:
    probes = []
    probes.append(_expect_reject("p4-over-quota", lambda: admit_p4(
        "P4-FARM-01",
        {"task": "P4-FARM-01", "bound": 64, "evidence": "x", "quota": 999, "queue": "build"},
    ), P4Reject))
    probes.append(_expect_reject("p3-self-promotion", lambda: admit_p3(
        "P3-CONSTRUCTION-AUTHORITY-01",
        {"task": "P3-CONSTRUCTION-AUTHORITY-01", "bound": 8, "evidence": "x", "projection": True, "self_promoting": True},
    ), P3Reject))
    probes.append(_expect_reject("wave4-foreign", lambda: admit_wave4(volume_ids()[0], {"volume": "VOL-000"}), VolumeReject))
    probes.append(_expect_reject("p4-deprecated-serve", lambda: admit_p4(
        "P4-LIFECYCLE-01",
        {"task": "P4-LIFECYCLE-01", "bound": 8, "evidence": "x", "deprecated": True, "stage": "serve"},
    ), P4Reject))
    failed = [row for row in probes if not row["held"]]
    if failed:
        raise ReviewReject("probe regression:" + ",".join(row["id"] for row in failed))
    return {
        "probes_held": len(probes),
        "open_findings": list(OPEN_FINDINGS),
        "stored_prose": 0,
        "clean": False,
    }


def _expect_reject(probe_id: str, fn, exc_type: type[Exception]) -> dict[str, Any]:
    try:
        fn()
    except exc_type:
        return {"id": probe_id, "held": True}
    return {"id": probe_id, "held": False}
