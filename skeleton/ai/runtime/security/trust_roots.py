"""Trust-root bootstrap, rotation, and recovery contracts for P1 AC-01."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from collections.abc import Mapping

from skeleton.kernel.keyholder import Keyholder


class TrustRootError(ValueError):
    """Trust-root bootstrap or rotation evidence failed validation."""


def _digest(value: object) -> str:
    try:
        raw = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TrustRootError("trust-root payload must be canonical JSON") from exc
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class TrustRootRotationProof:
    previous_root_id: str
    new_root_id: str
    generation: int
    payload_digest: str
    previous_signature: str
    new_signature: str

    def payload(self) -> dict[str, object]:
        return {
            "previous_root_id": self.previous_root_id,
            "new_root_id": self.new_root_id,
            "generation": self.generation,
            "payload_digest": self.payload_digest,
        }

    @property
    def proof_digest(self) -> str:
        return _digest(
            {
                **self.payload(),
                "previous_signature": self.previous_signature,
                "new_signature": self.new_signature,
            }
        )


class TrustRootStore:
    """Process-local trust-root chain with dual-signed atomic rotation."""

    def __init__(self, root: Keyholder) -> None:
        if not isinstance(root, Keyholder):
            raise TypeError("root must be Keyholder")
        self._generation = 1
        self._active_id = root.public_hex
        self._roots: dict[str, Keyholder] = {root.public_hex: root}
        self._history: list[str] = [root.public_hex]

    @classmethod
    def clean_bootstrap(cls, seed: bytes) -> "TrustRootStore":
        """Create one deterministic root for a clean-machine bootstrap."""
        return cls(Keyholder.mint(seed))

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def active_root_id(self) -> str:
        return self._active_id

    @property
    def history(self) -> tuple[str, ...]:
        return tuple(self._history)

    def propose_rotation(self, new_seed: bytes) -> TrustRootRotationProof:
        replacement = Keyholder.mint(new_seed)
        if replacement.public_hex in self._roots:
            raise TrustRootError("replacement trust root already exists")
        generation = self._generation + 1
        payload = {
            "previous_root_id": self._active_id,
            "new_root_id": replacement.public_hex,
            "generation": generation,
        }
        payload_digest = _digest(payload)
        message = payload_digest.encode("ascii")
        current = self._roots[self._active_id]
        return TrustRootRotationProof(
            previous_root_id=self._active_id,
            new_root_id=replacement.public_hex,
            generation=generation,
            payload_digest=payload_digest,
            previous_signature=current.sign(message),
            new_signature=replacement.sign(message),
        )

    def apply_rotation(
        self,
        proof: TrustRootRotationProof,
        *,
        new_seed: bytes,
    ) -> None:
        """Atomically rotate only after old-root and new-root signatures verify."""
        if not isinstance(proof, TrustRootRotationProof):
            raise TypeError("proof must be TrustRootRotationProof")
        if proof.previous_root_id != self._active_id:
            raise TrustRootError("rotation previous root does not match active root")
        if proof.generation != self._generation + 1:
            raise TrustRootError("rotation generation is not next")
        replacement = Keyholder.mint(new_seed)
        if replacement.public_hex != proof.new_root_id:
            raise TrustRootError("replacement seed does not match proposed root")
        expected_payload = _digest(
            {
                "previous_root_id": proof.previous_root_id,
                "new_root_id": proof.new_root_id,
                "generation": proof.generation,
            }
        )
        if expected_payload != proof.payload_digest:
            raise TrustRootError("rotation payload digest mismatch")
        message = proof.payload_digest.encode("ascii")
        previous = self._roots[self._active_id]
        if not previous.verify(message, proof.previous_signature):
            raise TrustRootError("previous trust-root signature invalid")
        if not replacement.verify(message, proof.new_signature):
            raise TrustRootError("new trust-root signature invalid")

        # Mutate only after all checks have passed.
        self._roots[replacement.public_hex] = replacement
        self._active_id = replacement.public_hex
        self._generation = proof.generation
        self._history.append(replacement.public_hex)

    def snapshot(self) -> dict[str, object]:
        """Return seed-free root history for recovery."""
        return {
            "schema_version": 1,
            "generation": self._generation,
            "active_root_id": self._active_id,
            "history": list(self._history),
        }

    @classmethod
    def restore(
        cls,
        snapshot: Mapping[str, object],
        *,
        seeds_by_root_id: Mapping[str, bytes],
    ) -> "TrustRootStore":
        if not isinstance(snapshot, Mapping):
            raise TypeError("snapshot must be a mapping")
        if snapshot.get("schema_version") != 1:
            raise TrustRootError("unsupported trust-root snapshot schema")
        generation = snapshot.get("generation")
        active = snapshot.get("active_root_id")
        history = snapshot.get("history")
        if (
            isinstance(generation, bool)
            or not isinstance(generation, int)
            or generation < 1
        ):
            raise TrustRootError("snapshot generation invalid")
        if not isinstance(active, str):
            raise TrustRootError("snapshot active root invalid")
        if (
            not isinstance(history, list)
            or not history
            or any(not isinstance(item, str) for item in history)
            or len(history) != len(set(history))
        ):
            raise TrustRootError("snapshot history invalid")
        if generation != len(history):
            raise TrustRootError("snapshot generation/history mismatch")
        if history[-1] != active:
            raise TrustRootError("snapshot active root is not history tip")

        roots: dict[str, Keyholder] = {}
        for root_id in history:
            seed = seeds_by_root_id.get(root_id)
            if seed is None:
                raise TrustRootError("missing recovery seed for trust root")
            root = Keyholder.mint(seed)
            if root.public_hex != root_id:
                raise TrustRootError("recovery seed does not match trust root")
            roots[root_id] = root

        store = cls.__new__(cls)
        store._generation = generation
        store._active_id = active
        store._roots = roots
        store._history = list(history)
        return store


__all__ = [
    "TrustRootError",
    "TrustRootRotationProof",
    "TrustRootStore",
]
