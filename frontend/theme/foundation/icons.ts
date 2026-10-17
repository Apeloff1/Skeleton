/**
 * Foundation iconography — read-only view over tokens.ts `iconography`
 * (UI_ART_ICONOGRAPHY.md / UI_ART_KIT §4), plus the naming helper (§4).
 */
import { iconography, radii } from '../tokens';

/** Master artboard, live area, keylines, viewBox (§1). */
export const ICON_GRID = iconography.grid;

export type IconSize = (typeof iconography.sizes)[number];
export const ICON_SIZES: readonly IconSize[] = iconography.sizes;

export type IconSpec = {
  stroke: number;
  padding: number;
  /** Minimum touch wrapper; null = not tappable alone / not specified. */
  minTouch: number | null;
  use: string;
};

/** Size table (§2 stroke, §3 sizes and touch). Hand-tuned, not auto-scaled. */
export const ICON_SPEC: Readonly<Record<IconSize, IconSpec>> = iconography.spec;

export const ICON_STROKE_STYLE = iconography.strokeStyle;

/** Square keyline corner scales with radii.xs (§1). */
export const ICON_CORNER_TOKEN = radii.xs;

export type IconDomain = (typeof iconography.domains)[number];
export const ICON_DOMAINS: readonly IconDomain[] = iconography.domains;

const SNAKE = /^[a-z0-9]+(?:_[a-z0-9]+)*$/;

/**
 * Build a canonical icon name: `ic_<domain>_<object>[_<modifier>]_<size>[_filled]` (§4).
 * Throws on a non-snake-case object/modifier, unknown domain or off-spec size.
 */
export function iconName(domain: IconDomain, object: string, size: IconSize, opts: { modifier?: string; filled?: boolean } = {}): string {
  if (!ICON_DOMAINS.includes(domain)) throw new Error(`iconName: unknown domain ${domain}`);
  if (!ICON_SIZES.includes(size)) throw new Error(`iconName: off-spec size ${size}`);
  if (!SNAKE.test(object)) throw new Error(`iconName: object must be lower snake case, got ${object}`);
  if (opts.modifier !== undefined && !SNAKE.test(opts.modifier)) throw new Error(`iconName: modifier must be lower snake case, got ${opts.modifier}`);
  const parts: string[] = ['ic', domain, object];
  if (opts.modifier) parts.push(opts.modifier);
  parts.push(String(size));
  if (opts.filled) parts.push('filled');
  return parts.join('_');
}

const NAME_RE = new RegExp(`^ic_(${iconography.domains.join('|')})_([a-z0-9]+(?:_[a-z0-9]+)*)_(${iconography.sizes.join('|')})(_filled)?$`);

/** Validate an icon name against the §4 convention. */
export function isIconName(name: string): boolean {
  return NAME_RE.test(name);
}
