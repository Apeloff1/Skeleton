"""Public runtime bootstrap contract for the assembled Skeleton application.

This module intentionally exposes only topology metadata that is safe for
browser/native clients: application identity, profile membership, dependency
order, service roles, and declared public health paths. Internal URLs,
environment values, container details, and secrets are excluded.
"""

from __future__ import annotations

from skeleton.app.assembly import AssemblyManifest, load_manifest
from skeleton.app.plan import build_plan


def public_bootstrap_payload(
    manifest: AssemblyManifest | None = None,
) -> dict[str, object]:
    """Return the canonical client-safe application bootstrap document."""

    manifest = manifest or load_manifest()
    default_plan = build_plan(manifest=manifest, full=False)
    full_plan = build_plan(manifest=manifest, full=True)
    default_names = set(default_plan.services)
    full_names = set(full_plan.services)

    services: list[dict[str, object]] = []
    for service in manifest.services:
        services.append(
            {
                "name": service.name,
                "role": service.role,
                "kind": service.kind,
                "canonical": service.canonical,
                "profile": service.profile,
                "health_path": service.health_path,
                "ingress_prefix": service.ingress_prefix,
                "depends_on": list(service.depends_on),
                "default": service.name in default_names,
                "full": service.name in full_names,
            }
        )

    return {
        "schema_version": 1,
        "application": {
            "name": manifest.name,
            "version": manifest.version,
            "assembly_schema_version": manifest.schema_version,
        },
        "contract": {
            "bootstrap": manifest.contract_path("bootstrap"),
            "status": manifest.contract_path("status"),
            "ready": manifest.contract_path("ready"),
        },
        "profiles": {
            "default": {
                "services": list(default_plan.services),
                "layers": [list(layer) for layer in default_plan.layers],
            },
            "full": {
                "services": list(full_plan.services),
                "layers": [list(layer) for layer in full_plan.layers],
            },
        },
        "services": services,
    }
