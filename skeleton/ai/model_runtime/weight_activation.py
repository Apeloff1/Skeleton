"""Native transformer activation for independently promoted shadow-weight candidates.

A promotion installs an already materialized NativeLLMRuntime. It never
generates weights, assumes a hash proves improvement, or mutates a live model
object in place. New requests can acquire the newly published runtime while
in-flight sessions retain their prior instance. The ledger provides a durable,
compare-and-swap active-model pointer and an auditable rollback receipt.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING

from skeleton.ai.training.flgb_training_runtime import digest_json, require_digest
from skeleton.ai.training.promotion_lifecycle import RuntimeAdmission, RollbackProof
from skeleton.ai.training.shadow_weight_ledger import ShadowWeightLedger
from skeleton.ai.training.shadow_weights import ShadowPromotionPermit, ShadowWeightError

if TYPE_CHECKING:
    from .native_llm_runtime import NativeLLMRuntime


@dataclass(frozen=True, slots=True)
class NativeActivationReceipt:
    candidate_id: str
    permit_digest: str
    prior_model_digest: str
    admitted_model_digest: str
    admission_digest: str
    rollback_proof_digest: str
    checkpoint_content_digest: str

    @property
    def digest(self) -> str:
        return digest_json({
            "candidate_id": self.candidate_id,
            "permit_digest": self.permit_digest,
            "prior_model_digest": self.prior_model_digest,
            "admitted_model_digest": self.admitted_model_digest,
            "admission_digest": self.admission_digest,
            "rollback_proof_digest": self.rollback_proof_digest,
            "checkpoint_content_digest": self.checkpoint_content_digest,
        })


@dataclass(frozen=True, slots=True)
class NativeRollbackReceipt:
    candidate_id: str
    activation_digest: str
    removed_model_digest: str
    restored_model_digest: str
    rollback_proof_digest: str

    @property
    def digest(self) -> str:
        return digest_json({
            "candidate_id": self.candidate_id,
            "activation_digest": self.activation_digest,
            "removed_model_digest": self.removed_model_digest,
            "restored_model_digest": self.restored_model_digest,
            "rollback_proof_digest": self.rollback_proof_digest,
        })


class NativeWeightDeployment:
    """Serializes local runtime pointer swaps and durable ledger mutations.

    The caller owns model construction and independent benchmarking. Passing a
    pre-loaded runtime does not bypass the source, evaluation, training-rights,
    rollback or authority gates recorded in the promotion permit.
    """

    def __init__(
        self,
        runtime: "NativeLLMRuntime",
        ledger: ShadowWeightLedger,
        *,
        checkpoint_directory: str | Path,
    ) -> None:
        from .native_llm_runtime import NativeLLMRuntime

        if not isinstance(runtime, NativeLLMRuntime):
            raise ShadowWeightError("initial serving model must be a native LLM runtime")
        if not isinstance(ledger, ShadowWeightLedger):
            raise ShadowWeightError("native deployment requires shadow weight ledger")
        if runtime.model_digest != ledger.active_model_digest:
            raise ShadowWeightError("initial native runtime does not match active-model ledger")
        self._runtime = runtime
        self._ledger = ledger
        self._lock = RLock()
        self._checkpoints = Path(checkpoint_directory)
        self._checkpoints.mkdir(parents=True, exist_ok=True)
        self._prior_runtimes: dict[str, NativeLLMRuntime] = {}
        self._activation_receipts: dict[str, NativeActivationReceipt] = {}

    @property
    def runtime(self) -> "NativeLLMRuntime":
        """Acquire the active runtime reference; in-flight sessions keep theirs."""
        with self._lock:
            if self._runtime.model_digest != self._ledger.active_model_digest:
                raise ShadowWeightError("serving runtime drifted from persistent active weights")
            self._runtime.assert_model_unchanged()
            return self._runtime

    @property
    def active_model_digest(self) -> str:
        return self.runtime.model_digest

    def _checkpoint(self, candidate_digest: str, runtime: "NativeLLMRuntime") -> str:
        """Write an immutable native checkpoint to a durable private path.

        Only a SHA-256-addressed basename is used: user-supplied candidate IDs
        cannot escape the checkpoint directory. Crash-safe replacement never
        truncates a previously committed checkpoint.
        """
        require_digest(candidate_digest, "candidate_digest")
        runtime.assert_model_unchanged()
        raw = runtime.checkpoint_json().encode("utf-8")
        content_digest = sha256(raw).hexdigest()
        target = self._checkpoints / (candidate_digest + ".rollback.json")
        if target.exists():
            if sha256(target.read_bytes()).hexdigest() != content_digest:
                raise ShadowWeightError("existing rollback checkpoint has different bytes")
            return content_digest
        tmp = self._checkpoints / (candidate_digest + f".{os.getpid()}.tmp")
        try:
            with tmp.open("xb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, target)
            if os.name == "posix":
                fd = os.open(self._checkpoints, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        finally:
            tmp.unlink(missing_ok=True)
        return content_digest

    @staticmethod
    def _admission(
        permit: ShadowPromotionPermit,
        admission: RuntimeAdmission,
        rollback: RollbackProof,
    ) -> None:
        if not isinstance(admission, RuntimeAdmission) or not isinstance(rollback, RollbackProof):
            raise ShadowWeightError("independent admission and rollback proofs required")
        if admission.candidate_digest != permit.candidate_digest:
            raise ShadowWeightError("native admission candidate identity mismatch")
        if admission.admitted_model_digest != permit.weights_digest:
            raise ShadowWeightError("native admission target weights mismatch")
        if admission.prior_model_digest != permit.base_model_digest:
            raise ShadowWeightError("native admission baseline mismatch")
        if admission.checkpoint_digest != permit.rollback_checkpoint_digest:
            raise ShadowWeightError("promotion rollback checkpoint mismatch")
        if admission.admission_authority != permit.admission_authority:
            raise ShadowWeightError("admission performed by a different authority")
        if rollback.admission_digest != admission.digest:
            raise ShadowWeightError("rollback proof not bound to this admission")
        if rollback.checkpoint_digest != admission.checkpoint_digest:
            raise ShadowWeightError("rollback proof checkpoint mismatch")
        if rollback.restored_model_digest != admission.prior_model_digest:
            raise ShadowWeightError("rollback cannot restore this baseline")
        if not rollback.verified or rollback.executed:
            raise ShadowWeightError("fresh admission requires a ready, unexecuted rollback proof")
        if rollback.verifier_id in {permit.mirror_verifier, permit.admission_authority}:
            raise ShadowWeightError("rollback verifier must be independent")

    def activate(
        self,
        candidate_id: str,
        loaded_runtime: "NativeLLMRuntime",
        *,
        admission: RuntimeAdmission,
        rollback: RollbackProof,
        expected_revision: int,
    ) -> NativeActivationReceipt:
        from .native_llm_runtime import NativeLLMRuntime

        if not isinstance(loaded_runtime, NativeLLMRuntime):
            raise ShadowWeightError("candidate weights must be materialized in native runtime")
        with self._lock:
            current = self.runtime
            snapshot = self._ledger.snapshot(candidate_id)
            if snapshot.state != "eligible" or snapshot.permit is None:
                raise ShadowWeightError("shadow candidate is not eligible for native activation")
            permit = snapshot.permit
            if candidate_id in self._activation_receipts:
                raise ShadowWeightError("duplicate native activation")
            if snapshot.revision != expected_revision:
                raise ShadowWeightError("stale native admission revision")
            self._admission(permit, admission, rollback)
            current.assert_model_unchanged()
            loaded_runtime.assert_model_unchanged()
            if current.model_digest != permit.base_model_digest:
                raise ShadowWeightError("candidate trained from another live model")
            if loaded_runtime.model_digest != permit.weights_digest:
                raise ShadowWeightError("loaded tensor state differs from candidate weights")
            if loaded_runtime.model_identity.weights_digest != permit.weights_digest:
                raise ShadowWeightError("native model identity does not bind candidate weights")

            checkpoint_digest = self._checkpoint(permit.candidate_digest, current)
            if checkpoint_digest != permit.rollback_checkpoint_digest:
                raise ShadowWeightError("rollback checkpoint content does not match approval")
            receipt = NativeActivationReceipt(
                candidate_id=candidate_id,
                permit_digest=permit.digest,
                prior_model_digest=current.model_digest,
                admitted_model_digest=loaded_runtime.model_digest,
                admission_digest=admission.digest,
                rollback_proof_digest=rollback.digest,
                checkpoint_content_digest=checkpoint_digest,
            )
            # The durable CAS runs first. Publishing a reference is an in-memory
            # assignment that follows only after the transaction has committed.
            self._ledger.commit_activation(
                candidate_id,
                permit_digest=permit.digest,
                admitted_model_digest=loaded_runtime.model_digest,
                activation_receipt_digest=receipt.digest,
                expected_revision=expected_revision,
            )
            self._prior_runtimes[candidate_id] = current
            self._activation_receipts[candidate_id] = receipt
            self._runtime = loaded_runtime
            return receipt

    def rollback(
        self,
        candidate_id: str,
        *,
        proof: RollbackProof,
        expected_revision: int,
    ) -> NativeRollbackReceipt:
        if not isinstance(proof, RollbackProof) or not proof.verified or not proof.executed:
            raise ShadowWeightError("rollback requires independent executed rollback proof")
        with self._lock:
            active = self.runtime
            original = self._prior_runtimes.get(candidate_id)
            activation = self._activation_receipts.get(candidate_id)
            snapshot = self._ledger.snapshot(candidate_id)
            if original is None or activation is None or snapshot.state != "active":
                raise ShadowWeightError("no resident rollback runtime for active candidate")
            if snapshot.revision != expected_revision:
                raise ShadowWeightError("stale rollback revision")
            if proof.admission_digest != activation.admission_digest:
                raise ShadowWeightError("executed rollback proof does not match admission")
            if proof.checkpoint_digest != activation.checkpoint_content_digest:
                raise ShadowWeightError("executed rollback proof does not match checkpoint")
            if proof.verifier_id == snapshot.permit.admission_authority or proof.verifier_id == snapshot.permit.mirror_verifier:
                raise ShadowWeightError("rollback verifier is not independent")
            original.assert_model_unchanged()
            if original.model_digest != activation.prior_model_digest:
                raise ShadowWeightError("resident rollback model mutated")
            if proof.restored_model_digest != original.model_digest:
                raise ShadowWeightError("rollback proof restored different model weights")
            receipt = NativeRollbackReceipt(
                candidate_id=candidate_id,
                activation_digest=activation.digest,
                removed_model_digest=active.model_digest,
                restored_model_digest=original.model_digest,
                rollback_proof_digest=proof.digest,
            )
            self._ledger.commit_rollback(
                candidate_id,
                restored_model_digest=original.model_digest,
                rollback_receipt_digest=receipt.digest,
                expected_revision=expected_revision,
            )
            self._runtime = original
            del self._prior_runtimes[candidate_id]
            del self._activation_receipts[candidate_id]
            return receipt


__all__ = [
    "NativeActivationReceipt", "NativeRollbackReceipt", "NativeWeightDeployment",
]
