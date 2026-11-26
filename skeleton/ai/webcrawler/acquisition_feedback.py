"""Bounded, replayable acquisition economics and conservative transport pacing.

Original Dragon algorithm, informed by latency/host queue feedback controllers.
One observation per charged request, including uncertain dispatch recovery.
No content strings, headers, credentials, or unconstrained target URLs enter
this ledger. Measurements do not create authorization or shrink a server hold.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Iterable
from urllib.parse import urlsplit

from .dragon_curriculum_trace import validate_receipt

MAX_OBSERVATIONS = 128
MAX_BYTES = 2_097_152
MAX_LATENCY_BUCKET = 240
LATENCY_QUANTUM = .25
MAX_PACING = 120.
_HOST = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?\Z")
_OUTCOMES = frozenset({"captured", "duplicate", "discovered", "robots", "redirect",
                       "retry", "error", "rejected", "source_rights_restricted",
                       "interrupted_dispatch", "deferred"})
_USEFUL = frozenset({"captured", "discovered"})
_FAILURE = frozenset({"retry", "error", "interrupted_dispatch"})
_FIELDS = {"request", "host", "kind", "status", "latency_bucket",
           "charged_bytes", "uncertain_bytes", "event_sequence", "source_id", "curriculum"}


@dataclass(frozen=True)
class HostEconomics:
    host: str
    observations: int
    successes: int
    failures: int
    novelty_observations: int
    mean_latency_seconds: float
    tail_latency_seconds: float
    mean_cost_bytes: float
    reliability: float
    novelty_probability: float
    uncertainty: float
    conservative_delay: float


def quantize_latency(seconds: float) -> int:
    if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds) or seconds < 0):
        raise ValueError("invalid measured acquisition latency")
    return max(1, min(MAX_LATENCY_BUCKET, math.ceil(seconds / LATENCY_QUANTUM)))


def settled_observation(*, request: int, url: str, kind: str, status: int | None,
                        latency_bucket: int | None, charged_bytes: int, uncertain_bytes: int,
                        event_sequence: int, source_id: str | None = None,
                        curriculum: dict | None = None) -> dict:
    host = urlsplit(url).hostname
    row = {"request": request, "host": host, "kind": kind, "status": status,
           "latency_bucket": latency_bucket, "charged_bytes": charged_bytes,
           "uncertain_bytes": uncertain_bytes, "event_sequence": event_sequence,
           "source_id": source_id, "curriculum": curriculum}
    _validate(row)
    return row


def _validate(row: object) -> None:
    if not isinstance(row, dict) or set(row) != _FIELDS:
        raise ValueError("acquisition measurement fields mismatch")
    if (type(row["request"]) is not int or not 1 <= row["request"] <= MAX_OBSERVATIONS
            or not isinstance(row["host"], str) or not _HOST.fullmatch(row["host"])
            or row["kind"] not in _OUTCOMES
            or type(row["event_sequence"]) is not int or not 1 <= row["event_sequence"] <= 10000):
        raise ValueError("invalid acquisition measurement identity")
    for field in ("charged_bytes", "uncertain_bytes"):
        if type(row[field]) is not int or not 0 <= row[field] <= MAX_BYTES:
            raise ValueError("invalid acquisition byte accounting")
    source = row["source_id"]
    if source is not None and (row["kind"] != "captured" or not isinstance(source, str)
                               or not re.fullmatch(r"[a-f0-9]{64}", source)):
        raise ValueError("invalid acquisition source identity")
    if row["curriculum"] is not None:
        validate_receipt(row["curriculum"])
        if row["kind"] == "captured" and row["curriculum"]["phase"] != "content":
            raise ValueError("policy acquisition cannot earn capture credit")
    status, latency = row["status"], row["latency_bucket"]
    if status is None:
        if latency is not None and (type(latency) is not int or not 1 <= latency <= MAX_LATENCY_BUCKET):
            raise ValueError("invalid failed-request timing")
        if row["charged_bytes"] or not row["uncertain_bytes"] or row["kind"] not in _FAILURE:
            raise ValueError("invalid uncertain measurement")
    elif (type(status) is not int or not 100 <= status <= 599
          or type(latency) is not int or not 1 <= latency <= MAX_LATENCY_BUCKET
          or row["uncertain_bytes"]):
        raise ValueError("invalid settled transport measurement")


def validate_measurements(rows: object, *, usage: dict, pending: dict | None,
                          sequence: int, hosts: Iterable[str]) -> None:
    if not isinstance(rows, list) or len(rows) > MAX_OBSERVATIONS:
        raise ValueError("acquisition ledger bound exceeded")
    allowed = frozenset(hosts)
    request_count = usage["requests"] - int(pending is not None)
    if len(rows) != request_count:
        raise ValueError("acquisition ledger request conservation failed")
    charged = uncertain = previous_sequence = 0
    for index, row in enumerate(rows, 1):
        _validate(row)
        if (row["host"] not in allowed or row["request"] != index
                or not previous_sequence < row["event_sequence"] <= sequence):
            raise ValueError("acquisition ledger order or scope invalid")
        previous_sequence = row["event_sequence"]
        charged += row["charged_bytes"]
        uncertain += row["uncertain_bytes"]
    if pending is not None:
        uncertain += pending["limit"]
    if charged != usage["bytes"] or uncertain != usage["reserved_bytes"]:
        raise ValueError("acquisition ledger byte conservation failed")


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)]


def _negative_outcome(row: dict) -> bool:
    # A successful HTTP envelope is not a successful acquisition. An
    # interstitial, denied source-use outcome or rejected representation
    # must not earn positive reliability or accelerate subsequent pacing.
    return (row["kind"] in _FAILURE
            or row["kind"] in {"rejected", "source_rights_restricted"}
            or row["status"] is None or row["status"] >= 400)


def host_economics(rows: list[dict], host: str, *, floor: float = .25) -> HostEconomics:
    if (not isinstance(rows, list) or len(rows) > MAX_OBSERVATIONS
            or not isinstance(host, str) or not _HOST.fullmatch(host)
            or isinstance(floor, bool) or not isinstance(floor, (int, float))
            or not math.isfinite(floor) or not .25 <= floor <= 86400):
        raise ValueError("invalid acquisition economics inputs")
    samples = [row for row in rows if row["host"] == host]
    # Last 16 measurements bound the controller's memory. The full ledger
    # remains available for custody and cumulative request/byte conservation.
    recent = samples[-16:]
    durations = [row["latency_bucket"] * LATENCY_QUANTUM for row in recent
                 if row["latency_bucket"] is not None]
    successful = sum(not _negative_outcome(row)
                     and 200 <= row["status"] < 400 for row in recent)
    failure = sum(_negative_outcome(row) for row in recent)
    content_rows = [row for row in recent if row["kind"] not in {"robots", "redirect"}]
    novelty = sum(row["kind"] in _USEFUL for row in content_rows)
    reliability = (2 + successful) / (4 + len(recent))
    useful_probability = (1 + novelty) / (2 + len(content_rows))
    uncertainty = 1 / math.sqrt(1 + len(content_rows))
    mean = .25
    delay = float(floor)
    for row in recent:
        # Unknown-outcome recovery is censored, not an observed 60s sample.
        # Its multiplicative failure penalty remains, but do not invent latency.
        duration = row["latency_bucket"] * LATENCY_QUANTUM if row["latency_bucket"] is not None else mean
        mean = .75 * mean + .25 * duration
        # Queue-depth target is exactly one; a shorter failed response may
        # not speed the crawler up. Robust tail latency and multiplicative
        # increase avoid punishing a host with bursts after one fast result.
        target = max(floor, 1.25 * max(0., mean - LATENCY_QUANTUM))
        if _negative_outcome(row):
            delay = max(delay, min(MAX_PACING, delay * 1.5), target)
        else:
            delay = max(floor, .85 * delay + .15 * target)
        delay = max(floor, min(MAX_PACING, delay))
    tail = _percentile(durations, .90)
    # Delay is additional policy, not a maximum on publisher requirements.
    delay = max(floor, delay, min(MAX_PACING, tail))
    cost = (65536 + sum(row["charged_bytes"] + row["uncertain_bytes"] for row in content_rows)) / (1 + len(content_rows))
    return HostEconomics(host, len(samples), successful, failure, novelty,
                         round(mean, 6), round(tail, 6), round(cost, 3),
                         round(reliability, 8), round(useful_probability, 8),
                         round(uncertainty, 8), round(delay, 6))


def portfolio_summary(rows: list[dict], hosts: Iterable[str], *, floor: float) -> dict:
    from dataclasses import asdict
    return {"settled_requests": len(rows),
            "charged_bytes": sum(row["charged_bytes"] for row in rows),
            "uncertain_bytes": sum(row["uncertain_bytes"] for row in rows),
            "hosts": {host: asdict(host_economics(rows, host, floor=floor)) for host in hosts},
            "network_authority_expanded": False}
