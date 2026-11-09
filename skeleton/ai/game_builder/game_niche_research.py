"""Bounded niche research agendas. No retrieval, promotion or release authority."""
from __future__ import annotations

from dataclasses import asdict
from itertools import combinations
from typing import Iterable

from .contracts import canonical_digest
from .game_niche_catalog import BY_ID, NICHES, niche_catalog
from .game_research_foundation import TARGETS, bounded
from .reviewed_knowledge import _integer, _text
from ..webcrawler.dragon_native_targets import demand_target


EVIDENCE_LANES = {
    "primary_implementation": "Versioned developer documentation, source or reproducible technical analysis",
    "empirical_measurement": "Methods, sample, raw artifacts, uncertainty and independent replication",
    "observed_play": "Timecoded gameplay with version, input device, skill, cuts and modifications",
    "independent_criticism": "Attributed critique with reviewer expertise, disclosures and corrections",
    "accessibility": "Evaluation with relevant players, settings, devices and documented barriers",
    "rights": "Exact work, rights chain, jurisdiction and current primary legal records",
}

CONTEXT_AXES = (
    "title_edition_region_language", "build_patch_mods", "platform_device_firmware",
    "input_latency_display_audio", "player_experience", "accessibility_settings",
    "session_duration_interruptions", "solo_local_online_player_count",
    "difficulty_seed_rules", "monetization_and_time_cost", "capture_date_and_method",
)


def _select(niche_ids: Iterable[str]) -> tuple:
    ids = bounded(niche_ids, len(NICHES), str)
    if not ids or len(set(ids)) != len(ids) or any(n not in BY_ID for n in ids):
        raise ValueError("nonempty unique known niche IDs required")
    return tuple(BY_ID[n] for n in ids)


def plan_niche_research(niche_ids: Iterable[str], *, platform: str,
                        title: str, max_queries: int = 60,
                        target_ids: Iterable[str] | None = None) -> dict:
    """Round-robin discovery intents; empty evidence lanes remain visibly empty.

    Query completeness means only that every selected niche/target pair has an
    intent. It says nothing about available sources or acquired knowledge.
    """
    niches = _select(niche_ids)
    _text(title, "research subject", 256)
    _text(platform, "platform", 64)
    native = demand_target(platform)
    _integer(max_queries, "query budget", 1, 2048)
    ids = tuple(t.target_id for t in TARGETS) if target_ids is None else bounded(target_ids, len(TARGETS), str)
    target_map = {t.target_id: t for t in TARGETS}
    if not ids or len(set(ids)) != len(ids) or any(t not in target_map for t in ids):
        raise ValueError("nonempty unique known target IDs required")
    selected = tuple(target_map[t] for t in ids)
    pairs = [(n, t) for t in selected for n in niches]
    queries = [{"niche_id": n.niche_id, "target_id": t.target_id,
                "evidence_role": t.evidence_role,
                "query": f"{title} {n.niche_id.replace('_', ' ')} {platform} {t.search_suffix}",
                "required_context": list(t.required_context),
                "retrieved": False, "reputation": "unassessed"}
               for n, t in pairs[:max_queries]]
    dossiers = []
    for n in niches:
        scheduled = sum(q["niche_id"] == n.niche_id for q in queries)
        dossiers.append({**asdict(n), "context_axes": CONTEXT_AXES,
            "measurement_state": "proposed_not_measured",
            "evidence_lanes": {k: {"requirement": v, "state": "not_acquired", "citations": []}
                               for k, v in EVIDENCE_LANES.items()},
            "scheduled_queries": scheduled, "deferred_queries": len(selected) - scheduled,
            "platform_questions": [
                f"Can the mechanics be implemented with {native.input}?",
                f"Can critical cues remain readable with {native.graphics}?",
                "What measured memory, timing, storage and frame budgets apply to this build?",
                "What fallback preserves play when the proposed interface is unavailable?"],
            "experiment_requirements": [
                "Preregister the claim, outcome, comparison and exclusion criteria",
                "Retain raw artifact hashes, methods, sample size and uncertainty",
                "Stratify by relevant skill, device and accessibility context",
                "Record negative results and plausible alternative explanations",
                "Seek independent studies; collapse shared data and syndicated reporting"],
            "originality_state": "prompt_only_not_cleared"})
    body = {"schema": "skeleton.game_builder.niche_research.v1",
            "catalog_digest": niche_catalog()["catalog_digest"],
            "subject": title, "platform": asdict(native), "dossiers": dossiers,
            "queries": queries, "query_pairs_total": len(pairs),
            "query_pairs_deferred": max(0, len(pairs) - len(queries)),
            "acquired_sources": 0, "empirically_validated": False,
            "network_executed": False, "training_authorized": False,
            "memory_promotion_authorized": False, "release_authorized": False}
    return {**body, "plan_digest": canonical_digest(body)}


def plan_niche_hybrid(niche_ids: Iterable[str], *, premise: str) -> dict:
    """Prepare a small design review without treating combinations as clearance."""
    niches = _select(niche_ids)
    if not 2 <= len(niches) <= 4:
        raise ValueError("hybrid review requires two to four niches")
    _text(premise, "original premise", 1024)
    tensions = [{"niches": [a.niche_id, b.niche_id], "state": "requires_prototype",
                 "questions": [
                     "Do timing and turn rules preserve agency in both mechanics?",
                     "Do progression and failure recovery create contradictory incentives?",
                     "Can information and controls remain accessible when combined?",
                     "Does either mechanic become compulsory busywork for the other?"]}
                for a, b in combinations(niches, 2)]
    body = {"schema": "skeleton.game_builder.niche_hybrid.v1", "premise": premise,
            "mechanics_by_niche": {n.niche_id: n.mechanics for n in niches},
            "pair_reviews": tensions,
            "prototype_tests": [{"niche_id": n.niche_id, "measure": n.proposed_measurement,
                                 "failure_probe": n.failure_probe} for n in niches],
            "review_axes": ["era", "genre", "story", "visual_style", "time_setting", "gameplay"],
            "required_handoff": "successor_blueprints.plan_successor_pipeline",
            "rights_inherited": False, "originality_verified": False,
            "product_built": False, "release_authorized": False}
    return {**body, "hybrid_digest": canonical_digest(body)}


def main() -> None:
    import argparse
    from .contracts import canonical_json
    parser = argparse.ArgumentParser(description="Inspect gaming niche research agendas")
    parser.add_argument("--catalog", action="store_true")
    parser.add_argument("--niche", action="append")
    parser.add_argument("--platform")
    parser.add_argument("--title")
    parser.add_argument("--max-queries", type=int, default=60)
    args = parser.parse_args()
    if args.catalog:
        result = niche_catalog()
    elif not args.niche or not args.platform or not args.title:
        parser.error("--niche, --platform and --title are required unless --catalog is used")
    else:
        result = plan_niche_research(args.niche, platform=args.platform,
                                     title=args.title, max_queries=args.max_queries)
    print(canonical_json(result))


if __name__ == "__main__":
    main()
