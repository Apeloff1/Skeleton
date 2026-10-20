"""84-gate candidate evidence review and accountable remediation."""
from __future__ import annotations

from .production_quality import QualityGateError, _digest
from .production_deep_gates import _sha
from .production_studio_assurance import ALL_GATES, OWNERS as BASE_OWNERS
from .production_advanced_assurance import NAMES as ADV_NAMES, NEW_OWNERS
from .production_expanded_gates import SPECS, NAMES, OWNERS

ORDER = ALL_GATES + ADV_NAMES + NAMES


def verify_84_structure(report):
    if type(report) is not dict or set(report) != {
        "schema", "source_digest", "candidate_passed", "release_certified",
        "gates", "findings", "evidence_digest",
    } or report["schema"] != "game.candidate.production_84.v1":
        raise QualityGateError("84-gate schema mismatch")
    _sha(report["source_digest"], "advanced source digest")
    _sha(report["evidence_digest"], "advanced report digest")
    gates = report["gates"]
    if type(gates) is not list or len(gates) != 84 or report["release_certified"] is not False:
        raise QualityGateError("incomplete or falsely released candidate")
    if any(type(x) is not dict for x in gates):
        raise QualityGateError("quality gate records must be objects")
    if tuple(x.get("name") for x in gates) != ORDER:
        raise QualityGateError("gate ordering mismatch")
    findings = []
    for gate in gates:
        if (set(gate) != {"name", "passed", "findings", "evidence_digest"}
                or type(gate.get("passed")) is not bool
                or type(gate.get("findings")) is not list):
            raise QualityGateError("gate status malformed")
        if gate["passed"] is not (not gate["findings"]):
            raise QualityGateError("gate status inconsistent")
        _sha(gate["evidence_digest"], "individual gate digest")
        for finding in gate["findings"]:
            if (type(finding) is not dict
                    or set(finding) != {"gate", "code", "subject"}
                    or finding["gate"] != gate["name"]
                    or any(type(v) is not str or not v for v in finding.values())):
                raise QualityGateError("misattributed or invalid finding")
        findings.extend(gate["findings"])
    if (type(report["candidate_passed"]) is not bool
            or report["candidate_passed"] is not (not findings)
            or report["findings"] != findings
            or report["evidence_digest"] != _digest(gates)):
        raise QualityGateError("summary inconsistent with evidence")
    return {"gate_count": 84, "findings_count": len(findings),
            "source_sha256": report["source_digest"],
            "evidence_sha256": report["evidence_digest"],
            "production_approved": False}


def compare_84(before, after):
    verify_84_structure(before)
    verify_84_structure(after)
    improved, regressed = [], []
    for a, b in zip(before["gates"], after["gates"], strict=True):
        change = {"gate": a["name"], "before": len(a["findings"]),
                  "after": len(b["findings"])}
        if change["after"] < change["before"]:
            improved.append(change)
        elif change["after"] > change["before"]:
            regressed.append(change)
    return {"improved": improved, "regressed": regressed,
            "strict_pareto_improvement": bool(improved) and not regressed,
            "production_approved": False}


def queue_84(report, *, limit=256):
    from .production_frontier_assurance import _REVIEW_OWNERS
    verify_84_structure(report)
    if type(limit) is not int or not 1 <= limit <= 512:
        raise QualityGateError("invalid work limit")
    owners = {**_REVIEW_OWNERS, **BASE_OWNERS, **NEW_OWNERS, **OWNERS}
    work = [{"gate": x["gate"], "code": x["code"],
             "subject": x["subject"], "owner": owners[x["gate"]],
             "mutation_authorized": False}
            for x in report["findings"]]
    return {"items": work[:limit], "remaining": max(0, len(work)-limit),
            "source_sha256": report["source_digest"], "auto_repair": False}


def impact_84(report):
    verify_84_structure(report)
    depends = {"timing": "cinematics", "physics": "physics", "graph": "canon",
               "asset": "assets", "integrity": "session"}
    blocked = {x["name"] for x in report["gates"] if not x["passed"]}
    return {"affected": [{"gate": s.name, "upstream": depends[s.mode]}
                         for s in SPECS if s.name in blocked],
            "source_sha256": report["source_digest"], "mutation_authorized": False}
