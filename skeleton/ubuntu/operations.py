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

from .package import *
from .package import __all__ as _package_all
from .service import *
from .service import __all__ as _service_all
from .network import *
from .network import __all__ as _network_all
from .storage import *
from .storage import __all__ as _storage_all
from .runtime import *
from .runtime import __all__ as _runtime_all
from .security import *
from .security import __all__ as _security_all
from .cloud import *
from .cloud import __all__ as _cloud_all
from .ci import *
from .ci import __all__ as _ci_all

MAX_CONTRACT_ID = 9000
_CONTRACT_NAME_RE = re.compile(r"^ubuntu_contract_(\\d+)$")

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
]
