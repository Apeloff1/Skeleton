/**
 * Strict presentation helpers for the existing game KB route.
 * Backend remains authoritative for artifacts, stage approvals and job state.
 */
export function confirmedApprovalCount(value: unknown): number {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return 0;
  return Object.values(value).filter(item => item && typeof item === 'object' &&
    !Array.isArray(item) && (item as Record<string, unknown>).approved === true).length;
}

export function parseEditableKnowledge(raw: string): Record<string, unknown> {
  let value: unknown;
  try { value = JSON.parse(raw); } catch { throw new Error('Invalid JSON — check syntax.'); }
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Top level must be a JSON object.');
  }
  return value as Record<string, unknown>;
}
