# Cross-era game capability and original-homebrew legal policy

Updated October 9, 2026. This file supersedes older guidance that
described licensed/commercial game modification in Skeleton's creative
pipeline. The **only** allowed production content is independently
authored original homebrew. Rights analysis of other works must remain
outside the create/edit/preview/export application.

## Strict admission

The homebrew gate requires an original game or independently authored
game mechanics, exclusively original assets and a hashed original source
map. The creative pipeline refuses existing-game references,
commercial-game modification or ROM conversion, commissioned or licensed
external assets, copyrighted expressive clones, trademarks, scraped
sprites/audio, extracted firmware, leaked platform SDK data, protected
keys and interoperability observation dumps.

A broad research license or a user-written permission statement does
not open an alternate third-party title exporter.

The requirement is intentionally stricter than all legally possible
uses. Source authorship, copyright and trademark rights cannot be
verified automatically by a hash: all project receipts leave release
authorization and human/independent legal review FALSE. Every new
game and editor mutation rechecks the original source provenance.
Homebrew does not itself confer console publisher privileges.

Useful official context:
- EU software directive, especially Articles 5–6:
  https://eur-lex.europa.eu/legal-content/en/TXT/?uri=CELEX%3A32009L0024
- US copyright originality and uncopyrightable methods:
  https://www.govinfo.gov/content/pkg/USCODE-2024-title17/html/USCODE-2024-title17-chap1-sec102.htm
- US Copyright Office and protected artwork:
  https://www.copyright.gov/engage/visual-artists/
- Nintendo's licensed developer process:
  https://developer.nintendo.com/the-process

Clean-room spiritual successors may independently recreate generic
mechanics, genre conventions or gameplay principles with entirely new
original expression. They cannot be guaranteed noninfringing by
automatic palette swaps, character renaming or source-file hashes.

## 166 design targets across eight eras

The catalog covers 1950s/1960s laboratory software and early computer
games, 1970s home computers/arcades, 1980s 8/16-bit consoles and
computers, 1990s 2D/3D systems, 2000s consoles/handheld/PC/mobile,
2010s and 2020s modern consoles, PC, mobile, fantasy and XR.

These are planning identities, NOT 166 actual binary exporters.

| Output | Code generator | Executed runtime | Independent release |
| --- | --- | --- | --- |
| Original CHIP-8 | Real classic homebrew .ch8 bytes | Local CHIP-8 VM / native Tk player | CI/hardware/rights not signed |
| Portable C89 | Original turn-based source | Compiler-backed win test | Target-dependent acceptance pending |
| Windows 2D | Verified original Tk 2D game | Native game runtime / headless replay | Installed window/signoff pending |
| Enhanced Windows | Original source + art/hybrid port blueprint | Native enhanced renderer and hybrid verifier | Installed and desktop signoff pending |
| NES, Game Boy, SNES, Sega etc. | Profiles only | No native ROM compiler verified | Not complete |
| PlayStation, Xbox, Nintendo modern | Profiles only | Must use authorized licensed development chain | Not complete |

## Advanced original homebrew editing

The native game editor and headless recipe CLI include 11 operators:
single-cell paint; circular, diamond and square brush; line;
rectangle; flood fill; masked stamp; spawn/goal relocation;
horizontal/vertical and 180-degree transforms; seeded original noise;
four-pass cellular smoothing; and corridor carving.

There are up to 32x32 map cells, 1,024 edited cells in a project
capsule, 256 actions per editor session, 32-command atomic batches,
stale-hash rejection, undo/redo and a hashed audit chain.
Static/dynamic analysis covers geometry, dead ends, route feasibility,
collider counts, controller-actual jump/gravity winning inputs and
per-platform export readiness.

Every created file uses exclusive Save As; no imported game, ROM,
protected third-party asset or model-training record is accepted.

## Destination adaptation: original Windows ports

Homebrew adapts to its destination rather than being artificially
limited to the original hardware palette or resolution. The Windows
path PRESERVES original map, collisions, start/goal, physics,
independent rights source and original replay, while adding original
graphics and optional self-authored hybrid gameplay modes.

Seven distinctive art directions; three rendering budgets;
16–56 pixel tile resolution; procedural decoration, parallax,
camera and goal glow; reduced-motion, high-contrast, colorblind-safe
palettes and an optional HUD are implemented.

Five genuinely simulated hybrid extensions are implemented:
collectathon scoring, collected-key gated victory, speedrun medal,
exploration fog and combo multipliers. Multiple modes can be
combined; a source controller trace must still produce a deterministic
valid destination victory.

For command examples, operator choices and native GUI port-studio
options, see HOMEBREW_DESTINATION_ADAPTATION.md.

A Windows blueprint is playable by the existing SkeletonGame.exe;
this does not claim per-title independent .exe installer generation.
Console-native exporters beyond CHIP-8, licensed SDK entitlement,
full multimedia editors, real desktop visual acceptance and complete
hardware coverage remain open. Do not mark these as done.

## Data discipline

The port/editor pipeline adds zero training records and does not change
the synthetic 720-record reference dataset. The active sparse default
remains 36 examples (optional 48/72 by configured policy).
