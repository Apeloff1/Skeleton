"""Bundle-level schema migrations on the GF-B save plane.

Scope: only the bundle sections (``bundle``, ``files``) and the receipts they
seal. Any other section (for example gameplay state, whose schema versions are
owned by B025) is passed through byte-for-byte and never migrated here.

- ``v0`` is the legacy pre-bundle layout: a single ``workspace`` section
  ``{"project", "genre", "files": {path: text}}`` with inline text and no
  receipts. :func:`upgrade_legacy_workspace` turns it into the v1 layout.
- :func:`install_bundle_migrations` registers that step through
  ``GameSavePlane.register_migration(0, ...)`` (call once per plane).
- Saves or bundles newer than this runtime are rejected (the plane rejects a
  newer ``schema_version``; :func:`check_bundle_schema` rejects a newer
  ``bundle_schema_version``).
"""
from __future__ import annotations

from typing import Any, Callable, Dict

from skeleton.kernel.game_save_plane import GameSavePlane

from .manifest import BUNDLE_SCHEMA_VERSION, BundleError
from .project_save import build_state

LEGACY_SECTION = "workspace"
# Future bundle-section steps: {from_bundle_version: fn(sections) -> sections}.
BUNDLE_STEPS: Dict[int, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}


def upgrade_legacy_workspace(state: Dict[str, Any]) -> Dict[str, Any]:
    sections = dict(state.get("sections", {}))
    legacy = sections.pop(LEGACY_SECTION, None)
    if legacy is None:
        return state  # not a bundle save; leave every section untouched
    if "bundle" in sections or "files" in sections:
        raise BundleError("legacy workspace save also carries bundle sections")
    try:
        files = {str(p): str(t) for p, t in dict(legacy["files"]).items()}
        new, receipts = build_state(legacy["project"], legacy["genre"], files, label="legacy-v0")
    except (KeyError, TypeError) as exc:
        raise BundleError("malformed legacy workspace save") from exc
    sections.update(new)
    out = dict(state)
    out["sections"] = sections
    out["receipts"] = receipts.to_state()
    out["receipt_root"] = receipts.root()
    return out


def install_bundle_migrations(plane: GameSavePlane) -> None:
    plane.register_migration(0, upgrade_legacy_workspace)


def check_bundle_schema(sections: Dict[str, Any]) -> Dict[str, Any]:
    """Step bundle sections up to BUNDLE_SCHEMA_VERSION; reject too-new."""
    version = int(sections["bundle"].get("bundle_schema_version", BUNDLE_SCHEMA_VERSION))
    if version > BUNDLE_SCHEMA_VERSION:
        raise BundleError("bundle schema is newer than this runtime")
    out = dict(sections)
    while version < BUNDLE_SCHEMA_VERSION:
        step = BUNDLE_STEPS.get(version)
        if step is None:
            raise BundleError(f"missing bundle migration from {version}")
        out = step(out)
        version += 1
        out["bundle"] = {**out["bundle"], "bundle_schema_version": version}
    return out


__all__ = ["LEGACY_SECTION", "BUNDLE_STEPS", "upgrade_legacy_workspace",
           "install_bundle_migrations", "check_bundle_schema"]
