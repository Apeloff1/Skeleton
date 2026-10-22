# Commercial Asset Starter (injected into #4200)

Deterministic PNG atlas + Godot SpriteFrames .tres emitter.

## Usage

```python
from skeleton.forge.pipelines.commercial_asset_starter import emit_atlas, emit_godot_tres
from pathlib import Path

frames = [bytes([255, 0, 0, 255] * 16)]
path, coverage = emit_atlas(frames, 4, 4, Path("./out"), "source-receipt")
tres = emit_godot_tres(path, 1, 4, 4, Path("./out"))
```

Guarantees: content-addressed, valid PNG, .tres with regions, receipts, fail-closed.
stored_prose=0.
