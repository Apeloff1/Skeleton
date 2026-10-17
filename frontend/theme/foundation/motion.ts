/**
 * Foundation motion — durations and easings from tokens.ts `motion`, plus the
 * HUD timing rules from tokens.ts `hud.motion` (UI_ART_KIT §3.2, §3.3, §3.5):
 * state in = fast, out = base, press = micro at 0.97, shimmer = slow,
 * ambient fade = slow × 10, <= 3 flashes/s, one pulsing element per tier.
 */
import { hud, motion } from '../tokens';

export const duration = motion.duration;
export const easing = motion.easing;
export type DurationKey = keyof typeof motion.duration;
export type EasingKey = keyof typeof motion.easing;

export const hudMotion = hud.motion;
