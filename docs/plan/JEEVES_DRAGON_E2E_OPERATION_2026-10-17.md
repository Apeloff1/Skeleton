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
| PROD-015 | PCM sound assets | Original synthesized 8kHz 16-bit mono WAV music/pickup/hazard cues, validated decodable media | Native and HTML5/Godot audio playback drivers not yet qualified |
| PROD-016 | Original parallax and environmental effects | 0..3 RGBA overlay files plus real foliage/shadow tile transformations | Overlay files available; actual camera/parallax playback not wired |
| PROD-017 | Source sprite animation | Browser interval and Godot frame-tick controller use generated frames and 1..24 FPS | Source integrated; target execution not observed |
| PROD-018 | Recoverable game publication | Complete native+browser/Godot+sprites/audio/media bundle is staged in a same-parent temporary directory and renamed after success | Late asset-fault injection proves no partial output, no automatic publishing to a store |
| PROD-018 | Full asset and native E2E tests | `tests/test_jeeves_native_studio_art_e2e.py`, `tests/test_jeeves_console_source_stage_e2e.py` | Tests authored/registered, not yet run on exact head |

Run example, using the existing verified regular-file authorship-document intake (a referenced document is not independent ownership clearance):

```bash
python -m skeleton.ai.game_builder.native_game_cli \
  --target nintendo_game_boy --basis bandai_wonderswan \
  --project-id originalconsole --title "Original Console Adventure" \
  --seed 733 --theme ocean --width 11 --height 11 --levels 1 \
  --collectibles 1 --hazards 1 --health 4 \
  --rights-evidence /path/to/owned-authorship-document.txt \
  --identity "original-characters" \
  --identity "independent-mechanics" \
  --studio-assets --studio-style luminous \
  --studio-contrast high --studio-animation-frames 3 \
  --studio-foliage 2 --studio-shadow 2 --studio-parallax-layers 2 \
  --studio-music-density 3 --studio-animation-fps 8 \
  --authorize-original-homebrew \
  --output /path/to/new-project-directory
```

The generated directory contains the target source entrypoint and build recipe, `assets/tiles/runtime.bin`, `assets/sprites/*.png`, `assets/previews/*.png`, `assets/metadata/{descriptors,manifest}.json`, and `assets/audio/*.wav`, `assets/parallax/*.png`, `engines/index.html`, `engines/tile-editor.html`, `engines/godot/**`, `engines/proof/**`, plus separate exact manifest receipts.

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


## Large milestones: durable console production and qualification

This tranche adds working owners rather than an isolated proposal. Source exists on the feature branch; tests are registered but not yet proven passing on exact branch head.

| Stage | Instrumental completion criterion | Implemented evidence | Outstanding independent proof |
| --- | --- | --- | --- |
| M21 Multi-target production | Build exact same game for several native consoles, preserve each platform-specific source | `studio_campaign.py`, typed `CampaignOrder` | Real multi-day production soak |
| M22 Source identity | All targets must bind identical original game, approved document reference and art controls | SHA-based campaign identity, per-target immutable receipt | External IP rights clearance |
| M23 Durable restart | Resume target N after fail/abort without rebuilding verified targets | Exact source checkpoint validation and incremental target loop | Machine-loss/reboot soak |
| M24 Single producer | Reject concurrent operations against the same source campaign | Cross-platform process-lifetime lock; explicit busy error | Multi-host distributed lease |
| M25 Interrupted staging | Reclaim only owned orphan temporary build directories on restart | Symlink refusal and directory-scoped recovery | Full unclean-power-cycle testing |
| M26 Source/asset attestation | Record exact original C/ASM/config/manifest bytes | `source_attestation.json` and SHA-256 | Signed build provenance |
| M27 Toolchain preflight | Identify usable fixed native compiler adapters | Explicit GB/GBC/NES adapters | Compiler installation/actual build |
| M28 Toolchain containment | Fixed arguments, no generated Makefile or shell, overall timeout, output size bound | `studio_build_qualification.py` | Privileged OS sandbox/container |
| M29 Real ROM structural validation | Inspect exact ROM header, size and CRC/checksum requirements after actual compilation | iNES and GB/GBC structural receipt logic | Emulator execution/functional game proof |
| M30 ROM publication | Failed compilation must never publish a partial binary | New-path exclusive hardlink commit; no overwrite | Concurrent process + disk fault drill |
| M31 Readiness gates | Source generation must not count as emulator/rights/release success | 16 explicit gates per console and 0% release qualification until independently proven | Runtime/QA approval |
| M32 Dragon operational evidence | Dragon observes exact verified source/ROM milestones without raw code | Chained read-only source/binary observation | Consent-bound video, human/AI playback |
| M33 Artist sprite ingestion | Import real original authored raster assets rather than only procedural placeholders | PNG 48x8, exact SHA, decoded RGBA, 2bpp palette converter | Large multi-frame sprites/atlas packing |
| M34 Pixel-editable Jeeves | Conversational Jeeves can stage actual typed sprite pixels for native C/ASM code review | `game.console.source.stage.artwork` exact 6×64 payload | Full visual sprite editing UI |
| M35 Artwork reproducibility | Replaying campaigns with the same artist input yields exact source-bound artwork | Artist SHA and quantization mode in order and manifest | Full asset edit history/version graph |
| M36 Engine rendering | Browser/Godot source loads same authored palette/index pixels and animates | Exact pack-digest binding and generated raster routines | Real browser/Godot playthrough proof |
| M37 Full audio/effects | Sound and parallax must be actually consumed during play | PCM/PNG asset generation | Native and engine audio playback, moving parallax |
| M38 AI production supervisor | Observe model actions, source edits, game revisions and gate progress with evidence | Jeeves goal journal + Dragon source/ROM projection | Real checkpoint-inference marathon |
| M39 Legal publishing | Licensed distribution approved only by rights and release owners | Explicit non-certification flags | Independent rights governance signoff |
| M40 True release gate | Finished game requires compiled ROM, playable scene, controller, continuity and approval | Blocking gate projection | Not achieved |

### Operator commands

First write a typed campaign order as UTF-8 JSON. The order binds the project/seed, target list, original authorship documentation and optional original artist PNG + source SHA.

```bash
# Build one platform at a time, checkpointing exact source files.
python -m skeleton.ai.game_builder.studio_campaign_cli \
  --order original-campaign.json --output ./campaign \
  --authorize-original-homebrew --max-targets 1

# Resume without overwriting verified targets.
python -m skeleton.ai.game_builder.studio_campaign_cli \
  --order original-campaign.json --output ./campaign \
  --resume --authorize-original-homebrew

# Read exact source/binary QA gates (no compiler or emulator started).
python -m skeleton.ai.game_builder.studio_campaign_assurance_cli \
  --order original-campaign.json --campaign ./campaign \
  --inspect --authorize-local-operation

# Independently opt in to a bounded GB, GBC or NES compilation.
python -m skeleton.ai.game_builder.studio_campaign_assurance_cli \
  --order original-campaign.json --campaign ./campaign \
  --target nintendo_game_boy --execute-build \
  --authorize-local-operation

# Inspect Dragon's digest-linked production observations, not video.
python -m skeleton.ai.game_builder.studio_campaign_assurance_cli \
  --order original-campaign.json --campaign ./campaign \
  --dragon-observe --authorize-local-operation
```

A source-only project has no qualified ROM. GB/GBC/NES structural compilation is conditional on installed approved toolchains, and none was launched through GitHub during this development session. Source receipts are SHA integrity references, not signed producer identities. All release gates remain blocked without independent native runtime, controller, performance, rights and human/Dragon review evidence.

### Artist-provided sprite inputs

An artist may provide an *original* 48×8 PNG containing six horizontally arranged 8×8 tile graphics (floor, wall, collectible, hazard, goal, hero). `--studio-artist-png` requires `--studio-artist-png-sha256` and `--studio-assets`. Colors are either exact to the selected game palette or converted deterministically with nearest/ordered 4×4 quantization. Partial transparency, mismatched source hashes, unknown palette data and oversized images are rejected, not silently resized. This pixel model is the current six-tile native engine envelope, not a purported full production sprite studio.

Jeeves can also stage 6×64 indexed arrays with the explicitly distinct action `game.console.source.stage.artwork`; it generates the appropriate original console assembly/C with human-reviewed CAS submission. A proposal is not a source commit or release.

### Focused validation, pending actual execution

```bash
python -m pytest -q -ra --tb=short --noconftest \
  tests/test_studio_build_qualification.py \
  tests/test_studio_campaign_e2e.py \
  tests/test_studio_campaign_assurance_e2e.py \
  tests/test_studio_artist_sprite_e2e.py
```

The specialized suites above are registered in `machine/e2e_suites.json` without adding always-on workflow gates. Successful exact-head checks and real native toolchain/emulator tests must be collected before marking these milestones qualified.
