#!/usr/bin/env python3
"""Validate a generated-document manifest/spec without mutating human documentation."""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from skeleton.documentation.runtime import (
    DocumentationSource, GeneratedDocument, GeneratedSection, GeneratorIdentity,
    SourceDigestSet, SourceKind, assert_clean_regeneration, generated_manifest,
    render_generated_document,
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
    parser.add_argument("--template", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-output", action="store_true")
    args = parser.parse_args()
    spec = json.loads(args.spec.read_text(encoding="utf-8"))
    document = build(spec)
    manifest = generated_manifest(document)
    encoded = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.manifest:
        current = args.manifest.read_text(encoding="utf-8") if args.manifest.exists() else None
        if current != encoded:
            raise SystemExit("generated manifest drift")
    else:
        print(encoded, end="")

    if args.check_output and not args.output:
        raise SystemExit("--check-output requires --output")
    if args.output and not args.template:
        raise SystemExit("--output requires --template")
    if args.template:
        template = args.template.read_text(encoding="utf-8")
        generated = render_generated_document(template, document)
        if args.output:
            if args.check_output:
                current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
                assert_clean_regeneration(current, generated)
            else:
                args.output.write_text(generated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
