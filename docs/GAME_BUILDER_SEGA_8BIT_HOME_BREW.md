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

