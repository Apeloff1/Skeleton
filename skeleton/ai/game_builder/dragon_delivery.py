"""Knowledge-to-native delivery composition over existing Dragon authorities.

Briefs are short-lived derived data, never approval receipts or executable code.
The reviewed library, Wiki/Hoag and native practice ledger retain ownership.
"""
from __future__ import annotations

from .contracts import canonical_digest
from .dragon_almanacs import DragonAlmanacs, _auth
from .dragon_wisdom_pyramid import DragonWisdomPyramid
from .dragon_wisdom_memory import DragonWisdomMemory
from .reviewed_knowledge import _integer, _text
from ..webcrawler.dragon_game_design import FIELDS, GameDesign, parse_design
from ..webcrawler.dragon_native_targets import target_catalog
from ..webcrawler.dragon_native_compile import COMMANDS

DESKTOP = frozenset({"pc_linux", "pc_windows", "pc_macos", "steam_deck"})


def design_controls(target: str, genre: str) -> dict:
    """Expose controls only where the current emitter consumes them."""
    effective = ["title", "target", "genre", "seed"]
    if target in DESKTOP:
        effective += ["stages", "difficulty"]
        if genre not in {"fixed_screen_puzzle", "rhythm_game"}:
            effective += ["palette", "candidates"]
            if genre != "turn_based_rpg":
                effective += ["quest_theme"]
            if genre not in {"first_person_shooter", "immersive_sim", "turn_based_rpg"}:
                effective += ["hero"]
    return {"effective": effective,
            "metadata_only": sorted(FIELDS - set(effective) - {"schema"}),
            "cartridge_single_stage": target not in DESKTOP}


class DragonDelivery:
    def __init__(self, almanacs: DragonAlmanacs):
        if not isinstance(almanacs, DragonAlmanacs):
            raise TypeError("canonical Almanakk projection required")
        self.almanacs = almanacs
        self.library = almanacs.library
        self.pyramid = DragonWisdomPyramid(self.library)
        self.memory = DragonWisdomMemory(self.pyramid)

    def overview(self, owner: str, *, now: int, authorized: bool) -> dict:
        _auth(owner, authorized); _integer(now, "clock", 0, 4_102_444_800)
        db = self.library.db
        sources = self.library._rows(owner)
        current = [row for row in sources if row["status"] == "active"]
        events = self.pyramid._history(owner)
        view = self.pyramid.hoag_view(owner, now=now, authorized=True, require_signed_approval=True)
        memory = self.memory.read_current(owner, now=now, authorized=True, limit=64)
        catalog = target_catalog()
        stages = []
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dragon_almanac_jobs'").fetchone():
            from .dragon_almanac_sequence import STAGES
            for stage, state, count in db.execute("SELECT stage,state,COUNT(*) FROM dragon_almanac_jobs WHERE owner=? GROUP BY stage,state ORDER BY stage,state", (owner,)):
                if type(stage) is not int or not 0 <= stage < len(STAGES):
                    raise ValueError("invalid acquisition stage")
                stages.append({"stage": STAGES[stage], "state": state, "count": count})
        counts = {"discovered_sources": db.execute("SELECT COUNT(*) FROM dragon_almanac_sources WHERE owner=?", (owner,)).fetchone()[0],
                  "almanacs": db.execute("SELECT COUNT(*) FROM dragon_almanac_topics WHERE owner=?", (owner,)).fetchone()[0],
                  "reviewed_sources": len(current),
                  "reviewed_notes": sum(len(r["notes"]) for r in current),
                  "wiki_reviews": sum(e["kind"] == "wiki_review" for e in events),
                  "approved_mechanics": len(view["items"]),
                  "current_memory_cards": len(memory["items"]),
                  "pending_recrawls": view["pending_recrawls"],
                  "source_targets": sum(r["status"] == "native_source" for r in catalog),
                  "catalog_targets": len(catalog), "compiler_adapters": len(COMMANDS)}
        return {"schema": "skeleton.dragon.delivery_overview.v1", "owner": owner,
                "knowledge_root": view["knowledge_root"], "counts": counts,
                "acquisition": stages, "memory_reconciliation_required": memory["reconciliation_required"],
                "next_actions": self._next_actions(counts, memory["reconciliation_required"]),
                "scope": "current_owner_evidence_not_global_completion",
                "overall_completion_percent": None,
                "training_authorized": False, "release_authorized": False}

    @staticmethod
    def _next_actions(counts, reconcile):
        actions = []
        for condition, code, label in (
            (counts["discovered_sources"] == 0, "source_discovery", "Import source discovery catalog through the trusted crawler"),
            (counts["reviewed_sources"] == 0, "source_review", "Acquire and independently review source material"),
            (counts["approved_mechanics"] == 0, "wiki_hoag", "Complete independent Wiki review and separate Hoag approval"),
            (counts["pending_recrawls"] > 0, "recrawl", "Refresh changed or challenged sources before reuse"),
            (reconcile, "memory_reconcile", "Run the trusted advisory-memory reconciler"),
        ):
            if condition:
                actions.append({"code": code, "label": label})
        actions.append({"code": "native_delivery", "label": "Create a cited design brief, generate source, then compile and playtest on its target"})
        return actions

    def search(self, owner: str, query: str, *, now: int, authorized: bool, limit: int = 12) -> dict:
        _auth(owner, authorized); _integer(limit, "limit", 1, 32)
        _text(query, "query", 300)
        view = self.pyramid.hoag_view(owner, now=now, authorized=True, require_signed_approval=True)
        cards = {r["mechanic"]: r for r in view["items"]}
        history = self.pyramid._history(owner)
        reviews = {r["digest"]: r for r in history if r["kind"] == "wiki_review"}
        approvals = {r["review_digest"]: r for r in history if r["kind"] == "promoted"}
        hits = self.library.search(owner, query, authorized=True, limit=limit, diversify=True)
        results = []
        for hit in hits:
            card = cards.get(hit.mechanic)
            review = reviews.get(card["review_digest"]) if card else None
            approved = review is not None and [hit.source_id, hit.revision_digest, hit.note_id, hit.dependence_group] in review["source_refs"]
            results.append({"source_id": hit.source_id, "revision_digest": hit.revision_digest,
                "note_id": hit.note_id, "source_url": hit.source_url, "title": hit.source_title,
                "mechanic": hit.mechanic, "statement": hit.statement, "stance": hit.stance,
                "confidence_ppm": hit.confidence_ppm, "dependence_group": hit.dependence_group,
                "approval": "wiki_hoag_approved" if approved else "source_reviewed_only",
                "review_digest": card["review_digest"] if approved else None,
                "review_evidence_digest": card["review_evidence_digest"] if approved else None,
                "approval_evidence_digest": approvals[card["review_digest"]].get("approval_evidence_digest") if approved else None,
                "expires_at": card["expires_at"] if approved else None})
        return {"schema": "skeleton.dragon.delivery_search.v1", "owner": owner,
                "query": query, "knowledge_root": view["knowledge_root"], "items": results,
                "source_text_included": False, "training_authorized": False,
                "release_authorized": False}

    def brief(self, owner: str, design: GameDesign, query: str, *, now: int,
              authorized: bool, prepared_at: int | None = None) -> dict:
        _auth(owner, authorized); _integer(now, "clock", 0, 4_102_444_800)
        if not isinstance(design, GameDesign):
            raise TypeError("typed native game design required")
        # Dataclass construction alone is not schema validation.
        canonical = parse_design({k: getattr(design, k) for k in FIELDS})
        if canonical != design:
            raise ValueError("design digest does not match canonical controls")
        issued = now if prepared_at is None else prepared_at
        _integer(issued, "brief time", max(0, now - 299), now)
        profile = next(r for r in target_catalog() if r["id"] == design.target)
        found = self.search(owner, query, now=now, authorized=True, limit=32)
        citations = [r for r in found["items"] if r["approval"] == "wiki_hoag_approved" and r["stance"] == "supports"]
        groups = len({r["dependence_group"] for r in citations})
        # Contradictions remain visible even if a different mechanic matches.
        conflicts = sorted({r["mechanic"] for r in found["items"] if r["stance"] == "challenges"})
        blockers = []
        if profile["status"] != "native_source" or design.genre not in profile["supported_styles"]:
            blockers.append("target_style_emitter_missing")
        if groups < 2:
            blockers.append("two_independent_approved_source_groups_required")
        if conflicts:
            blockers.append("source_contradictions_need_review")
        expiry = min([issued + 300] + [r["expires_at"] for r in citations])
        if expiry <= now:
            blockers.append("knowledge_expired")
        body = {"schema": "skeleton.dragon.delivery_brief.v1", "owner": owner,
                "design": {k: getattr(design, k) for k in sorted(FIELDS)}, "design_digest": design.digest,
                "query": query, "knowledge_root": found["knowledge_root"],
                "prepared_at": issued, "expires_at": expiry, "citations": citations,
                "independent_groups": groups, "conflicts": conflicts,
                "blockers": blockers, "ready_for_source_generation": not blockers,
                "controls": design_controls(design.target, design.genre),
                "toolchain": profile["toolchain"], "output_extension": profile["output"],
                "compiler_adapter_available": design.target in COMMANDS,
                "knowledge_application": "cited_design_guidance_not_automatic_code_synthesis",
                "build_state": "not_built", "gameplay_state": "not_verified",
                "training_authorized": False, "release_authorized": False}
        return {**body, "plan_digest": canonical_digest(body)}

    def record_project_learning(self, owner: str, native, attempt_id: str, *, authorized: bool) -> dict:
        """Rebuildable source-synthesis journal; no experiment or AI insight claim.

        Read back the canonical committed artifact, not caller-provided claims.
        This separate-store projection is idempotent and may be retried after a
        crash without regenerating source or spending another practice attempt.
        """
        _auth(owner, authorized)
        from ..webcrawler.dragon_native_practice import DragonNativePracticeLab
        from .dragon_almanacs import ProjectLearning
        import json
        if not isinstance(native, DragonNativePracticeLab):
            raise TypeError("canonical native artifact owner required")
        project = native.project(owner, attempt_id, authorized=True)
        raw = project["files"].get("dragon-knowledge-brief.json")
        if not isinstance(raw, str):
            raise ValueError("project has no knowledge-to-design lineage")
        brief = json.loads(raw)
        if (brief.get("owner") != owner or canonical_digest({k:v for k,v in brief.items() if k != "plan_digest"}) != brief.get("plan_digest")):
            raise ValueError("archived project brief integrity invalid")
        row = native.db.execute("SELECT created_at FROM dragon_native_game_attempts WHERE owner=? AND attempt_id=?", (owner, attempt_id)).fetchone()
        if row is None:
            raise LookupError("native attempt missing")
        topic = self.almanacs.ensure_topic(owner, ("Projects", project["target_id"], project["style"], "Design synthesis"), authorized=True)
        learning = ProjectLearning(attempt_id, project["digest"], topic,
            "steppingstone", "source_synthesis",
            "An original native source project was generated for " + project["target_id"] + " using " + project["style"] + " and the archived reviewed design guidance.",
            "Canonical artifact readback; " + str(len(project["files"])) + " generated files; applied controls: " + ", ".join(brief["controls"]["effective"]) + ".",
            "Source synthesis only. No new measured game result, learned neural weight, native gameplay success or independent empirical support is established.",
            (project["digest"], brief["plan_digest"]),
            source_refs=tuple(sorted({(r["source_id"],r["revision_digest"],r["note_id"]) for r in brief["citations"]})))
        digest = self.almanacs.record_learning(owner, learning, now=int(row[0]), authorized=True)
        return {"topic_id": topic, "learning_digest": digest, "kind": "source_synthesis",
                "empirical_truth_established": False, "memory_promotion_authorized": False}
