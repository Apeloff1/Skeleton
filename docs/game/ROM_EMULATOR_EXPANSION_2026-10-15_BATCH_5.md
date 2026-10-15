# Emulator core expansion and native-learning evidence — October 15, 2026, batch 5

## Changes

Pinned operator source-build recipes increase from **75 to 83**. This batch adds:
- bNES (NES);
- three distinct bsnes-mercury binaries: accuracy, balanced, and performance (SNES);
- MAME 2003 (legacy Neo Geo candidate);
- MAME 2016 (general driver catalog, all machine scopes explicitly unqualified);
- FB Alpha 2012 Neo Geo (legacy arcade candidate);
- DOSBox Core (DOS/Win16 machine candidate).

All eight are **deferred source recipes**. Upstream full commit identifiers, Linux makefile paths, artifacts and mandatory license locations are encoded in the installer and in `machine/ai_game_emulator_catalog.json`. The canonical Jeeves emulator catalog and compatibility mirror are updated identically. An upstream build invocation may need changes on a real Linux host; no compilation, gameplay or ABI execution has been carried out.

## Native AI training trace export

The existing `EmulatorEnvironment` now exposes `capture_training_trace(actions, seed=..., rights_evidence_digest=...)`. It executes real, isolated native frames, not reference-game simulation. Each transition binds the controller digest, frame SHA-256, prior transition hash, audio frame count, frame callbacks and observed rewards to the current core, ROM content digest, firmware, options, source code and registry identities.

The resulting `skeleton.game.trace.v1` object is passed through the **existing** bounded `_validate_trace` ingestor, requiring continuous observations, exact component totals, terminal state, bounded length and complete trace digest. It does **not** supply a training algorithm, model weight update, synthetic replay label, ROM license certificate, gameplay-success result, or hardware compatibility proof. Any rights digest is an operator assertion, not verified legal authorization.

```python
# Only after an approved native core and lawful content have been installed:
observation = environment.capture_training_trace(
    ["idle", "right", "a", "left", "idle"],
    seed=5,
    rights_evidence_digest=None,
)
# Result can be submitted to the existing governed offline trace ingestion path.
# No training/promotion occurs in capture_training_trace itself.
```

## Safety/security constraints L00–L13

- L00–L02: Ownership remains in the existing Jeeves native emulator host, catalog/installer and ingestion schema. No external provider, direct model weights owner or new background execution service.
- L03–L04: Source pin is not runtime approval. Exact operator core registry, native process sandbox and ELF symbol evidence are still required. `candidate_only=True` on all new recipes.
- L05–L06: Existing path protection, hash-bound media dependencies, bounded ZIP expansion/CRC, immutable local artifacts, firmware and source rights guards remain. Arcade ZIP retention is explicitly allowlisted only for exact core IDs and still checked against the live worker `block_extract`.
- L07–L08: Compiler logs and native frame/audio/controller/lineage SHA receipts are separately inspectable. Fail closed on foreign core, content digest, unknown controller, missing evidence, changed source or broken trace bounds.
- L09: Build concurrency, timeout, on-core frames, episode horizon, trace size and native worker resource caps remain bounded. MAME builds require exceptional storage/time/operator preflight.
- L10: No native binaries or homebrew ROMs were executed in this patch; actual build, ABI/architecture, save state, disc swaps, input fidelity, frame/audio timing, deterministic replay and training evaluation remain open.
- L11–L12: Explicit `--core` installation, reversible deferred core admission and normal Git revert. No broad bulk rollout of the new cores.
- L13: No proof of model accuracy improvement, parameter change, learned weight, canonical game victory or legal ROM-rights verification is claimed.

## Commands

```bash
python3 scripts/install_game_emulator_cores.py --coverage-matrix
python3 scripts/install_game_emulator_cores.py --list-cores
# Example explicit candidate fetch/compile; no game is run by the installer:
python3 scripts/install_game_emulator_cores.py --source-root /srv/skeleton-emulator-sources \
  --install-root /srv/skeleton-emulators --fetch-sources --core bnes --core bsnes_mercury_accuracy --jobs 2
```

**83 source recipes ≠ 83 verified emulators ≠ 169 target machines supported.**

## Additional pre-install and installed-instance audits

```bash
python3 scripts/install_game_emulator_cores.py --validate-recipes
python3 scripts/install_game_emulator_cores.py --installed-audit --install-root /srv/skeleton-emulators
```

The first command fail-closes on a mismatch between **all 83** pinned source revisions in the installer and the machine contract, invalid source URLs/Makefile/artifact/license paths, duplicate/unknown hardware IDs or unsafe Make variables. The second is strictly local, read-only, and checks actual currently operator-approved ELF SHA-256/ABI and bounded declared firmware inventory. Deferred candidates remain marked deferred; mismatching approved artifacts are separately marked invalid. Neither command executes ROMs, compiles source, promotes weights, accesses licensed SDKs nor certifies gameplay.

## Multi-run replay mirror audit (two through ten native captures)

After explicit operator installation and approval on a qualified host, capture multiple real libretro episodes under **identical** core, firmware, ROM content, seed and action sequence. Capture receipts include distinct 128-bit random nonces to distinguish separate recording calls; nonces do not prove process independence or externally attest source authenticity.

```python
from skeleton.jeeves.game_emulator_replay_audit import compare_emulator_replays

# env is an approved EmulatorEnvironment bound to lawful game content.
first = env.capture_training_trace(["idle", "right", "a", "idle"], seed=8)
second = env.capture_training_trace(["idle", "right", "a", "idle"], seed=8)
audit = compare_emulator_replays([first, second])
# Alternative: EmulatorEnvironment.audit_training_replays([first, second])
```

The audit uses the canonical `skeleton.game.trace.v1` offline validator before comparison. It verifies matching source/firmware/core/content/options and controls, then separately counts divergences in video pixel digests, PCM audio digests, observation/reward values, native callbacks and hash-chain receipts. It reports the first divergent step and a bounded per-run breakdown. The returned status **self_reported_replay_consistent** does not imply a perfect hardware emulator, lawful rights, a correct game result, an independently attested execution or a trained model. Any mismatch remains fail-visible; no automatic candidate or weight promotion.

This mirror audit does not schedule runs, execute cores itself, replay or download ROMs, or bypass the operator's existing libretro sandbox. Native execution, smoke tests and deterministic replay qualification remain to be performed on the real target host.
