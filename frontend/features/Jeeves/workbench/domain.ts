import { LIMITS, PROJECT_COLORS } from './types';
import type {
  ActivityEvent,
  CardSchedule,
  ChecklistItem,
  Entity,
  FocusSession,
  MutationContext,
  Note,
  Preferences,
  Project,
  ReviewGrade,
  SavedPrompt,
  Source,
  StudyCard,
  Task,
  TaskStatus,
  Workbench,
} from './types';
import {
  assertId,
  assertInteger,
  assertText,
  normalizeIds,
  normalizeTags,
  validateWorkbench,
  WorkbenchError,
} from './validation';
import { inspectIntegrity } from './integrity';
import { dependants, isTerminal, unmetDependencies, validateDependencies } from './planning';
import { initialSchedule, resumeSchedule, scheduleReview, suspendSchedule } from './review';

export type ProjectInput = Partial<Omit<Project, keyof Entity>> & Pick<Project, 'title'>;
export type TaskInput = Partial<Omit<Task, keyof Entity | 'completedAt'>> & Pick<Task, 'projectId' | 'title'>;
export type NoteInput = Partial<Omit<Note, keyof Entity>> & Pick<Note, 'projectId' | 'title'>;
export type SourceInput = Partial<Omit<Source, keyof Entity>> & Pick<Source, 'projectId' | 'title'>;
export type CardInput = Partial<Omit<StudyCard, keyof Entity | 'schedule'>> & Pick<StudyCard, 'projectId' | 'question' | 'answer'>;
export type PromptInput = Partial<Omit<SavedPrompt, keyof Entity | 'useCount' | 'lastUsedAt'>> & Pick<SavedPrompt, 'title' | 'template'>;

export type Command =
  | { type: 'project.create'; input: ProjectInput }
  | { type: 'project.update'; id: string; revision: number; patch: Partial<Omit<Project, keyof Entity>> }
  | { type: 'project.select'; id: string | null }
  | { type: 'project.delete'; id: string; revision: number }
  | { type: 'task.create'; input: TaskInput }
  | { type: 'task.update'; id: string; revision: number; patch: Partial<Omit<Task, keyof Entity | 'projectId' | 'completedAt'>> }
  | { type: 'task.status'; id: string; revision: number; status: TaskStatus }
  | { type: 'task.delete'; id: string; revision: number }
  | { type: 'task.check'; id: string; revision: number; itemId: string; done: boolean }
  | { type: 'task.reorder'; projectId: string; ids: string[] }
  | { type: 'task.batch-status'; ids: string[]; status: TaskStatus }
  | { type: 'note.create'; input: NoteInput }
  | { type: 'note.update'; id: string; revision: number; patch: Partial<Omit<Note, keyof Entity | 'projectId'>> }
  | { type: 'note.delete'; id: string; revision: number }
  | { type: 'source.create'; input: SourceInput }
  | { type: 'source.update'; id: string; revision: number; patch: Partial<Omit<Source, keyof Entity | 'projectId'>> }
  | { type: 'source.delete'; id: string; revision: number }
  | { type: 'card.create'; input: CardInput }
  | { type: 'card.update'; id: string; revision: number; patch: Partial<Omit<StudyCard, keyof Entity | 'projectId' | 'schedule'>> }
  | { type: 'card.delete'; id: string; revision: number }
  | { type: 'card.suspend'; id: string; revision: number; suspended: boolean }
  | { type: 'card.reset'; id: string; revision: number }
  | { type: 'card.review'; id: string; revision: number; grade: ReviewGrade; durationMs: number }
  | { type: 'card.undo-review'; reviewId: string }
  | { type: 'prompt.create'; input: PromptInput }
  | { type: 'prompt.update'; id: string; revision: number; patch: Partial<Omit<SavedPrompt, keyof Entity | 'useCount' | 'lastUsedAt'>> }
  | { type: 'prompt.delete'; id: string; revision: number }
  | { type: 'prompt.used'; id: string }
  | { type: 'focus.start'; projectId: string; taskId: string | null; minutes: number }
  | { type: 'focus.pause'; id: string }
  | { type: 'focus.resume'; id: string }
  | { type: 'focus.finish'; id: string; outcome: 'completed' | 'abandoned'; reflection: string }
  | { type: 'focus.delete'; id: string; revision: number }
  | { type: 'preferences.update'; patch: Partial<Preferences> };

export interface MutationResult {
  state: Workbench;
  createdId: string | null;
}

export function defaultPreferences(): Preferences {
  return {
    dailyNewCards: 10,
    dailyReviewCards: 100,
    focusMinutes: 25,
    weekStartsOn: 'monday',
    includeSourcesInContext: true,
    includeCompletedTasks: false,
    confirmBeforeDelete: true,
  };
}

export function createWorkbench(context: MutationContext): Workbench {
  return {
    version: 1,
    id: context.id(),
    revision: 0,
    createdAt: context.now,
    updatedAt: context.now,
    activeProjectId: null,
    projects: [],
    tasks: [],
    notes: [],
    sources: [],
    cards: [],
    reviews: [],
    prompts: [],
    sessions: [],
    events: [],
    preferences: defaultPreferences(),
  };
}

function entity(context: MutationContext): Entity {
  return {
    id: assertId(context.id()),
    createdAt: context.now,
    updatedAt: context.now,
    revision: 1,
  };
}

function touch<T extends Entity>(record: T, context: MutationContext): T {
  return {
    ...record,
    updatedAt: Math.max(record.createdAt, record.updatedAt, context.now),
    revision: record.revision + 1,
  };
}

function requireRecord<T extends Entity>(records: T[], id: string, revision?: number): T {
  const record = records.find(item => item.id === id);
  if (!record) throw new WorkbenchError('This record no longer exists.', 'missing');
  if (revision !== undefined && record.revision !== revision) {
    throw new WorkbenchError('This record changed while you were editing it. Reopen it before saving.', 'conflict');
  }
  return record;
}

function replace<T extends Entity>(records: T[], record: T): T[] {
  return records.map(item => item.id === record.id ? record : item);
}

function capacity(records: unknown[], max: number, label: string): void {
  if (records.length >= max) throw new WorkbenchError(`${label} limit reached. Export and remove unused records before adding more.`, 'limit');
}

function writableProject(state: Workbench, id: string): Project {
  const project = requireRecord(state.projects, id);
  if (project.status === 'archived') throw new WorkbenchError('Restore this archived project before editing its records.', 'blocked');
  return project;
}

function taskStatus(task: Task, status: TaskStatus, state: Workbench, context: MutationContext): Task {
  if (status === 'doing' || status === 'done') {
    const unmet = unmetDependencies(task, state.tasks);
    if (unmet.length) throw new WorkbenchError(`Complete dependencies first: ${unmet.map(item => item.title).join(', ')}`, 'blocked');
  }
  if (status === 'done' && task.checklist.some(item => !item.done)) {
    throw new WorkbenchError('Complete the checklist before marking this task done.', 'blocked');
  }
  if (task.status === 'done' && status !== 'done') {
    const completedDependants = dependants(task.id, state.tasks, true).filter(item => item.status === 'done');
    if (completedDependants.length) throw new WorkbenchError('Reopen completed dependent tasks before reopening their prerequisite.', 'blocked');
  }
  return touch({ ...task, status, completedAt: status === 'done' ? task.completedAt ?? context.now : null }, context);
}

function normalizeChecklist(items: ChecklistItem[]): ChecklistItem[] {
  if (!Array.isArray(items) || items.length > LIMITS.checklist) throw new WorkbenchError(`A checklist supports at most ${LIMITS.checklist} items.`);
  return items.map(item => ({
    id: assertId(item.id, 'Checklist ID'),
    text: assertText(item.text, 'Checklist item', 500, true).trim(),
    done: item.done,
  }));
}

function normalizeTask(task: Task): Task {
  return {
    ...task,
    title: task.title.trim(),
    tags: normalizeTags(task.tags),
    dependencies: normalizeIds(task.dependencies, 'Dependencies', LIMITS.dependencies),
    noteIds: normalizeIds(task.noteIds, 'Linked notes'),
    checklist: normalizeChecklist(task.checklist),
  };
}

function normalizeNote(note: Note): Note {
  return {
    ...note,
    title: note.title.trim(),
    tags: normalizeTags(note.tags),
    sourceIds: normalizeIds(note.sourceIds, 'Sources'),
    relatedNoteIds: normalizeIds(note.relatedNoteIds, 'Related notes'),
  };
}

function normalizeCard(card: StudyCard): StudyCard {
  return {
    ...card,
    question: card.question.trim(),
    answer: card.answer.trim(),
    tags: normalizeTags(card.tags),
    sourceIds: normalizeIds(card.sourceIds, 'Sources'),
  };
}

function event(
  context: MutationContext,
  entityKind: ActivityEvent['entityKind'],
  entityId: string,
  projectId: string | null,
  action: ActivityEvent['action'],
  summary: string,
): ActivityEvent {
  return {
    id: context.id(),
    at: context.now,
    projectId,
    entityKind,
    entityId,
    action,
    summary: summary.slice(0, 300),
  };
}

export function applyCommand(previous: Workbench, command: Command, context: MutationContext): MutationResult {
  let state = { ...previous };
  let createdId: string | null = null;
  let activity: ActivityEvent | null = null;
  const log = (kind: ActivityEvent['entityKind'], record: Entity, projectId: string | null, action: ActivityEvent['action'], summary: string) => {
    activity = event(context, kind, record.id, projectId, action, summary);
  };

  switch (command.type) {
    case 'project.create': {
      capacity(state.projects, LIMITS.projects, 'Project');
      const project: Project = {
        summary: '',
        goal: '',
        context: '',
        engine: '',
        experience: 'beginner',
        status: 'active',
        color: PROJECT_COLORS[state.projects.length % PROJECT_COLORS.length],
        tags: [],
        pinned: false,
        weeklyMinutes: 120,
        targetDate: null,
        ...command.input,
        ...entity(context),
      };
      project.title = project.title.trim();
      project.tags = normalizeTags(project.tags);
      state.projects = [...state.projects, project];
      state.activeProjectId = project.id;
      createdId = project.id;
      log('project', project, project.id, 'created', `Created ${project.title}`);
      break;
    }
    case 'project.update': {
      const previousProject = requireRecord(state.projects, command.id, command.revision);
      const project = touch({ ...previousProject, ...command.patch, id: previousProject.id }, context);
      project.title = project.title.trim();
      project.tags = normalizeTags(project.tags);
      if (project.status === 'archived' && state.sessions.some(item => item.projectId === project.id && item.outcome === 'running')) {
        throw new WorkbenchError('Finish the running focus session before archiving the project.', 'blocked');
      }
      state.projects = replace(state.projects, project);
      log('project', project, project.id, 'updated', `Updated ${project.title}`);
      break;
    }
    case 'project.select': {
      if (command.id !== null) requireRecord(state.projects, command.id);
      state.activeProjectId = command.id;
      break;
    }
    case 'project.delete': {
      const project = requireRecord(state.projects, command.id, command.revision);
      if (state.sessions.some(item => item.projectId === project.id && item.outcome === 'running')) {
        throw new WorkbenchError('Finish the running focus session before deleting this project.', 'blocked');
      }
      state.projects = state.projects.filter(item => item.id !== project.id);
      state.tasks = state.tasks.filter(item => item.projectId !== project.id);
      state.notes = state.notes.filter(item => item.projectId !== project.id);
      state.sources = state.sources.filter(item => item.projectId !== project.id);
      state.cards = state.cards.filter(item => item.projectId !== project.id);
      state.reviews = state.reviews.filter(item => item.projectId !== project.id);
      state.prompts = state.prompts.filter(item => item.projectId !== project.id);
      state.sessions = state.sessions.filter(item => item.projectId !== project.id);
      state.events = state.events.filter(item => item.projectId !== project.id);
      if (state.activeProjectId === project.id) state.activeProjectId = state.projects.find(item => item.status !== 'archived')?.id || null;
      break;
    }
    case 'task.create': {
      writableProject(state, command.input.projectId);
      capacity(state.tasks, LIMITS.tasks, 'Task');
      const task = normalizeTask({
        description: '',
        status: 'inbox',
        priority: 'normal',
        estimateMinutes: 25,
        dueDate: null,
        dependencies: [],
        checklist: [],
        tags: [],
        noteIds: [],
        order: state.tasks.filter(item => item.projectId === command.input.projectId).length,
        ...command.input,
        completedAt: null,
        ...entity(context),
      });
      validateDependencies(task, state.tasks);
      const checked = taskStatus(task, task.status, state, context);
      checked.revision = 1;
      state.tasks = [...state.tasks, checked];
      createdId = task.id;
      log('task', task, task.projectId, 'created', `Created task: ${task.title}`);
      break;
    }
    case 'task.update': {
      const original = requireRecord(state.tasks, command.id, command.revision);
      writableProject(state, original.projectId);
      let task = normalizeTask({ ...original, ...command.patch, id: original.id, projectId: original.projectId });
      validateDependencies(task, state.tasks);
      const desiredStatus = task.status;
      task = taskStatus({ ...task, status: original.status }, desiredStatus, state, context);
      state.tasks = replace(state.tasks, task);
      log('task', task, task.projectId, 'updated', `Updated task: ${task.title}`);
      break;
    }
    case 'task.status': {
      const original = requireRecord(state.tasks, command.id, command.revision);
      writableProject(state, original.projectId);
      const task = taskStatus(original, command.status, state, context);
      state.tasks = replace(state.tasks, task);
      log('task', task, task.projectId, 'status', `${task.title}: ${task.status}`);
      break;
    }
    case 'task.check': {
      const original = requireRecord(state.tasks, command.id, command.revision);
      writableProject(state, original.projectId);
      if (!original.checklist.some(item => item.id === command.itemId)) throw new WorkbenchError('Checklist item no longer exists.', 'missing');
      if (original.status === 'done' && !command.done) throw new WorkbenchError('Reopen the task before unchecking an item.', 'blocked');
      const task = touch({ ...original, checklist: original.checklist.map(item => item.id === command.itemId ? { ...item, done: command.done } : item) }, context);
      state.tasks = replace(state.tasks, task);
      break;
    }
    case 'task.reorder': {
      writableProject(state, command.projectId);
      const current = state.tasks.filter(item => item.projectId === command.projectId);
      if (command.ids.length !== current.length || new Set(command.ids).size !== current.length || current.some(item => !command.ids.includes(item.id))) {
        throw new WorkbenchError('Reordering must include every project task exactly once.');
      }
      const order = new Map(command.ids.map((id, index) => [id, index]));
      state.tasks = state.tasks.map(task => task.projectId === command.projectId ? touch({ ...task, order: order.get(task.id)! }, context) : task);
      break;
    }
    case 'task.batch-status': {
      const ids = normalizeIds(command.ids, 'Selected tasks', LIMITS.tasks);
      if (!ids.length) throw new WorkbenchError('Select at least one task.');
      // Atomic batch: failure returns no partial state to the caller.
      for (const id of ids) {
        const task = requireRecord(state.tasks, id);
        const result = applyCommand(state, { type: 'task.status', id, revision: task.revision, status: command.status }, context);
        state = result.state;
      }
      break;
    }
    case 'task.delete': {
      const task = requireRecord(state.tasks, command.id, command.revision);
      writableProject(state, task.projectId);
      if (dependants(task.id, state.tasks).length) throw new WorkbenchError('Remove this task from dependent tasks before deleting it.', 'blocked');
      if (state.sessions.some(item => item.taskId === task.id && item.outcome === 'running')) throw new WorkbenchError('Finish the active focus session first.', 'blocked');
      state.tasks = state.tasks.filter(item => item.id !== task.id);
      state.sessions = state.sessions.map(item => item.taskId === task.id ? touch({ ...item, taskId: null }, context) : item);
      log('task', task, task.projectId, 'deleted', `Deleted task: ${task.title}`);
      break;
    }
    case 'note.create': {
      writableProject(state, command.input.projectId);
      capacity(state.notes, LIMITS.notes, 'Note');
      const note = normalizeNote({
        body: '',
        kind: 'note',
        tags: [],
        sourceIds: [],
        relatedNoteIds: [],
        confidence: 'unverified',
        pinned: false,
        archived: false,
        ...command.input,
        ...entity(context),
      });
      state.notes = [...state.notes, note];
      createdId = note.id;
      log('note', note, note.projectId, 'created', `Created note: ${note.title}`);
      break;
    }
    case 'note.update': {
      const original = requireRecord(state.notes, command.id, command.revision);
      writableProject(state, original.projectId);
      const note = touch(normalizeNote({ ...original, ...command.patch, id: original.id, projectId: original.projectId }), context);
      state.notes = replace(state.notes, note);
      log('note', note, note.projectId, 'updated', `Updated note: ${note.title}`);
      break;
    }
    case 'note.delete': {
      const note = requireRecord(state.notes, command.id, command.revision);
      writableProject(state, note.projectId);
      state.notes = state.notes.filter(item => item.id !== note.id).map(item => item.relatedNoteIds.includes(note.id)
        ? touch({ ...item, relatedNoteIds: item.relatedNoteIds.filter(id => id !== note.id) }, context) : item);
      state.tasks = state.tasks.map(item => item.noteIds.includes(note.id)
        ? touch({ ...item, noteIds: item.noteIds.filter(id => id !== note.id) }, context) : item);
      state.cards = state.cards.map(item => item.noteId === note.id ? touch({ ...item, noteId: null }, context) : item);
      log('note', note, note.projectId, 'deleted', `Deleted note: ${note.title}`);
      break;
    }
    case 'source.create': {
      writableProject(state, command.input.projectId);
      capacity(state.sources, LIMITS.sources, 'Source');
      const source: Source = {
        kind: 'observation',
        locator: '',
        excerpt: '',
        author: '',
        accessedAt: context.now,
        tags: [],
        ...command.input,
        ...entity(context),
      };
      source.tags = normalizeTags(source.tags);
      state.sources = [...state.sources, source];
      createdId = source.id;
      log('source', source, source.projectId, 'created', `Added source: ${source.title}`);
      break;
    }
    case 'source.update': {
      const original = requireRecord(state.sources, command.id, command.revision);
      writableProject(state, original.projectId);
      const source = touch({ ...original, ...command.patch, id: original.id, projectId: original.projectId }, context);
      source.tags = normalizeTags(source.tags);
      state.sources = replace(state.sources, source);
      log('source', source, source.projectId, 'updated', `Updated source: ${source.title}`);
      break;
    }
    case 'source.delete': {
      const source = requireRecord(state.sources, command.id, command.revision);
      writableProject(state, source.projectId);
      state.sources = state.sources.filter(item => item.id !== source.id);
      state.notes = state.notes.map(item => item.sourceIds.includes(source.id)
        ? touch({ ...item, sourceIds: item.sourceIds.filter(id => id !== source.id) }, context) : item);
      state.cards = state.cards.map(item => item.sourceIds.includes(source.id)
        ? touch({ ...item, sourceIds: item.sourceIds.filter(id => id !== source.id) }, context) : item);
      log('source', source, source.projectId, 'deleted', `Deleted source: ${source.title}`);
      break;
    }
    case 'card.create': {
      writableProject(state, command.input.projectId);
      capacity(state.cards, LIMITS.cards, 'Study card');
      const card = normalizeCard({
        hint: '',
        explanation: '',
        tags: [],
        noteId: null,
        sourceIds: [],
        ...command.input,
        schedule: initialSchedule(context.now),
        ...entity(context),
      });
      state.cards = [...state.cards, card];
      createdId = card.id;
      log('card', card, card.projectId, 'created', `Created study card: ${card.question}`);
      break;
    }
    case 'card.update': {
      const original = requireRecord(state.cards, command.id, command.revision);
      writableProject(state, original.projectId);
      const card = touch(normalizeCard({ ...original, ...command.patch, id: original.id, projectId: original.projectId, schedule: original.schedule }), context);
      state.cards = replace(state.cards, card);
      log('card', card, card.projectId, 'updated', `Updated study card: ${card.question}`);
      break;
    }
    case 'card.delete': {
      const card = requireRecord(state.cards, command.id, command.revision);
      writableProject(state, card.projectId);
      state.cards = state.cards.filter(item => item.id !== card.id);
      state.reviews = state.reviews.filter(item => item.cardId !== card.id);
      log('card', card, card.projectId, 'deleted', `Deleted study card: ${card.question}`);
      break;
    }
    case 'card.suspend':
    case 'card.reset': {
      const original = requireRecord(state.cards, command.id, command.revision);
      writableProject(state, original.projectId);
      let schedule: CardSchedule;
      if (command.type === 'card.reset') schedule = initialSchedule(context.now);
      else schedule = command.suspended ? suspendSchedule(original.schedule) : resumeSchedule(original.schedule, context.now);
      const card = touch({ ...original, schedule }, context);
      state.cards = replace(state.cards, card);
      log('card', card, card.projectId, 'status', command.type === 'card.reset' ? 'Reset card schedule' : command.suspended ? 'Suspended card' : 'Resumed card');
      break;
    }
    case 'card.review': {
      const original = requireRecord(state.cards, command.id, command.revision);
      writableProject(state, original.projectId);
      assertInteger(command.durationMs, 'Review duration', 0, 3600000);
      const schedule = scheduleReview(original.schedule, command.grade, context.now);
      const card = touch({ ...original, schedule }, context);
      const review = {
        ...entity(context),
        projectId: card.projectId,
        cardId: card.id,
        grade: command.grade,
        durationMs: command.durationMs,
        reviewedAt: context.now,
        previous: { ...original.schedule },
        next: { ...schedule },
        sessionId: state.sessions.find(item => item.projectId === card.projectId && item.outcome === 'running')?.id || null,
      };
      state.cards = replace(state.cards, card);
      state.reviews = [...state.reviews, review].slice(-LIMITS.reviews);
      createdId = review.id;
      log('card', card, card.projectId, 'reviewed', `Reviewed card: ${command.grade}`);
      break;
    }
    case 'card.undo-review': {
      const review = requireRecord(state.reviews, command.reviewId);
      const card = requireRecord(state.cards, review.cardId);
      writableProject(state, card.projectId);
      const last = state.reviews.filter(item => item.cardId === card.id).at(-1);
      if (last?.id !== review.id || JSON.stringify(card.schedule) !== JSON.stringify(review.next)) {
        throw new WorkbenchError('Only the latest unchanged review can be undone.', 'conflict');
      }
      state.cards = replace(state.cards, touch({ ...card, schedule: { ...review.previous } }, context));
      state.reviews = state.reviews.filter(item => item.id !== review.id);
      log('card', card, card.projectId, 'restored', 'Undid the latest card review');
      break;
    }
    case 'prompt.create': {
      if (command.input.projectId) writableProject(state, command.input.projectId);
      capacity(state.prompts, LIMITS.prompts, 'Prompt');
      const prompt: SavedPrompt = {
        projectId: null,
        description: '',
        variables: [],
        tags: [],
        favorite: false,
        ...command.input,
        useCount: 0,
        lastUsedAt: null,
        ...entity(context),
      };
      prompt.tags = normalizeTags(prompt.tags);
      state.prompts = [...state.prompts, prompt];
      createdId = prompt.id;
      log('prompt', prompt, prompt.projectId, 'created', `Saved prompt: ${prompt.title}`);
      break;
    }
    case 'prompt.update': {
      const original = requireRecord(state.prompts, command.id, command.revision);
      if (original.projectId) writableProject(state, original.projectId);
      const prompt = touch({ ...original, ...command.patch, id: original.id }, context);
      if (prompt.projectId) writableProject(state, prompt.projectId);
      prompt.tags = normalizeTags(prompt.tags);
      state.prompts = replace(state.prompts, prompt);
      log('prompt', prompt, prompt.projectId, 'updated', `Updated prompt: ${prompt.title}`);
      break;
    }
    case 'prompt.delete': {
      const prompt = requireRecord(state.prompts, command.id, command.revision);
      if (prompt.projectId) writableProject(state, prompt.projectId);
      state.prompts = state.prompts.filter(item => item.id !== prompt.id);
      log('prompt', prompt, prompt.projectId, 'deleted', `Deleted prompt: ${prompt.title}`);
      break;
    }
    case 'prompt.used': {
      const original = requireRecord(state.prompts, command.id);
      const prompt = touch({ ...original, useCount: Math.min(1000000, original.useCount + 1), lastUsedAt: context.now }, context);
      state.prompts = replace(state.prompts, prompt);
      break;
    }
    case 'focus.start': {
      writableProject(state, command.projectId);
      capacity(state.sessions, LIMITS.sessions, 'Focus session');
      if (state.sessions.some(item => item.outcome === 'running')) throw new WorkbenchError('Finish the current focus session first.', 'blocked');
      assertInteger(command.minutes, 'Focus minutes', 1, 480);
      if (command.taskId) {
        const task = requireRecord(state.tasks, command.taskId);
        if (task.projectId !== command.projectId || isTerminal(task)) throw new WorkbenchError('Choose an unfinished task from this project.');
        if (task.status === 'blocked' || unmetDependencies(task, state.tasks).length) throw new WorkbenchError('Resolve blockers and complete dependencies before starting this task.', 'blocked');
      }
      const session: FocusSession = {
        ...entity(context),
        projectId: command.projectId,
        taskId: command.taskId,
        startedAt: context.now,
        endedAt: null,
        plannedMinutes: command.minutes,
        pausedAt: null,
        pausedMilliseconds: 0,
        outcome: 'running',
        reflection: '',
      };
      state.sessions = [...state.sessions, session];
      createdId = session.id;
      log('session', session, session.projectId, 'focused', `Started ${command.minutes}-minute focus session`);
      break;
    }
    case 'focus.pause':
    case 'focus.resume':
    case 'focus.finish': {
      const original = requireRecord(state.sessions, command.id);
      if (original.outcome !== 'running') throw new WorkbenchError('This focus session has already ended.', 'conflict');
      if (context.now < original.updatedAt || context.now < original.startedAt || (original.pausedAt !== null && context.now < original.pausedAt)) {
        throw new WorkbenchError('The device clock moved backwards. Check the clock before continuing.', 'conflict');
      }
      let session = touch(original, context);
      if (command.type === 'focus.pause') {
        if (session.pausedAt !== null) throw new WorkbenchError('This session is already paused.', 'conflict');
        session.pausedAt = context.now;
      } else if (command.type === 'focus.resume') {
        if (session.pausedAt === null) throw new WorkbenchError('This session is not paused.', 'conflict');
        session.pausedMilliseconds += context.now - session.pausedAt;
        session.pausedAt = null;
      } else {
        if (session.pausedAt !== null) session.pausedMilliseconds += context.now - session.pausedAt;
        session.pausedAt = null;
        session.endedAt = context.now;
        session.outcome = command.outcome;
        session.reflection = assertText(command.reflection, 'Reflection', LIMITS.summary);
      }
      state.sessions = replace(state.sessions, session);
      log('session', session, session.projectId, 'focused', command.type === 'focus.finish' ? `Focus session ${command.outcome}` : command.type === 'focus.pause' ? 'Paused focus session' : 'Resumed focus session');
      break;
    }
    case 'focus.delete': {
      const session = requireRecord(state.sessions, command.id, command.revision);
      if (session.outcome === 'running') throw new WorkbenchError('End this session before deleting it.', 'blocked');
      state.sessions = state.sessions.filter(item => item.id !== session.id);
      state.reviews = state.reviews.map(item => item.sessionId === session.id ? { ...item, sessionId: null } : item);
      log('session', session, session.projectId, 'deleted', 'Deleted focus session');
      break;
    }
    case 'preferences.update': {
      state.preferences = { ...state.preferences, ...command.patch };
      break;
    }
    default: {
      const exhaustive: never = command;
      throw new WorkbenchError(`Unknown workbench operation: ${String(exhaustive)}`);
    }
  }
  state.revision = previous.revision + 1;
  state.updatedAt = Math.max(previous.updatedAt, context.now);
  if (activity) state.events = [...state.events, activity].slice(-LIMITS.events);
  const parsed = validateWorkbench(state);
  if (!parsed.ok) throw new WorkbenchError(parsed.issues.map(item => `${item.path}: ${item.message}`).join('\n'));
  const issues = inspectIntegrity(parsed.value);
  if (issues.length) throw new WorkbenchError(issues.map(item => item.message).join('\n'));
  if (JSON.stringify(parsed.value).length > LIMITS.stateCharacters) {
    throw new WorkbenchError('The workbench storage budget is full. Export a backup and remove unused records.', 'limit');
  }
  return { state: parsed.value, createdId };
}
