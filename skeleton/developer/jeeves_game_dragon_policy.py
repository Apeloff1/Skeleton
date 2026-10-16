"""A real, small Dragon gameplay-policy learner built from Director journals.

Fits empirical action-frequency parameters with a held-out *session*, not
an invented LLM training receipt. Predictions are advisory, do not execute
actions and abstain on unseen quest contexts. It does not change production
Jeeves transformer weights or imply human preferences.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any

from skeleton.ai.game_builder.quest_scene_engine import (
    DirectorAction, available_director_actions, director_initial, director_step,
)
from skeleton.developer.jeeves_game_director_session import _load, _read_doc, _unique
from skeleton.developer.jeeves_game_dragon_lab import _names

SCHEMA = "skeleton.dragon.director_policy_checkpoint.v1"
HEX = re.compile(r"[0-9a-f]{64}\Z")
MAX_CHECKPOINT = 4 * 1024 * 1024


def _hash(doc: object) -> str:
    return sha256(json.dumps(doc, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _context(state: Any) -> str:
    # The legacy feature identity is byte-for-byte stable. Living worlds add
    # all access-affecting facts; otherwise the model might wrongly transfer a
    # policy learned *after* an unlock into the same scene before the unlock.
    feature = {
        "scene": state.scene,
        "stage_index": list(state.stage_index),
        "completed": list(state.complete),
    }
    if state.world_state is not None:
        feature["dynamic_permissions"] = {
            "acquired_items": list(state.acquired),
            "narrative_flags": list(state.narrative_flags),
            "world_flags": list(state.world_state.world_flags),
            "faction_standings": [list(x) for x in state.world_state.standings],
        }
        if state.world_state.society is not None:
            society = state.world_state.society
            # Do not borrow advice learned with a full wallet, open shop,
            # trusted NPC or new trade item for a pre-unlock state. Exact
            # calendar permission is not available from a saved state alone
            # without the original phase_turns; time is included separately.
            feature["dynamic_permissions"]["society"] = {
                "wallet": society.balance,
                "trust": [list(x) for x in society.relationships],
                "shop_stock": [list(x) for x in society.shop_stock],
                "owned_goods": [list(x) for x in society.owned],
                "last_talk": [list(x) for x in society.last_talk_cycle],
                "game_turn": state.turn,
            }
    return _hash(feature)


def _examples(root: Path, session: str) -> tuple[Any, dict[str, Any], list[tuple[str, str]]]:
    folder, world, end, manifest, head, count = _load(root, name=session)
    state = director_initial(world)
    rows = []
    for index in range(1, count + 1):
        entry = _read_doc(folder / f"{index:08d}.json")
        action = DirectorAction(**entry["action"])
        if entry["before_sha256"] != state.digest:
            raise ValueError("Dragon learner has a stale action context")
        rows.append((_context(state), action.kind + ":" + action.key))
        state = director_step(world, state, action)
        if state.digest != entry["after_sha256"]:
            raise ValueError("Dragon learner action result differs from canonical runtime")
    if state != end:
        raise ValueError("Dragon training sequence differs from independently replayed session")
    evidence = {
        "session": session, "head_sha256": head,
        "action_count": count, "source_sha256": manifest["source_sha256"],
        "final_state_sha256": end.digest,
    }
    return world, evidence, rows


def fit(root: Path, *, sessions: str) -> dict[str, Any]:
    names = _names(sessions)
    if len(names) < 3:
        raise ValueError("Dragon policy fitting needs 2 training sessions and 1 held-out session")
    worlds = []
    evidence = []
    sequences = []
    for name in names:
        world, receipt, rows = _examples(root, name)
        worlds.append(world)
        evidence.append(receipt)
        sequences.append(rows)
    world_hash = worlds[0].digest
    if any(world.digest != world_hash for world in worlds):
        raise ValueError("cannot combine action policy samples from unrelated game worlds")
    if len({r["source_sha256"] for r in evidence}) != 1:
        raise ValueError("Dragon action policy needs one exact original source revision")
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    all_actions = Counter()
    for rows in sequences[:-1]:
        for context, action in rows:
            counts[context][action] += 1
            all_actions[action] += 1
    if not all_actions:
        raise ValueError("training sessions need actual replayed player actions")
    trained = {key: dict(sorted(value.items())) for key, value in sorted(counts.items())}
    holdout = sequences[-1]
    seen, correct, log_loss = 0, 0, 0.0
    import math
    for context, chosen in holdout:
        frequency = counts.get(context)
        if not frequency:
            continue
        seen += 1
        top = sorted(frequency.items(), key=lambda item: (-item[1], item[0]))[0][0]
        correct += int(chosen == top)
        # Explicit unknown-action smoothing; this is not a calibration claim
        # for unobserved legal actions outside the recorded sample.
        denom = sum(frequency.values()) + len(frequency) + 1
        log_loss -= math.log((frequency.get(chosen, 0) + 1) / denom)
    model = {
        "schema": SCHEMA, "project": worlds[0].project_id,
        "world_sha256": world_hash, "source_sha256": evidence[0]["source_sha256"],
        "training_session_receipts": evidence[:-1],
        "held_out_session_receipt": evidence[-1],
        "fit_algorithm": "per-quest-state empirical action counts, Laplace-1 for seen actions",
        "action_count_by_context": trained,
        "train_action_count": sum(sum(v.values()) for v in counts.values()),
        "trained_context_count": len(trained),
        "heldout_action_count": len(holdout),
        "heldout_context_coverage_count": seen,
        "heldout_top1_correct_count": correct,
        "heldout_top1_accuracy": round(correct / seen, 6) if seen else None,
        "heldout_mean_log_loss": round(log_loss / seen, 6) if seen else None,
        "training_data_rights_scope": "operator-local-original-Director-actions",
        "user_preference_inferred": False,
        "foundational_llm_checkpoint_updated": False,
        "original_game_player_input_automated": False,
    }
    if len(json.dumps(model, ensure_ascii=True).encode()) > MAX_CHECKPOINT:
        raise ValueError("policy checkpoint exceeds one training batch; partition sessions")
    return model


def preview(root: Path, *, sessions: str) -> dict[str, Any]:
    model = fit(root, sessions=sessions)
    return {
        "ok": True, "action": "dragon-policy-preview",
        "model_sha256": _hash(model), "model": model,
        "empirical_parameters_fitted": True,
        "checkpoint_persisted": False,
        "jeeves_transformer_weights_modified": False,
    }


def _location(root: Path, digest: str) -> Path:
    if not isinstance(digest, str) or HEX.fullmatch(digest) is None:
        raise ValueError("invalid Dragon policy checkpoint digest")
    base = root / ".jeeves"
    folder = base / "dragon_policy_checkpoints"
    if (root.is_symlink() or base.is_symlink() or folder.is_symlink()
            or (base.exists() and not base.is_dir())
            or (folder.exists() and not folder.is_dir())):
        raise ValueError("unsafe Dragon checkpoint storage")
    return folder / (digest + ".json")


def train(root: Path, *, sessions: str, approved_digest: str | None
          ) -> dict[str, Any]:
    from skeleton.developer.jeeves_game_authoring import _create_only
    model = fit(root, sessions=sessions)
    digest = _hash(model)
    if approved_digest != digest:
        raise ValueError("--approve must match the reviewed empirical policy digest")
    # Fail closed if any source session changed while fitting the policy.
    if fit(root, sessions=sessions) != model:
        raise ValueError("Dragon training evidence changed before publishing weights")
    path = _location(root, digest)
    raw = (json.dumps(model, ensure_ascii=True, sort_keys=True,
                      indent=2, allow_nan=False) + "\n").encode()
    if len(raw) > MAX_CHECKPOINT:
        raise ValueError("Dragon policy checkpoint exceeds supported batch capacity")
    _create_only(path, raw)
    return {
        "ok": True, "action": "dragon-policy-train",
        "checkpoint": str(path), "model_sha256": digest,
        "fitted_action_count": model["train_action_count"],
        "heldout_context_coverage_count": model["heldout_context_coverage_count"],
        "heldout_accuracy": model["heldout_top1_accuracy"],
        "empirical_parameters_persisted": True,
        "foundational_llm_weights_modified": False,
    }


def _load_checkpoint(root: Path, digest: str) -> dict[str, Any]:
    path = _location(root, digest)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_CHECKPOINT:
        raise ValueError("Dragon policy checkpoint missing, unsafe or oversized")
    try:
        data = json.loads(path.read_text("utf-8"), object_pairs_hook=_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              ValueError("non-finite policy weight")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("invalid Dragon policy checkpoint JSON") from exc
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or _hash(data) != digest:
        raise ValueError("Dragon policy checkpoint integrity mismatch")
    return data


def predict(root: Path, *, session: str, digest: str) -> dict[str, Any]:
    model = _load_checkpoint(root, digest)
    sessions = [x["session"] for x in model["training_session_receipts"]]
    sessions.append(model["held_out_session_receipt"]["session"])
    rebuilt = fit(root, sessions=",".join(sessions))
    if rebuilt != model:
        raise ValueError("policy evidence or source world changed since training")
    _, world, state, manifest, _, _ = _load(root, name=session)
    if (world.digest != model["world_sha256"]
            or manifest["source_sha256"] != model["source_sha256"]):
        raise ValueError("Dragon policy cannot advise on a different original game")
    context = _context(state)
    learned = model["action_count_by_context"].get(context, {})
    legal = {action.kind + ":" + action.key for action in available_director_actions(world, state)}
    observed = {key: value for key, value in learned.items() if key in legal}
    if not observed:
        return {
            "ok": True, "action": "dragon-policy-predict", "session": session,
            "model_sha256": digest, "state_sha256": state.digest,
            "trained_context_observed": False, "abstained": True,
            "advisory_choices": [], "gameplay_action_executed": False,
        }
    denominator = sum(observed.values()) + len(legal)
    ranks = [
        {"choice": key, "observations": observed.get(key, 0),
         "estimated_probability": round((observed.get(key, 0) + 1) / denominator, 6)}
        for key in sorted(legal)
    ]
    ranks.sort(key=lambda x: (-x["observations"], x["choice"]))
    return {
        "ok": True, "action": "dragon-policy-predict", "session": session,
        "model_sha256": digest, "state_sha256": state.digest,
        "trained_context_observed": True, "abstained": False,
        "advisory_choices": ranks, "gameplay_action_executed": False,
        "independent_player_preference_verified": False,
    }
