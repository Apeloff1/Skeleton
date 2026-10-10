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
python -m skeleton.ai.game_builder.native_game_cli \
  --target sega_master_system --basis bandai_wonderswan \
  --project-id entirely-new-game --title 'My Original Star Maze' \
  --seed 1979 --width 17 --height 15 --levels 3 \
  --collectibles 3 --hazards 4 --health 4 \
  --rights-evidence ./my-authorship-proof.txt \
  --identity 'my original tiles and shapes' \
  --identity 'my own game concept and rules' \
  --output ./original-sms --authorize-original-homebrew
```

Substitute `sega_game_gear` for the handheld project. `native_portfolio_cli`
can also emit both with a shared, independently authored world digest.

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
