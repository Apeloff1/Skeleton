"""Adaptive ratchet for the game-creation byte network.

AdamW uses the standard betas, epsilon, and decoupled weight decay. The
ratchet keeps a step only when every holdout track improves, then tightens
the required gain and the step scale. It does not loosen. Holdout text is
never a training target, and nothing here promotes a checkpoint.
"""
from __future__ import annotations

import copy
import json
import os
import time
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

SCHEMA = "skeleton.game_adaptive_ratchet.v1"
ADAMW_LR = 1e-3
ADAMW_BETAS = (0.9, 0.999)
ADAMW_EPS = 1e-8
ADAMW_WEIGHT_DECAY = 0.01
GRAD_CLIP = 1.0
HIDDEN = 128
WARMUP_BYTES = 1024 * 1024


class AdaptiveRatchet:
    """Acceptance bar and step scale. Both move only toward a tighter fit."""

    def __init__(self, *, margin_cap: float = 5e-4, min_scale: float = 0.05) -> None:
        if margin_cap <= 0 or min_scale <= 0 or min_scale > 1:
            raise ValueError("ratchet bounds are invalid")
        self.margin = 0.0
        self.margin_cap = float(margin_cap)
        self.scale = 1.0
        self.min_scale = float(min_scale)
        self.accepts = 0
        self.rejects = 0

    def observe(self, before: Mapping[str, float], after: Mapping[str, float]) -> bool:
        if set(before) != set(after) or not before:
            raise ValueError("ratchet tracks must match")
        gains = {name: float(before[name]) - float(after[name]) for name in before}
        accepted = all(gain > self.margin for gain in gains.values())
        if accepted:
            self.accepts += 1
            smallest = min(gains.values())
            self.margin = min(self.margin_cap, max(self.margin, smallest * 0.25))
            self.scale = max(self.min_scale, self.scale * 0.998)
        else:
            self.rejects += 1
            self.scale = max(self.min_scale, self.scale * 0.9)
        return accepted

    def snapshot(self) -> dict[str, float | int]:
        return {
            "margin": self.margin,
            "scale": self.scale,
            "accepts": self.accepts,
            "rejects": self.rejects,
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


def _batch_loss(model: ByteRNN, texts: list[str]) -> torch.Tensor:
    seqs = [_encode(text) for text in texts]
    lengths = torch.tensor([len(seq) - 1 for seq in seqs])
    inputs = pad_sequence([seq[:-1] for seq in seqs], batch_first=True)
    targets = pad_sequence([seq[1:] for seq in seqs], batch_first=True, padding_value=-100)
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


def _save_checkpoint(
    path: Path,
    *,
    model: ByteRNN,
    opt: torch.optim.Optimizer,
    ratchet: AdaptiveRatchet,
    mastery: SamMatrix,
    bytes_done: int,
    best_state: dict[str, torch.Tensor],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": model.state_dict(),
        "optimizer": opt.state_dict(),
        "ratchet": ratchet.snapshot(),
        "mastery": mastery.snapshot(),
        "bytes_done": bytes_done,
        "best_state": best_state,
        "hidden": model.hidden,
    }
    tmp = path.with_suffix(".tmp")
    torch.save(payload, tmp)
    os.replace(tmp, path)


def train_budget(
    *,
    budget_bytes: int = BUDGET_BYTES,
    checkpoint_dir: Path | str = Path(".skeleton/game-corpus-199"),
    hidden: int = HIDDEN,
    chunk_docs: int = 192,
    log: Any = None,
) -> dict[str, Any]:
    """Train until `budget_bytes` of original text have been stepped.

    A PAUSE file in the checkpoint directory finishes the current chunk,
    saves, and waits. Removing the file resumes the same run.
    """
    if isinstance(budget_bytes, bool) or not isinstance(budget_bytes, int) or budget_bytes < 1:
        raise ValueError("budget_bytes must be a positive int")
    root = Path(checkpoint_dir)
    root.mkdir(parents=True, exist_ok=True)
    pause = root / "PAUSE"
    status_path = root / "status.json"
    ckpt_path = root / "checkpoint.pt"
    torch.manual_seed(11)
    tracks = track_holdouts()
    model = ByteRNN(hidden)
    parameters = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(
        parameters,
        lr=ADAMW_LR,
        betas=ADAMW_BETAS,
        eps=ADAMW_EPS,
        weight_decay=ADAMW_WEIGHT_DECAY,
    )
    ratchet = AdaptiveRatchet()
    mastery = SamMatrix()
    stream = CorpusStream()
    bytes_done = 0
    best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
    best_scores = _scores(model, tracks)
    if ckpt_path.exists():
        saved = torch.load(ckpt_path, map_location="cpu", weights_only=False)
        if int(saved["hidden"]) != hidden:
            raise ValueError("checkpoint hidden size does not match")
        model.load_state_dict(saved["model"])
        opt.load_state_dict(saved["optimizer"])
        ratchet.margin = float(saved["ratchet"]["margin"])
        ratchet.scale = float(saved["ratchet"]["scale"])
        ratchet.accepts = int(saved["ratchet"]["accepts"])
        ratchet.rejects = int(saved["ratchet"]["rejects"])
        bytes_done = int(saved["bytes_done"])
        best_state = saved["best_state"]
        model.load_state_dict(best_state)
        best_scores = _scores(model, tracks)
    started = time.perf_counter()
    model.train()
    while bytes_done < budget_bytes:
        if pause.exists():
            _save_checkpoint(
                ckpt_path,
                model=model,
                opt=opt,
                ratchet=ratchet,
                mastery=mastery,
                bytes_done=bytes_done,
                best_state=best_state,
            )
            status_path.write_text(
                json.dumps({"state": "paused", "bytes_done": bytes_done, "budget_bytes": budget_bytes}) + "\n",
                encoding="utf-8",
            )
            if log is not None:
                print(f"paused bytes={bytes_done}", file=log, flush=True)
            while pause.exists():
                time.sleep(0.5)
            if log is not None:
                print("resumed", file=log, flush=True)
        due = set(mastery.review_queue(limit=8))
        for name in due:
            if name in stream.weights:
                stream.weights[name] = max(stream.weights[name], 2.0)
        batch: list[tuple[str, str]] = []
        batch_bytes = 0
        while len(batch) < chunk_docs and bytes_done + batch_bytes < budget_bytes:
            domain, text = stream.next_document()
            batch.append((domain, text))
            batch_bytes += len(text.encode("utf-8"))
        if not batch:
            break
        before = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        opt_state = copy.deepcopy(opt.state_dict())
        warmup = min(1.0, max(bytes_done, 1) / WARMUP_BYTES)
        opt.param_groups[0]["lr"] = ADAMW_LR * warmup * ratchet.scale
        loss = _batch_loss(model, [text for _domain, text in batch])
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(parameters, GRAD_CLIP)
        opt.step()
        _pin(model)
        after_scores = _scores(model, tracks)
        kept = ratchet.observe(best_scores, after_scores)
        domain_loss = float(loss.detach())
        for domain, _text in batch:
            mastery.record_attempt(domain, success=kept and domain_loss < 2.5, weight=0.05)
            if not kept:
                stream.weights[domain] = min(4.0, stream.weights[domain] + 0.01)
        if kept:
            best_scores = after_scores
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        else:
            model.load_state_dict(before)
            opt.load_state_dict(opt_state)
            _pin(model)
        bytes_done += batch_bytes
        if log is not None and (bytes_done // (8 * 1024 * 1024) != (bytes_done - batch_bytes) // (8 * 1024 * 1024) or bytes_done >= budget_bytes):
            print(
                f"bytes={bytes_done} loss={domain_loss:.4f} "
                f"tracks={ {k: round(v, 4) for k, v in best_scores.items()} } "
                f"margin={ratchet.margin:.6f} scale={ratchet.scale:.4f} "
                f"accepts={ratchet.accepts} rejects={ratchet.rejects}",
                file=log,
                flush=True,
            )
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
    )
    weights_path = root / "model.json"
    tmp = weights_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(official.to_dict(), separators=(",", ":")), encoding="utf-8")
    os.replace(tmp, weights_path)
    receipt = {
        "schema": SCHEMA,
        "budget_bytes": budget_bytes,
        "bytes_trained": bytes_done,
        "hidden_size": hidden,
        "adamw": {
            "lr": ADAMW_LR,
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
        "byte_loss_is_gameplay_quality": False,
        "perfect_builder_claimed": False,
        "service_checkpoint_touched": False,
    }
    (root / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    status_path.write_text(json.dumps({"state": "complete", "bytes_done": bytes_done}) + "\n", encoding="utf-8")
    return receipt


def main() -> None:
    import sys

    print(json.dumps(train_budget(log=sys.stdout), indent=2), flush=True)


if __name__ == "__main__":
    main()
