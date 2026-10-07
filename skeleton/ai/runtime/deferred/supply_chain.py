"""Build, binary, installer and update supply-chain controls VOL-273..277."""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import sha256_json


def _t(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _d(value: object, name: str) -> str:
    text = _t(value, name)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{name} must be lowercase sha256")
    return text


@dataclass(frozen=True, slots=True)
class BuildInput:
    name: str
    digest: str
    source: str


@dataclass(frozen=True, slots=True)
class HermeticPolicy:
    network_allowed: bool
    vendored_network_inputs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HermeticBuild:
    source_digest: str
    toolchain_digest: str
    inputs: tuple[BuildInput, ...]
    policy: HermeticPolicy

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_digest",
            _d(self.source_digest, "source_digest"),
        )
        object.__setattr__(
            self,
            "toolchain_digest",
            _d(self.toolchain_digest, "toolchain_digest"),
        )
        if (
            len({item.name for item in self.inputs}) != len(self.inputs)
            or any(not item.name or not item.source for item in self.inputs)
        ):
            raise ValueError("unique build input identity required")
        for item in self.inputs:
            _d(item.digest, "input_digest")
        if (
            any(not item for item in self.policy.vendored_network_inputs)
            or len(set(self.policy.vendored_network_inputs))
            != len(self.policy.vendored_network_inputs)
        ):
            raise ValueError("unique vendored input identity required")
        if (
            self.policy.network_allowed
            and not self.policy.vendored_network_inputs
        ):
            raise ValueError(
                "qualified network build must declare vendored/cached inputs"
            )

    @property
    def identity(self) -> str:
        return sha256_json(
            {
                "source": self.source_digest,
                "toolchain": self.toolchain_digest,
                "inputs": sorted(
                    (item.name, item.digest, item.source)
                    for item in self.inputs
                ),
                "network": self.policy.network_allowed,
                "vendored": sorted(self.policy.vendored_network_inputs),
            }
        )


@dataclass(frozen=True, slots=True)
class CachePolicy:
    shared: bool
    sensitive: bool
    tenant_id: str | None

    def __post_init__(self) -> None:
        if self.shared and (self.sensitive or self.tenant_id):
            raise ValueError(
                "sensitive or tenant data cannot use shared cache"
            )


@dataclass(frozen=True, slots=True)
class BuildCacheKey:
    source_digest: str
    toolchain_digest: str
    config_digest: str
    dependency_digest: str

    def __post_init__(self) -> None:
        for name in (
            "source_digest",
            "toolchain_digest",
            "config_digest",
            "dependency_digest",
        ):
            object.__setattr__(self, name, _d(getattr(self, name), name))

    @property
    def key(self) -> str:
        return sha256_json(
            {
                "source": self.source_digest,
                "toolchain": self.toolchain_digest,
                "config": self.config_digest,
                "deps": self.dependency_digest,
            }
        )


@dataclass(frozen=True, slots=True)
class CachedArtifact:
    cache_key: str
    artifact_digest: str
    policy: CachePolicy


@dataclass(frozen=True, slots=True)
class BuildIdentity:
    source_digest: str
    environment_digest: str
    toolchain_digest: str


@dataclass(frozen=True, slots=True)
class ArtifactSignature:
    artifact_digest: str
    signer_id: str
    signature_digest: str


@dataclass(frozen=True, slots=True)
class BinaryAttestation:
    artifact_digest: str
    build: BuildIdentity
    signature: ArtifactSignature

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_digest",
            _d(self.artifact_digest, "artifact_digest"),
        )
        for name in (
            "source_digest",
            "environment_digest",
            "toolchain_digest",
        ):
            _d(getattr(self.build, name), name)
        _d(
            self.signature.artifact_digest,
            "signature_artifact_digest",
        )
        _t(self.signature.signer_id, "signer_id")
        _d(self.signature.signature_digest, "signature_digest")
        if self.signature.artifact_digest != self.artifact_digest:
            raise ValueError("signature must bind attested artifact")


def verify_attestation(
    attestation: BinaryAttestation,
    trusted_signers: tuple[str, ...],
) -> bool:
    if (
        len(set(trusted_signers)) != len(trusted_signers)
        or any(not signer for signer in trusted_signers)
    ):
        return False
    return (
        attestation.signature.signer_id in trusted_signers
        and attestation.signature.artifact_digest
        == attestation.artifact_digest
    )


@dataclass(frozen=True, slots=True)
class InstallerSecurityPolicy:
    allowed_roots: tuple[str, ...]
    trusted_signers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InstallPath:
    root: str
    relative_path: str
    contains_symlink: bool = False

    def __post_init__(self) -> None:
        _t(self.root, "root")
        _t(self.relative_path, "relative_path")
        if (
            self.relative_path.startswith("/")
            or ".." in self.relative_path.split("/")
        ):
            raise ValueError("install path traversal")
        if self.contains_symlink:
            raise ValueError("symlink install target rejected")


@dataclass(frozen=True, slots=True)
class InstallVerification:
    artifact_digest: str
    signature_verified: bool
    path_verified: bool

    @property
    def privileged_write_allowed(self) -> bool:
        return self.signature_verified and self.path_verified


@dataclass(frozen=True, slots=True)
class VersionFloor:
    minimum_version: int

    def __post_init__(self) -> None:
        if self.minimum_version < 0:
            raise ValueError("version floor must be nonnegative")


@dataclass(frozen=True, slots=True)
class UpdateSignature:
    metadata_digest: str
    signer_id: str


@dataclass(frozen=True, slots=True)
class UpdateMetadata:
    version: int
    artifact_digest: str
    metadata_digest: str
    signature: UpdateSignature
    authorized_rollback: bool = False

    def __post_init__(self) -> None:
        if self.version < 0:
            raise ValueError("update version must be nonnegative")
        object.__setattr__(
            self,
            "artifact_digest",
            _d(self.artifact_digest, "artifact_digest"),
        )
        object.__setattr__(
            self,
            "metadata_digest",
            _d(self.metadata_digest, "metadata_digest"),
        )
        _d(
            self.signature.metadata_digest,
            "signature_metadata_digest",
        )
        _t(self.signature.signer_id, "signer_id")
        if self.signature.metadata_digest != self.metadata_digest:
            raise ValueError("signature must bind update metadata")


def admit_update(
    metadata: UpdateMetadata,
    floor: VersionFloor,
    trusted_signers: tuple[str, ...],
) -> bool:
    if (
        len(set(trusted_signers)) != len(trusted_signers)
        or any(not signer for signer in trusted_signers)
    ):
        return False
    if metadata.signature.signer_id not in trusted_signers:
        return False
    if metadata.version < floor.minimum_version and not metadata.authorized_rollback:
        return False
    return True
