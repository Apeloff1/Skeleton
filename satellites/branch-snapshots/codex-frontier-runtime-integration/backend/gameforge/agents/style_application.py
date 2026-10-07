from __future__ import annotations
from typing import Any, Dict, Optional

from gameforge.rooms.coder_pool import CODER_POOL, CoderStyle


class StyleApplicator:
    def get_style(self, coder_key: str) -> Optional[CoderStyle]:
        return CODER_POOL.get(coder_key)

    def apply_to_generation(
        self, base_params: Dict[str, Any], coder_key: str, strength: float = 1.0
    ) -> Dict[str, Any]:
        style = self.get_style(coder_key)
        params = dict(base_params)
        if not style:
            return params
        inf = style.influence
        s = max(0.0, min(1.0, strength))

        if inf.get("simplicity", 0) > 0.6:
            params["prefer_simple_structures"] = True
            params["max_function_lines"] = int(params.get("max_function_lines", 80) * (1.0 - 0.4 * s))
        if inf.get("performance_focus", 0) > 0.7:
            params["performance_focus"] = True
            params["prefer_data_oriented"] = inf.get("data_oriented", 0) > 0.5
        if inf.get("abstraction", 0) < -0.5:
            params["prefer_flat_structures"] = True
            params["max_inheritance_depth"] = 1
        if inf.get("comment_density", 0) > 0.6:
            params["comment_density"] = 0.3 + 0.5 * s * inf["comment_density"]
        if inf.get("data_oriented", 0) > 0.6:
            params["prefer_data_oriented"] = True
        if inf.get("observability", 0) > 0.6:
            params["require_metrics_hooks"] = True
        params["active_coder"] = coder_key
        params["style_name"] = style.style_name
        return params

    def build_style_prompt_section(self, coder_key: str) -> str:
        style = self.get_style(coder_key)
        if not style:
            return "ACTIVE STYLE: standard"
        kws = ", ".join(style.keywords)
        return (
            f"ACTIVE STYLE: {style.coder_name} — {style.style_name}\n"
            f"GUIDANCE: {style.description}\n"
            f"KEYWORDS: {kws}\n"
            f"Apply this style to structure, naming, and tradeoffs."
        )
