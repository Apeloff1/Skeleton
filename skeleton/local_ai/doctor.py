"""
Doctor cycle for local AI. Runs health, schema check, and clipped-G validation.
"""
from .health import health
from .config_schema import SCHEMA
from .fail_closed import guard_clipped

def doctor() -> dict:
    report = health()
    report["schema_ok"] = "lora_rank" in SCHEMA["properties"]
    try:
        guard_clipped(10.0)
        report["clipped_ok"] = True
    except Exception:
        report["clipped_ok"] = False
    report["doctor"] = "passed" if report["healthy"] and report["schema_ok"] and report["clipped_ok"] else "failed"
    return report
