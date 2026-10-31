# Original studio local-media and production continuation — 30 October 2026

This tranche extends the existing 4,096 authored source documents and previous durable producer drafts. **Code is a stacked, unmerged draft**, not a native game-engine certification or completed consumer product.

## Actual implemented output

The production plane can now generate an original 1280×720 source-palette-derived SVG environment, a short **original generated** 16 kHz mono PCM/WAV instrumental ambience, and the existing genuinely playable deterministic HTML5 grid preview. The three are exported as a private offline sandbox with `studio.html`, `index.html`, `environment.svg`, `soundscape.wav` and an exact canonical `manifest.json`. The previewed grid remains distinct from the project's target genre. Media is rendered, but the full asset set, score, rights and target hardware remain unqualified.

Verified content-addressed streaming protects source and output from symlink/hardlink and reopen races. A single descriptor supplies both file hashing and bounded selected content. Producer object entries receive directory fsync on POSIX. Durable journal task mutations replay the hash-linked event history before altering the SQLite ledger. Existing output is never overwritten. Incomplete directories can be **manually** moved into a private quarantine without deleting content, and resumption revalidates complete five-file packages against current eight-section source identity.

## High-throughput operator workflows

With a private work root and a separate private output root already created by the operator:

```bash
mkdir -m 700 .studio-work .studio-output
python -m scripts.studio_ecosystem_production_cli \
    --private-root .studio-work --output-root .studio-output \
    --project studio_aerial_traversal_amber_highlands

python -m scripts.studio_ecosystem_production_cli \
    --private-root .studio-work --output-root .studio-output \
    --all --genre puzzle_expedition
```

`--all` is explicit. Each project gets an isolated private journal and artifact spool; dynamic CPU/RAM/disk checks gate new work before each project, with an operator-supplied working-set and output-size estimate. If measured capacity is insufficient, the batch reports the first deferred project without inventing success. Source catalog index admission now grows with measured free physical memory rather than a fixed 256 KiB size. Individual authoring sections retain their existing strict 32 KiB source input validation, pending a separate authenticated streaming-source design.

## Real signals and their limits

Local QA measures SVG shape count, actual PCM frames, peak/RMS, build elapsed time, disk-use deltas and hash correctness. The corpus-level source audit checks all registered project source schemas with explicit failure counts. These are **not** substitutes for human artistic review, cross-device visual/audio fidelity, accessible final mixers, native GPU tensors, original-rights licensing or signed provenance.

Partial exports require manual quarantine before rerunning, and existing complete bundles must pass exact file digests plus current source manifests before reuse. No automatic deletion. No unsupported swap/Metal migration. No reviewer claims are silently elevated into external proof or signed releases.

## Focused validation when the stack is ready

```bash
python -m pytest -q \
  tests/test_studio_ecosystem_spool.py \
  tests/test_studio_ecosystem_spool_commit.py \
  tests/test_studio_ecosystem_vector_art.py \
  tests/test_studio_ecosystem_synth_audio.py \
  tests/test_studio_ecosystem_assets.py \
  tests/test_studio_ecosystem_media_worker.py \
  tests/test_studio_ecosystem_offline_bundle.py \
  tests/test_studio_ecosystem_offline_verify.py \
  tests/test_studio_ecosystem_portfolio.py \
  tests/test_studio_ecosystem_preview_batch.py \
  tests/test_studio_ecosystem_production_cli.py \
  tests/test_studio_ecosystem_media_quality.py \
  tests/test_studio_ecosystem_incomplete_quarantine.py \
  tests/test_studio_ecosystem_resume_batch.py \
  tests/test_studio_ecosystem_media_corpus.py \
  tests/test_studio_ecosystem_adaptive_index.py
python -m compileall -q skeleton/ai/game_builder scripts
```

Also validate the complete earlier studio production/Jeeves integration tests and all GitHub exact-head release/security requirements. Cancelled, skipped, draft-bypassed or superseded results are never approvals. Keep the entire stacked branch chain draft until verified. This runbook describes implementation intent, not proof that the commands were executed or passed.
