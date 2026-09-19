"""Deterministic logical-toolchain authority manifests and drift analysis."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from types import MappingProxyType
from typing import Iterable, Mapping

from skeleton.shells.provenance import canonical_json
from skeleton.shells.toolchains.types import CommandRisk, LogicalCommandContract

SCHEMA_VERSION = "shell-toolchain-authority/v1"

_RISK_ORDER = {
    CommandRisk.LOW.value: 0,
    CommandRisk.MODERATE.value: 1,
    CommandRisk.HIGH.value: 2,
}


@dataclass(frozen=True)
class ContractAuthorityRecord:
    name: str
    executable_key: str
    risk: str
    effects: tuple[str, ...]
    tags: tuple[str, ...]
    capabilities: tuple[str, ...]
    environment_keys: tuple[str, ...]
    max_timeout: float | None
    allow_stdin: bool
    allow_nonzero_success: bool
    argument_digest: str
    environment_digest: str
    contract_digest: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "executable_key": self.executable_key,
            "risk": self.risk,
            "effects": list(self.effects),
            "tags": list(self.tags),
            "capabilities": list(self.capabilities),
            "environment_keys": list(self.environment_keys),
            "max_timeout": self.max_timeout,
            "allow_stdin": self.allow_stdin,
            "allow_nonzero_success": self.allow_nonzero_success,
            "argument_digest": self.argument_digest,
            "environment_digest": self.environment_digest,
            "contract_digest": self.contract_digest,
        }


@dataclass(frozen=True)
class ToolchainAuthorityManifest:
    schema_version: str
    records: tuple[ContractAuthorityRecord, ...]
    digest: str

    def __post_init__(self) -> None:
        names = [record.name for record in self.records]
        if names != sorted(names):
            raise ValueError("manifest records must be sorted by name")
        if len(names) != len(set(names)):
            raise ValueError("manifest contract names must be unique")
        if len(self.digest) != 64:
            raise ValueError("manifest digest must be SHA-256 hex")

    @property
    def by_name(self) -> Mapping[str, ContractAuthorityRecord]:
        return MappingProxyType({record.name: record for record in self.records})

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "records": [record.to_dict() for record in self.records],
            "digest": self.digest,
        }


@dataclass(frozen=True)
class AuthorityChange:
    name: str
    fields: tuple[str, ...]
    widening_fields: tuple[str, ...]
    before_digest: str = ""
    after_digest: str = ""

    @property
    def widening(self) -> bool:
        return bool(self.widening_fields)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "fields": list(self.fields),
            "widening_fields": list(self.widening_fields),
            "widening": self.widening,
            "before_digest": self.before_digest,
            "after_digest": self.after_digest,
        }


@dataclass(frozen=True)
class AuthorityManifestDiff:
    before_digest: str
    after_digest: str
    added: tuple[str, ...]
    removed: tuple[str, ...]
    changed: tuple[AuthorityChange, ...]

    @property
    def widening(self) -> bool:
        return bool(self.added) or any(change.widening for change in self.changed)

    @property
    def narrowing_only(self) -> bool:
        return not self.widening and bool(self.removed or self.changed)

    @property
    def unchanged(self) -> bool:
        return not self.added and not self.removed and not self.changed

    def to_dict(self) -> dict[str, object]:
        return {
            "before_digest": self.before_digest,
            "after_digest": self.after_digest,
            "added": list(self.added),
            "removed": list(self.removed),
            "changed": [change.to_dict() for change in self.changed],
            "widening": self.widening,
            "narrowing_only": self.narrowing_only,
            "unchanged": self.unchanged,
        }


def _subdigest(value: object) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def authority_record(contract: LogicalCommandContract) -> ContractAuthorityRecord:
    payload = contract.to_dict()
    arguments = payload["arguments"]
    environment = payload["environment"]
    argument_digest = _subdigest(arguments)
    environment_digest = _subdigest(environment)
    contract_digest = _subdigest(payload)
    return ContractAuthorityRecord(
        name=contract.name,
        executable_key=contract.executable_key,
        risk=contract.risk.value,
        effects=tuple(sorted(effect.value for effect in contract.effects)),
        tags=tuple(sorted(contract.tags)),
        capabilities=tuple(
            sorted(capability.value for capability in contract.required_capabilities)
        ),
        environment_keys=tuple(contract.environment.allowed_keys()),
        max_timeout=contract.max_timeout,
        allow_stdin=contract.allow_stdin,
        allow_nonzero_success=contract.allow_nonzero_success,
        argument_digest=argument_digest,
        environment_digest=environment_digest,
        contract_digest=contract_digest,
    )


def build_authority_manifest(
    contracts: Iterable[LogicalCommandContract],
) -> ToolchainAuthorityManifest:
    records = tuple(
        sorted(
            (authority_record(contract) for contract in contracts),
            key=lambda record: record.name,
        )
    )
    names = [record.name for record in records]
    if len(names) != len(set(names)):
        raise ValueError("cannot build authority manifest with duplicate names")
    body = {
        "schema_version": SCHEMA_VERSION,
        "records": [record.to_dict() for record in records],
    }
    digest = _subdigest(body)
    return ToolchainAuthorityManifest(SCHEMA_VERSION, records, digest)


def verify_authority_manifest(manifest: ToolchainAuthorityManifest) -> bool:
    if manifest.schema_version != SCHEMA_VERSION:
        return False
    body = {
        "schema_version": manifest.schema_version,
        "records": [record.to_dict() for record in manifest.records],
    }
    return _subdigest(body) == manifest.digest


def _set_widened(before: tuple[str, ...], after: tuple[str, ...]) -> bool:
    return bool(set(after) - set(before))


def _timeout_widened(before: float | None, after: float | None) -> bool:
    if before is None:
        return False
    if after is None:
        return True
    return after > before


def _risk_widened(before: str, after: str) -> bool:
    return _RISK_ORDER[after] > _RISK_ORDER[before]


def _changed_fields(
    before: ContractAuthorityRecord,
    after: ContractAuthorityRecord,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    changed: list[str] = []
    widening: list[str] = []

    scalar_pairs = (
        ("executable_key", before.executable_key, after.executable_key),
        ("risk", before.risk, after.risk),
        ("max_timeout", before.max_timeout, after.max_timeout),
        ("allow_stdin", before.allow_stdin, after.allow_stdin),
        (
            "allow_nonzero_success",
            before.allow_nonzero_success,
            after.allow_nonzero_success,
        ),
        ("argument_digest", before.argument_digest, after.argument_digest),
        ("environment_digest", before.environment_digest, after.environment_digest),
    )
    for name, left, right in scalar_pairs:
        if left != right:
            changed.append(name)

    set_pairs = (
        ("effects", before.effects, after.effects),
        ("tags", before.tags, after.tags),
        ("capabilities", before.capabilities, after.capabilities),
        ("environment_keys", before.environment_keys, after.environment_keys),
    )
    for name, left, right in set_pairs:
        if left != right:
            changed.append(name)
            if _set_widened(left, right):
                widening.append(name)

    if before.executable_key != after.executable_key:
        widening.append("executable_key")
    if _risk_widened(before.risk, after.risk):
        widening.append("risk")
    if _timeout_widened(before.max_timeout, after.max_timeout):
        widening.append("max_timeout")
    if not before.allow_stdin and after.allow_stdin:
        widening.append("allow_stdin")
    if not before.allow_nonzero_success and after.allow_nonzero_success:
        widening.append("allow_nonzero_success")

    # Grammar and environment rule changes cannot be proven narrowing from
    # digests alone, so fail closed and require human/policy review.
    if before.argument_digest != after.argument_digest:
        widening.append("argument_digest")
    if before.environment_digest != after.environment_digest:
        widening.append("environment_digest")

    return tuple(sorted(set(changed))), tuple(sorted(set(widening)))


def diff_authority_manifests(
    before: ToolchainAuthorityManifest,
    after: ToolchainAuthorityManifest,
) -> AuthorityManifestDiff:
    if not verify_authority_manifest(before):
        raise ValueError("before authority manifest failed verification")
    if not verify_authority_manifest(after):
        raise ValueError("after authority manifest failed verification")

    old = before.by_name
    new = after.by_name
    added = tuple(sorted(set(new) - set(old)))
    removed = tuple(sorted(set(old) - set(new)))
    changed: list[AuthorityChange] = []

    for name in sorted(set(old) & set(new)):
        left = old[name]
        right = new[name]
        if left.contract_digest == right.contract_digest:
            continue
        fields, widening = _changed_fields(left, right)
        changed.append(
            AuthorityChange(
                name=name,
                fields=fields,
                widening_fields=widening,
                before_digest=left.contract_digest,
                after_digest=right.contract_digest,
            )
        )

    return AuthorityManifestDiff(
        before.digest,
        after.digest,
        added,
        removed,
        tuple(changed),
    )


def require_no_authority_widening(
    before: ToolchainAuthorityManifest,
    after: ToolchainAuthorityManifest,
) -> AuthorityManifestDiff:
    diff = diff_authority_manifests(before, after)
    if diff.widening:
        details = []
        if diff.added:
            details.append("added=" + ",".join(diff.added))
        for change in diff.changed:
            if change.widening:
                details.append(
                    change.name + ":" + ",".join(change.widening_fields)
                )
        raise RuntimeError(
            "toolchain authority widening requires explicit approval: "
            + "; ".join(details)
        )
    return diff
