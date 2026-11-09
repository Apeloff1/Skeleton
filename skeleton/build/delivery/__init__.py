"""Build and deploy tooling (mass-build 2026-10-31, DevOps slice).

Pure, deterministic, non-executing contracts for packaging, artifact
manifests, release planning, environment configuration, deploy plans,
health evaluation, promotion gates and rollback. Nothing here opens a
network connection or spawns a process; runtime adapters consume the
plans emitted by these modules.

This package extends B008 (``skeleton.build.remote_build``) and the build
farm (``skeleton.ai.build.build_farm``) through ``remote_bridge`` and
``farm_bridge`` instead of duplicating them.
"""

from __future__ import annotations

DELIVERY_SCHEMA = 1

__all__ = ["DELIVERY_SCHEMA"]
