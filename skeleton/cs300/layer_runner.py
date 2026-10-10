"""Executable CS-300 layers. One adversary per stratum. stored_prose stays 0."""
from __future__ import annotations

import hashlib
import json
from typing import Any

STRATA = {
    1: "computability",
    2: "indexing",
    3: "types",
    4: "compiler",
    5: "runtime",
    6: "kernel",
    7: "concurrency",
    8: "distributed",
    9: "network",
    10: "storage",
    11: "database",
    12: "stream",
    13: "coding",
    14: "crypto",
    15: "formal",
    16: "architecture",
    17: "recovery",
    18: "observe",
    19: "supply",
    20: "privacy",
    21: "numeric",
    22: "accelerator",
    23: "hetero",
    24: "cloud",
    25: "realtime",
    26: "graphics",
    27: "quantum",
    28: "neuro",
    29: "autonomic",
    30: "finality",
}


class LayerReject(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def layer_ids() -> list[str]:
    return [f"CS300-{i:03d}" for i in range(1, 301)]


def stratum_of(layer_id: str) -> int:
    ordinal = int(layer_id.rsplit("-", 1)[1])
    if not 1 <= ordinal <= 300:
        raise LayerReject("ordinal")
    return (ordinal - 1) // 10 + 1


def admit(layer_id: str, card: dict[str, Any]) -> dict[str, Any]:
    if layer_id not in set(layer_ids()):
        raise LayerReject("unknown layer")
    if not isinstance(card, dict) or card.get("layer") != layer_id:
        raise LayerReject("identity mismatch")
    if card.get("stored_prose") not in (0, None):
        raise LayerReject("stored prose")
    if not isinstance(card.get("bound"), int) or not 1 <= card["bound"] <= 1024:
        raise LayerReject("bound")
    if card.get("evidence") in (None, "", [], {}):
        raise LayerReject("missing evidence")
    stratum = stratum_of(layer_id)
    _gate(stratum, card)
    if layer_id == "CS300-300" and card.get("finality") in (None, ""):
        raise LayerReject("finality")
    body = {"layer": layer_id, "stratum": stratum, "bound": card["bound"]}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "layer": layer_id,
        "stratum": f"CS300-S{stratum:02d}",
        "family": STRATA[stratum],
        "digest": digest,
        "admitted": True,
        "stored_prose": 0,
    }


def _gate(stratum: int, card: dict[str, Any]) -> None:
    if stratum == 1 and card.get("halt_claim") is not False:
        raise LayerReject("halt claim")
    if stratum == 2 and (not isinstance(card.get("fanout"), int) or card["fanout"] > card["bound"]):
        raise LayerReject("fanout")
    if stratum == 3 and card.get("sound") is not True:
        raise LayerReject("unsound")
    if stratum == 4 and card.get("ir") in (None, ""):
        raise LayerReject("missing ir")
    if stratum == 5 and card.get("sandbox") is not True:
        raise LayerReject("sandbox")
    if stratum == 6 and card.get("privilege") != "user":
        raise LayerReject("privilege")
    if stratum == 7 and card.get("race_free") is not True:
        raise LayerReject("race")
    if stratum == 8 and (not isinstance(card.get("quorum"), int) or card["quorum"] > card["bound"]):
        raise LayerReject("quorum")
    if stratum == 9 and card.get("checksum") in (None, ""):
        raise LayerReject("checksum")
    if stratum == 10 and card.get("durable") is not True:
        raise LayerReject("durability")
    if stratum == 11 and card.get("isolation") not in {"ru", "rc", "rr", "ser"}:
        raise LayerReject("isolation")
    if stratum == 12 and card.get("watermark") in (None, ""):
        raise LayerReject("watermark")
    if stratum == 13 and (not isinstance(card.get("rate"), int) or card["rate"] > card["bound"]):
        raise LayerReject("rate")
    if stratum == 14 and (card.get("nonce") in (None, "") or card.get("secret") not in (None, "")):
        raise LayerReject("crypto")
    if stratum == 15 and card.get("proof_id") in (None, ""):
        raise LayerReject("proof")
    if stratum == 16 and (not isinstance(card.get("coupling"), int) or card["coupling"] > card["bound"]):
        raise LayerReject("coupling")
    if stratum == 17 and card.get("checkpoint") in (None, ""):
        raise LayerReject("checkpoint")
    if stratum == 18 and (not isinstance(card.get("sample"), int) or card["sample"] > card["bound"]):
        raise LayerReject("sample")
    if stratum == 19 and card.get("unsigned") is not False:
        raise LayerReject("unsigned")
    if stratum == 20 and card.get("purpose") in (None, ""):
        raise LayerReject("purpose")
    if stratum == 21 and card.get("nan_policy") != "fail":
        raise LayerReject("nan")
    if stratum == 22 and (not isinstance(card.get("occupancy"), int) or card["occupancy"] > card["bound"]):
        raise LayerReject("occupancy")
    if stratum == 23 and card.get("device") in (None, ""):
        raise LayerReject("device")
    if stratum == 24 and (not isinstance(card.get("cold_start"), int) or card["cold_start"] > card["bound"]):
        raise LayerReject("cold start")
    if stratum == 25 and card.get("deadline") in (None, ""):
        raise LayerReject("deadline")
    if stratum == 26 and (not isinstance(card.get("frame"), int) or card["frame"] > card["bound"]):
        raise LayerReject("frame")
    if stratum == 27 and (not isinstance(card.get("decoherence"), int) or card["decoherence"] > card["bound"]):
        raise LayerReject("decoherence")
    if stratum == 28 and (not isinstance(card.get("spikes"), int) or card["spikes"] > card["bound"]):
        raise LayerReject("spikes")
    if stratum == 29 and card.get("budget") in (None, ""):
        raise LayerReject("budget")
    if stratum == 30 and card.get("reproduction") in (None, ""):
        raise LayerReject("reproduction")
