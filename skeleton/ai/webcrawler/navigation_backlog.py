"""Bounded, checkpoint-owned discovery inventory and advisory navigation discourse.

No network, model execution, credentials, authority, or source promotion lives
here. CrawlRun is the sole dispatcher. Jeeves' deterministic objective delegate
and Dragon's companion profile deliberate over pre-admitted URL metadata only.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
from urllib.parse import unquote, urlsplit

from .dragon_companion import companion_priority

MAX_RECORDS = 1024
MAX_BYTES = 384 * 1024
KINDS = frozenset({"seed", "robots_sitemap", "sitemap_urlset", "sitemap_index",
                   "structured", "document_link", "http_link"})
COUNTERS = ("observations", "outside_policy", "capacity_omissions", "circuit_held",
            "depth_held", "promoted", "retired", "parser_capped")
_TERMS = re.compile(r"[^\W_]{2,64}", re.UNICODE)


def _encoded(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_encoded(value)).hexdigest()


def new_backlog():
    return {"records": {}, "counts": dict.fromkeys(COUNTERS, 0), "last_discourse": None}


def count(ledger, name):
    if name not in COUNTERS:
        raise ValueError("unknown navigation observation counter")
    ledger["counts"][name] = min(1_000_000_000, ledger["counts"][name] + 1)


def record_for(ledger, url):
    return ledger["records"].get(hashlib.sha256(url.encode("utf-8")).hexdigest())


def observe(ledger, *, url, parent, depth, kind):
    """Keep a unique target and bounded provenance; never imply authorization."""
    if kind not in KINDS:
        raise ValueError("unknown discovery relation")
    count(ledger, "observations")
    records = ledger["records"]
    identity = hashlib.sha256(url.encode("utf-8")).hexdigest()
    previous = records.get(identity)
    if previous is not None:
        previous["observations"] = min(1_000_000_000, previous["observations"] + 1)
        if depth < previous["depth"]:
            previous["depth"] = depth
            previous["parent_url"] = parent
            previous["kind"] = kind
        if kind not in previous["relations"]:
            previous["relations"] = sorted(set(previous["relations"]) | {kind})
        if parent is not None and parent not in previous["parents"] and len(previous["parents"]) < 4:
            previous["parents"].append(parent)
        if len(_encoded(ledger)) > MAX_BYTES - 8192:
            previous["relations"] = [previous["kind"]]
            previous["parents"] = [previous["parent_url"]] if previous["parent_url"] is not None else []
        return previous
    if len(records) >= MAX_RECORDS:
        count(ledger, "capacity_omissions")
        return None
    row = {"url": url, "ordinal": ledger["counts"]["observations"],
           "depth": depth, "parent_url": parent, "parents": [parent] if parent is not None else [],
           "kind": kind, "relations": [kind], "observations": 1, "pending": False}
    records[identity] = row
    # Reserve room for changing counts, provenance and the last decision.
    if len(_encoded(ledger)) > MAX_BYTES - 32768:
        del records[identity]
        count(ledger, "capacity_omissions")
        return None
    return row


def pending_rows(ledger):
    return [{"url": r["url"], "original_url": r["url"], "depth": r["depth"],
             "parent_url": r["parent_url"], "attempts": 0,
             "ready_at": 0, "redirects": []}
            for r in sorted(ledger["records"].values(), key=lambda row: row["ordinal"])
            if r["pending"]]


def retire(ledger, url, *, promoted=False):
    row = record_for(ledger, url)
    if row is not None and row["pending"]:
        row["pending"] = False
        count(ledger, "promoted" if promoted else "retired")


def _terms(value):
    return frozenset(sorted(set(_TERMS.findall(value.casefold())))[:64])


def _unit(number):
    if not math.isfinite(number):
        raise ValueError("nonfinite navigation score")
    return round(min(1.0, max(0.0, number)), 8)


@dataclass(frozen=True)
class Discourse:
    url: str
    quest: str
    objective_coverage: float
    uncovered_terms: float
    evidence_novelty: float
    jeeves_proposal: float
    dragon_counterproposal: float
    disagreement: float
    final_priority: float
    authority: str = "advisory_only"

    def receipt(self):
        body = asdict(self)
        return {**body, "digest": _digest(body)}


def deliberate(row, *, base, profile, query):
    """Two independent role proposals followed by constrained arbitration.

    The objective delegate estimates query gap and opportunity from the
    existing captured evidence. Dragon contributes its learned campaign
    progress, uncertainty, energy and conservation quest. Neither can create
    a target or change the eligibility or transport decision.
    """
    base = _unit(base)
    parsed = urlsplit(row["url"])
    wanted = _terms(query)
    hits = wanted & _terms(unquote(parsed.path, errors="replace"))
    coverage = len(hits) / max(1, len(wanted))
    gap = sum(1 / (1 + profile.term_support.get(term, 0)) ** 2
              for term in hits) / max(1, len(wanted))
    host = parsed.hostname
    novelty = _unit(profile.host_novelty.get(host, .25))
    jeeves = _unit(.70 * base + .18 * gap + .08 * coverage
                   + .04 / (1 + row["depth"]))
    dragon = _unit(companion_priority(row, profile=profile, base=base, query=query))
    disagreement = abs(jeeves - dragon)
    if profile.quest in {"rest", "recover", "conserve"}:
        # Existing measured yield and recovery policy lead when energy is low.
        final = base
    else:
        # Consensus is conservative under disagreement. Retain exploration
        # rather than selecting only URLs matching the literal research query.
        consensus = .55 * jeeves + .45 * dragon - .12 * disagreement
        final = _unit(.55 * base + .45 * consensus)
    return Discourse(row["url"], profile.quest, _unit(coverage), _unit(gap),
                     novelty, jeeves, dragon, _unit(disagreement), final)


def remember(ledger, discourse):
    ledger["last_discourse"] = discourse


def validate(ledger, *, admit, max_depth):
    if not isinstance(ledger, dict) or set(ledger) != {"records", "counts", "last_discourse"}:
        raise ValueError("navigation ledger schema")
    records, counters = ledger["records"], ledger["counts"]
    if (not isinstance(records, dict) or len(records) > MAX_RECORDS
            or not isinstance(counters, dict) or set(counters) != set(COUNTERS)
            or any(type(v) is not int or not 0 <= v <= 1_000_000_000 for v in counters.values())
            or len(_encoded(ledger)) > MAX_BYTES):
        raise ValueError("navigation ledger bounds")
    total = 0
    ordinals = set()
    for identity, row in records.items():
        if not isinstance(row, dict) or set(row) != {
                "url", "ordinal", "depth", "parent_url", "parents", "kind", "relations", "observations", "pending"}:
            raise ValueError("navigation row fields")
        url = row["url"]
        admit(url)
        if (identity != hashlib.sha256(url.encode("utf-8")).hexdigest()
                or type(row["ordinal"]) is not int or not 1 <= row["ordinal"] <= counters["observations"]
                or row["ordinal"] in ordinals or not isinstance(row["parents"], list)
                or len(row["parents"]) > 4 or len(set(row["parents"])) != len(row["parents"])):
            raise ValueError("navigation identity or parent custody")
        ordinals.add(row["ordinal"])
        for parent in row["parents"]:
            admit(parent)
        if row["parent_url"] is not None:
            admit(row["parent_url"])
        if (type(row["depth"]) is not int or not 0 <= row["depth"] <= max_depth + 1
                or row["kind"] not in KINDS or not isinstance(row["relations"], list)
                or not row["relations"] or len(row["relations"]) > len(KINDS)
                or row["relations"] != sorted(set(row["relations"]))
                or not set(row["relations"]) <= KINDS or row["kind"] not in row["relations"]
                or type(row["observations"]) is not int or not 1 <= row["observations"] <= 1_000_000_000
                or type(row["pending"]) is not bool
                or (row["pending"] and row["depth"] > max_depth)):
            raise ValueError("navigation row values")
        total += row["observations"]
    if total > counters["observations"]:
        raise ValueError("navigation observation accounting")
    receipt = ledger["last_discourse"]
    if receipt is not None:
        if not isinstance(receipt, dict):
            raise ValueError("navigation discourse receipt")
        raw = dict(receipt)
        digest = raw.pop("digest", None)
        if set(raw) != set(Discourse.__dataclass_fields__) or digest != _digest(raw):
            raise ValueError("navigation discourse integrity")
        admit(raw["url"])
        if (raw["authority"] != "advisory_only"
                or raw["quest"] not in {"rest", "recover", "conserve", "explore", "synthesize", "diversify"}):
            raise ValueError("navigation discourse authority")
        for key in set(raw) - {"url", "quest", "authority"}:
            v = raw[key]
            if type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1:
                raise ValueError("navigation discourse score")


def projection(ledger, *, frontier, seen, max_depth):
    active = {r["url"] for r in frontier}
    visited = set(seen)
    records = ledger["records"]
    return {"unique_targets": len(records), "pending": sum(r["pending"] for r in records.values()),
            "active": len(active), "visited": len(visited),
            "depth_held_targets": sum(r["depth"] > max_depth for r in records.values()),
            "counts": dict(ledger["counts"]), "max_records": MAX_RECORDS,
            "max_bytes": MAX_BYTES, "last_discourse": ledger["last_discourse"],
            "inventory_complete": False, "authority": "advisory_only"}


def browse_page(ledger, *, frontier, seen, max_depth, after=0, limit=32):
    """Ordinal pagination over one immutable snapshot; links are never fetched."""
    if type(after) is not int or not 0 <= after <= 1_000_000_000:
        raise ValueError("invalid navigation cursor")
    if type(limit) is not int or not 1 <= limit <= 32:
        raise ValueError("invalid navigation page size")
    active = {u for row in frontier for u in (row["url"], row["original_url"])}
    visited = set(seen)
    rows = sorted((row for row in ledger["records"].values() if row["ordinal"] > after),
                  key=lambda row: row["ordinal"])
    selected = []
    for row in rows:
        if len(selected) >= limit:
            break
        url = row["url"]
        phase = ("visited" if url in visited else "active" if url in active else
                 "depth_held" if row["depth"] > max_depth else
                 "pending" if row["pending"] else "observed_only")
        candidate = {**row, "phase": phase, "navigation_authorized": False}
        if len(_encoded([*selected, candidate])) > 256 * 1024:
            break
        selected.append(candidate)
    next_after = selected[-1]["ordinal"] if selected and len(selected) < len(rows) else None
    return {"targets": selected, "next_after": next_after,
            "summary": projection(ledger, frontier=frontier, seen=seen, max_depth=max_depth),
            "network_authorized": False}
