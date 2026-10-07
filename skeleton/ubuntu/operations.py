"""Stable facade for declarative Ubuntu host operations.

The original 9k-line delivery mixed real resource policy with thousands of
cloned compatibility wrappers. The policy is now split by domain while this
facade preserves the public resource classes and helpers and adds registry,
evidence, diff, digest, and compatibility primitives.

This module never executes host commands.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from .model import MAX_TEXT, UbuntuAction, UbuntuPlan, _clean, merge_plans, validate_plan

from .package import (
    PackageAptPlan,
    PackageSnapPlan,
    PackageDebPlan,
    PackageRepoPlan,
    PackagePinPlan,
    PackageHoldPlan,
    PackageCachePlan,
    PackageMirrorPlan,
    PackageKeyringPlan,
    PackagePolicyPlan,
    validate_package_apt,
    plan_package_apt,
    audit_package_apt,
    validate_package_snap,
    plan_package_snap,
    audit_package_snap,
    validate_package_deb,
    plan_package_deb,
    audit_package_deb,
    validate_package_repo,
    plan_package_repo,
    audit_package_repo,
    validate_package_pin,
    plan_package_pin,
    audit_package_pin,
    validate_package_hold,
    plan_package_hold,
    audit_package_hold,
    validate_package_cache,
    plan_package_cache,
    audit_package_cache,
    validate_package_mirror,
    plan_package_mirror,
    audit_package_mirror,
    validate_package_keyring,
    plan_package_keyring,
    audit_package_keyring,
    validate_package_policy,
    plan_package_policy,
    audit_package_policy,
)
from .package import __all__ as _package_all
from .service import (
    ServiceSystemdPlan,
    ServiceSocketPlan,
    ServiceTimerPlan,
    ServiceTargetPlan,
    ServiceUnitPlan,
    ServiceJournalPlan,
    ServiceRestartPlan,
    ServiceEnablePlan,
    ServiceMaskPlan,
    ServiceHealthPlan,
    validate_service_systemd,
    plan_service_systemd,
    audit_service_systemd,
    validate_service_socket,
    plan_service_socket,
    audit_service_socket,
    validate_service_timer,
    plan_service_timer,
    audit_service_timer,
    validate_service_target,
    plan_service_target,
    audit_service_target,
    validate_service_unit,
    plan_service_unit,
    audit_service_unit,
    validate_service_journal,
    plan_service_journal,
    audit_service_journal,
    validate_service_restart,
    plan_service_restart,
    audit_service_restart,
    validate_service_enable,
    plan_service_enable,
    audit_service_enable,
    validate_service_mask,
    plan_service_mask,
    audit_service_mask,
    validate_service_health,
    plan_service_health,
    audit_service_health,
)
from .service import __all__ as _service_all
from .network import (
    NetworkNetplanPlan,
    NetworkDnsPlan,
    NetworkRoutePlan,
    NetworkBridgePlan,
    NetworkBondPlan,
    NetworkVlanPlan,
    NetworkMtuPlan,
    NetworkFirewallPlan,
    NetworkProxyPlan,
    NetworkTlsPlan,
    validate_network_netplan,
    plan_network_netplan,
    audit_network_netplan,
    validate_network_dns,
    plan_network_dns,
    audit_network_dns,
    validate_network_route,
    plan_network_route,
    audit_network_route,
    validate_network_bridge,
    plan_network_bridge,
    audit_network_bridge,
    validate_network_bond,
    plan_network_bond,
    audit_network_bond,
    validate_network_vlan,
    plan_network_vlan,
    audit_network_vlan,
    validate_network_mtu,
    plan_network_mtu,
    audit_network_mtu,
    validate_network_firewall,
    plan_network_firewall,
    audit_network_firewall,
    validate_network_proxy,
    plan_network_proxy,
    audit_network_proxy,
    validate_network_tls,
    plan_network_tls,
    audit_network_tls,
)
from .network import __all__ as _network_all
from .storage import (
    StorageMountPlan,
    StorageFstabPlan,
    StorageDiskPlan,
    StoragePartitionPlan,
    StorageLvmPlan,
    StorageZfsPlan,
    StorageRaidPlan,
    StorageQuotaPlan,
    StorageTmpfsPlan,
    StorageBackupPlan,
    validate_storage_mount,
    plan_storage_mount,
    audit_storage_mount,
    validate_storage_fstab,
    plan_storage_fstab,
    audit_storage_fstab,
    validate_storage_disk,
    plan_storage_disk,
    audit_storage_disk,
    validate_storage_partition,
    plan_storage_partition,
    audit_storage_partition,
    validate_storage_lvm,
    plan_storage_lvm,
    audit_storage_lvm,
    validate_storage_zfs,
    plan_storage_zfs,
    audit_storage_zfs,
    validate_storage_raid,
    plan_storage_raid,
    audit_storage_raid,
    validate_storage_quota,
    plan_storage_quota,
    audit_storage_quota,
    validate_storage_tmpfs,
    plan_storage_tmpfs,
    audit_storage_tmpfs,
    validate_storage_backup,
    plan_storage_backup,
    audit_storage_backup,
)
from .storage import __all__ as _storage_all
from .runtime import (
    RuntimePythonPlan,
    RuntimeDockerPlan,
    RuntimeContainerdPlan,
    RuntimePodmanPlan,
    RuntimeBuildxPlan,
    RuntimeQemuPlan,
    RuntimeGccPlan,
    RuntimeNodePlan,
    RuntimeUvPlan,
    RuntimePipPlan,
    validate_runtime_python,
    plan_runtime_python,
    audit_runtime_python,
    validate_runtime_docker,
    plan_runtime_docker,
    audit_runtime_docker,
    validate_runtime_containerd,
    plan_runtime_containerd,
    audit_runtime_containerd,
    validate_runtime_podman,
    plan_runtime_podman,
    audit_runtime_podman,
    validate_runtime_buildx,
    plan_runtime_buildx,
    audit_runtime_buildx,
    validate_runtime_qemu,
    plan_runtime_qemu,
    audit_runtime_qemu,
    validate_runtime_gcc,
    plan_runtime_gcc,
    audit_runtime_gcc,
    validate_runtime_node,
    plan_runtime_node,
    audit_runtime_node,
    validate_runtime_uv,
    plan_runtime_uv,
    audit_runtime_uv,
    validate_runtime_pip,
    plan_runtime_pip,
    audit_runtime_pip,
)
from .runtime import __all__ as _runtime_all
from .security import (
    SecurityApparmorPlan,
    SecurityAuditPlan,
    SecurityPermissionsPlan,
    SecurityLimitsPlan,
    SecuritySysctlPlan,
    SecuritySshPlan,
    SecuritySudoPlan,
    SecuritySecretsPlan,
    SecurityCertPlan,
    SecurityKernelPlan,
    validate_security_apparmor,
    plan_security_apparmor,
    audit_security_apparmor,
    validate_security_audit,
    plan_security_audit,
    audit_security_audit,
    validate_security_permissions,
    plan_security_permissions,
    audit_security_permissions,
    validate_security_limits,
    plan_security_limits,
    audit_security_limits,
    validate_security_sysctl,
    plan_security_sysctl,
    audit_security_sysctl,
    validate_security_ssh,
    plan_security_ssh,
    audit_security_ssh,
    validate_security_sudo,
    plan_security_sudo,
    audit_security_sudo,
    validate_security_secrets,
    plan_security_secrets,
    audit_security_secrets,
    validate_security_cert,
    plan_security_cert,
    audit_security_cert,
    validate_security_kernel,
    plan_security_kernel,
    audit_security_kernel,
)
from .security import __all__ as _security_all
from .cloud import (
    CloudCloudinitPlan,
    CloudMetadataPlan,
    CloudIdentityPlan,
    CloudInstancePlan,
    CloudUserdataPlan,
    CloudProvisionPlan,
    CloudImagePlan,
    CloudAgentPlan,
    CloudHealthPlan,
    CloudTagsPlan,
    validate_cloud_cloudinit,
    plan_cloud_cloudinit,
    audit_cloud_cloudinit,
    validate_cloud_metadata,
    plan_cloud_metadata,
    audit_cloud_metadata,
    validate_cloud_identity,
    plan_cloud_identity,
    audit_cloud_identity,
    validate_cloud_instance,
    plan_cloud_instance,
    audit_cloud_instance,
    validate_cloud_userdata,
    plan_cloud_userdata,
    audit_cloud_userdata,
    validate_cloud_provision,
    plan_cloud_provision,
    audit_cloud_provision,
    validate_cloud_image,
    plan_cloud_image,
    audit_cloud_image,
    validate_cloud_agent,
    plan_cloud_agent,
    audit_cloud_agent,
    validate_cloud_health,
    plan_cloud_health,
    audit_cloud_health,
    validate_cloud_tags,
    plan_cloud_tags,
    audit_cloud_tags,
)
from .cloud import __all__ as _cloud_all
from .ci import (
    CiRunnerPlan,
    CiCachePlan,
    CiArtifactPlan,
    CiWorkspacePlan,
    CiCheckoutPlan,
    CiToolchainPlan,
    CiTestPlan,
    CiLintPlan,
    CiCoveragePlan,
    CiPublishPlan,
    validate_ci_runner,
    plan_ci_runner,
    audit_ci_runner,
    validate_ci_cache,
    plan_ci_cache,
    audit_ci_cache,
    validate_ci_artifact,
    plan_ci_artifact,
    audit_ci_artifact,
    validate_ci_workspace,
    plan_ci_workspace,
    audit_ci_workspace,
    validate_ci_checkout,
    plan_ci_checkout,
    audit_ci_checkout,
    validate_ci_toolchain,
    plan_ci_toolchain,
    audit_ci_toolchain,
    validate_ci_test,
    plan_ci_test,
    audit_ci_test,
    validate_ci_lint,
    plan_ci_lint,
    audit_ci_lint,
    validate_ci_coverage,
    plan_ci_coverage,
    audit_ci_coverage,
    validate_ci_publish,
    plan_ci_publish,
    audit_ci_publish,
)
from .ci import __all__ as _ci_all


MAX_CONTRACT_ID = 9000
_CONTRACT_NAME_RE = re.compile(r"^ubuntu_contract_(\d+)$")
_COMPAT_CONTRACT_NAMES = tuple(
    f"ubuntu_contract_{contract_id}"
    for contract_id in range(4050, MAX_CONTRACT_ID + 1, 6)
)

_RESOURCE_IDS = (
    "package_apt",
    "package_snap",
    "package_deb",
    "package_repo",
    "package_pin",
    "package_hold",
    "package_cache",
    "package_mirror",
    "package_keyring",
    "package_policy",
    "service_systemd",
    "service_socket",
    "service_timer",
    "service_target",
    "service_unit",
    "service_journal",
    "service_restart",
    "service_enable",
    "service_mask",
    "service_health",
    "network_netplan",
    "network_dns",
    "network_route",
    "network_bridge",
    "network_bond",
    "network_vlan",
    "network_mtu",
    "network_firewall",
    "network_proxy",
    "network_tls",
    "storage_mount",
    "storage_fstab",
    "storage_disk",
    "storage_partition",
    "storage_lvm",
    "storage_zfs",
    "storage_raid",
    "storage_quota",
    "storage_tmpfs",
    "storage_backup",
    "runtime_python",
    "runtime_docker",
    "runtime_containerd",
    "runtime_podman",
    "runtime_buildx",
    "runtime_qemu",
    "runtime_gcc",
    "runtime_node",
    "runtime_uv",
    "runtime_pip",
    "security_apparmor",
    "security_audit",
    "security_permissions",
    "security_limits",
    "security_sysctl",
    "security_ssh",
    "security_sudo",
    "security_secrets",
    "security_cert",
    "security_kernel",
    "cloud_cloudinit",
    "cloud_metadata",
    "cloud_identity",
    "cloud_instance",
    "cloud_userdata",
    "cloud_provision",
    "cloud_image",
    "cloud_agent",
    "cloud_health",
    "cloud_tags",
    "ci_runner",
    "ci_cache",
    "ci_artifact",
    "ci_workspace",
    "ci_checkout",
    "ci_toolchain",
    "ci_test",
    "ci_lint",
    "ci_coverage",
    "ci_publish",
)


@dataclass(frozen=True, slots=True)
class ResourceSpec:
    """Stable identity for one declarative Ubuntu resource family."""

    resource_id: str
    domain: str
    resource: str
    class_name: str

    @property
    def key_prefix(self) -> str:
        return f"{self.domain}-{self.resource}"

    @property
    def argv_prefix(self) -> tuple[str, str, str]:
        return ("ubuntu", self.domain, self.resource)


def _class_name(resource_id: str) -> str:
    return "".join(part.title() for part in resource_id.split("_")) + "Plan"


RESOURCE_SPECS: tuple[ResourceSpec, ...] = tuple(
    ResourceSpec(
        resource_id=resource_id,
        domain=resource_id.split("_", 1)[0],
        resource=resource_id.split("_", 1)[1],
        class_name=_class_name(resource_id),
    )
    for resource_id in _RESOURCE_IDS
)

_RESOURCE_BY_ID: Mapping[str, ResourceSpec] = MappingProxyType(
    {spec.resource_id: spec for spec in RESOURCE_SPECS}
)
_RESOURCE_BY_KEY: Mapping[str, ResourceSpec] = MappingProxyType(
    {spec.key_prefix: spec for spec in RESOURCE_SPECS}
)

if len(_RESOURCE_BY_ID) != len(RESOURCE_SPECS):
    raise RuntimeError("duplicate Ubuntu resource ids")
if len(_RESOURCE_BY_KEY) != len(RESOURCE_SPECS):
    raise RuntimeError("duplicate Ubuntu resource key prefixes")


def resource_spec(resource_id: str) -> ResourceSpec:
    """Resolve one stable resource specification."""
    clean = _clean(resource_id)
    try:
        return _RESOURCE_BY_ID[clean]
    except KeyError as exc:
        raise KeyError(f"unknown Ubuntu resource: {clean}") from exc


def resource_specs(*, domain: str | None = None) -> tuple[ResourceSpec, ...]:
    """Return the immutable registry, optionally restricted to one domain."""
    if domain is None:
        return RESOURCE_SPECS
    clean = _clean(domain)
    return tuple(spec for spec in RESOURCE_SPECS if spec.domain == clean)


def plan_resources(resource_id: str, identifiers: Sequence[str]) -> UbuntuPlan:
    """Plan a registered resource through its stable compatibility helper."""
    spec = resource_spec(resource_id)
    planner = globals()[f"plan_{spec.resource_id}"]
    return planner(identifiers)


def audit_resource(resource_id: str, plan: UbuntuPlan) -> Mapping[str, object]:
    """Audit a registered resource through its stable compatibility helper."""
    spec = resource_spec(resource_id)
    auditor = globals()[f"audit_{spec.resource_id}"]
    return auditor(plan)


def canonical_plan_json(plan: UbuntuPlan) -> str:
    """Return deterministic JSON for evidence and cache identities."""
    if not isinstance(plan, UbuntuPlan):
        raise TypeError("plan must be UbuntuPlan")
    payload = {
        "actions": [
            {
                "argv": list(action.argv),
                "name": action.name,
                "reason": action.reason,
                "timeout_seconds": action.timeout_seconds,
            }
            for action in plan.actions
        ],
        "metadata": {key: plan.metadata[key] for key in sorted(plan.metadata)},
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def plan_digest(plan: UbuntuPlan) -> str:
    """Return SHA-256 identity of canonical declarative plan content."""
    return hashlib.sha256(canonical_plan_json(plan).encode("utf-8")).hexdigest()


def audit_plan(plan: UbuntuPlan) -> Mapping[str, object]:
    """Produce deterministic evidence for a complete plan."""
    errors = validate_plan(plan)
    counts: dict[str, int] = {}
    unknown: list[str] = []
    for action in plan.actions:
        prefix = action.name.split(":", 1)[0]
        if prefix not in _RESOURCE_BY_KEY:
            unknown.append(action.name)
            continue
        counts[prefix] = counts.get(prefix, 0) + 1
    return MappingProxyType(
        {
            "ok": not errors and not unknown,
            "errors": errors,
            "unknown_actions": tuple(unknown),
            "action_count": len(plan.actions),
            "resource_counts": MappingProxyType(dict(sorted(counts.items()))),
            "digest": plan_digest(plan),
        }
    )


@dataclass(frozen=True, slots=True)
class PlanDiff:
    """Deterministic action-identity diff."""

    added: tuple[str, ...]
    removed: tuple[str, ...]
    retained: tuple[str, ...]

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed)


def diff_plans(before: UbuntuPlan, after: UbuntuPlan) -> PlanDiff:
    """Compare two plans without executing either one."""
    if not isinstance(before, UbuntuPlan) or not isinstance(after, UbuntuPlan):
        raise TypeError("before and after must be UbuntuPlan")
    before_names = set(before.names())
    after_names = set(after.names())
    return PlanDiff(
        added=tuple(sorted(after_names - before_names)),
        removed=tuple(sorted(before_names - after_names)),
        retained=tuple(sorted(before_names & after_names)),
    )


def validate_resource_reference(name: str) -> tuple[ResourceSpec, str]:
    """Validate and split domain-resource:identifier identity."""
    clean = _clean(name)
    prefix, separator, identifier = clean.partition(":")
    if not separator:
        raise ValueError("resource reference must contain ':'")
    spec = _RESOURCE_BY_KEY.get(prefix)
    if spec is None:
        raise ValueError("unknown resource reference")
    return spec, _clean(identifier)


def _valid_contract_id(contract_id: int) -> bool:
    return (
        type(contract_id) is int
        and 4050 <= contract_id <= MAX_CONTRACT_ID
        and (contract_id - 4050) % 6 == 0
    )


def ubuntu_contract(value: str, contract_id: int) -> str:
    """Compact implementation of the historical numbered wrappers."""
    if type(contract_id) is not int:
        raise ValueError("contract id must be an integer")
    if not _valid_contract_id(contract_id):
        raise ValueError("unknown Ubuntu compatibility contract")
    clean = _clean(value)
    if clean.startswith("/"):
        raise ValueError("absolute identity rejected")
    return f"ubuntu-{contract_id}:{clean}"


def _compat_contract(contract_id: int) -> Callable[[str], str]:
    def contract(value: str) -> str:
        return ubuntu_contract(value, contract_id)

    contract.__name__ = f"ubuntu_contract_{contract_id}"
    contract.__qualname__ = contract.__name__
    contract.__doc__ = f"Bounded Ubuntu integration contract {contract_id}."
    return contract


def __getattr__(name: str) -> object:
    """Lazily preserve historical numbered Ubuntu contract attributes."""
    match = _CONTRACT_NAME_RE.fullmatch(name)
    if match is None:
        raise AttributeError(name)
    contract_id = int(match.group(1))
    if not _valid_contract_id(contract_id):
        raise AttributeError(name)
    value = _compat_contract(contract_id)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Expose historical compatibility attributes without eager function bodies."""
    return sorted(set(globals()) | set(_COMPAT_CONTRACT_NAMES))


_DOMAIN_EXPORTS = (
    *_package_all,
    *_service_all,
    *_network_all,
    *_storage_all,
    *_runtime_all,
    *_security_all,
    *_cloud_all,
    *_ci_all,
)

__all__ = [
    "MAX_CONTRACT_ID",
    "MAX_TEXT",
    "PlanDiff",
    "RESOURCE_SPECS",
    "ResourceSpec",
    "UbuntuAction",
    "UbuntuPlan",
    "audit_plan",
    "audit_resource",
    "canonical_plan_json",
    "diff_plans",
    "merge_plans",
    "plan_digest",
    "plan_resources",
    "resource_spec",
    "resource_specs",
    "ubuntu_contract",
    "validate_plan",
    "validate_resource_reference",
    *_DOMAIN_EXPORTS,
    *_COMPAT_CONTRACT_NAMES,
]
