# Game Frontier GF-I — Art-Direction Visual Acceptance Contract (2026-10-24)

Owner: Starlit (Art Director). Package: **GF-I** (rendering/audio/recorder bindings; code owned by NSOG + Bork).
Scope: the *art-direction* side of GF-I — what a renderer reference screenshot must satisfy before a
rendering item can be called visually accepted. This contract does **not** write renderer bindings.

Checker: `skeleton/game/art_acceptance.py` · Tests: `tests/test_game_frontier_art_acceptance.py`
Tokens: `design/art/visual_identity_tokens.json` (source `design_guidelines.json`, glass/luxe dark utility).

## Inputs
A reference frame (row-major RGB tuples, 0–255) plus a binary subject mask (True = subject: player,
cloud body, shadow caster, rock, etc.). Renderer lanes capture and decode; this module only judges pixels.

## Criteria

| # | Criterion | Rule (default threshold) | Why (art bar) |
|---|-----------|--------------------------|---------------|
| C1 | Silhouette read at thumbnail | subject mask fill in [0.02, 0.85] of frame | A form you can read at thumbnail; reject empty gray boxes and frame-swallowing blobs |
| C2 | Value/contrast bands | ≥ 2 of shadow (<0.25) / mid (0.25–0.70) / highlight (≥0.70) bands each hold ≥ 1% of pixels | Flat frames have no light; value structure precedes colour |
| C3 | Subject vs background contrast | relative-luminance ratio ≥ 3.0 | Readable at gameplay speed; subject separates from ground |
| C4 | Palette conformance | ≥ 90% of pixels within RGB distance 48 of a token colour | One locked look, no asset spam / off-identity hues |
| C5 | Lighting key/fill/rim | Token rig ratio key 1.15 : fill 0.45 : rim 0.85 (≈ 2.6 : 1 : 1.9). Reviewed on the bound scene; pixel proxy is C2+C3 | Key defines form, fill lifts shadow without flattening, rim separates silhouette |
| C6 | Readable at gameplay speed | C1+C3 must hold on every sampled frame of a motion capture, not just a hero still | Per-frame coherence, not a single beauty shot |

Thresholds are Art Director decisions; change them only with an art-review note in the PR.

## Mapping to TODO.md items

| TODO item | Contribution | Status claimed |
|-----------|--------------|----------------|
| GF-P0-13 (cloud geometry → real raster renderer) | C1–C4 are the visual acceptance for the cloud reference screenshot (cloud body mask vs sky) | Acceptance criteria only; binding not closed |
| GF-P0-35 (projected polygons / ray shadows → visible graphics, native reference screenshots) | C2/C3 define "visible" shadow (shadow band present, caster/receiver contrast); C4 keeps shadow tint on-palette | Acceptance criteria only |
| GF-P0-57 (live Godot weather/water/leaf-shadow/rock/character sim, per-frame screenshot proof) | C6 per-frame rule + C1–C4 per sampled frame | Acceptance criteria only; live sim not closed |
| GF-P0-60 (audio buses) | none — audio | **NOT claimed** |
| GF-P0-61 (GPU ray/path lighting profiling on low/high hardware) | none — needs real hardware | **NOT closed; hardware step** |
| GF-P0-165 (native recorder / installer) | none | **NOT claimed** |

No TODO.md checkboxes are ticked by this change (GF-N owns ticking).

## How renderer lanes use it
```python
from skeleton.game.art_acceptance import evaluate_frame
report = evaluate_frame(frame_rgb_rows, subject_mask_rows)
assert report.passed, report.failures
```
Run: `python3 -m pytest -q tests/test_game_frontier_art_acceptance.py`
