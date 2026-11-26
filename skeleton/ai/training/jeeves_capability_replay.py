"""Capability-balanced, hardness-guided rehearsal of reviewed Jeeves training data.

The *real parent-derived model* measures each TRAINING example's negative
log-likelihood. A bounded scheduler preserves all three capability domains,
prioritizes discovered weak spots and retains easier examples for anti-
forgetting rehearsal. Held-out examples never participate in selection.

This changes optimizer exposure; it is not a claim of verified improvement.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import math
import re
import time
from typing import Any

DOMAIN = re.compile(r"\AJeeves module jeeves\.(gaming|ai|coding)\.([a-z][a-z0-9_]*)\.([a-z_]+)\. Objective:")
MAX_SCAN = 256
MAX_REPLAY = 256


class CapabilityReplayError(ValueError):
    """Unsafe or incomplete training-only rehearsal schedule."""


def schedule_capability_replay(
    model: Any, documents: tuple[str, ...], *,
    max_examples: int = 64, max_scored_examples: int = 128,
    deadline: float | None = None,
) -> tuple[tuple[str, ...], dict[str, Any]]:
    if (type(max_examples) is not int or not 6 <= max_examples <= MAX_REPLAY or
            type(max_scored_examples) is not int or not 6 <= max_scored_examples <= MAX_SCAN or
            max_examples > max_scored_examples):
        raise CapabilityReplayError("rehearsal example or scoring budget outside limits")
    if type(documents) is not tuple or not 6 <= len(documents) <= max_scored_examples:
        raise CapabilityReplayError("actual approved training examples exceed scoring admission")
    if deadline is not None and (isinstance(deadline, bool) or not isinstance(deadline, (int, float))
                                 or not math.isfinite(deadline)):
        raise CapabilityReplayError("invalid monotonic rehearsal deadline")
    rows = []
    observed = set()

    def interrupt():
        if deadline is not None and time.monotonic() >= deadline:
            raise CapabilityReplayError("rehearsal scoring exceeded operator time budget")

    # The canonical CPU transformer supports cooperative loss measurement.
    # Do not pass new kwargs to third-party scorer adapters or silently
    # retry their failed work. Every scorer is still checked after return.
    from skeleton.cortex.transformer import TinyTransformer
    native_scorer = type(model) is TinyTransformer
    for text in documents:
        if type(text) is not str or len(text) > 24000:
            raise CapabilityReplayError("malformed training-only rehearsal source")
        match = DOMAIN.match(text)
        if match is None or " User: " not in text or " Jeeves: " not in text:
            raise CapabilityReplayError("rehearsal needs governed multidomain specialist examples")
        digest = sha256(text.encode("utf-8")).hexdigest()
        if digest in observed:
            raise CapabilityReplayError("duplicate text would inflate training exposure")
        observed.add(digest)
        interrupt()
        # No heldout references are supplied here. This uses real model logprob,
        # rather than deciding hardness from hand-written fictitious scores.
        difficulty = -float(model.logprob(text, interrupt=interrupt)
                            if native_scorer else model.logprob(text))
        interrupt()
        if not math.isfinite(difficulty) or difficulty < 0:
            raise CapabilityReplayError("nonfinite or invalid model training-loss score")
        rows.append({"text": text, "digest": digest, "domain": match.group(1),
                     "specialty": match.group(2), "lens": match.group(3),
                     "difficulty": difficulty})
    domains = {row["domain"] for row in rows}
    if domains != {"gaming", "ai", "coding"}:
        raise CapabilityReplayError("must preserve all game/AI/coding domains")
    capacity = min(max_examples, len(rows))
    hard = sorted(rows, key=lambda row: (-row["difficulty"], row["digest"]))
    easy = sorted(rows, key=lambda row: (row["difficulty"], row["digest"]))
    chosen: list[dict] = []
    chosen_hashes = set()

    def take(row):
        if row["digest"] not in chosen_hashes and len(chosen) < capacity:
            chosen.append(row)
            chosen_hashes.add(row["digest"])

    # Preserve hardest and least-hard examples per domain (anti-forgetting).
    for domain in ("gaming", "ai", "coding"):
        take(next(row for row in hard if row["domain"] == domain))
        # Equal loss can make the same digest first in both sort orders.
        # Require a distinct rehearsal example even under a tied scorer.
        partner = next((row for row in easy if row["domain"] == domain
                        and row["digest"] not in chosen_hashes), None)
        if partner is None:
            raise CapabilityReplayError("each capability domain needs two distinct examples")
        take(partner)
    # Cover novel specialty/lens combinations fairly across domains before
    # more hardness replay. Raw losses across unrelated domains need not
    # share a meaningful scale; rank within a domain and balance counts.
    def specialty(row):
        return row["domain"], row["specialty"], row["lens"]

    covered = {specialty(row) for row in chosen}
    coverage_counts = Counter(row["domain"] for row in chosen)
    while len(chosen) < max(6, capacity * 3 // 4):
        novel = {}
        for row in hard:
            domain = row["domain"]
            if row["digest"] not in chosen_hashes and specialty(row) not in covered:
                novel.setdefault(domain, row)
        if not novel:
            break
        domain = min(novel, key=lambda value: (coverage_counts[value], value))
        row = novel[domain]
        take(row)
        covered.add(specialty(row))
        coverage_counts[domain] += 1
    # Spend remaining slots on hard examples using domain-relative hardness.
    # Loss distributions can differ across domains; comparing raw losses
    # alone can starve skills whose examples are naturally more predictable.
    # Round-robin across currently least-represented available domains;
    # choose the hardest unused example within that domain. No extra scoring.
    counts = Counter(row["domain"] for row in chosen)
    queues = {domain: [row for row in hard if row["domain"] == domain]
              for domain in domains}
    while len(chosen) < capacity:
        available = []
        for domain, queue in queues.items():
            while queue and queue[0]["digest"] in chosen_hashes:
                queue.pop(0)
            if queue:
                available.append(domain)
        if not available:
            break
        domain = min(available, key=lambda value: (counts[value], value))
        take(queues[domain].pop(0))
        counts[domain] += 1
    interrupt()
    selected_hashes = {row["digest"] for row in chosen}
    selected = tuple(row["text"] for row in rows if row["digest"] in selected_hashes)
    if len(selected) != capacity:
        raise CapabilityReplayError("rehearsal scheduling lost samples")
    selected_domains = Counter(row["domain"] for row in chosen)
    if any(selected_domains[domain] < 2 for domain in domains):
        raise CapabilityReplayError("rehearsal dropped a capability domain")
    receipt = {
        "schema_version": "skeleton.jeeves.capability_replay.v1",
        "training_only_hardness_scoring": True,
        "source_examples": len(rows),
        "selected_examples": len(selected),
        "excluded_examples": len(rows) - len(selected),
        "selected_domains": {d: selected_domains[d] for d in sorted(domains)},
        "active_specialties": len({(r["domain"], r["specialty"]) for r in chosen}),
        "active_lenses": len({r["lens"] for r in chosen}),
        "selected_example_sha256": [sha256(text.encode()).hexdigest() for text in selected],
        "max_scored_examples": max_scored_examples,
        "max_selected_examples": max_examples,
        "mean_selected_training_loss": sum(r["difficulty"] for r in chosen) / len(chosen),
        "mean_all_training_loss": sum(r["difficulty"] for r in rows) / len(rows),
        "heldout_read_by_scheduler": False,
        "weights_modified_by_scheduler": False,
        "model_quality_improvement_established": False,
    }
    return selected, receipt


__all__ = ["CapabilityReplayError", "schedule_capability_replay"]
