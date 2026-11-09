"""True bounded DPO gradients and durable candidate-only native post-training."""

from __future__ import annotations

import hashlib
import math
import platform
import sqlite3
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from skeleton.ai.runtime.inference.neural import (
    BOS,
    EOS,
    NeuralLMError,
    NumpyRecurrentLM,
)

from .control import (
    TrainingCheckpoint,
    TrainingRepository,
    TrainingRunManifest,
    TrainingStateError,
    TrainingTelemetry,
    _canonical,
    _digest,
)
from .data import DatasetRegistry
from .neural_trainer import NeuralLocalTrainer
from .post_training import PostTrainingExperiment
from .trainer import LocalTrainingArtifact, corpus_digest

ALGORITHM = "numpy-recurrent-byte-dpo-v1"
BINDING_SCHEMA = "skeleton.preference_training_binding.v1"
PAYLOAD_SCHEMA = "skeleton.preference_training_resume.v1"
PAIR_SCHEMA = "skeleton.preference_pair.v1"
_PARAMETERS = ("embedding", "recurrent", "hidden_bias", "output", "output_bias")
_MAX_TARGETS = 16 * 1024 * 1024
_MAX_UPDATES = 65536


@dataclass(frozen=True, slots=True)
class PreferencePair:
    prompt: str
    chosen: str
    rejected: str

    def __post_init__(self) -> None:
        for name, value in (("prompt", self.prompt), ("chosen", self.chosen), ("rejected", self.rejected)):
            if not isinstance(value, str) or not value.strip() or len(value.encode("utf-8")) > 1024:
                raise ValueError(f"preference {name} must contain bounded nonempty UTF-8 text")
        if self.chosen == self.rejected:
            raise ValueError("chosen and rejected preferences must differ")
        if len(self.document.encode()) > 4096:
            raise ValueError("preference pair document exceeds byte bound")

    @property
    def document(self) -> str:
        return _canonical(
            {
                "schema_version": PAIR_SCHEMA,
                "prompt": self.prompt,
                "chosen": self.chosen,
                "rejected": self.rejected,
            }
        )

    @classmethod
    def from_document(cls, document: str) -> PreferencePair:
        import json

        try:
            if not isinstance(document, str) or len(document.encode()) > 4096:
                raise ValueError("pair document byte bound")
            value = json.loads(document)
            if (
                not isinstance(value, dict)
                or set(value) != {"schema_version", "prompt", "chosen", "rejected"}
                or value["schema_version"] != PAIR_SCHEMA
            ):
                raise ValueError("unsupported preference document schema")
            pair = cls(value["prompt"], value["chosen"], value["rejected"])
            if pair.document != document:
                raise ValueError("preference document must be canonical JSON")
            return pair
        except (ValueError, TypeError, KeyError, UnicodeError) as exc:
            raise TrainingStateError("invalid governed preference document") from exc


def _likelihood(model: NumpyRecurrentLM, prompt: str, completion: str, *, gradients: bool):
    """Conditional sum log likelihood with prompt-masked true recurrent BPTT."""
    tokens = (BOS, *prompt.encode(), *completion.encode(), EOS)
    inputs, targets = tokens[:-1], tokens[1:]
    states, probabilities = model._forward(inputs)
    prefix = len(prompt.encode())
    log_probability = 0.0
    for index in range(prefix, len(targets)):
        logits = states[index + 1] @ model.output + model.output_bias
        maximum = float(np.max(logits))
        log_probability += (
            float(logits[targets[index]]) - maximum - math.log(float(np.sum(np.exp(logits - maximum))))
        )
    if not math.isfinite(log_probability):
        raise TrainingStateError("nonfinite preference likelihood")
    if not gradients:
        return log_probability, None
    result = {name: np.zeros_like(getattr(model, name)) for name in _PARAMETERS}
    dh_next = np.zeros(model.config.hidden_size, dtype=np.float64)
    for index in range(len(inputs) - 1, -1, -1):
        dy = np.zeros_like(probabilities[index])
        if index >= prefix:
            dy = probabilities[index].copy()
            dy[targets[index]] -= 1.0
        hidden, previous = states[index + 1], states[index]
        result["output"] += np.outer(hidden, dy)
        result["output_bias"] += dy
        dz = (dy @ model.output.T + dh_next) * (1.0 - hidden * hidden)
        result["embedding"][inputs[index]] += dz
        result["recurrent"] += np.outer(previous, dz)
        result["hidden_bias"] += dz
        dh_next = dz @ model.recurrent.T
    return log_probability, result


def preference_objective_and_gradients(
    policy: NumpyRecurrentLM, reference: NumpyRecurrentLM, pair: PreferencePair, *, beta: float
):
    """Return DPO loss, actual policy preference margin and exact parameter gradients."""
    if type(policy) is not NumpyRecurrentLM or type(reference) is not NumpyRecurrentLM:
        raise TypeError("preference objective requires native recurrent models")
    if type(beta) not in {float, int} or not math.isfinite(beta) or not 0 < beta <= 10:
        raise ValueError("preference beta must be finite and in (0, 10]")
    chosen, chosen_grad = _likelihood(policy, pair.prompt, pair.chosen, gradients=True)
    rejected, rejected_grad = _likelihood(policy, pair.prompt, pair.rejected, gradients=True)
    ref_chosen, _ = _likelihood(reference, pair.prompt, pair.chosen, gradients=False)
    ref_rejected, _ = _likelihood(reference, pair.prompt, pair.rejected, gradients=False)
    margin = chosen - rejected
    z = beta * (margin - (ref_chosen - ref_rejected))
    loss = float(np.logaddexp(0.0, -z))
    exponent = math.exp(-abs(z))
    multiplier = beta * (exponent / (1 + exponent) if z >= 0 else 1 / (1 + exponent))
    gradient = {name: multiplier * (chosen_grad[name] - rejected_grad[name]) for name in _PARAMETERS}
    if not math.isfinite(loss) or any(not np.all(np.isfinite(value)) for value in gradient.values()):
        raise TrainingStateError("nonfinite DPO objective or gradients")
    return loss, margin, gradient


def _observations(policy, reference, pairs, beta):
    losses, margins = [], []
    for pair in pairs:
        chosen, _ = _likelihood(policy, pair.prompt, pair.chosen, gradients=False)
        rejected, _ = _likelihood(policy, pair.prompt, pair.rejected, gradients=False)
        ref_chosen, _ = _likelihood(reference, pair.prompt, pair.chosen, gradients=False)
        ref_rejected, _ = _likelihood(reference, pair.prompt, pair.rejected, gradients=False)
        margin = chosen - rejected
        loss = float(np.logaddexp(0.0, -beta * (margin - (ref_chosen - ref_rejected))))
        if not math.isfinite(loss) or not math.isfinite(margin):
            raise TrainingStateError("nonfinite preference observations")
        losses.append(loss)
        margins.append(margin)
    return {"loss": sum(losses) / len(losses), "margin": sum(margins) / len(margins)}


def _implementation_digest():
    root = Path(__file__).parent
    paths = (
        Path(__file__),
        root / "control.py",
        root / "data.py",
        root / "neural_trainer.py",
        root.parent / "inference" / "neural.py",
    )
    return _digest(
        {str(path.relative_to(root.parent)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    )


def _runtime():
    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "platform": sys.platform,
        "machine": platform.machine(),
        "numpy_configuration": _digest(getattr(np.__config__, "CONFIG", {})),
    }


def _validate_reserved_lineage(manifest, parent, experiment):
    expected = {
        "parent_run_id": parent["run_id"],
        "parent_checkpoint_digest": parent["checkpoint_digest"],
        "parent_model_digest": parent["model_digest"],
        "evaluation_suite_digest": experiment["evaluation_suite_digest"],
    }
    if any(manifest.hyperparameters.get(name, value) != value for name, value in expected.items()):
        raise TrainingStateError("preference immutable manifest lineage mismatch")


@dataclass(frozen=True, slots=True)
class PreferenceTrainingArtifact(LocalTrainingArtifact):
    parent_run_id: str
    parent_checkpoint_digest: str
    reference_model_digest: str
    experiment_digest: str
    evaluation_suite_digest: str
    initial_loss: float
    final_loss: float
    initial_margin: float
    final_margin: float
    epochs: int
    update_count: int
    token_count: int
    training_receipt_digest: str
    production_promotion_authorized: bool = False


class PreferenceLocalTrainer:
    """Single-worker DPO using an existing governed native neural parent."""

    def __init__(self, datasets: DatasetRegistry, runs: TrainingRepository, *, parent_run_id: str) -> None:
        if not isinstance(parent_run_id, str) or not parent_run_id.strip():
            raise ValueError("parent_run_id must be nonempty")
        self.datasets, self.runs, self.parent_run_id = datasets, runs, parent_run_id
        self.parent_trainer = NeuralLocalTrainer(datasets, runs)

    def _parent(self):
        manifest = self.runs.manifest(self.parent_run_id)
        if manifest.world_size != 1 or manifest.parallelism != "single":
            raise TrainingStateError("preference parent requires a single-worker native neural run")
        model, artifact = self.parent_trainer.load_artifact(self.parent_run_id)
        binding = self.runs.execution_binding(self.parent_run_id)
        if (
            model.config.hidden_size > 64
            or binding["schema_version"] != "skeleton.neural_training_binding.v1"
        ):
            raise TrainingStateError("preference parent must be a bounded single-worker native neural model")
        return model, {
            "run_id": self.parent_run_id,
            "manifest_digest": manifest.digest,
            "code_digest": manifest.code_digest,
            "environment_digest": manifest.environment_digest,
            "binding_digest": _digest(binding),
            "checkpoint_digest": artifact.checkpoint_digest,
            "model_digest": model.model_digest,
            "dataset_digest": manifest.dataset_digest,
            "dataset_authority_epoch": binding["dataset_authority_epoch"],
        }

    def _authority(self, binding):
        self.datasets.assert_dataset_authority(binding["dataset_digest"], binding["dataset_authority_epoch"])
        model, lineage = self._parent()
        if lineage != binding["parent"]:
            raise TrainingStateError("preference parent training lineage drift")
        return model

    @staticmethod
    def _usage(binding, epoch, pair_index):
        count = binding["document_count"]
        prefix_targets = sum(binding["pair_targets"][:pair_index])
        prefix_bytes = sum(binding["pair_training_bytes"][:pair_index])
        evaluation_passes = 2 if epoch == binding["training_config"]["epochs"] else 1
        optimization_steps = epoch * sum(binding["pair_targets"]) + prefix_targets
        evaluation_steps = evaluation_passes * sum(binding["pair_targets"])
        return {
            "steps": optimization_steps + evaluation_steps,
            "pairs": epoch * count + pair_index,
            "training_bytes": epoch * sum(binding["pair_training_bytes"])
            + prefix_bytes
            + evaluation_passes * sum(binding["pair_training_bytes"]),
            "epochs": epoch,
            "evaluation_steps": evaluation_steps,
        }

    @staticmethod
    def _enforce_usage(manifest, binding, usage):
        if usage["steps"] > _MAX_TARGETS or usage["pairs"] > _MAX_UPDATES:
            raise TrainingStateError("preference hard execution budget exceeded")
        for name, actual in (
            ("max_steps", usage["steps"]),
            ("max_tokens", usage["steps"]),
            ("max_pairs", usage["pairs"]),
            ("max_updates", usage["pairs"]),
            ("max_documents", usage["pairs"]),
            ("max_training_bytes", usage["training_bytes"]),
            ("max_epochs", usage["epochs"]),
            ("max_corpus_bytes", binding["corpus_bytes"]),
        ):
            limit = manifest.resource_budget.get(name)
            if limit is not None and actual > limit:
                raise TrainingStateError(f"preference budget exceeded: {name}")

    @staticmethod
    def _optimizer(config):
        return {
            "algorithm": ALGORITHM,
            "learning_rate": config["learning_rate"],
            "gradient_clip": config["gradient_clip"],
            "beta": config["beta"],
            "slots": {},
        }

    def _persist(self, manifest, binding, lease, policy, reference, epoch, index, observations, instant):
        usage = self._usage(binding, epoch, index)
        cursor = {"epoch": epoch, "pair_index": index, "update_count": usage["pairs"], "step": usage["steps"]}
        optimizer = self._optimizer(binding["training_config"])
        payload = {
            "schema_version": PAYLOAD_SCHEMA,
            "binding_digest": _digest(binding),
            "cursor": cursor,
            "usage": usage,
            "optimizer": optimizer,
            "model": policy.to_dict(),
            "reference": reference.to_dict(),
            "observations": observations,
            "finished": epoch == binding["training_config"]["epochs"],
        }
        checkpoint = TrainingCheckpoint(
            run_id=manifest.run_id,
            manifest_digest=manifest.digest,
            step=usage["steps"],
            model_digest=policy.model_digest,
            optimizer_digest=_digest(optimizer),
            rng_digest=_digest({"seed": manifest.seed, "stochastic_updates": False}),
            data_cursor_digest=_digest(cursor),
            worker_epoch=lease.epoch,
            created_at=instant.isoformat(),
            payload_digest=_digest(payload),
        )
        with self.datasets.training_authority(binding["dataset_digest"], binding["dataset_authority_epoch"]):
            self._authority(binding)
            self.runs.checkpoint(checkpoint, lease, payload=payload)
        return checkpoint

    def _restore(self, manifest, binding, checkpoint, documents=None, *, payload=None):
        if (
            manifest.run_id == self.parent_run_id
            or manifest.world_size != 1
            or manifest.parallelism != "single"
        ):
            raise TrainingStateError("preference candidate requires a distinct single-worker run")
        try:
            if set(binding) != {
                "schema_version",
                "manifest_digest",
                "dataset_digest",
                "dataset_authority_epoch",
                "split_name",
                "split_digest",
                "corpus_digest",
                "document_sequence_digest",
                "pair_digests",
                "document_count",
                "pair_targets",
                "pair_training_bytes",
                "corpus_bytes",
                "training_config",
                "parent",
                "experiment",
                "implementation_digest",
                "runtime",
            }:
                raise ValueError("unsupported preference binding fields")
            if (
                binding["schema_version"] != BINDING_SCHEMA
                or binding["manifest_digest"] != manifest.digest
                or binding["dataset_digest"] != manifest.dataset_digest
                or binding["parent"]["model_digest"] != manifest.base_model_digest
                or binding["parent"]["run_id"] != self.parent_run_id
                or binding["implementation_digest"] != _implementation_digest()
                or binding["runtime"] != _runtime()
            ):
                raise ValueError("preference identity/schema/code/runtime mismatch")
            config = binding["training_config"]
            if (
                set(config)
                != {
                    "algorithm",
                    "model_id",
                    "hidden_size",
                    "seed",
                    "dtype",
                    "epochs",
                    "beta",
                    "learning_rate",
                    "gradient_clip",
                }
                or config["algorithm"] != ALGORITHM
            ):
                raise ValueError("preference optimizer configuration drift")
            if (
                config["seed"] != manifest.seed
                or type(config["seed"]) is not int
                or config["model_id"] != "skeleton-local-preference:" + manifest.run_id
                or config["dtype"] != "float64"
                or type(config["hidden_size"]) is not int
                or not 4 <= config["hidden_size"] <= 64
                or type(config["epochs"]) is not int
                or not 1 <= config["epochs"] <= 128
                or checkpoint.run_id != manifest.run_id
                or checkpoint.manifest_digest != manifest.digest
            ):
                raise ValueError("preference bounded configuration drift")
            for name, maximum in (("beta", 10), ("learning_rate", 10), ("gradient_clip", 1000)):
                value = config[name]
                if type(value) not in {int, float} or not math.isfinite(value) or not 0 < value <= maximum:
                    raise ValueError("invalid preference optimizer value")
            for name in ("epochs", "beta", "learning_rate", "gradient_clip", "hidden_size", "dtype"):
                if name in manifest.hyperparameters and manifest.hyperparameters[name] != config[name]:
                    raise ValueError("preference manifest configuration mismatch")
            if manifest.hyperparameters.get("algorithm", "preference") not in {"preference", ALGORITHM}:
                raise ValueError("preference manifest algorithm mismatch")
            experiment = binding["experiment"]
            if set(experiment) != {
                "experiment_id",
                "base_candidate_digest",
                "dataset_digest",
                "objective",
                "algorithm",
                "configuration",
                "evaluation_suite_digest",
                "production_authority",
            }:
                raise ValueError("invalid preference experiment fields")
            parsed_experiment = PostTrainingExperiment(
                **{key: value for key, value in experiment.items() if key != "production_authority"}
            )
            if (
                parsed_experiment.as_dict() != experiment
                or experiment["production_authority"] is not False
                or experiment["base_candidate_digest"] != manifest.base_model_digest
                or experiment["dataset_digest"] != manifest.dataset_digest
                or experiment["objective"] != "dpo"
                or experiment["algorithm"] != ALGORITHM
                or experiment["configuration"]
                != {name: config[name] for name in ("epochs", "beta", "learning_rate", "gradient_clip")}
            ):
                raise ValueError("preference experiment lineage mismatch")
            _validate_reserved_lineage(manifest, binding["parent"], experiment)
            corpus = (
                self.datasets.training_corpus(manifest.dataset_digest, split_name=binding["split_name"])
                if documents is None
                else tuple(documents)
            )
            pairs = tuple(PreferencePair.from_document(doc) for doc in corpus)
            if (
                [_digest(doc) for doc in corpus] != binding["pair_digests"]
                or corpus_digest(corpus) != binding["corpus_digest"]
                or _digest(corpus) != binding["document_sequence_digest"]
                or binding["document_count"] != len(pairs)
            ):
                raise ValueError("preference exact pair sequence mismatch")
            if (
                not 1 <= len(pairs) <= 1024
                or len("\n".join(corpus).encode()) > 1024 * 1024
                or binding["split_digest"] != corpus_digest(corpus)
                or binding["split_name"] != "train"
            ):
                raise ValueError("invalid preference corpus bound/split")
            self.datasets.validate_training_corpus(
                manifest.dataset_digest, corpus, split_name=binding["split_name"]
            )
            expected_targets, expected_bytes = self._costs(pairs)
            if (
                binding["pair_targets"] != expected_targets
                or binding["pair_training_bytes"] != expected_bytes
                or binding["corpus_bytes"] != len("\n".join(corpus).encode())
            ):
                raise ValueError("preference budget dimension drift")
            self._authority(binding)
            payload = self.runs.checkpoint_payload(checkpoint) if payload is None else dict(payload)
            if (
                set(payload)
                != {
                    "schema_version",
                    "binding_digest",
                    "cursor",
                    "usage",
                    "optimizer",
                    "model",
                    "reference",
                    "observations",
                    "finished",
                }
                or payload["schema_version"] != PAYLOAD_SCHEMA
                or payload["binding_digest"] != _digest(binding)
                or _digest(payload) != checkpoint.payload_digest
            ):
                raise ValueError("unsupported preference resume schema")
            cursor, usage = payload["cursor"], payload["usage"]
            if set(cursor) != {"epoch", "pair_index", "update_count", "step"} or any(
                type(v) is not int or v < 0 for v in cursor.values()
            ):
                raise ValueError("invalid preference cursor")
            epoch, index = cursor["epoch"], cursor["pair_index"]
            if (
                not 0 <= epoch <= config["epochs"]
                or not 0 <= index < len(pairs)
                or (epoch == config["epochs"] and index)
            ):
                raise ValueError("preference cursor outside pair sequence")
            if (
                usage != self._usage(binding, epoch, index)
                or any(type(v) is not int for v in usage.values())
                or cursor["update_count"] != usage["pairs"]
                or cursor["step"] != usage["steps"]
                or checkpoint.step != usage["steps"]
                or checkpoint.data_cursor_digest != _digest(cursor)
            ):
                raise ValueError("preference cumulative usage mismatch")
            if (
                payload["optimizer"] != self._optimizer(config)
                or checkpoint.optimizer_digest != _digest(payload["optimizer"])
                or checkpoint.rng_digest != _digest({"seed": manifest.seed, "stochastic_updates": False})
                or payload["finished"] is not (epoch == config["epochs"])
            ):
                raise ValueError("preference optimizer/seed/terminal identity mismatch")
            policy = NumpyRecurrentLM.from_dict(payload["model"])
            reference = NumpyRecurrentLM.from_dict(payload["reference"])
            parent, _lineage = self._parent()
            if (
                reference.model_digest != manifest.base_model_digest
                or reference.to_dict() != parent.to_dict()
                or policy.model_digest != checkpoint.model_digest
                or policy.model_id != config["model_id"]
                or policy.config != parent.config
                or config["hidden_size"] != parent.config.hidden_size
                or manifest.seed != parent.config.seed
            ):
                raise ValueError("preference policy/reference model mismatch")
            if usage["pairs"] == 0 and any(
                not np.array_equal(getattr(policy, name), getattr(reference, name)) for name in _PARAMETERS
            ):
                raise ValueError("preference initial policy weights differ from reference")
            observations = payload["observations"]
            if set(observations) != {"initial", "final"} or observations["initial"] != _observations(
                reference, reference, pairs, config["beta"]
            ):
                raise ValueError("preference initial objective evidence mismatch")
            if epoch == config["epochs"]:
                if observations["final"] != _observations(policy, reference, pairs, config["beta"]):
                    raise ValueError("preference final objective evidence mismatch")
            elif observations["final"] is not None:
                raise ValueError("preference nonterminal objective evidence")
            self._enforce_usage(manifest, binding, usage)
            return policy, reference, cursor, usage, observations
        except (ValueError, TypeError, KeyError, NeuralLMError) as exc:
            raise TrainingStateError("invalid preference training resume state") from exc

    @staticmethod
    def _costs(pairs):
        training_bytes = [
            2 * (2 * len(pair.prompt.encode()) + len(pair.chosen.encode()) + len(pair.rejected.encode()))
            for pair in pairs
        ]
        return [value + 4 for value in training_bytes], training_bytes

    @staticmethod
    def _artifact(manifest, binding, checkpoint, policy, usage, observations):
        initial, final = observations["initial"], observations["final"]
        receipt = {
            "schema_version": "skeleton.preference_training_receipt.v1",
            "binding_digest": _digest(binding),
            "checkpoint_digest": checkpoint.digest,
            "model_digest": policy.model_digest,
            "observations": observations,
            "usage": usage,
        }
        return PreferenceTrainingArtifact(
            run_id=manifest.run_id,
            run_manifest_digest=manifest.digest,
            dataset_digest=manifest.dataset_digest,
            model_id=policy.model_id,
            model_digest=policy.model_digest,
            checkpoint_digest=checkpoint.digest,
            corpus_digest=binding["corpus_digest"],
            document_count=binding["document_count"],
            parent_run_id=binding["parent"]["run_id"],
            parent_checkpoint_digest=binding["parent"]["checkpoint_digest"],
            reference_model_digest=binding["parent"]["model_digest"],
            experiment_digest=_digest(binding["experiment"]),
            evaluation_suite_digest=binding["experiment"]["evaluation_suite_digest"],
            initial_loss=initial["loss"],
            final_loss=final["loss"],
            initial_margin=initial["margin"],
            final_margin=final["margin"],
            epochs=binding["training_config"]["epochs"],
            update_count=usage["pairs"],
            token_count=usage["steps"],
            training_receipt_digest=_digest(receipt),
        )

    def load_artifact(self, run_id):
        manifest = self.runs.manifest(run_id)
        binding, checkpoint = self.runs.execution_binding(run_id), self.runs.latest_checkpoint(run_id)
        if self.runs.state(run_id) != "completed" or binding is None or checkpoint is None:
            raise TrainingStateError("preference artifact requires a completed payload-backed run")
        policy, _reference, cursor, usage, observations = self._restore(manifest, binding, checkpoint)
        if cursor["epoch"] != binding["training_config"]["epochs"] or observations["final"] is None:
            raise TrainingStateError("completed preference artifact is not terminal")
        return policy, self._artifact(manifest, binding, checkpoint, policy, usage, observations)

    def train(
        self,
        manifest: TrainingRunManifest,
        documents: Sequence[str],
        *,
        experiment: PostTrainingExperiment,
        epochs: int = 8,
        beta: float = 0.1,
        learning_rate: float = 0.05,
        gradient_clip: float = 1.0,
        worker_id: str = "local-preference-trainer",
        now: datetime | None = None,
    ):
        instant = now or datetime.now(UTC)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("preference timestamp must be timezone-aware")
        if (
            manifest.run_id == self.parent_run_id
            or manifest.world_size != 1
            or manifest.parallelism != "single"
        ):
            raise TrainingStateError("preference candidate requires a distinct single-worker run")
        if type(epochs) is not int or not 1 <= epochs <= 128:
            raise TrainingStateError("preference epochs must be in [1,128]")
        for name, value, maximum in (
            ("beta", beta, 10),
            ("learning_rate", learning_rate, 10),
            ("gradient_clip", gradient_clip, 1000),
        ):
            if type(value) not in {float, int} or not math.isfinite(value) or not 0 < value <= maximum:
                raise TrainingStateError(f"invalid preference {name}")
        corpus = tuple(documents)
        if not 1 <= len(corpus) <= 1024 or len("\n".join(corpus).encode()) > 1024 * 1024:
            raise TrainingStateError("preference corpus count/bytes exceeds bound")
        pairs = tuple(PreferencePair.from_document(doc) for doc in corpus)
        self.datasets.validate_training_corpus(manifest.dataset_digest, corpus)
        dataset = self.datasets.require_training_ready(manifest.dataset_digest)
        split = next((item for item in dataset.splits if item.name == "train"), None)
        if split is None or split.digest != corpus_digest(corpus) or split.record_count != len(pairs):
            raise TrainingStateError("preference documents differ from registered train split")
        parent, lineage = self._parent()
        if manifest.base_model_digest != parent.model_digest:
            raise TrainingStateError("preference parent/base model identity mismatch")
        config = {
            "algorithm": ALGORITHM,
            "model_id": "skeleton-local-preference:" + manifest.run_id,
            "hidden_size": parent.config.hidden_size,
            "seed": manifest.seed,
            "dtype": "float64",
            "epochs": epochs,
            "beta": float(beta),
            "learning_rate": float(learning_rate),
            "gradient_clip": float(gradient_clip),
        }
        if manifest.seed != parent.config.seed:
            raise TrainingStateError("preference seed must retain parent numerical configuration")
        for name in ("epochs", "beta", "learning_rate", "gradient_clip", "hidden_size", "dtype"):
            if name in manifest.hyperparameters and manifest.hyperparameters[name] != config[name]:
                raise TrainingStateError("preference configuration conflicts with immutable manifest")
        if manifest.hyperparameters.get("algorithm", "preference") not in {"preference", ALGORITHM}:
            raise TrainingStateError("preference manifest algorithm mismatch")
        expected_experiment = {
            "epochs": epochs,
            "beta": float(beta),
            "learning_rate": float(learning_rate),
            "gradient_clip": float(gradient_clip),
        }
        if (
            not isinstance(experiment, PostTrainingExperiment)
            or experiment.base_candidate_digest != parent.model_digest
            or experiment.dataset_digest != manifest.dataset_digest
            or experiment.algorithm != ALGORITHM
            or experiment.objective != "dpo"
            or dict(experiment.configuration) != expected_experiment
        ):
            raise TrainingStateError("preference experiment lineage/configuration mismatch")
        _validate_reserved_lineage(manifest, lineage, experiment.as_dict())
        targets, byte_costs = self._costs(pairs)
        binding = {
            "schema_version": BINDING_SCHEMA,
            "manifest_digest": manifest.digest,
            "dataset_digest": manifest.dataset_digest,
            "dataset_authority_epoch": self.datasets.dataset_authority_epoch(manifest.dataset_digest),
            "split_name": "train",
            "split_digest": split.digest,
            "corpus_digest": corpus_digest(corpus),
            "document_sequence_digest": _digest(corpus),
            "pair_digests": [_digest(doc) for doc in corpus],
            "document_count": len(pairs),
            "pair_targets": targets,
            "pair_training_bytes": byte_costs,
            "corpus_bytes": len("\n".join(corpus).encode()),
            "training_config": config,
            "parent": lineage,
            "experiment": experiment.as_dict(),
            "implementation_digest": _implementation_digest(),
            "runtime": _runtime(),
        }
        self._enforce_usage(manifest, binding, self._usage(binding, epochs, 0))
        self.runs.register_run(manifest, self.datasets, created_at=instant)
        self.runs.bind_execution(manifest.run_id, binding)
        state = self.runs.state(manifest.run_id)
        checkpoint = self.runs.latest_checkpoint(manifest.run_id)
        reference = NumpyRecurrentLM.from_dict(parent.to_dict())
        policy = NumpyRecurrentLM(
            model_id=config["model_id"],
            config=parent.config,
            parameters={name: getattr(parent, name) for name in _PARAMETERS},
        )
        epoch = index = 0
        observations = {"initial": None, "final": None}
        if checkpoint is not None:
            policy, reference, cursor, _usage, observations = self._restore(
                manifest, binding, checkpoint, corpus
            )
            epoch, index = cursor["epoch"], cursor["pair_index"]
        if state == "completed":
            return self.load_artifact(manifest.run_id)
        if state in {"running", "failed"}:
            checkpoint = self.runs.recover(manifest.run_id, allow_empty=True)
            if checkpoint is not None:
                policy, reference, cursor, _usage, observations = self._restore(
                    manifest, binding, checkpoint, corpus
                )
                epoch, index = cursor["epoch"], cursor["pair_index"]
            state = "recovering"
        if state not in {"registered", "recovering"}:
            raise TrainingStateError("preference run state cannot execute")
        self.runs.start(manifest.run_id)
        lease = self.runs.lease_worker(manifest.run_id, worker_id, issued_at=instant)
        try:
            if checkpoint is None:
                self._authority(binding)
                observations["initial"] = _observations(policy, reference, pairs, beta)
                checkpoint = self._persist(
                    manifest, binding, lease, policy, reference, epoch, index, observations, instant
                )
            while epoch < epochs:
                self.runs.assert_worker_current(lease)
                self._authority(binding)
                _loss, _margin, gradients = preference_objective_and_gradients(
                    policy, reference, pairs[index], beta=beta
                )
                norm = math.sqrt(sum(float(np.sum(value * value)) for value in gradients.values()))
                if not math.isfinite(norm):
                    raise TrainingStateError("nonfinite preference gradient norm")
                scale = 1 if norm <= gradient_clip else gradient_clip / norm
                for name in _PARAMETERS:
                    updated = getattr(policy, name) - learning_rate * scale * gradients[name]
                    if not np.all(np.isfinite(updated)):
                        raise TrainingStateError("nonfinite preference weight update")
                    setattr(policy, name, updated)
                index += 1
                if index == len(pairs):
                    epoch, index = epoch + 1, 0
                if epoch == epochs:
                    observations["final"] = _observations(policy, reference, pairs, beta)
                checkpoint = self._persist(
                    manifest, binding, lease, policy, reference, epoch, index, observations, instant
                )
                self.runs.record_telemetry(
                    TrainingTelemetry(
                        manifest.run_id,
                        checkpoint.step,
                        {
                            "preference_updates": float(self._usage(binding, epoch, index)["pairs"]),
                            "epoch": float(epoch),
                        },
                        instant.isoformat(),
                    ),
                    lease,
                )
            with self.datasets.training_authority(
                binding["dataset_digest"], binding["dataset_authority_epoch"]
            ):
                self._authority(binding)
                terminal = self.runs.complete(manifest.run_id, lease)
            if terminal.digest != checkpoint.digest:
                raise TrainingStateError("preference terminal checkpoint drift")
        except Exception:
            try:
                self.runs.fail(manifest.run_id, lease)
            except (TrainingStateError, sqlite3.Error):
                pass
            raise
        return policy, self._artifact(
            manifest, binding, checkpoint, policy, self._usage(binding, epoch, index), observations
        )
