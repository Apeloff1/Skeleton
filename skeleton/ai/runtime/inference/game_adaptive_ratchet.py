"""Adaptive ratchet for the game-creation byte network.

AdamW uses the standard betas, epsilon, and decoupled weight decay. A chunk
is kept when the mean holdout improves and no track regresses past an
adaptive slack. The step scale hunts a stable acceptance rate under a cosine
ceiling that tightens across the cycle. Accepted text is recorded for review,
and the update stays on fresh lines. Holdout text is never a training
target, and nothing here promotes a checkpoint.
"""
from __future__ import annotations

import copy
import json
import math
import os
import time
from collections import deque
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence, pad_sequence

from skeleton.ai.runtime.inference.game_corpus_stream import (
    BUDGET_BYTES,
    CorpusStream,
    track_holdouts,
)
from skeleton.ai.runtime.inference.neural import BOS, EOS, NeuralLMConfig, NumpyRecurrentLM
from skeleton.jeeves.matrices import SamMatrix

SCHEMA = "skeleton.game_adaptive_ratchet.v2"
ADAMW_LR = 1e-3
ADAMW_BETAS = (0.9, 0.999)
ADAMW_EPS = 1e-8
ADAMW_WEIGHT_DECAY = 0.01
GRAD_CLIP = 1.0
HIDDEN = 128
WARMUP_BYTES = 1024 * 1024


class AdaptiveRatchet:
    """Mean-gain gate, per-track slack, and a step scale that hunts a stable accept rate."""

    def __init__(
        self,
        *,
        margin_cap: float = 5e-4,
        min_scale: float = 0.25,
        slack: float = 1e-4,
        slack_cap: float = 5e-4,
        target_accept: float = 0.4,
    ) -> None:
        if margin_cap <= 0 or min_scale <= 0 or min_scale > 1 or slack <= 0 or slack_cap < slack:
            raise ValueError("ratchet bounds are invalid")
        if not 0.05 <= target_accept <= 0.8:
            raise ValueError("target_accept is out of range")
        self.margin = 1e-5
        self.margin_floor = 1e-6
        self.margin_cap = float(margin_cap)
        self.scale = 1.0
        self.min_scale = float(min_scale)
        self.slack = float(slack)
        self.slack_cap = float(slack_cap)
        self.target_accept = float(target_accept)
        self.ceiling = 1.0
        self.accepts = 0
        self.rejects = 0
        self.reject_streak = 0
        self.stall = 0
        self.steps_since_adapt = 0
        self.recent: deque[int] = deque(maxlen=16)

    def observe(self, before: Mapping[str, float], after: Mapping[str, float]) -> bool:
        if set(before) != set(after) or not before:
            raise ValueError("ratchet tracks must match")
        gains = {name: float(before[name]) - float(after[name]) for name in before}
        mean_gain = sum(gains.values()) / len(gains)
        worst = min(gains.values())
        accepted = mean_gain > self.margin and worst >= -self.slack
        self.recent.append(int(accepted))
        if accepted:
            self.accepts += 1
            self.reject_streak = 0
            self.stall = 0
            # The bar only rises on a kept step. A reject run is what eases it.
            self.margin = min(self.margin_cap, max(self.margin, mean_gain * 0.2))
            self.slack = max(1e-5, self.slack * 0.98)
        else:
            self.rejects += 1
            self.reject_streak += 1
            self.stall += 1
            if self.reject_streak >= 4:
                # Ease the bar. The step size stays with the accept-rate window
                # so a reject run cannot pin it at the floor in one burst.
                self.slack = min(self.slack_cap, self.slack * 1.15)
                self.margin = max(self.margin_floor, self.margin * 0.5)
                self.reject_streak = 0
        self._adapt_scale()
        self.scale = min(self.scale, self.ceiling)
        return accepted

    def _adapt_scale(self) -> None:
        # Once per window, not once per chunk. A per-chunk cut pinned the step
        # at the floor before a real gain could land.
        self.steps_since_adapt += 1
        if len(self.recent) < 16 or self.steps_since_adapt < 16:
            return
        self.steps_since_adapt = 0
        rate = sum(self.recent) / len(self.recent)
        if rate < self.target_accept - 0.15:
            self.scale = max(self.min_scale, self.scale * 0.9)
        elif rate > self.target_accept + 0.2:
            self.scale = min(self.ceiling, self.scale * 1.05)

    def tighten(self, cycle_bytes: int, cycle_budget: int) -> float:
        """Cosine ceiling from 1 at the start of this cycle to the floor at the end."""
        if cycle_budget < 1:
            raise ValueError("cycle_budget must be positive")
        progress = min(1.0, max(0.0, cycle_bytes / cycle_budget))
        self.ceiling = self.min_scale + (1.0 - self.min_scale) * 0.5 * (1.0 + math.cos(math.pi * progress))
        self.scale = min(self.scale, self.ceiling)
        return self.scale

    def snapshot(self) -> dict[str, float | int]:
        rate = (sum(self.recent) / len(self.recent)) if self.recent else 0.0
        return {
            "margin": self.margin,
            "scale": self.scale,
            "ceiling": self.ceiling,
            "slack": self.slack,
            "accepts": self.accepts,
            "rejects": self.rejects,
            "reject_streak": self.reject_streak,
            "accept_rate": rate,
            "recent": [int(item) for item in self.recent],
        }


class ByteRNN(nn.Module):
    """Elman byte RNN whose weights map onto NumpyRecurrentLM."""

    def __init__(self, hidden: int) -> None:
        super().__init__()
        self.hidden = hidden
        self.embed = nn.Embedding(258, hidden)
        self.rnn = nn.RNN(hidden, hidden, nonlinearity="tanh", bias=True, batch_first=True)
        self.out = nn.Linear(hidden, 258)
        with torch.no_grad():
            self.rnn.weight_ih_l0.copy_(torch.eye(hidden))
            self.rnn.bias_hh_l0.zero_()
            self.rnn.weight_hh_l0.mul_(0.02)
        self.rnn.weight_ih_l0.requires_grad_(False)
        self.rnn.bias_hh_l0.requires_grad_(False)

    def numpy_parameters(self) -> dict[str, np.ndarray]:
        with torch.no_grad():
            return {
                "embedding": self.embed.weight.detach().cpu().numpy().astype(np.float64),
                "recurrent": self.rnn.weight_hh_l0.detach().T.contiguous().cpu().numpy().astype(np.float64),
                "hidden_bias": self.rnn.bias_ih_l0.detach().cpu().numpy().astype(np.float64),
                "output": self.out.weight.detach().T.contiguous().cpu().numpy().astype(np.float64),
                "output_bias": self.out.bias.detach().cpu().numpy().astype(np.float64),
            }


def _encode(text: str) -> torch.Tensor:
    return torch.tensor([BOS, *list(text.encode("utf-8")), EOS], dtype=torch.long)


def _batch_loss(
    model: ByteRNN,
    texts: list[str],
    kinds: list[tuple[str, ...]] | None = None,
    keep: frozenset[str] | None = None,
) -> torch.Tensor:
    seqs = [_encode(text) for text in texts]
    lengths = torch.tensor([len(seq) - 1 for seq in seqs])
    inputs = pad_sequence([seq[:-1] for seq in seqs], batch_first=True)
    targets = pad_sequence([seq[1:] for seq in seqs], batch_first=True, padding_value=-100)
    if keep is not None:
        if kinds is None or len(kinds) != len(texts):
            raise ValueError("kept-byte loss needs one kind row per document")
        for row, labels in enumerate(kinds):
            for col, kind in enumerate([*labels, "eos"]):
                if kind not in keep:
                    targets[row, col] = -100
        if int((targets != -100).sum()) == 0:
            raise ValueError("kept-byte loss dropped every target")
    packed = pack_padded_sequence(model.embed(inputs), lengths, batch_first=True, enforce_sorted=False)
    packed_out, _hidden = model.rnn(packed)
    unpacked, _ = pad_packed_sequence(packed_out, batch_first=True)
    logits = model.out(unpacked)
    return F.cross_entropy(logits.reshape(-1, 258), targets.reshape(-1), ignore_index=-100)


@torch.no_grad()
def _scores(model: ByteRNN, tracks: Mapping[str, tuple[str, ...]]) -> dict[str, float]:
    model.eval()
    measured = {name: float(_batch_loss(model, list(texts))) for name, texts in tracks.items()}
    model.train()
    return measured


def _pin(model: ByteRNN) -> None:
    with torch.no_grad():
        model.rnn.weight_ih_l0.copy_(torch.eye(model.hidden))
        model.rnn.bias_hh_l0.zero_()


def expand_byte_rnn(model: ByteRNN, hidden: int) -> ByteRNN:
    """Widen a fitted byte network without changing the function it already computes.

    New hidden units start at zero and stay zero until a later fine-tune uses them.
    """
    if isinstance(hidden, bool) or not isinstance(hidden, int) or hidden < model.hidden:
        raise ValueError("expanded hidden size must be an int >= the current size")
    if hidden == model.hidden:
        return model
    wider = ByteRNN(hidden)
    old = model.hidden
    with torch.no_grad():
        wider.embed.weight.zero_()
        wider.embed.weight[:, :old].copy_(model.embed.weight)
        wider.rnn.weight_hh_l0.zero_()
        wider.rnn.weight_hh_l0[:old, :old].copy_(model.rnn.weight_hh_l0)
        wider.rnn.bias_ih_l0.zero_()
        wider.rnn.bias_ih_l0[:old].copy_(model.rnn.bias_ih_l0)
        wider.out.weight.zero_()
        wider.out.weight[:, :old].copy_(model.out.weight)
        wider.out.bias.copy_(model.out.bias)
    _pin(wider)
    return wider


def network_digest(model: ByteRNN) -> str:
    """Digest of the official reload. The model id stays on the corpus network."""
    official = NumpyRecurrentLM(
        model_id="game-corpus-199",
        config=NeuralLMConfig(hidden_size=model.hidden, seed=11, dtype="float64"),
        parameters=model.numpy_parameters(),
    )
    return official.model_digest


def _save_checkpoint(
    path: Path,
    *,
    model: ByteRNN,
    opt: torch.optim.Optimizer,
    ratchet: AdaptiveRatchet,
    mastery: SamMatrix,
    bytes_done: int,
    best_state: dict[str, torch.Tensor],
    goal: int,
    cycle_start: int,
    replay: deque[tuple[str, str]],
    domain_ema: Mapping[str, float],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": model.state_dict(),
        "optimizer": opt.state_dict(),
        "ratchet": ratchet.snapshot(),
        "mastery": mastery.snapshot(),
        "sam_records": mastery.export_records(),
        "bytes_done": bytes_done,
        "best_state": best_state,
        "hidden": model.hidden,
        "goal": goal,
        "cycle_start": cycle_start,
        "replay": list(replay),
        "domain_ema": dict(domain_ema),
    }
    tmp = path.with_suffix(".tmp")
    torch.save(payload, tmp)
    os.replace(tmp, path)


def _restore_learning(
    mastery: SamMatrix,
    saved: Mapping[str, Any],
    replay: deque[tuple[str, str]],
    domain_ema: dict[str, float],
) -> None:
    """Carry review memory, accepted text, and domain difficulty into the next cycle."""
    records = saved.get("sam_records")
    if isinstance(records, list) and records:
        mastery.load_records(records)
    ema = saved.get("domain_ema")
    if isinstance(ema, dict):
        for name, value in ema.items():
            numeric = float(value)
            if math.isfinite(numeric):
                domain_ema[str(name)] = numeric
    stored = saved.get("replay", [])
    if isinstance(stored, list):
        for item in stored:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                replay.append((str(item[0]), str(item[1])))


def _restore_ratchet(ratchet: AdaptiveRatchet, saved: Mapping[str, Any]) -> None:
    state = saved.get("ratchet", {})
    if not isinstance(state, dict):
        return
    ratchet.margin = float(state.get("margin", ratchet.margin))
    ratchet.slack = float(state.get("slack", ratchet.slack))
    ratchet.accepts = int(state.get("accepts", 0))
    ratchet.rejects = int(state.get("rejects", 0))
    ratchet.scale = float(state.get("scale", 1.0))
    ratchet.ceiling = float(state.get("ceiling", ratchet.ceiling))
    ratchet.reject_streak = int(state.get("reject_streak", 0))
    ratchet.recent.clear()
    recent = state.get("recent", [])
    if isinstance(recent, list):
        ratchet.recent.extend(int(item) for item in recent)
    ratchet.scale = min(max(ratchet.scale, ratchet.min_scale), ratchet.ceiling)


def _warmup(cycle_bytes: int, *, continuation: bool) -> float:
    ramp = min(1.0, max(cycle_bytes, 1) / WARMUP_BYTES)
    # A continuation already has a fitted network, so the step starts at the peak rate.
    if continuation:
        return 1.0
    return ramp


def _append_ledger(path: Path, receipt: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    if path.exists():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, list):
            raise ValueError("cycle ledger must be a list")
        rows = loaded
    row = {
        "schema": receipt["schema"],
        "bytes_trained": receipt["bytes_trained"],
        "cycle_start": receipt["cycle_start"],
        "cycle_bytes": receipt["cycle_bytes"],
        "goal": receipt["goal"],
        "official_tracks": receipt["official_tracks"],
        "torch_best_tracks": receipt["torch_best_tracks"],
        "ratchet": {
            key: receipt["ratchet"][key]
            for key in ("margin", "scale", "slack", "accepts", "rejects", "accept_rate")
            if key in receipt["ratchet"]
        },
        "model_digest": receipt["model_digest"],
        "seconds": receipt["seconds"],
        "loss_focus": receipt.get("loss_focus"),
        "promotion": False,
    }
    if rows and rows[-1].get("model_digest") == row["model_digest"] and rows[-1].get("bytes_trained") == row["bytes_trained"]:
        rows[-1] = row
    else:
        rows.append(row)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _fresh_optimizer(parameters: list[torch.nn.Parameter], peak_lr: float) -> torch.optim.AdamW:
    return torch.optim.AdamW(
        parameters,
        lr=peak_lr,
        betas=ADAMW_BETAS,
        eps=ADAMW_EPS,
        weight_decay=ADAMW_WEIGHT_DECAY,
    )


def train_budget(
    *,
    budget_bytes: int = BUDGET_BYTES,
    additional_bytes: int | None = None,
    peak_lr: float = ADAMW_LR,
    checkpoint_dir: Path | str = Path(".skeleton/game-corpus-199"),
    hidden: int = HIDDEN,
    chunk_docs: int = 192,
    min_scale: float = 0.25,
    slack: float = 1e-4,
    margin_cap: float = 5e-4,
    stream_weights: Mapping[str, float] | None = None,
    continuation: bool | None = None,
    plateau_rejects: int = 64,
    log_bytes: int = 8 * 1024 * 1024,
    score_ceiling: Mapping[str, float] | None = None,
    loss_focus: str | None = None,
    ledger_path: Path | str | None = None,
    log: Any = None,
) -> dict[str, Any]:
    """Train until the byte goal is met.

    `additional_bytes` continues a saved network for another measured cycle.
    A PAUSE file finishes the current chunk, saves, and waits.
    """
    if isinstance(budget_bytes, bool) or not isinstance(budget_bytes, int) or budget_bytes < 1:
        raise ValueError("budget_bytes must be a positive int")
    if additional_bytes is not None and (isinstance(additional_bytes, bool) or additional_bytes < 1):
        raise ValueError("additional_bytes must be a positive int")
    if not isinstance(peak_lr, (int, float)) or isinstance(peak_lr, bool) or not 0.0 < float(peak_lr) <= 1.0:
        raise ValueError("peak_lr must be in (0, 1]")
    if isinstance(min_scale, bool) or not isinstance(min_scale, (int, float)) or not 0.0 < float(min_scale) <= 1.0:
        raise ValueError("min_scale must be in (0, 1]")
    if isinstance(slack, bool) or not isinstance(slack, (int, float)) or not 0.0 < float(slack) <= 1e-2:
        raise ValueError("slack must be in (0, 1e-2]")
    if isinstance(margin_cap, bool) or not isinstance(margin_cap, (int, float)) or not 0.0 < float(margin_cap) <= 1e-2:
        raise ValueError("margin_cap must be in (0, 1e-2]")
    min_scale = float(min_scale)
    slack = float(slack)
    margin_cap = float(margin_cap)
    if isinstance(plateau_rejects, bool) or not isinstance(plateau_rejects, int) or plateau_rejects < 1:
        raise ValueError("plateau_rejects must be a positive int")
    if isinstance(log_bytes, bool) or not isinstance(log_bytes, int) or log_bytes < 1:
        raise ValueError("log_bytes must be a positive int")
    if loss_focus not in (None, "skeleton"):
        raise ValueError("loss_focus must be None or 'skeleton'")
    kept_bytes = frozenset({"skeleton"}) if loss_focus == "skeleton" else None
    root = Path(checkpoint_dir)
    root.mkdir(parents=True, exist_ok=True)
    pause = root / "PAUSE"
    status_path = root / "status.json"
    ckpt_path = root / "checkpoint.pt"
    torch.manual_seed(11)
    tracks = track_holdouts()
    ceiling: dict[str, float] | None = None
    if score_ceiling is not None:
        if not isinstance(score_ceiling, Mapping) or isinstance(score_ceiling, str) or not score_ceiling:
            raise ValueError("score_ceiling must be a non-empty mapping")
        ceiling = {}
        for name, value in score_ceiling.items():
            numeric = float(value)
            if not math.isfinite(numeric) or numeric <= 0:
                raise ValueError("score_ceiling values must be positive and finite")
            ceiling[str(name)] = numeric
        if not set(ceiling) <= set(tracks):
            raise ValueError("score_ceiling names are not holdout tracks")
    model = ByteRNN(hidden)
    parameters = [p for p in model.parameters() if p.requires_grad]
    peak_lr = float(peak_lr)
    opt = _fresh_optimizer(parameters, peak_lr)
    ratchet = AdaptiveRatchet(min_scale=min_scale, slack=slack, slack_cap=max(slack, 5e-4), margin_cap=margin_cap)
    mastery = SamMatrix()
    stream = CorpusStream(weights=stream_weights)
    base_weights = dict(stream.weights)
    replay: deque[tuple[str, str]] = deque(maxlen=256)
    domain_ema: dict[str, float] = {}
    bytes_done = 0
    best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    best_scores = _scores(model, tracks)
    if ckpt_path.exists():
        saved = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        if int(saved["hidden"]) != hidden:
            raise ValueError("checkpoint hidden size does not match")
        model.load_state_dict(saved["best_state"])
        _pin(model)
        bytes_done = int(saved["bytes_done"])
        best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        best_scores = _scores(model, tracks)
        goal = bytes_done + additional_bytes if additional_bytes is not None else budget_bytes
        _restore_learning(mastery, saved, replay, domain_ema)
        same_cycle = int(saved.get("goal", -1)) == goal
        if same_cycle:
            model.load_state_dict(saved["model"])
            _pin(model)
            opt.load_state_dict(saved["optimizer"])
            _restore_ratchet(ratchet, saved)
            cycle_start = int(saved.get("cycle_start", bytes_done))
        else:
            opt = _fresh_optimizer(parameters, peak_lr)
            ratchet = AdaptiveRatchet(min_scale=min_scale, slack=slack, slack_cap=max(slack, 5e-4), margin_cap=margin_cap)
            cycle_start = bytes_done
    else:
        goal = additional_bytes if additional_bytes is not None else budget_bytes
        cycle_start = 0
    started = time.perf_counter()
    model.train()
    if log is not None:
        print(
            f"cycle_start={cycle_start} bytes={bytes_done} goal={goal} hidden={hidden} "
            f"tracks={ {k: round(v, 6) for k, v in best_scores.items()} } "
            f"replay={len(replay)} mastered={len(mastery.snapshot())}",
            file=log,
            flush=True,
        )
    while bytes_done < goal:
        if ceiling is not None and all(best_scores[name] <= ceiling[name] for name in ceiling):
            if log is not None:
                print(
                    f"ceiling bytes={bytes_done} tracks={ {k: round(v, 4) for k, v in best_scores.items()} }",
                    file=log,
                    flush=True,
                )
            break
        if pause.exists():
            _save_checkpoint(
                ckpt_path,
                model=model,
                opt=opt,
                ratchet=ratchet,
                mastery=mastery,
                bytes_done=bytes_done,
                best_state=best_state,
                goal=goal,
                cycle_start=cycle_start,
                replay=replay,
                domain_ema=domain_ema,
            )
            status_path.write_text(
                json.dumps({"state": "paused", "bytes_done": bytes_done, "goal": goal}) + "\n",
                encoding="utf-8",
            )
            if log is not None:
                print(f"paused bytes={bytes_done}", file=log, flush=True)
            while pause.exists():
                time.sleep(0.5)
            if log is not None:
                print("resumed", file=log, flush=True)
        review = set(mastery.review_queue(limit=6))
        if domain_ema:
            level = sorted(domain_ema.values())[len(domain_ema) // 2]
            level = level if level > 0 else 1.0
            for name, ema in domain_ema.items():
                base = base_weights.get(name, 1.0)
                stream.weights[name] = min(4.0, max(0.5, base * (ema / level)))
        for name in review:
            if name in stream.weights:
                stream.weights[name] = min(4.0, max(stream.weights[name], base_weights.get(name, 1.5)))
        batch: list[tuple[str, str, tuple[str, ...]]] = []
        batch_bytes = 0
        while len(batch) < chunk_docs and bytes_done + batch_bytes < goal:
            domain, text, kinds = stream.next_example()
            batch.append((domain, text, kinds))
            batch_bytes += len(text.encode("utf-8"))
        if not batch:
            break
        before = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        opt_state = copy.deepcopy(opt.state_dict())
        cycle_bytes = max(0, bytes_done - cycle_start)
        cycle_budget = max(1, goal - cycle_start)
        warmup = _warmup(cycle_bytes, continuation=cycle_start > 0 if continuation is None else continuation)
        ratchet.tighten(cycle_bytes, cycle_budget)
        opt.param_groups[0]["lr"] = peak_lr * warmup * ratchet.scale
        loss = _batch_loss(
            model,
            [text for _domain, text, _kinds in batch],
            kinds=[kinds for _domain, _text, kinds in batch],
            keep=kept_bytes,
        )
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(parameters, GRAD_CLIP)
        opt.step()
        _pin(model)
        domain_loss = float(loss.detach())
        if not math.isfinite(domain_loss):
            model.load_state_dict(before)
            opt.load_state_dict(opt_state)
            _pin(model)
            ratchet.scale = max(ratchet.min_scale, ratchet.scale * 0.5)
            bytes_done += batch_bytes
            continue
        after_scores = _scores(model, tracks)
        kept = ratchet.observe(best_scores, after_scores)
        for domain, _text, _kinds in batch:
            previous = domain_ema.get(domain, domain_loss)
            domain_ema[domain] = 0.9 * previous + 0.1 * domain_loss
            mastery.record_attempt(domain, success=kept, weight=0.08 if kept else 0.02)
        if kept:
            best_scores = after_scores
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            for domain, text, _kinds in batch:
                replay.append((domain, text))
        else:
            model.load_state_dict(before)
            # A rejected step's moments would replay the same overshoot.
            # The next chunk gets a fresh Adam step at the current rate.
            opt = _fresh_optimizer(parameters, peak_lr)
            _pin(model)
        bytes_done += batch_bytes
        plateau = ratchet.stall >= plateau_rejects and (ratchet.accepts > 0 or cycle_start > 0 or continuation is True)
        boundary = bytes_done // log_bytes != (bytes_done - batch_bytes) // log_bytes or bytes_done >= goal or plateau
        if boundary:
            _save_checkpoint(
                ckpt_path,
                model=model,
                opt=opt,
                ratchet=ratchet,
                mastery=mastery,
                bytes_done=bytes_done,
                best_state=best_state,
                goal=goal,
                cycle_start=cycle_start,
                replay=replay,
                domain_ema=domain_ema,
            )
            if log is not None:
                print(
                    f"bytes={bytes_done} loss={domain_loss:.4f} "
                    f"tracks={ {k: round(v, 4) for k, v in best_scores.items()} } "
                    f"margin={ratchet.margin:.6f} scale={ratchet.scale:.4f} "
                    f"accepts={ratchet.accepts} rejects={ratchet.rejects}",
                    file=log,
                    flush=True,
                )
        if plateau:
            if log is not None:
                print(
                    f"plateau bytes={bytes_done} accepts={ratchet.accepts} rejects={ratchet.rejects}",
                    file=log,
                    flush=True,
                )
            break
    model.load_state_dict(best_state)
    _pin(model)
    official = NumpyRecurrentLM(
        model_id="game-corpus-199",
        config=NeuralLMConfig(hidden_size=hidden, seed=11, dtype="float64"),
        parameters=model.numpy_parameters(),
    )
    official_scores = {name: float(official.loss(texts)) for name, texts in tracks.items()}
    _save_checkpoint(
        ckpt_path,
        model=model,
        opt=opt,
        ratchet=ratchet,
        mastery=mastery,
        bytes_done=bytes_done,
        best_state=best_state,
        goal=goal,
        cycle_start=cycle_start,
        replay=replay,
        domain_ema=domain_ema,
    )
    weights_path = root / "model.json"
    tmp = weights_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(official.to_dict(), separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, weights_path)
    receipt = {
        "schema": SCHEMA,
        "budget_bytes": budget_bytes,
        "additional_bytes": additional_bytes,
        "goal": goal,
        "cycle_start": cycle_start,
        "bytes_trained": bytes_done,
        "cycle_bytes": bytes_done - cycle_start,
        "hidden_size": hidden,
        "adamw": {
            "lr": peak_lr,
            "betas": list(ADAMW_BETAS),
            "eps": ADAMW_EPS,
            "weight_decay": ADAMW_WEIGHT_DECAY,
            "grad_clip": GRAD_CLIP,
        },
        "ratchet": ratchet.snapshot(),
        "torch_best_tracks": best_scores,
        "official_tracks": official_scores,
        "mastery": mastery.snapshot(),
        "domains": len(stream.counts),
        "model_digest": official.model_digest,
        "seconds": round(time.perf_counter() - started, 3),
        "promotion": False,
        "canonical_replaced": False,
        "loss_focus": loss_focus,
        "byte_loss_is_gameplay_quality": False,
        "perfect_builder_claimed": False,
        "service_checkpoint_touched": False,
    }
    (root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    status_path.write_text(json.dumps({"state": "complete", "bytes_done": bytes_done}) + "\n", encoding="utf-8")
    if ledger_path is not None:
        _append_ledger(Path(ledger_path), receipt)
    return receipt


def main() -> None:
    import sys

    print(
        json.dumps(
            train_budget(
                additional_bytes=BUDGET_BYTES,
                peak_lr=3e-4,
                chunk_docs=96,
                min_scale=1.0,
                ledger_path=Path("skeleton/ai/runtime/inference/game_corpus_cycles.json"),
                log=sys.stdout,
            ),
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
