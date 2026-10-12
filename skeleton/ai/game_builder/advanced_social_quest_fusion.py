"""Original multi-engine social causality: executable NPC/Dialogue/Quest transactions.

Each subsystem remains the existing advanced *actual gameplay* reference
engine. A cross-family action executes only legal world actions, inside all
three independent source worlds, then checks direct testimony and finite
material consequences. Nothing is injected into their resulting states.

The worlds currently use different physical coordinate systems. The bridge
therefore binds authored narrative roles, not a fictitious shared coordinate
space or a claim that an NPC is omnipresent between different games.
"""
from __future__ import annotations

from hashlib import sha256
import json

from .advanced_gameplay_runtime import (
    ACTION_HELP, AdvancedRuntimeError, run_advanced_session,
    verify_advanced_session,
)
from .advanced_level_scenes import make_advanced_scene, validate_advanced_scene
from .system_editors import make_editor_document

SCHEMA = "skeleton.game_builder.social_quest_fusion.v1"
FAMILIES = ("dialogue", "npc_society", "quest_director")
MAX_COMMANDS = 64
MAX_REPORT_BYTES = 260_000
BRIDGE_ACTIONS = tuple(
    f"bridge:{verb}:{id_}"
    for verb in ("interview", "pledge", "conclude") for id_ in range(3)
)
ROLE_BINDINGS = (
    {"dialogue_speaker": 0, "society_resident": 0, "quest_npc": 0,
     "dialogue_topic": 0, "quest_site": 0},
    {"dialogue_speaker": 1, "society_resident": 1, "quest_npc": 1,
     "dialogue_topic": 1, "quest_site": 1},
    {"dialogue_speaker": 2, "society_resident": 2, "quest_npc": 2,
     "dialogue_topic": 2, "quest_site": 2},
)


class SocialFusionError(AdvancedRuntimeError):
    """No forged multi-game speaker, source, spatial route or quest credit."""


def _canonical(data):
    try:
        return json.dumps(data, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise SocialFusionError("composite original social evidence is not bounded JSON") from exc


def _digest(data):
    return sha256(_canonical(data).encode("utf-8")).hexdigest()


def _sources(settings, scenes, seed):
    if type(seed) is not int or not 0 <= seed <= 2**31 - 1:
        raise SocialFusionError("source world seed must be a bounded original integer")
    if settings is None:
        settings = {}
    if type(settings) is not dict or set(settings) - set(FAMILIES):
        raise SocialFusionError("only declared original social game settings are supported")
    if scenes is None:
        scenes = {}
    if type(scenes) is not dict or set(scenes) - set(FAMILIES):
        raise SocialFusionError("unknown or unreviewed authored world in social fusion")
    rules = {}
    source_scenes = {}
    identity = {}
    for family in FAMILIES:
        config = make_editor_document(family, settings.get(family))
        rules[family] = config["settings"]
        scene = (
            validate_advanced_scene(scenes[family], config["settings"])
            if family in scenes
            else make_advanced_scene(family, config["settings"], seed=seed)
        )
        if scene["editor"] != family or scene["seed"] != seed:
            raise SocialFusionError("three source worlds must bind the same authored seed")
        source_scenes[family] = scene
        identity[family] = {
            "settings_digest": config["digest"],
            "scene_digest": scene["digest"],
        }
    return rules, source_scenes, identity


def _session(family, commands, configs, scenes, seed):
    if len(commands) > 128:
        raise SocialFusionError("social play cannot exceed an original engine turn budget")
    result = run_advanced_session(
        family, configs[family], commands, seed=seed, scene=scenes[family],
    )
    return result


def _find_quest(q, site_id, npc_id):
    for quest in q["quests"]:
        if quest["site_id"] != site_id or quest["status"] != "active":
            continue
        if npc_id not in quest["witnesses"]:
            continue
        event = next((e for e in q["events_log"]
                      if e["id"] == quest["origin_event"]), None)
        if event is None or event["site_id"] != site_id or (
            npc_id not in event["direct_witnesses"]
        ):
            continue
        actor = q["npcs"][npc_id]
        eyewitness = next((
            m for m in actor["memories"]
            if m["event_id"] == event["id"] and m["source"] == "eyewitness"
        ), None)
        if eyewitness is None:
            continue
        return quest, event, eyewitness
    raise SocialFusionError(
        "original quest needs a physical witnessed event and actual firsthand NPC memory"
    )


def _mapping_valid(role, state):
    d, n, q = (state[f]["state"] for f in FAMILIES)
    i = role["dialogue_speaker"]
    if i >= len(d["speakers"]) or i >= len(n["residents"]) or i >= len(q["npcs"]):
        raise SocialFusionError("unmodeled residents cannot pretend to be source witnesses")
    speaker = d["speakers"][i]
    resident = n["residents"][i]
    quest_npc = q["npcs"][i]
    if (speaker["id"] != i or speaker["topic"] != role["dialogue_topic"]
        or resident["id"] != i or quest_npc["id"] != i
        or role["quest_site"] != role["dialogue_topic"]):
        raise SocialFusionError("narrative role lacks exact original authored source mapping")
    if not any(w["id"] == i for w in n["witnesses"]):
        raise SocialFusionError("society mapping lacks an authored actual resident witness")
    return d, n, q


def _bridge(command, staged, sessions, records, rules, scenes, seed):
    _, verb, raw = command.split(":")
    if type(raw) is not str or raw not in ("0", "1", "2"):
        raise SocialFusionError("unsupported original multi-game narrative role")
    role = ROLE_BINDINGS[int(raw)]
    i = role["dialogue_speaker"]
    d, n, q = _mapping_valid(role, sessions)
    qrec = next((r for r in records if r["actor"] == i and r["kind"] == "interview"), None)
    if verb == "interview":
        if qrec is not None:
            raise SocialFusionError("one source event cannot mint duplicate role binding")
        if d["speakers"][i]["heard"]:
            raise SocialFusionError("cannot import preheard original testimony as fresh evidence")
        if d["position"] != d["speakers"][i]["location"]:
            raise SocialFusionError("dialogue narrator cannot interview an absent speaker")
        if n["focus"] != i and (
            abs(n["position"][0] - n["residents"][i]["position"][0]) +
            abs(n["position"][1] - n["residents"][i]["position"][1]) > 1
        ):
            raise SocialFusionError("civic partner must be physically approachable")
        if (abs(n["position"][0]-n["residents"][i]["position"][0]) +
            abs(n["position"][1]-n["residents"][i]["position"][1]) > 1):
            raise SocialFusionError("cross-system interview requires actual civic presence")
        quest, event, eyewitness = _find_quest(q, role["quest_site"], i)
        if any(x["actor"] == i and x["kind"] == "interview" for x in records):
            raise SocialFusionError("original firsthand binding already consumed")
        changes = {
            "dialogue": [f"speak:{i}"],
            "npc_society": [f"focus:{i}", "talk"],
            "quest_director": [f"speak:{i}"],
        }
        evidence = {
            "kind": "interview", "actor": i, "source_quest": quest["id"],
            "physical_event": event["id"], "physical_event_kind": event["kind"],
            "dialogue_topic": d["speakers"][i]["topic"],
            "quest_firsthand_memory": eyewitness,
            "source_inference": "three_role_context_not_single_spatial_actor",
        }
    elif verb == "pledge":
        if qrec is None or any(r["actor"] == i and r["kind"] == "pledge" for r in records):
            raise SocialFusionError("a social pledge requires one previous real interview")
        quest = next((x for x in q["quests"] if x["id"] == qrec["source_quest"]), None)
        if quest is None or quest["status"] != "active" or quest["choice"] is not None:
            raise SocialFusionError("original causal quest already consumed or missing")
        if i not in quest["testimonies"]:
            raise SocialFusionError("only firsthand quest testimony can authorize public choice")
        if d["speakers"][i]["heard"] < 1 or not d["social_choices_enabled"]:
            raise SocialFusionError("dialogue support requires a real consenting source")
        # A witness may have walked toward the farm/workplace after the
        # interview. Pursue using *actual* legal settlement movement rather
        # than teleporting a resident or manufacturing an assistance receipt.
        pursuit = [] if n["focus"] == i else [f"focus:{i}"]
        for _ in range(16):
            snapshot = _session(
                "npc_society", staged["npc_society"] + pursuit,
                rules, scenes, seed,
            )["state"]
            resident = snapshot["residents"][i]["position"]
            player = snapshot["position"]
            gap_x, gap_y = resident[0]-player[0], resident[1]-player[1]
            if abs(gap_x)+abs(gap_y) <= 1:
                break
            direction = (
                "east" if gap_x>0 else "west" if gap_x<0 else
                "north" if gap_y>0 else "south"
            )
            pursuit.append(direction)
        else:
            raise SocialFusionError("finite physical civic pursuit never reached speaker")
        changes = {
            "dialogue": [f"support:{i}"],
            "npc_society": pursuit + ["help"],
            "quest_director": [f"choose:{quest['id']}:support"],
        }
        evidence = {
            "kind": "pledge", "actor": i, "source_quest": quest["id"],
            "physical_event": qrec["physical_event"],
            "branch": "support", "finite_civic_food_paid": rules["npc_society"]["help_food"],
            "finite_dialogue_influence_paid": rules["dialogue"]["support_cost"],
        }
    elif verb == "conclude":
        pledge = next((x for x in records
                       if x["actor"] == i and x["kind"] == "pledge"), None)
        if pledge is None or any(
            x["actor"] == i and x["kind"] == "conclude" for x in records
        ):
            raise SocialFusionError("social resolution cannot be claimed without one paid pledge")
        resolved = next((x for x in q["quests"] if x["id"] == pledge["source_quest"]), None)
        if resolved is None or resolved["status"] != "resolved" or (
            resolved["ending"] != "restored" or i not in resolved["testimonies"]
        ):
            raise SocialFusionError("real follow-up and physically earned quest resolution absent")
        if not d["checkpoint"] or not any(
            item["speaker"] == i and item["branch"] == "support"
            for item in d["choices"]
        ):
            raise SocialFusionError("original dialogue corroborated social agreement missing")
        if not any(x["resident"] == i and x["kind"] == "assistance"
                   and x["proof"] == "food_inventory" for x in n["memories"]):
            raise SocialFusionError("finite civic welfare assistance has no original receipt")
        if not n["residents"][i]["bond"]:
            raise SocialFusionError("original resident did not actually form social bond")
        changes = {}
        evidence = {
            "kind": "conclude", "actor": i, "source_quest": resolved["id"],
            "physical_event": pledge["physical_event"], "ending": "restored",
            "quest_material_actions": resolved["material_actions"],
            "dialogue_verified_topics": list(d["corroborations"]),
            "society_bond": n["residents"][i]["bond"],
            "composite_nonterminal_milestone": True,
        }
    else:
        raise SocialFusionError("unknown authored social narrative transaction")

    # Evaluate all changes on a new local action stream: no partial engine or
    # final composite state can escape if one of the three actions is illegal.
    replayed = dict(sessions)
    for family, new_commands in changes.items():
        next_actions = staged[family] + new_commands
        replayed[family] = _session(family, next_actions, rules, scenes, seed)

    nd, nn, nq = _mapping_valid(role, replayed)
    if verb == "interview":
        quest_id = evidence["source_quest"]
        linked = next((x for x in nq["quests"] if x["id"] == quest_id), None)
        if (linked is None or i not in linked["testimonies"] or
            not any(s["speaker"] == i for s in nd["direct_statements"]) or
            not any(m["resident"] == i and m["kind"] == "conversation"
                    and m["proof"] == "direct_proximity" for m in nn["memories"])):
            raise SocialFusionError("triple actual firsthand interview failed source review")
    if verb == "pledge":
        linked = next((x for x in nq["quests"] if x["id"] == evidence["source_quest"]), None)
        if (linked is None or linked["choice"] != "support"
            or nd["speakers"][i]["supported"] == 0
            or not any(m["resident"] == i and m["kind"] == "assistance"
                       for m in nn["memories"])):
            raise SocialFusionError("multi-engine pledge never incurred real player costs")
        if nd["influence"] != d["influence"]-rules["dialogue"]["support_cost"]:
            raise SocialFusionError("paid original support did not spend player influence")
        if nn["residents"][i]["bond"] <= n["residents"][i]["bond"]:
            raise SocialFusionError("original resident received no actual social support")
        # Local household farming, background population and consumption
        # legitimately modify society food during each simulated walking
        # turn. The source engine, not a naïve before/after comparison,
        # independently verifies exact stock accounting.
    for family, actions in changes.items():
        staged[family].extend(actions)
    sessions.update(replayed)
    evidence["source_heads"] = {
        name: sessions[name]["head_digest"] for name in FAMILIES
    }
    return evidence


def run_social_quest_fusion(commands, settings=None, *, scenes=None, seed=0):
    """Actually execute a source-bound tri-engine narrative; no file writes."""
    if type(commands) not in (list, tuple) or len(commands) > MAX_COMMANDS:
        raise SocialFusionError("bounded original composite command array required")
    if type(commands) is not list and type(commands) is not tuple:
        raise SocialFusionError("invalid composite command format")
    rules, worlds, source_identities = _sources(settings, scenes, seed)
    staged = {name: [] for name in FAMILIES}
    sessions = {name: _session(name, [], rules, worlds, seed)
                for name in FAMILIES}
    links = []
    journal = []
    for index, command in enumerate(commands):
        if type(command) is not str or not 1 <= len(command) <= 90:
            raise SocialFusionError("original narrative commands must be bounded strings")
        if command in BRIDGE_ACTIONS:
            evidence = _bridge(command, staged, sessions, links,
                               rules, worlds, seed)
            links.append(evidence)
            action_effects = {name: sessions[name]["head_digest"]
                              for name in FAMILIES}
        else:
            family, split, action = command.partition(":")
            if split != ":" or family not in FAMILIES or action not in ACTION_HELP[family]:
                raise SocialFusionError("unknown or unregistered original game-world action")
            candidate = staged[family] + [action]
            session = _session(family, candidate, rules, worlds, seed)
            staged[family].append(action)
            sessions[family] = session
            action_effects = {family: session["head_digest"]}
        event = {
            "index": index, "command": command, "source_heads": action_effects,
            "cross_role_links": len(links),
        }
        journal.append({**event, "digest": _digest(event)})

    for family in FAMILIES:
        if not verify_advanced_session(sessions[family], rules[family]):
            raise SocialFusionError("one source original gameplay engine failed independent replay")
    projections = {
        family: {
            "source_session_digest": sessions[family]["digest"],
            "source_head_digest": sessions[family]["head_digest"],
            "action_count": len(staged[family]),
            "actions": list(staged[family]),
            "state": sessions[family]["state"],
        } for family in FAMILIES
    }
    record = {
        "schema": SCHEMA, "seed": seed, "settings": rules, "scenes": worlds,
        "source_identities": source_identities,
        "commands": list(commands), "journal": journal,
        "bindings": list(ROLE_BINDINGS),
        "narrative_links": links, "worlds": projections,
        "triple_corroborated_interviews": sum(x["kind"] == "interview" for x in links),
        "financed_social_pledges": sum(x["kind"] == "pledge" for x in links),
        "earned_narrative_resolutions": sum(x["kind"] == "conclude" for x in links),
        "any_narrative_terminal": any(
            sessions[f]["state"]["finished"] for f in FAMILIES
        ),
        "distinct_world_coordinates": True,
        "autonomous_phantom_citizens_created": False,
        "model_weights_promoted": False,
        "native_coupled_engine_certified": False,
        "source_projects_mutated": False,
        "release_approved": False,
    }
    if len(_canonical(record).encode("utf-8")) > MAX_REPORT_BYTES:
        raise SocialFusionError("combined authored game-state report exceeds evidence budget")
    return {**record, "digest": _digest(record)}


def verify_social_quest_fusion(report):
    """Reexecute every real source command and every cross-family transaction."""
    if type(report) is not dict or report.get("schema") != SCHEMA:
        raise SocialFusionError("exact original social-fusion evidence schema required")
    try:
        if len(_canonical(report).encode("utf-8")) > MAX_REPORT_BYTES + 1000:
            raise SocialFusionError("oversized multi-engine proof refused")
        expected = run_social_quest_fusion(
            report["commands"], report["settings"], scenes=report["scenes"],
            seed=report["seed"],
        )
    except (KeyError, IndexError, TypeError) as exc:
        raise SocialFusionError("malformed composed original game evidence") from exc
    if expected != report:
        raise SocialFusionError("source role links or composite social outcome forged")
    return True


__all__ = [
    "SCHEMA", "FAMILIES", "ROLE_BINDINGS", "BRIDGE_ACTIONS",
    "SocialFusionError", "run_social_quest_fusion",
    "verify_social_quest_fusion",
]
