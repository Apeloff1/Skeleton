# Jeeves × Dragon game-production E2E operating plan
Date: 2026-10-17
Owner: canonical Jeeves studio goal journal + game-builder runtime; Dragon observes as a non-executing evidence consumer.

## Product journey

An operator creates an authenticated original-game project; Jeeves issues typed goals and obtains bounded model decisions; the existing application owner rechecks permissions and authorizes each tool step. The original world is edited or built with real source mutations, replayed through the runtime, reviewed through its deterministic and independent mirror, compiled or packaged, and exported with the current source identity. Dragon observes the already sealed tool/goal receipts. It may propose experiments for review, but observations never grant training or publishing authority.

The application continues to own execution, leases, idempotency, terminal status, storage and recovery. The Dragon view is a read-only, owner-scoped projection over the canonical goal journal. There is **no new API service, provider boundary, activity store, background recorder, privilege elevation or implicitly authorized capture**.

## First tranche: work delivered on the feature branch

| ID | Milestone | Implementation | Evidence / condition |
| --- | --- | --- | --- |
| E2E-001 | Current canonical architecture and ownership inspection | completed inspection | Architecture bootstrap, existing studio owner and Dragon trust boundaries read |
| E2E-002 | Typed Dragon goal-observation projection | implemented, not production-qualified | `skeleton/ai/game_builder/studio_e2e_observation.py` |
| E2E-003 | Event-chain replay across paginated goal steps | implemented, offline test supplied | Source step digests, owner-validated journal, stable sequence/hash chain |
| E2E-004 | Read-only authenticated owner/tenant ingress | implemented, not live tested | `GET /game-studio-agent/goals/{goal_id}/dragon-observation` delegates to existing scoped `agent.inspect` |
| E2E-005 | Anti-leak bounded evidence projection | implemented, offline tests supplied | Whitelist only tool ids, status, hashed evidence, phase/action counts and recovery |
| E2E-006 | Real local game-build-to-mirror exercise | test supplied; execution not performed in this session | Generate original world; run playable proof; compile browser/Godot source; run independent mirror |
| E2E-007 | Distinguish activity from successful production | implemented, test supplied | No output claims video, rights certification, hardware verification, weight promotion or qualified game |
| E2E-008 | Negative/fault-mode gate coverage | test supplied; execution not performed in this session | Tampered chain/head, legacy journals, invalid cursor, forged receipt, unauthorized local execution |
| E2E-009 | Register focused low-noise offline E2E | implemented | `machine/e2e_suites.json`, not a new global CI gate |

## Next operational milestones — not yet complete

| ID | Required acceptance proof |
| --- | --- |
| E2E-010 | Authenticated live CORE_DB E2E with two tenant accounts, isolation, lease contention and goal restart |
| E2E-011 | Explicit consent-bound Dragon desktop/window/video capture through existing Dragon consent and capture owners; mask secrets, recording status and retention controls |
| E2E-012 | Synchronize captured frame timestamps, visual state transitions and typed Jeeves action receipts without confusing the camera with an execution oracle |
| E2E-013 | Actual locally loaded Jeeves model checkpoint inference (not mock / provider fallback) and independent decision-review |
| E2E-014 | Complete interactive first-install → game project → original source → compiled native binary → playthrough → export; retain all artifact checksums |
| E2E-015 | Multi-ending paths, save/load, controls, cameras, physics and quest continuity, including resumed sessions and negative playthroughs |
| E2E-016 | Hours-to-weeks resumed execution, bounded maintenance windows, checkpoint recovery, storage backpressure, cancellation/lease fencing, leak/latency/resource measurements |
| E2E-017 | Dragon generated lesson candidates routed to existing reviewed almanac and rights-governance owners; no auto-promotion |
| E2E-018 | Independent replay/causality checks before any behavioral adjustment, plus negative controls for ambiguous, contradictory, and stale learning |
| E2E-019 | Shadow-model training on reviewed consented data, contamination scanning, isolated eval, rollback and explicitly authorized checkpoint promotion |
| E2E-020 | Product inspection UI: bounded phase filmstrip, evidence links, playback controls, permission/consent statuses, recovery console, learning proposals |

## Trust and qualification

- **Observation is not video**: this tranche derives operational evidence from actual existing receipts. No screen, mic, camera or desktop content is recorded.
- **Observation is not learning**: the dragon's observation queue has zero promoted training candidates; user-granted capture and separate reviewed knowledge must precede learning.
- **Executed is not passed**: a tool execution receipt establishes that an authorized invocation occurred; only the separate underlying runtime, final playthrough and qualified release evidence can prove the resulting game is shippable.
- **No inflated E2E percentage**: code authored and focused tests added are work delivered, not test passes. Stage completeness depends on measured exact-head CI and operational evidence.
- **Current source dependency**: changing gameplay source invalidates downstream play/review/package/export evidence. No release or weight promotion without fresh source-bound proofs.

## Focused validation

```sh
python -m pytest -q -ra --tb=short --noconftest tests/test_jeeves_game_e2e_observation.py
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

Verification result for this session: the changes were committed to a feature branch through the GitHub connector; local runtime tests and live backend tests were **not executed**. This file is a working acceptance plan, not a qualification certificate.


## Second tranche: actual console source, original sprite assets and engine rendering

Implementation on this feature branch extends the operational proof chain beyond an observer-only milestone. No platform release certification is inferred.

| ID | Producer/action | Real output | Evidence level |
| --- | --- | --- | --- |
| PROD-001 | GameBuildIntent and existing playable world solver | Deterministic multi-level original game and winning reference actions | Python simulation; not a ROM emulator |
| PROD-002 | Native source emitter registry | Existing RGBDS, ca65, Z80, cc65, DOS and SDL2 source templates for 16 registered original-console/desktop targets | Actual original target source; external toolchains not run |
| PROD-003 | Studio pixel art engine | Original 8x8 floor, wall, collectible, hazard, goal and player bitmaps | Actual numeric RGBA/indexed pixel data, not prompt descriptions |
| PROD-004 | Console encoder | DMG/NES 2bpp, Sega Master System/Game Gear 4bpp, 8bpp portable editor tiles | Actual native byte arrays and roundtrip decoding |
| PROD-005 | Embedded native art | Generated original tiles replace compiled source art for GB, GBC, NES, SMS, GG | Native ROM source bytes changed, sources not assembled to binary |
| PROD-006 | Sprite animation | Original hero poses and blink/movement PNGs, animation frame descriptor | Frame pixels exist; individual native console frame driver integration remains incomplete |
| PROD-007 | Scene software renderer | Per-level pixel-composed PNG from actual world tile geometry | PNG bytes generated and independently decoded; not device framebuffer |
| PROD-008 | Sprite atlas and descriptions | PNG atlas, SHA-indexed 6 sprite records, roles, collision/interaction flags, style and palette | Content-addressed project sidecar |
| PROD-009 | Browser rendering | HTML5 canvas executes per-pixel studio sprite drawing instead of only geometric fallback when the pack is supplied | Source wired; browser execution not yet measured |
| PROD-010 | Godot rendering | GDScript loads content-bound `res://studio_art.json` and paints sprite pixels using the canonical scene graph source | Source wired; Godot binary execution not yet measured |
| PROD-011 | Multi-target engine source | Offline browser index.html, Godot project, interactive tile editor and verified replay source | Existing canonical engine exporter reused |
| PROD-012 | Existing native_game_cli integration | `--studio-assets` and style/contrast/animation flags, native and engine project source emission | Operator-invoked writing into a NEW source directory |
| PROD-013 | Jeeves native source studio action | `game.console.catalog`, `game.console.source.stage` | Actual generated ASM/C staged through existing GameWorkspace CAS, human commit still required |
| PROD-014 | Retain legacy behavior | Default native exporter output unchanged unless studio-art option supplied | Backwards-compatible optional tile_art parameter |
| PROD-015 | Full asset and native E2E tests | `tests/test_jeeves_native_studio_art_e2e.py`, `tests/test_jeeves_console_source_stage_e2e.py` | Tests authored/registered, not yet run on exact head |

Run example, using the existing verified regular-file authorship-document intake (a referenced document is not independent ownership clearance):

```bash
python -m skeleton.ai.game_builder.native_game_cli \
  --target nintendo_game_boy --basis bandai_wonderswan \
  --project-id originalconsole --title "Original Console Adventure" \
  --seed 733 --width 11 --height 11 --levels 1 \
  --collectibles 1 --hazards 1 --health 4 \
  --rights-evidence /path/to/owned-authorship-document.txt \
  --identity "original-characters" \
  --identity "independent-mechanics" \
  --studio-assets --studio-style luminous \
  --studio-contrast high --studio-animation-frames 3 \
  --authorize-original-homebrew \
  --output /path/to/new-project-directory
```

The generated directory contains the target source entrypoint and build recipe, `assets/tiles/runtime.bin`, `assets/sprites/*.png`, `assets/previews/*.png`, `assets/metadata/{descriptors,manifest}.json`, and `engines/index.html`, `engines/tile-editor.html`, `engines/godot/**`, `engines/proof/**`, plus separate exact manifest receipts.

For C64, DOS, Atari, Apple II, MSX, Spectrum, ColecoVision, Vectrex and desktop targets the original native-source generators work independently and the asset/engine outputs exist, but custom ROM tile integration is not claimed. This is an explicit backlog item.

### Further advanced-studio gaps, not represented as implemented

Console-specific toolchain execution and cartridge compilation; physical/emulator render and controller verification; sprite atlases, color attributes, palettes and animation VRAM transfer for the remaining consoles; actual Godot/browser preview playback and screenshot comparisons; arbitrarily large sprites, backgrounds, parallax, cinematics and 3D model/material/lighting; fully edited NPC/quest/scene/audio game systems across every era; content-based legal rights validation; multi-week resilient Jeeves decision loops; consented Dragon app video recording and measured model-learning improvement. Each needs exact current-source runtime evidence, not a passing source existence check.

### E2E suites

```bash
python -m pytest -q -ra --tb=short --noconftest \
  tests/test_jeeves_native_studio_art_e2e.py \
  tests/test_jeeves_console_source_stage_e2e.py \
  tests/test_jeeves_game_e2e_observation.py
```

Do not count tests as passing until they have actually run against the committed PR head.
