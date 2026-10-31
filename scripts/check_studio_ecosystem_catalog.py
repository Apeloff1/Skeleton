"""Read-only completeness, uniqueness and explicit-release-hold audit.

This audit is a catalog-source check, NOT a consumer or device qualification.
Usage: python scripts/check_studio_ecosystem_catalog.py --json
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import (
    ROOT, SECTIONS, _read_bytes, catalog_index, compile_preview, read_blueprint,
    StudioEcosystemError,
)


def audit(*, compile_samples: bool = False, root: Path = ROOT) -> dict[str, object]:
    records = catalog_index(root=root)
    hashes: set[str] = set()
    problems: list[str] = []
    all_narrative_premises: set[str] = set()
    sample_per_genre: dict[str, str] = {}
    documents = 0
    for record in records:
        pid = record["id"]
        entry_dir = root / pid
        expected = {section + ".json" for section in SECTIONS}
        actual = {x.name for x in entry_dir.iterdir()} if entry_dir.is_dir() else set()
        if expected != actual:
            problems.append(pid + ": missing or unexpected source files")
            continue
        try:
            docs = read_blueprint(pid, root=root)
        except (StudioEcosystemError, OSError) as exc:
            problems.append(pid + ": " + str(exc))
            continue
        all_narrative_premises.add(docs["narrative"]["premise"])
        sample_per_genre.setdefault(record["genre"], pid)
        for section in SECTIONS:
            path = entry_dir / (section + ".json")
            try:
                # Do not reopen pathname after a symlink check: use the same
                # descriptor-anchored, bounded reader as the catalog loader.
                digest = sha256(_read_bytes(path, root=root)).hexdigest()
            except (StudioEcosystemError, OSError) as exc:
                problems.append(pid + ": unsafe source document: " + str(exc))
                continue
            if digest in hashes:
                problems.append(pid + ": duplicate or filler-identical document")
            hashes.add(digest)
            documents += 1
        if any(g.get("status") != "not_tested"
               for g in docs["verification"]["quality_gates"]):
            problems.append(pid + ": unearned quality certification")
    if len(all_narrative_premises) != len(records):
        problems.append("narrative premises are not unique")
    if documents != len(records) * len(SECTIONS):
        problems.append("project source files are incomplete")
    compiled = 0
    if compile_samples and not problems:
        for pid in sample_per_genre.values():
            try:
                result = compile_preview(pid, authorized=True, root=root)
                if result.proof.final_state.status != "won":
                    raise StudioEcosystemError("winning replay not achieved")
                compiled += 1
            except Exception as exc:
                problems.append(pid + ": preview compilation error " + str(exc))
    return {
        "schema": "skeleton.game_builder.studio_ecosystem.audit.v1",
        "status": "source_valid" if not problems else "source_rejected",
        "projects": len(records),
        "documents": documents,
        "unique_source_digests": len(hashes),
        "genres": len(sample_per_genre),
        "sample_compiles": compiled,
        "release_certified": False,
        "errors": problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit complete original studio content catalog")
    parser.add_argument("--json", action="store_true", help="Output one machine-readable receipt")
    parser.add_argument("--compile-samples", action="store_true",
                        help="Compile and verify one real offline grid preview per genre")
    args = parser.parse_args(argv)
    receipt = audit(compile_samples=args.compile_samples)
    if args.json:
        print(json.dumps(receipt, sort_keys=True, separators=(",", ":")))
    else:
        print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0 if not receipt["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
