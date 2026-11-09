"""Materialized candidate-only native transformer training from shadow intake.

The trainer clones a pinned champion, consumes only a content-addressed local
UTF-8 training corpus, performs bounded TinyTransformer SGD, and atomically
stores native checkpoint bytes. It never mutates or activates serving weights.
Its output is a real candidate model plus replayable training custody for the
shadow ledger; independent mirror evaluation remains a separate authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
from typing import Callable
from uuid import uuid4

from skeleton.ai.model_runtime.native_llm_runtime import NativeLLMRuntime

from .flgb_training_runtime import (
    DatasetRevision, TrainingCheckpoint, TrainingManifest,
    digest_json, require_digest,
)
from .shadow_idle_training import (
    ShadowLeaseSession, ShadowTrainingArtifacts, ShadowTrainingRejected,
)
from .shadow_weight_intake import ShadowKnowledge
from .shadow_weights import ShadowWeightError

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

    def __post_init__(self) -> None:
        values = (
            ("maximum_corpus_bytes", self.maximum_corpus_bytes, 1, _MAX_TEXT_BYTES),
            ("maximum_lines", self.maximum_lines, 1, 100_000),
            ("maximum_steps", self.maximum_steps, 1, 1_000_000),
            ("lines_per_heartbeat", self.lines_per_heartbeat, 1, 1024),
            ("learning_rate_ppm", self.learning_rate_ppm, 1, 100_000),
        )
        for name, value, minimum, maximum in values:
            if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
                raise ShadowWeightError(f"invalid native shadow training {name}")

    @property
    def digest(self) -> str:
        return digest_json({
            "maximum_corpus_bytes": self.maximum_corpus_bytes,
            "maximum_lines": self.maximum_lines,
            "maximum_steps": self.maximum_steps,
            "lines_per_heartbeat": self.lines_per_heartbeat,
            "learning_rate_ppm": self.learning_rate_ppm,
            "schedule": "cosine-batch",
            "engine": "skeleton.cortex.TinyTransformer",
        })


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
        raw = checkpoint_json.encode("utf-8")
        digest = sha256(raw).hexdigest()
        target = self.directory / (digest + ".native.json")
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

    def __call__(self, session: ShadowLeaseSession) -> ShadowTrainingArtifacts:
        if not isinstance(session, ShadowLeaseSession):
            raise ShadowWeightError("training requires fenced shadow lease session")
        session.require_idle()
        item = session.lease.knowledge
        if self.champion.model_digest != item.base_model_digest:
            raise ShadowTrainingRejected("training-champion-drift")
        self.champion.assert_model_unchanged()
        if (
            any(source.contradiction or not source.allowed_for_training for source in item.sources)
        ):
            raise ShadowTrainingRejected("training-source-rights-unresolved")
        corpus = self._read_corpus(item)
        # The admitted model snapshot is cloned: active weights never receive SGD.
        model = NativeLLMRuntime.restore_json(self.champion.checkpoint_json())
        if model.model_digest != item.base_model_digest:
            raise ShadowWeightError("cloned native baseline has a different digest")
        estimated_steps = sum(max(0, len(model.model._ids(line)) - 1) for line in corpus)
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
                "training": "deterministic-sgd",
                "knowledge_digest": item.digest,
                "champion_digest": item.base_model_digest,
            }),
            max_steps=estimated_steps,
            output_kind="candidate-only",
        )
        genesis = TrainingCheckpoint(
            run_manifest_digest=manifest.digest,
            sequence=0, weights_digest=model.model_digest,
            optimizer_digest=digest_json({"optimizer": "sgd", "steps": 0}),
            rng_digest=digest_json({"mode": "deterministic", "steps": 0}),
        )
        steps = 0
        chunk_size = self.policy.lines_per_heartbeat
        for offset in range(0, len(corpus), chunk_size):
            session.heartbeat()
            batch = corpus[offset:offset + chunk_size]
            steps += model.model.fit(
                batch, lr=self.policy.learning_rate_ppm / 1_000_000,
                schedule="cosine",
            )
        session.require_idle()
        if steps != estimated_steps:
            raise ShadowWeightError("actual native SGD steps differ from admission budget")
        trained = NativeLLMRuntime(model.model, limits=model.limits)
        trained.assert_model_unchanged()
        if trained.model_digest == item.base_model_digest:
            raise ShadowTrainingRejected("candidate-training-no-weight-change")
        checkpoint_json = trained.checkpoint_json()
        checkpoint_path = self._publish_checkpoint(checkpoint_json)
        session.heartbeat()
        checkpoint = TrainingCheckpoint(
            run_manifest_digest=manifest.digest,
            sequence=1,
            weights_digest=trained.model_digest,
            optimizer_digest=digest_json({
                "optimizer": "sgd-no-momentum", "steps": steps,
                "learning_rate_ppm": self.policy.learning_rate_ppm,
            }),
            rng_digest=digest_json({
                "mode": "deterministic-sgd", "batch_count":
                (len(corpus) + chunk_size - 1) // chunk_size,
            }),
            prior_checkpoint_digest=genesis.digest,
        )
        return ShadowTrainingArtifacts(
            dataset=dataset, manifest=manifest, checkpoint=checkpoint,
            candidate_id=candidate_id, checkpoint_path=str(checkpoint_path),
        )


__all__ = ["ShadowNativeTrainingPolicy", "ShadowNativeTrainer"]
