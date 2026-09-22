"""Durable signed pins for runtime-trust epochs.

AIRuntimeTrustGuard can pin a trust epoch in process memory.  That protects a
long-lived worker but a process restart would otherwise be able to accept a
newly changed model/release surface.  This store persists the expected epoch
through a versioned backend and keeps a signed predecessor chain for explicit
rollover.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import time
from typing import Callable

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.runtime_trust import RuntimeTrustEpoch
from skeleton.shells.ai.signed_artifact import (
    ArtifactSignatureError,
    ArtifactSigner,
    SignedArtifact,
)
from skeleton.shells.ai.store_protocol import VersionedStateBackend


_SCOPE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")


@dataclass(frozen=True)
class RuntimeTrustPin:
    schema_version: int
    scope: str
    revision: int
    epoch_digest: str
    previous_pin_digest: str = ""
    change_id: str = ""
    reason: str = ""
    pinned_at: float = 0.0

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported runtime trust pin schema")
        if not isinstance(self.scope, str) or not _SCOPE_RE.fullmatch(self.scope):
            raise ValueError("invalid runtime trust pin scope")
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision <= 0
        ):
            raise ValueError("runtime trust pin revision must be positive")
        for name in ("epoch_digest",):
            value = getattr(self, name)
            if len(value) != 64:
                raise ValueError(f"{name} must be SHA-256 hex")
            # Opaque 64-character authority digest; equality is authoritative.
        if self.previous_pin_digest:
            if len(self.previous_pin_digest) != 64:
                raise ValueError(
                    "previous_pin_digest must be SHA-256 hex"
                )
            # Opaque 64-character authority digest; equality is authoritative.
        if self.revision == 1 and self.previous_pin_digest:
            raise ValueError("first runtime trust pin may not have predecessor")
        if self.revision > 1 and not self.previous_pin_digest:
            raise ValueError("runtime trust rollover requires predecessor")
        if len(self.change_id) > 256:
            raise ValueError("runtime trust change_id too long")
        if self.revision > 1 and not self.change_id:
            raise ValueError("runtime trust rollover requires change_id")
        if len(self.reason) > 2048:
            raise ValueError("runtime trust pin reason too long")
        if (
            isinstance(self.pinned_at, bool)
            or not isinstance(self.pinned_at, (int, float))
            or self.pinned_at < 0
        ):
            raise ValueError("runtime trust pin time must be non-negative")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "scope": self.scope,
            "revision": self.revision,
            "epoch_digest": self.epoch_digest,
            "previous_pin_digest": self.previous_pin_digest,
            "change_id": self.change_id,
            "reason": self.reason,
            "pinned_at": float(self.pinned_at),
        }

    @property
    def digest(self) -> str:
        raw = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class SignedRuntimeTrustPin:
    pin: RuntimeTrustPin
    signature: SignedArtifact

    def __post_init__(self) -> None:
        if self.signature.artifact_type != "ai-runtime-trust-pin":
            raise ValueError("invalid runtime trust pin artifact type")
        if self.signature.artifact_digest != self.pin.digest:
            raise ValueError("runtime trust pin signature digest mismatch")

    def to_dict(self) -> dict[str, object]:
        return {
            "pin": self.pin.to_dict(),
            "pin_digest": self.pin.digest,
            "signature": self.signature.to_dict(),
        }


@dataclass(frozen=True)
class RuntimeTrustPinVerification:
    ok: bool
    reasons: tuple[str, ...]
    scope: str
    revision: int = 0
    epoch_digest: str = ""
    pin_digest: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "reasons": list(self.reasons),
            "scope": self.scope,
            "revision": self.revision,
            "epoch_digest": self.epoch_digest,
            "pin_digest": self.pin_digest,
        }


class RuntimeTrustPinConflict(RuntimeError):
    pass


class RuntimeTrustPinStore:
    """Persist one current signed epoch per deployment scope with CAS rollover."""

    def __init__(
        self,
        backend: VersionedStateBackend,
        signer: ArtifactSigner,
        *,
        namespace: str = "shell-ai-runtime-trust-pin",
        max_revisions: int = 10_000,
        max_retries: int = 8,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not isinstance(backend, VersionedStateBackend):
            raise TypeError("backend must satisfy VersionedStateBackend")
        if not namespace or len(namespace) > 128:
            raise ValueError("invalid runtime trust pin namespace")
        if (
            isinstance(max_revisions, bool)
            or not isinstance(max_revisions, int)
            or max_revisions <= 0
        ):
            raise ValueError("max_revisions must be positive")
        if (
            isinstance(max_retries, bool)
            or not isinstance(max_retries, int)
            or not 1 <= max_retries <= 64
        ):
            raise ValueError("max_retries outside supported range")
        self.backend = backend
        self.signer = signer
        self.namespace = namespace
        self.max_revisions = max_revisions
        self.max_retries = max_retries
        self._clock = clock

    @staticmethod
    def _scope(scope: str) -> str:
        if not isinstance(scope, str) or not _SCOPE_RE.fullmatch(scope):
            raise ValueError("invalid runtime trust scope")
        return scope

    @classmethod
    def _head_key(cls, scope: str) -> str:
        return f"head:{cls._scope(scope)}"

    @classmethod
    def _history_key(cls, scope: str, revision: int) -> str:
        cls._scope(scope)
        if revision <= 0:
            raise ValueError("runtime trust revision must be positive")
        return f"history:{scope}:{revision:020d}"

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
    def _decode(cls, value: object) -> SignedRuntimeTrustPin:
        if not isinstance(value, dict):
            raise ValueError("runtime trust pin record must be mapping")
        raw_pin = value.get("pin")
        raw_signature = value.get("signature")
        if not isinstance(raw_pin, dict) or not isinstance(raw_signature, dict):
            raise ValueError("runtime trust pin record shape invalid")
        pin = RuntimeTrustPin(
            int(raw_pin["schema_version"]),
            str(raw_pin["scope"]),
            int(raw_pin["revision"]),
            str(raw_pin["epoch_digest"]),
            str(raw_pin.get("previous_pin_digest", "")),
            str(raw_pin.get("change_id", "")),
            str(raw_pin.get("reason", "")),
            float(raw_pin["pinned_at"]),
        )
        return SignedRuntimeTrustPin(
            pin,
            cls._signature(dict(raw_signature)),
        )

    def _sign(self, pin: RuntimeTrustPin) -> SignedRuntimeTrustPin:
        signature = self.signer.sign(
            "ai-runtime-trust-pin",
            pin.digest,
            metadata={
                "scope": pin.scope,
                "revision": str(pin.revision),
            },
        )
        return SignedRuntimeTrustPin(pin, signature)

    def _verify_item(self, item: SignedRuntimeTrustPin) -> None:
        if item.signature.artifact_type != "ai-runtime-trust-pin":
            raise RuntimeTrustPinConflict(
                "runtime trust pin artifact type mismatch"
            )
        if item.signature.artifact_digest != item.pin.digest:
            raise RuntimeTrustPinConflict(
                "runtime trust pin digest mismatch"
            )
        if item.signature.metadata.get("scope") != item.pin.scope:
            raise RuntimeTrustPinConflict(
                "runtime trust pin signature scope mismatch"
            )
        if item.signature.metadata.get("revision") != str(item.pin.revision):
            raise RuntimeTrustPinConflict(
                "runtime trust pin signature revision mismatch"
            )
        try:
            self.signer.verify(item.signature)
        except ArtifactSignatureError as exc:
            raise RuntimeTrustPinConflict(
                "runtime trust pin signature verification failed"
            ) from exc

    def current(
        self,
        scope: str,
    ) -> tuple[int, SignedRuntimeTrustPin] | None:
        record = self.backend.get(
            self.namespace,
            self._head_key(scope),
        )
        if record is None:
            return None
        item = self._decode(record.value)
        self._verify_item(item)
        if item.pin.scope != scope:
            raise RuntimeTrustPinConflict(
                "runtime trust head scope mismatch"
            )
        return record.revision, item

    def history_item(
        self,
        scope: str,
        revision: int,
    ) -> SignedRuntimeTrustPin:
        record = self.backend.get(
            self.namespace,
            self._history_key(scope, revision),
        )
        if record is None:
            raise KeyError((scope, revision))
        item = self._decode(record.value)
        self._verify_item(item)
        if item.pin.scope != scope or item.pin.revision != revision:
            raise RuntimeTrustPinConflict(
                "runtime trust history identity mismatch"
            )
        return item

    def _persist_revision(
        self,
        item: SignedRuntimeTrustPin,
    ) -> SignedRuntimeTrustPin:
        key = self._history_key(
            item.pin.scope,
            item.pin.revision,
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
                item.pin.scope,
                item.pin.revision,
            )
            same_authority = (
                existing.pin.scope == item.pin.scope
                and existing.pin.revision == item.pin.revision
                and existing.pin.epoch_digest == item.pin.epoch_digest
                and existing.pin.previous_pin_digest
                == item.pin.previous_pin_digest
                and existing.pin.change_id == item.pin.change_id
            )
            if not same_authority:
                raise RuntimeTrustPinConflict(
                    "runtime trust revision already contains different pin"
                )
            # Concurrent starters/rollovers may sign at different wall-clock
            # instants. The immutable history winner is canonical; all losing
            # writers must reuse it rather than manufacturing parallel history.
            return existing

    def pin(
        self,
        scope: str,
        epoch: RuntimeTrustEpoch,
        *,
        reason: str = "startup pin",
    ) -> SignedRuntimeTrustPin:
        scope = self._scope(scope)
        if not isinstance(epoch, RuntimeTrustEpoch):
            raise TypeError("epoch must be RuntimeTrustEpoch")
        for _ in range(self.max_retries):
            current = self.current(scope)
            if current is not None:
                _, item = current
                if item.pin.epoch_digest != epoch.digest:
                    raise RuntimeTrustPinConflict(
                        "runtime trust epoch differs from durable pin"
                    )
                return item

            pin = RuntimeTrustPin(
                1,
                scope,
                1,
                epoch.digest,
                "",
                "",
                reason,
                self._clock(),
            )
            item = self._sign(pin)
            item = self._persist_revision(item)
            try:
                self.backend.put_if_absent(
                    self.namespace,
                    self._head_key(scope),
                    item.to_dict(),
                )
                return item
            except DistributedStateConflict:
                continue
        raise RuntimeTrustPinConflict(
            "runtime trust initial pin retry bound exceeded"
        )

    def require(
        self,
        scope: str,
        epoch_digest: str,
    ) -> SignedRuntimeTrustPin:
        current = self.current(scope)
        if current is None:
            raise RuntimeTrustPinConflict(
                "runtime trust scope has no durable pin"
            )
        _, item = current
        if item.pin.epoch_digest != epoch_digest:
            raise RuntimeTrustPinConflict(
                "runtime trust epoch differs from durable pin"
            )
        return item

    def rollover(
        self,
        scope: str,
        epoch: RuntimeTrustEpoch,
        *,
        expected_revision: int,
        change_id: str,
        reason: str,
    ) -> SignedRuntimeTrustPin:
        scope = self._scope(scope)
        if not isinstance(epoch, RuntimeTrustEpoch):
            raise TypeError("epoch must be RuntimeTrustEpoch")
        if (
            isinstance(expected_revision, bool)
            or not isinstance(expected_revision, int)
            or expected_revision <= 0
        ):
            raise ValueError("expected_revision must be positive")
        if not change_id or len(change_id) > 256:
            raise ValueError("runtime trust rollover change_id is required")
        if not reason or len(reason) > 2048:
            raise ValueError("runtime trust rollover reason is required")

        for _ in range(self.max_retries):
            current = self.current(scope)
            if current is None:
                raise RuntimeTrustPinConflict(
                    "runtime trust scope is not pinned"
                )
            head_revision, previous = current
            if previous.pin.revision != expected_revision:
                raise RuntimeTrustPinConflict(
                    "runtime trust pin revision conflict"
                )
            if previous.pin.revision >= self.max_revisions:
                raise RuntimeError(
                    "runtime trust pin revision capacity exhausted"
                )
            if previous.pin.epoch_digest == epoch.digest:
                raise RuntimeTrustPinConflict(
                    "runtime trust rollover does not change epoch"
                )
            next_pin = RuntimeTrustPin(
                1,
                scope,
                previous.pin.revision + 1,
                epoch.digest,
                previous.pin.digest,
                change_id,
                reason,
                self._clock(),
            )
            item = self._sign(next_pin)
            item = self._persist_revision(item)
            try:
                self.backend.compare_and_swap(
                    self.namespace,
                    self._head_key(scope),
                    expected_revision=head_revision,
                    value=item.to_dict(),
                )
                return item
            except DistributedStateConflict:
                refreshed = self.current(scope)
                if (
                    refreshed is not None
                    and refreshed[1].pin.digest == item.pin.digest
                ):
                    return refreshed[1]
                continue
        raise RuntimeTrustPinConflict(
            "runtime trust rollover retry bound exceeded"
        )

    def verify(
        self,
        scope: str,
    ) -> RuntimeTrustPinVerification:
        scope = self._scope(scope)
        try:
            current = self.current(scope)
        except (ValueError, RuntimeTrustPinConflict) as exc:
            return RuntimeTrustPinVerification(
                False,
                (f"runtime trust head invalid: {type(exc).__name__}",),
                scope,
            )
        if current is None:
            return RuntimeTrustPinVerification(True, (), scope)

        _, head = current
        reasons: list[str] = []
        previous_digest = ""
        final: SignedRuntimeTrustPin | None = None
        for revision in range(1, head.pin.revision + 1):
            try:
                item = self.history_item(scope, revision)
            except (
                KeyError,
                ValueError,
                RuntimeTrustPinConflict,
            ) as exc:
                reasons.append(
                    "runtime trust history "
                    f"{revision} invalid: {type(exc).__name__}"
                )
                break
            if item.pin.previous_pin_digest != previous_digest:
                reasons.append(
                    f"runtime trust history {revision} predecessor mismatch"
                )
                break
            previous_digest = item.pin.digest
            final = item

        if not reasons:
            if final is None:
                reasons.append("runtime trust history unexpectedly empty")
            elif final.pin.digest != head.pin.digest:
                reasons.append(
                    "runtime trust head differs from signed history"
                )

        return RuntimeTrustPinVerification(
            not reasons,
            tuple(reasons),
            scope,
            head.pin.revision,
            head.pin.epoch_digest,
            head.pin.digest,
        )
