# Iconography

Owner: UI Art Lead (Unohashi) · Scope: visual craft only.
Companion to [`docs/UI_ART_KIT.md`](./UI_ART_KIT.md) §4. Docs-only; no binary assets in this PR.

## 1. Grid and keylines

- Master artboard **24 × 24**, 2 px padding → **20 × 20** live area.
- Keyline shapes inside the live area: circle Ø20, square 18 × 18, portrait 16 × 20, landscape 20 × 16.
- Snap to whole pixels at 24; square corner radius 2 px (scales with `radii.xs`).
- Optical centre: shift triangles / play glyphs ~0.5 px right.

## 2. Stroke

- **2 px** stroke at 24, round caps and round joins. Filled variant only for selected/active.
- Stroke by size (hand-tuned, not auto-scaled):

| Size | Stroke |
|------|--------|
| 16 | 1.5 px |
| 20 | 1.75 px |
| 24 | 2 px |
| 32 | 2.5 px |
| 48 | 3 px |

- Single colour via `currentColor`. No gradients inside glyphs (gradients belong on the container, e.g. `gradients.brand`).

## 3. Sizes and touch

| Size | Use | Padding | Min touch wrapper |
|------|-----|---------|-------------------|
| 16 | inline with caption/body, table status | 1 px | n/a (not tappable alone) |
| 20 | list rows, buttons with body label | 1.5 px | 44 |
| 24 | default; tab bar, toolbar, HUD contextual | 2 px | 44 |
| 32 | HUD critical, empty states | 2.5 px | 48 |
| 48 | feature tiles, onboarding, results | 4 px | — |

Icons on fills meet 3:1 against the fill (WCAG 1.4.11). Use the per-skin `onPrimary` table in `UI_ART_KIT.md` §2.6.

## 4. Naming

`ic_<domain>_<object>[_<modifier>]_<size>[_filled]`, lower snake case.

Examples: `ic_hud_health_24`, `ic_hud_threat_32_filled`, `ic_forge_build_20`, `ic_status_ok_16` (maps to `TONE_GLYPH.ok`).

Domains: `nav`, `hud`, `forge`, `status`, `action`, `social`, `store`.

## 5. Export formats

- **Source:** SVG, 24-grid master, outlined strokes in an `_src` layer kept editable.
- **App:** optimised SVG (SVGO, no IDs/metadata, `viewBox="0 0 24 24"`, `fill="none" stroke="currentColor"`), rendered through `react-native-svg` (already a dependency).
- **Raster fallbacks** (notifications, store, web OG): PNG @1x/2x/3x, matching the existing `react-logo.png / @2x / @3x` convention.

`@expo/vector-icons` remains fine for generic glyphs; custom brand and HUD-critical marks ship as SVG.

## 6. App icon inventory (`frontend/assets/images`)

Referenced from `frontend/app.json`. Findings from the #2463 audit:

| File | Size | Blob | Referenced as | Finding |
|------|------|------|---------------|---------|
| `icon.png` | 512 × 512 | `e1168f4e10` | `expo.icon` | Must be **1024 × 1024**, no transparency (iOS). Re-export from one master. |
| `adaptive-icon.png` | 512 × 512 | same as icon | `android.adaptiveIcon.foregroundImage`, bg `#000000` | Must be a **separate** 1024 × 1024 foreground with the mark in the central 66% safe zone. Background should be kit `bg #070B16`, not pure black. |
| `splash-icon.png` | 512 × 512 | same | not in `app.json` splash | Keep as splash mark; centre on `bg #070B16`. |
| `favicon.png` | 512 × **513** | `b402baf317` | `web.favicon` | Off-by-one height; re-export square (48 / 192 / 512). |
| `app-image.png` / `splash-image.png` | 336 × 729 | identical | — | Duplicate; keep one. |
| `react-logo*.png`, `partial-react-logo.png` | small | — | Expo template | Not brand assets; removal needs owner OK (not done here). |

## 7. Replacement brief (for art / eng when binaries land)

1. One master SVG under `frontend/assets/brand/` (mark only, transparent, 1024 artboard).
2. Export matrix:
   - `icon.png` — 1024×1024, opaque, kit background or solid brand field.
   - `adaptive-icon.png` — 1024×1024 foreground; safe zone 66%; `android.adaptiveIcon.backgroundColor` = `#070B16`.
   - `splash-icon.png` — centred mark on `#070B16`.
   - `favicon.png` — square 512² (and 48 / 192 for PWA).
3. No Expo React logos in ship paths.
4. Contrast: mark vs background ≥ 3:1 for UI glyphs; store icon readable at 32 px.
5. UI Art Lead reviews exports against this brief before merge of any asset PR.

## 8. Linkage

- Kit audit and migration: [`UI_ART_KIT.md`](./UI_ART_KIT.md).
- HUD semantic colours/glyphs: [`UI_ART_HUD_SEMANTIC.md`](./UI_ART_HUD_SEMANTIC.md).
- Token consolidation (engineering): [#2464](https://github.com/Apeloff1/Skeleton/issues/2464).
