"""Deterministic read-only report doctor: no claims from absent evidence."""
from __future__ import annotations
from .canonical import encode, decode, sha256
from .errors import deny
from .report import REPORT_SCHEMA


def inspect_report(raw: bytes) -> dict:
    parsed = decode(raw)
    if type(parsed) is not dict or parsed.get("schema") != REPORT_SCHEMA:
        deny("doctor-schema")
    model = parsed.get("model")
    metrics = parsed.get("metrics")
    if type(model) is not dict or type(metrics) is not dict:
        deny("doctor-metrics")
    total = metrics.get("cases_total")
    passed = metrics.get("cases_passed")
    cases = parsed.get("cases")
    if type(total) is not int or type(passed) is not int or not 0 <= passed <= total:
        deny("doctor-count")
    if type(cases) is not list or len(cases) != total:
        deny("doctor-case-count")
    count = sum(row.get("passed") is True for row in cases if type(row) is dict)
    if count != passed:
        deny("doctor-count-conflict")
    if parsed.get("release_certified") is not False or parsed.get("ci_qualified") is not False:
        deny("doctor-release-claim")
    return {
        "schema": "skeleton.native-qualification.doctor.v1",
        "sha256": sha256(raw),
        "report_canonical": encode(parsed) == raw,
        "cases_total": total,
        "cases_passed": passed,
        "policy_threshold_met": parsed.get("policy_threshold_met") is True,
        "release_certified": False,
        "ci_qualified": False,
    }
