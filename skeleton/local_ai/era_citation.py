"""
Bind eras on plan, cut, speak, and forge. Force era_bind citations on GameForgeRun.execute.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

ERA = "HOUSE_ERA"
_ACTS = ("plan", "cut", "speak", "forge")


def process(data: dict) -> dict:
    refused = admit("era_citation", data)
    if refused:
        return refused
    if "era" in data and data["era"] != ERA:
        return {"ok": False, "error": "era is pinned", "card": "era_citation", "era": ERA}
    act = data.get("act")
    if act is not None and act not in _ACTS:
        return {"ok": False, "error": "unknown act", "card": "era_citation", "era": ERA}
    body: dict = {"era": ERA}
    if act is not None:
        body["act"] = act
    return stamp("era_citation", data, body)
