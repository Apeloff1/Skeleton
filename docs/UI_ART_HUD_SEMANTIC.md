# HUD semantic palette

Owner: UI Art Lead (Unohashi) · Scope: visual craft only.
Companion to [`docs/UI_ART_KIT.md`](./UI_ART_KIT.md). Values are taken from `frontend/theme/tokens.ts` and the kit audit; nothing here invents a second palette.
Status: docs-only. Token code changes stay on [#2464](https://github.com/Apeloff1/Skeleton/issues/2464).

## 1. Canonical semantic roles (dark, default)

| Role | Token | Hex | On dark `bg` `#070B16` | Notes |
|------|-------|-----|------------------------|-------|
| Danger / hostile | `danger` | `#EF4444` | 5.22:1 AA | Never alone — always pair with ✕ / diamond |
| Warning | `warning` | `#F59E0B` | 9.15:1 AAA | Triangle + `!` glyph |
| Success / friendly | `success` | `#10B981` | 7.75:1 AAA | Check + solid fill |
| Info / neutral | `info` | `#3B82F6` | 5.34:1 AA | Circle outline + `i` |
| Idle / unavailable | `textDim` | `#64748B` | 4.13:1 large/UI only | Hollow ○ at 50% opacity |
| Gold / reward | `accentGold` | `#FBBF24` | AAA on dark | Not for body text on light surfaces |
| True cyan *(proposed rename)* | `accentCyan` | `#22D3EE` | from kit §2.1 | Replace misnamed `palette.cyan` blue |

Light-mode status colours (`success` `#059669`, `warning` `#D97706`, `danger` `#DC2626`) fail or barely meet AA as text on `#F8FAFC`. Use them as **icons/fills** with `text` labels, or step to the darker shade.

## 2. Colorblind-safe pairing (HUD rule everywhere)

Never encode state by hue alone. Pair **colour + glyph + shape**, extending the cockpit `TONE_GLYPH` set in `frontend/src/skeletonForge/components/theme.ts`:

| Meaning | Colour | Glyph | Shape |
|---------|--------|-------|-------|
| Good / friendly | `success #10B981` | ✓ | solid fill |
| Warning | `warning #F59E0B` | ! | triangle, dashed outline |
| Bad / hostile | `danger #EF4444` | ✕ | diamond, solid |
| Info / neutral | `info #3B82F6` | i | circle outline |
| Idle | `textDim #64748B` | ○ | hollow, 50% opacity |

Safe default pair for friendly vs hostile under deuteranopia/protanopia: **blue (`info`) vs amber (`warning`)**. Red is only used with the ✕/diamond glyph. A colour-blind mode swaps `success` → `info` and keeps glyphs.

## 3. Where each role appears on HUD

| Surface | Roles | Hierarchy |
|---------|-------|-----------|
| Health / threat | danger, warning, success | Critical tier (`metric` 24/800) |
| Objective timer | warning → danger as time runs out | Critical; one glow max |
| Ammo / resources / cooldowns | info, textMuted | Contextual |
| Combat telegraphs | danger (hostile), warning (telegraph), success (friendly) | Transient; centre clear zone |
| Notifications / feed | info, success, danger | Ambient; fade after ~3 s |

Safe zones, 3-tier hierarchy, and gameplay-speed readability rules are unchanged from `UI_ART_KIT.md` §3.

## 4. Interaction states (HUD chips / status buttons)

| State | Fill | Border | Icon/text | Extra |
|-------|------|--------|-----------|-------|
| Default | `surface` | `border` | role colour + glyph | — |
| Hover | `surfaceHover` | `borderStrong` | same | — |
| Pressed | `surfaceAlt` | `borderStrong` | same | scale 0.97, 80 ms |
| Focus | unchanged | 2 px `borderFocus` `#A78BFA` + 2 px offset | same | never colour-only |
| Selected | `primarySoft` | `primary` | same | — |
| Disabled | `surface` | `border` | `textDisabled` + lock glyph | no information in disabled text |
| Error | `surface` | `danger` | danger + ✕ | message in `danger` on `bg` |
| Loading | `ink800` shimmer | — | — | slow loop |

## 5. Acceptance for engineering (#2464)

- [ ] `tokens.ts` exposes the five semantic roles above with these hex values (already present for danger/warn/success/info).
- [ ] HUD components consume `TONE_GLYPH` (or an identical export) for every semantic chip.
- [ ] No HUD state is colour-only.
- [ ] Visual review by UI Art Lead against this doc before merge.
