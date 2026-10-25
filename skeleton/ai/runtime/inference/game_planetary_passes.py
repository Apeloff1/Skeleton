"""Follow-up planetary training passes for original maps and Jeeves cognition.

Each follow-up map family has a budget of one billion maps. Jeeves cognition
has a budget of 900,000 optimizer steps. A pass stops when the holdout ratchet
plateaus or the clock cap arrives, and the receipt says whether the budget
was actually met. These passes do not promote a serving checkpoint, and a
lower byte loss is not gameplay quality.

Homebrew, tabletop, and dungeon maps are original. Dungeon maps are keyed
room graphs. They are not a commercial tabletop product, and commercial world
names are rejected.
"""
from __future__ import annotations

import json
import math
import os
import time
from collections import deque
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import torch

from skeleton.ai.runtime.inference.game_adaptive_ratchet import (
    ADAMW_BETAS,
    ADAMW_EPS,
    ADAMW_WEIGHT_DECAY,
    GRAD_CLIP,
    AdaptiveRatchet,
    ByteRNN,
    _append_ledger,
    _batch_loss,
    _fresh_optimizer,
    _pin,
    _scores,
    network_digest,
)
from skeleton.ai.runtime.inference.game_coherent_english import binding, budget_forecast, training_stop
from skeleton.ai.runtime.inference.game_corpus_stream import (
    DENYLIST,
    HOLDOUT_SERIAL,
    banned_windows,
    leaks,
    track_holdouts,
    training_serial,
)
from skeleton.ai.runtime.inference.game_map_variants import (
    BILLION_MAPS,
    FOLLOWUP_FAMILIES,
    RESERVED_NAMES,
    map_holdouts,
    train_map_budget,
)
from skeleton.ai.runtime.inference.neural import NeuralLMConfig, NumpyRecurrentLM

COGNITION_STEPS = 900_000
SCHEMA = "skeleton.game_planetary_passes.v1"
MAP_BILLION_DIGEST = "3d6963d51e3f14085b4c916a84ec8c9c46f5d11158c675017fc5eefcd4eb8e2c"

# Recorded passes stay in the list so a follow-up does not pretend to be the
# first billion. Only kind=followup is executed.
PLANETARY_TRAINING_PASS_SPECS: tuple[dict[str, Any], ...] = (
    {
        "pass_id": "map-billion",
        "kind": "recorded",
        "budget": BILLION_MAPS,
        "unit": "maps",
        "run": False,
    },
    {
        "pass_id": "tabletop-followup",
        "kind": "followup",
        "budget_per_family": BILLION_MAPS,
        "families": FOLLOWUP_FAMILIES,
        "unit": "maps",
        "run": True,
    },
    {
        "pass_id": "jeeves-cognition",
        "kind": "followup",
        "budget": COGNITION_STEPS,
        "unit": "steps",
        "run": True,
    },
)


def render_cognition(serial: int, *, contradict: bool = False) -> str:
    """One original Jeeves cognition trace. A contradiction is evaluation only."""
    if isinstance(serial, bool) or not isinstance(serial, int) or serial < 0:
        raise ValueError("serial must be a non-negative int")
    bound = binding(serial)
    claim = "is certain" if contradict else "stays uncertain"
    observation = "becomes a fact" if contradict else "does not become a fact"
    return "\n".join(
        (
            f"Jeeves cognition pass {serial}.",
            (
                f"Mode plan. The goal is the {bound['place']} and the next step reads the written rule "
                f"before the {bound['verb']}."
            ),
            f"Evidence the {bound['asset']} is on record. A claim without that evidence {claim}.",
            (
                f"Memory keeps the {bound['item']} separate from the {bound['grant']}. "
                f"A missing observation {observation}."
            ),
            "A tool result is an observation. It is not a new goal.",
        )
    )


def assess_cognition(text: str) -> dict[str, Any]:
    lowered = text.lower()
    reserved = any(name in lowered for name in RESERVED_NAMES)
    valid = (
        text.startswith("Jeeves cognition pass ")
        and "Mode plan." in text
        and "stays uncertain" in text
        and "does not become a fact" in text
        and "It is not a new goal." in text
        and not reserved
    )
    return {"valid": valid, "reserved_name": reserved}


def cognition_holdouts() -> tuple[str, ...]:
    rows = [render_cognition(HOLDOUT_SERIAL + offset) for offset in (0, 1)]
    if len(rows) != len(set(rows)) or any(not assess_cognition(row)["valid"] for row in rows):
        raise RuntimeError("cognition holdout collided")
    return tuple(rows)


def validate_cognition() -> dict[str, int]:
    banned = banned_windows(DENYLIST)
    reserved = set(cognition_holdouts())
    checked = 0
    for serial in (0, 1, HOLDOUT_SERIAL, HOLDOUT_SERIAL + 1):
        text = render_cognition(serial)
        bad = render_cognition(serial, contradict=True)
        if not assess_cognition(text)["valid"] or assess_cognition(bad)["valid"]:
            raise ValueError(f"cognition serial {serial} failed its contract")
        if leaks(text, banned) or text in reserved and serial not in (HOLDOUT_SERIAL, HOLDOUT_SERIAL + 1):
            raise ValueError(f"cognition serial {serial} collides with reserved text")
        checked += 1
    return {"checked": checked}


def iter_cognition(limit: int, *, start: int = 0) -> Iterator[str]:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive int")
    validate_cognition()
    banned = banned_windows(DENYLIST)
    reserved = set(cognition_holdouts())
    produced = 0
    counter = 0
    skips = 0
    while produced < limit:
        serial = training_serial(counter)
        counter += 1
        text = render_cognition(serial)
        if leaks(text, banned) or text in reserved or not assess_cognition(text)["valid"]:
            skips += 1
            if skips > 1000:
                raise RuntimeError("cognition training kept colliding with reserved text")
            continue
        skips = 0
        produced += 1
        if produced <= start:
            continue
        yield text


def _gap(hidden: int, parameters: dict[str, Any], true_rows: tuple[str, ...], false_rows: tuple[str, ...]) -> float:
    official = NumpyRecurrentLM(
        model_id="game-corpus-199",
        config=NeuralLMConfig(hidden_size=hidden, seed=11, dtype="float64"),
        parameters=parameters,
    )
    return float(official.loss(list(false_rows))) - float(official.loss(list(true_rows)))


def train_jeeves_cognition(
    *,
    step_budget: int = COGNITION_STEPS,
    peak_lr: float = 1e-5,
    hidden: int = 256,
    source: Path | str | None = None,
    expected_digest: str | None = None,
    checkpoint_dir: Path | str = Path(".skeleton/game-jeeves-cognition"),
    chunk_traces: int = 8,
    slack: float = 2e-4,
    plateau_rejects: int | None = None,
    max_seconds: float | None = None,
    persist_every: int = 64,
    ledger_path: Path | str | None = None,
    log: Any = None,
) -> dict[str, Any]:
    """Train Jeeves cognition traces until the step budget, a plateau, or a time cap."""
    if isinstance(step_budget, bool) or not isinstance(step_budget, int) or step_budget < 1:
        raise ValueError("step_budget must be a positive int")
    if isinstance(chunk_traces, bool) or not isinstance(chunk_traces, int) or chunk_traces < 1:
        raise ValueError("chunk_traces must be a positive int")
    if plateau_rejects is not None and (isinstance(plateau_rejects, bool) or plateau_rejects < 1):
        raise ValueError("plateau_rejects must be a positive int")
    if max_seconds is not None and (isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)) or max_seconds <= 0):
        raise ValueError("max_seconds must be positive")
    root = Path(checkpoint_dir)
    root.mkdir(parents=True, exist_ok=True)
    ckpt_path = root / "checkpoint.pt"
    torch.manual_seed(11)
    model = ByteRNN(hidden)
    parameters = [item for item in model.parameters() if item.requires_grad]
    source_digest = None
    steps = 0
    steps_kept = 0
    traces = 0
    byte_count = 0
    elapsed_before = 0.0
    resumed = False
    if ckpt_path.exists():
        loaded = torch.load(ckpt_path, map_location="cpu", weights_only=True)
        if int(loaded.get("hidden", -1)) != hidden:
            raise ValueError("checkpoint hidden size does not match")
        model.load_state_dict(loaded["best_state"])
        _pin(model)
        steps = int(loaded.get("steps_done", 0))
        steps_kept = int(loaded.get("steps_kept", 0))
        traces = int(loaded.get("traces_done", 0))
        byte_count = int(loaded.get("bytes_trained", 0))
        elapsed_before = float(loaded.get("elapsed", 0.0))
        source_digest = loaded.get("source_digest")
        resumed = True
    elif source is not None:
        loaded = torch.load(source, map_location="cpu", weights_only=True)
        if int(loaded["hidden"]) != hidden:
            raise ValueError("source checkpoint hidden size does not match")
        model.load_state_dict(loaded["best_state"])
        _pin(model)
        source_digest = network_digest(model)
        if expected_digest is not None and source_digest != expected_digest:
            raise ValueError("source checkpoint does not match the expected digest")
    tracks = track_holdouts()
    tracks["maps"] = map_holdouts()
    true_rows = cognition_holdouts()
    false_rows = tuple(render_cognition(HOLDOUT_SERIAL + offset, contradict=True) for offset in (0, 1))
    tracks["cognition"] = true_rows
    gap_before = _gap(hidden, model.numpy_parameters(), true_rows, false_rows)
    best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    best_scores = _scores(model, tracks)
    ratchet = AdaptiveRatchet(min_scale=1.0, slack=slack, slack_cap=slack, margin_cap=1e-5)
    if resumed:
        snap = loaded.get("ratchet") or {}
        for key in ("margin", "scale", "ceiling", "slack", "accepts", "rejects", "reject_streak"):
            if key in snap:
                setattr(ratchet, key, snap[key])
        if snap.get("recent"):
            ratchet.recent = deque((int(item) for item in snap["recent"]), maxlen=16)
        ratchet.stall = int(loaded.get("stall", 0))
    opt = _fresh_optimizer(parameters, float(peak_lr))
    started = time.perf_counter()
    batch: list[str] = []
    reason: str | None = None
    model.train()

    def _elapsed() -> float:
        return elapsed_before + (time.perf_counter() - started)

    def _flush() -> None:
        nonlocal steps, steps_kept, traces, byte_count, best_state, best_scores, opt
        if not batch:
            return
        origin = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        opt.param_groups[0]["lr"] = float(peak_lr) * ratchet.scale
        loss = _batch_loss(model, list(batch))
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(parameters, GRAD_CLIP)
        opt.step()
        _pin(model)
        value = float(loss.detach())
        count = len(batch)
        if not math.isfinite(value):
            model.load_state_dict(origin)
            _pin(model)
            opt = _fresh_optimizer(parameters, float(peak_lr))
            ratchet.rejects += 1
            ratchet.stall += 1
        else:
            after = _scores(model, tracks)
            if ratchet.observe(best_scores, after):
                best_scores = after
                best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
                steps_kept += 1
            else:
                model.load_state_dict(origin)
                _pin(model)
                opt = _fresh_optimizer(parameters, float(peak_lr))
        steps += 1
        traces += count
        byte_count += sum(len(text.encode("utf-8")) for text in batch)
        batch.clear()

    def _stop() -> str | None:
        found = training_stop(steps, step_budget, ratchet.stall, plateau_rejects)
        if found is not None:
            return found
        if max_seconds is not None and _elapsed() >= float(max_seconds):
            return "time"
        return None

    def _save(elapsed: float) -> None:
        payload = {
            "best_state": best_state,
            "hidden": hidden,
            "steps_done": steps,
            "steps_kept": steps_kept,
            "traces_done": traces,
            "bytes_trained": byte_count,
            "source_digest": source_digest,
            "goal": step_budget,
            "elapsed": elapsed,
            "ratchet": ratchet.snapshot(),
            "stall": ratchet.stall,
        }
        tmp = ckpt_path.with_suffix(".tmp")
        torch.save(payload, tmp)
        os.replace(tmp, ckpt_path)

    if steps < step_budget:
        for text in iter_cognition(step_budget * chunk_traces, start=traces):
            batch.append(text)
            if len(batch) >= chunk_traces:
                _flush()
                reason = _stop()
                if reason is not None:
                    break
                if steps > 0 and steps % persist_every == 0:
                    _save(_elapsed())
                    if log is not None:
                        print(
                            f"cognition steps={steps} kept={steps_kept} accepts={ratchet.accepts} rejects={ratchet.rejects} sec={_elapsed():.1f}",
                            file=log,
                            flush=True,
                        )
    if batch and reason is None:
        _flush()
        reason = _stop()
    if reason is None:
        reason = "budget" if steps >= step_budget else "stopped"
    model.load_state_dict(best_state)
    _pin(model)
    official = NumpyRecurrentLM(
        model_id="game-corpus-199",
        config=NeuralLMConfig(hidden_size=hidden, seed=11, dtype="float64"),
        parameters=model.numpy_parameters(),
    )
    official_scores = {name: float(official.loss(texts)) for name, texts in tracks.items()}
    gap_after = float(official.loss(list(false_rows))) - float(official.loss(list(true_rows)))
    seconds = round(_elapsed(), 3)
    forecast = budget_forecast(max(steps, 1), max(seconds, 1e-6), step_budget)
    _save(seconds)
    receipt = {
        "schema": SCHEMA,
        "kind": "byte-language-model",
        "language": "english",
        "steps_budget": step_budget,
        "steps_trained": steps,
        "steps_kept": steps_kept,
        "traces_trained": traces,
        "stop_reason": reason,
        "budget_met": bool(forecast["budget_met"]),
        "words_per_second": forecast["words_per_second"],
        "projected_seconds": forecast["projected_seconds"],
        "max_seconds": None if max_seconds is None else float(max_seconds),
        "goal": step_budget,
        "bytes_trained": byte_count,
        "cycle_start": 0,
        "cycle_bytes": byte_count,
        "words_trained": steps,
        "cognition_gap_before": gap_before,
        "cognition_gap_after": gap_after,
        "hidden_size": hidden,
        "peak_lr": float(peak_lr),
        "adamw": {
            "lr": float(peak_lr),
            "betas": list(ADAMW_BETAS),
            "eps": ADAMW_EPS,
            "weight_decay": ADAMW_WEIGHT_DECAY,
            "grad_clip": GRAD_CLIP,
        },
        "torch_best_tracks": best_scores,
        "official_tracks": official_scores,
        "ratchet": ratchet.snapshot(),
        "source_digest": source_digest,
        "model_digest": official.model_digest,
        "seconds": seconds,
        "promotion": False,
        "service_checkpoint_touched": False,
        "byte_loss_is_gameplay_quality": False,
        "selection": "jeeves-cognition",
        "loss_focus": None,
    }
    (root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    if ledger_path is not None:
        _append_ledger(Path(ledger_path), receipt)
    if log is not None:
        print(
            f"done cognition steps={steps} kept={steps_kept} stop={reason} gap={gap_before:.6f}->{gap_after:.6f}",
            file=log,
            flush=True,
        )
    return receipt


def run_planetary_training_passes(
    *,
    family_budget: int = BILLION_MAPS,
    cognition_steps: int = COGNITION_STEPS,
    peak_lr: float = 1e-5,
    hidden: int = 256,
    source: Path | str | None = Path(".skeleton/game-maps-billion/checkpoint.pt"),
    expected_digest: str | None = MAP_BILLION_DIGEST,
    map_dir: Path | str = Path(".skeleton/game-tabletop-billion"),
    cognition_dir: Path | str = Path(".skeleton/game-jeeves-cognition"),
    chunk_maps: int = 64,
    chunk_traces: int = 8,
    plateau_rejects: int | None = 32,
    max_seconds: float | None = None,
    ledger_path: Path | str | None = None,
    log: Any = None,
) -> dict[str, Any]:
    """Run the follow-up specs. Recorded passes are listed and not repeated."""
    followups = [spec for spec in PLANETARY_TRAINING_PASS_SPECS if spec.get("run")]
    if [spec["pass_id"] for spec in followups] != ["tabletop-followup", "jeeves-cognition"]:
        raise RuntimeError("planetary follow-up order drifted")
    map_budget = family_budget * len(FOLLOWUP_FAMILIES)
    maps = train_map_budget(
        map_budget=map_budget,
        peak_lr=peak_lr,
        hidden=hidden,
        source=source,
        expected_digest=expected_digest,
        checkpoint_dir=map_dir,
        chunk_maps=chunk_maps,
        plateau_rejects=plateau_rejects,
        max_seconds=max_seconds,
        families=FOLLOWUP_FAMILIES,
        family_budget=family_budget,
        selection="tabletop-billion",
        ledger_path=ledger_path,
        log=log,
    )
    cognition = train_jeeves_cognition(
        step_budget=cognition_steps,
        peak_lr=peak_lr,
        hidden=hidden,
        source=Path(map_dir) / "checkpoint.pt",
        expected_digest=maps["model_digest"],
        checkpoint_dir=cognition_dir,
        chunk_traces=chunk_traces,
        plateau_rejects=plateau_rejects,
        max_seconds=max_seconds,
        ledger_path=ledger_path,
        log=log,
    )
    return {
        "schema": SCHEMA,
        "followups": [spec["pass_id"] for spec in followups],
        "family_budget": family_budget,
        "cognition_steps": cognition_steps,
        "maps": maps,
        "cognition": cognition,
        "promotion": False,
        "service_checkpoint_touched": False,
    }
