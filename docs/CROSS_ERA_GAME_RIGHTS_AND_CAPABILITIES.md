# Skeleton game capabilities: every era, verifiable rights and real artifacts

**Status:** Cross-era architecture and portable game composition built on PR
#3593. **166 named design-target profiles**, from 1950s computer/analog
experiments to 2020s PC, console, handheld, mobile and XR systems.

**Critical distinction:** A target profile is **not** a working hardware
emulator, console ROM exporter, publisher license, compatibility guarantee
or proof of hardware/SDK access. Every target currently reports
\`native_export_implemented=false\`, \`real_hardware_validated=false\`,
and \`sdk_access_verified=false\`. The working universal project emitter
and original portable C89 game exporter are separate from these
as-yet-unimplemented platform-specific build adapters.

## 1. Mission: full capability *planning*, honest readiness

The unified game system has four layers:

1. **Original, rights-attested project:** authored tiles, bounded edits,
   source SHA-256 and provenance manifest; protected/circumvention-dependent
   input is not admitted.
2. **Engine-neutral content compiler:** tiles, 2D scene, colliders,
   player/goal entities, deterministic game mechanics and replay.
3. **Target capability planner:** target features, missing design capabilities,
   toolchain entitlement required, unimplemented export blocker,
   hardware and compliance evidence.
4. **Verified build adapters:** separate future adapters for truly
   supported runtime/toolchain/hardware combinations. At present only
   portable project JSON and playable **generic ISO C89 console source**
   are implemented. A small native Windows Tk game also exists as
   \`SkeletonGame.exe\` in the app installer.

This architecture supports both independent original game creation and
modification of **properly authorized** work without treating ownership
claims, historical availability, abandoned servers or tools found online
as a legal exemption.

## 2. Coverage inventory

The checked-in catalog now includes original 1970s CHIP-8 VM homebrew alongside other historical systems. A real `.ch8` ROM generator and in-memory emulator are implemented for that one target, with hardware/legal signoff still pending.

The checked-in catalog at
\`skeleton/ai/runtime/game_platform_catalog.py\` spans:

| Era | Representative platforms | Scope |
| --- | --- | --- |
| 1950s/1960s | EDSAC OXO, Tennis for Two, PDP-1 Spacewar, early mainframes | Historical design reconstruction **only** |
| 1970s | Odyssey, Pong, Atari 2600, Channel F, Intellivision, Apple II | Original low-complexity game design |
| 1980s | NES/Famicom, Master System, Game Boy, C64, Spectrum, Amiga, MSX, Atari, PC DOS, arcade boards | 8/16-bit content architecture |
| 1990s | SNES, Mega Drive, PC Engine, Neo Geo, Game Gear, N64, Saturn, Dreamcast, PlayStation 1, DOS VGA, arcade 2D/3D | 2D sprite and early 3D planning |
| 2000s | PlayStation 2/3, Xbox/360, GameCube, Wii, PSP, DS, GBA, Windows PC, early mobile | Mixed 2D/3D design |
| 2010s | PlayStation 4, Xbox One, Wii U, Switch, Vita, 3DS, Windows/Linux/macOS, iOS/Android | Licensed SDK and modern toolchain gating |
| 2020s | PlayStation 5, Xbox Series X/S, Switch 2, Steam Deck, PC, modern mobile, XR, fantasy consoles | Device/API and publication compliance gating |

The catalog records broad **potential** design features, not validated
hardware limits or manufacturing facts. Historical, official and
community development tools vary in legality, availability and quality;
their presence is never assumed.

## 3. Rights admission and lawful modification

\`skeleton/ai/runtime/game_rights.py\` requires a unique asset ID, source
SHA-256, rights contact, source kind, licensor, actual permission scope,
license/reference, third-party/trademark/technological-protection flags
and review jurisdiction. Asset source categories include original,
commissioned, open-licensed, licensed, public-domain-*claimed*,
interoperability research and unverified user-supplied content.

Actions supported for **admission analysis**:
\`original_game\`, \`independent_mechanics\`,
\`modify_authorized\`, \`private_reproduction\`,
\`interoperability_study\`, \`publish\`, \`train_on_assets\`.

- **Create or independently recreate mechanics:** use original code,
  map layouts, audiovisual expression and branding. Do not embed assets
  copied from a reference game's ROM or claim endorsement.
- **Modify third-party games:** identify the specific source and
  license/permission to modify. Modification rights are distinct from
  permission to redistribute or commercially exploit that derivative.
- **Homebrew retro titles:** author original content and use toolchains
  under their own licenses. Never bundle commercially protected BIOS,
  firmware, cryptographic keys, proprietary SDK data or existing ROMs.
- **Interoperability research:** keep facts/observations segregated from
  copied expressive content. The importer blocks these observations
  from automatically becoming distributable/training assets.
- **Published games:** copying visual design, text, characters, names,
  sound recordings or logos may require *separate* rights even when
  the game logic is independently implemented. Trademark and
  platform/publisher requirements also apply.
- **Training:** never quietly use captured gameplay, scraped videos,
  licensed game art, private play sessions or proprietary code as
  training data. Training requires independent rights assessment.
  This rollout **adds no training records**.

The gate rejects explicitly pirated ROMs, unknown/unlicensed commercial
assets, leaked SDKs, extracted firmware and circumvention outputs. It
rejects internal contradictions such as "original" source that declares
third-party content, or a missing modify/distribute permission.

**Attestation is not proof.** SHA-256 validates local file identity,
not the truth of ownership; the user's stated license reference can be
incorrect. The receipt therefore *always* reports
\`all_licenses_independently_verified=false\`,
\`legal_compliance_certified=false\`,
\`distribution_authorized=false\` and
\`requires_human_review_for_release=true\`.
Production distribution cannot be authorized merely by changing JSON
flags or supplying an SDK contract reference.

### Jurisdiction-sensitive interpretation

Official legal material used to frame the policy (as of October 2026):

- **EU/EEA:** Directive 2009/24/EC Article 5(3) covers observation,
  study and testing by lawful users under specified conditions;
  Article 6 permits limited decompilation to obtain indispensable
  interoperability information under detailed conditions. Neither
  grants unrestricted rights to reproduce characters, sprites,
  music or assets.  
  https://eur-lex.europa.eu/legal-content/EN/ALL/?uri=CELEX:32009L0024
- **US:** Copyright law and 17 USC §1201 have separate copyright and
  technological-protection rules. The 2024 triennial exemption text
  allows some specific preservation/access activities, with conditions;
  it is **not a general-purpose permission to distribute decrypted
  games or bypass console security**. The 2027 rulemaking was still
  underway in October 2026.  
  https://www.copyright.gov/1201/2024/  
  https://www.copyright.gov/1201/2027/  
  https://copyright.gov/title37/201/37cfr201-40.html
- **WIPO comparative view:** game software and audiovisual expression
  may be treated differently under national laws.  
  https://www.wipo.int/en/web/copyright/activities/video_games
- **Current console development:** Nintendo requires registration and
  acceptance of developer conditions for its SDK; Xbox console
  publishing/full GDK features require partner agreements. Skeleton
  does not counterfeit these agreements or ship licensed tools.  
  https://developer.nintendo.com/the-process  
  https://learn.microsoft.com/en-us/gaming/game-publishing/onboarding/onboarding-sign-agreements

These are engineering policy references, **not legal advice**. Relevant
exceptions depend on who acquired the game, jurisdiction, purpose, how
information was obtained, the type of protected measure and other
conditions. Seek qualified legal review before high-risk or commercial
uses.

## 4. Actual workflow: create, modify, verify, play and export

From the repository root (Python with \`PYTHONPATH=.\`):

\`\`\`sh
# View the 166-target multi-era planning catalog.
python scripts/game/game_project.py --catalog

# Author original procedural content; plan four distinct eras.
python scripts/game/game_project.py \
  --demo-project ./private-game.json --seed 42 \
  --targets ibm-pc-dos,game-boy,playstation-5,windows-11 \
  --jurisdiction NO

# Recalculate source and edited maps, scene, legal attestation and
# every platform-readiness field.
python scripts/game/game_project.py \
  --verify-capsule ./private-game.json

# Emit real, playable, standalone turn-based ISO C89 source.
python scripts/game/export_portable_c89.py \
  --capsule ./private-game.json --output ./my-game.c

# A PC with a compatible C89 compiler can build that original source:
cc -std=c89 -Wall -Wextra -pedantic ./my-game.c -o my-game
./my-game
\`\`\`

The C89 game is **turn-based grid movement** and has no platformer
physics, music, internet services or platform-specific controller SDK.
It uses only \`stdio.h\`. It is not a direct binary translation of a
console title. It offers a genuine buildable game program on compatible
C implementations, without any proprietary SDK dependencies.

For visual/playable native preview of a controller-proven level:

\`\`\`sh
python -m skeleton app local-ai \
  --game-preview-check --game-project ./private-game.json --json
python -m skeleton app local-ai \
  --game-preview --game-project ./private-game.json
\`\`\`

On an installed Windows app:

\`\`\`powershell
SkeletonOffline.exe --game-preview-check --game-project .\private-game.json --json
SkeletonGame.exe --project .\private-game.json
\`\`\`

The game preview imports **only a manually selected local capsule**,
rechecks its SHA-256 content and scene/source-edit replay, then checks
controller reachability using bounded integer-tick jump and collision
physics. Unverified third-party media is not loaded.

### Authorized modifications

For \`--compose input.json --output private-modified.json\`,
provide the source tile map and an explicit rights manifest with the
source map digest, \`modify\` permission, jurisdiction, targets,
\`action="modify_authorized"\` and bounded \`edits\` of \`x\`, \`y\`,
\`tile\`. An authorized copied source must have an identified original
work and compatible license. The compiler refuses duplicate writes
to the same cell, malformed maps, broken spawn/goal, impossible grid
routes and mismatched source-rights hashes. The stored source tilemap
lets verification independently replay every edit.

The 96-frame real-controller search distinguishes
\`playable\`, \`unreachable_under_current_rules\`, and
\`inconclusive_*\` budget statuses. Grid connectivity alone does not
establish player reachability, and even successful simulation does
not establish quality on every real console/renderer.

For the first working vintage homebrew adapter, see [Original CHIP-8 ROM Export](CHIP8_HOMEBREW_EXPORT.md). It executes original bytecode and verifies a win in Skeleton's VM; it does not use proprietary console assets, nor does it establish real vintage-machine timing or official release clearance.

## 5. Release evidence and unimplemented planes

Before claiming "fully unlocked" on any hardware:
- Deliver a target-specific exporter using original/approved toolchains
  and licensed platform SDK access where applicable.
- Verify the compiler/linker/packer path, deterministic build and
  output identity; no restricted firmware/binary inclusions.
- Run genuine target emulator/hardware tests under appropriate rights.
- Test timing, sprites, memory, palette, audio, input, save, locale,
  performance, crash/rollback, accessibility and appropriate network
  safety/age-rating/store requirements.
- Verify distribution and trademark rights **for every asset** and
  obtain required publisher approvals.
- Track the exact target versions, compiler/SDK identity and sign
  a reviewed completion evidence receipt.

These gates are explicitly **not passed** for historical, current Sony,
Nintendo, Microsoft, mobile or XR target binaries simply because the
profile is present. Portable C89 **source** and local engine-neutral
scene JSON are the working development outputs; the Windows installer
also contains a small native Tk game demo.

The existing synthetic data bank of 720 reference examples has **not
grown**. Active model training remains 36 examples by default, with
optional caps of 48 or 72. Native game tools, source emission, rights
checks and gameplay search require **no training data**.
