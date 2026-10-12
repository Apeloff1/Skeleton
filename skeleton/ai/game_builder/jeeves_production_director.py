"""Conversation-to-production work orders for the Jeeves AI game builder.

Generates *instructions for the connected model* and exact editor targets,
not authored fiction, art, audio or neural weights. Approval stays with the
human reviewer after independent source and historical-canon verification.
"""
from __future__ import annotations

from copy import deepcopy
from .story_canon_fabric import (
    BIBLE, PHASES, StoryCanonError, digest, require, text,
    story_bible_template, story_scene_template, scene_path)
from .story_workspace import (load_story_workspace, load_continuity_contract,
                              story_workspace_brief)


WORK_UNITS = {
    "foundation": (
        "Define original game premise and dramatic conflict",
        "Outline all planned acts, chronology, divergent and nonterminal endings",
        "Define era, geography, theology when applicable, and invariant world laws",
        "Build lore anchors and original thematic inspirations, not copied stories",
        "Check source provenance and content rights before incorporation",
    ),
    "cast": (
        "Create original protagonists, NPCs, antagonist motivations and faction roles",
        "Design unique personality, voice constraints, interests and evolution",
        "Specify canonical silhouettes, hair, eyes, costumes and color palettes",
        "Establish initial lives, relationships, affiliations and exact locations",
        "Cross-check derivatives, names, likenesses and inspiration rights",
    ),
    "design": (
        "Define each region, settlement, theme, architecture and light treatment",
        "Build coherent canonical palettes and permitted scene-local color schemes",
        "Specify original character, item, skill, prop, environment and UI assets",
        "Specify animation, sound, music and cinematic requirements by asset identity",
        "Review provenance and mark individual assets approved only after rights review",
    ),
    "continuity_lock": (
        "Approve 100 chapters, 1000 acts and 9999 individually confirmed scenes",
        "Lock source voice ID and voice master hash for every character",
        "Lock permanent facial geometry and dialogue-to-expression rules",
        "Approve clothing variants, cloth textures, items and historical owners",
        "Lock regional era, architecture, material vocabulary and hex palettes",
        "Review asset/voice rights before any scene production",
        "Require uninterrupted exact-source and confirmation digest chains",
    ),
    "scene": (
        "Retrieve exact prior dialogue, interaction and causal event bookmarks",
        "Write scene beats in true event order and resolve character travel",
        "Write every character dialogue line with listener, voice intent and references",
        "Specify each NPC interaction, causal choice, quest trigger and consequence",
        "Bind every onscreen asset to original source identity and regional palette",
        "Verify all cast looks and mutable state against the scene-one canon",
        "Run full-history consistency review before proposing the scene for approval",
    ),
}
ASSET_JOB_KINDS = ("character", "environment", "prop", "item", "ability",
                   "animation", "audio", "vfx", "ui")


def work_order(workspace, project, user_message, *, cast=None, region=None,
               act=None, scene=None):
    """Create a full source-bound order for one Jeeves chat turn.

    A deterministic stage gate prevents generating scenes before story, cast,
    regional design and rights review exist. Revisions never silently mutate
    an existing accepted source.
    """
    text(user_message, "conversation instruction", 10000)
    bible, scenes, index = load_story_workspace(workspace, project)
    target = "game/story_bible.json"
    if bible is None:
        stage = "foundation"
        blank = story_bible_template(project)
        requires = []
        context = {"foundation_reviewed": False}
    elif bible["phase"] != "design":
        next_phase = PHASES[PHASES.index(bible["phase"])+1]
        stage = next_phase
        blank = deepcopy(bible)
        blank["phase"] = next_phase
        blank["digest"] = None
        requires = [bible["digest"]]
        context = {"previous_phase": bible["phase"],
                   "previous_bible_digest": bible["digest"]}
    elif not load_continuity_contract(workspace, project) and not scenes:
        from .story_continuity_assurance import contract_template
        stage = "continuity_lock"
        blank = contract_template(bible)
        target = "game/continuity_contract.json"
        requires = [bible["digest"]]
        context = {"approved_design_bible": bible["digest"],
                   "immutable_voice_and_face_identity_required": True,
                   "planned_acts": 100, "planned_scenes": 9999}
    else:
        stage = "scene"
        if act is None:
            if scenes and (scenes[-1]["scene"] >= 10 or
                    scenes[-1].get("storytelling",{}).get("chapter_outcome")
                        in ("resolution","cliffhanger")):
                act = scenes[-1]["act"] + 1
            else:
                act = scenes[-1]["act"] if scenes else 1
        if scene is None:
            scene = ((scenes[-1]["scene"] + 1)
                     if scenes and act == scenes[-1]["act"] else 1)
        if type(act) is not int or type(scene) is not int:
            raise StoryCanonError("scene coordinates must be exact integers")
        if load_continuity_contract(workspace, project) is not None:
            from .story_continuity_assurance import SCENE_TARGET
            if len(scenes) >= SCENE_TARGET:
                raise StoryCanonError("9999 meticulously verified scenes completed")
            if not scenes and (act,scene) != (1,1):
                raise StoryCanonError("strict story production begins at act 1 scene 1")
            if scenes and not ((act == scenes[-1]["act"] and
                                scene == scenes[-1]["scene"]+1) or
                               (act == scenes[-1]["act"]+1 and scene == 1)):
                raise StoryCanonError("Jeeves must author one exact next scene at a time")
        if load_continuity_contract(workspace,project) is not None:
            from .story_workspace import next_story_scene_template
            prepared = next_story_scene_template(
                workspace,project,act,scene)
            blank=prepared["document"]
            target=prepared["path"]
        else:
            blank = story_scene_template(bible, sequence=len(scenes)+1,
                                         act=act, scene=scene)
            blank["prior_digest"] = index["head_digest"]
            target = scene_path(blank)
        requires = [bible["digest"]] + ([index["head_digest"]]
                                        if index["head_digest"] else [])
        context = {"history_head_digest": index["head_digest"],
                   "history_index_digest": index["digest"],
                   "accepted_scenes": len(scenes),
                   "required_act": act, "required_scene": scene,
                   "required_chapter":blank.get("chapter"),
                   "strict_identity_contract_digest":
                       (load_continuity_contract(workspace,project) or {}).get("digest"),
                   "legacy_source_history_unlocked":
                       load_continuity_contract(workspace,project) is None}
        if cast is not None or region is not None:
            require(type(cast) is list and region is not None,
                    "Jeeves scene instructions need both cast and region")
            context["full_canon_brief"] = story_workspace_brief(
                workspace, project, cast=cast, region=region,
                prompt=user_message, max_bookmarks=48)
        else:
            context["full_canon_brief"] = None
            context["requires_cast_and_region_before_generation"] = True
    body = {
        "schema": "skeleton.game_builder.jeeves_production_workorder.v1",
        "project": project, "conversation_prompt": user_message,
        "stage": stage, "target_path": target,
        "source_template": blank,
        "predecessor_source_digests": requires,
        "source_context": context,
        "creative_tasks": list(WORK_UNITS[stage]),
        "generation_discipline": (
            "originality", "scene_specificity", "referential_continuity",
            "no_unlicensed_character_or_art_copying",
            "full_story_history_validation", "no_model_memory_fabrication",
            "chapter_context_handoff", "plot_point_highlighter",
            "prologue_prelude_interlude_editing",
            "chapter_suspense_and_resolution", "cinematic_staging"
        ),
        "independent_review_required": [
            "wiki_story_facts", "mirror_continuity_adversarial",
            "assets_palette_and_identity", "source_and_rights",
            "human_commit_approval",
            "chapter_plot_highlighters", "scene_tension_closure",
        ],
        "model_inference_performed": False,
        "provider_connected_by_this_call": False,
        "source_files_changed": False,
        "native_game_exported": False,
        "human_authority_not_delegated": True,
    }
    return {**body, "digest": digest(body)}


def planned_asset_orders(workspace, project, user_message, *,
                         region=None, kinds=None, max_jobs=128):
    """Detailed discipline-specific asset task queue, strictly after design."""
    text(user_message, "creative asset production goal", 5000)
    bible, history, index = load_story_workspace(workspace, project)
    require(bible is not None and bible["phase"] == "design",
            "asset production requires approved story, cast and world design")
    require(type(max_jobs) is int and 1 <= max_jobs <= 2048,
            "bounded asset production queue required")
    if kinds is None:
        kinds = list(ASSET_JOB_KINDS)
    require(type(kinds) is list and 1 <= len(kinds) <= len(ASSET_JOB_KINDS)
            and all(k in ASSET_JOB_KINDS for k in kinds),
            "select only supported asset production disciplines")
    require(len(kinds) == len(set(kinds)), "asset disciplines must be unique")
    regions = {r["id"]: r for r in bible["regions"]}
    require(region is None or region in regions, "unknown regional art direction")
    queue = []
    for asset in bible["assets"]:
        if asset["kind"] not in kinds or (region is not None
                                         and asset["region"] != region):
            continue
        approval = asset["rights"] == "original_reviewed"
        queue.append({
            "asset": asset["id"],
            "discipline": asset["kind"],
            "region": asset["region"],
            "spec": asset["spec"],
            "original_identity": asset["identity"],
            "identity_digest": digest(asset),
            "palette": asset["palette"],
            "regional_style": regions[asset["region"]],
            "historical_scene_appearances": index["assets"].get(asset["id"], []),
            "generation_allowed": approval,
            "blocked_reason": None if approval else "rights_review_required",
            "rendered_asset_created": False,
            "cross_scene_visual_reference_required": True,
        })
    selected = queue[:max_jobs]
    result = {"schema": "skeleton.game_builder.jeeves_asset_workorders.v1",
              "project": project, "prompt": user_message,
              "source_bible": bible["digest"], "history_digest": index["digest"],
              "jobs": selected, "total_matching": len(queue),
              "jobs_truncated": len(queue) > len(selected),
              "native_assets_generated": False, "rights_certified": False,
              "external_model_invocation_completed": False,
              "human_source_review_required": True}
    return {**result, "digest": digest(result)}
