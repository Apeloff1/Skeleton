# Exhaustive authored-source continuity receipts

`python -m scripts.check_studio_ecosystem_continuity --json` reads every
registered studio project, validates all eight source sections and their
quest, scene, cast, asset/audio and QA contracts, and streams deterministic
per-project source hashes into a final SHA-256 receipt.

Individual invalid project reports are bounded in displayed error details,
**not omitted from the failure count or digest**. The required baseline is
at least 512 project entries but not an upper cap on future authoring.

`python -m scripts.check_studio_ecosystem_continuity --project studio_arena_fighting_glacial_fjord --json`
runs the same check for a single source.

A clean source audit remains *not* native or consumer release certification,
game execution proof, artistic asset validation, or evidence of actual devices.
