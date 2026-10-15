# Asset Quality Tiers for Adventure Games

## Prototype
Functional placeholders. Solid colors, basic shapes. Used only for structure validation.

## Era-authentic (default target)
- Palette strictly matched to hardware (e.g., 16-bit SNES 256 colors with per-tile limits, or GBA 32k).
- Sprite counts and sizes respect scanline/hardware limits.
- Backgrounds use layering or parallax only where the target core supports it.
- Audio: chiptune or limited PCM with clear, non-clipping SFX for every interaction.
- UI never covers critical scene information.

## Polished
All era-authentic constraints plus:
- Consistent light direction and material reads.
- Idle/walk/use/examine animation sets with purposeful timing.
- Environmental audio beds that change per room.
- Readable interactive hotspots without permanent UI chrome.

## Premium
Polished plus selective modern clarity (higher internal resolution where core allows, richer sample sets) while preserving era identity. Still fully catalogued and provenance-tracked.

## Provenance rule
Every sprite sheet, background, SFX, and music stem carries source identity, license, and palette information in the asset catalog. No unlicensed or scraped material.
