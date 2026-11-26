/** Pure transport and review helpers. A model reply is data, never authority. */
export const JOURNEY_IDS = ['research', 'plan', 'creative', 'study', 'studio'] as const;
export type JourneyId = typeof JOURNEY_IDS[number];
export type JourneySource = { id: string; label: string; locator: string; excerpt: string };
export type JourneyRequest = { journey_id: JourneyId; goal: string; options: Record<string, string | number>; source_refs: JourneySource[] };
export type JourneyArtifact = {
  schema_version: 'skeleton.ai.workflow_artifact.v1'; journey_id: JourneyId;
  request_digest: string; title: string;
  [key: string]: unknown;
};
export type JourneyPreview = {
  schema_version: 'skeleton.ai.workflow_preview.v1'; journey_id: JourneyId; request_digest: string;
  artifact: JourneyArtifact; artifact_digest: string; checks: Record<string, unknown>; warnings: string[];
  execution_authorized: false;
};
export const REQUEST_MARKER = 'JEEVES_WORKFLOW_REQUEST_V1=';
export const ARTIFACT_SCHEMA = 'skeleton.ai.workflow_artifact.v1';
export const HASH = /^[a-f0-9]{64}$/;
export function canonicalJourneyJSON(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(canonicalJourneyJSON).join(',') + ']';
  if (isObject(value)) return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonicalJourneyJSON(value[key])).join(',') + '}';
  return JSON.stringify(value);
}
export function isObject(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === 'object' && !Array.isArray(value);
}
export function isJourneyId(value: unknown): value is JourneyId {
  return JOURNEY_IDS.includes(value as JourneyId);
}
export function checkedRequest(value: unknown): JourneyRequest {
  if (!isObject(value) || !isJourneyId(value.journey_id) || typeof value.goal !== 'string'
    || !value.goal.trim() || value.goal.length > 4000 || !isObject(value.options)
    || Object.keys(value.options).length > 12 || Object.values(value.options).some(item =>
      typeof item !== 'string' && !(Number.isSafeInteger(item) && Number(item) >= 0))
    || !Array.isArray(value.source_refs) || value.source_refs.length > 8) throw new Error('The saved journey request is invalid. Prepare a new request.');
  const ids = new Set<string>();
  for (const source of value.source_refs) {
    if (!isObject(source) || typeof source.id !== 'string' || !/^[A-Za-z0-9_-]{1,64}$/.test(source.id)
      || ids.has(source.id) || typeof source.label !== 'string' || !source.label.trim() || source.label.length > 160
      || typeof source.locator !== 'string' || source.locator.length > 512
      || typeof source.excerpt !== 'string' || source.excerpt.length > 800) throw new Error('The saved source selection is invalid.');
    ids.add(source.id);
  }
  return value as JourneyRequest;
}
export function readJourneyEnvelope(text: string): { request: JourneyRequest; request_digest: string } | null {
  if (typeof text !== 'string' || text.length > 16000) return null;
  const lines = text.split(/\r?\n/).filter(line => line.startsWith(REQUEST_MARKER));
  if (lines.length !== 1) return null;
  try {
    const value: unknown = JSON.parse(lines[0].slice(REQUEST_MARKER.length));
    if (!isObject(value) || !HASH.test(String(value.request_digest))) return null;
    return { request: checkedRequest(value.request), request_digest: value.request_digest as string };
  } catch { return null; }
}
export function readJourneyArtifact(text: string, request: JourneyRequest, digest: string): JourneyArtifact {
  if (typeof text !== 'string' || text.length > 64000) throw new Error('The reply exceeds the structured review limit.');
  const trimmed = text.trim();
  const fenced = /^```(?:json)?\s*\n([\s\S]*?)\n```$/.exec(trimmed);
  let value: unknown;
  try { value = JSON.parse(fenced ? fenced[1] : trimmed); }
  catch { throw new Error('This reply is not a complete JSON artifact. Edit the response below or ask Jeeves to return the requested structure.'); }
  if (!isObject(value) || value.schema_version !== ARTIFACT_SCHEMA || value.journey_id !== request.journey_id
    || value.request_digest !== digest || typeof value.title !== 'string' || !value.title.trim() || value.title.length > 160) {
    throw new Error('The reply does not match this journey request. Its identity and request fingerprint must match before review.');
  }
  // Validate the editor's shape before rendering model data. The server owns
  // the complete semantic schema; invalid data stays in the repairable JSON view.
  for (const key of ['claims', 'tasks', 'cards', 'items', 'steps']) {
    if (value[key] === undefined) continue;
    const rows = value[key];
    if (!Array.isArray(rows) || rows.length > 24 || rows.some(row => !isObject(row)
      || Object.keys(row).length > 12 || Object.values(row).some(part =>
        Array.isArray(part) ? part.length > 24 || part.some(item => typeof item !== 'string' || item.length > 8000)
          : part !== null && typeof part !== 'string' && typeof part !== 'number'
            || typeof part === 'string' && part.length > 8000))) throw new Error('The reply has invalid structured items. Repair its JSON before opening the form.');
  }
  for (const key of ['open_questions', 'completion_requirements']) {
    if (value[key] !== undefined && (!Array.isArray(value[key]) || (value[key] as unknown[]).length > 24
      || (value[key] as unknown[]).some(item => typeof item !== 'string' || item.length > 8000))) throw new Error('The reply has an invalid list. Repair its JSON before opening the form.');
  }
  return value as JourneyArtifact;
}
/** Exact compare-and-set: never truncate or silently overwrite authored text. */
export function stagedJourneyDraft(current: string, reviewed: string, prompt: string, mode: 'append' | 'replace'): string {
  if (current !== reviewed) throw new Error('Your message changed after preview. Review the latest draft before applying this journey.');
  if (mode === 'append' && current.split(/\r?\n/).some(line => line.startsWith(REQUEST_MARKER))) throw new Error('Your message already contains a guided request. Review Replace to keep one unambiguous journey per turn.');
  const value = mode === 'append' && current ? current + '\n\n' + prompt : prompt;
  if (value.length > 16000) throw new Error('The combined message exceeds 16,000 characters. Shorten the draft or choose Replace after reviewing it.');
  return value;
}
export function artifactText(artifact: JourneyArtifact): string {
  const lines = [artifact.title];
  const refs = (value: unknown) => Array.isArray(value) ? value.join(', ') : '';
  if (artifact.journey_id === 'research') {
    lines.push(String(artifact.summary || ''));
    for (const claim of (artifact.claims || []) as Record<string, unknown>[]) lines.push('• ' + claim.text + '\n  Proposed confidence: ' + claim.confidence + ' · Sources: ' + (refs(claim.source_ids) || 'none'));
    for (const question of (artifact.open_questions || []) as string[]) lines.push('Open question: ' + question);
  } else if (artifact.journey_id === 'plan') {
    for (const task of (artifact.tasks || []) as Record<string, unknown>[]) lines.push(String(task.id) + '. ' + task.title + '\n' + task.description + '\nEstimate: ' + task.estimate_minutes + ' minutes · Cost units: ' + task.cost + '\nDepends on: ' + (refs(task.depends_on) || 'none'));
  } else if (artifact.journey_id === 'study') {
    for (const card of (artifact.cards || []) as Record<string, unknown>[]) lines.push('Question: ' + card.question + '\nAnswer: ' + card.answer + '\nExplanation: ' + card.explanation);
  } else if (artifact.journey_id === 'creative') {
    for (const item of (artifact.items || []) as Record<string, unknown>[]) lines.push(Object.entries(item).map(([key, value]) => key + ': ' + (Array.isArray(value) ? value.join(' · ') : String(value))).join('\n'));
  } else {
    lines.push(String(artifact.goal || ''));
    for (const step of (artifact.steps || []) as Record<string, unknown>[]) lines.push('• ' + step.operation + ': ' + step.description);
    lines.push('Required evidence: ' + refs(artifact.completion_requirements));
  }
  return lines.filter(Boolean).join('\n\n');
}
/** A plan-only handoff keeps a stable reply origin even after its text is edited. */
export function studioHandoffSpec(projectId: string, preview: JourneyPreview, conversationId: string, messageId: string, mode: 'native' | 'original') {
  if (preview.journey_id !== 'studio' || !HASH.test(preview.artifact_digest)
    || [projectId, conversationId, messageId].some(value => !/^[A-Za-z0-9:_-]{1,160}$/.test(value))) throw new Error('The studio handoff identity is invalid.');
  const origin = `Jeeves journey: ${conversationId}/${messageId}/studio`;
  const goal = artifactText(preview.artifact) + '\n\n' + origin;
  if (goal.length > 7500) throw new Error('The reviewed studio goal exceeds 7,500 characters. Shorten its descriptions and check it again before saving.');
  return { projectId, origin, goal, mode, keyMaterial: canonicalJourneyJSON([projectId, preview.artifact_digest]) };
}
export function existingStudioHandoff(goals: readonly unknown[], spec: ReturnType<typeof studioHandoffSpec>): number | null {
  const matches = goals.map((goal, index) => ({ goal, index })).filter(({ goal }) => isObject(goal) && typeof goal.goal === 'string' && goal.goal.split(/\r?\n/).includes(spec.origin));
  if (!matches.length) return null;
  if (matches.length !== 1) throw new Error('More than one studio goal uses this reply origin. Inspect goal history before continuing.');
  const { goal, index } = matches[0];
  if (!isObject(goal) || goal.project_id !== spec.projectId || goal.goal !== spec.goal || goal.execution_mode !== 'plan'
    || goal.allow_edits !== false || goal.completion_mode !== spec.mode || !Array.isArray(goal.completion_requirements)
    || goal.completion_requirements.length !== 0) throw new Error('This reply already has a different studio goal or authorization. Inspect its original goal; no new goal was created.');
  return index;
}
