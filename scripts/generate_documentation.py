#!/usr/bin/env python3
"""Validate a generated-document manifest/spec without mutating human documentation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from skeleton.documentation.runtime import (
    DocumentationSource, GeneratedDocument, GeneratedSection, GeneratorIdentity,
    SourceDigestSet, SourceKind, generated_manifest,
)


def build(spec):
    generator = GeneratorIdentity(**spec["generator"])
    sources = SourceDigestSet(tuple(
        DocumentationSource(
            source_id=item["source_id"],
            kind=SourceKind(item["kind"]),
            path=item["path"],
            digest=item["digest"],
        )
        for item in spec["sources"]
    ))
    sections = tuple(
        GeneratedSection(
            section_id=item["section_id"],
            source_digest_set=sources.digest,
            generator_digest=generator.digest,
            body=item["body"],
        )
        for item in spec["sections"]
    )
    return GeneratedDocument(path=spec["path"], generator=generator, source_set=sources, sections=sections)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    manifest = generated_manifest(build(spec))
    encoded = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.manifest:
        current = args.manifest.read_text(encoding="utf-8") if args.manifest.exists() else None
        if current != encoded:
            raise SystemExit("generated manifest drift")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
