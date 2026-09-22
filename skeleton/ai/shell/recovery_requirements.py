"""Signed durable manifests for required AI recovery finalizations.

DurableRecoveryHealthGuard can verify a supplied set of finalization IDs, but a
process-local tuple is not itself an authority. A restarted or misconfigured
worker could accidentally omit the one finalization that needs review.

This module makes the required proof set durable:
- one signed manifest per monotonically increasing generation;
- predecessor digest chaining;
- CAS-pinned current head;
- immutable generation history;
- explicit change IDs and reasons for every rollover;
- optional runtime-trust and release-evidence bindings.

The manifest authorizes only which recovery proofs must be checked. It does not
authorize process execution.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
import time
from typing import Callable, Iterable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend


_SCOPE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")


def _opaque_digest(
    name: str,
    value: str,
    *,
    optional: bool = False,
) -> str:
    if optional and not value:
        return ""
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"{name} must be 64 characters")
    return value.lower()


def _scope(value: str) -> str:
    if not isinstance(value, str) or not _SCOPE_RE.fullmatch(value):
        raise ValueError("invalid recovery requirement scope")
    return value


def _ids(
    values: Iterable[str],
    *,
    maximum: int,
) -> tuple[str, ...]:
    items = tuple(values)
    if len(items) > maximum:
        raise ValueError("recovery requirement finalization bound exceeded")
    if any(
        not isinstance(item, str)
        or not item
        or len(item) > 256
        for item in items
    ):
        raise ValueError("invalid required finalization_id")
    if len(items) != len(set(items)):
        raise ValueError("duplicate required finalization_id")
    return tuple(sorted(items))


@dataclass(frozen=True)
class DurableRecoveryRequirementManifest:
    schema_version: int
    scope: str
    generation: int
    finalization_ids: tuple[str, ...]
    previous_manifest_digest: str = ""
    runtime_trust_digest: str = ""
    release_evidence_digest: str = ""
    change_id: str = ""
    reason: str = ""
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported recovery requirement schema")
        object.__setattr__(self, "scope", _scope(self.scope))
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation <= 0
        ):
            raise ValueError("recovery requirement generation must be positive")
        object.__setattr__(
            self,
            "finalization_ids",
            _ids(self.finalization_ids, maximum=4096),
        )
        object.__setattr__(
            self,
            "previous_manifest_digest",
            _opaque_digest(
                "previous_manifest_digest",
                self.previous_manifest_digest,
                optional=True,
            ),
        )
        object.__setattr__(
            self,
            "runtime_trust_digest",
            _opaque_digest(
                "runtime_trust_digest",
                self.runtime_trust_digest,
                optional=True,
            ),
        )
        object.__setattr__(
            self,
            "release_evidence_digest",
            _opaque_digest(
                "release_evidence_digest",
                self.release_evidence_digest,
                optional=True,
            ),
        )
        if self.generation == 1 and self.previous_manifest_digest:
            raise ValueError("initial recovery requirement may not have predecessor")
        if self.generation > 1 and not self.previous_manifest_digest:
            raise ValueError("recovery requirement rollover needs predecessor")
        if self.generation == 1 and self.change_id:
            raise ValueError("initial recovery requirement may not have change_id")
        if self.generation > 1 and (
            not self.change_id or len(self.change_id) > 256
        ):
            raise ValueError("recovery requirement rollover needs change_id")
        if len(self.reason) > 2048:
            raise ValueError("recovery requirement reason too long")
        if self.generation > 1 and not self.reason:
            raise ValueError("recovery requirement rollover needs reason")
        if (
            isinstance(self.created_at, bool)
            or not isinstance(self.created_at, (int, float))
            or not math.isfinite(float(self.created_at))
            or float(self.created_at) < 0.0
        ):
            raise ValueError("recovery requirement created_at must be finite and non-negative")
        object.__setattr__(self, "created_at", float(self.created_at))

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "scope": self.scope,
            "generation": self.generation,
            "finalization_ids": list(self.finalization_ids),
            "previous_manifest_digest": self.previous_manifest_digest,
            "runtime_trust_digest": self.runtime_trust_digest,
            "release_evidence_digest": self.release_evidence_digest,
            "change_id": self.change_id,
            "reason": self.reason,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class SignedDurableRecoveryRequirementManifest:
    manifest: DurableRecoveryRequirementManifest
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if self.signature.artifact_type != "ai-durable-recovery-requirements":
            raise ValueError("invalid recovery requirement artifact type")
        if self.signature.artifact_digest != self.manifest.digest:
            raise ValueError("recovery requirement signature digest mismatch")

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest": self.manifest.to_dict(),
            "manifest_digest": self.manifest.digest,
            "signature": self.signature.to_dict(),
        }


@dataclass(frozen=True)
class DurableRecoveryRequirementVerification:
    ok: bool
    scope: str
    generation: int
    manifest_digest: str
    finalization_ids: tuple[str, ...]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.ok, bool):
            raise ValueError("ok must be bool")
        object.__setattr__(self, "scope", _scope(self.scope))
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation < 0
        ):
            raise ValueError("generation must be non-negative")
        if self.manifest_digest:
            object.__setattr__(
                self,
                "manifest_digest",
                _opaque_digest("manifest_digest", self.manifest_digest),
            )
        object.__setattr__(
            self,
            "finalization_ids",
            _ids(self.finalization_ids, maximum=4096),
        )
        object.__setattr__(self, "reasons", tuple(self.reasons))

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "scope": self.scope,
            "generation": self.generation,
            "manifest_digest": self.manifest_digest,
            "finalization_ids": list(self.finalization_ids),
            "reasons": list(self.reasons),
        }


class DurableRecoveryRequirementConflict(RuntimeError):
    pass


class DurableRecoveryRequirementStore:
    """CAS-backed signed required-finalization manifest with immutable history."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        signer: ArtifactSigner,
        *,
        namespace: str = "shell-ai-durable-recovery-requirements",
        max_finalizations: int = 4096,
        max_generations: int = 10_000,
        max_retries: int = 16,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(backend, VersionedStateBackend):
            raise TypeError("backend must satisfy VersionedStateBackend")
        if not isinstance(signer, ArtifactSigner):
            raise TypeError("signer must be ArtifactSigner")
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid recovery requirement namespace")
        for name, value in (
            ("max_finalizations", max_finalizations),
            ("max_generations", max_generations),
            ("max_retries", max_retries),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value <= 0
            ):
                raise ValueError(f"{name} must be positive integer")
        if max_finalizations > 4096:
            raise ValueError("max_finalizations exceeds hard bound")
        if max_retries > 64:
            raise ValueError("max_retries exceeds hard bound")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self.backend = backend
        self.signer = signer
        self.namespace = namespace
        self.max_finalizations = max_finalizations
        self.max_generations = max_generations
        self.max_retries = max_retries
        self._clock = clock

    @classmethod
    def _head_key(cls, scope: str) -> str:
        return f"head:{_scope(scope)}"

    @classmethod
    def _history_key(cls, scope: str, generation: int) -> str:
        scope = _scope(scope)
        if (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation <= 0
        ):
            raise ValueError("generation must be positive")
        return f"history:{scope}:{generation:020d}"

    @staticmethod
    def _signature(raw: dict[str, object]) -> SignedArtifact:
        return SignedArtifact(
            str(raw["artifact_type"]),
            str(raw["artifact_digest"]),
            str(raw["key_id"]),
            float(raw["issued_at"]),
            dict(raw.get("metadata", {})),
            str(raw["signature"]),
        )

    @classmethod
    def _decode(
        cls,
        value: object,
    ) -> SignedDurableRecoveryRequirementManifest:
        if not isinstance(value, dict):
            raise DurableRecoveryRequirementConflict(
                "recovery requirement record must be mapping"
            )
        raw_manifest = value.get("manifest")
        raw_signature = value.get("signature")
        if not isinstance(raw_manifest, dict) or not isinstance(raw_signature, dict):
            raise DurableRecoveryRequirementConflict(
                "recovery requirement record shape invalid"
            )
        manifest = DurableRecoveryRequirementManifest(
            int(raw_manifest["schema_version"]),
            str(raw_manifest["scope"]),
            int(raw_manifest["generation"]),
            tuple(str(item) for item in raw_manifest.get("finalization_ids", ())),
            str(raw_manifest.get("previous_manifest_digest", "")),
            str(raw_manifest.get("runtime_trust_digest", "")),
            str(raw_manifest.get("release_evidence_digest", "")),
            str(raw_manifest.get("change_id", "")),
            str(raw_manifest.get("reason", "")),
            float(raw_manifest["created_at"]),
        )
        return SignedDurableRecoveryRequirementManifest(
            manifest,
            cls._signature(dict(raw_signature)),
        )

    def _sign(
        self,
        manifest: DurableRecoveryRequirementManifest,
    ) -> SignedDurableRecoveryRequirementManifest:
        signature = self.signer.sign(
            "ai-durable-recovery-requirements",
            manifest.digest,
            metadata={
                "scope": manifest.scope,
                "generation": str(manifest.generation),
            },
        )
        return SignedDurableRecoveryRequirementManifest(
            manifest,
            signature,
        )

    def _verify_item(
        self,
        item: SignedDurableRecoveryRequirementManifest,
    ) -> None:
        manifest = item.manifest
        if item.signature.artifact_type != "ai-durable-recovery-requirements":
            raise DurableRecoveryRequirementConflict(
                "recovery requirement artifact type mismatch"
            )
        if item.signature.artifact_digest != manifest.digest:
            raise DurableRecoveryRequirementConflict(
                "recovery requirement artifact digest mismatch"
            )
        if item.signature.metadata.get("scope") != manifest.scope:
            raise DurableRecoveryRequirementConflict(
                "recovery requirement signature scope mismatch"
            )
        if item.signature.metadata.get("generation") != str(manifest.generation):
            raise DurableRecoveryRequirementConflict(
                "recovery requirement signature generation mismatch"
            )
        try:
            self.signer.verify(item.signature)
        except ArtifactSignatureError as exc:
            raise DurableRecoveryRequirementConflict(
                "recovery requirement signature verification failed"
            ) from exc

    def current(
        self,
        scope: str,
    ) -> tuple[int, SignedDurableRecoveryRequirementManifest] | None:
        scope = _scope(scope)
        record = self.backend.get(
            self.namespace,
            self._head_key(scope),
        )
        if record is None:
            return None
        item = self._decode(record.value)
        self._verify_item(item)
        if item.manifest.scope != scope:
            raise DurableRecoveryRequirementConflict(
                "recovery requirement head scope mismatch"
            )
        if item.manifest.generation != record.revision:
            raise DurableRecoveryRequirementConflict(
                "recovery requirement head generation/revision mismatch"
            )
        return record.revision, item

    def history_item(
        self,
        scope: str,
        generation: int,
    ) -> SignedDurableRecoveryRequirementManifest:
        record = self.backend.get(
            self.namespace,
            self._history_key(scope, generation),
        )
        if record is None:
            raise KeyError((scope, generation))
        item = self._decode(record.value)
        self._verify_item(item)
        if (
            item.manifest.scope != scope
            or item.manifest.generation != generation
        ):
            raise DurableRecoveryRequirementConflict(
                "recovery requirement history identity mismatch"
            )
        return item

    def _persist_generation(
        self,
        item: SignedDurableRecoveryRequirementManifest,
    ) -> SignedDurableRecoveryRequirementManifest:
        key = self._history_key(
            item.manifest.scope,
            item.manifest.generation,
        )
        try:
            self.backend.put_if_absent(
                self.namespace,
                key,
                item.to_dict(),
            )
            return item
        except DistributedStateConflict:
            existing = self.history_item(
                item.manifest.scope,
                item.manifest.generation,
            )
            left = item.manifest
            right = existing.manifest
            same_authority = (
                left.scope == right.scope
                and left.generation == right.generation
                and left.finalization_ids == right.finalization_ids
                and left.previous_manifest_digest == right.previous_manifest_digest
                and left.runtime_trust_digest == right.runtime_trust_digest
                and left.release_evidence_digest == right.release_evidence_digest
                and left.change_id == right.change_id
                and left.reason == right.reason
            )
            if not same_authority:
                raise DurableRecoveryRequirementConflict(
                    "recovery requirement generation already differs"
                )
            return existing

    def initialize(
        self,
        scope: str,
        finalization_ids: Iterable[str],
        *,
        runtime_trust_digest: str = "",
        release_evidence_digest: str = "",
        reason: str = "initial recovery proof set",
    ) -> SignedDurableRecoveryRequirementManifest:
        scope = _scope(scope)
        ids = _ids(finalization_ids, maximum=self.max_finalizations)
        runtime_trust_digest = _opaque_digest(
            "runtime_trust_digest",
            runtime_trust_digest,
            optional=True,
        )
        release_evidence_digest = _opaque_digest(
            "release_evidence_digest",
            release_evidence_digest,
            optional=True,
        )
        if len(reason) > 2048:
            raise ValueError("recovery requirement reason too long")

        for _ in range(self.max_retries):
            current = self.current(scope)
            if current is not None:
                _, item = current
                manifest = item.manifest
                same = (
                    manifest.generation == 1
                    and manifest.finalization_ids == ids
                    and manifest.runtime_trust_digest == runtime_trust_digest
                    and manifest.release_evidence_digest == release_evidence_digest
                )
                if not same:
                    raise DurableRecoveryRequirementConflict(
                        "recovery requirement scope already initialized differently"
                    )
                return item

            manifest = DurableRecoveryRequirementManifest(
                1,
                scope,
                1,
                ids,
                "",
                runtime_trust_digest,
                release_evidence_digest,
                "",
                reason,
                self._clock(),
            )
            item = self._persist_generation(self._sign(manifest))
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    self._head_key(scope),
                    item.to_dict(),
                )
                return item
            except DistributedStateConflict:
                continue
        raise DurableRecoveryRequirementConflict(
            "recovery requirement initialization retry bound exceeded"
        )

    def rollover(
        self,
        scope: str,
        finalization_ids: Iterable[str],
        *,
        expected_generation: int,
        change_id: str,
        reason: str,
        runtime_trust_digest: str | None = None,
        release_evidence_digest: str | None = None,
    ) -> SignedDurableRecoveryRequirementManifest:
        scope = _scope(scope)
        ids = _ids(finalization_ids, maximum=self.max_finalizations)
        if (
            isinstance(expected_generation, bool)
            or not isinstance(expected_generation, int)
            or expected_generation <= 0
        ):
            raise ValueError("expected_generation must be positive")
        if not change_id or len(change_id) > 256:
            raise ValueError("change_id is required")
        if not reason or len(reason) > 2048:
            raise ValueError("reason is required")

        for _ in range(self.max_retries):
            current = self.current(scope)
            if current is None:
                raise DurableRecoveryRequirementConflict(
                    "recovery requirement scope is not initialized"
                )
            head_revision, previous = current
            old = previous.manifest
            if old.generation != expected_generation:
                raise DurableRecoveryRequirementConflict(
                    "recovery requirement generation conflict"
                )
            if old.generation >= self.max_generations:
                raise RuntimeError(
                    "recovery requirement generation capacity exhausted"
                )
            next_runtime = (
                old.runtime_trust_digest
                if runtime_trust_digest is None
                else _opaque_digest(
                    "runtime_trust_digest",
                    runtime_trust_digest,
                    optional=True,
                )
            )
            next_release = (
                old.release_evidence_digest
                if release_evidence_digest is None
                else _opaque_digest(
                    "release_evidence_digest",
                    release_evidence_digest,
                    optional=True,
                )
            )
            if (
                ids == old.finalization_ids
                and next_runtime == old.runtime_trust_digest
                and next_release == old.release_evidence_digest
            ):
                raise DurableRecoveryRequirementConflict(
                    "recovery requirement rollover makes no authority change"
                )

            manifest = DurableRecoveryRequirementManifest(
                1,
                scope,
                old.generation + 1,
                ids,
                old.digest,
                next_runtime,
                next_release,
                change_id,
                reason,
                self._clock(),
            )
            item = self._persist_generation(self._sign(manifest))
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    self._head_key(scope),
                    expected_revision=head_revision,
                    value=item.to_dict(),
                )
                return item
            except DistributedStateConflict:
                latest = self.current(scope)
                if (
                    latest is not None
                    and latest[1].manifest.digest == item.manifest.digest
                ):
                    return latest[1]
                continue
        raise DurableRecoveryRequirementConflict(
            "recovery requirement rollover retry bound exceeded"
        )

    def add(
        self,
        scope: str,
        finalization_ids: Iterable[str],
        *,
        expected_generation: int,
        change_id: str,
        reason: str,
    ) -> SignedDurableRecoveryRequirementManifest:
        current = self.current(scope)
        if current is None:
            raise DurableRecoveryRequirementConflict(
                "recovery requirement scope is not initialized"
            )
        _, item = current
        additions = _ids(finalization_ids, maximum=self.max_finalizations)
        merged = tuple(sorted(set(item.manifest.finalization_ids) | set(additions)))
        return self.rollover(
            scope,
            merged,
            expected_generation=expected_generation,
            change_id=change_id,
            reason=reason,
        )

    def remove(
        self,
        scope: str,
        finalization_ids: Iterable[str],
        *,
        expected_generation: int,
        change_id: str,
        reason: str,
    ) -> SignedDurableRecoveryRequirementManifest:
        current = self.current(scope)
        if current is None:
            raise DurableRecoveryRequirementConflict(
                "recovery requirement scope is not initialized"
            )
        _, item = current
        removals = set(_ids(finalization_ids, maximum=self.max_finalizations))
        unknown = removals - set(item.manifest.finalization_ids)
        if unknown:
            raise DurableRecoveryRequirementConflict(
                "cannot remove finalization not in required set"
            )
        remaining = tuple(
            value
            for value in item.manifest.finalization_ids
            if value not in removals
        )
        return self.rollover(
            scope,
            remaining,
            expected_generation=expected_generation,
            change_id=change_id,
            reason=reason,
        )

    def verify_history(
        self,
        scope: str,
        *,
        runtime_trust_digest: str | None = None,
        release_evidence_digest: str | None = None,
    ) -> DurableRecoveryRequirementVerification:
        scope = _scope(scope)
        reasons: list[str] = []
        current = self.current(scope)
        if current is None:
            return DurableRecoveryRequirementVerification(
                False,
                scope,
                0,
                "",
                (),
                ("recovery requirement scope has no manifest",),
            )
        _, head = current
        previous_digest = ""
        previous_ids: tuple[str, ...] | None = None
        for generation in range(1, head.manifest.generation + 1):
            try:
                item = self.history_item(scope, generation)
            except Exception as exc:
                reasons.append(
                    "recovery requirement history read failed at generation "
                    f"{generation}: {type(exc).__name__}"
                )
                break
            manifest = item.manifest
            if manifest.previous_manifest_digest != previous_digest:
                reasons.append(
                    f"recovery requirement predecessor mismatch at generation {generation}"
                )
            if generation > 1 and previous_ids == manifest.finalization_ids:
                # A generation may still legitimately change runtime/release
                # binding, so this is diagnostic only when all authority stayed
                # unchanged; the digest chain itself remains authoritative.
                previous = self.history_item(scope, generation - 1).manifest
                if (
                    previous.runtime_trust_digest == manifest.runtime_trust_digest
                    and previous.release_evidence_digest == manifest.release_evidence_digest
                ):
                    reasons.append(
                        f"recovery requirement no-op generation {generation}"
                    )
            previous_digest = manifest.digest
            previous_ids = manifest.finalization_ids

        if previous_digest != head.manifest.digest:
            reasons.append("recovery requirement head is not terminal history generation")
        if runtime_trust_digest is not None:
            expected = _opaque_digest(
                "runtime_trust_digest",
                runtime_trust_digest,
                optional=True,
            )
            if head.manifest.runtime_trust_digest != expected:
                reasons.append("recovery requirement runtime trust binding mismatch")
        if release_evidence_digest is not None:
            expected = _opaque_digest(
                "release_evidence_digest",
                release_evidence_digest,
                optional=True,
            )
            if head.manifest.release_evidence_digest != expected:
                reasons.append("recovery requirement release binding mismatch")

        return DurableRecoveryRequirementVerification(
            not reasons,
            scope,
            head.manifest.generation,
            head.manifest.digest,
            head.manifest.finalization_ids,
            tuple(reasons),
        )

    def require(
        self,
        scope: str,
        *,
        runtime_trust_digest: str | None = None,
        release_evidence_digest: str | None = None,
    ) -> SignedDurableRecoveryRequirementManifest:
        report = self.verify_history(
            scope,
            runtime_trust_digest=runtime_trust_digest,
            release_evidence_digest=release_evidence_digest,
        )
        if not report.ok:
            raise DurableRecoveryRequirementConflict(
                report.reasons[0]
                if report.reasons
                else "recovery requirement verification failed"
            )
        current = self.current(scope)
        if current is None:
            raise DurableRecoveryRequirementConflict(
                "recovery requirement scope disappeared"
            )
        return current[1]
