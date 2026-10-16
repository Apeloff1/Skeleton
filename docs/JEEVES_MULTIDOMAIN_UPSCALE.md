# Jeeves multidomain upscale implementation

Status: executable, bounded original-media transforms plus evidence-only scrutiny.
This is not universal native console rendering, trained checkpoint improvement
or verified finished-game quality. Source ownership remains canonical GameForge
and Jeeves developer interfaces, not another model/provider/engine runtime.

## Original image and animation

Static PNGs can become actual vertically stacked animated PNG frames with
wind, breathe, bob, shimmer or water motion. Existing vertical frame strips
can receive small interior edge-detail and shadow transforms. The sprite
conversion uses the canonical console PNG decoder/encoder and works on
bounded resolutions; it does not invent 3D geometry or professional rigging.
Input art is never overwritten. Each successful output is queued for review.

    python -m skeleton dev game jeeves upscale-animation --project . --target snes --source assets/hero.png --output assets/hero-animated.png --pattern bob --frames 8
    python -m skeleton dev game jeeves upscale-foliage --project . --target snes --source assets/tree.png --output assets/tree-wind.png --pattern wind --frames 12
    python -m skeleton dev game jeeves upscale-animation --project . --target nes --source assets/animated-strip.png --output assets/detail-strip.png --frame-height 16 --frames 16
    python -m skeleton dev game jeeves upscale-shadow --project . --target snes --source assets/prop.png --output assets/prop-shadow.png --distance 2

## World, scenery, foliage, clutter and stage

A typed stage source lives under design/, with schema
skeleton.jeeves.stage_source.v1 and EXACT fields: schema, grid, depth, biome,
layers, camera. Grid is a rectangular list of strings: # is solid, . is
walkable, S is one spawn, G is one goal. The route from S to G must be
traversable before any upgrade. Depth is 2d, 2_5d, 2_9d or 3d.
Biomes: forest, desert, city, mountain, underwater, industrial and space.
Layers contain original project PNG paths and depth numbers 0..1.
Camera contains yaw and pitch degrees.

Biome-specified dressing is procedurally added only to noncolliding walkable
cells off the protected route. Original grid, collision, source and
parallax-asset fingerprints remain unchanged. This produces real JSON
stage enrichment, but NOT a rendered, interactive level.

    python -m skeleton dev game jeeves upscale-world --project . --target snes --source design/forest.json --output design/forest-upscaled.json --richness 5
    python -m skeleton dev game jeeves upscale-environment --project . --target snes --source design/forest.json --output design/forest-weather.json --richness 4
    python -m skeleton dev game jeeves upscale-clutter --project . --target snes --source design/forest.json --output design/forest-clutter.json --richness 4
    python -m skeleton dev game jeeves upscale-stage --project . --target snes --source design/forest.json --output design/forest-foliage.json --focus foliage --richness 5

## Parallax and camera

Parallax input schema skeleton.jeeves.parallax.v1:
{"schema":"skeleton.jeeves.parallax.v1","width":320,"height":180,
"layers":[{"path":"assets/sky.png","depth":1.0},
{"path":"assets/trees.png","depth":0.0}]}

Each source plane is a real same-size PNG, composite offsets derive from
authored depth and the operator's camera pan, actual pixels are blended
and resulting PNG bytes are hashed. It does not execute a game camera.

    python -m skeleton dev game jeeves upscale-parallax --project . --target snes --source design/parallax.json --output assets/parallax-view.png --pan 8
    python -m skeleton dev game jeeves camera-plan --project . --depth 2_9d --yaw 45 --pitch 15 --parallax-planes 7

Flat 2D allows no yaw/pitch; 2.5D up to 45/20 degrees, 2.9D to 90/45,
and 3D to 180/89. Numeric rotation matrices and parallax weights are
real outputs, while occlusion and billboard rendering remain future checks.

## Music and ambience

Input must be original signed 16-bit PCM mono/stereo WAV. Output is a real
bounded PCM WAV preserving original tempo, channel count and frame count.
Remaster uses bounded gain/headroom. Ambience combines an explicitly
provided source stem with the original music and source-derived echo;
cinematic mode uses an additional source-derived echo. This is signal
processing, NOT generative composition or trained audio synthesis.

    python -m skeleton dev game jeeves upscale-music --project . --target snes --source assets/theme.wav --output assets/theme-hd.wav --mode remaster
    python -m skeleton dev game jeeves upscale-music --project . --target snes --source assets/theme.wav --output assets/theme-rain.wav --mode ambience --ambience assets/rain.wav

## Scrutiny and vividness

The asset inventory covers all discoverable workspace files under assets/
and design/, hashing content and classifying probable domains. Response
pagination is finite; project history and total passes have no lifetime
cap. Generic upscale-review reparses all assets. Dedicated vividness-review
also checks every stage decoration, source identity, linked parallax image,
unchanged grid and protected traversal route, reporting density and
diversity. Neither test certifies subjective artistic quality.

    python -m skeleton dev game jeeves asset-inventory --project . --page 0 --page-size 256
    python -m skeleton dev game jeeves upscale-review --project . --passes 8
    python -m skeleton dev game jeeves vividness-review --project . --source design/forest-upscaled.json --passes 8

## Upscale-priority training review

Every committed original upscale result enters the existing local Jeeves
production workbench queue, with source and output SHA-256 and target
evidence. P0 represents known failed output; P1 represents unreviewed
output; P2 represents separately reviewed output. Each candidate remains
subject to rights clearance, critical inspection, held-out training
evaluation and checkpoint promotion governance. Candidate creation alone
NEVER modifies model weights.

    python -m skeleton dev game jeeves queue-upscaled-training --project . --page 0 --page-size 64

## Production limitations and acceptance

All files are created without overwriting existing approved work. Source
hashes, safe relative paths, format bounds and strict schemas are used
to refuse unsafe/unsound inputs. Hardware support must come from the
canonical console and engine registry. This work does not certify every
console's native renderer, shaders, final-game functionality, physics,
audio spatialization, IP rights or universal GPU performance.

A standalone AAA-scale game studio requires executable scene/render
integration, real skeletal animation, high-end materials and lighting,
end-to-end gameplay and release validation, and trained weights with
observed model gains. These remain qualification gaps, not reasons to
decrease the fixed bar of matching or surpassing the era's best-reviewed
commercial games.

Focused tests:
python -m pytest skeleton/testing/test_jeeves_game_multidomain_upscale.py -q

Additional contract checks:
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
