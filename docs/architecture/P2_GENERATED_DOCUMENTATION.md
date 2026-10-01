# P2 Generated Documentation

Machine authority: `machine/generated_documentation.json`
Generator: `scripts/generate_p2_docs.py`

This lane implements the masterplan gaps in VOL-089 and VOL-090.

Only files explicitly declared by the machine manifest under `docs/generated/` are writable by the generator. Human-authored documentation, rationale, warnings, ADRs, and operational notes outside that root are never overwritten.

Every generated artifact contains:

- a do-not-edit marker;
- generator identity/version;
- the Git blob identity of every machine source;
- deterministic ordering and formatting.

`python scripts/generate_p2_docs.py --check` renders the artifacts in memory and requires byte-for-byte equality with the committed files. Source changes therefore invalidate stale generated docs, and manual edits fail the same clean-regeneration gate.

Generated documents are navigational snapshots only. They cannot override machine authority, sign P2 tasks, close evidence debt, or promote maturity.
