"""Materialized candidate-only native transformer training from shadow intake.

The trainer clones a pinned champion, consumes only a content-addressed local
UTF-8 training corpus, performs bounded TinyTransformer SGD, and atomically
stores native checkpoint bytes. It never mutates or activates serving weights.
Its output is a real candidate model plus replayable training custody for the
shadow ledger; independent mirror evaluation remains a separate authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import os
import math
import json
from pathlib import Path
from typing import Callable
from uuid import uuid4

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime
from skeleton.ai.model_runtime.flgb_model_runtime import TokenSequence
from skeleton.cortex.attn import cosine_lr, softmax
from skeleton.cortex.transformer import KVCache

from .flgb_training_runtime import (
    DatasetRevision, TrainingCheckpoint, TrainingManifest,
    digest_json, require_digest,
)
from .shadow_idle_training import (
    ShadowLeaseSession, ShadowTrainingArtifacts, ShadowTrainingRejected,
)
from .shadow_weight_intake import ShadowKnowledge
from .shadow_weights import ShadowWeightError
from .native_adapter_learning import NativeAdapterPolicy, fit_native_output_adapter

_MAX_TEXT_BYTES = 4 * 1024 * 1024
_MAX_LINE_BYTES = 16 * 1024


@dataclass(frozen=True, slots=True)
class ShadowNativeTrainingPolicy:
    """Explicit bounds for original training, never evaluation/admission."""

    maximum_corpus_bytes: int = 512 * 1024
    maximum_lines: int = 2048
    maximum_steps: int = 8192
    lines_per_heartbeat: int = 16
    learning_rate_ppm: int = 20_000
    teacher_retention_ppm: int = 0
    teacher_min_target_probability_ppm: int = 100_000
    adapter_policy: NativeAdapterPolicy | None = None

    def __post_init__(self) -> None:
        values = (
            ("maximum_corpus_bytes", self.maximum_corpus_bytes, 1, _MAX_TEXT_BYTES),
            ("maximum_lines", self.maximum_lines, 1, 100_000),
            ("maximum_steps", self.maximum_steps, 1, 1_000_000),
            ("lines_per_heartbeat", self.lines_per_heartbeat, 1, 1024),
            ("learning_rate_ppm", self.learning_rate_ppm, 1, 100_000),
            ("teacher_retention_ppm", self.teacher_retention_ppm, 0, 500_000),
            ("teacher_min_target_probability_ppm", self.teacher_min_target_probability_ppm, 1, 1_000_000),
        )
        for name, value, minimum, maximum in values:
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise ShadowWeightError(f"invalid native shadow training {name}")

        if self.adapter_policy is not None:
            if type(self.adapter_policy) is not NativeAdapterPolicy:
                raise ShadowWeightError("typed native adapter training policy required")
            if self.teacher_retention_ppm:
                raise ShadowWeightError("choose one native weight update mode")
            if self.adapter_policy.maximum_steps > self.maximum_steps:
                raise ShadowWeightError("adapter budget exceeds shadow training admission")
            if self.adapter_policy.learning_rate_ppm != self.learning_rate_ppm:
                raise ShadowWeightError("adapter learning rate differs from shadow admission")

    @property
    def digest(self) -> str:
        payload = {
            "maximum_corpus_bytes": self.maximum_corpus_bytes,
            "maximum_lines": self.maximum_lines,
            "maximum_steps": self.maximum_steps,
            "lines_per_heartbeat": self.lines_per_heartbeat,
            "learning_rate_ppm": self.learning_rate_ppm,
            "schedule": "cosine-batch",
            "engine": "skeleton.cortex.TinyTransformer",
        }
        if self.teacher_retention_ppm:
            payload["teacher_retention"] = {
                "algorithm": "unit-temperature-confidence-gated-soft-target-v1",
                "weight_ppm": self.teacher_retention_ppm,
                "minimum_target_probability_ppm": self.teacher_min_target_probability_ppm,
            }
        if self.adapter_policy is not None:
            payload["native_adapter_policy"] = self.adapter_policy.digest
            payload["schedule"] = "cosine-global-native-output-lora"
        return digest_json(payload)


class ShadowNativeTrainer:
    """Callable trainer for ShadowIdleTrainingWorker.

    corpus_path resolves the *materialized* corpus for a shadow knowledge item.
    code_digest must identify the exact trainer implementation/version, not a
    claimed quality score. The produced checkpoint is private, immutable and
    SHA-256 named. It is never loaded into a live serving model by this class.
    """

    def __init__(
        self,
        champion: NativeLLMRuntime,
        *,
        corpus_path: Callable[[ShadowKnowledge], str | Path],
        artifact_directory: str | Path,
        code_digest: str,
        policy: ShadowNativeTrainingPolicy | None = None,
    ) -> None:
        if not isinstance(champion, NativeLLMRuntime):
            raise ShadowWeightError("native champion runtime required")
        if not callable(corpus_path):
            raise ShadowWeightError("source-pinned corpus resolver required")
        self.champion = champion
        self.corpus_path = corpus_path
        self.code_digest = require_digest(code_digest, "trainer code digest")
        self.policy = policy or ShadowNativeTrainingPolicy()
        if not isinstance(self.policy, ShadowNativeTrainingPolicy):
            raise ShadowWeightError("native shadow training policy required")
        self.directory = Path(artifact_directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)

    def _read_corpus(self, item: ShadowKnowledge) -> tuple[str, ...]:
        path = Path(self.corpus_path(item))
        if path.is_symlink() or not path.is_file():
            raise ShadowTrainingRejected("source-corpus-unavailable")
        if path.stat().st_size > self.policy.maximum_corpus_bytes:
            raise ShadowTrainingRejected("source-corpus-over-budget")
        with path.open("rb") as source:
            raw = source.read(self.policy.maximum_corpus_bytes + 1)
        if len(raw) > self.policy.maximum_corpus_bytes:
            raise ShadowTrainingRejected("source-corpus-over-budget")
        if sha256(raw).hexdigest() != item.content_digest:
            raise ShadowTrainingRejected("source-corpus-digest-mismatch")
        try:
            decoded = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ShadowTrainingRejected("source-corpus-non-utf8") from exc
        lines = tuple(line.strip() for line in decoded.splitlines() if line.strip())
        if not lines or len(lines) > self.policy.maximum_lines:
            raise ShadowTrainingRejected("source-corpus-line-budget")
        if any(len(line.encode("utf-8")) > _MAX_LINE_BYTES for line in lines):
            raise ShadowTrainingRejected("source-corpus-line-over-budget")
        return lines

    def _publish_checkpoint(self, checkpoint_json: str) -> Path:
        return self._publish_native_artifact(checkpoint_json.encode("utf-8"), ".native.json")

    def _publish_native_artifact(self, raw: bytes, suffix: str) -> Path:
        # Existing private content-addressed artifact owner. The sidecar is
        # observation evidence only, never an activation authorization.
        if suffix not in (".native.json", ".adapter-evidence.json"):
            raise ShadowWeightError("unrecognized native candidate artifact suffix")
        digest = sha256(raw).hexdigest()
        target = self.directory / (digest + suffix)
        if target.is_symlink():
            raise ShadowWeightError("native candidate checkpoint must not be a symlink")
        if target.exists():
            if target.read_bytes() != raw:
                raise ShadowWeightError("native candidate checkpoint content conflict")
            return target
        temporary = self.directory / ("." + uuid4().hex + ".native.tmp")
        try:
            with os.fdopen(
                os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
            ) as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                if target.is_symlink() or target.read_bytes() != raw:
                    raise ShadowWeightError("concurrent native candidate checkpoint conflict")
            else:
                if os.name == "posix":
                    fd = os.open(self.directory, os.O_RDONLY)
                    try:
                        os.fsync(fd)
                    finally:
                        os.close(fd)
        finally:
            temporary.unlink(missing_ok=True)
        return target

    def _fit_retention_batch(self, candidate: NativeLLMRuntime, batch: tuple[str, ...],
                             session: ShadowLeaseSession) -> tuple[int, int]:
        """Actual local confidence-gated champion rehearsal, no extra corpus.

        Teacher gets the exact training prefix. Do not imitate teacher
        distributions when their known target probability is too low.
        Candidate and champion never share mutable parameter arrays.
        """
        teacher = self.champion
        if (candidate.model is teacher.model
                or candidate.tokenizer.digest != teacher.tokenizer.digest
                or candidate.architecture.digest != teacher.architecture.digest
                or candidate.limits.max_context != teacher.limits.max_context
                or candidate.model._accel is not None or candidate.model.use_mod):
            raise ShadowTrainingRejected("teacher-retention-tokenizer-or-graph-drift")
        sequences=[]
        for line in batch:
            session.require_idle()
            source = teacher.encode(line)
            # The candidate's runtime identity describes the pre-SGD clone;
            # tokenizer identity is unchanged, but do not pretend candidate
            # weights are still the original admitted inference graph.
            student_ids = tuple(candidate.model._ids(line))
            if source.token_ids != student_ids:
                raise ShadowTrainingRejected("teacher-retention-tokenization-drift")
            sequences.append(source)
        total = max(1, sum(max(0,len(seq.token_ids)-1) for seq in sequences))
        steps = soft_steps = 0
        for source in sequences:
            cache = KVCache(teacher.model.n_layers, teacher.limits.max_context)
            ids = source.token_ids
            for i in range(1,len(ids)):
                session.require_idle()
                if steps and steps % 64 == 0:
                    session.heartbeat()
                window = ids[max(0,i-teacher.limits.max_context):i]
                prefix = TokenSequence(teacher.tokenizer.digest, window,
                                       digest_json([source.digest,i]))
                result = teacher.infer_sequence(prefix, cache=cache, interrupt=session.require_idle)
                probabilities = softmax(list(result.logits))
                if any(not math.isfinite(p) for p in probabilities):
                    raise ShadowTrainingRejected("teacher-retention-nonfinite-distribution")
                eta = cosine_lr(steps,total,base=self.policy.learning_rate_ppm / 1_000_000)
                if probabilities[ids[i]] * 1_000_000 >= self.policy.teacher_min_target_probability_ppm:
                    candidate.model._sgd_soft_target(list(window),ids[i],result.logits,
                            teacher_weight=self.policy.teacher_retention_ppm/1_000_000,lr=eta)
                    soft_steps += 1
                else:
                    candidate.model._sgd(list(window),ids[i],eta)
                steps += 1
                session.require_idle()
        candidate.model.fitted += len(batch)
        return steps,soft_steps

    def __call__(self, session: ShadowLeaseSession) -> ShadowTrainingArtifacts:
        if not isinstance(session, ShadowLeaseSession):
            raise ShadowWeightError("training requires fenced shadow lease session")
        session.require_idle()
        item = session.lease.knowledge
        if self.champion.model_digest != item.base_model_digest:
            raise ShadowTrainingRejected("training-champion-drift")
        self.champion.assert_model_unchanged()
        if (self.policy.teacher_retention_ppm or self.policy.adapter_policy is not None) and (self.champion.device.actual != "cpu"
                or self.champion.device.resident or self.champion.model._accel is not None
                or self.champion.model.use_mod):
            raise ShadowTrainingRejected("teacher-retention-requires-admitted-cpu-graph")
        if (
            any(source.contradiction or not source.allowed_for_training for source in item.sources)
        ):
            raise ShadowTrainingRejected("training-source-rights-unresolved")
        corpus = self._read_corpus(item)
        # The admitted model snapshot is cloned: active weights never receive SGD.
        model = NativeLLMRuntime.restore_json(self.champion.checkpoint_json())
        if model.model_digest != item.base_model_digest:
            raise ShadowWeightError("cloned native baseline has a different digest")
        estimated_steps = 0
        for line in corpus:
            session.require_idle()
            estimated_steps += max(0, len(model.model._ids(line)) - 1)
            if estimated_steps > self.policy.maximum_steps:
                raise ShadowTrainingRejected("source-corpus-step-budget")
        if not 1 <= estimated_steps <= self.policy.maximum_steps:
            raise ShadowTrainingRejected("source-corpus-step-budget")
        dataset = DatasetRevision(
            dataset_id="shadow-" + item.digest[:24],
            revision=0,
            content_digest=item.content_digest,
            rights_digest=digest_json(sorted({source.rights_digest for source in item.sources})),
            transform_digest=digest_json({
                "encoding": "utf-8", "line_filter": "strip-nonempty",
                "max_line_bytes": _MAX_LINE_BYTES,
            }),
        )
        candidate_id = "shadow-native-" + item.digest[:32]
        manifest = TrainingManifest(
            run_id=candidate_id,
            base_model_digest=item.base_model_digest,
            dataset_revision_digests=(dataset.digest,),
            code_digest=self.code_digest,
            config_digest=self.policy.digest,
            seed_manifest_digest=digest_json({
                "training": "deterministic-output-lora" if self.policy.adapter_policy is not None else "deterministic-sgd",
                **({"adapter_seed": self.policy.adapter_policy.seed} if self.policy.adapter_policy is not None else {}),
                "knowledge_digest": item.digest,
                "champion_digest": item.base_model_digest,
            }),
            max_steps=estimated_steps,
            output_kind="candidate-only",
        )
        genesis = TrainingCheckpoint(
            run_manifest_digest=manifest.digest,
            sequence=0, weights_digest=model.model_digest,
            optimizer_digest=digest_json({"optimizer": "native-output-lora" if self.policy.adapter_policy is not None else "sgd", "steps": 0}),
            rng_digest=digest_json({"mode": "deterministic", "steps": 0}),
        )
        steps = 0
        soft_steps = 0
        adapter_report = None
        chunk_size = self.policy.lines_per_heartbeat
        if self.policy.adapter_policy is not None:
            session.heartbeat()
            adapter_report = fit_native_output_adapter(
                model, corpus, policy=self.policy.adapter_policy,
                expected_base_digest=item.base_model_digest,
                interrupt=session.require_idle, heartbeat=session.heartbeat,
            )
            steps = adapter_report.optimizer_steps
        else:
            for offset in range(0, len(corpus), chunk_size):
                session.heartbeat()
                batch = corpus[offset:offset + chunk_size]
                if self.policy.teacher_retention_ppm:
                    added, distilled = self._fit_retention_batch(model, batch, session)
                    steps += added
                    soft_steps += distilled
                else:
                    steps += model.model.fit(
                        batch, lr=self.policy.learning_rate_ppm / 1_000_000,
                        schedule="cosine", interrupt=session.require_idle,
                    )
        session.require_idle()
        if steps != estimated_steps:
            raise ShadowWeightError("actual native SGD steps differ from admission budget")
        trained = NativeLLMRuntime(model.model, limits=model.limits)
        trained.assert_model_unchanged()
        if trained.model_digest == item.base_model_digest:
            raise ShadowTrainingRejected("candidate-training-no-weight-change")
        session.require_idle()
        self.champion.assert_model_unchanged()
        if self.champion.model_digest != item.base_model_digest:
            raise ShadowTrainingRejected("training-champion-drift")
        checkpoint_json = trained.checkpoint_json()
        session.heartbeat()
        checkpoint_path = self._publish_checkpoint(checkpoint_json)
        adapter_evidence_path = None
        adapter_evidence_digest = None
        if adapter_report is not None:
            session.require_idle()
            evidence = {
                "schema": "skeleton.native_adapter_training_evidence.v1",
                "manifest_digest": manifest.digest,
                "dataset_digest": dataset.digest,
                "candidate_model_digest": trained.model_digest,
                "candidate_checkpoint_bytes_sha256": sha256(checkpoint_json.encode("utf-8")).hexdigest(),
                "report": asdict(adapter_report),
                "promotion_authorized": False,
            }
            raw = json.dumps(evidence, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
            adapter_evidence_digest = sha256(raw).hexdigest()
            adapter_evidence_path = self._publish_native_artifact(raw, ".adapter-evidence.json")
        session.heartbeat()
        self.champion.assert_model_unchanged()
        if self.champion.model_digest != item.base_model_digest:
            raise ShadowTrainingRejected("training-champion-drift")
        checkpoint = TrainingCheckpoint(
            run_manifest_digest=manifest.digest,
            sequence=1,
            weights_digest=trained.model_digest,
            optimizer_digest=digest_json({
                "optimizer": "native-output-lora" if adapter_report is not None else "sgd-no-momentum", "steps": steps,
                **({"adapter_receipt": adapter_report.receipt_digest,
                    "adapter_evidence_bytes_sha256": adapter_evidence_digest,
                    "factor_digest": adapter_report.factor_digest,
                    "merged_projection_digest": adapter_report.merged_projection_digest,
                    "rank": adapter_report.final_rank,
                    "trainable_parameters": adapter_report.trainable_parameters}
                   if adapter_report is not None else {}),
                "learning_rate_ppm": self.policy.learning_rate_ppm,
                **({
                    "teacher_model_digest": item.base_model_digest,
                    "soft_target_steps": soft_steps,
                    "teacher_retention_ppm": self.policy.teacher_retention_ppm,
                } if self.policy.teacher_retention_ppm else {}),
            }),
            rng_digest=digest_json({
                "mode": "deterministic-output-lora" if adapter_report is not None else "deterministic-sgd",
                **({"adapter_seed": self.policy.adapter_policy.seed} if adapter_report is not None else {}),
                "batch_count":
                (len(corpus) + chunk_size - 1) // chunk_size,
            }),
            prior_checkpoint_digest=genesis.digest,
        )
        return ShadowTrainingArtifacts(
            dataset=dataset, manifest=manifest, checkpoint=checkpoint,
            candidate_id=candidate_id, checkpoint_path=str(checkpoint_path),
            learning_evidence_path=str(adapter_evidence_path) if adapter_evidence_path is not None else None,
        )


__all__ = ["ShadowNativeTrainingPolicy", "ShadowNativeTrainer"]
