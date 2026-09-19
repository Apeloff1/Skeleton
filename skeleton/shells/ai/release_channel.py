"""CAS-pinned AI release channels for multi-instance deployment."""

from __future__ import annotations

from dataclasses import dataclass

from skeleton.shells.ai.distributed_state import DistributedStateConflict
from skeleton.shells.ai.release_registry import RegisteredRelease
from skeleton.shells.ai.store_protocol import VersionedStateBackend


@dataclass(frozen=True)
class ReleaseChannelState:
    channel: str
    release_id: str
    release_revision: int
    evidence_digest: str
    registry_signature: str

    def __post_init__(self) -> None:
        if not self.channel or len(self.channel) > 128:
            raise ValueError("invalid release channel")
        if not self.release_id or len(self.release_id) > 160:
            raise ValueError("invalid release_id")
        if self.release_revision <= 0:
            raise ValueError("release revision must be positive")
        if len(self.evidence_digest) != 64 or len(self.registry_signature) != 64:
            raise ValueError("release channel digests must be SHA-256 hex")

    def to_dict(self) -> dict[str, object]:
        return {
            "channel": self.channel,
            "release_id": self.release_id,
            "release_revision": self.release_revision,
            "evidence_digest": self.evidence_digest,
            "registry_signature": self.registry_signature,
        }


class ReleaseChannelConflict(RuntimeError):
    pass


class AIReleaseChannelStore:
    def __init__(
        self,
        backend: VersionedStateBackend,
        *,
        namespace: str = "shell-ai-release-channel",
    ) -> None:
        self.backend = backend
        self.namespace = namespace

    @staticmethod
    def from_release(channel: str, release: RegisteredRelease) -> ReleaseChannelState:
        if not release.active:
            raise ValueError("release must be active before channel assignment")
        return ReleaseChannelState(
            channel,
            release.release_id,
            release.revision,
            release.evidence.digest,
            release.signature.signature,
        )

    def current(self, channel: str) -> tuple[int, ReleaseChannelState] | None:
        record = self.backend.get(self.namespace, channel)
        if record is None:
            return None
        if not isinstance(record.value, ReleaseChannelState):
            raise RuntimeError("release channel record type mismatch")
        return record.revision, record.value

    def set(
        self,
        state: ReleaseChannelState,
        *,
        expected_revision: int = 0,
    ) -> tuple[int, ReleaseChannelState]:
        try:
            record = self.backend.compare_and_swap(
                self.namespace,
                state.channel,
                expected_revision=expected_revision,
                value=state,
            )
        except DistributedStateConflict as exc:
            raise ReleaseChannelConflict("release channel revision conflict") from exc
        return record.revision, state
