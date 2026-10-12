"""Original playable dialogue worlds: spatial speakers, finite conversations,
first-hand statements, memory, consent, trust, corroboration and branching.

There is no generated unreviewed script or omniscient truth oracle. Authored
speaker/source identities are bound to the replayed scene; dialogue choices
alter a finite social world without changing immutable testimony provenance.
"""
from __future__ import annotations

LOCATIONS = ("plaza", "market", "archive")
TOPICS = ("home", "work", "safety", "history")
ACTIONS = (
    ("inspect", "wait", "rest", "claim", "retire")
    + tuple(f"travel:{i}" for i in range(3))
    + tuple(f"{verb}:{i}" for verb in ("speak", "support", "challenge")
            for i in range(8))
    + tuple(f"compare:{i}" for i in range(4))
)


class DialogueActionError(ValueError):
    """Requested dialogue action cannot be grounded in real source state."""


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise DialogueActionError("invalid bounded original dialogue " + label)
    return value


def _bounded_title(value, label):
    if (type(value) is not str or not 3 <= len(value) <= 64 or
        any(not (c.isalnum() or c in " -_") for c in value)):
        raise DialogueActionError("unsafe unreviewed dialogue " + label)
    return value


def _count(config):
    return min(8, config["speakers"], config["active_speakers_budget"])


def default_layout(config, seed):
    _integer(seed, 0, 2**31 - 1, "seed")
    count = _count(config)
    voices = []
    for i in range(count):
        voices.append({
            "id": i, "name": "Original Voice " + str(i + 1),
            "location": i % 3, "topic": i % 4,
            "position": i % 2, "testimony": ((seed + i * 7) % 5) + 1,
            "agenda": "community" if i % 2 == 0 else "personal",
            "initial_patience": config["speaker_patience"],
        })
    return {
        "title": "Original Dialogue World " + str(seed % 1000),
        "locations": list(LOCATIONS), "speakers": voices,
        "origin": 0, "nonterminal": True,
        "provenance": "original_authored_statements",
    }


def normalize_layout(config, layout):
    if type(layout) is not dict or set(layout) != {
        "title", "locations", "speakers", "origin", "nonterminal", "provenance"
    }:
        raise DialogueActionError("authored dialogue scene requires exact source fields")
    title = _bounded_title(layout["title"], "title")
    if layout["locations"] != list(LOCATIONS):
        raise DialogueActionError("real social stations must retain original identities")
    if type(layout["origin"]) is not int or layout["origin"] not in range(3):
        raise DialogueActionError("original dialogue origin outside authored world")
    if layout["nonterminal"] is not True or (
        layout["provenance"] != "original_authored_statements"
    ):
        raise DialogueActionError("dialogue cannot fabricate a terminal or provider source")
    voices = layout["speakers"]
    if type(voices) is not list or len(voices) != _count(config):
        raise DialogueActionError("real active speakers exceed finite detailed speaker budget")
    validated = []
    names = set()
    for index, voice in enumerate(voices):
        keys = {"id", "name", "location", "topic", "position",
                "testimony", "agenda", "initial_patience"}
        if type(voice) is not dict or set(voice) != keys:
            raise DialogueActionError("original voice needs exact typed source data")
        if _integer(voice["id"], 0, 7, "speaker id") != index:
            raise DialogueActionError("source speaker identifiers cannot be swapped")
        name = _bounded_title(voice["name"], "speaker name")
        if name in names:
            raise DialogueActionError("original speaker names must be distinct")
        names.add(name)
        location = _integer(voice["location"], 0, 2, "spatial speaker location")
        topic = _integer(voice["topic"], 0, 3, "subject identity")
        position = _integer(voice["position"], 0, 1, "interpersonal position")
        testimony = _integer(voice["testimony"], 1, 5, "finite source evidence")
        patience = _integer(voice["initial_patience"], 1,
                            config["speaker_patience"], "source patience")
        if voice["agenda"] not in ("community", "personal"):
            raise DialogueActionError("unsupported authored interpersonal agenda")
        validated.append({
            "id": index, "name": name, "location": location,
            "topic": topic, "position": position, "testimony": testimony,
            "agenda": voice["agenda"], "initial_patience": patience,
        })
    return {
        "title": title, "locations": list(LOCATIONS), "speakers": validated,
        "origin": layout["origin"], "nonterminal": True,
        "provenance": "original_authored_statements",
    }


def _speaker(voice, config):
    return {
        **voice, "trust": config["starting_trust"],
        "patience": voice["initial_patience"], "heard": 0,
        "supported": 0, "challenged": 0,
        "memories": [], "last_heard": None,
    }


def start(config, seed):
    source = normalize_layout(config, default_layout(config, seed))
    return {
        "tick": 0, "title": source["title"],
        "position": source["origin"], "locations": list(LOCATIONS),
        "speakers": [_speaker(voice, config) for voice in source["speakers"]],
        "active_speakers": _count(config),
        "unmodeled_speakers": config["speakers"] - _count(config),
        "direct_statements": [], "corroborations": [],
        "history": [], "choices": [],
        "influence": config["starting_influence"],
        "reputation": config["starting_reputation"],
        "support_count": 0, "challenge_count": 0,
        "attention_spent": 0, "conversations": 0,
        "checkpoint": False, "retired": False,
        "finished": False, "failed": False, "events": [],
        "statement_limit": config["lines_per_scene"],
    }


def apply_scene(state, config, layout):
    if state["tick"] != 0:
        raise DialogueActionError("active dialogue cannot swap original speaker sources")
    source = normalize_layout(config, layout)
    state["title"] = source["title"]
    state["position"] = source["origin"]
    state["speakers"] = [_speaker(s, config) for s in source["speakers"]]
    return state


def _remember(speaker, config, source, tick):
    if config["memory_turns"] == 0:
        speaker["memories"] = []
        return
    speaker["memories"].append({
        "turn": tick, "kind": source, "speaker": speaker["id"],
    })
    if len(speaker["memories"]) > min(32, config["memory_turns"]):
        speaker["memories"] = speaker["memories"][-min(32, config["memory_turns"]):]


def _decay(state, config):
    if not config["memory_turns"]:
        return
    for speaker in state["speakers"]:
        speaker["memories"] = [entry for entry in speaker["memories"]
                               if state["tick"] - entry["turn"] <
                               config["memory_turns"]]


def step(state, config, action):
    if action not in ACTIONS:
        raise DialogueActionError("unknown or unregistered original dialogue action")
    if state["finished"] or state["failed"]:
        raise DialogueActionError("ended dialogue cannot forge continued conversations")
    if state["tick"] >= config["dialogue_turn_budget"]:
        raise DialogueActionError("source bounded original social session exhausted")
    events = []
    if action.startswith("travel:"):
        index = int(action.split(":")[1])
        if abs(index - state["position"]) != 1:
            raise DialogueActionError("dialogue conversations need adjacent real travel")
        state["position"] = index
        events.append("player_traveled_to_original_social_station")
    elif action.startswith(("speak:", "support:", "challenge:")):
        verb, raw = action.split(":")
        who = int(raw)
        if who >= len(state["speakers"]):
            raise DialogueActionError("source speaker outside detailed local cohort")
        speaker = state["speakers"][who]
        if speaker["location"] != state["position"]:
            raise DialogueActionError("cannot remotely interrogate absent speaker")
        if speaker["patience"] <= 0:
            raise DialogueActionError("person's finite conversational patience is exhausted")
        if verb == "speak":
            if state["conversations"] >= config["lines_per_scene"]:
                raise DialogueActionError("actual authored dialogue line budget exceeded")
            if speaker["heard"] > 0:
                raise DialogueActionError("cannot duplicate first-hand original testimony")
            speaker["heard"] += 1
            speaker["patience"] -= 1
            speaker["last_heard"] = state["tick"]
            state["conversations"] += 1
            statement = {
                "speaker": speaker["id"], "topic": speaker["topic"],
                "position": speaker["position"], "testimony": speaker["testimony"],
                "source": "original_first_hand_speaker_statement",
                "heard_at": state["tick"],
            }
            state["direct_statements"].append(statement)
            _remember(speaker, config, "first_hand_speech", state["tick"])
            events.append("original_direct_testimony_heard_at_real_position")
        elif verb == "support":
            if speaker["heard"] < 1:
                raise DialogueActionError("support must follow real local conversation")
            if state["influence"] < config["support_cost"]:
                raise DialogueActionError("support needs actual finite influence resources")
            state["influence"] -= config["support_cost"]
            speaker["patience"] -= 1
            speaker["supported"] += 1
            speaker["trust"] = min(config["trust_cap"],
                                   speaker["trust"] + config["support_trust_gain"])
            state["support_count"] += 1
            state["reputation"] += config["support_reputation"]
            state["choices"].append({
                "speaker": who, "branch": "support", "tick": state["tick"],
                "cost": config["support_cost"],
            })
            _remember(speaker, config, "paid_source_support", state["tick"])
            events.append("finite_cost_original_support_raised_real_trust")
        else:
            if speaker["heard"] < 1:
                raise DialogueActionError("challenge requires an actual authored statement")
            if state["influence"] < config["challenge_cost"]:
                raise DialogueActionError("can't challenge without finite influence")
            state["influence"] -= config["challenge_cost"]
            speaker["patience"] -= 1
            speaker["challenged"] += 1
            speaker["trust"] = max(0, speaker["trust"] - config["challenge_trust_loss"])
            state["challenge_count"] += 1
            state["reputation"] -= config["challenge_reputation"]
            state["choices"].append({
                "speaker": who, "branch": "challenge", "tick": state["tick"],
                "cost": config["challenge_cost"],
            })
            _remember(speaker, config, "paid_source_challenge", state["tick"])
            events.append("finite_cost_original_challenge_with_social_consequence")
    elif action.startswith("compare:"):
        topic = int(action.split(":")[1])
        if state["position"] != 2:
            raise DialogueActionError("corroboration requires a real archive visit")
        if topic in state["corroborations"]:
            raise DialogueActionError("cannot duplicate an already checked social claim")
        reports = [item for item in state["direct_statements"] if item["topic"] == topic]
        if len({r["speaker"] for r in reports}) < 2:
            raise DialogueActionError("social corroboration needs two distinct direct speakers")
        state["corroborations"].append(topic)
        state["corroborations"].sort()
        events.append("original_two_independent_direct_speaker_sources_compared")
    elif action == "claim":
        trusted = [s for s in state["speakers"]
                   if s["supported"] and s["trust"] >= config["trust_threshold"]]
        if (state["checkpoint"] or not state["corroborations"]
            or state["support_count"] < config["support_goal"] or not trusted):
            raise DialogueActionError("social resolution needs real verified multiple voices")
        state["checkpoint"] = True
        events.append("earned_original_social_consensus_nonterminal")
    elif action == "retire":
        if not state["checkpoint"]:
            raise DialogueActionError("social retirement requires earned consensus")
        state["retired"] = True
        state["finished"] = True
        events.append("voluntary_original_dialogue_epilogue")
    elif action == "rest":
        if state["influence"] >= config["starting_influence"]:
            raise DialogueActionError("social influence cannot be fabricated by resting")
        state["influence"] = min(config["starting_influence"],
                                 state["influence"] + config["rest_influence"])
        events.append("bounded_original_social_recovery")
    elif action in ("inspect", "wait"):
        events.append("original_social_context_observed_without_fake_progress")
    else:
        raise DialogueActionError("dialogue command lacks actual causal behavior")
    state["tick"] += 1
    _decay(state, config)
    state["events"] = events
    return events


__all__ = (
    "LOCATIONS", "TOPICS", "ACTIONS", "DialogueActionError",
    "default_layout", "normalize_layout", "start", "apply_scene", "step",
)
