/**
 * Foundation radius — tokens.ts radii (UI_ART_KIT §2.3) plus the documented
 * legacy mappings and the icon keyline corner (UI_ART_ICONOGRAPHY.md §1).
 */
import { iconography, radii } from '../tokens';

export const radius = radii;
export type RadiusKey = keyof typeof radii;

/** UI_ART_KIT §2.3 mapping for the 2464 migration (legacy name -> canonical). */
export const legacyRadius = {
  /** deluxe.ts R.sm 6 -> xs 4 (chips). */
  deluxeSm: radii.xs,
  deluxeMd: radii.md,
  /** deluxe.ts R.lg 20 -> xl 20. */
  deluxeLg: radii.xl,
  deluxePill: radii.pill,
  /** skeletonForge RADIUS 12 -> md 12. */
  forge: radii.md,
} as const;

/** Square keyline corner radius at the 24 grid (UI_ART_ICONOGRAPHY.md §1). */
export const ICON_SQUARE_RADIUS = iconography.grid.squareCornerRadius;
