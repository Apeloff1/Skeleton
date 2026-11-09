# Universal libretro time controls and paused asset inspection

**Status:** source implementation committed on the full-console feature branch; native fleet, rights-cleared game boots, compiled ABI timing and wall-clock speed improvements **not yet independently qualified**.

## Scope

Every core instantiated through `EmulatorEnvironment` (the common installed, pinned libretro host) now accepts `input_frame_step(controls, frames=1..60)`. This commands the existing isolated libretro worker to execute exactly that many `retro_run` calls. The core's binary and ROM are never patched. The host also exposes `inspect_frame()` on its currently checksum-validated RGB24 frame. The live comparison session adds one time profile per independent core lane, with optional local browser auto-advance.

These features do **not** magically enable non-libretro systems, GPU-render-only cores, exotic peripherals, uninstalled core binaries, copyrighted content, a game-specific scoring oracle or automatic production-model training. The canonical 169-target registry is a coverage catalog, **not** 169 certified playable consoles.

## Time modes

| Mode | Factor | Actual native work | Operator intent |
|---|---:|---|---|
| **Paused** | 0 | No `retro_run`, no state/step cursor change. Timing control and RGB inspection generate separate chained receipts. | Hold game scene for inspection |
| **Slow** | 2, 4, 8 | Exactly **1** native `retro_run` per step; automatic viewer delay targets 1/2, 1/4 or 1/8 of the native core's reported nominal FPS (bounded 10–240 Hz, 60 Hz fallback). | Locate transient assets, capture subtle effects and inspect movement |
| **Normal** | 1 | The approved game's configured 1–60 native frames per step. | Baseline observation and control |
| **Fast** | 2, 4, 8 | 2/4/8 **separate real native steps** per batch with the game's configured frames per step. Each step has its own frame/audio/control evidence; only the final PNG preview is transferred. | Reduced browser/request overhead for bounded exploration and training-data collection |

**Important:** speed multipliers describe requested native stepping/batching and browser pacing, not a guaranteed wall-clock acceleration, CPU overclock or internal libretro clock change. The live session measures per-burst wall time and receipted native frames/second; those numbers are not hardware accuracy proof. Source-only mode changes have no effect on model weights.

## Inspection fidelity and source custody

Paused inspection uses the real last host-held RGB24 frame, verifying its full SHA-256 before sampling. The frame is partitioned into **up to 16×16 tiles** (256 tile regions), each hashed from **every byte** of its true full-resolution RGB pixels. For each tile, 64 fixed-location sample pixels generate approximate RGB means, luminance range and dark/bright counts. The full frame and tile hashes are exact; color statistics are explicitly sampled, not represented as exact full-tile histograms. PNG previews and pixel zoom are available in the operator viewer where payload caps permit.

Inspection transfers **no ROM, BIOS, disk image, game save, arbitrary native RAM or core executable bytes** to the browser. The live response contains bounded tile metrics and digests. The viewer's “Export full tile evidence JSON” produces the complete tile audit for local review. The separate study evidence export includes its inspection receipt and a digest committing to that report, but does **not** itself include raw RGB pixel data or the full tile report. Store both exports if independent audit of the tile metrics is needed.

## Control and receipt contracts

- The native studio HTTP surface is loopback-only, same-origin restricted and bearer-token protected. The two new mutation paths are `POST /api/timing` with exact `{"game_id":"…","mode":"slow","factor":4}`, and `POST /api/inspect` with exact `{"game_id":"…"}`.
- Inputs are fail-closed. Speed factors outside exact allowed profiles, unapproved game lanes, extra request keys, inspection unless paused, reset and disc swap while paused, and native step while paused all fail.
- Per lane: **256** lifetime native step receipts, **4** reset receipts, **32** preloaded disc swap receipts, **32** speed-change receipts and **24** frozen inspection receipts. Maximum = **348** bounded events.
- A timing receipt binds mode/factor transitions, source/core SHA-256, episode/reset generation, current native frame digest and native `retro_run` cursor. An inspection receipt binds the frozen frame SHA-256, tile-report digest and unchanged run cursor.
- The offline verifier checks strict timing-mode transitions, counters, frame cursor continuity, requested native frames per step, source provenance and every chained event digest. The frame/run cursor does not advance in pause or inspection. Hash chains prove local consistency, **not** independent execution attestation.
- Per-core failures remain isolated; the viewer never performs automatic rights clearance, autonomous training or unapproved core installation.

## Qualification

A dedicated `tests/test_game_emulator_timing.py` exercises speed profile bounds, exact tile hashes, non-divisible dimensions, corrupted pixels, host no-worker inspection and exact 1–60 frame acceptance. The original **compiled C libretro fixture** additionally exports a test-only run cursor, which the isolated subprocess uses to assert that paused tile inspection executes zero core ticks, single-step executes exactly one tick and an eight-frame batch executes exactly eight ticks. These are real native C callback checks when the manual workflow runs, not proofs of commercial-console behavior. Extended live and HTTP tests cover paused-step/reset rejection, timing transitions, synthetic per-core fast bursts, inspection cursor tampering, viewer placement and same-origin access. The manually triggered `.github/workflows/focused-game-emulator-comparison.yml` includes the new module. It intentionally has **no push/PR triggers**.

**Not completed in this pass:** running those tests against the updated branch, running the extended compiled libretro fixture timing assertions, validating every installed system/core, measuring true slow/fast FPS on user hardware, collecting licensed game asset datasets, or training/promoting any production weights. These require an explicit validated run and consent/rights-cleared source media.
