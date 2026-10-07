"""Unified application assembly surface.

This package is the canonical operational boundary for the repository-wide
application.  It does not collapse independent runtimes into one Python
process; it gives them one manifest, one preflight contract and one launcher.
"""

from skeleton.app.assembly import (
    AssemblyCheck,
    AssemblyManifest,
    ServiceSpec,
    compose_command,
    find_repo_root,
    load_manifest,
    parse_manifest,
    preflight,
)
from skeleton.app.bootstrap import public_bootstrap_payload
from skeleton.app.health import ProbeResult, probe_application, probe_http, probe_url, probes_ok, wait_for_application
from skeleton.app.plan import AssemblyPlan, build_plan, dependency_closure, validate_manifest_topology

__all__ = [
    "AssemblyCheck",
    "AssemblyManifest",
    "ServiceSpec",
    "compose_command",
    "find_repo_root",
    "load_manifest",
    "parse_manifest",
    "preflight",
    "ProbeResult",
    "probe_application",
    "probe_http",
    "probe_url",
    "probes_ok",
    "wait_for_application",
    "AssemblyPlan",
    "build_plan",
    "dependency_closure",
    "validate_manifest_topology",
    "public_bootstrap_payload",
]
