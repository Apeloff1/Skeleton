# Commercial Asset Starter

Deterministic PNG atlas + Godot SpriteFrames .tres emitter.

## Usage

```python
from skeleton.forge.pipelines.commercial_asset_starter import emit_atlas, emit_godot_tres
from pathlib import Path

frames = [bytes([255, 0, 0, 255] * 16)]  # 4x4 example
path, coverage = emit_atlas(frames, 4, 4, Path("./out"), "source-receipt-sha")
tres = emit_godot_tres(path, 1, 4, 4, Path("./out"))
```

## Guarantees

- Content-addressed PNG (SHA-256 of raw before encode).
- Valid PNG (IHDR 8-bit RGBA, filtered scanlines, zlib IDAT, CRC32, IEND).
- .tres with AtlasTexture regions, duration, loop, speed.
- Fail-closed on geometry, frame count, path escape (via hardener if wired).
- Provenance receipts on every emit. stored_prose=0.

## Next

Wire into studio_sprite_* and compressed_vault sites. Add mesh/audio planes.
