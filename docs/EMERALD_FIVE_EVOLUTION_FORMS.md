# Emerald evolution forms — poster-guided first 3D pass

Visual reference: **Emerald Dragon Evolution Sanctuary.png**, the retained approved six-stage sanctuary concept. The same green-jade hide, ivory chest, blue-cyan eyes, gold hardware, increasing wing span, cheek frills and horns are carried from the small dragon to the larger one. The reference is not used as a flat image texture. The generated models are distinct geometric candidates, not a claim of visual equivalence to the poster.

| Stage | Levels | Distinct anatomy and equipment |
| --- | --- | --- |
| Hatchling | 1–10 | Rounded muzzle, oversized eyes, short horns, small webbed wings, broken ivory shell and cap |
| Scout | 11–20 | Longer neck and tail, small harness, medallion, explorer leather pouch |
| Scholar | 21–30 | Larger throat and wings, additional cheek frills, scrolls and crystal |
| Pathfinder | 31–40 | Broader wings, taller neck, gilded wing detail, mantle and expedition gear |
| Archivist | 41–50 | More substantial torso, developed wings and horns, scroll stack, mantle, archive crystal |
| Hoarder | 51–60 | Existing separately pinned original; unchanged |

The five GLB files are committed as actual binaries, with individual SHA-256, Git blob identity and geometry/animation counts in the manifest. The deterministic JavaScript generator can produce each form at density 1–3; the committed files use density 2. This is an initial procedural, articulated-node model implementation, **not** the existing Hoarder model's weighted anatomical skin, handcrafted textures, 380-clip motion repertoire or physical rendering qualification. The poster's appearance remains the artistic target.

Generate a new candidate set into a fresh directory: `node scripts/emerald-evolution/build.cjs /path/to/new-output 2`. Verify committed candidates: `node scripts/emerald-evolution/verify.cjs`.

Independent generation audit checked all actual candidate vertex positions, unit normals, index bounds, nonzero triangle area, animation time ordering and normalized quaternions. The receipt is in the asset directory. Final-head CI separately checks the committed bytes. These assets are not yet wired into the production companion; do not automatically select them in place of the original Hoarder or infer artist acceptance. Remaining: continuous anatomical transition morphs, shared weighted skinning/retargeting, high-fidelity hand-authored textures and scale relief, rendered comparison with poster, physical motion, device/Unreal/RTX and runtime integration. No merge or release.
