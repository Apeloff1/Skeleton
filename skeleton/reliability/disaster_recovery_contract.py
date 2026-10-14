"""Topology-wide disaster-recovery contract for hostile gap G012.

Existing REL-04/REL-05 code qualifies backup/restore evidence and disaster
recovery drills. This module closes a different architectural hole: every
current source-of-truth domain must be represented by one machine-readable
recovery unit before the repository can claim a complete disaster-recovery
contract.

The validator is fail closed on:
* source-of-truth domains added or removed without plan reconciliation;
* owner or physical-store drift between topology and recovery plan;
* missing required backup-policy stores;
* duplicate recovery ownership;
* invalid restore ordering/dependencies;
* missing executable evidence;
* global traffic admission before every global recovery unit verifies;
* derived/projection recovery ordered before authoritative restoration.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "skeleton.ai.disaster_recovery_contract.v1"
ALLOWED_STRATEGIES = frozenset(
    {
        "sqlite-online-backup-restore",
        "mongo-logical-backup-restore",
        "operator-journal-preserve",
        "restore-then-reconcile",
        "rebuild-from-authority",
    }
)


class DisasterRecoveryContractError(RuntimeError):
    """The machine disaster-recovery contract is incomplete or inconsistent."""


def _text(value: object, field: str, *, maximum: int = 256) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise DisasterRecoveryContractError(
            f"{field} must be canonical non-empty text"
        )
    if len(value) > maximum:
        raise DisasterRecoveryContractError(f"{field} exceeds maximum length")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise DisasterRecoveryContractError(f"{field} contains control characters")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise DisasterRecoveryContractError(f"{field} must be a positive integer")
    return value


def _canonical_digest(value: object) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DisasterRecoveryContractError(
            "disaster recovery contract must be canonical JSON"
        ) from exc
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _string_tuple(
    values: object,
    field: str,
    *,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(values, list):
        raise DisasterRecoveryContractError(f"{field} must be a list")
    normalized = tuple(sorted({_text(item, field) for item in values}))
    if not normalized and not allow_empty:
        raise DisasterRecoveryContractError(f"{field} must be non-empty")
    if list(normalized) != values:
        raise DisasterRecoveryContractError(
            f"{field} must be sorted and duplicate-free"
        )
    return normalized


@dataclass(frozen=True, slots=True)
class RecoveryUnit:
    unit_id: str
    strategy: str
    restore_order: int
    domain_ids: tuple[str, ...]
    backup_policy_store_ids: tuple[str, ...]
    depends_on_units: tuple[str, ...]
    rto_seconds: int
    rpo_seconds: int
    required_for_global_traffic: bool
    verification_refs: tuple[str, ...]
    post_restore_checks: tuple[str, ...]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "RecoveryUnit":
        required = {
            "unit_id",
            "strategy",
            "restore_order",
            "domain_ids",
            "backup_policy_store_ids",
            "depends_on_units",
            "rto_seconds",
            "rpo_seconds",
            "required_for_global_traffic",
            "verification_refs",
            "post_restore_checks",
        }
        if set(raw) != required:
            raise DisasterRecoveryContractError(
                f"recovery unit schema drift: {sorted(set(raw) ^ required)}"
            )
        strategy = _text(raw["strategy"], "strategy")
        if strategy not in ALLOWED_STRATEGIES:
            raise DisasterRecoveryContractError(
                f"unsupported recovery strategy {strategy!r}"
            )
        traffic = raw["required_for_global_traffic"]
        if not isinstance(traffic, bool):
            raise DisasterRecoveryContractError(
                "required_for_global_traffic must be boolean"
            )
        return cls(
            unit_id=_text(raw["unit_id"], "unit_id"),
            strategy=strategy,
            restore_order=_positive_int(raw["restore_order"], "restore_order"),
            domain_ids=_string_tuple(
                raw["domain_ids"],
                "domain_ids",
                allow_empty=True,
            ),
            backup_policy_store_ids=_string_tuple(
                raw["backup_policy_store_ids"],
                "backup_policy_store_ids",
                allow_empty=True,
            ),
            depends_on_units=_string_tuple(
                raw["depends_on_units"],
                "depends_on_units",
                allow_empty=True,
            ),
            rto_seconds=_positive_int(raw["rto_seconds"], "rto_seconds"),
            rpo_seconds=_positive_int(raw["rpo_seconds"], "rpo_seconds"),
            required_for_global_traffic=traffic,
            verification_refs=_string_tuple(
                raw["verification_refs"],
                "verification_refs",
            ),
            post_restore_checks=_string_tuple(
                raw["post_restore_checks"],
                "post_restore_checks",
            ),
        )

    def payload(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "strategy": self.strategy,
            "restore_order": self.restore_order,
            "domain_ids": list(self.domain_ids),
            "backup_policy_store_ids": list(self.backup_policy_store_ids),
            "depends_on_units": list(self.depends_on_units),
            "rto_seconds": self.rto_seconds,
            "rpo_seconds": self.rpo_seconds,
            "required_for_global_traffic": self.required_for_global_traffic,
            "verification_refs": list(self.verification_refs),
            "post_restore_checks": list(self.post_restore_checks),
        }

    @property
    def digest(self) -> str:
        return _canonical_digest(self.payload())


@dataclass(frozen=True, slots=True)
class RecoveryContractReport:
    valid: bool
    errors: tuple[str, ...]
    source_of_truth_domains: tuple[str, ...]
    covered_domains: tuple[str, ...]
    required_backup_stores: tuple[str, ...]
    covered_backup_stores: tuple[str, ...]
    unit_digests: tuple[str, ...]
    contract_digest: str

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": "skeleton.ai.disaster_recovery_contract_report.v1",
            "valid": self.valid,
            "errors": list(self.errors),
            "source_of_truth_domains": list(self.source_of_truth_domains),
            "covered_domains": list(self.covered_domains),
            "required_backup_stores": list(self.required_backup_stores),
            "covered_backup_stores": list(self.covered_backup_stores),
            "unit_digests": list(self.unit_digests),
            "contract_digest": self.contract_digest,
        }


def validate_disaster_recovery_contract(
    *,
    topology: Mapping[str, Any],
    backup_policy: Mapping[str, Any],
    contract: Mapping[str, Any],
    repository_root: Path | None = None,
) -> RecoveryContractReport:
    """Validate exact recovery coverage against topology and backup authority."""

    errors: list[str] = []

    if contract.get("schema_version") != SCHEMA:
        errors.append("disaster recovery contract schema drift")
    if contract.get("status") != "active":
        errors.append("disaster recovery contract must be active")
    if contract.get("gap_id") != "G012":
        errors.append("disaster recovery contract gap identity drift")
    if contract.get("topology_contract") != "machine/state_topology.json":
        errors.append("topology contract path drift")
    if contract.get("backup_policy") != "machine/state_backup_policy.json":
        errors.append("backup policy path drift")

    invariants = contract.get("invariants")
    if not isinstance(invariants, list) or any(
        not isinstance(item, str) or not item.strip() for item in invariants
    ):
        errors.append("contract invariants must be a non-empty text list")
        invariants = []
    elif not invariants:
        errors.append("contract invariants must be non-empty")

    domains_raw = topology.get("state_domains")
    if not isinstance(domains_raw, list):
        raise DisasterRecoveryContractError("topology state_domains must be a list")
    source_domains: dict[str, Mapping[str, Any]] = {}
    for raw in domains_raw:
        if not isinstance(raw, Mapping):
            raise DisasterRecoveryContractError("topology domain must be an object")
        if raw.get("source_of_truth") is True:
            domain_id = _text(raw.get("id"), "topology.domain.id")
            if domain_id in source_domains:
                raise DisasterRecoveryContractError(
                    f"duplicate topology source-of-truth domain {domain_id}"
                )
            source_domains[domain_id] = raw

    expectations = contract.get("domain_expectations")
    if not isinstance(expectations, Mapping):
        errors.append("domain_expectations must be an object")
        expectations = {}
    expected_ids = set(expectations)
    source_ids = set(source_domains)
    for missing in sorted(source_ids - expected_ids):
        errors.append(f"domain expectation missing: {missing}")
    for extra in sorted(expected_ids - source_ids):
        errors.append(f"unknown domain expectation: {extra}")
    for domain_id in sorted(source_ids & expected_ids):
        expected = expectations[domain_id]
        if not isinstance(expected, Mapping) or set(expected) != {
            "authority", "owner_plane", "physical_store"
        }:
            errors.append(f"{domain_id} domain expectation schema drift")
            continue
        actual = source_domains[domain_id]
        for field in ("authority", "owner_plane", "physical_store"):
            try:
                wanted = _text(expected.get(field), f"{domain_id}.{field}")
                observed = _text(actual.get(field), f"topology.{domain_id}.{field}")
            except DisasterRecoveryContractError as exc:
                errors.append(str(exc))
                continue
            if wanted != observed:
                errors.append(
                    f"{domain_id} {field} drift: expected {wanted}, got {observed}"
                )

    stores_raw = backup_policy.get("stores")
    if not isinstance(stores_raw, list):
        raise DisasterRecoveryContractError("backup policy stores must be a list")
    backup_stores: dict[str, Mapping[str, Any]] = {}
    required_backup_stores: set[str] = set()
    for raw in stores_raw:
        if not isinstance(raw, Mapping):
            raise DisasterRecoveryContractError("backup store must be an object")
        store_id = _text(raw.get("id"), "backup.store.id")
        if store_id in backup_stores:
            raise DisasterRecoveryContractError(
                f"duplicate backup policy store {store_id}"
            )
        backup_stores[store_id] = raw
        if raw.get("required") is True:
            required_backup_stores.add(store_id)

    raw_units = contract.get("recovery_units")
    if not isinstance(raw_units, list) or not raw_units:
        errors.append("recovery_units must be a non-empty list")
        raw_units = []

    units: list[RecoveryUnit] = []
    unit_by_id: dict[str, RecoveryUnit] = {}
    orders: dict[int, str] = {}
    for index, raw in enumerate(raw_units):
        if not isinstance(raw, Mapping):
            errors.append(f"recovery unit {index} must be an object")
            continue
        try:
            unit = RecoveryUnit.from_mapping(raw)
        except DisasterRecoveryContractError as exc:
            errors.append(f"recovery unit {index}: {exc}")
            continue
        if unit.unit_id in unit_by_id:
            errors.append(f"duplicate recovery unit {unit.unit_id}")
            continue
        if unit.restore_order in orders:
            errors.append(
                f"duplicate restore_order {unit.restore_order}: "
                f"{orders[unit.restore_order]} and {unit.unit_id}"
            )
        orders[unit.restore_order] = unit.unit_id
        unit_by_id[unit.unit_id] = unit
        units.append(unit)

    covered_domains: dict[str, str] = {}
    covered_backup_stores: dict[str, str] = {}

    for unit in units:
        if not unit.domain_ids and not unit.backup_policy_store_ids:
            errors.append(
                f"{unit.unit_id} owns neither domains nor backup-policy stores"
            )
        for domain_id in unit.domain_ids:
            domain = source_domains.get(domain_id)
            if domain is None:
                errors.append(
                    f"{unit.unit_id} references non-source-of-truth domain {domain_id}"
                )
                continue
            prior = covered_domains.get(domain_id)
            if prior is not None:
                errors.append(
                    f"source-of-truth domain {domain_id} has duplicate recovery owners "
                    f"{prior} and {unit.unit_id}"
                )
            covered_domains[domain_id] = unit.unit_id
            authority = domain.get("authority")
            if (
                authority == "authoritative"
                and not unit.required_for_global_traffic
            ):
                errors.append(
                    f"{domain_id} is authoritative but recovery unit "
                    f"{unit.unit_id} does not gate global traffic"
                )

        for store_id in unit.backup_policy_store_ids:
            if store_id not in backup_stores:
                errors.append(
                    f"{unit.unit_id} references unknown backup-policy store {store_id}"
                )
                continue
            prior = covered_backup_stores.get(store_id)
            if prior is not None:
                errors.append(
                    f"backup-policy store {store_id} has duplicate recovery owners "
                    f"{prior} and {unit.unit_id}"
                )
            covered_backup_stores[store_id] = unit.unit_id

        for dependency in unit.depends_on_units:
            dependency_unit = unit_by_id.get(dependency)
            if dependency_unit is None:
                errors.append(
                    f"{unit.unit_id} depends on unknown recovery unit {dependency}"
                )
            elif dependency_unit.restore_order >= unit.restore_order:
                errors.append(
                    f"{unit.unit_id} dependency {dependency} must restore earlier"
                )

        if repository_root is not None:
            for ref in unit.verification_refs:
                path = repository_root / ref
                if not path.exists():
                    errors.append(
                        f"{unit.unit_id} verification ref missing: {ref}"
                    )

    source_set = set(source_domains)
    covered_set = set(covered_domains)
    for missing in sorted(source_set - covered_set):
        errors.append(f"uncovered source-of-truth domain: {missing}")
    for extra in sorted(covered_set - source_set):
        errors.append(f"unexpected covered domain: {extra}")

    covered_store_set = set(covered_backup_stores)
    for missing in sorted(required_backup_stores - covered_store_set):
        errors.append(f"uncovered required backup-policy store: {missing}")

    global_units = [u for u in units if u.required_for_global_traffic]
    if not global_units:
        errors.append("at least one recovery unit must gate global traffic")

    admission = contract.get("traffic_admission")
    if not isinstance(admission, Mapping):
        errors.append("traffic_admission must be an object")
    else:
        if admission.get("requires_all_global_units_verified") is not True:
            errors.append(
                "traffic admission must require all global units verified"
            )
        if admission.get("derived_rebuild_after_authority") is not True:
            errors.append(
                "derived rebuild must occur after authoritative recovery"
            )
        if admission.get("fail_closed_on_unknown_unit") is not True:
            errors.append(
                "traffic admission must fail closed on unknown recovery units"
            )

    contract_digest = _canonical_digest(contract)
    return RecoveryContractReport(
        valid=not errors,
        errors=tuple(sorted(set(errors))),
        source_of_truth_domains=tuple(sorted(source_set)),
        covered_domains=tuple(sorted(covered_set)),
        required_backup_stores=tuple(sorted(required_backup_stores)),
        covered_backup_stores=tuple(sorted(covered_store_set)),
        unit_digests=tuple(sorted(unit.digest for unit in units)),
        contract_digest=contract_digest,
    )


def validate_repository_disaster_recovery(
    root: str | Path,
) -> RecoveryContractReport:
    """Load and validate the canonical machine contracts from one repo root."""

    repository_root = Path(root)
    try:
        topology = json.loads(
            (repository_root / "machine/state_topology.json").read_text(
                encoding="utf-8"
            )
        )
        backup_policy = json.loads(
            (repository_root / "machine/state_backup_policy.json").read_text(
                encoding="utf-8"
            )
        )
        contract = json.loads(
            (repository_root / "machine/disaster_recovery_contract.json").read_text(
                encoding="utf-8"
            )
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise DisasterRecoveryContractError(
            "cannot load disaster recovery machine contracts"
        ) from exc
    if not all(isinstance(item, Mapping) for item in (topology, backup_policy, contract)):
        raise DisasterRecoveryContractError(
            "disaster recovery machine contracts must be objects"
        )
    return validate_disaster_recovery_contract(
        topology=topology,
        backup_policy=backup_policy,
        contract=contract,
        repository_root=repository_root,
    )


__all__ = [
    "ALLOWED_STRATEGIES",
    "DisasterRecoveryContractError",
    "RecoveryContractReport",
    "RecoveryUnit",
    "SCHEMA",
    "validate_disaster_recovery_contract",
    "validate_repository_disaster_recovery",
]
