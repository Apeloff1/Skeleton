"""
🔗 BOOT-TIME WIRING — hand retry-exhausted forge artifacts to the polish loop.

routes/game_kb.py's ``_llm_json`` re-rolls up to N attempts and returns the best
scoring artifact even when it is still under the 95 gate. Editing that ~50KB file
via the file API is unsafe, so this module wraps ``_llm_json`` at boot instead:
after the original loop returns an under-gate best attempt, we run the targeted
polish loop (routes/quality_polish.py) against it — a rewrite guided by the
auditor's feedback rather than another blind roll.

Importing this module applies the patch (idempotent). It is imported from
routes/quality_control.py, which is already registered in core/routes_registry.py.
"""
from __future__ import annotations

import json

_WRAPPED_ATTR = "_polish_wrapped"
_SIM_STAGES = {"physics", "tileset", "cinematics", "procedural"}


def _wrap() -> bool:
    """Wrap game_kb._llm_json with the polish fallback. Returns True if applied."""
    try:
        from routes import game_kb as gkb
    except Exception:
        return False
    if getattr(gkb, _WRAPPED_ATTR, False):
        return True
    original = gkb._llm_json

    async def _llm_json_polished(prompt, system, required_key, attempts=3,
                                 pid=None, stage=None):
        data, routed = await original(prompt, system, required_key,
                                      attempts=attempts, pid=pid, stage=stage)
        try:
            if not (isinstance(data, dict) and required_key in data):
                return data, routed
            q = data.get("_quality") or {}
            score = int(q.get("score", 0) or 0)
            from routes.quality import MIN_QUALITY
            if score >= MIN_QUALITY:
                return data, routed  # already cleared the gate

            from routes.quality_polish import polish_pass
            sim = bool(stage and stage in _SIM_STAGES)
            polished = await polish_pass(required_key, json.dumps(data),
                                         simulate=sim, artifact=data)
            pdata = gkb._extract_json(polished.get("content", ""))
            if pdata and required_key in pdata and polished.get("score", 0) > score:
                pdata["_quality"] = {"score": polished["score"],
                                     "passed": polished["passed"],
                                     "polished": True,
                                     "passes": polished.get("passes", []),
                                     "enforced": MIN_QUALITY}
                if sim and polished.get("simulation") and pid:
                    try:
                        from core.forge_validator import cache_trace
                        cache_trace(pid, stage, polished["simulation"])  # Item 25
                    except Exception:
                        pass
                return pdata, routed
        except Exception:
            pass  # never break a forge because the polish fallback failed
        return data, routed

    gkb._llm_json = _llm_json_polished
    setattr(gkb, _WRAPPED_ATTR, True)
    return True


APPLIED = _wrap()
