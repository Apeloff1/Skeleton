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


## Cross-engine executable playthrough milestones M41–M60

This tranche directly addresses the gap between “source exists” and “playable runtime has executed,” while retaining strict noncertification for everything still untested. All code is present on the PR branch; it has **not been executed in this GitHub-only session**.

### M41–M45: real generated JavaScript game controls

A separate actual JavaScript runner, `studio_browser_probe.js`, loads **the exact rendered HTML5 game's real JavaScript** into a bounded Node VM with a minimal instrumented DOM and Canvas2D recorder. It runs the canonical Python-winning sequence using the actual game's `takeTurn` source, compares final level/position/score/health/turns, checks actual pixel drawing calls and executes an animation tick. It additionally exercises the real event listeners for arrow-key movement, directional buttons, undo and restart. This is executable JavaScript parity, not a rendered Chromium framebuffer or a simulated third-party game.

The operator CLI provides a separate `--browser-target` mode. Node absence and any mismatch leave the gate unqualified. Evidence is SHA-bound to actual released HTML, canonical proof JSON and campaign identity; editing source after verification invalidates the gate.

### M46–M48: real Godot 4 headless playthrough

The Godot qualification owner verifies exact scene, GDScript, world, proof and optional studio art files against the canonical release manifest; copies only those files into an isolated temporary project; then, **only with explicit operator execution authorization**, calls an installed Godot binary with `--headless --path <temporary source> -- --verify-proof`. It accepts the underlying `NATIVE_REPLAY_OK <world-digest> actions=<count>` marker only with an exit code of zero and matching action count. Godot writes to a bounded local log, not into the original source tree. Native Godot export/signing, GPU frame quality, real input devices and human gameplay remain unqualified.

### M49–M52: exact content and runtime source integrity

`studio_pixel_parity.py` verifies the actual 8×8 indexed pixel values from console 2bpp/4bpp bytes, the browser's embedded live data, the Godot art source, the generated PNG sprite atlas, palettes, animated frames, and every level preview's dimensions. It checks both art-pack and engine-release manifests. A mismatch makes the assurance inspection fail rather than producing a false passed percentage.

The separate JavaScript and Godot execution receipts become independent production gates. They never imply another runtime has been tested, and Dragon receives only read-only source-bound hashes and named verification facts.

### M53–M56: explicit Dragon visual observation of generated games

`studio_dragon_canvas_capture.py` introduces an opt-in **actual local browser screenshot** of the *generated original game canvas only*. It requires both local operator authorization and separate explicit original-game capture consent. When Playwright and Chromium are installed, it launches an offline headless browser, replays actual DOM directional inputs, captures a bounded sequence of PNG frames, verifies real displayed victory, and writes an exact SHA-indexed frame manifest to a new private local output directory outside source control. Missing dependencies do **not** count as captured video.

This records no desktop, user camera, web browsing or other applications. Recording does not authorize Dragon knowledge promotion, source/IP approval, model training, checkpoint tuning, or publication. The SHA-bound manifest is rechecked by the campaign assurance owner; tampered frame bytes or source changes fail the gate.

### Remaining high-impact engineering milestones M57–M60

- M57: measured Chromium/Godot pixel-to-pixel comparison (including shadow, color, anti-aliasing, canvas screenshot and GPU output).
- M58: native cartridge compilation and emulator CPU/graphics/controller full-playthrough qualification on each supported console.
- M59: true expansive game creation: scene graph editing, canon-bound longform story, quests, NPC behavior, multi-act dialogue, full cinematics, asset animation/lighting, audio integration and advanced 2.5D/3D engines.
- M60: months-long persistent producer/Dragon/AI co-iteration with verified checkpoint resumes, bounded storage/capture controls, independent human review, weight-evaluation/rollback and full release evidence.

### Exact operator commands

```bash
# Run the actual generated HTML5 JavaScript winning replay (Node required):
python -m skeleton.ai.game_builder.studio_campaign_assurance_cli \
  --order original-campaign.json --campaign ./campaign \
  --browser-target nintendo_game_boy --execute-build \
  --authorize-local-operation

# Run real Godot replay on an isolated engine copy (Godot 4 required):
python -m skeleton.ai.game_builder.studio_campaign_assurance_cli \
  --order original-campaign.json --campaign ./campaign \
  --godot-target nintendo_game_boy --execute-build \
  --authorize-local-operation

# Prove exact native console/HTML5/Godot sprite parity without execution:
python -m skeleton.ai.game_builder.studio_campaign_assurance_cli \
  --order original-campaign.json --campaign ./campaign \
  --pixel-parity-target nintendo_game_boy \
  --authorize-local-operation

# Capture original game-only canvas frames with explicit separate permission
# (requires Playwright plus a local Chromium runtime):
python -m skeleton.ai.game_builder.studio_campaign_assurance_cli \
  --order original-campaign.json --campaign ./campaign \
  --canvas-target nintendo_game_boy --execute-build \
  --consent-generated-game-canvas --authorize-local-operation

# Inspect the now expanded source/runtime/canvas qualification gates:
python -m skeleton.ai.game_builder.studio_campaign_assurance_cli \
  --order original-campaign.json --campaign ./campaign \
  --inspect --authorize-local-operation
```

### Specialized E2E suite

```bash
python -m pytest -q -ra --tb=short --noconftest \
  tests/test_studio_browser_runtime_e2e.py \
  tests/test_studio_godot_runtime_e2e.py \
  tests/test_studio_pixel_parity_e2e.py \
  tests/test_studio_dragon_canvas_capture.py
```

Tests requiring an external binary or Chromium may skip when it is absent. Such skips do not qualify that runtime. Source-generated tests and snapshot checks alone are not permission to merge or release. No new always-on CI workflow was added.


## M61–M80: audible/visible original gameplay, controller handling and Dragon feedback

This is an additional implementation pass on the same production branch, not a claim that all games/platforms are finished. Distinguish source-integrated functionality from execution or GPU/speaker/hardware validation.

### Playable HTML5 music and environment (M61–M65)

The generated HTML5 game now carries the actual original synthesized WAV media in its offline game-data payload. After a real directional gesture, ambient audio starts once; collectible and hazard encounters trigger their original sound cues. The playable page includes mute/unmute, music-level and effects-level controls. Game music stays optional. Browser Content Security Policy permits only embedded data media and imagery, not remote connections.

Environment overlays use the original RGBA PNG layers produced with the game artwork, decode as offline data images and composite over real game tiles before the animated hero. Movement offsets successive layers to provide simple parallax. These are functional Canvas drawing paths, not sophisticated GPU shaders, compositing-grade smoke, lighting or real 3D scene systems.

### Godot source integration (M66–M69)

The Godot exporter copies the exact original `audio/{ambient,collectible,hazard}.wav` and `parallax/layer_NN.png` bytes into its project, hashes them into the engine release, and adds native GDScript `AudioStreamPlayer` playback source for music and event cues. Original environment overlays are loaded as textures and redrawn across the actual tile scene with movement-offset scrolling.

Godot source replay qualification now stages these exact media resources in its isolated temporary project. Godot runtime audio import/playback, sound-device output, actual GPU frame parity and Godot editor correctness are still unqualified until a real engine run passes.

### Three-way source-media parity (M70)

Production assurance now fails if the browser's embedded PCM/PNG bytes differ from the asset producer's original files or from the Godot project. It checks original source audio assets, ambient, pickup and hazard WAV headers, per-layer PNG payloads, manifest SHA-256 and engine release identity. No byte-compatible but stylistically inconsistent media silently gets a passed digest.

### Native browser controller parity (M71–M74)

The HTML5 game implements the standard Gamepad API: left analog stick, D-pad directional movement, B undo and Start restart. An edge trigger prevents replay flooding when buttons are held. Existing keyboard and touchscreen buttons remain available below the game.

The Node executable probe now installs a synthetic Gamepad API device, presses/repeats/releases an actual mapped button, checks one move per press, invokes undo and restart, and exercises actual generated audio and overlay renderer calls. The receipt separates these browser-method checks from physical controller verification and real audible media playback. No native emulator controller core is falsely reported as certified.

### Dragon's corrective operational learning (M75–M77)

`studio_dragon_learning_bridge.py` reads canonical per-target game production assurance and derives bounded improvement candidates when a stage is missing or blocked. Each candidate names a specific gate, target, blocker, proposed next check and exact current report/source digest. Raw model prompts, copyrighted game data, screenshots and third-party assets are not accepted into lessons.

Human review is an explicit operator action. Accepted, rejected and needs-more-evidence decisions receive content-bound receipts stored outside the immutable source target. The operation locks the campaign, rereads the entire production-assurance digest and refuses changed ROM/runtime/art/scene evidence. An existing review cannot be overwritten by a revised claim.

`studio_dragon_lessons_cli.py` exposes reviewable proposals and reviewed-draft inspection. This creates operational knowledge *drafts*, not trained weights or automatically promoted almanac entries. Independent rights and evaluation gates remain required.

```bash
# Generate bounded, exact-current improvement proposals.
python -m skeleton.ai.game_builder.studio_dragon_lessons_cli \
  --order original-campaign.json --campaign ./campaign \
  --propose --authorize-local-operation

# Human approves ONE referenced proposal as a reviewed knowledge draft.
python -m skeleton.ai.game_builder.studio_dragon_lessons_cli \
  --order original-campaign.json --campaign ./campaign \
  --review-candidate <exact-candidate-sha256> \
  --decision approve_for_reviewed_knowledge \
  --reviewer-note "Independently reproduce this runtime blocker before promotion." \
  --human-reviewed --authorize-local-operation

# Inspect current, source-bound approved/rejected review drafts.
python -m skeleton.ai.game_builder.studio_dragon_lessons_cli \
  --order original-campaign.json --campaign ./campaign \
  --inspect-reviewed --authorize-local-operation
```

### M78–M80: explicit release blockers

Native GB/GBC/NES assembly must actually run and pass emulator playthroughs with real controller layout and video/PPU evidence. Real sound-card and GPU output must be measured. Complete multi-platform cinematic, NPC/dialogue, longform canon, 2.5D/3D and advanced asset direction remain separate production requirements. Dragon's independently evaluated knowledge admission and checkpoint weight updates remain unimplemented rather than inferred from review drafts.

### Updated specialized suites

```bash
python -m pytest -q -ra --tb=short --noconftest \
  tests/test_studio_playable_media_e2e.py \
  tests/test_studio_browser_runtime_e2e.py \
  tests/test_studio_godot_runtime_e2e.py \
  tests/test_studio_pixel_parity_e2e.py \
  tests/test_studio_dragon_learning_e2e.py
```

The new code and tests are committed but none is represented as a passing game E2E run. Exact-head GitHub checks and real installed native/browser/Godot runtimes are required before accepting any runtime qualification or game release.


## M81–M100: verified native ROM/WRAM emulator and complete E2E campaign runner

This tranche turns an earlier source-to-ROM structural boundary into a **real optional GB/GBC emulator input/playthrough qualification path**, with exact source evidence. Source code and tests are committed on the feature branch. The actual RGBDS assembler and PyBoy must still be installed and successfully executed locally before a ROM/gameplay milestone may be signed complete.

### M81–M84: native ROM plus exact RGBDS symbols

GB and GBC source now links with an actual `-n game.sym` argument to RGBLINK. The native build qualifier validates the assembler-emitted WRAM labels `Level`, `PlayerX`, `PlayerY`, `Health`, `Score`, `GemsRemaining`, `GameWon`, and `GameLost` and refuses missing, duplicate, overlapping or out-of-WRAM addresses. Source cannot simply guess the offsets from the template.

Compiled ROM and symbol-map outputs use exclusive publication and an owned rollback path on failure. The native ROM qualification receipt commits both ROM and symbol SHA-256; changed symbols cannot pass future build or emulator inspection. The explicit lower-level native build CLI accepts `--output-symbols <new-path>` for GB/GBC; NES remains ROM-only.

### M85–M92: run the *actual* compiled cartridge in an emulator

`studio_game_boy_emulator.py` is a conditional PyBoy adapter, not a simulated rendering of the Python world. After explicit local operator execution authorization, it opens a private copy of the qualified ROM, advances boot frames, delivers the canonical winning directional inputs using real PyBoy gamepad methods, observes the actual 8-bit WRAM flags through assembler-owned symbol addresses, and hashes the final rendered emulated LCD framebuffer. It compares the cartridge's final coordinates, level, health, score, remaining crystals, victory/loss status to the actual Python source proof.

The adapter enforces a maximum wall-clock budget, an explicit frame budget and a bounded reference action list. A missing PyBoy installation, early win/loss, incorrect score/health/coordinates, ROM mismatch or expired time budget remains a **failed/blocked qualification**, never a successful build or “controller verified” fiction. Emulated D-pad input is not a physical USB controller, hardware console, actual audio device or rights clearance.

### M93–M95: binding native execution to production and Dragon

`qualify_campaign_emulator()` refuses unqualified source/ROM/symbols and writes a separate evidence receipt only after actual machine-code victory. The canonical assurance projection independently re-reads the current ROM, exact native source, assembler symbols and browser/Python reference proof before accepting a native emulator claim. The independent production gates `emulator_playthrough_executed` and `controller_response_verified` can be filled by this **emulated** full-game result. The physical controller and hardware release flags remain false.

Dragon's read-only production observation chain now records `studio.native_cpu_dpad_playthrough` only against that verified native emulator receipt. No automatic Dragon knowledge promotion, hidden recording or checkpoint weight updates are authorized.

### M96–M98: one ordered end-to-end operator campaign

`studio_execution_campaign.py` drives the actual canonical owners rather than installing a second game-building application. Stages run in order: source -> ROM -> emulator -> browser -> Godot -> optional canvas. The operator can select a subset, run full production, cap per-stage elapsed time/frames and source targets per invocation, and choose to stop on the first blocker or continue with independent targets.

Native console-specific stages are explicitly marked `unsupported` for targets without real compiler/emulator adapters. Missing tools and bad execution receipts remain `blocked`. The summarized plan has a fresh SHA of the canonical full-assurance report, per-target stage results and exact current artifact/evidence hashes; never an invented percentage of release completion.

### M99–M100: remaining native hardware gaps

The NES build adapter currently validates the iNES cartridge structure but **does not** execute a full 6502 CPU/PPU/D-pad winning replay. Other legacy-platform emulators and full emulation/controller matrix, actual native audio/video timing, physical input devices and hardware-specific releases remain future real implementations. Real RGBDS+PyBoy compilation/playthrough and a production installer-first-launch also need actual execution and recorded evidence.

### Exact operator execution

```bash
# Produce full original game source, then compile GB/GBC/NES where supported,
# run the PyBoy native CPU replay for GB/GBC, and run browser/Godot proofs
# if the respective tools are installed:
python -m skeleton.ai.game_builder.studio_execution_campaign_cli \
  --order original-campaign.json --campaign ./campaign \
  --stages source,rom,emulator,browser,godot \
  --authorize-local-operation --execute-run \
  --timeout-seconds 90 --max-emulator-frames 260000

# One specific qualified native Game Boy ROM against actual PyBoy CPU/PPU:
python -m skeleton.ai.game_builder.studio_campaign_assurance_cli \
  --order original-campaign.json --campaign ./campaign \
  --emulator-target nintendo_game_boy --execute-build \
  --authorize-local-operation --timeout-seconds 90

# Explicitly consent to game-only Chromium image capture (never implied by a
# regular source, emulator or gameplay command):
python -m skeleton.ai.game_builder.studio_execution_campaign_cli \
  --order original-campaign.json --campaign ./campaign \
  --stages canvas --consent-generated-game-canvas \
  --authorize-local-operation --execute-run
```

### Milestone-test contract

```bash
python -m pytest -q -ra --tb=short --noconftest \
  tests/test_studio_build_qualification.py \
  tests/test_studio_game_boy_emulator_e2e.py \
  tests/test_studio_campaign_assurance_e2e.py \
  tests/test_studio_execution_campaign_e2e.py
```

Synthetic/mocked native-emulator tests validate error paths and receipt contracts only; they do not qualify a real cartridge. An operator must install and execute real RGBDS, PyBoy and downstream runtimes on the generated original game before checking off runtime, completion or publishing criteria.


## M101–M120: actual NES CPU/PPU path and durable production history

### Native NES qualification (M101–M115)

The existing NROM engine now exports the actual zero-page `Level`, `PlayerX`, `PlayerY`, `Health`, `Score`, `GemsRemaining`, `GameWon`, and `GameLost` labels. Its ca65/ld65 build produces `game.sym` using the linker `-Ln` format, and the native adapter requires the symbol file beside `qualified.rom`. The qualification path refuses duplicate, out-of-range or missing CPU state addresses, and binds the ROM and linker symbols to the source target via SHA-256.

`studio_nes_emulator.py` is an operator-approved FCEUX 6502/PPU adapter, not a synthetic CPU emulator. It constructs a fixed Lua script from the *actual original-game canonical winning trace*, boots a private qualified ROM, delivers D-pad press/release events through FCEUX joypad APIs, advances real emulator frames, reads CPU zero-page memory via `memory.readbyte`, and records an emulated PPU image via `gui.gdscreenshot(true)`. A successful report requires the actual compiled ROM to finish with the original expected level, position, health, score, zero remaining collectibles, GameWon=1 and GameLost=0 **and** include a genuine emulator-produced framebuffer receipt. A missing/incompatible FCEUX runtime leaves the stage blocked, never passed. Some FCEUX builds are not fully headless; operators may need a controlled local display environment. These are not physical controllers, GPU quality certification or hardware audio measurements.

`studio_nes_chr_parity.py` adds a separate independent compile-to-asset integrity guarantee: extract the first six indexed 2bpp tiles from the **actual iNES CHR ROM bank** and compare them byte-for-byte to the source-generated NES `assets/tiles/runtime.bin`. A cartridge whose CHR bytes do not match the studio artwork does not qualify even with a valid iNES header. The operator qualification workflow rejects the bad binary and reclaims the newly published unqualified ROM/symbol pair. Future inspection rechecks the compiled-asset parity after publication.

The source-bound production assurance now accepts GB/GBC PyBoy or NES FCEUX CPU-gameplay receipts for the **emulated** playthrough/controller gates, never treating those receipts as physical console verification. Dragon can observe digest-linked native CPU input and machine-code victory evidence. The ordered full-studio E2E runner now attempts the NES emulator stage rather than declaring the platform unsupported.

### Production history and long-duration qualification (M116–M120)

`studio_execution_history.py` adds an atomic, bounded, append-only qualification attempt journal. Entries are created only after the full production report is revalidated **under the campaign OS lock**; each contains the exact current assurance digest, linked previous entry digest, run identity and counts of blocked, verified or unsupported stages. A previous run becomes visibly stale when a new game source, ROM or runtime receipt changes the canonical report. Edited history is rejected. There is no false assertion that a successful source-only pass is a verified game release.

The normal `studio_execution_campaign_cli` now stores an E2E journal entry after each operator-authorized synchronous run. The same CLI supports `--inspect-history` for a read-only recheck. This is useful groundwork for days-to-months production, but a six-month/year endurance qualification, actual fault/reboot testing, GPU/audio/device checks and checkpoint model learning remain **unverified or unimplemented**.

### Operator execution

```bash
# Compile exact original NES source and its ld65 labels:
python -m skeleton.ai.game_builder.studio_campaign_assurance_cli \
  --order original-campaign.json --campaign ./campaign \
  --target nintendo_famicom --execute-build --authorize-local-operation

# Run actual 6502 FCEUX CPU/PPU, Lua D-pad replay and memory observation
# only when a compatible local FCEUX build is installed and authorized:
python -m skeleton.ai.game_builder.studio_campaign_assurance_cli \
  --order original-campaign.json --campaign ./campaign \
  --emulator-target nintendo_famicom --execute-build \
  --authorize-local-operation --timeout-seconds 90

# Run a full explicit, receipt-backed original game production pass:
python -m skeleton.ai.game_builder.studio_execution_campaign_cli \
  --order original-campaign.json --campaign ./campaign \
  --stages source,rom,emulator,browser,godot \
  --authorize-local-operation --execute-run

# Read exact, chain-linked E2E history; this does not start a game:
python -m skeleton.ai.game_builder.studio_execution_campaign_cli \
  --order original-campaign.json --campaign ./campaign \
  --inspect-history --authorize-local-operation
```

### Focused regression suites

```bash
python -m pytest -q -ra --tb=short --noconftest \
  tests/test_studio_build_qualification.py \
  tests/test_studio_nes_emulator_e2e.py \
  tests/test_studio_nes_campaign_e2e.py \
  tests/test_studio_execution_campaign_e2e.py \
  tests/test_studio_execution_history_e2e.py
```

These tests include synthetic FCEUX responses to exercise the assurance contracts. They are **not** evidence of a real FCEUX or PyBoy cartridge victory; real optional runtime tests, first-install verification, sustained endurance and game release gates require execution on an appropriately provisioned machine.


## M121–M140: correct native gameplay rules and proof sampled input operation

This pass uncovered a substantive defect in the original generated native game code: the Python game awards **10 points per crystal and 100 points per level goal**, while the earlier GB/GBC and NES assembly awarded one point per crystal and did not add the goal bonus. Any genuinely executed winning ROM would therefore fail the final score parity gate for reasons not related to emulator setup. The old 8-bit native score also overflowed for longer games.

### Exact gameplay correction (M121–M130)

The Game Boy/GBC and NES original world source now uses a two-byte, 16-bit score accumulator, initialized on game boot. Both engines add ten to the score on collectible pickup and 100 after an eligible goal. Carry propagation updates `ScoreHigh` so long multi-level original games can exceed 255 points without rolling over or rejecting valid progress. RGBDS and ld65 source-symbol verifiers require `ScoreHigh` alongside the existing main score and controller state. The native CPU-replay verifiers calculate actual combined score as `Score + 256 * ScoreHigh`.

The GB engine now also commits the incremented `Level` in machine state on the final win, matching its own intermediate level transitions and the NES engine's native terminal convention. Emulator verification deliberately compares this native terminal counter to the zero-based Python final level index **plus one**. These source-code changes are committed, but real assembler execution and final CPU-parity signoff have not happened.

### Intermediate actual CPU state evidence (M131–M138)

`studio_native_replay_telemetry.py` introduces reproducible input-boundary checkpoints. For games up to 128 actions it records every post-input state; longer traces use at most 128 deterministic checkpoints including the first and last actions. Only exact 8-bit emulator-derived state fields are allowed: level, X/Y position, health, score low/high, gems remaining, victory and loss. The verifier fails closed on malformed, missing or reordered checkpoints, unexpected health healing, score decreases, impossible level jumps, early wins or losses, or mismatch to the canonical winning Python ending.

The PyBoy adapter samples the *actual emulated RAM* after submitting directional controller events. The NES FCEUX script writes a bounded ASCII CPU checkpoint log from its actual `memory.readbyte` calls; its verifier validates every expected sample and combines it with the previously required PPU screenshot and final machine-code victory. Positive emulator receipts include a checkpoint digest and observed count, both now mandatory in the campaign gate. They are surfaced in Jeeves' assurance report, Dragon read-only observation projection, ordered execution runner and hash-linked qualification history.

**Important:** These are sampled CPU checks, not frame-by-frame proof of all CPU instructions. A synthetic/mock checkpoint fixture is not evidence of real emulator operation. No physical controller or hardware-audio validation is implied, and no weight training has been authorized.

### Outstanding runtime qualification (M139–M140)

Run true RGBDS/cc65 builds and installed PyBoy/FCEUX against real generated multilevel games whose scores cross 255. Independently validate controller timing, actual machine frames, native sound, first installation and long-running crash/recovery boundaries before any platform is signed off. The source-level test suite now explicitly checks the 16-bit native templates and executes the genuine Python winning replay with a score above 255.

```bash
python -m pytest -q -ra --tb=short --noconftest \
  tests/test_studio_native_score_parity.py \
  tests/test_studio_native_replay_telemetry.py \
  tests/test_studio_build_qualification.py \
  tests/test_studio_game_boy_emulator_e2e.py \
  tests/test_studio_nes_emulator_e2e.py \
  tests/test_studio_nes_campaign_e2e.py \
  tests/test_studio_campaign_assurance_e2e.py
```

All these additions are in source control. Specialized exact-head E2E execution remains pending; no green result for the new source should be inferred from older CI runs.


## M141–M180: original Python-game reference, exact native input accounting and Dragon repair triage

### Build the independent reference, not just a plausible CPU ending (M141–M148)

`studio_native_replay_telemetry.py` now rereads the canonical generated HTML5 game's embedded immutable intent and the release-manifest-bound winning action proof. It regenerates the actual authored Python game via `generate_playable_world()`, verifies its digest and **every original level's rows/start/exit/collectible positions**, then steps the entire original controller trace through the Python `advance()` implementation.

At each deterministic sampled action boundary (all actions for traces up to 128, at most 128 across longer runs) the reference records exactly what a compiled ROM should expose: CPU level counter, true player X/Y, health, 16-bit score, remaining collectibles, victory/loss flags and action counter. Actual PyBoy or FCEUX memory is then required to match **every sampled field** of this independently regenerated reference, not merely avoid impossible health/score jumps or end at the goal.

The previously authored game export cannot silently change its levels while retaining a passing reference; the checker rejects source/world mismatches, renamed or corrupted intent, different final score, different final action count and incomplete replay.

### Count every directional attempt, including wall collisions (M149–M153)

Original GB/GBC RGBDS and NES ca65 source both now maintain `TurnCount` + `TurnCountHigh` in the game CPU state. The counter increments whenever an actual D-pad action enters the tile movement/collision operation, including actions blocked by walls. It uses an explicit carry into the high byte, so a long game does not roll over after 255 turns. Both toolchain symbol-map qualifiers require the actual source labels, and the native adapters compare the true combined count to the controller trace after every observed boundary and at the final winning ROM state.

This is important because a correct final location can be reached even when a controller device lost, repeated or failed to consume some moves. A successful game must consume the complete authored action trace. It still does not certify physical USB controller latency or real console electronics.

### Actionable Dragon correction without unreviewed self-training (M154–M178)

`first_cpu_divergence()` returns the first sampled source-versus-emulator state discrepancy, with a bounded set of changed CPU fields and exact observed/reference values. GB/GBC and NES emulation failure receipts now carry this diagnostic. `studio_execution_campaign.py` passes it into the E2E operator report. The crash-safe, chain-linked `studio_execution_history.py` stores the first mismatch digest/category/action after revalidating the full current source and refusing duplicated or fabricated stage counts.

`studio_native_correction_triage.py` adds a **read-only Dragon bridge** that maps the first actual mismatch to a precise investigation: D-pad/collision code, 16-bit score carries, hazard damage, collectible consumption, level transitions, or victory/loss conditions. It may suggest a concrete regression check but **never edits code, watches user applications, trains weights, authorizes replay retries or auto-promotes knowledge**. If the source or assurance digest has changed since the last recorded run, the bridge emits zero current repair proposals. The operator command is:

```bash
python -m skeleton.ai.game_builder.studio_dragon_lessons_cli \
  --order original-campaign.json --campaign ./campaign \
  --triage-native --authorize-local-operation
```

Regression tests cover generated three-level Python games, scores above 255, source-map integrity, corrupted intermediate positions, mocked NES/GB CPU replay, mismatched input counts, forged E2E history entries, current-only Dragon triage and the full report-to-triage handoff.

### Runtime blockers M179–M180

This is source implementation and specialized tests, **not** a measured successful native emulation run. An operator still needs to compile and play real original GB/GBC/NES cartridges with installed RGBDS, ca65/ld65, PyBoy/FCEUX; verify the exact script/controller timing and recorded CPU states; execute real browser/Godot end-to-end; then qualify physical devices, graphical/audio parity, first-install and sustained multi-month production. No model checkpoint weight update or release signoff is claimed.

```bash
python -m pytest -q -ra --tb=short --noconftest \
  tests/test_studio_native_python_reference_e2e.py \
  tests/test_studio_native_replay_telemetry.py \
  tests/test_studio_native_score_parity.py \
  tests/test_studio_game_boy_emulator_e2e.py \
  tests/test_studio_nes_emulator_e2e.py \
  tests/test_studio_native_correction_triage.py \
  tests/test_studio_execution_history_e2e.py
```

The 180 milestones in this plan are **work and verification objectives**, not a claim that 180 release features have passed native E2E.


## M181–M200: real artifact identity, GB/GBC compiled pixels and corrective blocker taxonomy

### Release evidence must correspond to an independently checked artifact (M181–M185)

The full studio operator-run pipeline previously tracked the general campaign identity as a source-stage receipt. It now resolves the **exact source target artifact digest** after independently inspecting the campaign and requires every claimed successful stage to match its separately verified source/ROM/emulator/browser/Godot/game-canvas digest. A locally recomputed E2E run checksum is insufficient proof that a stage occurred.

The digest-linked longform history checks those stage-to-evidence bindings again while holding the campaign filesystem lock. A source-only pass cannot invent a ROM, JS playback, emulator victory, Godot completion or consent-bound screenshot by replacing a status flag. Tests explicitly forge and rehash these apparent successes and require the system to reject them.

### Compiled Game Boy and Game Boy Color source-art integrity (M186–M193)

NES compilation already extracts the actual iNES CHR sprite bank. The GB/GBC native assembler now has an equivalent compiled-ROM assurance: RGBLINK's own `Tiles` and `TilesEnd` symbol addresses must identify exactly 96 contiguous bytes in bank-0 ROM. These bytes must match the six original 2bpp tile assets generated for the game, byte for byte. No arbitrary ROM scan, approximate image match, wrong bank, guessed offset or decorative asset descriptor is accepted.

`studio_game_boy_rom_art_parity.py` verifies these exact compiled bytes against the source producer. Every successful GB/GBC native build must pass this comparison before it becomes qualified. Future independent inspections recheck it; mutated ROMs, altered source tiles and incorrect linker maps fail even when the cartridge header checksum is valid. If the just-built ROM contains the wrong artwork, the locked build rejects and reclaims its own unpublished ROM/symbol pair, without overwriting a prior qualified artifact.

The tests cover both DMG and GBC headers, correct linker address identity, invalid mappings, wrong sprite pixels and rollback after compiled-art divergence. All existing mocked GB production tests now embed the actual generated 2bpp tiles rather than zero-filled nominal cartridges.

### More useful source-bound Dragon failure classification (M194–M198)

`studio_production_blocker_taxonomy.py` classifies independently observed production problems into separate categories such as missing native compiler, missing PyBoy/FCEUX, compiled cartridge artwork mismatch, incorrect CPU-controller trace, browser or Godot execution gap, and absent generated canvas evidence. It stores only bounded, normalized classifications and suggested human investigations, **not raw subprocess output, secrets, user screens, model prompts or auto-executable repair instructions**.

The hash-linked execution history retains a bounded number of these classifications. `studio_native_correction_triage.py` can now present specific review proposals for current-source game production; it suppresses duplicated CPU diagnostics and refuses to use stale history to recommend a correction. No model weights are trained, no arbitrary code is run and no source file is automatically modified.

### Qualification and tests (M199–M200)

The `jeeves-native-cartridge-emulator-full-e2e` specialized suite now includes compiled handheld-art parity, independent E2E stage receipts, intermediate CPU gameplay and source-current Dragon repair checks. It is registered without adding a new always-on CI workflow.

```bash
python -m pytest -q -ra --tb=short --noconftest \
  tests/test_studio_game_boy_rom_art_parity.py \
  tests/test_studio_campaign_assurance_e2e.py \
  tests/test_studio_execution_history_e2e.py \
  tests/test_studio_production_blocker_taxonomy.py \
  tests/test_studio_native_correction_triage.py
```

**Release status is still fail-closed.** An actual GB/GBC/NES cartridge compile and emulator victory, full browser/Godot runtime, physical controller, audio/GPU, first-install and six-month/year endurance require separately executed evidence and signoff. A generated code file or authored test must not be counted as an executed console game.


## M201–M260: source-real native sprite animation, original PSG and Jeeves studio entrypoints

This is the largest single functional production tranche in the current branch: 60 new explicitly classified milestones, 45 source-implemented and 15 dependent on actual toolchain/AV/endurance qualification. **Neither source emission nor unit fixtures qualify the corresponding emulator/hardware milestone.**

### M201–M220 — actual GB/GBC/NES hero sprite animation

The asset pipeline already authors 1–4 truly different original 8×8 hero frames. Previously, browser and Godot could cycle them but the native cartridge source retained a static tile. The native engines now include all authored frames:

- **Game Boy / Game Boy Color RGBDS:** The first six semantic 2bpp tiles remain a 96-byte source-stable segment. Additional authored hero frames are appended under distinct `AnimationTiles` and `AnimationTilesEnd` labels. Initial VRAM upload includes the entire tile inventory. `AnimTick` and `AnimFrame` advance sprite tile index from tile 5 through the available 1–4 frame cycle, on finite original-game frame intervals. All timing state stays in the real WRAM model; controller/collision/gameplay behavior remains separately verified.
- **NES ca65/ld65:** Additional 8×8 two-plane CHR frames follow the initial six semantic tiles. The engine advances `AnimTick` / `AnimFrame` within the real 6502 sprite update and changes OAM sprite tile indices. Original goal/loss tile behavior still overrides the ordinary hero animation.
- **Compiled artwork evidence:** GB/GBC inspections use actual RGBLINK ROM0 animation label bounds, and require the compiled bytes equal the additional encoded original animation frame bytes. NES CHR inspection does the equivalent against the actual compiled iNES CHR bank. Incorrect first frame, frame count, altered compiled pixels, forged symbol addresses, unexpected bytes, or unsafe frame budget cause a fail-closed rejection.

The native source manifests record exact animation count, cadence and source pixel digest. The native creation receipt distinguishes `native_hero_animation_source_integrated` from the still-false `native_hero_animation_runtime_executed`. This is not a claim of visually measured LCD/PPU animation until an actual ROM and emulator playback have been executed.

### M221–M236 — genuine platform-local audio rather than an unplayable WAV attachment

`studio_native_psg.py` creates a deterministic original eight-note theme arrangement, based on the game's theme, creative seed and bounded sound-intensity setting (0–4). It derives native 11-bit square-wave periods with hardware-specific calculations:

- For **GB/GBC**, pulse frequency is related to the register value by `131072 / (2048 - period)`.
- For **NTSC NES 2A03**, pulse frequency is `1789773 / (16 * (timer + 1))`.

The RGBDS engine now uses actual `NR52/NR50/NR51` audio enable/routing, `NR11–14` for the eight-note melody, and `NR21–24` for distinct collectible/hazard/goal cues. The CGB source reuses these handheld sound hardware controls. The NES engine uses real `$4015` channel enable, `$4000–$4003` pulse-one melody registers, and `$4004–$4007` pulse-two cues. Melody/cue writes occur in the existing game loop and its actual tile interaction outcomes. Zero intensity disables the native audio writer.

**Important fidelity boundary:** Console-local PSG scores are original thematic adaptations; they are not identical waveforms to the PCM16 WAV assets authored for browser and Godot. Existing album/artifact source identity checks do not imply audio waveform or physical speaker equivalence. Audio output, tone accuracy, mixing and latency still require actual playback capture. Register choices and hardware frequency formulas should be verified against <https://www.nesdev.org/wiki/APU_registers> and current Pan Docs before release.

### M237–M245 — single full-studio Jeeves/native-builder behavior

`native_game_cli.build_game()` now decodes actual authored hero frames via the console codec, converts authored animation FPS into bounded 60Hz console tick intervals, generates original PSG score from the same theme/direction, and passes all source pixels and sound parameters through the existing GB/GBC/NES owners. The build receipt exposes the true number of frames, cadence, score identity and the absence of independently executed animation/audio.

`jeeves_app_runtime.game.console.source.stage` can generate the same original animated and musical native source through the **existing human-reviewed project workspace**. It accepts optional bounded `animation_fps` and `music_density` controls without breaking existing callers, verifies source manifest count/digests, and uses the same CAS revision/human approval for source editing. This does not give Jeeves unchecked shell, ROM assembly or checkpoint-training authority.

Tests in `tests/test_studio_native_console_animation_e2e.py` and `tests/test_studio_native_psg.py` verify generated 1–4 frame assembly on all three console families, actual byte insertion in synthetic ROM/CHR fixtures, wrong-art / wrong-address rejections, typed hardware timer limits, five themes × five intensity levels, muted state, visible sound register writes and false-result prevention. Existing Jeeves CLI and native-game tests now assert the new source receipt fields.

### M246–M260 — explicitly unqualified release and endurance work

Actual **RGBDS/ca65 compilation, FCEUX/PyBoy animated gameplay, LCD/PPU framebuffer sequences, APU sound capture, native tone-frequency and mix analysis, frame/input timing under long replay, physical controller/speaker output, packaging, first-install, six-month/year endurance and release signoff** remain separate acceptance milestones. No synthetic ROM fixture, source code string or metadata can sign these off.

### Focused operator commands

```bash
# Test the authored animation, generated hardware sound score, and reviewed source.
python -m pytest -q -ra --tb=short --noconftest \
  tests/test_studio_native_console_animation_e2e.py \
  tests/test_studio_native_psg.py \
  tests/test_jeeves_console_source_stage_e2e.py \
  tests/test_jeeves_native_studio_art_e2e.py

# For a real original cartridge and CPU/controller replay, install RGBDS /
# ca65+ld65 plus PyBoy/FCEUX and use the existing explicit-operator E2E CLI.
python -m skeleton.ai.game_builder.studio_execution_campaign_cli \
  --order original-campaign.json --campaign ./campaign \
  --stages source,rom,emulator,browser,godot \
  --authorize-local-operation --execute-run
```

No always-on CI workflow was added, because the repository has already been constrained to minimize CI congestion. The manually selectable existing specialized suite lists all relevant offline source-contract tests. **Test registration is not a claim that the suite was run or passed.**
