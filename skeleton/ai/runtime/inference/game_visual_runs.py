"""Visually specific runs for every corpus domain.

Each run paints one domain with one elemental light, one shadow, and one
weather variant, and it records the author so a commercial frame is not
copied. The budget is one billion runs. A pass stops on a reject plateau or
a time cap, and the receipt says whether that budget was actually met.

A lower byte loss is not gameplay quality. This pass does not promote a
serving checkpoint.
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
    domains,
    leaks,
    track_holdouts,
    training_serial,
)
from skeleton.ai.runtime.inference.game_map_variants import RESERVED_NAMES, map_holdouts
from skeleton.ai.runtime.inference.neural import NeuralLMConfig, NumpyRecurrentLM

BILLION_RUNS = 1_000_000_000
SCHEMA = "skeleton.game_visual_runs.v1"
COGNITION_DIGEST = "a39eba98a5a8100a2d8053bd3ba72193d625aabfc3cd4990a54269f8e489c536"
ELEMENTS: tuple[str, ...] = ("ember", "tide", "stone", "gust", "frost")
SHADOWS: tuple[str, ...] = ("cast", "rim", "occluded", "long", "pooled")
WEATHERS: tuple[str, ...] = ("clear", "rain", "snow", "fog", "squall")
STYLE_NAMES: tuple[str, ...] = ("pixar", "ghibli", "disney", "nintendo", "blizzard", "dreamworks")


def _variant(serial: int) -> dict[str, str]:
    names = domains()
    span = len(names)
    return {
        "domain": names[serial % span],
        "element": ELEMENTS[(serial // span) % len(ELEMENTS)],
        "shadow": SHADOWS[(serial // (span * len(ELEMENTS))) % len(SHADOWS)],
        "weather": WEATHERS[(serial // (span * len(ELEMENTS) * len(SHADOWS))) % len(WEATHERS)],
    }


def render_visual_run(serial: int) -> str:
    """One original picture of one corpus domain. The same serial rebuilds it."""
    if isinstance(serial, bool) or not isinstance(serial, int) or serial < 0:
        raise ValueError("serial must be a non-negative int")
    chosen = _variant(serial)
    bound = binding(serial)
    return "\n".join(
        (
            (
                f"Visual run {serial} domain {chosen['domain']} element {chosen['element']} "
                f"shadow {chosen['shadow']} weather {chosen['weather']}."
            ),
            (
                f"The {bound['asset']} at the {bound['place']} keeps one key light and a readable silhouette "
                f"in {chosen['weather']}."
            ),
            (
                f"{chosen['element'].capitalize()} light stays on the {bound['item_color']} {bound['cloth']}, "
                f"and the {chosen['shadow']} shadow separates the subject from the ground."
            ),
            (
                f"Copyright avoidance: the {bound['role']} names the author of this {chosen['domain']} picture "
                "and does not copy a commercial frame. A missing grant keeps the picture out of the build."
            ),
        )
    )


def assess_visual_run(text: str) -> dict[str, Any]:
    lines = text.splitlines()
    title = lines[0] if lines else ""
    lowered = text.lower()
    reserved = any(name in lowered for name in (*RESERVED_NAMES, *STYLE_NAMES))
    valid = False
    parsed: dict[str, str] = {}
    if title.startswith("Visual run ") and " domain " in title and not reserved:
        serial_text = title.split(" domain ", 1)[0].removeprefix("Visual run ").strip()
        if serial_text.isdigit():
            serial = int(serial_text)
            expected = _variant(serial)
            parsed = expected
            valid = (
                f"domain {expected['domain']} element {expected['element']} "
                f"shadow {expected['shadow']} weather {expected['weather']}."
            ) in title and (
                "one key light" in text
                and "readable silhouette" in text
                and "separates the subject from the ground" in text
                and "names the author" in text
                and "does not copy a commercial frame" in text
                and "missing grant keeps the picture out of the build" in text
            )
    return {"valid": bool(valid), "reserved_name": reserved, **parsed}


def visual_holdouts() -> tuple[str, ...]:
    rows = [render_visual_run(HOLDOUT_SERIAL + offset) for offset in (0, 1)]
    if len(rows) != len(set(rows)) or any(not assess_visual_run(row)["valid"] for row in rows):
        raise RuntimeError("visual holdout collided")
    return tuple(rows)


def validate_visual_runs() -> dict[str, int]:
    banned = banned_windows(DENYLIST)
    reserved = set(visual_holdouts())
    seen: set[str] = set()
    checked = 0
    for serial in (0, 1, HOLDOUT_SERIAL, HOLDOUT_SERIAL + 1):
        text = render_visual_run(serial)
        report = assess_visual_run(text)
        if not report["valid"] or leaks(text, banned):
            raise ValueError(f"visual run {serial} is not a valid original picture")
        if serial not in (HOLDOUT_SERIAL, HOLDOUT_SERIAL + 1) and text in reserved:
            raise ValueError(f"visual run {serial} collides with a holdout")
        seen.add(str(report["domain"]))
        checked += 1
    covered = 0
    for serial in range(len(domains())):
        covered_domain = assess_visual_run(render_visual_run(serial))["domain"]
        seen.add(str(covered_domain))
        covered += 1
    if seen != set(domains()):
        raise ValueError("visual runs do not cover the corpus")
    return {"checked": checked, "domains": covered}


def iter_visual_runs(run_budget: int, *, start: int = 0) -> Iterator[tuple[str, str]]:
    if isinstance(run_budget, bool) or not isinstance(run_budget, int) or run_budget < 1:
        raise ValueError("run_budget must be a positive int")
    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        raise ValueError("start must be a non-negative int")
    validate_visual_runs()
    banned = banned_windows(DENYLIST)
    reserved = set(visual_holdouts())
    produced = 0
    counter = 0
    skips = 0
    while produced < run_budget:
        serial = training_serial(counter)
        counter += 1
        text = render_visual_run(serial)
        report = assess_visual_run(text)
        if leaks(text, banned) or text in reserved or not report["valid"]:
            skips += 1
            if skips > 1000:
                raise RuntimeError("visual runs kept colliding with reserved text")
            continue
        skips = 0
        produced += 1
        if produced <= start:
            continue
        yield str(report["domain"]), text


def train_visual_runs(
    *,
    run_budget: int = BILLION_RUNS,
    peak_lr: float = 1e-5,
    hidden: int = 256,
    source: Path | str | None = Path(".skeleton/game-jeeves-cognition/checkpoint.pt"),
    expected_digest: str | None = COGNITION_DIGEST,
    checkpoint_dir: Path | str = Path(".skeleton/game-visual-billion"),
    chunk_runs: int = 64,
    slack: float = 2e-4,
    plateau_rejects: int | None = 32,
    max_seconds: float | None = None,
    persist_every: int = 2048,
    ledger_path: Path | str | None = None,
    log: Any = None,
) -> dict[str, Any]:
    """Train picture runs until the billion, a reject plateau, or a time cap."""
    if isinstance(run_budget, bool) or not isinstance(run_budget, int) or run_budget < 1:
        raise ValueError("run_budget must be a positive int")
    if not isinstance(peak_lr, (int, float)) or isinstance(peak_lr, bool) or not 0.0 < float(peak_lr) <= 1.0:
        raise ValueError("peak_lr must be in (0, 1]")
    if isinstance(chunk_runs, bool) or not isinstance(chunk_runs, int) or chunk_runs < 1:
        raise ValueError("chunk_runs must be a positive int")
    if plateau_rejects is not None and (isinstance(plateau_rejects, bool) or plateau_rejects < 1):
        raise ValueError("plateau_rejects must be a positive int")
    if max_seconds is not None and (
        isinstance(max_seconds, bool) or not isinstance(max_seconds, (int, float)) or max_seconds <= 0
    ):
        raise ValueError("max_seconds must be positive")
    root = Path(checkpoint_dir)
    root.mkdir(parents=True, exist_ok=True)
    ckpt_path = root / "checkpoint.pt"
    torch.manual_seed(11)
    model = ByteRNN(hidden)
    parameters = [item for item in model.parameters() if item.requires_grad]
    source_digest = None
    runs = 0
    runs_kept = 0
    byte_count = 0
    elapsed_before = 0.0
    seen: set[str] = set()
    resumed = False
    loaded: dict[str, Any] = {}
    if ckpt_path.exists():
        loaded = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        if int(loaded.get("hidden", -1)) != hidden:
            raise ValueError("checkpoint hidden size does not match")
        model.load_state_dict(loaded["best_state"])
        _pin(model)
        runs = int(loaded.get("runs_done", 0))
        runs_kept = int(loaded.get("runs_kept", 0))
        byte_count = int(loaded.get("bytes_trained", 0))
        elapsed_before = float(loaded.get("elapsed", 0.0))
        source_digest = loaded.get("source_digest")
        seen = set(loaded.get("domains") or [])
        resumed = True
    elif source is not None:
        if not Path(source).exists():
            raise ValueError("source checkpoint is missing")
        loaded = torch.load(source, map_location="cpu", weights_only=False)
        if int(loaded["hidden"]) != hidden:
            raise ValueError("source checkpoint hidden size does not match")
        model.load_state_dict(loaded["best_state"])
        _pin(model)
        source_digest = network_digest(model)
        if expected_digest is not None and source_digest != expected_digest:
            raise ValueError("source checkpoint does not match the expected digest")
    tracks = track_holdouts()
    tracks["maps"] = map_holdouts()
    tracks["visual_runs"] = visual_holdouts()
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
    batch: list[tuple[str, str]] = []
    reason: str | None = None
    model.train()

    def _elapsed() -> float:
        return elapsed_before + (time.perf_counter() - started)

    def _flush() -> None:
        nonlocal runs, runs_kept, byte_count, best_state, best_scores, opt
        if not batch:
            return
        texts = [text for _domain, text in batch]
        origin = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        opt.param_groups[0]["lr"] = float(peak_lr) * ratchet.scale
        loss = _batch_loss(model, texts)
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
                runs_kept += count
            else:
                model.load_state_dict(origin)
                _pin(model)
                opt = _fresh_optimizer(parameters, float(peak_lr))
        runs += count
        byte_count += sum(len(text.encode("utf-8")) for text in texts)
        batch.clear()

    def _stop() -> str | None:
        found = training_stop(runs, run_budget, ratchet.stall, plateau_rejects)
        if found is not None:
            return found
        if max_seconds is not None and _elapsed() >= float(max_seconds):
            return "time"
        return None

    def _save() -> None:
        payload = {
            "best_state": best_state,
            "hidden": hidden,
            "runs_done": runs,
            "runs_kept": runs_kept,
            "bytes_trained": byte_count,
            "source_digest": source_digest,
            "goal": run_budget,
            "elapsed": _elapsed(),
            "ratchet": ratchet.snapshot(),
            "stall": ratchet.stall,
            "domains": sorted(seen),
        }
        tmp = ckpt_path.with_suffix(".tmp")
        torch.save(payload, tmp)
        os.replace(tmp, ckpt_path)

    if runs < run_budget:
        for domain, text in iter_visual_runs(run_budget, start=runs):
            seen.add(domain)
            batch.append((domain, text))
            if len(batch) >= chunk_runs:
                _flush()
                reason = _stop()
                if reason is not None:
                    break
                if runs > 0 and runs % persist_every == 0:
                    _save()
                    if log is not None:
                        print(
                            f"runs={runs} kept={runs_kept} accepts={ratchet.accepts} rejects={ratchet.rejects} sec={_elapsed():.1f}",
                            file=log,
                            flush=True,
                        )
    if batch and reason is None:
        _flush()
        reason = _stop()
    if reason is None:
        reason = "budget" if runs >= run_budget else "stopped"
    model.load_state_dict(best_state)
    _pin(model)
    official = NumpyRecurrentLM(
        model_id="game-corpus-199",
        config=NeuralLMConfig(hidden_size=hidden, seed=11, dtype="float64"),
        parameters=model.numpy_parameters(),
    )
    official_scores = {name: float(official.loss(texts)) for name, texts in tracks.items()}
    seconds = round(_elapsed(), 3)
    forecast = budget_forecast(max(runs, 1), max(seconds, 1e-6), run_budget)
    _save()
    receipt = {
        "schema": SCHEMA,
        "kind": "byte-language-model",
        "language": "english",
        "run_budget": run_budget,
        "runs_trained": runs,
        "runs_kept": runs_kept,
        "domains_seen": sorted(seen),
        "elements": list(ELEMENTS),
        "shadows": list(SHADOWS),
        "weathers": list(WEATHERS),
        "stop_reason": reason,
        "budget_met": bool(forecast["budget_met"]),
        "words_per_second": forecast["words_per_second"],
        "projected_seconds": forecast["projected_seconds"],
        "max_seconds": None if max_seconds is None else float(max_seconds),
        "goal": run_budget,
        "bytes_trained": byte_count,
        "cycle_start": 0,
        "cycle_bytes": byte_count,
        "words_trained": runs,
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
        "selection": "visual-billion",
        "loss_focus": None,
    }
    (root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    if ledger_path is not None:
        _append_ledger(Path(ledger_path), receipt)
    if log is not None:
        print(
            f"done runs={runs} kept={runs_kept} stop={reason} accepts={ratchet.accepts} rejects={ratchet.rejects}",
            file=log,
            flush=True,
        )
    return receipt
