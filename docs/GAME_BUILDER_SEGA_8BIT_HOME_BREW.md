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

No menu uses a proprietary logo, commercial character, game soundtrack or
platform BIOS resource. The pause mode freezes movement, but still maintains a
visible familiar and frame-synchronized VDP display. Reduced-motion settings
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
