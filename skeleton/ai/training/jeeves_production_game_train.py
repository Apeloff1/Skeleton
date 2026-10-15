"""Train the *persisted Jeeves cortex* only, never a substitute model.

Operator-only, checkpoint-pinned, candidate-only. This command REQUIRES the
actual live SKELETON_OWN snapshot and an independently obtained expected SHA256.
Missing/unverifiable production weights are a hard error, not a scratch fallback.

A lower LM perplexity does not prove better games. This trainer reports generated
held-out outputs and refuses to certify broad game-design improvement.
"""

from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any

MAX_BYTES = 128 * 1024 * 1024
SCHEMA = "skeleton.jeeves.production_game_candidate.v1"
_WORD = re.compile(r"[a-z][a-z0-9_-]*")
_SHA = re.compile(r"[0-9a-f]{64}")


class ProductionCheckpointError(ValueError):
    """The serving checkpoint was absent or lacked required binding evidence."""


def _strict_json(data: bytes) -> dict[str, Any]:
    def pairs(rows):
        out = {}
        for key, value in rows:
            if key in out:
                raise ProductionCheckpointError("duplicate checkpoint key")
            out[key] = value
        return out

    try:
        blob = json.loads(data.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(
                              ProductionCheckpointError("non-finite checkpoint value")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProductionCheckpointError("invalid production checkpoint JSON") from exc
    if not isinstance(blob, dict):
        raise ProductionCheckpointError("production checkpoint must be a JSON object")
    return blob


def _active_snapshot(blob: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    """Resolve Jeeves's selected speaking weights; never train a silent fallback.

    Mirrors JeevesCortex.speaking_name()/mouth(): RMS uses neo_rms, while
    neo/gelu use transformer. An unsupported specialist or torch-stack mouth
    is a hard stop until its own optimizer and serialization are supported.
    """
    raw = blob.get("mouth_override") or blob.get("winner") or "neo"
    if not isinstance(raw, str):
        raise ProductionCheckpointError("live speaking mouth must be text")
    mouth = raw.strip().lower()
    if mouth in ("neo", "gelu", "transformer"):
        key = "transformer"
    elif mouth in ("rms", "swiglu", "neo_rms"):
        key = "neo_rms"
    else:
        raise ProductionCheckpointError(
            "unsupported active Jeeves speaking mouth: " + mouth[:60]
        )
    snapshot = blob.get(key)
    if not isinstance(snapshot, dict):
        raise ProductionCheckpointError("active production speaking weights missing: " + key)
    kind = snapshot.get("kind")
    if kind == "torch-stack":
        required = ("itos", "state", "dim", "ctx", "steps", "fitted")
    else:
        required = ("itos", "E", "layers", "dim", "ctx", "steps", "fitted")
    if any(field not in snapshot for field in required):
        raise ProductionCheckpointError("active production model is not a weight-bearing snapshot")
    if type(snapshot["steps"]) is not int or type(snapshot["fitted"]) is not int:
        raise ProductionCheckpointError("invalid active production training counters")
    if snapshot["steps"] < 1 and snapshot["fitted"] < 1:
        raise ProductionCheckpointError("active production weights have no training history")
    return key, snapshot, mouth


def _production_source(explicit: Path | None, expected: str) -> tuple[Path, dict[str, Any], str]:
    """Require operator-pinned bytes at the *live* Jeeves persistence path."""
    env = os.environ.get("SKELETON_OWN", "").strip()
    if not env:
        raise ProductionCheckpointError("SKELETON_OWN is not configured; production checkpoint unavailable")
    configured = Path(env).expanduser()
    source = explicit.expanduser() if explicit is not None else configured
    if source.resolve() != configured.resolve():
        raise ProductionCheckpointError("--checkpoint differs from live SKELETON_OWN")
    if not _SHA.fullmatch(expected):
        raise ProductionCheckpointError("an independently verified 64-character --expected-sha256 is required")
    if source.is_symlink() or not source.is_file():
        raise ProductionCheckpointError("live Jeeves checkpoint missing or symbolic link")
    size = source.stat().st_size
    if size < 64 or size > MAX_BYTES:
        raise ProductionCheckpointError("production checkpoint size outside allowed range")
    raw = source.read_bytes()
    digest = sha256(raw).hexdigest()
    if digest != expected:
        raise ProductionCheckpointError("production checkpoint SHA-256 differs from active-runtime evidence")
    blob = _strict_json(raw)
    # A NumPy RNN artifact or ranking adapter MUST NEVER be treated as Jeeves.
    if not isinstance(blob.get("own"), dict) or not isinstance(blob.get("lms"), dict):
        raise ProductionCheckpointError("not a full persisted Jeeves cortex state")
    _active_snapshot(blob)
    if not isinstance(blob.get("bpe"), dict):
        raise ProductionCheckpointError("live Jeeves BPE tokenizer snapshot missing")
    return source, blob, digest


def _texts() -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    from skeleton.ai.runtime.inference.game_pareto_train import plan
    from skeleton.ai.runtime.inference.game_pareto_curriculum import CURRICULUM

    _summary, train, held = plan()
    names = tuple(CURRICULUM)
    expected = tuple(case for name in names for case in CURRICULUM[name]["holdout"])
    if held != expected or set(train).intersection(held):
        raise ProductionCheckpointError("game evaluation data split inconsistent")
    return train, {name: tuple(CURRICULUM[name]["holdout"]) for name in names}


def _token_coverage(model: Any, corpus: tuple[str, ...]) -> float:
    total = unseen = 0
    for text in corpus:
        if hasattr(model, "_ids"):
            ids = model._ids(text)
        else:
            from skeleton.cortex.port import tokens
            ids = [model._id(piece) for piece in tokens(text)]
        total += len(ids)
        unseen += sum(1 for token in ids if token == model.unk)
    return 0.0 if total == 0 else (total - unseen) / total


def _heldout(model: Any, cases: dict[str, tuple[str, ...]]) -> tuple[dict[str, float], dict[str, list[dict[str, Any]]]]:
    """Score held-out sequences and save actual generation for independent review."""
    loss: dict[str, float] = {}
    samples: dict[str, list[dict[str, Any]]] = {}
    for family, rows in cases.items():
        values: list[float] = []
        examples: list[dict[str, Any]] = []
        for index, case in enumerate(rows):
            prompt = case.partition(" Jeeves: ")[0]
            # Log probability is a limited language-model measure, not a design score.
            lp = float(model.logprob(case))
            if not math.isfinite(lp):
                raise ProductionCheckpointError("non-finite held-out loss")
            values.append(-lp)
            generated = model.decode(prompt, n=32, seed=index + 41)
            examples.append({"prompt": prompt, "output": generated, "reference": case})
        loss[family] = sum(values) / len(values)
        samples[family] = examples
    return loss, samples


def _publish_new(path: Path, payload: bytes) -> None:
    if path.is_symlink() or path.exists():
        raise ProductionCheckpointError("refusing existing candidate output")
    if not path.parent.is_dir():
        raise ProductionCheckpointError("candidate parent directory must exist")
    with tempfile.TemporaryDirectory(prefix=".jeeves-game-", dir=path.parent) as folder:
        staged = Path(folder) / "candidate.json"
        with staged.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(staged, 0o600)
        os.link(staged, path)  # never overwrite a concurrent publisher


def train(source: Path | None, *, expected: str, candidate: Path, report: Path,
          epochs: int, lr: float, min_coverage: float, max_domain_regression: float,
          expand_vocabulary: bool = False,
          max_optimizer_steps: int = 25000,
          max_training_seconds: int = 1200) -> dict[str, Any]:
    from skeleton.cortex.transformer import TinyTransformer
    from skeleton.cortex.bpe import BytePairEncoder

    if type(max_optimizer_steps) is not int or not 1 <= max_optimizer_steps <= 1000000:
        raise ValueError("max_optimizer_steps must be an integer in [1, 1000000]")
    if type(max_training_seconds) is not int or not 1 <= max_training_seconds <= 86400:
        raise ValueError("max_training_seconds must be an integer in [1, 86400]")
    if type(expand_vocabulary) is not bool:
        raise ValueError("expand_vocabulary must be boolean")
    if type(epochs) is not int or not 1 <= epochs <= 3:
        raise ValueError("epochs must be 1..3")
    if type(lr) is not float or not math.isfinite(lr) or not 0 < lr <= 0.03:
        raise ValueError("learning rate must be finite and in (0, 0.03]")
    if not 0 <= min_coverage <= 1 or not 0 <= max_domain_regression <= 0.1:
        raise ValueError("invalid evaluation boundaries")
    if candidate.resolve() == report.resolve():
        raise ProductionCheckpointError("candidate and report paths must differ")
    for path in (candidate, report):
        if path.exists() or path.is_symlink() or not path.parent.is_dir():
            raise ProductionCheckpointError("outputs must be new paths in existing directories")

    parent_path, original, parent_sha = _production_source(source, expected)
    if parent_path.resolve() in (candidate.resolve(), report.resolve()):
        raise ProductionCheckpointError("outputs cannot overwrite active production checkpoint")
    dataset, heldout = _texts()
    selected_key, original_snapshot, mouth = _active_snapshot(original)
    torch_stack = original_snapshot.get("kind") == "torch-stack"
    if torch_stack:
        from skeleton.cortex.torch_lm import TorchTransformer
        model = TorchTransformer.from_snapshot(original_snapshot)
        if model.snapshot().get("state") != original_snapshot.get("state"):
            raise ProductionCheckpointError("restored Torch model weights differ from the production checkpoint")
    else:
        model = TinyTransformer.from_snapshot(original_snapshot)
        model.bpe = BytePairEncoder.from_snapshot(original["bpe"])
        if model.snapshot().get("E") != original_snapshot.get("E"):
            raise ProductionCheckpointError("restored native embeddings differ from production checkpoint")
    if model.snapshot()["steps"] != original_snapshot["steps"]:
        raise ProductionCheckpointError("restored transformer training cursor mismatch")
    curriculum_and_eval = dataset + tuple(
        case for rows in heldout.values() for case in rows
    )
    # Capture *actual parent* outputs before even the optional vocabulary
    # growth. The post-growth but pre-SGD loss is a different tokenizer
    # baseline, so never mislabel it as production-model improvement.
    parent_heldout, parent_generations = _heldout(model, heldout)
    vocab_coverage_before = _token_coverage(model, curriculum_and_eval)
    expansion: dict[str, Any] | None = None
    if expand_vocabulary and vocab_coverage_before < min_coverage:
        if torch_stack:
            raise ProductionCheckpointError(
                "torch-stack production vocabulary expansion is not implemented; "
                "never substitute a native transformer"
            )
        from .jeeves_game_vocabulary import expand_native_game_pieces
        expansion = expand_native_game_pieces(
            model, curriculum_and_eval,
            expected_snapshot_digest=sha256(json.dumps(
                original_snapshot, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            ).encode("utf-8")).hexdigest(),
        )
    vocab_coverage = _token_coverage(model, curriculum_and_eval)
    # The tiny default cortex vocabulary typically cannot represent arbitrary
    # game-design language. Fail closed rather than training mostly <UNK> ids.
    if vocab_coverage < min_coverage:
        raise ProductionCheckpointError(
            f"production vocabulary coverage {vocab_coverage:.4f} < {min_coverage:.4f}; "
            "refusing ineffective UNK-token specialization"
        )
    before, sample_before = _heldout(model, heldout)
    steps_before = model.steps
    if torch_stack:
        from skeleton.cortex.port import tokens
        expected_per_epoch = sum(
            max(0, len(tokens(case)) - 1) for case in dataset
        )
    else:
        expected_per_epoch = sum(
            max(0, len(model._ids(case)) - 1) for case in dataset
        )
    expected_steps = expected_per_epoch * epochs
    if not 1 <= expected_steps <= max_optimizer_steps:
        raise ProductionCheckpointError(
            "real game curriculum optimizer updates exceed operator budget: "
            + str(expected_steps) + " > " + str(max_optimizer_steps)
        )
    # Bound work by small batches, checking a monotonic deadline between them.
    # A single in-progress document is not preemptible by this mechanism.
    deadline = time.monotonic() + max_training_seconds
    observed_steps = 0
    for _ in range(epochs):
        for offset in range(0, len(dataset), 8):
            if time.monotonic() >= deadline:
                raise ProductionCheckpointError("training time budget expired")
            batch = dataset[offset:offset + 8]
            if torch_stack:
                observed_steps += model.fit(batch, lr=lr)
            else:
                observed_steps += model.fit(batch, lr=lr, schedule="cosine")
            if time.monotonic() >= deadline:
                raise ProductionCheckpointError("training time budget expired after batch")
    if observed_steps != expected_steps or model.steps - steps_before != expected_steps:
        raise ProductionCheckpointError("actual optimizer steps differ from admitted budget")
    trained_snapshot = model.snapshot()
    if model.steps <= steps_before or trained_snapshot == original_snapshot:
        raise ProductionCheckpointError("production-derived weights did not change")
    after, sample_after = _heldout(model, heldout)
    regressions = [name for name in before
                   if after[name] > before[name] * (1 + max_domain_regression)]
    mean_before = sum(before.values()) / len(before)
    mean_after = sum(after.values()) / len(after)
    lower_loss = mean_after < mean_before
    result: dict[str, Any] = {
        "schema_version": SCHEMA,
        "status": "rejected_evaluation_gate" if regressions or not lower_loss else "candidate_trained_needs_game_design_review",
        "source": "operator_pinned_live_jeeves_cortex",
        "source_checkpoint_sha256": parent_sha,
        "model_kind": "JeevesCortex." + selected_key,
        "architecture": "torch-stack" if torch_stack else "TinyTransformer",
        "speaking_mouth": mouth,
        "production_weights_modified": False,
        "candidate_promoted": False,
        "curriculum_exposures_per_epoch": len(dataset),
        "epochs": epochs,
        "training_steps_before": steps_before,
        "training_steps_after": model.steps,
        "expected_optimizer_updates": expected_steps,
        "observed_optimizer_updates": observed_steps,
        "max_optimizer_steps": max_optimizer_steps,
        "max_training_seconds": max_training_seconds,
        "vocabulary_coverage_before": vocab_coverage_before,
        "vocabulary_coverage": vocab_coverage,
        "vocabulary_expansion": expansion,
        "vocabulary_growth_opted_in": expand_vocabulary,
        "parent_heldout_losses_before_vocabulary_growth": parent_heldout,
        "parent_generated_before_vocabulary_growth": parent_generations,
        "losses_across_changed_vocabulary_not_directly_comparable": bool(expansion and expansion["new_tokens"]),
        "heldout_losses_before": before,
        "heldout_losses_after": after,
        "mean_heldout_loss_before": mean_before,
        "mean_heldout_loss_after": mean_after,
        "regression_families": regressions,
        "generated_before": sample_before,
        "generated_after": sample_after,
        "game_design_improvement_established": False,
        "require_independent_game_design_judgment": True,
    }
    if sha256(parent_path.read_bytes()).hexdigest() != parent_sha:
        raise ProductionCheckpointError("live checkpoint changed during training; refusing stale candidate")
    if result["status"] != "rejected_evaluation_gate":
        output = dict(original)
        output[selected_key] = trained_snapshot
        blob = json.dumps(output, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        _publish_new(candidate, blob)
        result["candidate_sha256"] = sha256(blob).hexdigest()
        result["candidate_path"] = str(candidate.resolve())
    report_payload = json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False).encode()
    _publish_new(report, report_payload)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, help="must match SKELETON_OWN")
    parser.add_argument("--expected-sha256", required=True,
                        help="SHA-256 obtained independently from live serving checkpoint")
    parser.add_argument("--candidate", type=Path, required=True, help="new candidate cortex-state JSON path")
    parser.add_argument("--report", type=Path, required=True, help="new evaluation report JSON path")
    parser.add_argument("--epochs", type=int, default=1)
    parser.add_argument("--max-optimizer-steps", type=int, default=25000)
    parser.add_argument("--max-training-seconds", type=int, default=1200)
    parser.add_argument("--learning-rate", type=float, default=0.005)
    parser.add_argument("--min-coverage", type=float, default=0.80)
    parser.add_argument("--expand-vocabulary", action="store_true",
                        help="explicitly add missing original BPE pieces to a cloned native LM only")
    parser.add_argument("--max-domain-regression", type=float, default=0.0)
    args = parser.parse_args(argv)
    try:
        result = train(args.checkpoint, expected=args.expected_sha256, candidate=args.candidate,
                       report=args.report, epochs=args.epochs, lr=args.learning_rate,
                       min_coverage=args.min_coverage,
                       max_domain_regression=args.max_domain_regression,
                       expand_vocabulary=args.expand_vocabulary,
                       max_optimizer_steps=args.max_optimizer_steps,
                       max_training_seconds=args.max_training_seconds)
        print(json.dumps({k: v for k, v in result.items() if not k.startswith("generated_")},
                         sort_keys=True, allow_nan=False))
        return 0 if result["status"] != "rejected_evaluation_gate" else 3
    except (OSError, ValueError, TypeError, RuntimeError, OverflowError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)[:500]}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
