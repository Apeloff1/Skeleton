/** Explicit chat -> workbench task proposal adapter.
 *
 * Assistant output is untrusted text, not a command or user authorization.
 * Only visible checklist/numbered steps become a bounded preview. The shared
 * WorkbenchStore is the sole writer; every commit is user-initiated, atomic,
 * revision-fenced, undoable and checked for durable local persistence.
 */
import { LIMITS } from './types';
import type { Workbench } from './types';
import type { Command } from './domain';
import type { WorkbenchStore } from './WorkbenchStore';

export const CHAT_TASK_LIMIT = 12;
const TASK_LINE = /^ {0,3}(?:[-*•]|\d{1,2}[.)])\s+(?:\[[ xX]\]\s+)?(.+?)\s*$/;
const SOURCE_ID = /^[A-Za-z0-9:_-]{1,160}$/;
const SOURCE_LABEL = 'Jeeves chat source: ';

export class ChatTaskActionError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ChatTaskActionError';
  }
}

export type ChatTaskDraft = Readonly<{
  ordinal: number;
  title: string;
  source: string;
}>;

export type ChatTaskPlan = Readonly<{
  workbenchId: string;
  workbenchRevision: number;
  projectId: string;
  projectRevision: number;
  projectTitle: string;
  conversationId: string;
  messageId: string;
  steps: readonly ChatTaskDraft[];
}>;

export type ChatTaskCommit = Readonly<{
  status: 'saved' | 'unsaved' | 'refused';
  revision: number | null;
  message: string;
}>;

function canonicalId(value: string): string {
  if (typeof value !== 'string' || !SOURCE_ID.test(value)) {
    throw new ChatTaskActionError('Chat message identity is invalid.');
  }
  return value;
}

function sourceFor(conversationId: string, messageId: string, ordinal: number): string {
  return SOURCE_LABEL + canonicalId(conversationId) + '/' + canonicalId(messageId) + '/' + ordinal;
}

/** No instructions within code blocks, quotes, or prose can become actions. */
export function extractChatTaskTitles(response: string): string[] {
  if (typeof response !== 'string' || response.length > 16000) return [];
  let fenced = false;
  const titles: string[] = [];
  const seen = new Set<string>();
  for (const line of response.split(/\r?\n/)) {
    if (/^\s*(`{3,}|~{3,})/.test(line)) {
      fenced = !fenced;
      continue;
    }
    if (fenced || /^\s*>/.test(line)) continue;
    const matched = TASK_LINE.exec(line);
    if (!matched) continue;
    const title = matched[1]
      .replace(/^\*{1,2}(.*?)\*{1,2}$/, '$1')
      .replace(/\s+/g, ' ').trim();
    if (!title || title.length > LIMITS.title || /[\u0000-\u001f\u007f]/.test(title)) continue;
    const key = title.toLocaleLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    titles.push(title);
    if (titles.length > CHAT_TASK_LIMIT) return [];
  }
  return titles;
}

/** Rejects stale, archived, full, or previously imported destinations. */
export function prepareChatTasks(
  state: Workbench,
  projectId: string,
  response: string,
  conversationId: string,
  messageId: string,
): ChatTaskPlan {
  canonicalId(conversationId);
  canonicalId(messageId);
  if (typeof state?.id !== 'string' || !Number.isSafeInteger(state.revision)) {
    throw new ChatTaskActionError('Workbench state is invalid.');
  }
  const project = state.projects.find(item => item.id === projectId);
  if (!project) throw new ChatTaskActionError('Choose an existing workbench project.');
  if (project.status === 'archived') throw new ChatTaskActionError('Archived projects cannot accept tasks.');
  const titles = extractChatTaskTitles(response);
  if (!titles.length) throw new ChatTaskActionError('No usable numbered or bulleted steps were found.');
  if (state.tasks.length + titles.length > LIMITS.tasks) {
    throw new ChatTaskActionError('Workbench task capacity would be exceeded.');
  }
  const steps = titles.map((title, index) => ({
    ordinal: index + 1,
    title,
    source: sourceFor(conversationId, messageId, index + 1),
  }));
  if (steps.some(step => state.tasks.some(task =>
    task.projectId === projectId && task.description.includes(step.source)
  ))) {
    throw new ChatTaskActionError('Some steps from this reply already exist in this project. Review its task board.');
  }
  return {
    workbenchId: state.id,
    workbenchRevision: state.revision,
    projectId: project.id,
    projectRevision: project.revision,
    projectTitle: project.title,
    conversationId,
    messageId,
    steps,
  };
}

export function checkedTaskCommands(state: Workbench, plan: ChatTaskPlan): Command[] {
  if (state.id !== plan.workbenchId || state.revision !== plan.workbenchRevision) {
    throw new ChatTaskActionError('Workbench changed after preview. Review the updated project before applying.');
  }
  const project = state.projects.find(item => item.id === plan.projectId);
  if (!project || project.revision !== plan.projectRevision || project.status === 'archived') {
    throw new ChatTaskActionError('Project changed after preview. Reopen the proposal.');
  }
  if (!plan.steps.length || plan.steps.length > CHAT_TASK_LIMIT ||
      state.tasks.length + plan.steps.length > LIMITS.tasks) {
    throw new ChatTaskActionError('Task batch is invalid or exceeds capacity.');
  }
  const sources = new Set<string>();
  let previousOrdinal = 0;
  return plan.steps.map(step => {
    if (!Number.isSafeInteger(step.ordinal) || step.ordinal <= previousOrdinal ||
        step.ordinal > CHAT_TASK_LIMIT || typeof step.title !== 'string' ||
        !step.title.trim() || step.title.length > LIMITS.title ||
        typeof step.source !== 'string' ||
        step.source !== sourceFor(plan.conversationId, plan.messageId, step.ordinal) ||
        sources.has(step.source) || /[\r\n\u0000-\u001f\u007f]/.test(step.title)) {
      throw new ChatTaskActionError('Task proposal has invalid or duplicate fields.');
    }
    if (state.tasks.some(task => task.projectId === plan.projectId &&
      task.description.includes(step.source))) {
      throw new ChatTaskActionError('This chat proposal has already been applied.');
    }
    previousOrdinal = step.ordinal;
    sources.add(step.source);
    return {
      type: 'task.create' as const,
      input: {
        projectId: plan.projectId,
        title: step.title,
        description: 'Suggested by Jeeves chat. Review and define acceptance criteria before execution.\n\n' +
          step.source,
        priority: 'normal' as const,
        status: 'inbox' as const,
        estimateMinutes: 0,
      },
    };
  });
}

/** Confirmation must be a direct user UI event, never a model/tool callback. */
export async function commitChatTasks(store: WorkbenchStore, plan: ChatTaskPlan): Promise<ChatTaskCommit> {
  const snapshot = store.getSnapshot();
  if (!snapshot.ready || snapshot.saveStatus === 'conflict' || snapshot.saveStatus === 'failed') {
    return { status: 'refused', revision: null, message: 'Workbench is not ready for editing.' };
  }
  let commands: Command[];
  try {
    commands = checkedTaskCommands(snapshot.state, plan);
  } catch (error) {
    return {
      status: 'refused', revision: null,
      message: error instanceof Error ? error.message : 'Proposal is invalid.',
    };
  }
  if (!store.dispatchBatch(commands)) {
    return { status: 'refused', revision: null, message: store.getSnapshot().notice || 'Atomic task update refused.' };
  }
  const revision = store.getSnapshot().state.revision;
  await store.settled();
  const status = store.getSnapshot().saveStatus;
  if (status !== 'saved') {
    return {
      status: 'unsaved', revision,
      message: 'Tasks were added in memory, but storage has not confirmed the save. Open Workbench to resolve it; do not reapply.',
    };
  }
  return {
    status: 'saved', revision,
    message: 'Tasks saved to Workbench. They remain proposed work, not completed game changes.',
  };
}

/** Only undo the exact latest local transaction; never roll back unrelated edits. */
export async function undoChatTasks(store: WorkbenchStore, appliedRevision: number): Promise<boolean> {
  const before = store.getSnapshot();
  if (!before.ready || before.saveStatus !== 'saved' || !before.undoAvailable ||
      before.state.revision !== appliedRevision) return false;
  store.undo();
  await store.settled();
  return store.getSnapshot().saveStatus === 'saved';
}
