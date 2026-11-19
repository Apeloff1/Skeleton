# Visual UI Kit — tokens audit, HUD and iconography rules

Owner: UI Art Lead (Unohashi) · Scope: **visual craft only** (colour, type, spacing, radius, elevation, HUD, icons).
Interaction logic, state management and component APIs belong to UI/UX engineering and are out of scope.
Status: spec / docs-only. **No code changes in this PR.** Consolidation is tracked in a separate issue.

All values below come from files on `main` at `8e4a228`. Contrast ratios were computed with the WCAG 2.x
relative-luminance formula (sRGB, `(L1 + 0.05) / (L2 + 0.05)`) on the hex values shown.

---

## 1. Audit — where visual values are defined today

### 1.1 Sources

| # | File | Exports | Consumed by (known) | Colour model | Spacing | Radius | Type | Elevation |
|---|------|---------|---------------------|--------------|---------|--------|------|-----------|
| A | `frontend/theme/tokens.ts` | default `theme` = `{ colors (dark), gradients, spacing, radii, typography, elevation, motion, hitSlop, breathing, palette }` | app-wide; mutated at runtime by `frontend/src/utils/skinStore.ts` | `palette.ink` 0–1000 (slate-based), `palette.brand` 50–900 (violet), semantic `colors.dark` / `colors.light` | `none 0, xs 4, sm 8, md 12, base 16, lg 20, xl 24, 2xl 32, 3xl 40, 4xl 56, 5xl 72` | `none 0, xs 4, sm 8, md 12, lg 16, xl 20, 2xl 28, 3xl 36, full/pill 9999` | 15 roles, display 34 → micro 10, mono 13/11 | `none, xs, sm, md, lg, xl, glow, glowCyan` |
| B | `frontend/theme/skins.ts` | `SKINS` (30), `DEFAULT_SKIN = 'hyperwave'`, `SKIN_BY_ID` | `frontend/src/utils/skinStore.ts` → `Object.assign(theme.colors, BASE, skin.colors)` | overrides 10 keys: `bg, bgElevated, bgSubtle, primary, primaryHover, primarySoft, borderFocus, accentCyan, accentPink, accentGold` | — | — | — | — |
| C | `frontend/constants/themes.ts` | `darkTheme`, `lightTheme`, `themes`, `ThemeColors` ("CodeDock Quantum Nexus v4.2.0") | `frontend/hooks/useTheme.ts` | flat 20-key palette, indigo primary | — | — | — | — |
| D | `frontend/hooks/useTheme.ts` | `useTheme()` → `{ theme, colors, setTheme, toggleTheme, isDark }` | screens using the hook | reads **C**, persists `'light' \| 'dark'` in AsyncStorage | — | — | — | — |
| E | `frontend/src/theme/deluxe.ts` | `C, S, R, T, card, cardActive, glow` ("Deluxe — Tutolage / Galaxy Studio") | creation → compete → monetize → level-up flow | neutral-grey (`#0A0A0A` base), violet brand | `xs 4, sm 8, md 12, lg 16, xl 24, xxl 32, xxxl 48` | `sm 6, md 12, lg 20, pill 999` | 7 roles (h1 26, h2 20, metric 24, label 12, body 14, small 12) | border-highlight `card`, `glow` |
| F | `frontend/src/skeletonForge/components/theme.ts` | `C, TONE_COLOR, TONE_GLYPH, TOUCH = 44, RADIUS = 12` | Skeleton Forge cockpit (mirrors `app/gameforge-studio.tsx`) | slate/navy (`#0b1220`), tone colours | — | single `RADIUS 12` | — | — |

So there are **four independent palettes** (A+B, C, E, F), **two independent theme-switch mechanisms**
(B's `skinStore` mutates A in place; D toggles C), and **three spacing/radius scales** (A, E, F).

### 1.2 Same role, different value

| Role | A `tokens.ts` (dark) | C `themes.ts` (dark) | E `deluxe.ts` | F `skeletonForge/.../theme.ts` | B default skin `hyperwave` |
|------|------|------|------|------|------|
| App background | `#070B16` (ink950) | `#0A0A0F` | `#0A0A0A` | `#0b1220` | `#0b0820` |
| Elevated surface | `#0B1120` (ink900) | `#12121A` | `#141414` | `#111827` | `#15103a` |
| Primary text | `#F8FAFC` | `#FFFFFF` | `#E5E5E5` | `#e5e7eb` (`textStrong #f8fafc`) | — |
| Muted text | `#94A3B8` | `#A0A0B0` (secondary) / `#606070` (muted) | `#A3A3A3` | `#94a3b8` / `#64748b` | — |
| Primary / brand | `#8B5CF6` | `#6366F1` | `#8B5CF6` | `#a78bfa` (accent), `#3b82f6` (blue) | `#c026d3` |
| Success | `#10B981` | `#22C55E` | `#10B981` | `#22c55e` | — |
| Warning | `#F59E0B` | `#F59E0B` | `#F59E0B` | `#f59e0b` | — |
| Danger | `#EF4444` | `#EF4444` | `#EF4444` | `#ef4444` | — |
| Gold | `#FBBF24` (accentGold) | `#FFD700` | `#F5C451` | — | `#fbbf24` |
| Border | `rgba(255,255,255,0.10)` | `#2A2A3A` | `#262626` | `#1f2a44` | — |

### 1.3 Contradictions and defects found

1. **Two "single sources of truth".** `tokens.ts` says "Single source of truth for every visual property… Do not hardcode colors anywhere else", yet `constants/themes.ts`, `src/theme/deluxe.ts` and `skeletonForge/components/theme.ts` each define full palettes.
2. **Default brand hue drifts.** `tokens.ts` brand is violet `#8B5CF6`, but the default skin `hyperwave` overrides `primary` with magenta `#c026d3` on first paint, and `themes.ts` uses indigo `#6366F1`. Three different "primary" hues can be on screen in one session.
3. **`palette.cyan` is blue.** `tokens.ts` `cyan: { 400: '#3B82F6', 500: '#2563EB', 600: '#1D4ED8' }` is the same ramp as `info`; `accentCyan` and gradient `cyan` are therefore blue, not cyan. Many skins also set `accentCyan` to `#3B82F6`. Rename to `blue` or replace with a real cyan ramp (C's `accent #22D3EE` is the only true cyan in the repo).
4. **Light mode is split.** `tokens.ts` has a full `colors.light` but `theme.colors` is hard-wired to `colors.dark`; the light/dark toggle in `useTheme` switches the *other* palette (C). The two light palettes disagree (e.g. primary `#7C3AED` vs `#4F46E5`).
5. **Skins override only 10 of ~30 colour keys.** Text, borders and status colours stay slate/violet-tuned while backgrounds turn green/red/orange; `primarySoft` is built by appending `'28'` (≈16% alpha) to the hex.
6. **Radius scales disagree at the same name.** `radii.lg` = 16 (A) vs `R.lg` = 20 (E); `R.sm` = 6 (E) does not exist in A (A has 4 and 8).
7. **Spacing scales disagree at the same name.** `spacing.lg` = 20 (A) vs `S.lg` = 16 (E); `xl` = 24 in both; E's `xxxl 48` is not on A's scale (A jumps 40 → 56).
8. **Type scales disagree.** `h1` 28/800 (A) vs 26/800 (E); `h2` 22/700 vs 20/800; letter-spacing negative (A) vs positive (E). E has no `lineHeight` on headings.
9. **Elevation philosophy disagrees.** A uses drop shadows `xs…xl`; E says "border-highlight elevation (no heavy drop shadows)" for OLED.
10. **Disabled text fails everywhere.** `textDisabled` is 2.59:1 (dark) and 2.45:1 (light). WCAG exempts disabled controls, but at gameplay speed it reads as missing content (see §3).
11. **On-primary text is not defined.** No `onPrimary` token exists. White on default `#8B5CF6` is 4.23:1 (fails AA for body text); white fails AA on 25 of 30 skin primaries (table §2.6).
12. **App icon assets are duplicated.** `icon.png`, `adaptive-icon.png` and `splash-icon.png` share blob `e1168f4e10` (512×512); `app-image.png` and `splash-image.png` share blob `5d2155c044` (336×729). `favicon.png` is 512×**513**. Expo template files `react-logo*.png` and `partial-react-logo.png` are still shipped.

---

## 2. Canonical kit (built from existing values — nothing new invented)

The canonical kit is `frontend/theme/tokens.ts`. Values below are its values; where another source has a
role tokens.ts lacks, the closest existing value is adopted and its origin noted.

### 2.1 Colour roles (dark, default)

| Role token | Value | From |
|------------|-------|------|
| `bg` | `#070B16` (ink950) | A |
| `bgElevated` | `#0B1120` (ink900) | A |
| `bgSubtle` | `#0D1425` (ink850) | A |
| `bgMuted` | `#1E293B` (ink700) | A |
| `surface` / `surfaceAlt` / `surfaceHover` | white @ 4.5% / 7% / 10% | A |
| `border` / `borderStrong` / `borderFocus` | white @ 10% / 18% / `#A78BFA` | A |
| `text` | `#F8FAFC` | A |
| `textMuted` | `#94A3B8` | A |
| `textDim` | `#64748B` (large text / icons only) | A |
| `textDisabled` | `#475569` (never for information) | A |
| `primary` / `primaryHover` | `#8B5CF6` / `#A78BFA` | A |
| `onPrimary` *(new name, existing value)* | `#FFFFFF` on `brand600 #7C3AED` for text buttons; use `primary #8B5CF6` fills only with ≥ 18.66 px bold labels or icons | A palette |
| `success` / `warning` / `danger` / `info` | `#10B981` / `#F59E0B` / `#EF4444` / `#3B82F6` | A |
| `accentPink` / `accentGold` | `#F472B6` / `#FBBF24` | A |
| `accentCyan` *(fix)* | `#22D3EE` (true cyan) | C `accent` |
| `overlay` / `overlayLight` | `rgba(4,6,13,0.72)` / `0.45` | A |

Light mode: use `tokens.ts` `colors.light` as-is, except status text (see 2.5).

### 2.2 Type scale (system UI font; mono = Menlo / monospace)

| Role | Size / line | Weight | Tracking | Use |
|------|-------------|--------|----------|-----|
| `display` | 34 / 40 | 800 | −0.5 | splash, results |
| `h1` | 28 / 34 | 800 | −0.4 | screen title |
| `h2` | 22 / 28 | 700 | −0.3 | section |
| `h3` | 18 / 24 | 700 | −0.2 | card title |
| `h4` | 16 / 22 | 700 | −0.1 | list header |
| `bodyLg` | 16 / 24 | 500 | 0 | long-form |
| `body` | 14 / 20 | 500 | 0 | default |
| `caption` | 12 / 16 | 600 | 0 | meta |
| `micro` | 10 / 14 | 700 | +0.4, UPPERCASE | tags only, never HUD-critical |
| `metric` *(from E)* | 24 / 28 | 800 | +0.5, tabular | HUD numbers, scores |
| `label` *(from E)* | 12 / 16 | 700 | +1.1, UPPERCASE | HUD labels |
| `mono` / `monoSm` | 13 / 18, 11 / 14 | 500 | 0 | code, logs |
| `buttonLg` / `button` / `buttonSm` | 16/20, 14/18, 12/16 | 700 | — | buttons |

`deluxe.ts` display font (`sans-serif-condensed` on Android) may stay as a **display-only** family for HUD metrics.

### 2.3 Spacing and radius

- **Spacing (4-pt base):** `0, 4, 8, 12, 16, 20, 24, 32, 40, 56, 72` (A). E's `48` maps to `3xl 40` or `4xl 56`; prefer `4xl` for section breaks.
- **Layout rhythm:** use A `breathing` (`gutter 14`, `cardPadding 14`, `minTouch 44`, `headerHeight 56`). Note 14 is off the 4-pt grid by design (A); keep it but do not add new off-grid values.
- **Radius:** `4, 8, 12, 16, 20, 28, 36, 9999` (A). Mapping: E `R.sm 6` → `xs 4` (chips) or `sm 8`; E `R.lg 20` → `xl 20`; F `RADIUS 12` → `md 12`.
- **Touch target:** 44 pt minimum (A `minTouch`, F `TOUCH`). `minTouchSm 38` only with `hitSlop.sm` (6) to reach 44+ effective.

### 2.4 Elevation

| Level | Dark (OLED) treatment | Light treatment | Token |
|-------|------------------------|-----------------|-------|
| 0 flat | `bg` | `bg` | `elevation.none` |
| 1 card | `bgElevated` + 1 px `border` | `elevation.xs` | E `card` pattern |
| 2 raised / selected | `surfaceAlt` + 1 px `borderStrong` (selected: `borderFocus`) | `elevation.sm` | E `cardActive` |
| 3 sheet / popover | `bgSubtle` + `elevation.md` | `elevation.md` | A |
| 4 modal | `overlay` scrim + `elevation.lg` | `elevation.lg` | A |
| accent | `elevation.glow` — one per screen max (primary CTA / active objective) | same | A / E `glow` |

On dark backgrounds, separation comes from surface tint + border first, shadow second (E's OLED rule is adopted).

### 2.5 WCAG AA contrast — real pairs

AA = 4.5:1 normal text, 3:1 large text (≥ 24 px, or ≥ 18.66 px bold) and UI glyphs/icons.

| Pair (fg on bg) | Hex | Ratio | Result |
|-----------------|-----|-------|--------|
| A dark `text` on `bg` | `#F8FAFC` / `#070B16` | 18.78:1 | AAA |
| A dark `textMuted` on `bg` | `#94A3B8` / `#070B16` | 7.67:1 | AAA |
| A dark `textMuted` on `bgElevated` | `#94A3B8` / `#0B1120` | 7.34:1 | AAA |
| A dark `textDim` on `bg` | `#64748B` / `#070B16` | 4.13:1 | large / UI only |
| A dark `textDisabled` on `bg` | `#475569` / `#070B16` | 2.59:1 | **fail** |
| A dark `primary` on `bg` | `#8B5CF6` / `#070B16` | 4.64:1 | AA |
| A dark `primaryHover` on `bg` | `#A78BFA` / `#070B16` | 7.22:1 | AAA |
| White on `primary` `#8B5CF6` | `#FFFFFF` / `#8B5CF6` | 4.23:1 | large / UI only |
| White on `brand600` | `#FFFFFF` / `#7C3AED` | 5.70:1 | AA |
| A dark `success` on `bg` | `#10B981` / `#070B16` | 7.75:1 | AAA |
| A dark `warning` on `bg` | `#F59E0B` / `#070B16` | 9.15:1 | AAA |
| A dark `danger` on `bg` | `#EF4444` / `#070B16` | 5.22:1 | AA |
| A dark `info` on `bg` | `#3B82F6` / `#070B16` | 5.34:1 | AA |
| A dark `accentPink` on `bg` | `#F472B6` / `#070B16` | 7.42:1 | AAA |
| A light `text` on `bg` | `#0B1120` / `#F8FAFC` | 18.00:1 | AAA |
| A light `textMuted` on `bg` | `#475569` / `#F8FAFC` | 7.24:1 | AAA |
| A light `textDim` on `bg` | `#64748B` / `#F8FAFC` | 4.55:1 | AA (barely) |
| A light `textDisabled` on `bg` | `#94A3B8` / `#F8FAFC` | 2.45:1 | **fail** |
| A light `primary` on `bg` | `#7C3AED` / `#F8FAFC` | 5.45:1 | AA |
| A light `success` on `bg` | `#059669` / `#F8FAFC` | 3.60:1 | large / UI only |
| A light `warning` on `bg` | `#D97706` / `#F8FAFC` | 3.04:1 | large / UI only |
| A light `danger` on `bg` | `#DC2626` / `#F8FAFC` | 4.62:1 | AA |
| A light `accentGold` on `bg` | `#F59E0B` / `#F8FAFC` | 2.05:1 | **fail** |
| F `text` on `bg` | `#e5e7eb` / `#0b1220` | 15.12:1 | AAA |
| F `mute` on `card` | `#94a3b8` / `#111827` | 6.92:1 | AA |
| F `dim` (idle tone) on `card` | `#64748b` / `#111827` | 3.73:1 | large / UI only |
| F `green` / `amber` / `red` / `blue` on `card` | vs `#111827` | 7.79 / 8.26 / 4.71 / 4.82 | AA+ |
| E `text` on `bg` | `#E5E5E5` / `#0A0A0A` | 15.72:1 | AAA |
| E `textMute` on `surface` | `#A3A3A3` / `#141414` | 7.30:1 | AAA |
| E `brand` on `bg` | `#8B5CF6` / `#0A0A0A` | 4.68:1 | AA |
| C dark `textMuted` on `background` | `#606070` / `#0A0A0F` | 3.20:1 | large / UI only |
| C dark `primary` on `background` | `#6366F1` / `#0A0A0F` | 4.42:1 | large / UI only |
| C light `gold` on `surface` | `#CA8A04` / `#FFFFFF` | 2.94:1 | **fail** |

**Rules from the table**
- Light mode status colours (`success`, `warning`, `accentGold`) must not carry body text. Use them for icons/fills with `text` labels, or step to the `-600`/darker value plus an icon.
- `textDim` is for large text, icons and dividers only. `textDisabled` must never carry information.
- Text on a `primary` fill uses `brand600` or bold ≥ 18.66 px labels.

### 2.6 Skins — `onPrimary` per skin

White on skin `primary` passes AA (4.5:1) in only **5 of 30** skins (`hyperwave 4.71`, `coffee 5.02`, `slate 4.76`, `blood 4.83`, `cyber 5.17` — `royal 4.47` just misses).
Dark ink `#0B1120` (ink900) on the primary is the better choice for the rest. Proposed `onPrimary` per skin (higher of the two). `royal` (4.47) and `lavender` (4.45) miss 4.5:1 with either choice, so use bold ≥ 18.66 px labels on their primary fills, or step `primary` one shade darker:

| `onPrimary` = `#FFFFFF` | `onPrimary` = `#0B1120` |
|---|---|
| hyperwave (4.71), coffee (5.02), royal (4.47), slate (4.76), blood (4.83), cyber (5.17) | midnight 5.12, aurora 7.42, ember 6.72, forest 8.26, mono 12.70, sakura 5.34, oceanic 5.12, neon 9.53, sunset 7.00, glacier 10.44, vapor 6.92, goldnoir 11.56, matrix 8.26, crimson 5.00, lavender 4.45, arctic 7.41, toxic 12.49, peach 8.32, mint 7.41, dune 5.91, nebula 4.76, rosegold 9.96, obsidian 6.31, citrus 9.82 |

Skin `primary` as text on its own `bg` falls below 4.5:1 for `hyperwave 4.17`, `coffee 3.87`, `slate 4.11`, `blood 4.13`, `cyber 3.89`, `royal 4.40` → use `primaryHover` for primary-coloured text in those skins.

---

## 3. HUD rules (gameplay overlays, cockpit, Forge run views)

### 3.1 Safe zones
- **Title-safe:** all critical HUD content inside a 5% inset on each edge (TV/console) or the OS safe-area insets plus `breathing.gutter` (14) on mobile, whichever is larger. Bottom inset never below `breathing.safeBottomMin` (14).
- **Action-safe:** decorative frames may reach 2.5% from the edge; no text there.
- **Thumb zones (touch):** primary actions in the bottom 40% of the screen, ≥ 44 pt targets (`minTouch`), ≥ 8 px (`spacing.sm`) apart.
- **Centre clear:** the middle 40% × 40% of the screen stays free of persistent HUD; only transient hit markers, telegraphs and reticle.

### 3.2 Hierarchy (max 3 tiers on screen)
1. **Critical** — health, threat, objective timer: `metric` style (24/800), `text` colour, top-left or bottom-centre, never moves.
2. **Contextual** — ammo/resources/cooldowns, current objective: `h4`/`label`, `textMuted`, appears near the relevant action.
3. **Ambient** — score feed, notifications, minimap labels: `caption`, auto-fade after 3 s (`motion.duration.slow` ×10 rule of thumb).
- One `elevation.glow` element per screen (the current objective or primary CTA).
- No more than **one** pulsing/animated element at a time per tier.

### 3.3 Readability at gameplay speed
- HUD text minimum 14 px (`body`) for anything read while moving; `micro` (10 px) is forbidden in HUD.
- Numbers use tabular figures and `metric`/`label`; never animate digit width.
- HUD text sits on a scrim (`overlayLight` `rgba(4,6,13,0.45)` or `overlay` 0.72) or has a 1 px `#04060D` outline/shadow, so contrast ≥ 4.5:1 holds over any scene.
- State changes use `motion.duration.fast` (150 ms) in, `base` (220 ms) out; damage/alert flashes ≤ 3 per second (photosensitivity).
- Glance test: the critical tier must be readable in a 250 ms glance at arm's length on a 6" phone.

### 3.4 Colour-blind-safe pairings
Never encode state by hue alone. Pair **colour + glyph + position/shape**. The cockpit already does this with
`TONE_GLYPH` (`ok ✓`, `warn !`, `bad ✕`, `idle ○`) in `frontend/src/skeletonForge/components/theme.ts` — make this the HUD rule everywhere.

| Meaning | Colour (dark) | Glyph | Shape/pattern |
|---------|---------------|-------|---------------|
| Good / friendly | `success #10B981` | ✓ | solid fill |
| Warning | `warning #F59E0B` | ! | triangle, dashed outline |
| Bad / hostile | `danger #EF4444` | ✕ | diamond, solid |
| Info / neutral | `info #3B82F6` | i | circle outline |
| Idle / unavailable | `textDim #64748B` | ○ | hollow, 50% opacity |

- Red/green must not be the only distinction (deuteranopia/protanopia). Friendly vs hostile: **blue (`info`) vs orange/amber (`warning`)** is the safe default pair; use red only with the ✕/diamond.
- Provide a colour-blind mode that swaps `success` → `info` and keeps glyphs.

### 3.5 Interaction states (visual only)

| State | Fill | Border | Text/icon | Other |
|-------|------|--------|-----------|-------|
| Default | `surface` | `border` | `text` | — |
| Hover (pointer) | `surfaceHover` | `borderStrong` | `text` | — |
| Pressed | `surfaceAlt` | `borderStrong` | `text` | scale 0.97, `motion.duration.micro` (80 ms) |
| Focus (keyboard/gamepad) | unchanged | 2 px `borderFocus` `#A78BFA` + 2 px offset | `text` | always visible, never colour-only |
| Selected / active | `primarySoft` | `primary` | `text` | E `cardActive` |
| Disabled | `surface` | `border` | `textDisabled` + 50% icon opacity | add lock glyph if the reason matters |
| Error | `surface` | `danger` | `text` + ✕ glyph | message in `danger` on `bg` (5.22:1) |
| Loading | `skeleton` (`ink800`) shimmer | — | — | `motion.duration.slow` loop |

---

## 4. Iconography spec

`@expo/vector-icons` (^15.0.3) and `react-native-svg` (15.12.1) are already dependencies; custom icons ship as SVG via `react-native-svg`.

### 4.1 Grid and keylines
- Master artboard **24 × 24**, 2 px padding → 20 × 20 live area.
- Keyline shapes inside the live area: circle Ø20, square 18 × 18, portrait 16 × 20, landscape 20 × 16.
- Snap to whole pixels at 24; corner radius 2 px on squares (scales with `radii.xs`).
- Optical centre: shift triangles/play glyphs ~0.5 px right.

### 4.2 Stroke
- **2 px** stroke at 24, round caps and round joins. Filled variant for selected/active state only.
- Stroke scales with size: 16 → 1.5 px, 20 → 1.75 px, 24 → 2 px, 32 → 2.5 px, 48 → 3 px (hand-tuned, not auto-scaled).
- Single colour, `currentColor`; no gradients inside glyphs (gradients belong to the container, e.g. `gradients.brand`).

### 4.3 Sizes

| Size | Use | Padding | Stroke | Min touch wrapper |
|------|-----|---------|--------|-------------------|
| 16 | inline with `caption`/`body`, table status | 1 px | 1.5 | n/a (not tappable alone) |
| 20 | list rows, buttons with `button` label | 1.5 px | 1.75 | 44 |
| 24 | default; tab bar, toolbar, HUD contextual | 2 px | 2 | 44 |
| 32 | HUD critical, empty states | 2.5 px | 2.5 | 48 |
| 48 | feature tiles, onboarding, results | 4 px | 3 | — |

Icons on fills meet 3:1 against the fill (WCAG 1.4.11): use the §2.6 `onPrimary` table.

### 4.4 Naming
`ic_<domain>_<object>[_<modifier>]_<size>[_filled]`, lower snake case. Examples: `ic_hud_health_24`, `ic_hud_threat_32_filled`, `ic_forge_build_20`, `ic_status_ok_16` (maps to `TONE_GLYPH.ok`). Domains: `nav`, `hud`, `forge`, `status`, `action`, `social`, `store`.

### 4.5 Export formats
- **Source:** SVG, 24-grid master, outlined strokes in an `_src` layer kept editable.
- **App:** optimised SVG (SVGO, no IDs/metadata, `viewBox="0 0 24 24"`, `fill="none" stroke="currentColor"`), rendered through `react-native-svg`.
- **Raster fallbacks** (notifications, store, web OG): PNG @1x/2x/3x, matching the existing `react-logo.png / @2x / @3x` convention.

### 4.6 Mapping to existing app icons (`frontend/assets/images`, referenced by `frontend/app.json`)

| File | Size | Blob | Referenced as | Finding / rule |
|------|------|------|---------------|----------------|
| `icon.png` | 512 × 512 | `e1168f4e10` | `expo.icon` | Store/app icon should be **1024 × 1024**, no transparency (iOS). Re-export from master. |
| `adaptive-icon.png` | 512 × 512 | `e1168f4e10` (same as `icon.png`) | `android.adaptiveIcon.foregroundImage`, `backgroundColor #000000` | Must be a **separate** 1024 × 1024 foreground with the mark inside the central 66% safe zone; current file is a copy of the full icon and will be cropped by launcher masks. Background should use `bg #070B16`, not pure black, to match the kit. |
| `splash-icon.png` | 512 × 512 | `e1168f4e10` (same) | not in `app.json` `splash` (null) | Keep as splash mark; centre on `bg #070B16`. |
| `favicon.png` | 512 × **513** | `b402baf317` | `web.favicon` | Off-by-one height; re-export square (48 × 48 + 192/512 PWA). |
| `app-image.png` / `splash-image.png` | 336 × 729 | `5d2155c044` (identical) | — | Duplicate; keep one. |
| `react-logo*.png`, `partial-react-logo.png` | small | — | Expo template | Not brand assets; candidates for removal (needs owner OK — not done here). |

Brand mark source of truth: one master SVG (to be added under `frontend/assets/brand/`), from which all of the above are exported.

---

## 5. Migration note — single source of truth

**Canonical module: `frontend/theme/tokens.ts`.** It already has the richest scale (palette ramps, semantic dark/light roles, spacing, radii, typography, elevation, motion, hit slop) and is the module `skinStore` mutates.

Proposed order (separate engineering PRs; nothing changes here):
1. Add the missing roles to `tokens.ts`: `onPrimary`, `metric`/`label` type roles, true cyan (`#22D3EE`) and rename `palette.cyan` → `palette.blue`.
2. Extend `SkinColors` in `frontend/theme/skins.ts` with `onPrimary` (values in §2.6) and derive `primarySoft` from `palette` alpha instead of string concatenation.
3. Make `frontend/constants/themes.ts` a thin re-export mapped from `tokens.ts` (`colors.dark` / `colors.light`) and point `frontend/hooks/useTheme.ts` at it, so the light/dark toggle and skins drive one palette.
4. Re-express `frontend/src/theme/deluxe.ts` `C/S/R/T` as aliases of tokens (`S.lg` → `spacing.base`, `R.lg` → `radii.xl`, `R.sm` → `radii.xs`/`sm`).
5. Re-express `frontend/src/skeletonForge/components/theme.ts` `C` as aliases; keep `TONE_GLYPH`, `TOUCH`, `RADIUS` (→ `radii.md`).
6. Lint guard (later): forbid hex literals outside `frontend/theme/`.

Tracking issue: "UI tokens: consolidate theme sources into a single token module".
