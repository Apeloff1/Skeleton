/** Developmental dragon forms may be inspected, but not auto-animated until
 * real rig/wing contact clearance is independently qualified.
 *
 * This is a PRESENTATION policy, not authorization to earn XP or dispatch work.
 * Never infer safety from a valid SHA-256, structural GLB, or synthetic test.
 */
import type {AtelierVariant} from './atelierAsset';

export type MotionIntent = Readonly<{airborne:boolean;reduced:boolean}>;
export type MotionPolicy = Readonly<MotionIntent & {
  mode:'original-event-driven'|'manual-pose-only';
  isClearanceHold:boolean;
}>;

export function enforceDragonClearanceHold(
  variant:AtelierVariant,
  intent:MotionIntent,
):MotionPolicy {
  const original=variant==='hoarder';
  return Object.freeze({
    airborne:original && intent.airborne,
    reduced:!original || intent.reduced,
    mode:original?'original-event-driven':'manual-pose-only',
    isClearanceHold:!original,
  });
}
