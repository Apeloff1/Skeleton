"""Registry of signed AI release evidence artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import threading

from skeleton.shells.ai.release_evidence import ReleaseEvidence
from skeleton.shells.ai.signed_artifact import ArtifactSigner, SignedArtifact


@dataclass(frozen=True)
class RegisteredRelease:
    release_id: str
    revision: int
    evidence: ReleaseEvidence
    signature: SignedArtifact
    active: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "release_id": self.release_id,
            "revision": self.revision,
            "evidence_digest": self.evidence.digest,
            "signature": self.signature.to_dict(),
            "active": self.active,
        }


class ReleaseRegistryConflict(RuntimeError):
    pass


class AIReleaseRegistry:
    def __init__(
        self,
        signer: ArtifactSigner,
        *,
        max_releases: int = 1024,
    ) -> None:
        if max_releases <= 0:
            raise ValueError("max_releases must be positive")
        self.signer = signer
        self.max_releases = max_releases
        self._items: dict[str, list[RegisteredRelease]] = {}
        self._lock = threading.RLock()

    def register(
        self,
        evidence: ReleaseEvidence,
        *,
        expected_revision: int | None = None,
    ) -> RegisteredRelease:
        with self._lock:
            history = self._items.get(evidence.release_id)
            if history is None:
                if len(self._items) >= self.max_releases:
                    raise RuntimeError("AI release registry capacity exhausted")
                if expected_revision not in {None, 0}:
                    raise ReleaseRegistryConflict("AI release does not exist")
                revision = 1
            else:
                current = history[-1]
                if expected_revision is not None and current.revision != expected_revision:
                    raise ReleaseRegistryConflict("AI release revision conflict")
                if current.evidence.digest == evidence.digest:
                    return current
                revision = current.revision + 1
            signature = self.signer.sign(
                "ai-release-evidence",
                evidence.digest,
                metadata={
                    "release_id": evidence.release_id,
                    "code_revision": evidence.code_revision,
                },
            )
            item = RegisteredRelease(
                evidence.release_id,
                revision,
                evidence,
                signature,
                False,
            )
            self._items.setdefault(evidence.release_id, []).append(item)
            return item

    def activate(
        self,
        release_id: str,
        *,
        expected_revision: int | None = None,
    ) -> RegisteredRelease:
        with self._lock:
            current = self.current(release_id)
            if expected_revision is not None and current.revision != expected_revision:
                raise ReleaseRegistryConflict("AI release revision conflict")
            if not current.evidence.deployable:
                raise RuntimeError("cannot activate non-deployable AI release")
            self.signer.verify(current.signature)
            item = RegisteredRelease(
                current.release_id,
                current.revision + 1,
                current.evidence,
                current.signature,
                True,
            )
            self._items[release_id].append(item)
            return item

    def deactivate(
        self,
        release_id: str,
        *,
        expected_revision: int | None = None,
    ) -> RegisteredRelease:
        with self._lock:
            current = self.current(release_id)
            if expected_revision is not None and current.revision != expected_revision:
                raise ReleaseRegistryConflict("AI release revision conflict")
            if not current.active:
                return current
            item = RegisteredRelease(
                current.release_id,
                current.revision + 1,
                current.evidence,
                current.signature,
                False,
            )
            self._items[release_id].append(item)
            return item

    def current(self, release_id: str) -> RegisteredRelease:
        with self._lock:
            return self._items[release_id][-1]

    def history(self, release_id: str) -> tuple[RegisteredRelease, ...]:
        with self._lock:
            return tuple(self._items[release_id])
