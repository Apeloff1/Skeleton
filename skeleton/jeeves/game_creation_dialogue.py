"""Jeeves's native conversational game-creation questionnaire and creator bridge.

No second inference provider, application API, editor authority or durable store.
The local model uses host-registered read-only tools to compile B014 creator
plans. Only the existing permitted creator runbook can execute those plans.
"""
from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
import json
import re
from typing import Any

SCHEMA = "skeleton.jeeves.game_creation_dialogue.v1"
MAX_FACETS = 32
FIELDS = ("intent", "constraints", "variants")
FACETS = {
    "concept": ("Game vision", "Audience, target platforms", "Full-game scope"),
    "story": ("Narrative premise", "Canon and causality", "Alternate acts and endings"),
    "world": ("World history and rules", "Regions and connections", "Coherent world variation"),
    "geography": ("Terrain, sky islands and biomes", "Routes and travel types", "Weather and hazards"),
    "character": ("Cast identities", "Motivations and histories", "Visual identity and evolution"),
    "npc": ("Population roles", "NPC memory and agency", "Reaction and reputation"),
    "dialogue": ("Speaker knowledge and voice", "Branches and state", "Consequences and continuity"),
    "scene": ("Scene setting and goal", "Beats and staging", "Alternate outcomes"),
    "quest": ("Quest goal", "Prerequisites and consequences", "Alternative solutions"),
    "faction": ("Groups and allegiances", "Political and social constraints", "Reputation consequences"),
    "level": ("Level topology", "Traversal and pacing", "Hidden paths and accessibility"),
    "mechanics": ("Player verbs", "System invariants", "Progression and difficulty"),
    "combat": ("Combat verbs", "Balance and timing", "Counterplay and recoverability"),
    "physics": ("Motion and forces", "Body and material behavior", "Determinism and stability"),
    "environment": ("Weather and fluids", "Lighting and shadows", "Environmental reactions"),
    "asset": ("Original asset requirements", "Visual fidelity and era", "Variants and LODs"),
    "animation": ("Subjects and motion", "Transition timing", "Temporal consistency"),
    "music": ("Music identity", "Gameplay synchronization", "Mix and adaptive variations"),
    "audio": ("Audio events", "Spatial effects", "Subtitles and alternatives"),
    "cinematics": ("Shot intent", "Actor and camera blocking", "Branching timelines"),
    "interface": ("Screen and control flows", "Feedback and state", "Accessibility and mobile"),
    "inventory": ("Items and slots", "Crafting and acquisition", "Persistent invariants"),
    "economy": ("Currencies and resources", "Market rules", "Sinks and anti-exploits"),
    "procedural": ("Generation grammars", "Seeds and bounds", "Canon-coherent variation"),
    "camera": ("Camera modes", "2.5D/3D rotation", "Occlusion and transitions"),
    "engine": ("Engine selection", "Runtime features", "Build and export"),
    "platform": ("Consoles and OS targets", "Resource profiles", "Input and rendering"),
    "testing": ("Full-game journeys", "Acceptance invariants", "Evidence and regression"),
    "release": ("Distribution channels", "Copyright and originality", "Rollback"),
    "training": ("Curriculum and target skills", "Licensed references", "Independent evaluations"),
}
MEDIA = ("text", "image", "audio", "video", "scene_frame", "3d_asset")
HEX = re.compile(r"[0-9a-f]{64}\Z")


def _canonical(value: Any) -> bytes:
    try:
        raw = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError("Non-canonical game-creation input") from exc
    if len(raw) > 256 * 1024:
        raise ValueError("Game creation request exceeds byte budget")
    return raw


def _sha(value: Any) -> str:
    return sha256(_canonical(value)).hexdigest()


def _validate_answers(facet: str, answers: Any) -> dict[str, str]:
    if facet not in FACETS:
        raise ValueError("Unknown game-creation facet")
    if not isinstance(answers, dict) or len(answers) > 3 or set(answers) - set(FIELDS):
        raise ValueError("Invalid questionnaire fields")
    result = {}
    for key, value in answers.items():
        if (not isinstance(value, str) or not value.strip() or len(value) > 4096
                or any(ord(c) < 32 and c not in "\n\t" for c in value)):
            raise ValueError("Questionnaire answers require bounded nonempty text")
        result[key] = value.strip()
    return result


def questionnaire(facet: str, answers: dict[str, str] | None = None) -> dict[str, Any]:
    values = _validate_answers(facet, {} if answers is None else answers)
    missing = [{"id": key, "question": title} for key, title in zip(FIELDS, FACETS[facet])
               if key not in values]
    return {"schema_version": SCHEMA, "facet": facet, "answers": values,
            "questions_remaining": missing, "complete": not missing,
            "answers_sha256": _sha({"facet": facet, "answers": values}),
            "execution_authority": "none"}


def catalog() -> dict[str, Any]:
    return {"schema_version": SCHEMA,
            "facets": [{"name": facet, "questions": [
                {"id": name, "question": text} for name, text in zip(FIELDS, titles)]}
                for facet, titles in FACETS.items()],
            "count": len(FACETS), "execution_authority": "none",
            "model": "standalone Jeeves; multimodal references are augmentations",
            "execution": "existing host creator runbook, grants and receipts"}


def _media(media: Any) -> list[dict[str, str]]:
    if not isinstance(media, list) or len(media) > 32:
        raise ValueError("Expected at most 32 content-addressed multimodal references")
    seen = set()
    for entry in media:
        if not isinstance(entry, dict) or set(entry) != {
            "modality", "asset_sha256", "source_id", "rights_review_id"
        }:
            raise ValueError("Media needs exact provenance fields")
        if entry["modality"] not in MEDIA or not isinstance(entry["asset_sha256"], str) or not HEX.fullmatch(entry["asset_sha256"]):
            raise ValueError("Unsupported modality or content digest")
        if any(not isinstance(entry[key], str) or not 3 <= len(entry[key]) <= 128
               for key in ("source_id", "rights_review_id")):
            raise ValueError("Media source and rights review identities are required")
        identity = (entry["modality"], entry["asset_sha256"])
        if identity in seen:
            raise ValueError("Duplicate media reference")
        seen.add(identity)
    return list(media)


def compose(project_id: str, selections: Mapping[str, dict[str, str]],
            media: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Propose a complete multi-forge workflow, not an implicit execution.

    CreatorRunbookRunner with host-injected CreatorRunbookStore and per-step
    ToolGrants is the only mutating path. Queued work is not completed work.
    """
    from skeleton.jeeves.app_capability_bridge import creator_plan
    if not isinstance(selections, Mapping) or not 1 <= len(selections) <= MAX_FACETS:
        raise ValueError("A game workflow needs 1..32 selected facets")
    references = _media([] if media is None else media)
    steps = []
    for facet in FACETS:
        if facet not in selections:
            continue
        answers = _validate_answers(facet, selections[facet])
        if len(answers) != 3:
            raise ValueError("Incomplete questionnaire: " + facet)
        intent = {"schema_version": SCHEMA, "facet": facet, "answers": answers,
                  "media_references": references,
                  "input_sha256": _sha({"answers": answers, "media": references}),
                  "authority": "proposal_only"}
        steps.append({"step_id": "facet_" + facet, "operation": "create",
                      "payload": {"intent": intent},
                      "after": [steps[-1]["step_id"]] if steps else []})
    if len(steps) != len(selections):
        raise ValueError("Unknown facet in requested workflow")
    plan = creator_plan(project_id, steps)
    return {"schema_version": SCHEMA, "kind": "game-creation-flow",
            "facets": [step["step_id"][6:] for step in steps],
            "plan": plan, "plan_sha256": plan["plan_sha256"],
            "media_sha256": _sha(references), "dispatch_performed": False,
            "execution_authority": "none", "requires_durable_runbook": True}


def verify_receipts(flow: Mapping[str, Any], receipts: list[Any]) -> dict[str, Any]:
    """Independently check every completed B014 creator receipt; chain hashes."""
    from skeleton.forge.creator.command_surface import (
        CreatorCommandReceipt, build_creator_command, validate_creator_receipt,
    )
    if not isinstance(flow, Mapping) or flow.get("schema_version") != SCHEMA:
        raise ValueError("Invalid flow")
    plan = flow.get("plan")
    if (not isinstance(plan, dict) or plan.get("plan_sha256") != flow.get("plan_sha256")
            or not isinstance(plan.get("steps"), list)
            or not isinstance(receipts, list) or len(receipts) != len(plan["steps"])):
        raise ValueError("Plan/receipt mismatch")
    prior = "0" * 64
    for step, receipt in zip(plan["steps"], receipts):
        data = step["command"]
        command = build_creator_command(data["operation"], project_id=data["project_id"],
                                        payload=data["payload"])
        if command.to_dict() != data or not isinstance(receipt, CreatorCommandReceipt):
            raise ValueError("Invalid exact-command receipt")
        validate_creator_receipt(receipt, command)
        prior = _sha({"previous": prior, "step": step["step_id"],
                      "command": command.digest, "receipt": receipt.digest})
    return {"schema_version": SCHEMA, "plan_sha256": flow["plan_sha256"],
            "verified_steps": len(receipts), "receipt_chain_sha256": prior,
            "complete": True, "certifies_game_quality": False}


def register_dialogue_tools(registry) -> tuple[str, ...]:
    """Add the local model's read-only interactive control surface to the host."""
    from skeleton.jeeves.agent.tools import ArgumentRule, ToolRegistry, ToolSpec
    from skeleton.jeeves.agent.types import RiskTier
    if not isinstance(registry, ToolRegistry):
        raise TypeError("Expected existing host-owned Jeeves ToolRegistry")
    tools = (
        (ToolSpec(name="game_creation_catalog", description="Discover 30 game-production forges, questionnaires and flows.",
                  risk=RiskTier.READ_ONLY),
         lambda _args, _context: catalog()),
        (ToolSpec(name="game_creation_questions", description="Collect and resume typed game-making questionnaire answers.",
                  risk=RiskTier.READ_ONLY,
                  arguments=(ArgumentRule("facet", "string", choices=tuple(FACETS)),
                             ArgumentRule("answers", "object", required=False, max_length=3))),
         lambda args, _context: questionnaire(args["facet"], args.get("answers"))),
        (ToolSpec(name="game_creation_compose", description="Compile all selected forges into authorized-host-only creator runbook plan.",
                  risk=RiskTier.READ_ONLY,
                  arguments=(ArgumentRule("project_id", "string", max_length=128),
                             ArgumentRule("selections", "object", max_length=MAX_FACETS),
                             ArgumentRule("media", "array", required=False, max_length=32))),
         lambda args, _context: compose(args["project_id"], args["selections"],
                                        args.get("media"))),
    )
    for spec, handler in tools:
        registry.register(spec, handler)
    return tuple(spec.name for spec, _ in tools)
