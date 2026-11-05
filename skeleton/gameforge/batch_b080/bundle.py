"""B080 — Release quality evidence bundle.

Success criterion: "Every release packages machine-readable
test/perf/security/provenance evidence."

:class:`ReleaseEvidenceBundle` collects four mandatory sections — ``tests``
(counts + B072 compact evidence for failures), ``perf`` (B074 gate results per
target), ``compat`` (B079 matrix dict), ``security`` (caller-supplied scan
summary) — plus ``provenance`` (commit, builder, artifact digests). ``build()``
refuses to emit a bundle with missing sections, failing tests without
evidence, or non-green perf/compat unless an explicit signed-off waiver names
it. Output is canonical JSON with a SHA-256 seal checked by
:func:`verify_bundle`.
"""
from __future__ import annotations

import hashlib
import json
from typing import Dict, List, Mapping, Optional

from skeleton.gameforge.batch_b074 import GateResult
from skeleton.gameforge.batch_b079 import CompatMatrix

SCHEMA = "gameforge.release-evidence/v1"
SECTIONS = ("tests", "perf", "compat", "security", "provenance")


class BundleError(ValueError):
    pass


def _canon(doc) -> str:
    return json.dumps(doc, sort_keys=True, separators=(",", ":"))


class ReleaseEvidenceBundle:
    def __init__(self, version: str) -> None:
        if not version:
            raise BundleError("version required")
        self.version = version
        self.sections: Dict[str, dict] = {}
        self.waivers: Dict[str, str] = {}

    def add_tests(self, passed: int, failed: int, failure_evidence: Mapping[str, str]) -> None:
        if passed < 0 or failed < 0:
            raise BundleError("negative counts")
        if failed != len(failure_evidence):
            raise BundleError("every failure needs replay evidence")
        self.sections["tests"] = {"passed": passed, "failed": failed,
                                  "evidence": dict(sorted(failure_evidence.items()))}

    def add_perf(self, results: List[GateResult]) -> None:
        self.sections["perf"] = {r.target: {"passed": r.passed, "violations": list(r.violations),
                                            "measured": dict(r.measured)} for r in results}

    def add_compat(self, matrix: CompatMatrix) -> None:
        self.sections["compat"] = matrix.to_dict()

    def add_security(self, scanner: str, critical: int, high: int, report_digest: str) -> None:
        self.sections["security"] = {"scanner": scanner, "critical": critical, "high": high,
                                     "report_digest": report_digest}

    def add_provenance(self, commit: str, builder: str, artifacts: Mapping[str, str]) -> None:
        if len(commit) < 7:
            raise BundleError("commit sha required")
        if not artifacts:
            raise BundleError("at least one artifact digest required")
        self.sections["provenance"] = {"commit": commit, "builder": builder,
                                       "artifacts": dict(sorted(artifacts.items()))}

    def waive(self, section: str, approver: str, reason: str) -> None:
        if section not in SECTIONS or not approver.strip() or not reason.strip():
            raise BundleError("waiver needs a known section, approver and reason")
        self.waivers[section] = f"{approver}: {reason}"

    def _blockers(self) -> List[str]:
        b = [f"missing section {s}" for s in SECTIONS if s not in self.sections]
        if b:
            return b
        if self.sections["tests"]["failed"]:
            b.append("tests")
        if any(not v["passed"] for v in self.sections["perf"].values()) or not self.sections["perf"]:
            b.append("perf")
        if any(self.sections["compat"]["problems"].values()):
            b.append("compat")
        if self.sections["security"]["critical"]:
            b.append("security")
        return [x for x in b if x not in self.waivers]

    def build(self) -> str:
        blockers = self._blockers()
        if blockers:
            raise BundleError("release blocked: " + ", ".join(blockers))
        body = {"schema": SCHEMA, "version": self.version, "sections": self.sections,
                "waivers": dict(sorted(self.waivers.items()))}
        seal = hashlib.sha256(_canon(body).encode()).hexdigest()
        return _canon({"body": body, "seal": seal})


def verify_bundle(blob: str) -> dict:
    try:
        doc = json.loads(blob)
        body, seal = doc["body"], doc["seal"]
    except (ValueError, KeyError, TypeError) as exc:
        raise BundleError("malformed bundle") from exc
    if hashlib.sha256(_canon(body).encode()).hexdigest() != seal:
        raise BundleError("seal mismatch")
    if body.get("schema") != SCHEMA or set(body["sections"]) != set(SECTIONS):
        raise BundleError("schema/sections invalid")
    return body
