"""Whole-game structured story production manifest.

Computes *structural* coverage only. No manifest, even one covering every
scene, may claim absolute artistic correctness, historical authenticity,
dialogue quality, audio identity, or factual completeness without independent
review evidence. Reports missing indexes and chain mismatches explicitly.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from core.chapter_continuity import (
    MAX_ACTS, MAX_CHAPTERS, MAX_SCENES,
    PROOFREAD_INSPECTIONS, chapter_for_act, digest,
)

MANIFEST_SCHEMA = "jeeves.story.production-manifest.v1"


def production_manifest(
    chapters: Sequence[Mapping[str, Any]],
    scenes: Sequence[Mapping[str, Any]],
    *, complete_source: bool = True,
) -> dict[str, Any]:
    if len(chapters) > MAX_CHAPTERS or len(scenes) > MAX_SCENES:
        raise ValueError("Production manifest exceeds canonical project dimensions.")
    by_chapter: dict[int, Mapping[str, Any]] = {}
    seen_scenes: dict[int, Mapping[str, Any]] = {}
    seen_acts: set[int] = set()
    faults: list[dict[str, Any]] = []
    issue_count = 0

    def fault(kind: str, number: int, detail: str):
        nonlocal issue_count
        issue_count += 1
        if len(faults) < 200:
            faults.append({"kind": kind, "number": number, "detail": detail})

    stable_voices: dict[str, str] = {}
    stable_faces: dict[str, str] = {}
    for record in chapters:
        number = record.get("chapter")
        if type(number) is not int or not 1 <= number <= MAX_CHAPTERS:
            fault("chapter_out_of_range", 0, "Chapter coordinate is malformed.")
            continue
        if number in by_chapter:
            fault("duplicate_chapter", number, "Chapter identity repeated.")
        by_chapter[number] = record
        for kind, registry in (("voice", stable_voices), ("face", stable_faces)):
            for actor, marker in record.get(kind + "_cast", {}).items():
                if actor in registry and registry[actor] != marker:
                    fault(kind + "_replacement", number, "Character " + actor + " identity changed.")
                registry.setdefault(actor, marker)

    last_act = 0
    preceding_digest: str | None = None
    approved = 0
    proofed = 0
    plotted = 0
    for record in sorted(scenes, key=lambda x: x.get("scene", 0)):
        number = record.get("scene")
        act = record.get("act")
        chapter = record.get("chapter")
        if type(number) is not int or not 1 <= number <= MAX_SCENES:
            fault("scene_out_of_range", 0, "Scene coordinate is malformed.")
            continue
        if number in seen_scenes:
            fault("duplicate_scene", number, "Scene identity repeated.")
        seen_scenes[number] = record
        if type(act) is not int or not 1 <= act <= MAX_ACTS:
            fault("act_out_of_range", number, "Act coordinate is malformed.")
        else:
            seen_acts.add(act)
            if act < last_act:
                fault("act_out_of_sequence", number, "Act moves backwards.")
            last_act = act
            if chapter != chapter_for_act(act):
                fault("chapter_mismatch", number, "Scene act belongs to another chapter.")
        referenced = by_chapter.get(chapter)
        if referenced is None:
            fault("chapter_unavailable", number, "No chapter rules are recorded.")
        elif (record.get("chapter_digest") != referenced.get("digest")
              or record.get("chapter_revision") != referenced.get("revision")):
            fault("stale_chapter", number, "Scene binds an outdated chapter note.")
        if record.get("status") == "approved_for_production":
            approved += 1
        else:
            fault("not_approved", number, "Human scene sign-off is absent.")
        proof = record.get("proof") or {}
        if (proof.get("status") == "machine_checks_passed"
            and proof.get("inspections_executed") == PROOFREAD_INSPECTIONS
            and proof.get("history_complete") is True
            and not proof.get("blocking_issues")
            and proof.get("scene_digest") == record.get("digest")
            and proof.get("chapter_digest") == record.get("chapter_digest")
            and proof.get("chapter_revision") == record.get("chapter_revision")):
            proofed += 1
        else:
            fault("proof_missing", number, "Current 100k inspection receipt is absent or blocked.")
        if proof.get("predecessor_scene_digest") != preceding_digest:
            fault("broken_receipt_chain", number, "Prior accepted scene digest no longer matches.")
        if not record.get("plot_points"):
            fault("plot_unmarked", number, "Plot points have no reviewed anchors.")
        else:
            plotted += 1
        if referenced:
            for actor in record.get("characters", []):
                if (actor not in referenced.get("voice_cast", {})
                    or actor not in referenced.get("face_cast", {})):
                    fault("unbound_character", number, "Character " + actor + " lacks pinned face/voice.")
        preceding_digest = record.get("digest")

    missing_chapters = [i for i in range(1, MAX_CHAPTERS + 1) if i not in by_chapter]
    missing_acts = [i for i in range(1, MAX_ACTS + 1) if i not in seen_acts]
    missing_scenes = [i for i in range(1, MAX_SCENES + 1) if i not in seen_scenes]
    complete = (
        bool(complete_source) and not missing_chapters and not missing_acts
        and not missing_scenes and issue_count == 0
        and approved == MAX_SCENES and proofed == MAX_SCENES and plotted == MAX_SCENES
    )
    evidence = {
        "chapters": [(k, x.get("digest")) for k, x in sorted(by_chapter.items())],
        "scenes": [(k, x.get("digest"), (x.get("proof") or {}).get("receipt_digest"))
                   for k, x in sorted(seen_scenes.items())],
    }
    return {
        "schema_version": MANIFEST_SCHEMA,
        "complete_source": bool(complete_source),
        "structural_ready": bool(complete),
        "continuity_100_percent_guaranteed": False,
        "human_creative_quality_review_required": True,
        "coverage": {
            "chapter_notes": len(by_chapter),
            "chapters_expected": MAX_CHAPTERS,
            "acts_with_scenes": len(seen_acts),
            "acts_expected": MAX_ACTS,
            "scene_drafts": len(seen_scenes),
            "scenes_expected": MAX_SCENES,
            "scenes_approved": approved,
            "scenes_proofed": proofed,
            "scenes_plot_marked": plotted,
            "structural_completion_pct": round(
                100 * (len(by_chapter) + len(seen_acts) + proofed) /
                (MAX_CHAPTERS + MAX_ACTS + MAX_SCENES), 4,
            ),
        },
        "missing_chapters": missing_chapters[:100],
        "missing_acts": missing_acts[:100],
        "missing_acts_count": len(missing_acts),
        "missing_scenes": missing_scenes[:100],
        "missing_scenes_count": len(missing_scenes),
        "issues": faults,
        "issue_count": issue_count,
        "receipt_digest": digest(evidence),
        "verification_type": "deterministic_structural_receipts_not_semantic_truth",
    }
