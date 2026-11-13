"""Streaming all-project source assurance for the canonical original studio.

Per-entry source identity and logical continuity are audited without claiming
native gameplay or using a provider. No skipped/bad project is quietly
converted into success; receipts are deterministic over ordered source input.
"""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

from .studio_ecosystem_catalog import (
    ROOT, catalog_index, StudioEcosystemError,
)
from .studio_ecosystem_continuity import audit_catalog_continuity
from .studio_ecosystem_quest import StudioQuestError


def audit_all_studio_sources(*, root: Path = ROOT, minimum_projects: int = 512,
                             max_error_details: int = 32) -> dict[str, object]:
    if (type(minimum_projects) is not int or minimum_projects < 1
            or type(max_error_details) is not int
            or not 1 <= max_error_details <= 256):
        raise StudioEcosystemError("invalid assurance envelope")
    records = catalog_index(root=root)
    bad = []
    failures = 0
    consistent = 0
    sha = sha256(b"skeleton.game_builder.studio_continuity_corpus.v1\n")
    for entry in records:
        pid = entry["id"]
        try:
            receipt = audit_catalog_continuity(pid, root=root)
            valid = receipt["source_consistent"]
            detail = receipt["errors"] if not valid else ()
            digest = receipt["source_digest"]
        except (StudioEcosystemError, StudioQuestError, OSError,
                ValueError, TypeError) as exc:
            valid = False
            detail = (type(exc).__name__,)
            digest = ""
        consistent += int(valid)
        failures += int(not valid)
        if not valid and len(bad) < max_error_details:
            bad.append({"project_id": pid, "errors": list(detail)})
        line = json.dumps({"id": pid, "source_digest": digest, "valid": valid},
                          ensure_ascii=True, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
        sha.update(line.encode("ascii") + b"\n")
    sufficient = len(records) >= minimum_projects
    return {
        "schema": "skeleton.game_builder.studio_continuity_corpus.v1",
        "status": ("source_consistent_with_release_holds"
                   if failures == 0 and sufficient else "source_rejected"),
        "source_consistent": failures == 0 and sufficient,
        "indexed_projects": len(records),
        "document_sections_expected": len(records) * 8,
        "minimum_required_projects": minimum_projects,
        "consistent_projects": consistent,
        "rejected_projects": failures,
        "truncated_error_details": failures > len(bad),
        "errors": bad,
        "source_chain_sha256": sha.hexdigest(),
        "release_certified": False,
        "native_genre_runtime_verified": False,
        "external_evidence_verified": False,
    }
