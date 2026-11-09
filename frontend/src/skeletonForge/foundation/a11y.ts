/**
 * Resolve studio motion and text-size preferences against what the platform
 * actually reports. Explicit sizes replace system scaling so the two do not stack.
 */
import type { StudioPrefs } from './model';
import { TEXT_SCALE } from './model';

export interface A11yPlatformSnapshot {
  /** The platform reports a reduced-motion preference. */
  motionSupported: boolean;
  systemReducedMotion: boolean;
  /** Native font scale, or null when the platform does not report one. */
  systemTextScale: number | null;
}

export interface ResolvedA11y {
  reduceMotion: boolean;
  textScale: number;
  allowSystemFontScaling: boolean;
}

export function resolveA11y(prefs: StudioPrefs, platform: A11yPlatformSnapshot): ResolvedA11y {
  const reduceMotion = prefs.reducedMotion === 'on'
    ? true
    : prefs.reducedMotion === 'off'
      ? false
      : Boolean(platform.motionSupported && platform.systemReducedMotion);
  if (prefs.textSize === 'system') {
    return { reduceMotion, textScale: 1, allowSystemFontScaling: true };
  }
  return { reduceMotion, textScale: TEXT_SCALE[prefs.textSize], allowSystemFontScaling: false };
}

export function motionHint(prefs: StudioPrefs, platform: A11yPlatformSnapshot): string {
  if (prefs.reducedMotion !== 'system') return prefs.reducedMotion === 'on' ? 'Motion is reduced in this studio.' : 'Motion is allowed in this studio.';
  if (!platform.motionSupported) return 'This platform does not report a motion setting. Match device leaves motion on.';
  return platform.systemReducedMotion ? 'The device is asking for reduced motion.' : 'The device is not asking for reduced motion.';
}

export function textHint(prefs: StudioPrefs, platform: A11yPlatformSnapshot): string {
  if (prefs.textSize === 'system') {
    if (platform.systemTextScale == null) {
      return 'This platform does not report a text size. Match device uses the system setting where it exists, otherwise the app default.';
    }
    return `Device text size is ${Math.round(platform.systemTextScale * 100)} percent. Studio text follows it.`;
  }
  return 'This size applies to studio controls. Match device to follow the system text size instead.';
}
