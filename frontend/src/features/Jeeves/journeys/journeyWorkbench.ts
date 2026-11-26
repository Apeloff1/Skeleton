/** Reviewed journey artifacts reuse the existing device-local Workbench writer. */
import type { Command } from '../workbench/domain';
import type { CaptureInput } from '../workbench/capture';
import type { WorkbenchStore } from '../workbench/WorkbenchStore';
import { LIMITS } from '../workbench/types';
import type { Workbench } from '../workbench/types';
import { artifactText, checkedRequest, HASH, isObject } from './journeyDraft';
import type { JourneyPreview, JourneyRequest } from './journeyDraft';

type Origin = { conversationId: string; messageId: string; request: JourneyRequest };
export type JourneyCommitPlan = Readonly<{
  workbenchId: string; workbenchRevision: number;
  projectId: string; projectRevision: number; projectTitle: string;
  preview: JourneyPreview; origin: Origin; marker: string;
}>;
export type JourneyCommitResult = Readonly<{
  status: 'saved' | 'unsaved' | 'refused'; revision: number | null; message: string;
}>;

const ID = /^[A-Za-z0-9:_-]{1,160}$/;
const ITEM_ID = /^[A-Za-z][A-Za-z0-9_-]{0,31}$/;
function fail(message: string): never { throw new Error(message); }
function text(value: unknown, maximum: number, label: string, empty = false): string {
  if (typeof value !== 'string' || value.length > maximum || !empty && !value.trim() ||
      /[\u0000-\u0008\u000b-\u001f\u007f]/.test(value)) fail(`${label} exceeds its reviewed text bounds.`);
  return value;
}
function list(value: unknown, maximum: number, label: string, minimum = 0): unknown[] {
  if (!Array.isArray(value) || value.length < minimum || value.length > maximum) fail(`${label} exceeds its reviewed item bounds.`);
  return value;
}
function row(value: unknown): Record<string, unknown> {
  if (!isObject(value)) fail('A reviewed artifact item is invalid.');
  return value;
}
function freeze<T>(value: T): T {
  if (value && typeof value === 'object') {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
}
function sourceIds(value: unknown, request: JourneyRequest): void {
  const refs = list(value, 8, 'Source references');
  if (new Set(refs).size !== refs.length || refs.some(id =>
    typeof id !== 'string' || !request.source_refs.some(source => source.id === id))) {
    fail('The artifact cites a source outside the reviewed request.');
  }
}
function originMarker(origin: Origin, journeyId: string): string {
  if (typeof origin.conversationId !== 'string' || !ID.test(origin.conversationId) ||
      typeof origin.messageId !== 'string' || !ID.test(origin.messageId)) fail('The journey message identity is invalid.');
  return `Jeeves journey: ${origin.conversationId}/${origin.messageId}/${journeyId}`;
}
function duplicate(state: Workbench, marker: string): boolean {
  const contains = (value: string) => value.split(/\r?\n/).includes(marker);
  return state.tasks.some(task => contains(task.description)) ||
    state.notes.some(note => contains(note.body)) ||
    state.cards.some(card => contains(card.explanation));
}
function sourceText(request: JourneyRequest): string {
  return request.source_refs.length ? 'Sources supplied for this request (support remains unverified):\n' +
    request.source_refs.map(source => `[${source.id}] ${source.label}\nLocation: ${source.locator || 'Not supplied'}`).join('\n\n') :
    'No external source references were supplied for this request.';
}

function commandsFor(preview: JourneyPreview, origin: Origin, projectId: string, marker: string): {
  commands: Command[]; dependencies: Record<number, number[]>; capture?: CaptureInput;
} {
  const artifact = preview.artifact;
  const request = origin.request;
  const commands: Command[] = [];
  const dependencies: Record<number, number[]> = {};
  if (preview.journey_id === 'studio') fail('Open the existing Studio goal form to review its owned project, budgets and permissions.');
  if (preview.journey_id === 'plan') {
    const tasks = list(artifact.tasks, 24, 'Plan tasks', 1).map(row);
    const ids = tasks.map(task => text(task.id, 32, 'Task identifier'));
    if (ids.some(id => !ITEM_ID.test(id)) || new Set(ids).size !== ids.length) fail('Plan task identifiers are invalid or repeated.');
    let effort = 0;
    let cost = 0;
    tasks.forEach((task, index) => {
      const title = text(task.title, LIMITS.title, 'Task title');
      const body = text(task.description, 2000, 'Task description');
      if (!Number.isSafeInteger(task.estimate_minutes) || Number(task.estimate_minutes) < 1 || Number(task.estimate_minutes) > 10080 ||
          !Number.isSafeInteger(task.cost) || Number(task.cost) < 0 || Number(task.cost) > 1000000) fail('Plan effort or cost is invalid.');
      effort += Number(task.estimate_minutes); cost += Number(task.cost);
      const refs = list(task.depends_on, 23, 'Task dependencies');
      if (new Set(refs).size !== refs.length || refs.some(id => typeof id !== 'string' || !ids.includes(id) || id === ids[index])) fail('Plan dependencies are invalid or repeated.');
      dependencies[index] = refs.map(id => ids.indexOf(id as string));
      commands.push({ type: 'task.create', input: { projectId, title,
        description: `${body}\n\nProposed cost units: ${task.cost}\n\n${marker}`,
        estimateMinutes: Number(task.estimate_minutes), priority: 'normal', status: 'inbox', tags: ['jeeves-journey', 'plan'] } });
    });
    const active = new Set<number>(); const done = new Set<number>();
    const visit = (index: number): void => {
      if (active.has(index)) fail('Plan dependencies contain a cycle.');
      if (done.has(index)) return;
      active.add(index); dependencies[index].forEach(visit); active.delete(index); done.add(index);
    };
    tasks.forEach((_, index) => visit(index));
    if (preview.checks.within_time_budget === false || preview.checks.within_cost_budget === false ||
        effort > Number(request.options.time_budget_minutes ?? 240) || cost > Number(request.options.cost_budget ?? 0)) {
      fail('This plan exceeds the reviewed effort or cost budget. Revise the request before applying it.');
    }
  } else if (preview.journey_id === 'study') {
    list(artifact.cards, 20, 'Study cards', 1).map(row).forEach(card => {
      const question = text(card.question, 2000, 'Card question');
      const answer = text(card.answer, 4000, 'Card answer');
      const explanation = text(card.explanation, 4000, 'Card explanation');
      const choices = list(card.choices, 6, 'Answer choices').map(choice => text(choice, 1000, 'Answer choice'));
      if (new Set(choices).size !== choices.length || choices.length === 1 ||
          choices.length && request.options.format === 'short_answer' ||
          !choices.length && request.options.format === 'multiple_choice' ||
          choices.length && (!Number.isSafeInteger(card.correct_choice) || Number(card.correct_choice) < 0 ||
            Number(card.correct_choice) >= choices.length || answer !== choices[Number(card.correct_choice)]) ||
          !choices.length && card.correct_choice !== null) fail('Study answer choices do not match the reviewed answer.');
      sourceIds(card.source_ids, request);
      const fullQuestion = choices.length ? `${question}\n\n${choices.map((choice, index) => `${String.fromCharCode(65 + index)}. ${choice}`).join('\n')}` : question;
      const fullExplanation = `${explanation}\n\n${sourceText(request)}\n\n${marker}`;
      text(fullQuestion, LIMITS.summary, 'Question with answer choices');
      text(fullExplanation, LIMITS.answer, 'Card explanation with provenance');
      commands.push({ type: 'card.create', input: { projectId, question: fullQuestion, answer,
        explanation: fullExplanation, tags: ['jeeves-journey', 'study'] } });
    });
  } else {
    if (preview.journey_id === 'research') {
      text(artifact.summary, 4000, 'Research summary');
      list(artifact.claims, 12, 'Research claims', 1).map(row).forEach(claim => {
        text(claim.text, 2000, 'Research claim'); sourceIds(claim.source_ids, request);
        if (!['supported', 'uncertain', 'contradicted'].includes(String(claim.confidence)) ||
            claim.confidence !== 'uncertain' && !(claim.source_ids as unknown[]).length) fail('Research claim confidence or sources are invalid.');
      });
      list(artifact.open_questions, 12, 'Open questions').forEach(question => text(question, 1000, 'Open question'));
    } else if (preview.journey_id === 'creative') {
      if (!['story', 'cast', 'quests', 'scene'].includes(String(artifact.artifact_kind)) ||
          artifact.artifact_kind !== request.options.artifact) fail('The creative artifact does not match the reviewed kind.');
      const items = list(artifact.items, 12, 'Creative items', 1).map(row);
      const ids = new Set<string>();
      items.forEach(item => {
        const id = text(item.id, 32, 'Creative item identifier');
        if (!ITEM_ID.test(id) || ids.has(id) || Object.keys(item).length > 12) fail('Creative items have invalid or repeated identifiers.');
        ids.add(id);
        Object.entries(item).forEach(([key, value]) => {
          if (Array.isArray(value)) list(value, 12, key).forEach(part => text(part, 1000, key));
          else text(value, key === 'title' || key === 'name' ? 160 : 2000, key);
        });
      });
    } else fail('This journey cannot be saved to Workbench.');
    const body = `${artifactText(artifact)}\n\n${sourceText(request)}\n\n${marker}`;
    text(body, LIMITS.body, 'Note with source provenance');
    return { commands, dependencies, capture: { projectId, title: artifact.title, text: body,
      kind: preview.journey_id === 'research' ? 'reference' : 'note',
      conversationId: origin.conversationId, conversationTitle: artifact.title,
      messageId: origin.messageId, role: 'assistant', model: null } };
  }
  return { commands, dependencies };
}

export function prepareJourneyCommit(state: Workbench, projectId: string, preview: JourneyPreview, origin: Origin): JourneyCommitPlan {
  checkedRequest(origin.request);
  if (!state || typeof state.id !== 'string' || !ID.test(state.id) || !Number.isSafeInteger(state.revision)) fail('Workbench state is invalid.');
  const project = state.projects.find(item => item.id === projectId);
  if (!project || project.status === 'archived') fail('Choose an existing active Workbench project.');
  if (!preview || preview.schema_version !== 'skeleton.ai.workflow_preview.v1' ||
      preview.execution_authorized !== false || !HASH.test(preview.request_digest) || !HASH.test(preview.artifact_digest) ||
      preview.journey_id !== origin.request.journey_id || !isObject(preview.checks) ||
      preview.checks.structure_valid !== true || preview.checks.execution_performed !== false ||
      preview.checks.factual_accuracy_verified !== false || !isObject(preview.artifact) ||
      preview.artifact.schema_version !== 'skeleton.ai.workflow_artifact.v1' ||
      preview.artifact.journey_id !== preview.journey_id || preview.artifact.request_digest !== preview.request_digest ||
      !Array.isArray(preview.warnings) || preview.warnings.some(warning => typeof warning !== 'string')) fail('Review a valid server-normalized journey preview before saving.');
  text(preview.artifact.title, LIMITS.title, 'Artifact title');
  const encoded = JSON.stringify({ preview, origin });
  if (new TextEncoder().encode(encoded).byteLength > 96 * 1024) fail('The reviewed journey exceeds its transfer bounds.');
  const detached = JSON.parse(encoded) as { preview: JourneyPreview; origin: Origin };
  const marker = originMarker(detached.origin, detached.preview.journey_id);
  if (duplicate(state, marker)) fail('This journey reply has already been applied. Review its existing Workbench records.');
  const work = commandsFor(detached.preview, detached.origin, projectId, marker);
  const tasks = work.commands.filter(command => command.type === 'task.create').length;
  const cards = work.commands.filter(command => command.type === 'card.create').length;
  if (state.tasks.length + tasks > LIMITS.tasks || state.cards.length + cards > LIMITS.cards ||
      work.capture && (state.notes.length >= LIMITS.notes ||
        state.sources.length >= LIMITS.sources && !state.sources.some(source => source.projectId === projectId &&
          source.kind === 'conversation' && source.locator === `jeeves-conversation:${encodeURIComponent(origin.conversationId)}#${encodeURIComponent(origin.messageId)}`))) {
    fail('Workbench capacity would be exceeded. Export and remove unused records before saving.');
  }
  return freeze({ workbenchId: state.id, workbenchRevision: state.revision,
    projectId, projectRevision: project.revision, projectTitle: project.title,
    preview: detached.preview, origin: detached.origin, marker });
}

/** Call only from the explicit reviewed-apply UI event. No generation or studio action runs here. */
export async function commitJourneyArtifact(store: WorkbenchStore, plan: JourneyCommitPlan, stillCurrent: () => boolean): Promise<JourneyCommitResult> {
  const refuse = (message: string): JourneyCommitResult => ({ status: 'refused', revision: null, message });
  let appliedRevision: number | null = null;
  try {
    if (!stillCurrent()) return refuse('Your account changed. Reopen the journey before applying it.');
    const snapshot = store.getSnapshot();
    if (!snapshot.ready || snapshot.saveStatus === 'conflict' || snapshot.saveStatus === 'failed') return refuse('Workbench is not ready for editing. Resolve its storage state first.');
    if (snapshot.state.id !== plan.workbenchId || snapshot.state.revision !== plan.workbenchRevision ||
        snapshot.state.projects.find(project => project.id === plan.projectId)?.revision !== plan.projectRevision) {
      return refuse('Workbench or project changed after preview. Review the latest destination before applying.');
    }
    prepareJourneyCommit(snapshot.state, plan.projectId, plan.preview, plan.origin);
    const work = commandsFor(plan.preview, plan.origin, plan.projectId, plan.marker);
    if (!stillCurrent()) return refuse('Your account changed. No records were applied.');
    const applied = work.capture ? store.capture(work.capture) : store.dispatchBatch(work.commands, work.dependencies);
    if (!applied) return refuse(store.getSnapshot().notice || 'The atomic Workbench update was refused.');
    const revision = store.getSnapshot().state.revision;
    appliedRevision = revision;
    await store.settled();
    if (!stillCurrent()) return { status: 'unsaved', revision, message: 'The account changed after the local update. Inspect Workbench before attempting another apply.' };
    if (store.getSnapshot().saveStatus !== 'saved') return { status: 'unsaved', revision,
      message: 'Records were added in memory, but storage has not confirmed the save. Resolve Workbench storage; do not reapply.' };
    return { status: 'saved', revision, message: 'Reviewed journey saved to this device’s Workbench. Its content remains unverified.' };
  } catch (error) {
    if (appliedRevision !== null) return { status: 'unsaved', revision: appliedRevision,
      message: 'The local update was applied, but its final state could not be confirmed. Inspect Workbench; do not reapply.' };
    return refuse(error instanceof Error ? error.message : 'The reviewed journey could not be applied.');
  }
}
