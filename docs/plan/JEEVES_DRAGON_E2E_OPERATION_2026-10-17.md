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
