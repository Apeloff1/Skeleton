"""E2E smoke runner for critical paths.
Run with: python -m skeleton.jeeves.studio.e2e_smoke
"""
from __future__ import annotations
from typing import Any

def smoke() -> dict[str, Any]:
    results: dict[str, Any] = {"ok": True, "checks": []}
    # UTC compat
    try:
        from skeleton.compat_datetime import UTC
        results["checks"].append({"name": "utc_compat", "ok": UTC is not None})
    except Exception as exc:
        results["checks"].append({"name": "utc_compat", "ok": False, "error": type(exc).__name__})
        results["ok"] = False
    # studio conductor (may fail if deps missing)
    try:
        from skeleton.jeeves.studio.integrated_studio import IntegratedStudio
        s = IntegratedStudio()
        r = s.run_pipeline("smoke brief")
        results["checks"].append({"name": "integrated_studio", "ok": bool(r.get("ok"))})
    except Exception as exc:
        results["checks"].append({"name": "integrated_studio", "ok": False, "error": type(exc).__name__})
    return results

if __name__ == "__main__":
    import json
    print(json.dumps(smoke(), indent=2))
