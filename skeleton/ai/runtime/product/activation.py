"""Promotion-bound local model activation for the standalone AI runtime.

Training, Mirror Room, the evaluation firewall, lifecycle qualification and the
canonical model program produce evidence. This module is the narrow deployment
handoff from that evidence to local runtime selection.

It does not allow the learning process to edit process environment or activate
itself. An operator supplies an authorization reference and deployment pins the
exact manifest digest through AI_LOCAL_ACTIVATION_DIGEST. The manifest binds
both candidate and rollback artifacts, so runtime selection is content-addressed
and reversible rather than a loose path switch.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from skeleton.ai.runtime.inference.artifact import (
    LoadedLocalModel,
    LocalModelArtifactError,
    load_local_model_artifact,
)
from skeleton.ai.runtime.inference.local import (
    LocalInferenceEngine,
    LocalModelAdapter,
)
from skeleton.ai.runtime.product.qualification import (
    LearningQualificationBundle,
)
from skeleton.learning.model_program import ModelPromotionReceipt


_SCHEMA = "skeleton.local_model_activation.v2"
_MAX_MANIFEST_BYTES = 64 * 1024


class LocalModelActivationError(RuntimeError):
    """A promoted local model cannot be selected safely."""


def _stable_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise LocalModelActivationError(
            "activation manifest is not deterministic JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _text(value: object, name: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LocalModelActivationError(
            f"{name} must be non-empty text"
        )
    result = value.strip()
    if result != value or len(result) > maximum:
        raise LocalModelActivationError(
            f"{name} must be normalized and bounded"
        )
    return result


def _sha(value: object, name: str) -> str:
    result = _text(value, name, maximum=64).lower()
    if (
        len(result) != 64
        or any(ch not in "0123456789abcdef" for ch in result)
    ):
        raise LocalModelActivationError(
            f"{name} must be lowercase sha256"
        )
    return result


def _bounded_int(
    value: object,
    name: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LocalModelActivationError(
            f"{name} must be an integer"
        )
    if value < minimum or value > maximum:
        raise LocalModelActivationError(
            f"{name} must be in [{minimum}, {maximum}]"
        )
    return value


def _strict_object(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LocalModelActivationError(
                f"activation manifest contains duplicate key: {key}"
            )
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise LocalModelActivationError(
        "activation manifest contains non-finite constant: " + value
    )


def _artifact_path(value: object, name: str) -> Path:
    if isinstance(value, Path):
        raw_value = str(value)
    elif isinstance(value, str):
        raw_value = value
    else:
        raise LocalModelActivationError(
            f"{name} must be text or Path"
        )
    raw = _text(raw_value, name, maximum=4096)
    path = Path(raw).expanduser()
    if path.is_symlink():
        raise LocalModelActivationError(
            f"{name} symlink is forbidden"
        )
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise LocalModelActivationError(
            f"{name} is unavailable"
        ) from exc
    if not resolved.is_file():
        raise LocalModelActivationError(
            f"{name} must be a regular file"
        )
    return resolved


@dataclass(frozen=True, slots=True)
class LocalModelActivationManifest:
    """Exact runtime selection plus rollback identity."""

    candidate_path: str
    candidate_artifact_sha256: str
    candidate_model_id: str
    candidate_model_digest: str
    baseline_path: str
    baseline_artifact_sha256: str
    baseline_model_id: str
    baseline_model_digest: str
    promotion_receipt_digest: str
    lifecycle_promotion_transition_digest: str
    training_receipt_digest: str
    qualification_digest: str
    model_program_bridge_digest: str
    verifier_id: str
    operator_authorization_ref: str
    cache_size: int
    default_seed: int
    rollback_required: bool
    direct_self_modify: bool
    manifest_digest: str

    def __post_init__(self) -> None:
        candidate_path = _artifact_path(
            self.candidate_path,
            "candidate_path",
        )
        baseline_path = _artifact_path(
            self.baseline_path,
            "baseline_path",
        )
        if candidate_path == baseline_path:
            raise LocalModelActivationError(
                "candidate and rollback baseline paths must differ"
            )
        object.__setattr__(
            self,
            "candidate_path",
            str(candidate_path),
        )
        object.__setattr__(
            self,
            "baseline_path",
            str(baseline_path),
        )
        for name in (
            "candidate_artifact_sha256",
            "candidate_model_digest",
            "baseline_artifact_sha256",
            "baseline_model_digest",
            "promotion_receipt_digest",
            "lifecycle_promotion_transition_digest",
            "training_receipt_digest",
            "qualification_digest",
            "model_program_bridge_digest",
        ):
            object.__setattr__(
                self,
                name,
                _sha(getattr(self, name), name),
            )
        object.__setattr__(
            self,
            "candidate_model_id",
            _text(
                self.candidate_model_id,
                "candidate_model_id",
                maximum=512,
            ),
        )
        object.__setattr__(
            self,
            "baseline_model_id",
            _text(
                self.baseline_model_id,
                "baseline_model_id",
                maximum=512,
            ),
        )
        object.__setattr__(
            self,
            "verifier_id",
            _text(self.verifier_id, "verifier_id"),
        )
        object.__setattr__(
            self,
            "operator_authorization_ref",
            _text(
                self.operator_authorization_ref,
                "operator_authorization_ref",
                maximum=2048,
            ),
        )
        object.__setattr__(
            self,
            "cache_size",
            _bounded_int(
                self.cache_size,
                "cache_size",
                minimum=0,
                maximum=16_384,
            ),
        )
        object.__setattr__(
            self,
            "default_seed",
            _bounded_int(
                self.default_seed,
                "default_seed",
                minimum=-(2**63),
                maximum=(2**63) - 1,
            ),
        )
        if self.rollback_required is not True:
            raise LocalModelActivationError(
                "promoted local activation requires rollback identity"
            )
        if self.direct_self_modify is not False:
            raise LocalModelActivationError(
                "local activation cannot authorize direct self-modification"
            )
        if self.candidate_model_digest == self.baseline_model_digest:
            raise LocalModelActivationError(
                "candidate and rollback baseline model identities must differ"
            )

        expected = _digest(self.payload())
        actual = _sha(
            self.manifest_digest,
            "manifest_digest",
        )
        if expected != actual:
            raise LocalModelActivationError(
                "activation manifest digest mismatch"
            )
        object.__setattr__(self, "manifest_digest", actual)

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": _SCHEMA,
            "candidate_path": self.candidate_path,
            "candidate_artifact_sha256": self.candidate_artifact_sha256,
            "candidate_model_id": self.candidate_model_id,
            "candidate_model_digest": self.candidate_model_digest,
            "baseline_path": self.baseline_path,
            "baseline_artifact_sha256": self.baseline_artifact_sha256,
            "baseline_model_id": self.baseline_model_id,
            "baseline_model_digest": self.baseline_model_digest,
            "promotion_receipt_digest": self.promotion_receipt_digest,
            "lifecycle_promotion_transition_digest": (
                self.lifecycle_promotion_transition_digest
            ),
            "training_receipt_digest": self.training_receipt_digest,
            "qualification_digest": self.qualification_digest,
            "model_program_bridge_digest": self.model_program_bridge_digest,
            "verifier_id": self.verifier_id,
            "operator_authorization_ref": self.operator_authorization_ref,
            "cache_size": self.cache_size,
            "default_seed": self.default_seed,
            "rollback_required": True,
            "direct_self_modify": False,
        }

    def as_dict(self) -> dict[str, object]:
        return {
            **self.payload(),
            "manifest_digest": self.manifest_digest,
        }

    def rollback_target(self) -> dict[str, str]:
        return {
            "path": self.baseline_path,
            "artifact_sha256": self.baseline_artifact_sha256,
            "model_id": self.baseline_model_id,
            "model_digest": self.baseline_model_digest,
        }


@dataclass(frozen=True, slots=True)
class LoadedLocalModelActivation:
    manifest: LocalModelActivationManifest
    candidate: LoadedLocalModel
    baseline: LoadedLocalModel


def _load_exact_artifact(
    path: str,
    *,
    artifact_sha256: str,
    model_id: str,
    model_digest: str,
    role: str,
) -> LoadedLocalModel:
    try:
        loaded = load_local_model_artifact(path)
    except LocalModelArtifactError as exc:
        raise LocalModelActivationError(
            f"{role} local model artifact is invalid"
        ) from exc
    if loaded.receipt.artifact_sha256 != artifact_sha256:
        raise LocalModelActivationError(
            f"{role} artifact identity drift"
        )
    if loaded.receipt.model_id != model_id:
        raise LocalModelActivationError(
            f"{role} model id drift"
        )
    if loaded.receipt.model_digest != model_digest:
        raise LocalModelActivationError(
            f"{role} model digest drift"
        )
    return loaded


def build_local_model_activation_manifest(
    *,
    candidate_path: str | Path,
    baseline_path: str | Path,
    promotion_receipt: ModelPromotionReceipt,
    qualification: LearningQualificationBundle,
    lifecycle_promotion_transition: object,
    model_program_bridge_digest: str,
    operator_authorization_ref: str,
    cache_size: int = 128,
    default_seed: int = 0,
) -> LocalModelActivationManifest:
    """Bind independently promoted evidence to exact runtime/rollback bytes."""

    if not isinstance(promotion_receipt, ModelPromotionReceipt):
        raise TypeError(
            "promotion_receipt must be ModelPromotionReceipt"
        )
    if not isinstance(qualification, LearningQualificationBundle):
        raise TypeError(
            "qualification must be LearningQualificationBundle"
        )
    # Lazy import avoids an activation<->lifecycle module import cycle while
    # still requiring the actual typed transition contract.
    from .lifecycle import (
        ModelLifecycleState,
        ModelLifecycleTransitionReceipt,
    )

    if not isinstance(
        lifecycle_promotion_transition,
        ModelLifecycleTransitionReceipt,
    ):
        raise TypeError(
            "lifecycle_promotion_transition must be "
            "ModelLifecycleTransitionReceipt"
        )
    if (
        lifecycle_promotion_transition.from_state
        is not ModelLifecycleState.VALIDATED
        or lifecycle_promotion_transition.to_state
        is not ModelLifecycleState.PROMOTED
    ):
        raise LocalModelActivationError(
            "activation requires exact validated-to-promoted lifecycle transition"
        )

    candidate_resolved = _artifact_path(
        candidate_path,
        "candidate_path",
    )
    baseline_resolved = _artifact_path(
        baseline_path,
        "baseline_path",
    )
    if candidate_resolved == baseline_resolved:
        raise LocalModelActivationError(
            "candidate and rollback baseline paths must differ"
        )
    candidate = load_local_model_artifact(candidate_resolved)
    baseline = load_local_model_artifact(baseline_resolved)

    if (
        promotion_receipt.model_id != candidate.receipt.model_id
        or promotion_receipt.model_digest
        != candidate.receipt.model_digest
    ):
        raise LocalModelActivationError(
            "promotion receipt does not bind candidate artifact"
        )
    if (
        qualification.candidate_model_digest
        != candidate.receipt.model_digest
        or qualification.candidate_artifact_sha256
        != candidate.receipt.artifact_sha256
    ):
        raise LocalModelActivationError(
            "qualification does not bind candidate artifact"
        )
    if (
        qualification.baseline_model_digest
        != baseline.receipt.model_digest
    ):
        raise LocalModelActivationError(
            "qualification does not bind rollback baseline"
        )

    lifecycle_transition = lifecycle_promotion_transition
    if (
        lifecycle_transition.model_id != candidate.receipt.model_id
        or lifecycle_transition.model_digest
        != candidate.receipt.model_digest
        or lifecycle_transition.artifact_digest
        != candidate.receipt.artifact_sha256
    ):
        raise LocalModelActivationError(
            "lifecycle promotion transition does not bind candidate artifact"
        )
    if lifecycle_transition.authority_id != promotion_receipt.verifier_id:
        raise LocalModelActivationError(
            "lifecycle promotion authority differs from promotion receipt"
        )
    promotion_ref = (
        "model-promotion-receipt-sha256:" + promotion_receipt.digest
    )
    if promotion_ref not in lifecycle_transition.evidence_refs:
        raise LocalModelActivationError(
            "lifecycle promotion transition lacks model promotion receipt"
        )
    lifecycle_transition_digest = _sha(
        lifecycle_transition.digest,
        "lifecycle_promotion_transition_digest",
    )

    bridge_digest = _sha(
        model_program_bridge_digest,
        "model_program_bridge_digest",
    )
    required_refs = {
        *qualification.lifecycle_evidence_refs,
        "learning-qualification-sha256:"
        + qualification.qualification_digest,
        "model-program-bridge-sha256:" + bridge_digest,
    }
    if not required_refs.issubset(
        set(promotion_receipt.evaluation_refs)
    ):
        raise LocalModelActivationError(
            "promotion receipt lacks qualification/bridge evidence"
        )

    payload: dict[str, object] = {
        "schema_version": _SCHEMA,
        "candidate_path": str(candidate_resolved),
        "candidate_artifact_sha256": candidate.receipt.artifact_sha256,
        "candidate_model_id": candidate.receipt.model_id,
        "candidate_model_digest": candidate.receipt.model_digest,
        "baseline_path": str(baseline_resolved),
        "baseline_artifact_sha256": baseline.receipt.artifact_sha256,
        "baseline_model_id": baseline.receipt.model_id,
        "baseline_model_digest": baseline.receipt.model_digest,
        "promotion_receipt_digest": promotion_receipt.digest,
        "lifecycle_promotion_transition_digest": (
            lifecycle_transition_digest
        ),
        "training_receipt_digest": (
            promotion_receipt.training_receipt_digest
        ),
        "qualification_digest": qualification.qualification_digest,
        "model_program_bridge_digest": bridge_digest,
        "verifier_id": promotion_receipt.verifier_id,
        "operator_authorization_ref": _text(
            operator_authorization_ref,
            "operator_authorization_ref",
            maximum=2048,
        ),
        "cache_size": _bounded_int(
            cache_size,
            "cache_size",
            minimum=0,
            maximum=16_384,
        ),
        "default_seed": _bounded_int(
            default_seed,
            "default_seed",
            minimum=-(2**63),
            maximum=(2**63) - 1,
        ),
        "rollback_required": True,
        "direct_self_modify": False,
    }
    return LocalModelActivationManifest(
        **{
            key: value
            for key, value in payload.items()
            if key != "schema_version"
        },
        manifest_digest=_digest(payload),
    )


def write_local_model_activation_manifest(
    manifest: LocalModelActivationManifest,
    path: str | Path,
) -> Path:
    """Atomically materialize one already-authorized activation manifest."""

    if not isinstance(manifest, LocalModelActivationManifest):
        raise TypeError(
            "manifest must be LocalModelActivationManifest"
        )
    raw_path = _text(str(path), "activation manifest path", maximum=4096)
    destination = Path(raw_path).expanduser()
    parent = destination.parent.resolve()
    if not parent.exists() or not parent.is_dir():
        raise LocalModelActivationError(
            "activation manifest parent directory does not exist"
        )
    if destination.is_symlink():
        raise LocalModelActivationError(
            "activation manifest symlink is forbidden"
        )

    raw = (
        _stable_json(manifest.as_dict()) + "\n"
    ).encode("utf-8")
    if len(raw) > _MAX_MANIFEST_BYTES:
        raise LocalModelActivationError(
            "activation manifest exceeds byte limit"
        )

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=destination.name + ".",
            suffix=".tmp",
            dir=str(parent),
            delete=False,
        ) as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
            temp_path = Path(handle.name)
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, destination)
        temp_path = None
        try:
            directory_fd = os.open(str(parent), os.O_RDONLY)
        except OSError:
            directory_fd = None
        if directory_fd is not None:
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    except OSError as exc:
        raise LocalModelActivationError(
            "activation manifest could not be written atomically"
        ) from exc
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
    return destination.resolve(strict=True)


def load_local_model_activation_manifest(
    path: str | Path,
    *,
    expected_manifest_digest: str,
) -> LoadedLocalModelActivation:
    """Load, digest-pin and authenticate candidate plus rollback baseline."""

    source = Path(
        _text(str(path), "activation manifest path", maximum=4096)
    ).expanduser()
    if source.is_symlink():
        raise LocalModelActivationError(
            "activation manifest symlink is forbidden"
        )
    try:
        resolved = source.resolve(strict=True)
        stat = resolved.stat()
        raw = resolved.read_bytes()
    except OSError as exc:
        raise LocalModelActivationError(
            "activation manifest is unavailable"
        ) from exc
    if not resolved.is_file():
        raise LocalModelActivationError(
            "activation manifest must be a regular file"
        )
    if (
        stat.st_size < 1
        or stat.st_size > _MAX_MANIFEST_BYTES
        or len(raw) != stat.st_size
    ):
        raise LocalModelActivationError(
            "activation manifest byte bounds/identity failed"
        )

    expected = _sha(
        expected_manifest_digest,
        "expected_manifest_digest",
    )
    try:
        payload = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise LocalModelActivationError(
            "activation manifest must be UTF-8 JSON"
        ) from exc
    except json.JSONDecodeError as exc:
        raise LocalModelActivationError(
            "activation manifest contains invalid JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise LocalModelActivationError(
            "activation manifest root must be an object"
        )
    if payload.get("schema_version") != _SCHEMA:
        raise LocalModelActivationError(
            "unsupported activation manifest schema"
        )
    if payload.get("manifest_digest") != expected:
        raise LocalModelActivationError(
            "deployment-pinned activation digest mismatch"
        )

    allowed = {
        "schema_version",
        "candidate_path",
        "candidate_artifact_sha256",
        "candidate_model_id",
        "candidate_model_digest",
        "baseline_path",
        "baseline_artifact_sha256",
        "baseline_model_id",
        "baseline_model_digest",
        "promotion_receipt_digest",
        "lifecycle_promotion_transition_digest",
        "training_receipt_digest",
        "qualification_digest",
        "model_program_bridge_digest",
        "verifier_id",
        "operator_authorization_ref",
        "cache_size",
        "default_seed",
        "rollback_required",
        "direct_self_modify",
        "manifest_digest",
    }
    if set(payload) != allowed:
        raise LocalModelActivationError(
            "activation manifest field set mismatch"
        )
    manifest = LocalModelActivationManifest(
        candidate_path=payload["candidate_path"],
        candidate_artifact_sha256=payload[
            "candidate_artifact_sha256"
        ],
        candidate_model_id=payload["candidate_model_id"],
        candidate_model_digest=payload["candidate_model_digest"],
        baseline_path=payload["baseline_path"],
        baseline_artifact_sha256=payload[
            "baseline_artifact_sha256"
        ],
        baseline_model_id=payload["baseline_model_id"],
        baseline_model_digest=payload["baseline_model_digest"],
        promotion_receipt_digest=payload[
            "promotion_receipt_digest"
        ],
        lifecycle_promotion_transition_digest=payload[
            "lifecycle_promotion_transition_digest"
        ],
        training_receipt_digest=payload[
            "training_receipt_digest"
        ],
        qualification_digest=payload["qualification_digest"],
        model_program_bridge_digest=payload[
            "model_program_bridge_digest"
        ],
        verifier_id=payload["verifier_id"],
        operator_authorization_ref=payload[
            "operator_authorization_ref"
        ],
        cache_size=payload["cache_size"],
        default_seed=payload["default_seed"],
        rollback_required=payload["rollback_required"],
        direct_self_modify=payload["direct_self_modify"],
        manifest_digest=payload["manifest_digest"],
    )
    if manifest.manifest_digest != expected:
        raise LocalModelActivationError(
            "activation manifest content digest is not deployment-pinned"
        )

    candidate = _load_exact_artifact(
        manifest.candidate_path,
        artifact_sha256=manifest.candidate_artifact_sha256,
        model_id=manifest.candidate_model_id,
        model_digest=manifest.candidate_model_digest,
        role="candidate",
    )
    baseline = _load_exact_artifact(
        manifest.baseline_path,
        artifact_sha256=manifest.baseline_artifact_sha256,
        model_id=manifest.baseline_model_id,
        model_digest=manifest.baseline_model_digest,
        role="rollback baseline",
    )
    return LoadedLocalModelActivation(
        manifest=manifest,
        candidate=candidate,
        baseline=baseline,
    )


def local_model_adapter_from_activation_manifest(
    path: str | Path,
    *,
    expected_manifest_digest: str,
    target: str = "candidate",
) -> LocalModelAdapter:
    """Build a digest-pinned candidate or rollback adapter.

    Target selection is operator-controlled. The activation manifest itself
    authenticates both artifacts, so rollback never depends on a mutable loose
    path and does not grant the learning process production mutation authority.
    """

    loaded = load_local_model_activation_manifest(
        path,
        expected_manifest_digest=expected_manifest_digest,
    )
    selected_target = _text(target, "activation target", maximum=32).lower()
    if selected_target not in {"candidate", "rollback"}:
        raise LocalModelActivationError(
            "activation target must be candidate or rollback"
        )
    selected = (
        loaded.candidate
        if selected_target == "candidate"
        else loaded.baseline
    )
    adapter = LocalModelAdapter(
        LocalInferenceEngine(
            selected.model,  # type: ignore[arg-type]
            cache_size=loaded.manifest.cache_size,
        ),
        default_seed=loaded.manifest.default_seed,
    )
    adapter.artifact_receipt = selected.receipt
    adapter.activation_manifest = loaded.manifest
    adapter.activation_target = selected_target
    return adapter


__all__ = [
    "LoadedLocalModelActivation",
    "LocalModelActivationError",
    "LocalModelActivationManifest",
    "build_local_model_activation_manifest",
    "load_local_model_activation_manifest",
    "local_model_adapter_from_activation_manifest",
    "write_local_model_activation_manifest",
]
