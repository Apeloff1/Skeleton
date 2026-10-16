"""Reviewable society forge for original Director worlds, with source-bound consent.

Produces an explicit NPC roster, 4-period routines, finite local shops and
two *actual* conditional transport unlocks: one earned through human/NPC
trust and another unlocked by buying a ticket. The preview writes nothing.
Publishing never overwrites a source or previously approved project.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from skeleton.ai.game_builder.quest_scene_forge import compile_director_blueprint
from skeleton.ai.game_builder.quest_world_dynamics import WorldDynamics, Passage, Requirements
from skeleton.ai.game_builder.quest_society import (
    SocietyRules, Resident, Shop, Good, TrustRequirement, DialogueChoice,
)
from skeleton.developer.jeeves_game_production_board import _load_world

SCHEMA = "skeleton.jeeves.society_design.v1"


def _sha(value: object) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _fresh(prefix: str, used: set[str]) -> str:
    for index in range(1, 10000):
        candidate = prefix[:64] if index == 1 else prefix[:59] + "_" + str(index)
        if candidate not in used:
            used.add(candidate)
            return candidate
    raise ValueError("cannot allocate unique stable original-character identity")


def _draft(world: Any, intensity: int) -> tuple[Any, dict[str, Any]]:
    if type(intensity) is not int or not 1 <= intensity <= 5:
        raise ValueError("social complexity level must be a strict integer 1..5")
    existing = world.dynamics
    if existing is not None and existing.society is not None:
        raise ValueError("source already has an authored NPC society; use a new revision")
    if len(world.scenes) < 2:
        raise ValueError("NPC society requires at least two authored locations")
    scenes = list(world.scenes)
    safe_scene_ids = {s.key for s in scenes}
    faction = existing.factions[0].key if existing and existing.factions else None
    people: list[Resident] = []
    used_names = set()
    count = min(len(scenes) * 2, max(3, intensity * 3), 24)
    cast = sorted({
        person for scene in scenes for person in scene.cast
        if isinstance(person, str) and person.isidentifier()
        and person.isascii() and person.islower() and len(person) <= 64
    })
    if not cast:
        cast = ["traveler", "artisan", "keeper"]
    main_story = next(q for q in world.quests if q.scope == "main")
    canon_choice = main_story.stages[0].solutions[0].outcome_flag
    for number in range(count):
        home = scenes[number % len(scenes)]
        branch = scenes[(number + 1) % len(scenes)]
        key = _fresh("resident_" + str(number + 1), used_names)
        cameo = cast[number % len(cast)]
        rhythm = (home.key, home.key, branch.key, home.key)
        greeting = ("I remember the road through " + home.region.replace("_", " ")
                    + ". Listen to the choices people make before you judge them.")
        unlock = "friend_" + key if number < 3 else None
        dialogue = [
            DialogueChoice(
                key="offer_help",
                prompt="Offer to help without demanding a reward",
                response=("Your generosity matters in " + home.region.replace("_", " ")
                          + ". I will remember that you helped."),
                trust_delta=24,
                reputation_delta=2 if faction is not None else 0,
                requires_flags=(),
                grant_world_flag="aided_" + key,
            ),
            DialogueChoice(
                key="question_motives",
                prompt="Ask hard questions about their responsibilities",
                response=("Trust is earned by actions. My people will remember "
                          "what you choose to do next."),
                trust_delta=-8,
                reputation_delta=-1 if faction is not None else 0,
                requires_flags=(),
                grant_world_flag=None,
            ),
        ]
        if intensity >= 3:
            dialogue.append(DialogueChoice(
                key="reflect_on_choice",
                prompt="Reflect on the first major story decision",
                response=("I know what happened. This region carries the "
                          "consequences, even when the hero moves on."),
                trust_delta=12,
                reputation_delta=1 if faction is not None else 0,
                requires_flags=(canon_choice,),
                grant_world_flag="witness_" + key,
            ))
        people.append(Resident(
            key=key,
            name=cameo.replace("_", " ").title() + " of " + home.region.replace("_", " ").title(),
            faction=faction,
            schedule=rhythm, greeting=greeting,
            initial_trust=0, trust_gain=15 if intensity < 4 else 20,
            reputation_gain=2 if faction is not None else 0,
            unlock_at_trust=40,
            unlock_world_flag=unlock,
            dialogue=tuple(dialogue),
        ))
    # Merchant goods never reuse resources earned from original quest
    # affordances, so player shop sales cannot destroy script-earned items.
    existing_items = {a.produces for scene in scenes for a in scene.affordances
                      if a.produces is not None}
    goods_ids = set(existing_items)
    shops: list[Shop] = []
    price_scale = 10 + intensity * 3
    for index in range(min(intensity + 1, len(scenes), 6)):
        scene = scenes[index]
        seller = people[index]
        offers = []
        for offset in range(1, 2 + (intensity >= 3)):
            good_key = _fresh(
                "trade_" + str(index + 1) + "_good_" + str(offset), goods_ids,
            )
            cost = price_scale * (offset + 1)
            offers.append(Good(
                key=good_key, name="Original " + scene.region.replace("_", " ")
                + " craft " + str(offset),
                buy_price=cost, sell_price=max(0, cost // 2),
                starting_stock=3 + intensity * 3,
            ))
        shops.append(Shop(
            key="bazaar_" + str(index + 1),
            keeper=seller.key, scene=scene.key,
            name=scene.region.replace("_", " ").title() + " Cooperative",
            goods=tuple(offers),
        ))
    society = SocietyRules(
        phase_turns=5 + intensity * 2,
        starting_balance=100 + intensity * 65,
        residents=tuple(people), shops=tuple(shops),
    )
    transport = list(existing.passages) if existing else []
    keys = {route.key for route in transport}
    from_scene = world.starting_scene
    to_scene = next(s.key for s in reversed(scenes) if s.key != from_scene)
    friendship_route = _fresh("trusted_npc_passage", keys)
    transport.append(Passage(
        key=friendship_route,
        source=from_scene, destination=to_scene,
        name="Original resident-guided passage",
        mode="shuttle", cost_turns=2,
        requirements=Requirements(
            trust=(TrustRequirement(
                resident=people[0].key, at_least=40, at_most=100,
            ),),
        ),
        bidirectional=True,
    ))
    ticket_route = _fresh("ticketed_bazaar_passage", keys)
    ticket = shops[0].goods[0].key
    transport.append(Passage(
        key=ticket_route,
        source=from_scene, destination=to_scene,
        name="Ticketed resident night ferry",
        mode="ferry", cost_turns=2,
        requirements=Requirements(items=(ticket,)),
        consume_item=ticket,
        bidirectional=False,
    ))
    updated = WorldDynamics(
        factions=existing.factions if existing else (),
        gates=existing.gates if existing else (),
        passages=tuple(transport),
        influences=existing.influences if existing else (),
        society=society,
    )
    rewritten = world.payload()
    rewritten["dynamics"] = updated.payload()
    compiled = compile_director_blueprint(rewritten, human_reviewed=True)
    if compiled.payload() != rewritten or compiled.digest == world.digest:
        raise ValueError("society design failed exact original world compilation")
    return compiled, {
        "residents": len(people),
        "authored_dialogue_choices": sum(len(n.dialogue) for n in people),
        "merchant_locations": len(shops),
        "merchandise_types": sum(len(shop.goods) for shop in shops),
        "phase_turns": society.phase_turns,
        "starting_balance": society.starting_balance,
        "friendship_transport": friendship_route,
        "consumable_ticket_transport": ticket_route,
        "ticket": ticket,
        "quests_or_original_cast_altered": False,
        "physical_character_ai_or_animation_verified": False,
    }


def preview(root: Path, *, source: str, intensity: int = 3) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_quality import _read
    world, source_sha = _load_world(root, source)
    candidate, stats = _draft(world, intensity)
    proposal = {
        "schema": SCHEMA,
        "source": source,
        "source_sha256": source_sha,
        "original_world_sha256": world.digest,
        "candidate_world_sha256": candidate.digest,
        "intensity": intensity,
        "candidate": {
            "schema": "skeleton.jeeves.director_campaign_source.v1",
            "director_world": candidate.payload(),
            "author_review_acknowledged": False,
        },
        "statistics": stats,
        "actual_model_inference_or_weight_training_performed": False,
        "human_review_required_before_adoption": True,
    }
    identity = _sha(proposal)
    if _read(root, source, 16 * 1024 * 1024)[1] != source_sha:
        raise ValueError("original game changed during source-bound NPC design")
    return {
        "ok": True, "action": "director-society-design",
        "design": proposal, "design_sha256": identity,
        "published": False, "filesystem_writes": 0,
    }


def publish(root: Path, *, source: str, intensity: int,
            approved_sha256: str | None) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_authoring import _create_only
    proposal = preview(root, source=source, intensity=intensity)
    if approved_sha256 != proposal["design_sha256"]:
        raise ValueError("exact --approve society proposal SHA256 required")
    if preview(root, source=source, intensity=intensity) != proposal:
        raise ValueError("game source changed after NPC society review")
    doc = dict(proposal["design"]["candidate"])
    doc["author_review_acknowledged"] = True
    encoded = (json.dumps(doc, sort_keys=True, indent=2,
                          ensure_ascii=True, allow_nan=False) + "\n").encode()
    if len(encoded) > 16 * 1024 * 1024:
        raise ValueError("original world social blueprint exceeds bounded source file size")
    directory = root / "design"
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("missing or unsafe project design directory")
    destination = directory / (
        "director_society_" + proposal["design_sha256"][:24] + ".json"
    )
    _create_only(destination, encoded)
    return {
        "ok": True, "action": "director-society-publish",
        "source": destination.relative_to(root).as_posix(),
        "source_sha256": sha256(encoded).hexdigest(),
        "world_sha256": proposal["design"]["candidate_world_sha256"],
        "original_game_file_overwritten": False,
        "author_has_approved_exact_source_digest": True,
        "native_npc_performance_verified": False,
        "published": True,
    }
