/**
 * Forge-operator tab ids + deep-link parsing (?tab=compose|plans|…).
 * Mirrors skeletonForge/cockpitScreen tab helpers without coupling to that UI.
 */
export const OPERATOR_TABS = ['compose', 'plans', 'walk', 'eras', 'beats', 'report', 'recovery'] as const;
export type OperatorTab = (typeof OPERATOR_TABS)[number];

export const OPERATOR_TAB_LABELS: Record<OperatorTab, string> = {
  compose: 'Compose / Run',
  plans: 'Plans',
  walk: 'Walk',
  eras: 'Eras',
  beats: 'Beats',
  report: 'Run report',
  recovery: 'Recovery',
};

export const OPERATOR_TAB_HINTS: Record<OperatorTab, string> = {
  compose: 'Compose a vision, then forge via /api/skeleton or sealed engine run',
  plans: 'POST /api/skeleton/plan — Jeeves build plan preview',
  walk: 'POST /api/skeleton/walk — extraction walkthrough preview',
  eras: 'GET /api/skeleton/eras — dialect pack catalogue',
  beats: 'GET /api/skeleton/beats — questionnaire beats',
  report: 'Seal · playtest · repair status from the last engine/app run',
  recovery: 'Cancel in-flight work, clear seal, and reset operator state',
};

export function parseOperatorTab(raw: string | string[] | null | undefined): OperatorTab | null {
  const v = Array.isArray(raw) ? raw[0] : raw;
  if (!v) return null;
  const key = String(v).trim().toLowerCase();
  return (OPERATOR_TABS as readonly string[]).includes(key) ? (key as OperatorTab) : null;
}

export function tabA11yLabel(tab: OperatorTab, badge?: string | null): string {
  const base = OPERATOR_TAB_LABELS[tab];
  return badge ? `${base}, ${badge}` : base;
}
