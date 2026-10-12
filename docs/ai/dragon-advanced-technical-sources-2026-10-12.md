# Dragon advanced technical source atlas — 2026-10-12

This source-ingestion work adds **55 editorial entry-point leads** in 12 families: game engines/editors, native runtime, graphics APIs, audio, homebrew/retro hardware, programming/compiler debugging, software security, AI, research, accessibility, delivery and intellectual property. This is a *separately measured* source shortlist, **not** an increase of 55 independently reviewed websites over the pre-existing 12,777 raw discovery-lead chain. Many curated URLs may overlap that chain.

## Technical workflow

- Source identities use the existing Dragon canonical HTTP URL normalization and source SHA-256 namespace.
- A trusted operator's `import` operation atomically adds previously absent unreviewed source metadata, nested technical-topic almanac memberships, digest-chained editorial history, and stage-0 jobs in the **existing** DragonAlmanacs/SequentialAlmanacWorker queue. It preserves existing source bodies and input digests; replay of unchanged metadata adds no duplicate jobs or events.
- Editorial events contain the supplied UTC epoch, source ID, revision, parent digest and changes in parentheses, e.g. `(new candidate; no source content inspected)` or `(topics: metadata revised)`. The timestamp is an editorial record time, **not** evidence that the remote site was updated.
- A deterministic `plan` queries curated concepts against the current task and expands bounded adjacent terms such as NPC→agents/testing/dialogue; crawler→security/rights/research; retro→ROM/sprites/audio; editor→accessibility/serialization. The plan lists direct and adjacent matches, topic family, recommended review interval, canonical policy state, and unknown page freshness. Its score is **not a statistical quality probability**.
- Owner isolation, bounded user inputs, one-host caps, immutable previous records, corrupt-history refusal and stale policy-input refusal are regression-tested.

## Operator commands

Run from the repository root against a provisioned owner-specific local SQLite library:

```sh
python -m skeleton.ai.game_builder.dragon_technical_source_cli census \
  --database /approved/studio.sqlite --owner studio --trusted-local-operator
python -m skeleton.ai.game_builder.dragon_technical_source_cli import \
  --database /approved/studio.sqlite --owner studio --trusted-local-operator \
  --recorded-at "$(date -u +%s)"
python -m skeleton.ai.game_builder.dragon_technical_source_cli plan \
  --database /approved/studio.sqlite --owner studio --trusted-local-operator \
  --query "gameboy retro rom errors" --limit 20
```

The existing authenticated crawler (not this CLI) must subsequently acquire each source through network/SSRF/redirect/robots/terms/consent/resource checks, capture original source revision evidence, perform rights and independent factual review, and submit evidence to Wiki/HOAG for promotion. Public technical documentation does not imply permission to reproduce protected works or to train on their contents. Suggested review days are operator planning hints, not a bypass of any lease, clock or crawl policy.

## Exact-head validation

```sh
python -m pytest -q --noconftest tests/test_dragon_technical_source_atlas.py
python -m compileall -q skeleton/ai/game_builder
```

The Dragon AI Verification workflow includes the new regression module. A passing test suite validates the metadata/queue code, **not** online source availability, published rights approval, actual acquired pages, independent verified facts, real neural-weight improvement or a production rollout. A user or trusted operator must authorize source import and subsequent crawling; importing into a checked-out branch does not automatically mutate a deployed database.

## Next measurable completion gates

1. Operator-approved import against a staged tenant; count unique new source IDs rather than raw link strings.
2. Policy-approved fetch of each destination with revision hashes, observed response timestamp, media-specific extraction and source-specific rights declarations.
3. Source-to-claim provenance with diff and revisit receipts; independent Wiki factual review and HOAG presentation only on verified evidence.
4. Keep article, video and source-change gatherers idle-only, workload admitted, and strictly subordinate to foreground activity.
5. Benchmark task-relevant knowledge gain using independent original game-building tests before any separate weight-admission request.
