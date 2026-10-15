"""Fail-closed checkpoint-linked quest-graph design selection (candidate only).

Requires an explicit Skeleton recurrent checkpoint and a separately trained
PyTorch ranking adapter. Neither is automatically promoted. Every proposed
game graph is checked for playability before model ranking is considered.
"""

from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
from typing import Any

N = 7
START, KEY, DOOR, GOAL = 0, 1, 2, 3
NAMES = ("Start", "Key cache", "Locked gate", "Goal", "Fork", "Side chamber", "Scenic route")
PARAMETERS = ("embedding", "recurrent", "hidden_bias", "output", "output_bias")


def load_verified_parent(path: Path) -> tuple[dict[str, Any], str]:
    """Verify actual stored model weights before using them as features."""
    import numpy as np

    if path.is_symlink() or not path.is_file() or path.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("parent must be a bounded regular non-symlink file")
    raw = path.read_bytes()
    parent = json.loads(raw)
    if parent.get("schema_version") != "skeleton.numpy_recurrent_lm.v1":
        raise ValueError("only native recurrent Skeleton checkpoints are supported")
    cfg = parent["config"]
    if cfg.get("schema_version") != "skeleton.numpy_recurrent_lm_config.v1":
        raise ValueError("unsupported parent config")
    if cfg.get("dtype") != "float64" or not 4 <= cfg.get("hidden_size", 0) <= 2048:
        raise ValueError("invalid parent numeric architecture")
    parts = [
        json.dumps(cfg, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
        parent["model_id"].encode("utf-8"),
    ]
    for field in PARAMETERS:
        array = np.asarray(parent["parameters"][field], dtype="<f8", order="C")
        if not np.isfinite(array).all():
            raise ValueError("non-finite parent model weights")
        parts.extend([str(array.shape).encode("ascii"), array.tobytes(order="C")])
    digest = hashlib.sha256()
    for part in parts:
        digest.update(len(part).to_bytes(8, "big"))
        digest.update(part)
    if digest.hexdigest() != parent["model_digest"]:
        raise ValueError("parent checkpoint model digest mismatch")
    return parent, hashlib.sha256(raw).hexdigest()


def _features(task: dict[str, Any], edges: set[tuple[int, int]], parent: dict[str, Any]):
    import numpy as np

    weights = parent["parameters"]
    embedding, recurrent, bias = (
        np.asarray(weights[name], dtype=np.float64) for name in PARAMETERS[:3]
    )
    hidden = np.zeros(parent["config"]["hidden_size"], dtype=np.float64)
    prompt = task["biome"] + " " + task["goal"] + " " + task["difficulty"]
    for token in [256] + list(prompt.encode("utf-8")):
        hidden = np.tanh(embedding[token] + hidden @ recurrent + bias)
    adjacency = np.zeros((N, N), dtype=np.float32)
    for source, destination in edges:
        adjacency[source, destination] = 1
    return np.concatenate([
        adjacency.flatten(),
        adjacency.sum(axis=1) / 7,
        adjacency.sum(axis=0) / 7,
        np.asarray([
            task["min_steps"] / 10, task["max_steps"] / 10,
            task["max_edges"] / 14, len(edges) / 20,
        ], dtype=np.float32),
        hidden.astype("float32"),
    ])


def check_quest_graph(task: dict[str, Any], edges: set[tuple[int, int]]) -> dict[str, Any]:
    """Evaluate graph reachability, mandatory gating, safety, agency, pacing."""
    if any(
        type(a) is not int or type(b) is not int or a not in range(N) or b not in range(N)
        for a, b in edges
    ):
        raise ValueError("graph node identities must be integers 0 through 6")
    adjacency = {i: sorted(b for a, b in edges if a == i) for i in range(N)}

    def explore(skip_door: bool):
        start = (START, False)
        distance = {start: 0}
        forward = {}
        queue = deque([start])
        while queue:
            node, has_key = queue.popleft()
            options = []
            for target in adjacency[node]:
                if target == DOOR and (not has_key or skip_door):
                    continue
                successor = (target, has_key or target == KEY)
                options.append(successor)
                if successor not in distance:
                    distance[successor] = distance[(node, has_key)] + 1
                    queue.append(successor)
            forward[(node, has_key)] = options
        return distance, forward

    distance, forward = explore(False)
    has_goal = any(room == GOAL for room, _ in distance)
    without_gate, _ = explore(True)
    gate_required = has_goal and all(room != GOAL for room, _ in without_gate)
    can_recover = {state for state in distance if state[0] == GOAL}
    changed = True
    while changed:
        before = len(can_recover)
        can_recover.update(
            state for state, options in forward.items()
            if any(other in can_recover for other in options)
        )
        changed = len(can_recover) != before

    reachable_rooms = {room for room, _ in distance}
    authored_rooms = {START, GOAL} | {node for edge in edges for node in edge}
    shortest = min((length for (room, _), length in distance.items() if room == GOAL), default=0)
    checks = {
        "reachable": has_goal,
        "gate_required": gate_required,
        "all_states_recoverable": has_goal and all(state in can_recover for state in distance),
        "all_authored_rooms_reachable": authored_rooms.issubset(reachable_rooms),
        "player_choice": any(
            len(set(options)) >= 2 for state, options in forward.items() if state[0] != GOAL
        ),
        "pacing": task["min_steps"] <= shortest <= task["max_steps"],
        "resource_budget": len(edges) <= task["max_edges"],
        "clean_edges": all(a != b and b != START and a != GOAL for a, b in edges),
    }
    return {"accepted": all(checks.values()), "checks": checks, "shortest_win_steps": shortest}


def choose(
    task: dict[str, Any],
    options: list[list[list[int]]],
    *,
    parent_path: Path,
    adapter_path: Path,
) -> dict[str, Any]:
    """First prove design constraints; then use model only to rank valid options."""
    import numpy as np
    import torch
    from torch import nn

    parent, parent_sha = load_verified_parent(parent_path)
    if (
        adapter_path.is_symlink()
        or not adapter_path.is_file()
        or adapter_path.stat().st_size > 50 * 1024 * 1024
    ):
        raise ValueError("ranking adapter must be a bounded non-symlink file")
    adapter = torch.load(adapter_path, map_location="cpu", weights_only=True)
    if adapter.get("schema_version") != "skeleton.game_design_ranker.v1":
        raise ValueError("unsupported game design adapter schema")
    if (
        adapter.get("parent_model_digest") != parent["model_digest"]
        or adapter.get("parent_checkpoint_sha256") != parent_sha
    ):
        raise ValueError("adapter was trained against a different parent checkpoint")
    if not options or len(options) > 100:
        raise ValueError("candidate budget must be between 1 and 100")
    valid = []
    for index, pairs in enumerate(options):
        if not isinstance(pairs, list) or len(pairs) > 49:
            raise ValueError("candidate graph malformed or unbounded")
        if any(not isinstance(edge, list) or len(edge) != 2 for edge in pairs):
            raise ValueError("each graph edge must contain two integer IDs")
        edges = {tuple(edge) for edge in pairs}
        proof = check_quest_graph(task, edges)
        if proof["accepted"]:
            valid.append((index, edges, proof))
    if not valid:
        return {
            "status": "rejected_no_playable_design",
            "production_promotion": False,
            "accepted_options": 0,
        }
    dimension = adapter["network_input_dimension"]
    network = nn.Sequential(
        nn.Linear(dimension, 64), nn.ReLU(),
        nn.Linear(64, 32), nn.ReLU(), nn.Linear(32, 1),
    )
    weights = {
        key.removeprefix("network."): value
        for key, value in adapter["model_state"].items()
    }
    network.load_state_dict(weights, strict=True)
    network.eval()
    inputs = np.stack([_features(task, edges, parent) for _, edges, _ in valid])
    with torch.no_grad():
        scores = network(torch.from_numpy(inputs)).view(-1)
    index, edges, proof = valid[int(torch.argmax(scores).item())]
    return {
        "status": "candidate_graph_verified",
        "production_promotion": False,
        "parent_model_digest": parent["model_digest"],
        "adapter_sha256": hashlib.sha256(adapter_path.read_bytes()).hexdigest(),
        "candidate_index": index,
        "accepted_options": len(valid),
        "task": task,
        "score_is_not_authority": True,
        "proof": proof,
        "proposal": {
            "objective": task["goal"],
            "setting": task["biome"],
            "core_loop": "explore -> choose route -> obtain key -> open gate -> reach goal",
            "rules": {
                "key": "collect at key cache",
                "gate": "entry requires collected key",
            },
            "edges": [
                {"from": NAMES[a], "to": NAMES[b]} for a, b in sorted(edges)
            ],
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.request.is_symlink() or args.request.stat().st_size > 1024 * 1024:
            raise ValueError("request must be bounded and cannot be a symlink")
        request = json.loads(args.request.read_text(encoding="utf-8"))
        result = choose(
            request["task"], request["candidates"],
            parent_path=args.checkpoint, adapter_path=args.adapter,
        )
        print(json.dumps(result, indent=2, allow_nan=False, sort_keys=True))
        return 0 if result["status"] == "candidate_graph_verified" else 3
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)[:400]}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
