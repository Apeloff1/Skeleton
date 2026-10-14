"""Mother Dragon's task-aware, non-executing three-hatchling research plan.

A task plan selects only from the canonical owner-scoped research workboard.
Lexical matching to curated source topics is a navigation heuristic; neither
publisher independence nor research quality, acquisition permission, or model
improvement is inferred from relevance scores.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import re

from .contracts import canonical_digest
from .dragon_almanacs import _auth
from .dragon_research_workboard import DragonResearchWorkboard
from .dragon_technical_source_atlas import CATALOG, _ADJACENT
from .reviewed_knowledge import _integer

_TERM = re.compile(r"[a-z0-9][a-z0-9-]{1,39}\Z")
_LANES = ("article", "video", "updates")
_LIMIT_PER_SCAN = 60
_MAX_SCANNED = 300
_MAX_RESULTS = 18
_SOURCE_TOPICS = {
    "source-" + sha256(item["url"].encode()).hexdigest(): (
        item["slug"], item["family"], frozenset(item["topics"])
    ) for item in CATALOG
}
if len(_SOURCE_TOPICS) != len(CATALOG):
    raise ValueError("curated source topic identities are not unique")


class DragonTaskResearchPlanner:
    """Review suggestions only. Not an idle-worker admission authority."""

    def __init__(self, board: DragonResearchWorkboard):
        if not isinstance(board, DragonResearchWorkboard):
            raise TypeError("verified three-hatchling workboard required")
        self.board = board

    @staticmethod
    def _terms(terms: tuple[str, ...]) -> tuple[str, ...]:
        if (type(terms) is not tuple or not 1 <= len(terms) <= 8
            or len(set(terms)) != len(terms)
            or any(type(t) is not str or not _TERM.fullmatch(t)
                   for t in terms)):
            raise ValueError("one to eight unique canonical game task terms required")
        return terms

    def plan(self, owner: str, *, authorized: bool,
             task_terms: tuple[str, ...],
             max_sources: int = 300,
             limit: int = 12) -> dict:
        _auth(owner, authorized)
        task_terms = self._terms(task_terms)
        _integer(max_sources, "task scan budget", 1, _MAX_SCANNED)
        _integer(limit, "task recommendations", 1, _MAX_RESULTS)
        adjacent = set()
        for term in task_terms:
            adjacent.update(_ADJACENT.get(term, ()))
        adjacent.difference_update(task_terms)
        adjacent = frozenset(adjacent)

        checked = 0
        cursor = None
        all_missions: list[dict] = []
        seen = set()
        remaining = False
        # Walk bounded pages, never a direct SQL sweep or an unconstrained
        # crawler. The read-only workboard validates each source and receipt.
        while checked < max_sources:
            page_size = min(_LIMIT_PER_SCAN, max_sources - checked)
            batch = self.board.page(
                owner, authorized=True, limit=page_size,
                after_source=cursor)
            if (batch.get("schema") != "skeleton.dragon.research_workboard.v1"
                or batch.get("read_only") is not True
                or batch.get("network_requests") != 0
                or batch.get("workers_started") != 0
                or batch.get("permissions_granted") != 0
                or batch.get("xp_awarded") != 0
                or batch.get("training_authorized") is not False):
                raise ValueError("canonical non-executing workboard required")
            n = batch["scanned_registered_source_rows"]
            if type(n) is not int or n < 0 or n > page_size:
                raise ValueError("source census exceeds page budget")
            checked += n
            for task in batch["missions"]:
                identity = (task["lane"], task["source_id"])
                if identity in seen:
                    raise ValueError("duplicate source mission in canonical census")
                seen.add(identity)
                if task["lane"] not in _LANES:
                    raise ValueError("unrecognized hatchling lane")
                if task.get("automatically_executable") is not False:
                    raise ValueError("unsafe executable research task")
                all_missions.append(task)
            remaining = bool(batch["has_more"])
            if not remaining:
                break
            next_cursor = batch["next_after_source"]
            if (not isinstance(next_cursor, str) or
                next_cursor == cursor):
                raise ValueError("nonadvancing research cursor")
            cursor = next_cursor
            if n == 0:
                raise ValueError("empty nonterminal research page")

        findings = []
        for mission in all_missions:
            if mission["source_kind"] == "article":
                entry = _SOURCE_TOPICS.get(mission["source_id"])
                if entry is None:
                    raise ValueError("article mission lacks exact curated atlas identity")
                slug, family, topics = entry
                vocabulary = set(topics)
                vocabulary.add(family)
                vocabulary.add(slug)
                # Join hyphenated topics into their component search tokens.
                for token in tuple(vocabulary):
                    vocabulary.update(token.split("-"))
            else:
                # A registered video without reviewed transcript metadata has
                # no dependable game-domain tags. Do not hallucinate them.
                family = "video"
                vocabulary = set()
            direct = sorted(set(task_terms) & vocabulary)
            related = sorted(adjacent & vocabulary)
            # Lexical relevance alone. Never "model confidence" or source
            # reliability. Requiring manual review is not a penalty on truth.
            score = 12 * len(direct) + 3 * len(related)
            if mission["action"].endswith("_candidate"):
                score += 2
            if mission["action"] == "update_unchanged":
                score = max(0, score - 2)
            findings.append({
                "lane": mission["lane"],
                "source_id": mission["source_id"],
                "source_kind": mission["source_kind"],
                "host": mission["host"],
                "label": mission["label"],
                "action": mission["action"],
                "next_step": mission["next_step"],
                "source_family": family,
                "task_terms_matched": direct,
                "adjacent_terms_matched": related,
                "lexical_priority_signal": score,
                "evidence_digest": mission["evidence_digest"],
                "observed_at": mission["observed_at"],
                "requires_idle": mission["requires_idle"],
                "requires_operator_authorization":
                    mission["requires_operator_authorization"],
                "requires_independent_wiki_review":
                    mission["requires_independent_wiki_review"],
                "automatically_executable": False,
                "source_independence_verified": False,
                "knowledge_approved": False,
                "xp_awarded": 0,
                "training_authorized": False,
            })
        findings.sort(key=lambda f: (
            -f["lexical_priority_signal"], f["host"], f["source_id"],
            f["lane"]))
        # Reserve an available slot for each of the three hatchling lanes,
        # even if registered video metadata has no topical relevance signal.
        selected = []
        used = set()
        for lane in _LANES:
            if len(selected) == limit:
                break
            candidate = next((f for f in findings if f["lane"] == lane), None)
            if candidate is not None:
                selected.append(candidate)
                used.add((candidate["lane"], candidate["source_id"]))

        # Prefer distinct hosts (as a workload-balancing heuristic, NOT
        # independent provenance). Preserve scores within each host bucket.
        host_use = Counter(f["host"] for f in selected)
        for host_round in range(1, len(findings) + 2):
            if len(selected) == limit:
                break
            progress = False
            for f in findings:
                identity = (f["lane"], f["source_id"])
                if identity not in used and host_use[f["host"]] < host_round:
                    selected.append(f)
                    used.add(identity)
                    host_use[f["host"]] += 1
                    progress = True
                    if len(selected) == limit:
                        break
            if not progress and all((f["lane"], f["source_id"]) in used
                                    for f in findings):
                break

        represented = {term for f in findings for term in
                       f["task_terms_matched"]}
        source_ids = {f["source_id"] for f in selected}
        core = {
            "schema": "skeleton.dragon.task_research_plan.v1",
            "owner": owner,
            "task_terms": list(task_terms),
            "adjacent_research_terms": sorted(adjacent),
            "matched_task_terms": sorted(represented),
            "unmatched_task_terms": sorted(set(task_terms) - represented),
            "scanned_registered_sources": checked,
            "available_research_missions": len(findings),
            "search_scope_exhausted": not remaining,
            "source_scan_budget": max_sources,
            "suggestions": selected,
            "suggestion_count": len(selected),
            "represented_hatchlings": sorted({f["lane"] for f in selected}),
            "distinct_source_ids": len(source_ids),
            "distinct_source_hosts": len({f["host"] for f in selected}),
            "host_diversity_not_independent_corroboration": True,
            "lexical_priority_not_quality_or_fact_confidence": True,
            "read_only": True,
            "network_requests": 0,
            "workers_started": 0,
            "permissions_granted": 0,
            "xp_awarded": 0,
            "knowledge_approved": False,
            "training_authorized": False,
        }
        return {**core, "plan_digest": canonical_digest(core)}
