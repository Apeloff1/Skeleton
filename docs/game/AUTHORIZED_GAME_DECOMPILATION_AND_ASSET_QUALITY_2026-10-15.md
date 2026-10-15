# Authorized Game Decompilation, Asset Intelligence and Quality Training

**2026-10-15 — source implementation; verification not yet run.**

## Goals, reality and restrictions

The pipeline `skeleton.jeeves.game_decompilation` supplies an **actual**, byte-backed, deterministic reverse-engineering toolchain to help Jeeves study game technologies and improve **original** games. It combines ROM/header parsing already present in Skeleton, finite static disassembly, exact NES CHR tile decoding, safe game-project resource measurements, per-core native RGB observation and reviewable design insights. The new shadow regressor can **actually fit a small local numeric model** to independently human-labeled measures. It does not fine-tune the production LLM or automatically transfer pixels/sound/source into weights.

A compiled game's complete authored source, asset identities, shader logic, level graph, scripts and music usually **cannot** be reliably reconstructed simply by reverse-engineering its ROM. This pass disassembles supported code subsets and explicitly reports unsupported banked/dynamic/compressed formats. Do not call these results a full game decompilation or an independent assessment of game quality.

**Copyright and rights:** only analyze games you own or are licensed/authorized to reverse engineer under applicable law. A game being abandoned, no longer sold or available online is not itself a grant to copy assets or train on them. Existing model policy calls require source-specific backend current authorization. The supplied local CLI makes the operator explicitly attest scoped rights and preserves the digest of external evidence; it **does not** cryptographically verify a license or independently establish legal rights. Source digests and license evidence must be checked against actual permissions before using material. Do not redistribute extracted copyrighted assets or clone expressive content.

## Actual implemented capability matrix

| Format | Structural format/layout | Executable reverse-engineering | Graphics / sound |
|---|---|---|---|
| NES iNES / NES 2 | Existing header and mapper checks | Control-flow-aware **mapper-0 iNES 6502** starting at NMI/reset/IRQ vectors, bounded 4096 instructions. Unsupported banked mappers explicitly rejected. | Full native-2bpp CHR ROM decoding, tile hashes, duplication and edge measurements, 16-column PNG preview using an explicitly synthetic grayscale palette. CHR RAM not recovered. |
| Game Boy / Color | Existing authentic Nintendo-logo, mapper/bank/checksum layout | SM83 fixed-bank entry-point flow and instruction **lengths**, verified branch targets. Generic mnemonic labels where full opcode operands are unimplemented. No switched banks. | No guessed sprite locations; operator may authorize exact tile offsets in NES/GB/SNES/Genesis/GBA/SMS native encodings. |
| GBA | Existing structural game-code/fixed-header checksum | ARM7TDMI **ARM-state-only** reachable entry/branch families with bounded words. No Thumb, BIOS, instruction operand reconstruction or real machine execution. | Explicit tile candidates only; no inference of decompressed VRAM or palette without provenance. |
| SNES, Genesis, N64, Lynx, Atari 7800, SMS/GG, NDS, PBP | Existing cartridge/package layout parsing where supported | **Not yet a full verified decompiler.** Returns an honest unsupported-code report unless architecture-specific decoder exists. | Explicit tile candidate layouts; unknown regions not classified as real sprites. |
| Windows PE / Linux ELF | Exact endian-aware, bounded section inventories and SHA-256 | Section flags, raw ranges and hashes only; not x86/x64 recompilable decompilation. | No automatic proprietary assets exported. |
| ISO9660 | Primary-volume descriptor and bounded root directory inventory, complete supplied image only | Does not execute contained PS1/PS2/etc. code | No encrypted/compressed disc decoding; full-size multi-GiB ISO streaming remains to be implemented. |
| Game-project ZIP | Up to 96 safely checked members, file size/inflation/CRC/path guards, no disk extraction | Scripts recognized as **opaque**, never executed | Actual bounded PNG decoding and WAV PCM feature measurements with no raw media returned. |
| **Any installed libretro core** | User/host captures actual RGB24 frames | No game RAM scraping, instruction execution or asset classification | Up to 16 checksum-verified frames, each spatially tiled into up to 16×16 full-region hashes; sampled palette/brightness, cross-frame pixel changes and native-run-counter consistency. Requires authorized source + approved core binary digest. |

## Authorization contract

Each call to `decompile_authorized_game(data, filename, grant=…, authorize=…)` requires:
1. Exact SHA-256 of original input, SHA-256 of external rights evidence, accountable principal and rights acknowledgement.
2. Explicit independent per-operation authorization **callback** for structure, code reverse engineering, asset decode, synthetic preview export and derivative design feature review. Source rights are not inferred from a filename, game age, genre, emulator or ROM accessibility.
3. Independent **human-labeled shadow training** scope for `prepare_reviewed_training_candidate`. Review label record separately binds numeric measurements, source SHA, human reviewer and evidence digest.
4. No automatic network access, game-core execution, arbitrary command execution, copyright bypass, production model training or asset upload.

Maximum in-memory game source is **32 MiB**, deterministic disassembly at most **4096 instructions**, at most **4** operator-declared extra tile ranges, at most **256** tile-region preview atlas tiles per group? Actual atlas limit is 1024 native 8×8 tiles, bank limited to 512 NES tiles. Source report bound **8 MiB**. Per-frame RGB cap is **4 MiB**, source runtime sequence max **16** frames.

**Data custody:** report JSON contains source provenance, hashes, bounded opcode words, target addresses, asset metrics and design questions; not raw ROM, code file, PCM, game bytes or uncompressed RGB. Separate PNG previews are created **only** when preview scope is allowed, and those are reconstructive copies of source tiles that may themselves be copyrighted. A hash chain does not independently attest authentic console execution.

## Operator CLI

From the repository root, on the local machine with authorized source:

```bash
PYTHONPATH=. python scripts/decompile_game_assets.py ./homebrew.nes \
  --output ./evidence/homebrew_001 \
  --principal original_author \
  --rights-digest <64-lowercase-hex-sha256-of-evidence> \
  --attest-rights \
  --export-previews
```

Run without `--export-previews` for a metadata-only evidence export. Use `--candidate-tile 0x200:256:gb_2bpp` **only** when the offset/codec is independently documented; output is labeled as a *candidate*, not a proven graphics region. No output directory will be overwritten. Source is opened without symlink traversal, and the output is a new private directory.

For reviewed quality data, add `--human-score 76 --reviewer original_reviewer --label-evidence-digest <sha>` and ensure explicit shadow rights. This adds a bounded human-label candidate to the local evidence, **not** a trained model.

To **actually train** a local shadow numeric regressor from **8–128 distinct, human-labeled reports**:

```bash
PYTHONPATH=. python scripts/train_game_asset_quality_shadow.py \
  --authorize-shadow-training --output ./shadow_quality_checkpoint.json \
  ./evidence/game_*/report.json
```

The fit uses fixed-feature logarithmic normalization, deterministic source-disjoint train/holdout split, bounded batch-gradient MSE updates with L2 weight shrinkage, per-source evidence digests and a checkpoint checksum. A better holdout MSE is **not sufficient for automatic promotion**; reviewers must also evaluate score bias, representativeness, originality, robustness, legal source rights, adversarial game design/animation and independent playtest outcomes. Even a failed holdout guard records actual local model learning but is not promotion admissible. The production Jeeves/Dragon/LLM weights remain unchanged.

## Quality dimensions and future work

Quality reports produce observed **tile reuse, palette-index distribution, edge density, branching structure, native frame-motion measurements, and source-evidence gaps**. Their design questions encourage novel asset silhouettes, accessible palette contrast, scene state-machine clarity and provenance review. They do **not** reproduce character likenesses, dialog, maps, levels, plots, names, audio tracks or distinctive expressive game artwork for distribution.

Future capability gaps: streaming multi-GiB discs/CHD, authenticated BIOS/firmware inspection, bank-aware 65816/68000/MIPS disassembly, GBA Thumb support, symbol-rich executable decompilation, texture compression codecs, dynamic VRAM tile extraction with PPU metadata, audio sequence reconstruction, provenance-verified game entity/asset graph, on-device performance limits, reviewed/legal training corpus acquisition, adversarial train/eval splits, and validated long-horizon production game design improvement.

## Qualification evidence

`tests/test_game_decompilation.py` includes **generated original synthetic cartridges/resources only**. It asserts real NROM branch decoding, GB and GBA reachability, CHR image bytes, PNG/PCM ZIP parsing, PE inventories, traversal/bad-rights rejection, native-frame non-advancement and tamper checks, human score provenance, shadow gradient-update checkpoints, holdout separation, and no production model promotion.

`.github/workflows/focused-game-decompilation.yml` is **manually triggered only** to avoid further CI congestion. Both test suite execution and commercial-core/ROM qualification **remain unverified at commit time**. Do not describe committed tests as passed without a completed run.
