"""
Mixture-of-depths distinct from mixture-of-experts. PR 49 owns MoD. cortex/moe.py owns MoE. Do not fork either.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

MOD = "PR49"
MOE = "cortex/moe.py"


def process(data: dict) -> dict:
    refused = admit("mod_depth", data)
    if refused:
        return refused
    owner = data.get("owner")
    if owner is not None and owner not in (MOD, MOE):
        return {
            "ok": False,
            "error": "owner is already bound",
            "card": "mod_depth",
            "mod": MOD,
            "moe": MOE,
        }
    body: dict = {"mod": MOD, "moe": MOE}
    if owner is not None:
        body["owner"] = owner
    return stamp("mod_depth", data, body)
