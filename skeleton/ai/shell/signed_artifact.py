"""HMAC signing for AI shell governance artifacts.

This is intended for service-to-service integrity with a shared secret. It is
not a public-signature replacement for independent third-party verification.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import time
from types import MappingProxyType
from typing import Callable, Mapping


@dataclass(frozen=True)
class SignedArtifact:
    artifact_type: str
    artifact_digest: str
    key_id: str
    issued_at: float
    metadata: Mapping[str, str]
    signature: str

    def __post_init__(self) -> None:
        if not self.artifact_type or len(self.artifact_type) > 128:
            raise ValueError("invalid artifact_type")
        if len(self.artifact_digest) != 64:
            raise ValueError("artifact_digest must be SHA-256 hex")
        if not self.key_id or len(self.key_id) > 128:
            raise ValueError("invalid key_id")
        if len(self.signature) != 64:
            raise ValueError("signature must be SHA-256 HMAC")
        metadata = dict(self.metadata)
        if len(metadata) > 64:
            raise ValueError("too many signed artifact metadata fields")
        object.__setattr__(self, "metadata", MappingProxyType(metadata))

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "artifact_type": self.artifact_type,
            "artifact_digest": self.artifact_digest,
            "key_id": self.key_id,
            "issued_at": self.issued_at,
            "metadata": dict(self.metadata),
        }

    def to_dict(self) -> dict[str, object]:
        data = self.unsigned_dict()
        data["signature"] = self.signature
        return data


class ArtifactSignatureError(RuntimeError):
    pass


class ArtifactSigner:
    def __init__(
        self,
        key_id: str,
        key: bytes,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if not key_id or len(key_id) > 128:
            raise ValueError("invalid key_id")
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError("artifact signing key must be at least 32 bytes")
        self.key_id = key_id
        self._key = key
        self._clock = clock

    def _sign(self, payload: dict[str, object]) -> str:
        raw = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return hmac.new(self._key, raw, hashlib.sha256).hexdigest()

    def sign(
        self,
        artifact_type: str,
        artifact_digest: str,
        *,
        metadata: Mapping[str, str] | None = None,
    ) -> SignedArtifact:
        issued_at = float(self._clock())
        payload = {
            "artifact_type": artifact_type,
            "artifact_digest": artifact_digest,
            "key_id": self.key_id,
            "issued_at": issued_at,
            "metadata": dict(metadata or {}),
        }
        return SignedArtifact(
            artifact_type,
            artifact_digest,
            self.key_id,
            issued_at,
            dict(payload["metadata"]),
            self._sign(payload),
        )

    def verify(self, artifact: SignedArtifact) -> None:
        if artifact.key_id != self.key_id:
            raise ArtifactSignatureError("artifact key_id mismatch")
        expected = self._sign(artifact.unsigned_dict())
        if not hmac.compare_digest(expected, artifact.signature):
            raise ArtifactSignatureError("artifact signature mismatch")
