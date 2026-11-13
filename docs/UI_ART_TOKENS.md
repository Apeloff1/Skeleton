# Foundation design tokens — consumer guide

Owner: UI Art Lead (Unohashi) · Audience: Frontend (app shell and screens).
Package: `frontend/theme/foundation/` · Single edit point: `frontend/theme/tokens.ts` · Specs: [`UI_ART_KIT.md`](./UI_ART_KIT.md) (#2463),
[`UI_ART_HUD_SEMANTIC.md`](./UI_ART_HUD_SEMANTIC.md) and [`UI_ART_ICONOGRAPHY.md`](./UI_ART_ICONOGRAPHY.md) (#3609).
Migration tracking: [#2464](https://github.com/Apeloff1/Skeleton/issues/2464).

> **`frontend/theme/tokens.ts` is the single edit point for every token value** (Technical Director
> ruling). Colours, type, spacing, radius, elevation, motion, HUD rules, iconography, status glyphs
> and all 30 skin palettes live there. Everything else reads from it.

| Source | Role now | Edit values here? |
|--------|----------|-------------------|
| `frontend/theme/tokens.ts` | canonical values (+ `canonicalColors`, `textUsage`, `status`, `hud`, `iconography`, `skinPalettes`, `DEFAULT_SKIN_ID` as named exports; `colors`, `colorModes`, `palette`, `spacing`, `radii`, `typography`, `elevation`, `motion`, `gradients`, `hitSlop`, `breathing` on the default `theme` object only) | **yes — only here** |
| `frontend/theme/foundation/*` | typed read-only API (`getTheme`, `foundation`) | no |
| `frontend/theme/skins.ts` | compatibility: derives `SKINS` / `SKIN_BY_ID` from `skinPalettes` (same exports and shapes) | no |
| `frontend/constants/themes.ts` + `hooks/useTheme.ts` | compatibility: legacy role names over tokens | no |
| `frontend/src/theme/deluxe.ts` | compatibility: `C/S/R/T/card/cardActive/glow` over tokens | no |
| `frontend/src/skeletonForge/components/theme.ts` | compatibility: `C/TONE_COLOR/TONE_GLYPH/TOUCH/RADIUS` over tokens | no |

A test (`test:foundation-tokens`) fails if any of those files except tokens.ts contains a hex literal.

**Import rule (lint:ci).** A binding lives either on the default `theme` object *or* as a named export,
never both — duplicates trip `import/no-named-as-default-member` and fail `yarn lint:ci --max-warnings=0`.
Read `theme.colors` (live, skin-mutated dark palette), `theme.colorModes.dark|light`, `theme.spacing`,
`theme.radii`, `theme.typography`, `theme.elevation`, `theme.motion`, `theme.gradients`, `theme.hitSlop`,
`theme.breathing`, `theme.palette` from the default import. Import `canonicalColors`, `textUsage`,
`status`, `hud`, `iconography`, `skinPalettes`, `DEFAULT_SKIN_ID` by name. When adding a token, put it
in exactly one of those two places (`test:foundation-tokens` enforces this).
No file was removed: every legacy source still has importers, so each stays as a thin adapter with
its original export names and object shapes. `skinStore` still mutates `theme.colors` exactly as before.

## 1. Import

```ts
import { getTheme, foundation } from '@/theme/foundation';
// or individual pieces
import { iconName, STATUS_GLYPH, hudMotion, contrastRatio } from '@/theme/foundation';
```

| Module | What it gives you | Source |
|--------|-------------------|--------|
| `color.ts` | `ramps` (ink, brand, blue, cyan, pink, status ramps), `roles.dark` / `roles.light`, `TRUE_CYAN` `#22D3EE`, `LEGACY_CYAN_BLUE` (the ramp once misnamed cyan), `STATUS_GLYPH`, `statusRoles()`, `TEXT_USAGE` | tokens.ts · KIT §2.1, §2.5, §3.4 · HUD_SEMANTIC §1–2 |
| `typography.ts` | `typeScale` (16 roles incl. HUD `metric` / `label`), `fontFamily`, `hudType` tiers, `LARGE_TEXT` | tokens.ts · KIT §2.2, §3.2–3.3 |
| `spacing.ts` | `spacing` (4-pt), `breathing`, `hitSlop`, `touch`, `hudSafeZone` | tokens.ts · KIT §2.3, §3.1 |
| `radius.ts` | `radius`, `legacyRadius` (deluxe / forge mapping), `ICON_SQUARE_RADIUS` | tokens.ts · KIT §2.3 · ICONOGRAPHY §1 |
| `elevation.ts` | `shadows`, `surfaces(mode, colors)` ladder (flat → modal), `GLOW_MAX_PER_SCREEN` | tokens.ts · KIT §2.4 |
| `motion.ts` | `duration`, `easing`, `hudMotion` (state in/out, press, shimmer, ambient fade, flash cap) | tokens.ts · KIT §3.2–3.5 |
| `icons.ts` | `ICON_GRID`, `ICON_SIZES`, `ICON_SPEC` (stroke/padding/touch per size), `ICON_STROKE_STYLE`, `iconName()`, `isIconName()` | ICONOGRAPHY §1–5 |
| `skins.ts` | `SKIN_IDS`, `ON_PRIMARY_BY_SKIN`, `skinOverrides(id)`, `skinPrimaryText()` | skins.ts · KIT §2.6 |
| `contrast.ts` | `relativeLuminance`, `contrastRatio`, `WCAG` thresholds | KIT §2.5 formula |
| `index.ts` | `foundation` (frozen static object), `getTheme()`, `ResolvedTheme` type, everything above | — |

## 2. App shell: `getTheme(mode, skinId?, options?)`

```ts
import { StatusBar } from 'expo-status-bar';
import { getActiveSkinId, useActiveSkin } from '@/src/utils/skinStore';
import { getTheme } from '@/theme/foundation';

export function AppShell({ isDark, children }: { isDark: boolean; children: React.ReactNode }) {
  useActiveSkin(); // re-render on skin change
  const t = getTheme(isDark ? 'dark' : 'light', getActiveSkinId());
  return (
    <View style={{ flex: 1, backgroundColor: t.colors.bg }}>
      <StatusBar style={t.statusBarStyle} />
      {children}
    </View>
  );
}
```

`getTheme` returns a `ResolvedTheme` with **every** key filled in (the unit test checks this for
both modes × canonical + 30 skins): `mode`, `isDark`, `skinId`, `statusBarStyle`, `colors`, `status`,
`surfaces`, `gradients`, `type`, `fontFamily`, `hudType`, `spacing`, `breathing`, `touch`, `hitSlop`,
`hudSafeZone`, `radius`, `shadows`, `motion`, `icons`.

- Results are **frozen and memoised** per `(mode, skinId, colorBlind)`, so they are safe in
  `useMemo` deps / context values and never change under you.
- `getTheme` never writes to tokens.ts. `skinStore` still mutates `theme.colors` for legacy
  consumers; foundation reads tokens.ts `canonicalColors` (frozen at module evaluation, before any
  skin) so a skin cannot leak into `getTheme('dark')`.
- `skinId` omitted → the **canonical kit** (brand violet `#8B5CF6`). To match what legacy screens
  show, pass `getActiveSkinId()` (default `hyperwave`). Unknown ids resolve to canonical, `skinId: null`.
- `options.colorBlind` → status `ok` uses `info` instead of `success`; glyphs stay (KIT §3.4).

### Common mappings

| Shell element | Token |
|---------------|-------|
| Screen background | `t.colors.bg` |
| Card / list row | `t.surfaces.card` (dark: `bgElevated` + 1 px `border`; light: `bgElevated` + `shadows.xs`) |
| Selected card | `t.surfaces.selected` |
| Bottom sheet / popover | `t.surfaces.sheet` |
| Modal | `t.surfaces.modal` + `scrim` (`overlay`) behind it |
| Primary button fill / label | `t.colors.primary` / `t.colors.onPrimary` (≥ 4.5:1 in every mode and skin) |
| Primary-coloured text / links | `t.colors.primaryText` (falls back to `primaryHover` where `primary` < 4.5:1 on `bg`, KIT §2.6) |
| Focus ring | 2 px `t.colors.borderFocus` + 2 px offset |
| Tab bar icons | `iconName('nav', …, 24)`, stroke `t.icons.spec[24].stroke`, touch `t.touch.min` |
| Screen title / section | `t.type.h1` / `t.type.h2` |
| Status chip | `t.status.ok|warn|bad|info|idle` → `color` + `glyph` + `shape` (never colour alone) |

React Navigation: `{ dark: t.isDark, colors: { primary: t.colors.primary, background: t.colors.bg, card: t.colors.bgElevated, text: t.colors.text, border: t.colors.border, notification: t.colors.danger } }`.

## 3. Light / dark

- Two canonical role sets: `foundation.roles.dark` = tokens.ts `canonicalColors.dark`,
  `foundation.roles.light` = `canonicalColors.light`, each plus `primaryText`. Same keys in both modes.
- **Skins are dark-only.** All 30 skins have near-black backgrounds, so `getTheme('light', id)`
  ignores the skin and returns the canonical light set (`skinId: null`).
- Light-mode text rules (KIT §2.5): `success` (3.60:1) and `warning` (3.04:1) are large text / icon
  only; `accentGold` (2.05:1) and `textDisabled` never carry information. `TEXT_USAGE[mode]` encodes
  these as `'body' | 'large' | 'never'`.
- Elevation differs by mode (KIT §2.4): dark is border-first (OLED, no shadows on card/raised/selected),
  light uses `shadows.xs/sm/md/lg`. Use `t.surfaces.*` instead of picking shadows by hand.
- `statusBarStyle` is `'light'` in dark mode and `'dark'` in light mode.

## 4. HUD

- Tiers: `hudType.critical` (`metric` 24/800, tabular), `contextualTitle` / `contextualLabel`
  (`h4` / `label`), `ambient` (`caption`). Never use `micro` in HUD; moving text ≥ 14 px.
- Safe zones: `hudSafeZone.titleSafe` 5 %, `actionSafe` 2.5 %, `thumbZone` bottom 40 %,
  `centreClear` 40 % × 40 %.
- Motion: `hudMotion.stateIn` 150 ms, `stateOut` 220 ms, `press` 80 ms at scale 0.97,
  `ambientFade` 3200 ms, `maxFlashesPerSecond` 3.
- Status pairing (HUD_SEMANTIC §2): ✓ solid · ! dashed triangle · ✕ diamond · i circle outline ·
  ○ hollow 50 %. Glyphs match `TONE_GLYPH` in the Forge cockpit (the test checks parity).

## 5. Icons

```ts
iconName('hud', 'health', 24);                     // 'ic_hud_health_24'
iconName('hud', 'threat', 32, { filled: true });   // 'ic_hud_threat_32_filled'
isIconName('ic_forge_build_20');                   // true
ICON_SPEC[32];  // { stroke: 2.5, padding: 2.5, minTouch: 48, use: 'HUD critical, empty states' }
```

SVGs use `ICON_GRID.viewBox` (`0 0 24 24`) and `ICON_STROKE_STYLE` (`fill="none" stroke="currentColor"`,
round caps/joins).

## 6. Mapping to the #2464 migration

#2464 consolidates the legacy theme sources onto tokens.ts. #4066 / #4070 moved `constants/themes.ts`,
`deluxe.ts` and the Forge theme onto tokens; this package finishes it: skin palettes and Forge glyphs
moved into tokens.ts, `skins.ts` became a derivation, and deluxe.ts reads `elevation` from the default
object (it previously named-imported a binding tokens.ts never exported, so `glow` was `undefined` and
importing deluxe.ts threw at runtime on main).

To change a value: edit tokens.ts → run `yarn test:canonical-theme && yarn test:foundation-tokens`.
To add a skin: append a row to tokens.ts `skinPalettes`.

Foundation is the **target API** for new and migrated code; the adapters stay for existing screens:

| Legacy | Foundation equivalent |
|--------|-----------------------|
| `useTheme().colors` (`constants/themes.ts`) | `getTheme(isDark ? 'dark' : 'light', getActiveSkinId()).colors` |
| `theme.colors.*` from tokens.ts default export (mutated by skinStore) | `getTheme('dark', getActiveSkinId()).colors` (immutable) |
| deluxe `S.*` / `R.*` / `T.*` | `spacing` / `radius` + `legacyRadius` / `typeScale` |
| deluxe `card` / `cardActive` | `t.surfaces.card` / `t.surfaces.selected` |
| Forge `TONE_COLOR` + `TONE_GLYPH` | `t.status.ok|warn|bad|idle` (`.color` + `.glyph`) |
| Forge `TOUCH` / `RADIUS` | `touch.min` / `radius.md` |
| `palette.cyan` meaning blue (old code) | `LEGACY_CYAN_BLUE` / `ramps.blue` |

Suggested order for Frontend (each a separate PR under #2464): (1) app shell root + navigation
theme on `getTheme`; (2) shared primitives (Button, Card, Chip, Icon) on `t.surfaces` / `t.status` /
`ICON_SPEC`; (3) screens one flow at a time; (4) once no screen reads mutated `theme.colors`,
skinStore can drive `getTheme` via `getActiveSkinId()` only. Visual sign-off by UI Art Lead per KIT §5.

## 7. Tests

`frontend/scripts/test-foundation-tokens.cjs` (`yarn test:foundation-tokens`, node `--test`, same
transpile-in-vm pattern as `test:canonical-theme`). It implements the WCAG luminance function
independently and checks:

- every KIT §2.5 tokens.ts text/background pair (dark and light) matches its claimed ratio
  (± 0.01) and level, plus `onPrimary` on `primary` in both modes;
- `getTheme` returns every key with no `undefined` for both modes × canonical + 30 skins, memoised and frozen;
- every dark skin: `onPrimary`/`primary` and `text`/`bg` ≥ 4.5:1, `primaryText` follows the §2.6 rule;
- drift guard: foundation's pinned dark defaults equal tokens.ts `colors.dark`; a skin applied
  before import does not leak into the canonical theme;
- status glyph parity with Forge `TONE_GLYPH`, colour-blind swap, icon naming, elevation rules;
- single edit point: no hex literal in skins.ts, themes.ts, useTheme.ts, deluxe.ts, Forge theme or
  `theme/foundation/*`; compatibility layers keep their export names and skins derive exactly from
  `skinPalettes`; skinStore-style mutation still drives deluxe `C`.

No per-PR workflow currently runs the frontend `node --test` scripts (the Product UI qualification
workflow is manual dispatch), so run it locally: `cd frontend && yarn test:foundation-tokens`.
