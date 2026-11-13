# Arena Forge Author — atomic equipment and stage editing

This builder-facing CLI edits source-bound tactical equipment progression
without mutating the input or partially publishing an invalid source.
Operations: add/remove recipe, change recipe stats or costs, change stage
salvage drops and replace authored arena geometry/actors.

    python -m skeleton arena-forge-author demo
    python -m skeleton arena-forge-author patch --source-json SOURCE --edits-json EDITS
    python -m skeleton arena-forge-author verify --report-json REPORT

After edits, the entire source is revalidated, then the bounded forge solver
previews actual gameplay using the canonical tactical engine. An inconclusive
budget-limited preview is never mislabeled as unwinnable. Reports preserve
original source, edits, result, replay digests and preview.

Maximum 32 edits and 2 MiB report. No arbitrary code execution, network,
provider calls, untrusted rewards or filesystem writes.

    python -m pytest skeleton/testing/test_arena_forge_author.py -q

Reports are integrity evidence, not cryptographic signatures or release proof.
