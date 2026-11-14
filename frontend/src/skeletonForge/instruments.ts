/**
 * Historical Prood DeepSlider UX recovered as a *sparse*, per-run editor.
 * Keys mirror skeleton.context.tensor.AXES; values stay finite and in [0,1].
 * Untouched axes are NOT implied to equal 0.5: they belong to GameForge.
 */
export const DESIGN_AXES = [
  { id: 'risk', label: 'Risk', hint: 'Consequences, stakes and survival pressure' },
  { id: 'tempo', label: 'Tempo', hint: 'Pacing and combat or exploration speed' },
  { id: 'lethality', label: 'Lethality', hint: 'How dangerous conflict and failure feel' },
  { id: 'opacity', label: 'Mystery', hint: 'How much players must discover for themselves' },
  { id: 'scarcity', label: 'Scarcity', hint: 'Resource pressure and abundance' },
  { id: 'agency', label: 'Agency', hint: 'Player choice and systemic freedom' },
  { id: 'spectacle', label: 'Spectacle', hint: 'Visual intensity and dramatic scale' },
  { id: 'intimacy', label: 'Intimacy', hint: 'Character relationships and emotional proximity' },
  { id: 'grind', label: 'Progression depth', hint: 'Investment, repetition and long-term mastery' },
  { id: 'authorial', label: 'Authored direction', hint: 'Strength of the designed narrative or challenge' },
] as const;

export type DesignAxis = typeof DESIGN_AXES[number]['id'];
export function isDesignAxis(axis: string): axis is DesignAxis {
  return DESIGN_AXES.some((item) => item.id === axis);
}
export function normaliseAxisEdit(value: unknown): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value)) return null;
  return Math.round(Math.max(0, Math.min(1, value)) * 100) / 100;
}
export function sparseInstrumentPayload(values: Record<string, number> | undefined): Record<string, number> {
  const result: Record<string, number> = {};
  if (!values) return result;
  for (const axis of DESIGN_AXES) {
    const value = values[axis.id];
    if (value !== undefined) {
      const bounded = normaliseAxisEdit(value);
      if (bounded !== null) result[axis.id] = bounded;
    }
  }
  return result;
}
