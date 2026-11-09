"""Import-free audit of scaffold templates versus architecture.TEMPLATES."""

from __future__ import annotations

from typing import Final

from .audit_parse import architecture_templates, export_drift, scaffold_template_catalog
from .capability_manifest import CAPABILITY_MANIFEST_VERSION


TEMPLATE_AUDIT_KIND: Final = "template_audit"


def template_audit_snapshot() -> dict[str, object]:
    """Return a JSON-serializable scaffold/architecture template audit."""

    scaffold = scaffold_template_catalog()
    documented = architecture_templates()
    documented_map = {str(row["id"]): row for row in documented}
    scaffold_ids = [str(row["id"]) for row in scaffold]
    documented_ids = [str(row["id"]) for row in documented]
    extras = [name for name in scaffold_ids if name not in documented_map]
    names = documented_ids + extras
    scaffold_map = {str(row["id"]): row for row in scaffold}
    rows: list[dict[str, object]] = []
    for name in names:
        live = scaffold_map.get(name)
        architecture = documented_map.get(name)
        live_files = list(live["files"]) if live else []
        documented_files = list(architecture["files"]) if architecture else []
        rows.append(
            {
                "id": name,
                "in_scaffold": live is not None,
                "architecture_documented": architecture is not None,
                "scaffold_files": live_files,
                "architecture_files": documented_files,
                "file_drift": export_drift(
                    [item for item in live_files if isinstance(item, str)],
                    [item for item in documented_files if isinstance(item, str)],
                ),
            }
        )
    return {
        "schema_version": CAPABILITY_MANIFEST_VERSION,
        "kind": TEMPLATE_AUDIT_KIND,
        "templates": rows,
        "missing_from_architecture": extras,
        "missing_from_scaffold": [name for name in documented_ids if name not in scaffold_map],
    }


def get_template_audit_row(template_id: str) -> dict[str, object]:
    """Return one template-audit row by scaffold template ID."""

    if not isinstance(template_id, str):
        raise TypeError("template_id must be a string")
    normalized = template_id.strip().lower()
    if not normalized:
        raise ValueError("template_id must not be empty")
    for row in template_audit_snapshot()["templates"]:
        if row["id"] == normalized:
            return dict(row)
    raise KeyError(f"unknown template: {normalized}")
