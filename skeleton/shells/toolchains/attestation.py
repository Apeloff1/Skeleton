"""Executable content attestations for compiled logical toolchains."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import stat
from types import MappingProxyType
from typing import Mapping

from skeleton.shells.toolchains.compiler import CompiledToolchain
from skeleton.shells.toolchains.execution import (
    ToolchainExecutionPlane,
    ToolchainExecutionResult,
    ToolchainInvocation,
)
from skeleton.shells.retry import RetryPolicy
from skeleton.shells.session import ShellSession


class ExecutableAttestationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExecutableAttestationPolicy:
    max_binary_bytes: int = 1024 * 1024 * 1024
    hash_chunk_bytes: int = 1024 * 1024
    reject_world_writable: bool = True
    reject_group_writable: bool = False
    require_executable_bit: bool = True

    def __post_init__(self) -> None:
        for name in ("max_binary_bytes", "hash_chunk_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class ExecutableAttestation:
    executable_key: str
    requested_path: str
    resolved_path: str
    sha256: str
    size: int
    device: int
    inode: int
    mode: int
    mtime_ns: int
    captured_at: str

    def __post_init__(self) -> None:
        if not self.executable_key:
            raise ValueError("executable_key is required")
        if len(self.sha256) != 64:
            raise ValueError("sha256 must be a 64-character digest")
        if self.size < 0:
            raise ValueError("size must be non-negative")

    def to_dict(self, *, include_paths: bool = False) -> dict[str, object]:
        payload: dict[str, object] = {
            "executable_key": self.executable_key,
            "sha256": self.sha256,
            "size": self.size,
            "device": self.device,
            "inode": self.inode,
            "mode": self.mode,
            "mtime_ns": self.mtime_ns,
            "captured_at": self.captured_at,
        }
        if include_paths:
            payload["requested_path"] = self.requested_path
            payload["resolved_path"] = self.resolved_path
        return payload


@dataclass(frozen=True)
class ExecutableAttestationSet:
    attestations: Mapping[str, ExecutableAttestation]
    digest: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attestations",
            MappingProxyType(dict(self.attestations)),
        )
        if len(self.digest) != 64:
            raise ValueError("attestation set digest must be SHA-256 hex")

    def get(self, executable_key: str) -> ExecutableAttestation:
        try:
            return self.attestations[executable_key]
        except KeyError as exc:
            raise KeyError(
                f"no executable attestation for {executable_key!r}"
            ) from exc

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self.attestations))

    def to_dict(self, *, include_paths: bool = False) -> dict[str, object]:
        return {
            "attestations": {
                key: self.attestations[key].to_dict(include_paths=include_paths)
                for key in sorted(self.attestations)
            },
            "digest": self.digest,
        }


@dataclass(frozen=True)
class ExecutableVerification:
    executable_key: str
    valid: bool
    reasons: tuple[str, ...]
    expected_sha256: str
    actual_sha256: str = ""

    def require(self) -> None:
        if not self.valid:
            raise ExecutableAttestationError(
                f"executable attestation failed for {self.executable_key}: "
                + ", ".join(self.reasons)
            )


class ExecutableAttestor:
    def __init__(
        self,
        policy: ExecutableAttestationPolicy | None = None,
    ) -> None:
        self.policy = policy or ExecutableAttestationPolicy()

    def _inspect_path(self, path: str | Path) -> tuple[Path, os.stat_result]:
        requested = Path(path).expanduser()
        if not requested.is_absolute():
            raise ExecutableAttestationError(
                "executable attestation requires an absolute path"
            )
        try:
            resolved = requested.resolve(strict=True)
            metadata = resolved.stat()
        except (OSError, RuntimeError) as exc:
            raise ExecutableAttestationError(
                "executable is unavailable for attestation"
            ) from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise ExecutableAttestationError(
                "attested executable must resolve to a regular file"
            )
        if metadata.st_size > self.policy.max_binary_bytes:
            raise ExecutableAttestationError(
                "executable exceeds attestation byte bound"
            )
        mode = stat.S_IMODE(metadata.st_mode)
        if self.policy.require_executable_bit and not (mode & 0o111):
            raise ExecutableAttestationError(
                "attested file is not executable"
            )
        if self.policy.reject_world_writable and mode & 0o002:
            raise ExecutableAttestationError(
                "world-writable executable is not trusted"
            )
        if self.policy.reject_group_writable and mode & 0o020:
            raise ExecutableAttestationError(
                "group-writable executable is not trusted"
            )
        return resolved, metadata

    def _hash_stable(
        self,
        resolved: Path,
        expected: os.stat_result,
    ) -> str:
        digest = hashlib.sha256()
        read_bytes = 0
        try:
            with resolved.open("rb", buffering=0) as handle:
                opened = os.fstat(handle.fileno())
                if (
                    opened.st_dev != expected.st_dev
                    or opened.st_ino != expected.st_ino
                    or opened.st_size != expected.st_size
                    or opened.st_mtime_ns != expected.st_mtime_ns
                ):
                    raise ExecutableAttestationError(
                        "executable changed before hashing"
                    )
                while True:
                    chunk = handle.read(self.policy.hash_chunk_bytes)
                    if not chunk:
                        break
                    digest.update(chunk)
                    read_bytes += len(chunk)
                    if read_bytes > self.policy.max_binary_bytes:
                        raise ExecutableAttestationError(
                            "executable grew beyond attestation bound"
                        )
                closed = os.fstat(handle.fileno())
        except OSError as exc:
            raise ExecutableAttestationError(
                "failed to hash executable"
            ) from exc
        if (
            closed.st_dev != opened.st_dev
            or closed.st_ino != opened.st_ino
            or closed.st_size != opened.st_size
            or closed.st_mtime_ns != opened.st_mtime_ns
        ):
            raise ExecutableAttestationError(
                "executable changed while hashing"
            )
        return digest.hexdigest()

    def capture(
        self,
        executable_key: str,
        path: str | Path,
    ) -> ExecutableAttestation:
        resolved, metadata = self._inspect_path(path)
        digest = self._hash_stable(resolved, metadata)
        return ExecutableAttestation(
            executable_key=executable_key,
            requested_path=str(Path(path).expanduser()),
            resolved_path=str(resolved),
            sha256=digest,
            size=int(metadata.st_size),
            device=int(metadata.st_dev),
            inode=int(metadata.st_ino),
            mode=stat.S_IMODE(metadata.st_mode),
            mtime_ns=int(metadata.st_mtime_ns),
            captured_at=datetime.now(timezone.utc).isoformat(),
        )

    def verify(
        self,
        attestation: ExecutableAttestation,
    ) -> ExecutableVerification:
        reasons: list[str] = []
        actual_digest = ""
        try:
            resolved, metadata = self._inspect_path(attestation.requested_path)
        except ExecutableAttestationError as exc:
            return ExecutableVerification(
                attestation.executable_key,
                False,
                (str(exc),),
                attestation.sha256,
                "",
            )

        if str(resolved) != attestation.resolved_path:
            reasons.append("resolved path changed")
        if int(metadata.st_dev) != attestation.device:
            reasons.append("device changed")
        if int(metadata.st_ino) != attestation.inode:
            reasons.append("inode changed")
        if int(metadata.st_size) != attestation.size:
            reasons.append("size changed")
        if stat.S_IMODE(metadata.st_mode) != attestation.mode:
            reasons.append("mode changed")

        try:
            actual_digest = self._hash_stable(resolved, metadata)
        except ExecutableAttestationError as exc:
            reasons.append(str(exc))
        if actual_digest and actual_digest != attestation.sha256:
            reasons.append("content digest changed")

        return ExecutableVerification(
            executable_key=attestation.executable_key,
            valid=not reasons,
            reasons=tuple(reasons),
            expected_sha256=attestation.sha256,
            actual_sha256=actual_digest,
        )

    def capture_many(
        self,
        executable_paths: Mapping[str, str],
    ) -> ExecutableAttestationSet:
        attestations = {
            key: self.capture(key, executable_paths[key])
            for key in sorted(executable_paths)
        }
        digest = self._set_digest(attestations)
        return ExecutableAttestationSet(attestations, digest)

    @staticmethod
    def _set_digest(
        attestations: Mapping[str, ExecutableAttestation],
    ) -> str:
        payload = [
            {
                "key": key,
                "sha256": attestations[key].sha256,
                "size": attestations[key].size,
                "device": attestations[key].device,
                "inode": attestations[key].inode,
                "mode": attestations[key].mode,
            }
            for key in sorted(attestations)
        ]
        import json
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def verify_set(
        self,
        attestations: ExecutableAttestationSet,
    ) -> tuple[ExecutableVerification, ...]:
        return tuple(
            self.verify(attestations.attestations[key])
            for key in sorted(attestations.attestations)
        )

    def require_set(
        self,
        attestations: ExecutableAttestationSet,
    ) -> None:
        for verification in self.verify_set(attestations):
            verification.require()


def attest_compiled_toolchain(
    compiled: CompiledToolchain,
    *,
    attestor: ExecutableAttestor | None = None,
) -> ExecutableAttestationSet:
    engine = attestor or ExecutableAttestor()
    return engine.capture_many(compiled.executable_bindings)


class AttestedToolchainExecutionPlane:
    """Verify the selected executable's content before each invocation."""

    def __init__(
        self,
        base: ToolchainExecutionPlane,
        attestations: ExecutableAttestationSet,
        *,
        attestor: ExecutableAttestor | None = None,
    ) -> None:
        self.base = base
        self.attestations = attestations
        self.attestor = attestor or ExecutableAttestor()

    def verify_contract(self, contract_name: str) -> ExecutableVerification:
        contract = self.base.compiled.get(contract_name)
        attestation = self.attestations.get(contract.executable_key)
        return self.attestor.verify(attestation)

    def execute(
        self,
        invocation: ToolchainInvocation,
        *,
        retry: RetryPolicy | None = None,
        session: ShellSession | None = None,
    ) -> ToolchainExecutionResult:
        self.verify_contract(invocation.contract).require()
        return self.base.execute(
            invocation,
            retry=retry,
            session=session,
        )

    def names(self) -> tuple[str, ...]:
        return self.base.names()
