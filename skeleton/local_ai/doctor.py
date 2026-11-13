"""Fail-closed local-AI doctor: structural health never certifies inference."""
from .health import health
from .config_schema import SCHEMA
from .fail_closed import guard_clipped


def doctor() -> dict:
    report = health()
    properties = SCHEMA.get("properties", {}) if isinstance(SCHEMA, dict) else {}
    report["schema_ok"] = isinstance(properties, dict) and "lora_rank" in properties
    try:
        guard_clipped(10.0)
        report["clipped_ok"] = True
    except Exception:
        report["clipped_ok"] = False
    report["doctor"] = (
        "passed"
        if report["healthy"] and report["schema_ok"] and report["clipped_ok"]
        and report.get("inference_ready") is True
        and report.get("readiness_evidence")
        else "failed"
    )
    return report
