# Durable original-studio production plane — qualification boundaries

This documentation describes the **stacked draft** after #4431, including 20 new PRs #4432–#4451. It does not certify an app installation, native genre support, GPU coherency, audio/asset generation, consumer delivery, or release.

## Implemented in source

The existing authoring catalog has 512 original production briefs × eight linked documents = 4,096 authored section files. The new runtime builds on the previously drafted scene/quest replay, alternative route, social faction, resource conservation, original asset/audio planning, full-section source manifests, dependency DAGs and hardware-adaptive capacity plans.

A private SQLite `studio_work.sqlite3` journal now persists producer tasks with WAL, synchronous FULL, private file permissions, graph identity, transaction-serialized claims, hashed worker capability tokens, independent reviewer decisions, and explicit operator recovery. Original content identity is pinned before the first work event; the application refuses subsequent eight-section changes. The durable event history is checked through SHA-256 canonical chaining **and** replayed against each mutable task row; this is locally detectable integrity, not cryptographic external attestation against an operator who controls the entire database.

A separate private content-addressed `objects` spool streams untrusted local producer bytes to temporary files and atomically links committed SHA-256 objects without overwriting existing data. Reads verify object hashes and check a bounded requested byte window; the spool census reports incomplete staging and corruption without deleting historical data. An individual large source object can exceed host RAM because it is streamed in chunks, subject to available disk and measured reserve. This is application-managed disk storage, **not** physical RAM enlargement or GPU/Metal tensor paging.

The source-fenced `StudioSupervisor` combines the journal, spool, project source pin, operator-reviewed submission, local restart inspection, an actual winning **existing 2D HTML5 grid-maze preview** compiler output and hash-addressed quest replay save/restore. Review acceptance is only `reviewed_claim`, never evidence of actual native play, source rights, generated 3D art, or release.

## Local owner-only CLI

Create an existing private work directory with owner-only permissions on POSIX, e.g. `mkdir -m 700 .studio-private`. Do not place secrets or object stores under public static or versioned web directories.

Use `python -m scripts.studio_work_operator --root .studio-private --project studio_arena_fighting_glacial_fjord status` for recovery and source checks, or `... preview` for an actual **grid-only** compiled HTML5 artifact receipt.

For claim/submit, supply a long random private token through the `SKELETON_STUDIO_WORK_TOKEN` environment variable, not a command-line argument. Example suffix: `claim --task source-canon --worker local-author`, followed by `submit --task source-canon --worker local-author --artifact /trusted/path/original.txt`. An independent reviewer can use `review --task source-canon --reviewer reviewer-id --accept`, but that grants planning progression only, not release. `pause --operator owner-id` / `resume-admission --operator owner-id` gate fresh claims without taking over in-flight tasks; `recover --task TASK --former-worker WORKER --attempt N --operator OWNER` performs explicit compare-and-swap owner recovery. `audit-spool` checks all local objects without deleting any.

## Required validation and hard holds

Run after full stacked branch completion:

```bash
python -m pytest -q tests/test_studio_ecosystem_journal.py tests/test_studio_ecosystem_spool.py tests/test_studio_ecosystem_filing.py tests/test_studio_ecosystem_fence.py tests/test_studio_ecosystem_recovery.py tests/test_studio_ecosystem_supervisor.py tests/test_studio_ecosystem_preview_worker.py tests/test_studio_ecosystem_checkpoint_store.py tests/test_studio_ecosystem_spool_audit.py tests/test_studio_work_operator.py tests/test_studio_private_production_e2e.py
python -m compileall -q skeleton/ai/game_builder scripts
```

These drafts remain **uncertified** until their exact-head required CI, frontend/backend/security policies, source rights and target-device integration evidence complete. Historical success, skipped draft checks, queued/cancelled runs and authoring simulations never count as completed release certification. Do not squash the stacked chain out of order; each small draft's base depends on the preceding one. Keep GitHub size limits and security gates intact. 

Known limitations: local Python/SQLite single-host coordination rather than distributed workers, no automatic OS process manager, no persistent materialized native 3D assets, no cross-owner signed provenance, no true producer GPU KV ownership or driver sync, no released full genre gameplay. Next layers require real engine adapters, media pipelines, device-qualified benchmarking, and independent evidence attestation.
