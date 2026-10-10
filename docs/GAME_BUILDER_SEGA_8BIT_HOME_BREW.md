# Native Sega Master System and Game Gear homebrew adapter

**Scope:** Independently authored, rights-referenced source projects. This is not a
Sega SDK, a licensed commercial-game port, an emulator, or redistribution
approval.

## Implemented

`skeleton.ai.game_builder.sega_8bit_native_export` compiles the same replay-proven
`PlayableWorld` into two genuinely distinct **Z80 C game source** envelopes:

| Machine | Original display | Authorable playfield | On-screen location | ROM output |
|---|---|---|---|---|
| Master System | 256x192, 32x24 tiles | up to 31x21 | 0..30, rows 2..22 | `.sms` |
| Game Gear | 160x144 visible crop of SMS VDP | up to 19x15 | columns 6..24, rows 5..19 | `.gg` |

Each source contains an original four-plane Sega VDP tile set, original numeral
glyphs, individual authored stage ROM arrays, matching stage spawns, visible
on-console objective/health/score HUD, four-way controller input, bounded
movement timing, collision logic, collectible consumption, hazard damage, stage
transitions, and distinct win/loss appearance. The Game Gear edition uses
Game Gear palette instructions, visible viewport and `TARGET_GG` plus the GG
library; it is **not** a Master System binary renamed to `.gg`.

Sources and build scripts are deterministically hashed together with a
manifest binding game-world, safe replay, original-project, rights-reference and
port-planner digests. Compiler/emulator/hardware/distribution claims remain
false unless a later independent gate records actual evidence.

## Authoring

```sh
printf '%s\n' 'My independently authored graphics, rules and level design.' > my-authorship-proof.txt
python -m scripts.game_builder.native_sega_8bit_ci \\
  --target sega_master_system \\
  --emit ./original-sms --author-evidence ./my-authorship-proof.txt
```

Use `sega_game_gear` to generate the handheld SDCC backend. The
`native_game_cli` and native portfolio additionally expose an independently
authored **direct Z80 assembly** Master System exporter. Both methods generate
original machine-specific games; they are distinct implementations, not a
renamed cartridge. The SDCC generator is invoked explicitly above to avoid
silently replacing the independent Z80 assembly backend.

## Building with separately obtained tools

Use a **lawfully obtained and appropriately licensed** SDCC 4.2+ installation
and devkitSMS-compatible source/build tools. The generator never downloads or
redistributes them. Follow the toolchain's own documentation and notices;
review all linked runtime/library, CRT, converter, and toolchain obligations
for the exact revision you choose.

```sh
make -C original-sms \
  SMSLIB_DIR=/path/to/devkitSMS/SMSlib \
  CRT0_SMS=/path/to/crt0_sms.rel \
  SDCC=sdcc MAKESMS=makesms
```

`SMSLIB_DIR` must point to a directory containing the proper `SMSlib.h`
and `SMSlib.lib` (or `SMSlib_GG.lib`) arrangement. Supply a separate
include directory or adapt the local Makefile if your devkitSMS package lays
those files out in different directories. Do not copy CRTs/libraries into
distributed game archives without verifying their precise licence conditions.

The output of `make` is an intended genuine `.sms` / `.gg` cartridge ROM,
**not an attested build** merely because this recipe is present. Next acceptance
work should compile in a pinned and licensed toolchain, verify the console ROM
header/size/checksum, then execute a deterministically checked gameplay route
in an appropriately licensed emulator (and ultimately supported real hardware).
Actual compiled ROM, emulator gameplay and provenance evidence must be
cryptographically bound before any release approval.

## Legality and originality

A new game targeting the hardware may be lawful without the commercial rights
to a third-party game, but this does not create permission to extract
copyrighted game content, trademarked characters, music, artwork, firmware,
proprietary keys or protected SDKs, or to circumvent technical protection
measures. No hardware incompatibility or publisher inactivity overrides
applicable intellectual-property law. Third-party tools are **dependencies**,
not original artwork or proprietary assets embedded by this adapter.

The standard Sega-compatible ROM header is a compatibility record, not a claim
of Sega affiliation, licence or sponsorship. If used commercially or
distributed, review the target territory, third-party tool/library obligations,
possible trademark concerns, and applicable platform policies with qualified
human reviewers. Similarity/originality scanning cannot guarantee noninfringement.

Upstream technical references (not bundled):
- https://github.com/sverx/devkitSMS
- https://github.com/sverx/devkitSMS/blob/master/SMSlib/src/SMSlib.h

**Verification status:** Original source emitted; no verified ROM, emulated
controller replay, actual-hardware proof, legal certificate or permission to
redistribute claimed.


## Living companion, musical reactions, and eight cosmetic ranks

The SDL-free cartridge generator now emits distinct **native Z80 code** for an
original expressive follower. The actual authored display assets are 8x8
four-plane VDP pixels (22 tiles × 32 bytes), not PNG animations, JavaScript,
HTML or sprite frames extracted from a commercial game. In addition to the
player's alternate pose, the tiny follower has curious, blink, joy, injury and
celebration expressions. A second renderer uses the Sega VDP's **hardware
sprite attribute table**, with a visual bob above the player. The companion
also lives in the score HUD, where the player can see its current expression.

Collectibles grant a **purely cosmetic bond progression** through eight ranks.
Thresholds are 3, 7, 12, 18, 25, 33 and 42 collectibles. A level-up changes
the follower's expression and plays a short reward cue, but it never modifies
the source game's authoritative map, collision, pathfinding, collectible
scoring, health, win condition, release rights or signed provenance. The
original deterministic replay remains the authoritative gameplay reference.

All sounds are synthesized as original SN76489 PSG register writes; no
third-party sample, music file, commercial game melody, BIOS sound or
proprietary API is copied. Pickup, damage, game-over and advancement signals
use bounded tones rather than arbitrary host-side playback.

Display updates are coalesced into a small queue and limited to three name
table changes per VBlank. The independently authored familiar uses separate
sprite memory and a two-step bob instead of writing over game collision tiles.
Neither implementation has yet been proven on the real hardware in this
increment. The presence of native source and test assertions is **not**
emulator acceptance.

The manifest records all optional animations, personality ranks, reaction
sound capability and non-authoritative cosmetic status. It deliberately keeps
`emulator_playthrough_verified`, `physical_hardware_verified`, and
`release_approved` false. Exact cartridge generation, gameplay replay,
audio timing and physical console compatibility remain separately gated.


## In-game controls and accessibility

The generated original ROM contains keyboard-free, real-device input handling:

| Input | Master System | Game Gear |
| --- | --- | --- |
| D-pad | Navigate the playable maze | Navigate the playable maze |
| Button 1 | Toggle original PSG sound on/off | Toggle original PSG sound on/off |
| Button 2 | Pause/unpause game physics and controls | Toggle reduced-motion effects |
| Start | Not available as a standard dedicated hardware key | Pause/unpause |
| Briefly press buttons 1+2 together | Pet the original companion | Pet the original companion |
| Hold buttons 1+2 for 25 video frames | Play a native demonstration using the authored solution | Play the same native authored demonstration |
| After winning or losing | Button 2 starts a fresh campaign | Start begins a fresh campaign |

No menu uses a proprietary logo, commercial character, game soundtrack or
platform BIOS resource. The pause mode freezes movement and immediately silences PSG channel zero
to avoid a stuck note, but still maintains a visible familiar and
frame-synchronized VDP display. Restarting after victory or defeat restores
the original game colors instead of leaving the victory/defeat palette
stuck on the next run. A companion pet gesture produces a brief animated
reaction (a smile, or a cheer every fourth pet) and a fresh original short
tone when sound is enabled. Pets do not give score, health, objectives,
unlock gameplay ranks, or alter replay integrity. The optional attract mode
runs the exact same native gameplay rules as a human player; a new human
input cancels it and restores a clean original game. Reduced-motion settings
suppress cosmetic blinking and breathing; the follower keeps a fixed offset
rather than bouncing. Companion improvements are cosmetic, never a reason to
make a formerly playable world unwinnable.

Builders can also set `reduced_motion=True` and `audio_enabled=False` via the
low-level `compile_native_sega_8bit` function. Those defaults are encoded into
the generated Z80 game's own C source and manifest, producing a distinct,
content-hashed artifact without changing the original world digest or safe
replay identity. The consumer may override defaults with the inputs above
where the console's hardware supports those keys.

These are authored implementation capabilities. Verified ROM execution,
accessibility acceptance by disabled players and physical console testing are
still separately pending.


## Hardware-native art direction

Five original visual themes are supported in actual cartridge C source:
`forest`, `space`, `desert`, `ocean` and `arcade`. They are not CSS,
external image themes or a desktop-only preview. Each selects distinct
full-color Game Gear 12-bit RGB444 palette bytes and a separately constrained
Master System 6-bit RGB222 CRAM palette, shared between backgrounds and the
animated native familiar's hardware sprite. Each palette is written through
the relevant devkitSMS hardware API at initialization.

Each generated source manifest includes both hardware palette vectors, the
original game's requested art direction, and an exact content digest. The
theme is part of the authored `PlayableWorld` identity; changing it is a new
generation that requires rechecking and re-signing release evidence, rather
than silently reusing a previous build certificate. No sample artwork or
platform-exclusive commercial textures are copied.

## Real SDCC toolchain revision, source and authorship evidence

The original Sega Master System/Game Gear CI uses a pinned public Git
revision of devkitSMS (`533ae572c897cf44f1da865013ebf690134301a3`).
This is an **exact 40-character Git SHA-1 commit ID**. It must not be
misidentified as a SHA-256 content digest, which is 64 hexadecimal
characters. The `native_sega_8bit_ci.verify` adapter accepts full Git
revision IDs of either 40 or 64 hex digits, refuses branch/tag names,
partial revisions and malformed hashes, and labels the revision algorithm
in the resulting receipt. A commit ID is not proof of signed toolchain
provenance: `toolchain_source_authenticated` remains false.

Original source authorship and the native ROM are **different evidence
objects**. The dedicated workflow now records the authored game's source
digest and the author's declaration-file digest at generation time, before
compiling with SDCC. The later verification step reopens the real game C,
Makefile and manifest using no-follow directory file descriptors, rejects
unreviewed extra root files, allows only the separate legitimate `build`
directory and validates the exact prebuild source and author declaration
hashes. Both checks are recorded distinctly; matching developer-provided
hashes does **not** establish independent legal clearance, compiler
authenticity or a license to reuse third-party commercial material.

The ROM file also uses no-follow, bounded, inode-checked opening. Symlinked
ancestor paths, hardlinked ROM bytes, named pipes and oversized sparse
cartridges fail closed rather than falling back to unsafe `Path.read_bytes`
after an earlier symlink check.

The workflow separately checks that a clean second SDCC build produces the
same SHA-256 ROM as the first build and uploads **receipts rather than public
ROM binaries**. Deterministic output is valuable regression evidence but
does not prove emulator boot, game playability, developer-kit license
compatibility, or publisher distribution rights. Those require distinct
trusted provenance and authorized operating-system/hardware evaluation.

Regression coverage includes 40-character real Git revision IDs,
64-character Git SHA-256 IDs, malformed or abbreviated IDs, changed source
after generation, substituted authorship records, unreviewed extra files,
allowed build intermediates, linked/sparse cartridge files and forged
release booleans.


## Differential execution of actual generated game logic

A deterministic, independently generated reference now accompanies each
original native SDCC console example:

```bash
python -m scripts.game_builder.native_sega_8bit_ci \
  --target sega_game_gear --emit ./homebrew-gg \
  --host-reference-out ./gameplay-reference.json \
  --author-evidence ./my-authorship-proof.txt

python -m scripts.game_builder.sega8_source_replay \
  --source-dir ./homebrew-gg \
  --reference ./gameplay-reference.json
```

The second command uses GCC to **compile and execute the very same emitted
`game.c` gameplay implementation** with a deliberately narrow host-only
SMSlib hardware stand-in. It is not a restatement of the gameplay rules in
Python, nor an independent Game Gear or Z80 emulator. The input actions and
every expected movement, health, score, objective, win/loss and cosmetic
companion rank are computed beforehand from the authoritative independently
maintained `playable_simulation` reference. The generated C must match each
step exactly. The host stub also checks original VDP name-table writes,
four-digit score glyphs, companion rank UI updates, palette writes and
per-move follower sprite submission.

A dedicated adversarial eight-stage case verifies the entire maximum
world stack, a 1,280-point final score, seven bond unlocks, and terminal
level-index safety. The native engine was repaired after discovering an
incorrect final-level increment and missing 100-point exit rewards.

The CI workflow now requires **both** this host-executed gameplay
differential **and** independent real SDCC cartridge builds with bounded ROM
integrity evidence. The two checks are complementary: neither a valid
cartridge header nor host C execution alone proves machine-code playability.
Neither constitutes an independent license review or permission to
redistribute a ROM, a proprietary firmware component, or external artwork.

Required remaining gates before claiming a fully playable native cartridge:
independent Z80/VDP input-driven emulation of the **compiled** SMS/GG ROM
with a complete winning replay, external emulator confirmation,
and targeted physical hardware tests. Each status is separately represented
in the evidence and remains false until that test actually occurs.


## Two-source, two-cartridge deterministic evidence (October 2026)

The native Sega Master System and Game Gear CI now performs independent
source-generation calls before native compilation. The second authored output
lives outside the released source tree and must match `game.c`, `Makefile`
and `manifest.json` **byte for byte**, along with the previously recorded
source SHA-256. A file differing in an edited game mechanic, sprite table,
audio engine, C flags, copyright/rights marker or legal claims fails closed.
The comparison also rejects unreviewed extra files and linked source folders.

After real SDCC and devkitSMS compilation, CI records the *first* native
32 KiB ROM outside the game build directory. It performs a clean second
build, then invokes:

`python -m scripts.game_builder.sega_reproducibility_ci`

The comparison insists on two distinct, safely opened cartridge paths,
correct hardware-specific Sega headers and checksums, the exact same ROM
SHA-256 as the first postbuild report, literal equality of the two 32 KiB
cartridge payloads, and uninterrupted links to the authored source,
author-declaration digest, safe replay digest, original world digest and
pinned Git toolchain revision. The source root may include the legitimate
`build` folder only; compiled output may not masquerade as source input.

### Evidence terminology is deliberately narrower than legal certification

| Receipt field | Meaning |
| --- | --- |
| `identical_source_bytes=true` | Two existing source folders actually contain the same reviewed file bytes |
| `exact_rom_bytes_match=true` | Two actual ROM file payloads passed the format checks and are identical |
| `source_and_authorship_digests_match=true` | The read source and author-declaration hashes agree with the separately supplied expected values |
| `two_compiler_executions_independently_verified=false` | The byte reader cannot observe two actual process executions; trusted CI is responsible for that |
| `generator_invocations_independently_attested=false` | Two source folders do not by themselves prove two independently executed generators |
| `source_rights_independently_verified=false` | User-supplied authorship declarations are *not* proven legal title |
| `gameplay_execution_verified=false` | Header/ROM comparison is not emulator or hardware playthrough |
| `publication_licensed=false` | Source/ROM determinism cannot authorize third-party proprietary redistribution |

The CI uploads **only** bounded JSON receipts (and preexisting permitted
source metadata). The first and rebuilt ROMs are temporary and are not
uploaded as public commercial game binaries by this release-integrity
workflow. Other platform-specific output workflows have separately
documented build artifacts and should not be misrepresented by this policy.

The provenance receipt is written create-only, using a descriptor-anchored
directory and exclusive file creation with restrictive permissions. It
refuses overwriting or following existing output symlinks and removes only
its own partially created file on serialization failure; it does not
delete a preexisting file after an exclusive-open collision.

### Highest-value adversarial examples

- Replace the first cartridge with a ROM of the wrong console, a different
  checksum-valid game, a copied commercial title or a header-only stub;
  exact source and ROM hashes prevent inheriting previous evidence.
- Keep the additive Sega checksum the same while swapping program bytes;
  SHA-256 and actual byte comparison detect the change.
- Modify only `Makefile`, `game.c`, `manifest.json`, source rights or
  author declaration, then attempt to reuse the previous first-build proof.
- Replace a generated source, author statement or cartridge with a linked
  inode, symlinked parent, named pipe or sparse over-budget file.
- Reuse a Sega Master System receipt for Game Gear, or a different project
  world, release territory or unpinned developer revision.
- Fake `source_rights_independently_verified`, `release_approved`,
  hardware acceptance or compiler execution booleans in the prior JSON.
- Replace an existing integrity JSON via a symlink or induce a failure
  after creating a partial receipt.

These cases are covered by
`test_game_builder_sega_reproducibility.py` alongside the existing Sega
ROM, game-engine and reviewer-identity suites.

**Outstanding:** the SDCC development kit's license compatibility still
requires accountable human review. Full SMS/Game Gear emulator *gameplay*
replay and physical-console validation remain separate milestones.

## Real Z80 opcode startup acceptance

The dedicated build workflow now performs a strictly bounded *compiled cartridge
boot test* as well as the existing host-C gameplay replay. It opens the real
32 KiB .sms or .gg cartridge with the no-follow binary intake, verifies Sega
header and checksums, then interprets **the actual Z80 opcodes at reset PC 0**
using the separately installed z80-python==0.4.0 instruction core.

The device test bench models unbanked ROM, mirrored 8 KiB console RAM,
active-low controller ports, Mode-4 VRAM and VDP command writes,
Master System RGB222 and Game Gear RGB444 CRAM, PSG ports and synthetic
VBlank interrupts. Unsupported hardware I/O and execution beyond strict
instruction/frame limits fail the test.

The ROM must actually initialize color and video hardware, enable display,
draw one hero on its game board, draw the original companion expression
and zero-score HUD, initialize PSG sound and acknowledge a video interrupt.
Every successful result is bound to the actual cartridge SHA-256.

The resulting receipt can assert hardware_boot_smoke_verified only after
this real machine-code execution. It retains **false** values for
entire_game_playthrough_verified, independent_cycle_exact_emulator_verified,
physical_hardware_verified and release_approved. A successful boot smoke
test cannot substitute for a full input-driven winning route, cycle-accurate
console emulation, electrical compatibility or legal distribution clearance.

Run the gate against an original cartridge compiled using the pinned
devkitSMS/SDCC workflow:

```bash
python -m pip install z80-python==0.4.0
python -m scripts.game_builder.emulate_sega8_sdcc_boot \
  --rom ./homebrew-gg/build/skeleton-original.gg \
  --target sega_game_gear --receipt-out ./game-gear-z80-boot.json
```

## Cross-console originality and gameplay-parity gate

A separate CI job runs only after both independent cartridge-build jobs
complete. It retrieves the two original-game evidence artifacts without
downloading or distributing the game ROMs themselves. It verifies that
the Sega Master System and Game Gear ports preserve the **same original
project, world digest, safe winning replay, author-evidence fingerprint,
visual theme, level count, world dimensions and title**.

The required native binaries must have **different** SHA-256 hashes and
console-specific .sms/.gg header identities. Gameplay test receipts must
confirm the same level and input-action counts, while independently
binding each console's own source SHA-256 and compiled-ROM SHA-256.
The hardware-facing Z80 boot smoke must also have passed independently
for each variant. Source-specific host reference hashes are not required
to match, since they incorporate intentionally distinct native outputs.

Release review is fail-closed: missing, duplicated, symlinked, hardlinked,
tampered, incorrectly routed or rights-elevating JSON evidence is rejected.
The generated cross-port receipt is content-hashed and keeps full Z80
playthrough, physical hardware verification, external rights review and
release authorization marked **false** until those gates actually succeed.

Both targets are original homebrew. Hardware compatibility headers,
recognizable genre conventions and independent reimplementation are not
treated as permission to extract commercial assets, distribute proprietary
firmware or plagiarize a protected game's audiovisual presentation.


## Cross-port verification requires reproducibility receipts (October 10, 2026)

The final Master System/Game Gear parity stage now **refuses** to conclude
the ports are equivalent unless it can inspect *both* console-specific
`skeleton.game_builder.sega_reproducibility.v1` receipts alongside each
native source manifest, host-executed original C replay and the bounded
real-Z80 startup evidence.

Every reproducibility receipt must match its own console's exact world,
source, signed-scope author declaration, safe route, 32 KiB ROM SHA-256,
full Git toolchain commit and independently compared source/tree identities.
The comparison digest is recomputed from the complete immutable JSON
representation. Duplicate JSON fields, unknown data fields, fake legal or
full-hardware success booleans, altered compilation metadata and missing
second-build reports are rejected.

The final parity receipt contains a separate SHA-256 digest for each
console's native rebuild report. Different machine ROM binaries remain
distinct, while their original authored world and solved route remain
the same. The final report writer uses create-only/no-follow file handles:
the cross-port output cannot silently overwrite an old approved receipt.

**The cross-platform outcome can establish agreement of existing source,
ROM and host-replay reports; it cannot independently establish that two
compiler processes ran, that the Z80 emulator is cycle-accurate, or that
copyright clearance or publication permission exists.** These remain
explicitly separate fail-closed gates.

An independently executed 8-bit CPU startup smoke test has also exposed
a current integration failure: the compiled Z80 interpreter has been
exhausting its bounded instruction budget without the expected video or
audio I/O writes. The branch must NOT be marked hardware-playable until
the startup trace, selected CPU core, real ROM mapper and device callbacks
produce validated hardware-facing results in exact-head CI. Successful
source-host gameplay tests do not substitute for real ROM CPU execution.

## Complete native Z80 winning-route execution

The original homebrew pipeline now has an **input-driven native game replay**
that loads the real SDCC-generated 32 KiB Sega cartridge into an independent
Z80 instruction interpreter and observes only the guest console's video
memory, hardware palette and controller operations. It does not copy Python
gameplay rules into the emulator or override guest RAM with expected values.

For each independently generated safe move the runner presses the actual
console joypad bit, gives the native cartridge time to handle interrupt
driven input and drain its bounded VDP queue, then releases the button.
The original hardware name table is inspected for **exactly one hero tile**,
stage, coordinates, health, collectibles, four-digit score and cosmetic
companion rank. If any guest observation differs from the source-game
reference, including after the controller is released, acceptance fails.

At the final authored exit the guest must actually change the original
hardware palette to the victory color in its console-specific color
RAM: RGB222 on Master System and RGB444 on Game Gear. Test receipts bind
every action, screen state, original project digest, source digest and
compiled ROM SHA-256. A source-only replay or a structural ROM checksum
cannot satisfy this acceptance gate.

After building an original ROM and its independent source route:

```bash
python -m scripts.game_builder.sega8_real_z80_gameplay \
  --rom ./homebrew-gg/build/skeleton-original.gg \
  --source-dir ./homebrew-gg \
  --route ./original-winning-route.json \
  --target sega_game_gear \
  --receipt-out ./game-gear-real-z80-gameplay.json
```

The CI matrix builds both consoles separately and checks that their
original rules and route outcomes agree while the cartridge bytes remain
distinct. The cross-port gate requires both machine-code replay receipts
before reporting full native Z80 gameplay parity.

This is instruction-level execution with a deliberately bounded device
model and synthetic video interrupts. It is **not** a cycle-accurate
full-consumer emulator, physical-console acceptance, or legal permission
to redistribute ROMs, outside artwork or proprietary firmware. The
latter statuses remain explicitly false even after a successful replay.


## Deterministic native screen-state transcript (October 10, 2026)

The original Sega game now records a compact **instruction-level gameplay
semantic chain** while replaying the independently generated winning route
against actual compiled Z80 ROM bytes. The chain commits to the actual
VDP-observed player X/Y, stage, life, collectible count, score and companion
rank, and the real controller button and input position. **Host reference
predictions never supply the recorded screen-state input.**

The chain begins with a domain-separated SHA-256 digest of the original
world identity, then folds each observed initial screen and each actual
controller movement into the prior digest. The replay report records the
final `semantic_controller_screen_trace_sha256`, the exact count of screens
hashed, a total native Z80 instruction budget and a total frame budget.
Bounded execution rejects loops and routes that exhaust the hard budget,
rather than silently keeping the worker occupied indefinitely.

The Master System/Game Gear cross-port validator now demands the
**same semantic gameplay trace**, not just matching level counts, game
identity and overall action count. Hardware-specific render placement,
color palette, instruction count and scheduling may differ; actual
gameplay state and controller-input sequences may not.

The source reference and generated manifest use the strict bounded JSON
intake with duplicate-key detection. Exact typed fields are enforced at
the root, original initial state and each action. A replay must not start
already won or lost; floating infinities, non-finite values, unknown
extra source fields, invalid controller actions or altered rights/status
claims fail closed even when an attacker recomputes the unsiged JSON digest.

**Boundaries:** the trace demonstrates an instruction-level Z80 guest
running under the project's deliberately limited SMS/Game Gear model.
It is not an independent cycle-accurate console emulation, physical
controller/audio measurement, anti-malware audit, official platform
certification or copyright release approval. Those remain independent
human/technical gates with separate evidence.

Target tests:
- `skeleton/testing/test_game_builder_sega8_real_z80_gameplay.py`
- `skeleton/testing/test_game_builder_sega8_port_parity.py`
- `skeleton/testing/test_game_builder_sega8_route_security.py`

All are now in the focused historical archive checks; the native
Sega CI also runs original source replay and compiled native guest
execution for both consoles.

## Native original-game demonstration and exhibition controls

Both **Master System** and **Game Gear** cartridges now embed each generated
world's own independently verified safe solution as a compact native
direction table, with no commercial video-game data or proprietary assets.
Four directions (up/down/left/right) are packed into two-bit codes, **four
moves per ROM byte**, with the first move in the lowest two bits. This
uses approximately one quarter of the cartridge ROM space required by an
uncompressed one-byte-per-move route, especially useful on fixed 32 KiB
Master System and Game Gear cartridges. The individual level lengths and
the cross-console canonical route hash preserve stage boundaries and
make any altered, missing or reordered move fail acceptance.

Hold both face buttons **1 + 2 together for 25 video frames** to start
an optional original-game exhibition. The cartridge resets the score,
health, collectible counters and cosmetic companion rank to an unplayed
level 1, restores the original theme palette, and then performs the
solution movements using exactly the same native `advance()` gameplay
routine used for human-controlled play. Each level hands off to its own
verified route. Actual game collision, score, collectible and victory
rules are never bypassed by the demonstration.

Press any **new** button during playback to cancel; the game restores a
new human-controlled run. Playback never starts automatically. The
two-button chord takes precedence over individual pause/sound toggles
while held, preventing accidental state changes. The demonstration
can be invoked after a finished game as well as before the first move.

The original authored paths are generated into *different* native ROM
source files for each destination console. The CI host compiler executes
the real emitted C tables separately and must reproduce every state of
the source-game replay. An additional instruction-level Z80 gate presses
the real face-button combination against the compiled cartridge and
**replays the entire original winning solution without directional input**.
Every autonomous stage, score, reward, collectible, companion rank and
screen coordinate must equal the authoritative independent reference.
The game must enter its genuine hardware victory palette again, and
the hash of all guest-observed automatic game states must match the
earlier manual-input Z80 winning route. A second demonstration is
then started, allowed to make its first original move, cancelled with
a real hardware button press, and checked for a pristine game reset.

Cross-console acceptance rejects a missing/modified demonstration
fingerprint, unequal gameplay traces, absence of real Z80 demonstration
activation or a cancelled exhibition that fails to restore user control.
The receipts still never claim physical hardware testing or legal
publication approval without independent verification.

## Extended original campaigns and stage-specific physical palette adaptation

The independently authored native hardware exporter supports a full
**eight-level campaign** alongside the earlier three-level demonstration.
Each stage includes six original collectible objectives, an independently
solved safe route, optional authored hazards and original sprite/audio
interactions. Forty-eight total collectibles unlock all seven cosmetic
companion progress ranks and yield a **1,280-point** winning game. Stage
progression is still performed by the same collision-and-reward engine;
there is no host-side game-state mutation or shortcut to victory.

Example creation without any proprietary ROM, BIOS or commercial artwork:

```bash
python -m scripts.game_builder.native_sega_8bit_ci \
  --target sega_master_system \
  --profile full_campaign \
  --emit ./my-original-eight-stage-sms \
  --author-evidence ./my-original-authorship.txt \
  --host-reference-out ./my-original-route.json
```

The dedicated native CI matrix now also creates this full campaign for
**both** Master System and Game Gear, executes its native C against the
complete independently generated reference, compiles real cartridges with
the pinned legal toolchain, validates their genuine 32 KiB Sega ROM
structures and boots their compiled Z80 instructions. The eight-stage
campaign additionally has a **required full compiled-Z80 winning route**,
including every authored collectible, all eight stage exits, exact
score and bond progression, actual hardware CRAM stage colors and a
second autonomous on-cartridge completion with the same semantic trace.
The native replay uses a bounded 30,000-frame overall execution envelope;
CI must pass for both variants before this acceptance is considered
verified. The compiled ROM is intentionally not uploaded or
distributed as an artifact.

## Hardware-native stage color progression

Each original visual theme (forest, space, desert, ocean and arcade) now
generates deterministic **per-stage color accents** for both hardware
palettes: Master System RGB222 and Game Gear RGB444. Native level
transitions call the console video palette APIs rather than altering
collision, collectible, health or score state. Stage zero retains
the originally authored theme, and later stages rotate and harmonize
accent channels. Contrast protection prevents physical color quantization
from collapsing two different world accents to the same or nearly
indistinguishable color, especially in the 2-bit Master System palette.

Exact stage colors are included in the signed-source candidate manifest.
Host tests validate five original themes across eight stages, and the
instruction-level acceptance runner inspects actual CRAM palette bytes
after every human-controlled and autonomous demonstration move. Cross-
console parity rejects missing palette data, invalid RGB222/RGB444 values,
mismatched original color plans and absent real Z80 stage-color checks.

This work neither uses copyrighted third-party palettes nor certifies
rights, distribution permission, physical hardware timing or compatibility
with proprietary games. Those independent release gates remain closed.

## Author your own independent native cartridge project

The console builder is no longer limited to bundled example campaigns.
Use the bounded `custom_original` profile to create a new, deterministic
homebrew game from your own project identity, title, seed, theme and
level configuration, with its own independently solved playable maps.

```bash
python -m scripts.game_builder.native_sega_8bit_ci \
  --target sega_game_gear \
  --profile custom_original \
  --original-project-id my-original-ocean-quest \
  --original-title 'My Original Ocean Quest' \
  --original-seed 271828 \
  --original-theme ocean \
  --original-levels 4 \
  --original-width 17 \
  --original-height 15 \
  --original-collectibles 5 \
  --original-hazards 4 \
  --original-health 4 \
  --emit ./my-original-gamegear \
  --author-evidence ./authorship-evidence.txt \
  --host-reference-out ./my-original-winning-route.json
```

Supported themes: `forest`, `space`, `desert`, `ocean`, `arcade`.
The shared SMS/GG console-safe profile allows odd map dimensions of
9–19 columns and 9–15 rows, 1–8 stages, 1–6 collectibles per stage,
0–24 hazards, and 1–10 initial health, subject to the source world's
independent solvability constraint and the aggregate 48-collectible
native progression cap. Seed values are bounded and replay-deterministic.
The generated native `game.c`, `Makefile`, `manifest.json`, signed-source
candidate digest and original winning-route reference are kept separate
from any proprietary ROM or BIOS.

The user-provided authorship file is a **claim and fingerprint**, not
external proof of copyright ownership. The generator does not authorize
publishing, reverse engineering third-party game expression, including
copied visuals/audio, or bypassing a platform's real license terms.
No automatically fabricated legal review, independent rights approval,
physical hardware pass, or distribution license is asserted.

The same profile can target `sega_master_system` instead of Game Gear
while retaining original world identity and adapting actual palette,
viewport and sprite interfaces to the destination hardware.
