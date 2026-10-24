"""Compatibility namespace for deployment strategies, plus the self-host plane.

New code should import deployment *strategies* from
:mod:`skeleton.deploy.strategies`; the four strategy names below remain
compatibility re-exports.

The self-host plane lives here (stdlib-only, import-light):

* :mod:`.profile` — declarative self-host profiles rendered to ``SKL_*`` env;
* :mod:`.validation` — fail-closed, coded configuration validation;
* :mod:`.envfile` — dotenv parse/render/redaction with 0600 atomic writes;
* :mod:`.health` — startup/liveness/readiness host checks and HTTP probes;
* :mod:`.manifest` — reproducible packaging manifest (Dockerfile parity);
* :mod:`.units` — hardened systemd and compose renderers;
* :mod:`.boot` — the one-command local boot sequence;
* :mod:`.cli` — ``python -m skeleton deploy``.
"""

from skeleton.deploy.strategies import (
    BlueGreenDeployer,
    CanaryController,
    EnvironmentManager,
    ReleaseNotesGenerator,
)

from .boot import BootOptions, Booter, BootResult, boot, child_environment
from .health import CheckKind, CheckRegistry, CheckStatus, HealthReport, build_preflight_registry
from .manifest import PackageManifest, build_manifest, verify_manifest
from .profile import SelfHostProfile, get_profile, list_profiles, resolve_profile
from .validation import DeploymentConfigError, ValidationReport, validate_profile

__all__ = [
    "BlueGreenDeployer",
    "CanaryController",
    "EnvironmentManager",
    "ReleaseNotesGenerator",
    # self-host plane
    "BootOptions",
    "BootResult",
    "Booter",
    "CheckKind",
    "CheckRegistry",
    "CheckStatus",
    "DeploymentConfigError",
    "HealthReport",
    "PackageManifest",
    "SelfHostProfile",
    "ValidationReport",
    "boot",
    "build_manifest",
    "build_preflight_registry",
    "child_environment",
    "get_profile",
    "list_profiles",
    "resolve_profile",
    "validate_profile",
    "verify_manifest",
]
