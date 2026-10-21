/** Typed authenticated source-book lessons and host-approved practice for Jeeves. */
import api, { type ApiResult } from '../utils/apiClient';
import { authHeaders } from '../auth/gameforgeAuth';
import { chatApiError } from './chatErrors';
import { learningRequestKey } from './gameLearningClient';

const BOOKS = '/api/game-frontier-authoring/curriculum';
const STUDIO = '/api/game-studio-tools/execute';
const SHA = /^[a-f0-9]{64}$/;
export type BookGeneration = 'worldline'|'phase'|'campaign'|'chronicle'|'epoch'|'saga'|'epic';
export const BOOK_GENERATIONS: readonly BookGeneration[] = [
  'worldline','phase','campaign','chronicle','epoch','saga','epic',
] as const;

function opts(key?: string) {
  return { headers: authHeaders(), retries: 0, timeoutMs: 40000, idempotencyKey: key };
}
async function value<T>(response: Promise<ApiResult<T>>, message: string): Promise<T> {
  const result = await response;
  if (!result.ok || !result.data) throw chatApiError(result, message);
  return result.data;
}
function indexKey(generation: BookGeneration, index: number): string {
  if (!BOOK_GENERATIONS.includes(generation) || !Number.isSafeInteger(index) || index < 0)
    throw new Error('Choose a valid, exact source-backed book reference.');
  return encodeURIComponent(generation) + '/' + index;
}
export type BookReference = {
  schema: 'skeleton.jeeves.forge_book_curriculum.v1';
  ref: string; generation: BookGeneration; index: number;
  identity: string[]; path: string; unrendered: true; trained: false;
};
export type CurriculumCatalog = {
  schema: 'skeleton.jeeves.forge_book_curriculum.v1';
  book_count: number;
  indexed_not_materialized: true;
  curriculum_levels: Array<{generation: BookGeneration; book_count: number;
    prerequisites: string[]; competencies: string[];
    first_reference: string; last_reference: string}>;
  provider_training: 'not_started'; weight_promoted: false;
};
export type CurriculumLesson = {
  schema: 'skeleton.jeeves.forge_book_curriculum.v1';
  reference: BookReference; parent_reference: string|null;
  questions: Array<{question_id: number; prompt: string; type: 'exact_source_axis'}>;
  source_exercise_action: string;
  mastery_threshold: number; self_study_not_weight_training: true;
};
export type CurriculumAssessment = {
  schema: 'skeleton.jeeves.forge_curriculum_assessment.v1';
  ref: string; answered: number; passed: number; checks: boolean[];
  score: number; mastery_earned: boolean; practical_preview_verified: false;
  weight_trained: false; receipt_sha256: string;
};
export type CurriculumManifest = {
  schema: 'skeleton.jeeves.forge_book_manifest.v1';
  reference: string; path: string; source_dimensions: string[];
  markdown: string; content_sha256: string; bytes: number;
  content_realized: true; weight_trained: false;
};
export type CurriculumPath = {
  schema: 'skeleton.jeeves.forge_learning_path.v1';
  target: string; course_levels: number; curriculum_sha256: string;
  modules: Array<{level: number; book: string; generation: BookGeneration;
    operation: string; learning_objectives: string[];
    practical_checkpoints: string[]; theory_assessed: false;
    practical_evidence_verified: false; lesson_sha256: string}>;
  weights_promoted: false; requires_independent_practical_receipts: true;
};
export type CurriculumWorklist = {
  schema: 'skeleton.jeeves.forge_study_worklist.v1';
  selected_generation: BookGeneration; start_index: number;
  sessions: number; issued_jobs: 0; completed_lessons: 0;
  worklist_sha256: string;
  tasks: Array<{session: number; book: string; exact_operation: string;
    status: 'not_started'}>;
};
export type CurriculumToolResponse = {
  schema_version: 'skeleton.game.studio_tool_receipt.v1';
  operation: string; project_id: string; command_digest: string;
  result_digest: string;
  result: {
    schema: string; project_id?: string;
    source_sha256: string; candidate_sha256?: string;
    expected_revision?: number; operations: string[]; books: string[];
    batch_receipt?: {receipt_sha256: string; actually_changed: boolean};
    measured_changed?: boolean; persisted: boolean;
    saved_source_sha256?: string; saved_revision?: number;
    requires_explicit_operator_approval?: boolean;
    neural_training_complete?: false;
    trained_weights?: false;
  };
};

export async function readCurriculumCatalog(): Promise<CurriculumCatalog> {
  const doc = await value(api.get<CurriculumCatalog>(BOOKS, opts()),
    'Jeeves source curriculum is unavailable.');
  if (!doc || doc.schema !== 'skeleton.jeeves.forge_book_curriculum.v1'
      || doc.curriculum_levels?.length !== 7
      || !Number.isSafeInteger(doc.book_count)
      || doc.curriculum_levels.some((row, index) =>
        row.generation !== BOOK_GENERATIONS[index] || !Number.isSafeInteger(row.book_count))
      || doc.weight_promoted !== false)
    throw new Error('The seven-level source library failed protocol validation.');
  return doc;
}

export async function readCurriculumLesson(
  generation: BookGeneration, index: number,
): Promise<CurriculumLesson> {
  const key = indexKey(generation, index);
  const lesson = await value(api.get<CurriculumLesson>(BOOKS + '/lesson/' + key, opts()),
    'Could not load an exact original-game book lesson.');
  if (!lesson || lesson.schema !== 'skeleton.jeeves.forge_book_curriculum.v1'
      || lesson.reference?.ref !== 'forgebook:' + generation + ':' + index
      || lesson.questions?.length !== lesson.reference.identity.length
      || !/^([a-z]+_)[a-z_]+$/.test(lesson.source_exercise_action))
    throw new Error('The selected original-game lesson is not source-grounded.');
  return lesson;
}

export async function readCurriculumPath(
  generation: BookGeneration, index: number,
): Promise<CurriculumPath> {
  const path = await value(api.get<CurriculumPath>(
    BOOKS + '/path/' + indexKey(generation, index), opts()),
    'Could not derive the prerequisite learning path.');
  if (!path || path.schema !== 'skeleton.jeeves.forge_learning_path.v1'
      || !SHA.test(path.curriculum_sha256) ||
      path.target !== 'forgebook:' + generation + ':' + index ||
      path.course_levels !== BOOK_GENERATIONS.indexOf(generation) + 1 ||
      path.modules?.length !== path.course_levels || path.weights_promoted !== false)
    throw new Error('Jeeves prerequisite path failed integrity validation.');
  return path;
}

export async function readCurriculumWorklist(
  generation: BookGeneration, index: number, sessions = 8,
): Promise<CurriculumWorklist> {
  if (!Number.isSafeInteger(sessions) || sessions < 1 || sessions > 16)
    throw new Error('Curriculum sessions must be 1 through 16.');
  const doc = await value(api.get<CurriculumWorklist>(
    BOOKS + '/worklist?generation=' + generation + '&index=' + index +
    '&sessions=' + sessions, opts()), 'Could not prepare Jeeves study sessions.');
  if (!doc || doc.schema !== 'skeleton.jeeves.forge_study_worklist.v1'
      || !SHA.test(doc.worklist_sha256) || doc.tasks?.length !== sessions ||
      doc.issued_jobs !== 0 || doc.completed_lessons !== 0)
    throw new Error('Curriculum worklist is not trustworthy.');
  return doc;
}

export async function readCurriculumManifest(
  generation: BookGeneration, index: number,
): Promise<CurriculumManifest> {
  const book = await value(api.get<CurriculumManifest>(
    BOOKS + '/manifest/' + indexKey(generation, index), opts()),
    'Could not render the referenced manuscript.');
  if (!book || book.schema !== 'skeleton.jeeves.forge_book_manifest.v1'
      || book.reference !== 'forgebook:' + generation + ':' + index
      || !SHA.test(book.content_sha256) || !book.content_realized
      || typeof book.markdown !== 'string' || !book.markdown.length
      || book.markdown.length > 512000 || !Number.isSafeInteger(book.bytes))
    throw new Error('Materialized original-game book violates source integrity.');
  return book;
}

export async function assessCurriculumLesson(
  generation: BookGeneration, index: number, answers: string[],
): Promise<CurriculumAssessment> {
  const result = await value(api.post<CurriculumAssessment>(
    BOOKS + '/assess/' + indexKey(generation, index), {answers},
    opts(learningRequestKey('forge-curriculum-assess'))),
    'Jeeves could not assess this specific source-book lesson.');
  if (!result || result.schema !== 'skeleton.jeeves.forge_curriculum_assessment.v1'
      || !SHA.test(result.receipt_sha256)
      || result.ref !== 'forgebook:' + generation + ':' + index
      || result.answered !== answers.length || result.weight_trained !== false
      || result.practical_preview_verified !== false)
    throw new Error('Jeeves curriculum assessment receipt was malformed.');
  return result;
}

export type BookRefRequest = {generation: BookGeneration; index: number};
export type CurriculumAction = 'game.studio.curriculum.automation.plan' |
  'game.studio.curriculum.automation.preview' |
  'game.studio.curriculum.automation.commit';

export async function executeCurriculumAction(
  operation: CurriculumAction, projectId: string, books: BookRefRequest[],
  parameters: Record<string, unknown>,
  source?: {expected_revision: number; expected_sha256: string},
  approvedCandidate?: string,
): Promise<CurriculumToolResponse['result']> {
  if (!projectId || projectId.length > 128 || !Array.isArray(books)
      || books.length < 1 || books.length > 4
      || books.some(b => !BOOK_GENERATIONS.includes(b.generation)
        || !Number.isSafeInteger(b.index) || b.index < 0))
    throw new Error('Select a current project and 1–4 exact source books.');
  if (operation !== 'game.studio.curriculum.automation.plan'
      && (!source || !SHA.test(source.expected_sha256)
        || !Number.isSafeInteger(source.expected_revision)))
    throw new Error('Refresh the live source revision before preview or commit.');
  if (operation === 'game.studio.curriculum.automation.commit'
      && (!approvedCandidate || !SHA.test(approvedCandidate)))
    throw new Error('Preview and explicitly approve an identical source digest first.');
  const payload: Record<string, unknown> = {books, parameters};
  if (source) Object.assign(payload, source);
  if (operation === 'game.studio.curriculum.automation.commit') {
    payload.approved_candidate_sha256 = approvedCandidate;
    payload.idempotency_key = learningRequestKey('jeeves-source-book-approval');
  }
  const response = await value(api.post<CurriculumToolResponse>(STUDIO,
    {operation, project_id: projectId, payload},
    opts(operation.endsWith('.commit')
      ? String(payload.idempotency_key) : undefined)),
    'Jeeves could not execute the authorized book-based work.');
  if (!response || response.schema_version !== 'skeleton.game.studio_tool_receipt.v1'
      || response.operation !== operation || response.project_id !== projectId
      || !SHA.test(response.command_digest) || !SHA.test(response.result_digest)
      || !SHA.test(response.result?.source_sha256)
      || !Array.isArray(response.result?.books)
      || response.result.books.length !== books.length
      || (operation === 'game.studio.curriculum.automation.commit'
        && (response.result.persisted !== true
            || response.result.saved_source_sha256 !== approvedCandidate))
      || (operation !== 'game.studio.curriculum.automation.commit'
        && response.result.persisted !== false))
    throw new Error('Host-side curriculum work receipt did not match its exact command.');
  return response.result;
}
