"""
Mobile bank card. Speculative RAG, SSE, bench GPU, HF import stay dark on mobile.
Bank card stays green.
"""
from __future__ import annotations

from .seam_runtime import admit, stamp

DEFAULTS = {
    "speculative_rag": False,
    "sse": False,
    "bench_gpu": False,
    "hf_import": False,
    "bank_green": True,
}
_DARK = ("speculative_rag", "sse", "bench_gpu", "hf_import")


def get_mobile_defaults() -> dict:
    return DEFAULTS.copy()


def process(data: dict) -> dict:
    refused = admit("mobile_bank_card", data)
    if refused:
        return refused
    if any(data.get(flag) is True for flag in _DARK):
        return {
            "ok": False,
            "error": "mobile flag stays dark",
            "card": "mobile_bank_card",
            "defaults": dict(DEFAULTS),
        }
    if "bank_green" in data and data["bank_green"] is not True:
        return {
            "ok": False,
            "error": "bank card stays green",
            "card": "mobile_bank_card",
            "defaults": dict(DEFAULTS),
        }
    return stamp("mobile_bank_card", data, {"defaults": DEFAULTS})
