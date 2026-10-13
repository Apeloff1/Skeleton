# Visual identity — Skeleton / GameForge

Art Director bar: **silhouette, read, consistency** over asset spam.
Rockstar/Blizzard polish. Ship-ready is not feel-ready.

## Personality

Fusion of Glass/Luxe cinematic command surfaces and dark-first utility
(from `design_guidelines.json`): off-black `#0A0A0A`, brand violet
`#8B5CF6`, Rajdhani metrics, Satoshi body. No pure black `#000000`.

## Material language (forge → Godot)

Every materialised scene must carry:

1. **Silhouette** — readable form at thumbnail: Player/Ground/Camera
   nodes with distinct masses; no floating empty `Node2D`.
2. **Material** — `StandardMaterial3D` (or 2D color/modulate) bound to
   tokens: surface charcoal, brand emissive rim, success/warning accents.
3. **Lighting** — key DirectionalLight (cool fill) + rim OmniLight
   (brand violet) so form reads; not flat gray boxes.
4. **Consistency** — one grammar across platformer / topdown / empty
   templates. Critique fails if lighting or material metadata is missing.

## Critique checklist

- `silhouette_ok` — scene declares Player + Ground (or equivalent)
  with non-zero extent / collision.
- `readable` — lighting nodes present (Directional or Omni).
- `consistent` — material albedo/emissive drawn from token set;
  no ad-hoc hex outside the palette.

Fidelity floats in `forge_quality` are **not** an art language.
A number that greenlights gray boxes is rejected.

## Binding

Tokens live in `design/art/visual_identity_tokens.json`.
Runtime: `backend/core/art_identity.py`.
Godot emit: `backend/gameforge/godot_engine/scenes.py` calls
`apply_art_pass` before writing `.tscn` text.
