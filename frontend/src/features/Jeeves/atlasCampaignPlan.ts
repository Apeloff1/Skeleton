/**
 * Immutable, bounded operator research campaign compilation.
 *
 * This helper owns only browser form normalization. It cannot invent source
 * rights, execute a crawler, approve external text, issue model directives,
 * or retain documents. Backend Pydantic + current Mongo source policy remain
 * authoritative regardless of this convenience validation.
 */
import type { CrawlAtlasObjective } from '../../product/crawlerClient';

export type AtlasObjectiveDraft = {
  question: string;
  dimension: CrawlAtlasObjective['dimension'];
  stage: CrawlAtlasObjective['stage'];
  priority: string;
  requiredTerms: string;
  blockedTerms: string;
  passageTarget: string;
  independenceTarget: string;
  maxAgeMinutes: string;
};

export const MAX_ATLAS_OBJECTIVES = 8;
export const NEW_ATLAS_DRAFT: AtlasObjectiveDraft = Object.freeze({
  question: '', dimension: 'method', stage: 'verification',
  priority: '0.9', requiredTerms: '', blockedTerms: '',
  passageTarget: '1', independenceTarget: '1', maxAgeMinutes: '60',
});
const IDENTITY = /^operator-goal-0[1-8]$/;
const TERM = /^[a-z0-9_-]{2,48}$/;
const DIMENSIONS = new Set(['fact', 'method', 'timeline', 'source',
  'counterexample', 'implementation']);
const STAGES = new Set(['discovery', 'collection', 'verification', 'review']);

function whole(raw: string, low: number, high: number, field: string): number {
  if (typeof raw !== 'string' || !/^\d+$/.test(raw)) {
    throw new RangeError(field + ' requires a finite whole number.');
  }
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < low || value > high) {
    throw new RangeError(field + ' exceeds the authorized bounds.');
  }
  return value;
}
function normalizedTermList(raw: string, name: string): string[] {
  if (typeof raw !== 'string' || raw.length > 1024) {
    throw new RangeError(name + ' exceeds the term input bound.');
  }
  const terms = raw.trim() ? raw.trim().split(/[\s,]+/) : [];
  if (terms.length > 16 || terms.some(term => !TERM.test(term))) {
    throw new RangeError(name + ' requires up to 16 lowercase normalized terms.');
  }
  if (new Set(terms).size !== terms.length) {
    throw new RangeError(name + ' contains repeated terms.');
  }
  return terms;
}
function verifyExisting(queue: readonly CrawlAtlasObjective[]): void {
  if (!Array.isArray(queue) || queue.length > MAX_ATLAS_OBJECTIVES) {
    throw new RangeError('Operator objective campaign exceeds eight entries.');
  }
  const ids = new Set<string>();
  const questions = new Set<string>();
  for (const entry of queue) {
    if (!entry || !IDENTITY.test(entry.objective_id)
        || ids.has(entry.objective_id)
        || typeof entry.question !== 'string'
        || entry.question.length < 3 || entry.question.length > 512
        || entry.question.trim() !== entry.question
        || !DIMENSIONS.has(entry.dimension) || !STAGES.has(entry.stage)) {
      throw new RangeError('Campaign contains an invalid or duplicate objective.');
    }
    const key = entry.question.normalize('NFKC').toLocaleLowerCase('en-US');
    if (questions.has(key)) {
      throw new RangeError('The same research question is already queued.');
    }
    questions.add(key);
    ids.add(entry.objective_id);
  }
}
function nextIdentity(queue: readonly CrawlAtlasObjective[]): string {
  const occupied = new Set(queue.map(item => item.objective_id));
  for (let i = 1; i <= MAX_ATLAS_OBJECTIVES; i++) {
    const id = 'operator-goal-0' + i;
    if (!occupied.has(id)) return id;
  }
  throw new RangeError('The maximum of eight distinct objectives is reached.');
}

/** Turn one explicit operator entry into a deterministic request object. */
export function compileAtlasObjective(
  draft: AtlasObjectiveDraft,
  queue: readonly CrawlAtlasObjective[],
): CrawlAtlasObjective {
  verifyExisting(queue);
  if (!draft || typeof draft.question !== 'string') {
    throw new TypeError('An operator-authored question is required.');
  }
  const question = draft.question.trim();
  if (question.length < 3 || question.length > 512) {
    throw new RangeError('Research questions must be 3–512 characters.');
  }
  if (!DIMENSIONS.has(draft.dimension) || !STAGES.has(draft.stage)) {
    throw new RangeError('Unsupported objective dimension or research stage.');
  }
  const unique = question.normalize('NFKC').toLocaleLowerCase('en-US');
  if (queue.some(item =>
    item.question.normalize('NFKC').toLocaleLowerCase('en-US') === unique
  )) {
    throw new RangeError('The same research question is already queued.');
  }
  const priority = Number(draft.priority);
  if (typeof draft.priority !== 'string' || !/^(?:0(?:\.\d{1,3})?|1(?:\.0{1,3})?)$/.test(draft.priority)
      || !Number.isFinite(priority) || priority < 0 || priority > 1) {
    throw new RangeError('Priority must be a decimal from 0 to 1.');
  }
  const required = normalizedTermList(draft.requiredTerms, 'Required terms');
  const blocked = normalizedTermList(draft.blockedTerms, 'Excluded terms');
  if (required.some(term => blocked.includes(term))) {
    throw new RangeError('Required and excluded terms cannot overlap.');
  }
  const passageTarget = whole(draft.passageTarget, 1, 32, 'Passage target');
  const independenceTarget = whole(draft.independenceTarget, 1, 16, 'Independent source groups');
  const ageMinutes = whole(draft.maxAgeMinutes, 1, 1440, 'Capture age');
  const maxAgeSeconds = ageMinutes * 60;
  return {
    objective_id: nextIdentity(queue),
    question, dimension: draft.dimension, stage: draft.stage,
    priority, minimum_reviewable_passages: passageTarget,
    minimum_attested_groups: independenceTarget,
    max_source_age_seconds: maxAgeSeconds,
    required_terms: required, blocked_terms: blocked,
  };
}

/** Immutable enqueue: no silent removal, truncation or hidden goal edits. */
export function enqueueAtlasObjective(
  queue: readonly CrawlAtlasObjective[],
  draft: AtlasObjectiveDraft,
): CrawlAtlasObjective[] {
  if (queue.length >= MAX_ATLAS_OBJECTIVES) {
    throw new RangeError('Remove an objective before adding more than eight.');
  }
  return [...queue, compileAtlasObjective(draft, queue)];
}

/** Return exactly the visible queued objectives plus the current draft.
 * A populated draft cannot be silently discarded when the user clicks Run.
 */
export function compileAtlasCampaign(
  queue: readonly CrawlAtlasObjective[],
  draft: AtlasObjectiveDraft,
): CrawlAtlasObjective[] {
  verifyExisting(queue);
  if (draft.question.trim()) return enqueueAtlasObjective(queue, draft);
  if (!queue.length) {
    throw new RangeError('Enter a research question or queue an objective.');
  }
  return [...queue];
}

/** Removing a goal cannot mutate the source session or preserve stale results. */
export function removeAtlasObjective(
  queue: readonly CrawlAtlasObjective[],
  objectiveId: string,
): CrawlAtlasObjective[] {
  verifyExisting(queue);
  if (!IDENTITY.test(objectiveId) || !queue.some(x => x.objective_id === objectiveId)) {
    throw new RangeError('No matching operator objective exists in the campaign.');
  }
  return queue.filter(item => item.objective_id !== objectiveId);
}
