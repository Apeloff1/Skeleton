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
    preflight,
)
from skeleton.app.health import ProbeResult, probe_application, probe_url, probes_ok

__all__ = [
    "AssemblyCheck",
    "AssemblyManifest",
    "ServiceSpec",
    "compose_command",
    "find_repo_root",
    "load_manifest",
    "preflight",
    "ProbeResult",
    "probe_application",
    "probe_url",
    "probes_ok",
]
