"""Evidence-fed virtual companion and bounded curiosity controller.

The pet is a reversible projection of the owner-scoped crawl, not a second
agent, credential store, model trainer or scheduler. It has no independent
network, clock-decay, payment, notification or background-work authority.
Growth is recomputed from actual retained evidence and conserved outcomes.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import math
import re
import unicodedata
from urllib.parse import urlsplit

from .frontier_coverage import _unicode_terms, _url_tokens
from .dragon_questbook import Contribution, derive_questbook

SCHEMA = "skeleton.dragon.companion.v1"
MAX_SOURCES = 64
MAX_REQUESTS = 128
MAX_SIGNATURES = 96
MAX_WORDS = 2048
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_CONTINUOUS = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af\u0e00-\u0e7f]+")
_AXES = ("discovery", "understanding", "diversity", "discipline", "resilience")
_FORMS = ("hatchling", "scout", "scholar", "pathfinder", "archivist")
_QUESTS = ("explore", "synthesize", "diversify", "conserve", "recover", "rest")
_STYLES = ("balanced", "curious", "scholarly", "guardian")


def companion_style(strategy: str) -> str:
    return {"companion_curiosity": "curious", "companion_scholar": "scholarly",
            "companion_guardian": "guardian"}.get(strategy, "balanced")


def _unit(value: float) -> float:
    return round(max(0., min(1., value)), 6)


def _host(url: str) -> str:
    host = urlsplit(url).hostname
    if not host:
        raise ValueError("companion requires canonical source origin")
    return host


def _lexemes(text: str) -> list[str]:
    """Bounded language-neutral lexical projection, with continuous scripts."""
    words = []
    normalized = unicodedata.normalize("NFKC", text).casefold()
    for match in _WORD.finditer(normalized):
        for token in re.split(r"([\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af\u0e00-\u0e7f]+)", match.group()):
            if not token:
                continue
            if _CONTINUOUS.fullmatch(token) and len(token) > 1:
                words.extend(token[i:i+2] for i in range(min(len(token)-1, MAX_WORDS-len(words))))
            else:
                words.append(token[:96])
            if len(words) >= MAX_WORDS:
                return words[:MAX_WORDS]
    return words


def _signature(text: str) -> frozenset[int]:
    """Bottom-k trigram hashes; no source words in the derived memory."""
    if not isinstance(text, str) or len(text.encode("utf-8")) > 24000:
        raise ValueError("companion evidence outside preserved text bound")
    words = _lexemes(text)
    if len(words) < 5:
        return frozenset()
    hashes = {int.from_bytes(hashlib.blake2b(
        "\x1f".join(words[i:i+3]).encode("utf-8"), digest_size=8,
        person=b"dragon-pet").digest(), "big") for i in range(len(words)-2)}
    return frozenset(sorted(hashes)[:MAX_SIGNATURES])


def _lexical_quality(text: str) -> float:
    """Saturating lexical density; repetition/keyword padding earns little."""
    words = _lexemes(text)
    if len(words) < 8:
        return 0.
    counts = Counter(words)
    distinct = len(counts)
    entropy = -sum((n/len(words))*math.log2(n/len(words)) for n in counts.values())
    richness = min(1., distinct / 16)
    normalized = entropy / math.log2(max(2, min(len(words), 64)))
    return min(1., richness * normalized)


def _similarity(a: frozenset[int], b: frozenset[int]) -> float:
    if not a or not b:
        return 0.
    # Shared bottom-k sample of the union avoids bias from separately
    # truncated sets. Approximate lexical overlap, not semantic equivalence.
    sample = sorted(a | b)[:MAX_SIGNATURES]
    return sum(x in a and x in b for x in sample) / len(sample)


def _medium(ctype: str) -> str:
    if ctype in {"text/html", "application/xhtml+xml"}:
        return "web"
    if ctype == "application/pdf":
        return "document"
    if "json" in ctype or "xml" in ctype or "csv" in ctype:
        return "structured"
    if ctype.startswith(("audio/", "video/", "image/", "model/")):
        return "media"
    if ctype.startswith("text/"):
        return "text"
    return "artifact"


@dataclass(frozen=True)
class CompanionProfile:
    projection: dict
    host_progress: dict[str, float]
    host_novelty: dict[str, float]
    host_trials: dict[str, int]
    term_support: dict[str, int]
    seen_hosts: frozenset[str]
    quest: str


def build_companion(*, sources: dict, measurements: list[dict], query: str,
                    usage: dict, limits: dict, state: str, frontier_count: int,
                    consent_current: bool, due: bool, incidents: int = 0,
                    style: str = "balanced") -> CompanionProfile:
    if (not isinstance(sources, dict) or len(sources) > MAX_SOURCES
            or not isinstance(measurements, list) or len(measurements) > MAX_REQUESTS
            or not isinstance(query, str) or len(query) > 1024
            or style not in _STYLES or type(frontier_count) is not int
            or not 0 <= frontier_count <= 512 or type(incidents) is not int
            or not 0 <= incidents <= 128 or type(consent_current) is not bool
            or type(due) is not bool):
        raise ValueError("invalid companion projection input")
    wanted = frozenset(sorted(_unicode_terms(query))[:32])
    support = defaultdict(set)
    archive: list[frozenset[int]] = []
    hashes = set()
    hosts = set()
    niches = Counter()
    host_rewards: dict[str, list[float]] = defaultdict(list)
    measured_rewards: dict[int, float] = {}
    novelty_mass = relevance_mass = 0.
    contributions = []
    origin_credit = defaultdict(float)
    last_sequence = 0
    ordered = sorted(sources.values(), key=lambda s: (
        s.get("provenance", {}).get("capture_sequence", 10001),
        s.get("fetched_at", 0), s.get("source_id", "")))
    for row in ordered:
        digest = row["content_hash"]
        if digest in hashes:
            continue
        hashes.add(digest)
        text, url = row["text"], row["canonical_url"]
        host = _host(row.get("fetched_url", url))
        signature = _signature(text)
        if not signature:
            # Very short distinct pages do not farm growth simply because
            # no signal is available to measure similarity.
            novelty = 0.
        else:
            novelty = 1 - max((_similarity(signature, old) for old in archive), default=0.)
            archive.append(signature)
        matches = _unicode_terms(text) & wanted
        relevance = len(matches) / len(wanted) if wanted else .5
        # An extra hostname is only lexical diversity, not verified
        # independence. Near-identical text cannot award a new niche.
        quality = _lexical_quality(text)
        # A matching keyword alone is not evidence of useful novelty.
        # Marginal credit saturates per origin, so repetitive one-origin
        # harvesting cannot dominate a diversified, high-quality expedition.
        credit = novelty * relevance * quality / math.sqrt(1 + origin_credit[host])
        novel_enough = novelty >= .25 and len(text) >= 80 and credit >= .05
        added = multi_added = 0
        habitat = _medium(row["content_type"])
        if novel_enough:
            hosts.add(host)
            niches[habitat] += 1
            origin_credit[host] += credit
            for term in matches:
                prior = len(support[term])
                support[term].add(host)
                current = len(support[term])
                added += int(prior == 0 and current == 1)
                multi_added += int(prior == 1 and current == 2)
        reward = credit if novel_enough else 0.
        novelty_mass += reward
        relevance_mass += relevance * int(novel_enough)
        sequence = row.get("provenance", {}).get("capture_sequence")
        if type(sequence) is int:
            measured_rewards[sequence] = reward
            if sequence <= last_sequence:
                raise ValueError("duplicate or unordered companion acquisition sequence")
            last_sequence = sequence
            contributions.append(Contribution(row["source_id"], sequence, host, habitat,
                round(reward, 6), round(novelty, 6), round(relevance, 6),
                added, multi_added, novel_enough))
        else:
            # Synthetic/legacy rows can remain visible to existing capture
            # clients but cannot unlock a receipt requiring exact identity.
            host_rewards[host].append(reward)
    # Every attempted content acquisition participates in learning progress.
    # Failures and redundant pages have zero reward, not positive surprise.
    for measurement in measurements:
        if measurement["kind"] not in {"robots", "redirect"}:
            host_rewards[measurement["host"]].append(
                measured_rewards.get(measurement["event_sequence"], 0.)
            )
    host_progress = {}
    host_novelty = {}
    host_trials = {}
    for host, rewards in host_rewards.items():
        recent = rewards[-8:]
        host_trials[host] = len(recent)
        # Shrink low-sample observations to a conservative prior.
        host_novelty[host] = _unit((.5 + sum(recent)) / (2 + len(recent)))
        # Learning progress is improvement, not raw prediction error. Failed
        # exploration, duplicated pages and declining yield give no bonus.
        if len(recent) >= 4:
            midpoint = len(recent) // 2
            earlier, later = recent[:midpoint], recent[midpoint:]
            difference = max(0., sum(later)/len(later)-sum(earlier)/len(earlier))
            host_progress[host] = _unit(difference * len(recent)/(4 + len(recent)))
        else:
            host_progress[host] = 0.
    settled = len(measurements)
    productive = sum(row["kind"] == "captured" for row in measurements)
    negatives = sum(row["kind"] in {"error", "retry", "interrupted_dispatch", "rejected"}
                    for row in measurements)
    unknown = sum(row["uncertain_bytes"] for row in measurements)
    covered = sum(bool(support[term]) for term in wanted)
    multi = sum(len(support[term]) >= 2 for term in wanted)
    requests_left = max(0, limits["max_requests"] - usage["requests"])
    bytes_left = max(0, limits["max_total_bytes"] - usage["bytes"] - usage["reserved_bytes"])
    documents_left = max(0, limits["max_documents"] - usage["documents"])
    energy = min(requests_left / max(1, limits["max_requests"]),
                 bytes_left / max(1, limits["max_total_bytes"]),
                 documents_left / max(1, limits["max_documents"]))
    recovery_pairs = 0
    prior_failure = set()
    for row in measurements:
        host = row["host"]
        if row["kind"] in {"error", "retry", "interrupted_dispatch"}:
            prior_failure.add(host)
        elif row["kind"] == "captured" and host in prior_failure:
            recovery_pairs += 1
            prior_failure.remove(host)
    unique = len(hashes)
    skills = {
        "discovery": _unit(novelty_mass / 8),
        "understanding": _unit((covered + .5 * multi) / max(1, 1.5 * len(wanted))
                               if wanted else relevance_mass / 8),
        "diversity": _unit((min(4, len(hosts))/4 + min(4, len(niches))/4)/2),
        "discipline": _unit(productive / max(1, settled) * min(1., unique/4)),
        # No points for generating failures/incidents. This is an operational
        # readiness meter, not an experience currency.
        "resilience": _unit((1 + productive)/(2 + settled + negatives)),
    }
    # No reward for raw volume, denial encounters, or repeated recovery.
    growth = int(round(1000 * (.40*skills["discovery"] + .38*skills["understanding"]
                               + .22*skills["diversity"])))
    stage = sum(growth >= t for t in (120, 300, 550, 800))
    dormant = not consent_current or state in {"paused", "cancelled", "completed", "budget_exhausted", "failed"}
    if dormant or not due or not frontier_count:
        quest = "rest"
    elif energy < .15:
        quest = "conserve"
    elif negatives >= 2 and negatives / max(1, settled) >= .45:
        quest = "recover"
    else:
        deficits = {
            "explore": (1-skills["discovery"]) * (.9 if style == "scholarly" else 1.),
            "synthesize": (1-skills["understanding"]) * (1.2 if style == "scholarly" else 1.),
            "diversify": (1-skills["diversity"]) * (1.2 if style == "curious" else .85),
            "conserve": (1-energy) * (1.2 if style == "guardian" else .6),
        }
        quest = max(deficits, key=lambda key: (deficits[key], -_QUESTS.index(key)))
    # The visual state never punishes inactivity or implies suffering.
    posture = "resting" if dormant or not due else "recovering" if quest == "recover" else (
        "studying" if quest == "synthesize" else "roaming")
    projection = {
        "schema": SCHEMA, "form": _FORMS[stage], "stage": stage, "growth": growth,
        "skills": skills, "energy": _unit(energy), "quest": quest, "posture": posture,
        "style": style, "captured_sources": unique, "novel_origins": len(hosts),
        "habitats": dict(sorted(niches.items())), "covered_terms": covered,
        "term_count": len(wanted), "multi_origin_terms": multi,
        "recovery_observations": recovery_pairs, "quarantines": incidents,
        "uncertain_bytes": unknown, "unreviewed_evidence_only": True,
        "network_authority_expanded": False, "training_permission": False,
        "inactivity_penalty": False,
        "learning_progress": _unit(max(host_progress.values(), default=0.)),
        "novelty_yield": _unit(novelty_mass / max(1, unique)),
    }
    projection["questbook"] = derive_questbook(contributions, term_count=len(wanted),
        settled=settled, request_budget=limits["max_requests"], source_budget=limits["max_documents"])
    return CompanionProfile(projection, host_progress, host_novelty, host_trials,
                            {k: len(v) for k,v in support.items()}, frozenset(hosts), quest)


def companion_priority(row: dict, *, profile: CompanionProfile, base: float,
                       query: str) -> float:
    """Bounded relative adjustment after due eligibility, never an admission."""
    if not math.isfinite(base) or not 0 <= base <= 1:
        raise ValueError("invalid companion base priority")
    host = _host(row["url"])
    matches = _url_tokens(row["url"]) & frozenset(sorted(_unicode_terms(query))[:32])
    gap = sum(1/(1+profile.term_support.get(t,0))**2 for t in matches)/max(1,len(matches))
    progress = profile.host_progress.get(host, 0.)
    novelty = profile.host_novelty.get(host, .25)
    trials = profile.host_trials.get(host, 0)
    total_trials = sum(profile.host_trials.values())
    tempered_exploration = min(.18, .07 * math.sqrt(math.log(2 + total_trials)/(1 + trials)))
    novelty = min(1., novelty + tempered_exploration * max(.25, gap))
    diversity = float(host not in profile.seen_hosts)
    quest = profile.quest
    if quest == "rest":
        return base
    if quest == "recover" or quest == "conserve":
        # No extra exploration when scarce or degraded; core reliability,
        # cost and existing cooldowns remain decisive.
        return base
    need = {"explore": .50*novelty+.30*progress+.20*gap,
            "synthesize": .70*gap+.30*progress,
            "diversify": .55*diversity+.30*gap+.15*progress}[quest]
    # Limit influence to 12%; no bonus can overpower hard policy.
    # Anneal influence as acquisition budget falls; guardian is always
    # more conservative. This changes ordering only, not pacing or quota.
    weight = min(.12, .04 + .08 * profile.projection["energy"])
    if profile.projection["style"] == "guardian":
        weight *= .5
    return _unit((1-weight)*base+weight*need)
