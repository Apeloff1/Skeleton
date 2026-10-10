# Portable original-homebrew kernels

This is the source-data adaptation layer for the existing Skeleton game-builder
owner. It is **not** a new provider/runtime plane, a ROM downloader, a proprietary
SDK, an emulator, a trained model, or a certificate of legal clearance.

The layer accepts **authored pixel indices, colors, sound parameters, controller
frames, and grid geometry** and produces deterministic, bounded outputs.
Every public operation validates its input before allocation. Errors fail
closed; there is no implicit hardware emulation, protected-media import, or
release authorization.

## Native indexed sprite conversions

| Platform family | Tile bytes | Layout | Console-specific producer |
|---|---:|---|---|
| DMG / Game Boy Color | 16 | 2bpp, interleaved low and high row planes | `encode_gb_2bpp` |
| Famicom / NES | 16 | 2bpp, low eight rows then high eight rows | `encode_nes_2bpp` |
| Super Famicom / SNES | 32 | 4bpp, two interleaved plane banks | `encode_snes_4bpp` |
| Master System / Game Gear | 32 | 4bpp, four planes per scanline | `encode_sms_4bpp` |
| Mega Drive / Genesis | 32 | 4bpp, packed high-first pixel nibbles | `encode_genesis_4bpp` |

All codecs require **exactly eight rows of eight pixel indices** with values
within the target palette depth. All decoder inputs have exact 16- or 32-byte
lengths. Encode/decode regression vectors pin the native bit orders. Providing
other console names does not silently substitute a neighboring platform codec.

`compile_original_tile_bundle` compiles 1–256 acknowledged-original tiles,
returns the exact byte array and SHA-256, and records **false** for independent
rights clearance, native binary verification and release approval.
`verify_original_tile_roundtrip` checks that the native bytes decode to the
original indexed tiles; this is a correctness test, **not** a provenance audit.

`emit_original_tile_source` can produce a C99 static `uint8_t` array from
any supported tile bundle, RGBDS `db` statements for Game Boy data, or ca65
`.byte` statements for NES CHR data. It does not compile the source or
produce a cartridge image.

Example, using only original artwork:

```python
from skeleton.ai.game_builder import (
    compile_original_tile_bundle,
    verify_original_tile_roundtrip,
    emit_original_tile_source,
)

artwork = tuple(tuple((x + y) % 4 for x in range(8)) for y in range(8))
bundle = compile_original_tile_bundle(
    "nintendo_game_boy", (artwork,),
    acknowledged_original_source=True,
)
assert verify_original_tile_roundtrip(bundle, (artwork,))
assembly_data = emit_original_tile_source(bundle, syntax="rgbds")
print(bundle.native_sha256, len(bundle.native_bytes))
```

The acknowledgement says only that the caller has asserted the origin of
pixels. Independent asset rights, license restrictions, marks, protected
characters, trade dress, and distribution permissions remain separate,
fail-closed game-builder release gates.

## Operator command (offline, source-only)

Create a regular UTF-8 file named `authored_tiles.json`:

```json
{
  "schema": "skeleton.game_builder.original_indexed_tiles.v1",
  "project_id": "my-original-homebrew",
  "tiles": [
    [[0,0,1,1,1,1,0,0],
     [0,1,2,2,2,2,1,0],
     [1,2,3,3,3,3,2,1],
     [1,2,3,0,0,3,2,1],
     [1,2,3,0,0,3,2,1],
     [1,2,3,3,3,3,2,1],
     [0,1,2,2,2,2,1,0],
     [0,0,1,1,1,1,0,0]]
  ]
}
```

Then compile the original pixels into an **RGBDS source declaration**:

```bash
python -m skeleton.ai.game_builder.portable_tile_cli \
  --input authored_tiles.json \
  --target nintendo_game_boy \
  --syntax rgbds \
  --output original_tiles.asm \
  --acknowledge-original
```

The command emits a machine-readable SHA-256 receipt to standard output.
Alternative native source declarations are `--syntax ca65` for Famicom/NES
CHR tiles and `--syntax c99` for any supported target family. The command
never downloads firmware, compiles a ROM, runs an emulator, or clears third-
party rights.

The input source must be one regular, non-symlink file no larger than 256 KB
and contain exact schema keys, a bounded original project ID and 1–256 valid
8×8 tiles. Duplicate JSON keys, non-finite values and replacement races are
rejected. Output uses exclusive creation and never overwrites an existing
file. A user-origin acknowledgement is mandatory but **does not qualify the
project for distribution**.

## Color and presentation

`encode/decode_rgb555`, `encode/decode_rgb565` and
`encode/decode_rgb332` perform rounded component quantization.
`nearest_palette_index` uses a stable weighted RGB distance and chooses the
earliest equal-distance palette candidate deterministically. `index_image`
is capped at 64×64. `ordered_luma_dither` uses a Bayer 4×4 ordered matrix,
producing repeatable gradients with 2–16 luminance levels and no random
frame-to-frame flicker. `contrast_ratio` uses gamma-linearized sRGB.

No profile claims a Game Gear 12-bit hardware palette converter, a C64
multicolor sprite conversion, or an Atari ANTIC bitmap exporter. Those
hardware-specific formats require their own implementation and qualification.

## Sound

There are exact bounded note-divider calculations for the Game Boy pulse
channel, NTSC NES 2A03 pulse, Sega/TI SN76489 tone and AY-3-8910 tone.
Original waveform helpers synthesize limited pulse, triangle, LFSR noise and
ADSR envelopes using explicit samples and integer phase. `resample_linear`
performs deterministic signed PCM16 resampling on a bounded buffer.

These are components for author-authored audio. They do not reproduce any
copyrighted game score, sample or recording. They do not claim full sound-chip
emulation or frame-perfect device output.

## Input, frame-rate adaptation, and geometry

`frame_schedule` produces a rational per-source-frame number of destination
frames (including e.g. 50↔60 Hz) without accumulating fractional drift.
`source_frame_at` maps display frames to original simulation frames. Edges,
deadzone normalization, Schmitt hysteresis, eight-way pad mapping, debounce,
repeat and injective button remapping all use explicit bounded state.

Grid algorithms provide deterministic cardinal neighbors, Bresenham rays,
line-of-sight occlusion, connected flood-fill, BFS distance fields and A*.
Half-open AABB collision and rational swept time-of-impact avoid a platform
float divergence. Sprite shelf packing and camera clamp are bounded.

These are **deterministic reference kernels**: they do not yet replace the
application's canonical gameplay simulation. Integration should bind actual
game build targets through the existing owner, retain world and replay
digests, and compare output against platform-specific runtime behavior.

## Operational and acceptance rules

- This source layer has no access to third-party network content or model
  credentials and should not be routed through the provider execution plane.
- Keep the codec vocabulary explicit by hardware family. Unknown platform
  formats fail closed; no automatic fallback to an incompatible format.
- Complete the existing game-builder rights and release assurance process
  before using artifacts in a distributed commercial/homebrew release.
- Run the targeted regression tests under `skeleton/testing/`:
  `test_portable_bitplanes.py`, `test_portable_palette.py`,
  `test_portable_audio.py`, `test_portable_input_timing.py`,
  `test_portable_geometry.py`, `test_portable_kernel_integration.py`.
- Run existing `test_game_builder_platform_porting.py` and all mandatory
  architecture and application gates. An exported C/ASM source array proves
  neither successful assembly nor playability on hardware.
- Include byte-level toolchain compile receipts, real-hardware/emulator
  validation, independent rights review, gameplay parity, and artifact
  provenance before promoting a target's native availability.

Known limitations: no built binaries, no proprietary console firmware, no
non-original asset import, no certified device performance, no licensed-game
migration, no current independent hardware benchmarking, and no independently
approved release status.
