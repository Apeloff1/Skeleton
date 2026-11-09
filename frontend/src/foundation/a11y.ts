/**
 * Accessibility baseline helpers shared by foundation primitives.
 * Pure: values come from theme/tokens but are passed in, keeping this testable.
 */
export const MIN_TOUCH_TARGET = 44;

/** Hit slop needed to bring a visual element up to the minimum touch target. */
export function hitSlopFor(width: number, height: number, min: number = MIN_TOUCH_TARGET) {
  const h = Math.max(0, Math.ceil((min - width) / 2));
  const v = Math.max(0, Math.ceil((min - height) / 2));
  return { top: v, bottom: v, left: h, right: h };
}

export function touchTargetStyle(min: number = MIN_TOUCH_TARGET) {
  return { minHeight: min, minWidth: min };
}

/** Animation duration that collapses to 0 when the user prefers reduced motion. */
export function motionDuration(ms: number, reduceMotion: boolean): number {
  return reduceMotion ? 0 : Math.max(0, ms);
}

/** Build a spoken label: skips empty parts, joins with commas. */
export function composeLabel(...parts: (string | number | null | undefined | false)[]): string {
  return parts.filter(p => p !== null && p !== undefined && p !== false && String(p).trim() !== '').map(p => String(p).trim()).join(', ');
}

/** WCAG relative-luminance contrast ratio between two #RRGGBB colors. */
export function contrastRatio(a: string, b: string): number {
  const lum = (hex: string) => {
    const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
    if (!m) throw new Error(`Invalid color: ${hex}`);
    const n = parseInt(m[1], 16);
    const ch = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map(v => {
      const c = v / 255;
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
  };
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}
