"""Deterministic local multiplayer protocol simulator, not a socket server.

Models authoritative input sequencing, bounded transport delay, prediction,
acknowledgement and rollback against an actual integer-coordinate world. No
real peer credentials, internet transport, or commercial netcode certification.
"""
from __future__ import annotations

from copy import deepcopy

ACTIONS = ("inspect", "tick", "tick:4", "tick:16", "sync",
           "predict", "disconnect:1", "disconnect:2",
           "join:1", "join:2", "send:1:left", "send:1:right",
           "send:2:left", "send:2:right", "retire")


class NetworkingActionError(ValueError):
    """Undeclared packet, foreign peer, rollback violation or forged network map."""


def _int(value, lo, hi, field):
    if type(value) is not int or not lo <= value <= hi:
        raise NetworkingActionError("invalid network " + field)
    return value


def default_layout(config, seed):
    _int(seed, 0, 2**31 - 1, "seed")
    return {
        "title": "Original Local Netplay " + str(seed % 10000),
        "spawn": [seed % 11, (seed // 11) % 11],
        "input_delay_frames": min(3, max(0, config["max_latency_ms"] * config["tick_rate"] // 2000)),
        "world_limit": 100,
    }


def normalize_layout(config, layout):
    if type(layout) is not dict or set(layout) != {
        "title", "spawn", "input_delay_frames", "world_limit"
    }:
        raise NetworkingActionError("exact network simulation source required")
    if (type(layout["title"]) is not str or
            not 1 <= len(layout["title"]) <= 100 or
            any(ord(ch) < 32 for ch in layout["title"])):
        raise NetworkingActionError("invalid original local world title")
    spawn = layout["spawn"]
    if type(spawn) is not list or len(spawn) != 2:
        raise NetworkingActionError("world spawn requires two coordinates")
    world_limit = _int(layout["world_limit"], 4, 1000, "world_limit")
    clean_spawn = [_int(coord, 0, world_limit, "spawn") for coord in spawn]
    delay = _int(layout["input_delay_frames"], 0, 30, "delay")
    if delay > config["max_latency_ms"] * config["tick_rate"] // 1000:
        raise NetworkingActionError("network delay exceeds admitted latency")
    return {
        "title": layout["title"], "spawn": clean_spawn,
        "input_delay_frames": delay, "world_limit": world_limit,
    }


def start(config, seed):
    source = normalize_layout(config, default_layout(config, seed))
    return {
        "title": source["title"], "spawn": list(source["spawn"]),
        "input_delay_frames": source["input_delay_frames"],
        "world_limit": source["world_limit"],
        "clock": 0, "tick": 0,
        "players": {"0": {"connected": True, "x": source["spawn"][0],
                          "confirmed_x": source["spawn"][0], "last_seq": 0}},
        "pending": [], "acks": [], "history": [], "delivered": 0, "dropped": 0,
        "rollbacks": 0, "prediction_mismatches": 0,
        "score": 0, "turn": 0, "finished": False, "failed": False,
        "events": [], "real_network": False, "authority": config["authority"],
    }


def apply_scene(state, config, layout):
    if state["turn"]:
        raise NetworkingActionError("network world source cannot change during execution")
    source = normalize_layout(config, layout)
    state["title"] = source["title"]
    state["spawn"] = list(source["spawn"])
    state["input_delay_frames"] = source["input_delay_frames"]
    state["world_limit"] = source["world_limit"]
    state["players"]["0"]["x"] = source["spawn"][0]
    state["players"]["0"]["confirmed_x"] = source["spawn"][0]


def _deliver(state, config, events):
    deliverable = [packet for packet in state["pending"]
                   if packet["deliver_at"] <= state["tick"]]
    state["pending"] = [packet for packet in state["pending"]
                        if packet["deliver_at"] > state["tick"]]
    for packet in deliverable:
        key = str(packet["peer"])
        player = state["players"].get(key)
        if player is None or not player["connected"]:
            state["dropped"] += 1
            events.append("packet_dropped_for_disconnected_peer")
            continue
        confirmed = max(0, min(state["world_limit"],
                               player["confirmed_x"] + packet["delta"]))
        if config["authority"] == "server":
            if player["x"] != confirmed:
                state["prediction_mismatches"] += 1
                if state["tick"] - packet["issued"] <= config["rollback_frames"]:
                    state["rollbacks"] += 1
                    events.append("bounded_authoritative_rollback")
                player["x"] = confirmed
            else:
                events.append("authoritative_prediction_confirmed")
        else:
            player["x"] = confirmed
        player["confirmed_x"] = confirmed
        state["acks"].append([packet["peer"], packet["seq"], state["tick"]])
        state["delivered"] += 1
        state["score"] += 1
        events.append("actual_local_protocol_packet_applied")
    state["acks"] = state["acks"][-32:]


def step(state, config, action):
    if action not in ACTIONS or state["finished"] or state["failed"]:
        raise NetworkingActionError("unavailable netcode command")
    events = []
    if action.startswith("join:"):
        peer = action[-1]
        if int(peer) >= config["max_players"]:
            raise NetworkingActionError("peer exceeds authored player capacity")
        if peer in state["players"] and state["players"][peer]["connected"]:
            raise NetworkingActionError("duplicate live peer join")
        if len([p for p in state["players"].values() if p["connected"]]) >= config["max_players"]:
            raise NetworkingActionError("simulated lobby is full")
        state["players"][peer] = {
            "connected": True, "x": state["spawn"][0],
            "confirmed_x": state["spawn"][0], "last_seq": 0,
        }
        events.append("authenticated_local_peer_slot_reserved")
    elif action.startswith("disconnect:"):
        peer = action[-1]
        if peer not in state["players"] or not state["players"][peer]["connected"]:
            raise NetworkingActionError("peer not active")
        state["players"][peer]["connected"] = False
        events.append("peer_session_disconnected")
    elif action.startswith("send:"):
        _, peer, direction = action.split(":")
        player = state["players"].get(peer)
        if player is None or not player["connected"]:
            raise NetworkingActionError("cannot send as absent local test peer")
        if len(state["pending"]) >= 32:
            raise NetworkingActionError("finite network input queue full")
        delta = -1 if direction == "left" else 1
        player["last_seq"] += 1
        packet = {
            "peer": int(peer), "delta": delta, "issued": state["tick"],
            "deliver_at": state["tick"] + state["input_delay_frames"] + 1,
            "seq": player["last_seq"],
        }
        state["pending"].append(packet)
        if config["authority"] == "server":
            player["x"] = max(0, min(state["world_limit"], player["x"] + delta))
        events.append("bounded_source_bound_input_queued")
    elif action == "predict":
        if config["authority"] != "server":
            raise NetworkingActionError("client-side prediction requires server authority")
        state["score"] += len(state["pending"]) // 4
        events.append("predicted_state_inspected_without_server_commit")
    elif action in ("tick", "tick:4", "tick:16"):
        count = 1 if action == "tick" else int(action.partition(":")[2])
        for _ in range(count):
            state["tick"] += 1
            _deliver(state, config, events)
        events.append("fixed_tick_transport_simulated")
    elif action == "sync":
        _deliver(state, config, events)
        events.append("peer_acknowledgements_collected")
    elif action == "retire":
        if not state["delivered"] or state["pending"]:
            raise NetworkingActionError("network session cannot retire with unconfirmed work")
        state["finished"] = True
        events.append("source_bound_local_network_trial_completed")
    elif action == "inspect":
        events.append("network_protocol_evidence_inspected")
    state["turn"] += 1
    state["events"] = events[-48:]
    return state["events"]


__all__ = ["ACTIONS", "NetworkingActionError", "default_layout",
           "normalize_layout", "start", "apply_scene", "step"]
