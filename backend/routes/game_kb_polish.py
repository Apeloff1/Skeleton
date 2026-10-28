"""
🔗 FORGE POLISH WIRING — attaches the targeted polish loop to every stage forge
WITHOUT editing the (very large) routes/game_kb.py.

How it works
------------
Every forge in ``routes/game_kb.py`` resolves ``_llm_json`` from its module globals
at CALL time. This module wraps that attribute with a fallback: when the forge's
own re-roll attempts finish below the 95 gate, the best attempt is handed to
``routes.quality_polish.polish_pass`` — a targeted rewrite against the auditor's
feedback — and the polished artifact is returned if it scores higher.

Applied at import time. Imported by ``routes/quality_control`` (already registered
in core/routes_registry.py), so the wiring is live on every boot. Importing this
module is idempotent — a second import leaves the original wrap in place.
"""
from __future__ import annotations

import json

import routes.game_kb as _gkb
from routes.quality import MIN_QUALITY
from routes.quality_polish import polish_pass

_SIM_STAGES = {"physics", "tileset", "cinematics", "procedural"}

if not getattr(_gkb, "_polish_wired", False):
    _orig_llm_json = _gkb._llm_json

    async def _llm_json_with_polish(prompt: str, system: str, required_key: str,
                                    attempts: int = 3, pid: str | None = None,
                                    stage: str | None = None):
        """Drop-in wrapper for game_kb._llm_json: identical contract, plus a
        targeted polish fallback when all re-rolls land under the 95 gate."""
        data, routed = await _orig_llm_json(prompt, system, required_key,
                                            attempts=attempts, pid=pid, stage=stage)
        try:
            q = (data or {}).get("_quality") or {}
            score = q.get("score", -1)
            if data is None or not isinstance(score, (int, float)) or score >= MIN_QUALITY:
                return data, routed
            clean = {k: v for k, v in data.items() if k != "_quality"}
            polished = await polish_pass(required_key, json.dumps(clean),
                                         simulate=bool(stage and stage in _SIM_STAGES),
                                         artifact=clean)
            pdata = _gkb._extract_json(polished.get("content", ""))
            if pdata and required_key in pdata and polished.get("score", 0) > score:
                pdata["_quality"] = {"score": polished["score"], "passed": polished["passed"],
                                     "polished": True, "passes": polished.get("passes", []),
                                     "enforced": MIN_QUALITY}
                return pdata, routed
        except Exception:
            pass  # wiring is best-effort — never break a forge over polish
        return data, routed

    _gkb._llm_json = _llm_json_with_polish
    _gkb._polish_wired = True
