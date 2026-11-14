import {
  CONFIDENCES,
  LIMITS,
  NOTE_KINDS,
  PRIORITIES,
  PROJECT_COLORS,
  TASK_STATUSES,
} from './types';
import type {
  ActivityEvent,
  CardSchedule,
  ChecklistItem,
  FocusSession,
  Note,
  Preferences,
  Project,
  PromptVariable,
  Result,
  Review,
  SavedPrompt,
  Source,
  StudyCard,
  Task,
  ValidationIssue,
  Workbench,
} from './types';

type Raw = Record<string, unknown>;

export class WorkbenchError extends Error {
  constructor(
    message: string,
    public readonly code: 'invalid' | 'missing' | 'conflict' | 'limit' | 'blocked' = 'invalid',
  ) {
    super(message);
    this.name = 'WorkbenchError';
  }
}

export function isRecord(value: unknown): value is Raw {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function assertText(value: unknown, label: string, max: number, required = false): string {
  if (typeof value !== 'string') throw new WorkbenchError(`${label} must be text.`);
  const normalized = value.replace(/\r\n/g, '\n').replace(/\u0000/g, '');
  if (required && !normalized.trim()) throw new WorkbenchError(`${label} cannot be empty.`);
  if (normalized.length > max) throw new WorkbenchError(`${label} exceeds ${max.toLocaleString()} characters.`);
  return normalized;
}

export function assertNumber(value: unknown, label: string, min: number, max: number): number {
  if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max) {
    throw new WorkbenchError(`${label} must be between ${min} and ${max}.`);
  }
  return value;
}

export function assertInteger(value: unknown, label: string, min: number, max: number): number {
  const number = assertNumber(value, label, min, max);
  if (!Number.isInteger(number)) throw new WorkbenchError(`${label} must be a whole number.`);
  return number;
}

export function assertEnum<T extends string>(value: unknown, values: readonly T[], label: string): T {
  if (typeof value !== 'string' || !values.includes(value as T)) {
    throw new WorkbenchError(`${label} must be one of: ${values.join(', ')}.`);
  }
  return value as T;
}

export function assertId(value: unknown, label = 'ID'): string {
  const id = assertText(value, label, 120, true);
  if (!/^[a-zA-Z0-9_-]+$/.test(id)) throw new WorkbenchError(`${label} contains unsupported characters.`);
  return id;
}

export function validDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const parsed = new Date(`${value}T12:00:00Z`);
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

export function assertDate(value: unknown, label: string): string | null {
  if (value === null || value === '') return null;
  if (typeof value !== 'string' || !validDate(value)) {
    throw new WorkbenchError(`${label} must be a real date in YYYY-MM-DD format.`);
  }
  return value;
}

export function normalizeTags(input: string[] | string): string[] {
  const list = typeof input === 'string' ? input.split(',') : input;
  if (!Array.isArray(list)) throw new WorkbenchError('Tags must be a list.');
  const values = list.map(tag => assertText(tag, 'Tag', LIMITS.tag).trim().toLocaleLowerCase()).filter(Boolean);
  const unique = [...new Set(values)];
  if (unique.length > LIMITS.tags) throw new WorkbenchError(`Use at most ${LIMITS.tags} tags.`);
  return unique;
}

export function safeUrl(value: string): string | null {
  try {
    const url = new URL(value.trim());
    if (!['http:', 'https:'].includes(url.protocol) || !url.hostname || url.username || url.password) return null;
    return url.toString();
  } catch {
    return null;
  }
}

export function normalizeIds(values: string[], label: string, max: number = LIMITS.links): string[] {
  if (!Array.isArray(values)) throw new WorkbenchError(`${label} must be a list.`);
  if (values.length > max) throw new WorkbenchError(`${label} exceeds ${max} items.`);
  return [...new Set(values.map(value => assertId(value, label)))];
}

class Reader {
  readonly issues: ValidationIssue[] = [];

  issue(path: string, message: string): void {
    if (this.issues.length < 100) this.issues.push({ path, message });
  }

  object(value: unknown, path: string): Raw {
    if (isRecord(value)) return value;
    this.issue(path, 'Expected an object.');
    return {};
  }

  run<T>(path: string, fallback: T, operation: () => T): T {
    try {
      return operation();
    } catch (error) {
      this.issue(path, error instanceof Error ? error.message : 'Invalid value.');
      return fallback;
    }
  }

  text(value: unknown, path: string, max: number, required = false): string {
    return this.run(path, '', () => assertText(value, path, max, required));
  }

  number(value: unknown, path: string, min = 0, max = Number.MAX_SAFE_INTEGER): number {
    return this.run(path, min, () => assertNumber(value, path, min, max));
  }

  integer(value: unknown, path: string, min = 0, max = Number.MAX_SAFE_INTEGER): number {
    return this.run(path, min, () => assertInteger(value, path, min, max));
  }

  boolean(value: unknown, path: string): boolean {
    if (typeof value === 'boolean') return value;
    this.issue(path, 'Expected true or false.');
    return false;
  }

  id(value: unknown, path: string): string {
    return this.run(path, '', () => assertId(value, path));
  }

  nullableId(value: unknown, path: string): string | null {
    return value === null ? null : this.id(value, path);
  }

  nullableTime(value: unknown, path: string): number | null {
    return value === null ? null : this.number(value, path, 0, 8.64e15);
  }

  date(value: unknown, path: string): string | null {
    return this.run(path, null, () => assertDate(value, path));
  }

  enum<T extends string>(value: unknown, values: readonly T[], path: string): T {
    return this.run(path, values[0], () => assertEnum(value, values, path));
  }

  list<T>(value: unknown, path: string, max: number, parse: (value: unknown, path: string) => T): T[] {
    if (!Array.isArray(value)) {
      this.issue(path, 'Expected a list.');
      return [];
    }
    if (value.length > max) this.issue(path, `At most ${max} entries are allowed.`);
    return value.slice(0, max).map((item, i) => parse(item, `${path}[${i}]`));
  }

  ids(value: unknown, path: string, max = LIMITS.links): string[] {
    const ids = this.list(value, path, max, (item, at) => this.id(item, at));
    if (new Set(ids).size !== ids.length) this.issue(path, 'Duplicate links are not allowed.');
    return ids;
  }

  tags(value: unknown, path: string): string[] {
    return this.list(value, path, LIMITS.tags, (item, at) => this.text(item, at, LIMITS.tag, true));
  }

  entity(raw: Raw, path: string) {
    return {
      id: this.id(raw.id, `${path}.id`),
      createdAt: this.number(raw.createdAt, `${path}.createdAt`, 0, 8.64e15),
      updatedAt: this.number(raw.updatedAt, `${path}.updatedAt`, 0, 8.64e15),
      revision: this.integer(raw.revision, `${path}.revision`, 1),
    };
  }

  project = (value: unknown, path: string): Project => {
    const raw = this.object(value, path);
    return {
      ...this.entity(raw, path),
      title: this.text(raw.title, `${path}.title`, LIMITS.title, true),
      summary: this.text(raw.summary, `${path}.summary`, LIMITS.summary),
      goal: this.text(raw.goal, `${path}.goal`, LIMITS.summary),
      context: this.text(raw.context, `${path}.context`, LIMITS.context),
      engine: this.text(raw.engine, `${path}.engine`, 120),
      experience: this.enum(raw.experience, ['beginner', 'intermediate', 'advanced'], `${path}.experience`),
      status: this.enum(raw.status, ['active', 'paused', 'completed', 'archived'], `${path}.status`),
      color: this.enum(raw.color, PROJECT_COLORS, `${path}.color`),
      tags: this.tags(raw.tags, `${path}.tags`),
      pinned: this.boolean(raw.pinned, `${path}.pinned`),
      weeklyMinutes: this.integer(raw.weeklyMinutes, `${path}.weeklyMinutes`, 0, 10080),
      targetDate: this.date(raw.targetDate, `${path}.targetDate`),
    };
  };

  checklist = (value: unknown, path: string): ChecklistItem => {
    const raw = this.object(value, path);
    return {
      id: this.id(raw.id, `${path}.id`),
      text: this.text(raw.text, `${path}.text`, 500, true),
      done: this.boolean(raw.done, `${path}.done`),
    };
  };

  task = (value: unknown, path: string): Task => {
    const raw = this.object(value, path);
    return {
      ...this.entity(raw, path),
      projectId: this.id(raw.projectId, `${path}.projectId`),
      title: this.text(raw.title, `${path}.title`, LIMITS.title, true),
      description: this.text(raw.description, `${path}.description`, LIMITS.body),
      status: this.enum(raw.status, TASK_STATUSES, `${path}.status`),
      priority: this.enum(raw.priority, PRIORITIES, `${path}.priority`),
      estimateMinutes: this.integer(raw.estimateMinutes, `${path}.estimateMinutes`, 0, 10080),
      dueDate: this.date(raw.dueDate, `${path}.dueDate`),
      completedAt: this.nullableTime(raw.completedAt, `${path}.completedAt`),
      dependencies: this.ids(raw.dependencies, `${path}.dependencies`, LIMITS.dependencies),
      checklist: this.list(raw.checklist, `${path}.checklist`, LIMITS.checklist, this.checklist),
      tags: this.tags(raw.tags, `${path}.tags`),
      noteIds: this.ids(raw.noteIds, `${path}.noteIds`),
      order: this.number(raw.order, `${path}.order`, -1e9, 1e9),
    };
  };

  note = (value: unknown, path: string): Note => {
    const raw = this.object(value, path);
    return {
      ...this.entity(raw, path),
      projectId: this.id(raw.projectId, `${path}.projectId`),
      title: this.text(raw.title, `${path}.title`, LIMITS.title, true),
      body: this.text(raw.body, `${path}.body`, LIMITS.body),
      kind: this.enum(raw.kind, NOTE_KINDS, `${path}.kind`),
      tags: this.tags(raw.tags, `${path}.tags`),
      sourceIds: this.ids(raw.sourceIds, `${path}.sourceIds`),
      relatedNoteIds: this.ids(raw.relatedNoteIds, `${path}.relatedNoteIds`),
      confidence: this.enum(raw.confidence, CONFIDENCES, `${path}.confidence`),
      pinned: this.boolean(raw.pinned, `${path}.pinned`),
      archived: this.boolean(raw.archived, `${path}.archived`),
    };
  };

  source = (value: unknown, path: string): Source => {
    const raw = this.object(value, path);
    const source: Source = {
      ...this.entity(raw, path),
      projectId: this.id(raw.projectId, `${path}.projectId`),
      title: this.text(raw.title, `${path}.title`, LIMITS.title, true),
      kind: this.enum(raw.kind, ['url', 'book', 'file', 'conversation', 'observation'], `${path}.kind`),
      locator: this.text(raw.locator, `${path}.locator`, 2000),
      excerpt: this.text(raw.excerpt, `${path}.excerpt`, LIMITS.answer),
      author: this.text(raw.author, `${path}.author`, 200),
      accessedAt: this.number(raw.accessedAt, `${path}.accessedAt`, 0, 8.64e15),
      tags: this.tags(raw.tags, `${path}.tags`),
    };
    if (source.kind === 'url' && !safeUrl(source.locator)) {
      this.issue(`${path}.locator`, 'URL sources require an HTTP(S) URL without embedded credentials.');
    }
    return source;
  };

  schedule = (value: unknown, path: string): CardSchedule => {
    const raw = this.object(value, path);
    return {
      state: this.enum(raw.state, ['new', 'learning', 'review', 'relearning', 'suspended'], `${path}.state`),
      dueAt: this.number(raw.dueAt, `${path}.dueAt`, 0, 8.64e15),
      intervalDays: this.number(raw.intervalDays, `${path}.intervalDays`, 0, 36500),
      ease: this.number(raw.ease, `${path}.ease`, 1.3, 3.5),
      repetitions: this.integer(raw.repetitions, `${path}.repetitions`, 0, 1000000),
      lapses: this.integer(raw.lapses, `${path}.lapses`, 0, 1000000),
      learningStep: this.integer(raw.learningStep, `${path}.learningStep`, 0, 2),
      lastReviewedAt: this.nullableTime(raw.lastReviewedAt, `${path}.lastReviewedAt`),
      suspendedFrom: raw.suspendedFrom === null ? null : this.enum(raw.suspendedFrom, ['new', 'learning', 'review', 'relearning'] as const, `${path}.suspendedFrom`),
    };
  };

  card = (value: unknown, path: string): StudyCard => {
    const raw = this.object(value, path);
    return {
      ...this.entity(raw, path),
      projectId: this.id(raw.projectId, `${path}.projectId`),
      question: this.text(raw.question, `${path}.question`, LIMITS.summary, true),
      answer: this.text(raw.answer, `${path}.answer`, LIMITS.answer, true),
      hint: this.text(raw.hint, `${path}.hint`, LIMITS.summary),
      explanation: this.text(raw.explanation, `${path}.explanation`, LIMITS.answer),
      tags: this.tags(raw.tags, `${path}.tags`),
      noteId: this.nullableId(raw.noteId, `${path}.noteId`),
      sourceIds: this.ids(raw.sourceIds, `${path}.sourceIds`),
      schedule: this.schedule(raw.schedule, `${path}.schedule`),
    };
  };

  review = (value: unknown, path: string): Review => {
    const raw = this.object(value, path);
    return {
      ...this.entity(raw, path),
      projectId: this.id(raw.projectId, `${path}.projectId`),
      cardId: this.id(raw.cardId, `${path}.cardId`),
      grade: this.enum(raw.grade, ['again', 'hard', 'good', 'easy'], `${path}.grade`),
      durationMs: this.integer(raw.durationMs, `${path}.durationMs`, 0, 3600000),
      reviewedAt: this.number(raw.reviewedAt, `${path}.reviewedAt`, 0, 8.64e15),
      previous: this.schedule(raw.previous, `${path}.previous`),
      next: this.schedule(raw.next, `${path}.next`),
      sessionId: this.nullableId(raw.sessionId, `${path}.sessionId`),
    };
  };

  variable = (value: unknown, path: string): PromptVariable => {
    const raw = this.object(value, path);
    const key = this.text(raw.key, `${path}.key`, 40, true);
    if (!/^[a-z][a-z0-9_]*$/.test(key)) this.issue(`${path}.key`, 'Use a lowercase variable name.');
    return {
      key,
      label: this.text(raw.label, `${path}.label`, 100, true),
      description: this.text(raw.description, `${path}.description`, 500),
      defaultValue: this.text(raw.defaultValue, `${path}.defaultValue`, LIMITS.summary),
      required: this.boolean(raw.required, `${path}.required`),
    };
  };

  prompt = (value: unknown, path: string): SavedPrompt => {
    const raw = this.object(value, path);
    return {
      ...this.entity(raw, path),
      projectId: this.nullableId(raw.projectId, `${path}.projectId`),
      title: this.text(raw.title, `${path}.title`, LIMITS.title, true),
      description: this.text(raw.description, `${path}.description`, LIMITS.summary),
      template: this.text(raw.template, `${path}.template`, LIMITS.context, true),
      variables: this.list(raw.variables, `${path}.variables`, 20, this.variable),
      tags: this.tags(raw.tags, `${path}.tags`),
      favorite: this.boolean(raw.favorite, `${path}.favorite`),
      useCount: this.integer(raw.useCount, `${path}.useCount`, 0, 1000000),
      lastUsedAt: this.nullableTime(raw.lastUsedAt, `${path}.lastUsedAt`),
    };
  };

  session = (value: unknown, path: string): FocusSession => {
    const raw = this.object(value, path);
    return {
      ...this.entity(raw, path),
      projectId: this.id(raw.projectId, `${path}.projectId`),
      taskId: this.nullableId(raw.taskId, `${path}.taskId`),
      startedAt: this.number(raw.startedAt, `${path}.startedAt`, 0, 8.64e15),
      endedAt: this.nullableTime(raw.endedAt, `${path}.endedAt`),
      plannedMinutes: this.integer(raw.plannedMinutes, `${path}.plannedMinutes`, 1, 480),
      pausedAt: this.nullableTime(raw.pausedAt, `${path}.pausedAt`),
      pausedMilliseconds: this.number(raw.pausedMilliseconds, `${path}.pausedMilliseconds`, 0, 8.64e15),
      outcome: this.enum(raw.outcome, ['running', 'completed', 'abandoned'], `${path}.outcome`),
      reflection: this.text(raw.reflection, `${path}.reflection`, LIMITS.summary),
    };
  };

  event = (value: unknown, path: string): ActivityEvent => {
    const raw = this.object(value, path);
    return {
      id: this.id(raw.id, `${path}.id`),
      at: this.number(raw.at, `${path}.at`, 0, 8.64e15),
      projectId: this.nullableId(raw.projectId, `${path}.projectId`),
      entityKind: this.enum(raw.entityKind, ['project', 'task', 'note', 'card', 'prompt', 'source', 'session'], `${path}.entityKind`),
      entityId: this.id(raw.entityId, `${path}.entityId`),
      action: this.enum(raw.action, ['created', 'updated', 'status', 'deleted', 'restored', 'reviewed', 'imported', 'focused'], `${path}.action`),
      summary: this.text(raw.summary, `${path}.summary`, 300, true),
    };
  };

  preferences(value: unknown): Preferences {
    const raw = this.object(value, 'preferences');
    return {
      dailyNewCards: this.integer(raw.dailyNewCards, 'preferences.dailyNewCards', 0, 200),
      dailyReviewCards: this.integer(raw.dailyReviewCards, 'preferences.dailyReviewCards', 1, 1000),
      focusMinutes: this.integer(raw.focusMinutes, 'preferences.focusMinutes', 1, 480),
      weekStartsOn: this.enum(raw.weekStartsOn, ['monday', 'sunday'], 'preferences.weekStartsOn'),
      includeSourcesInContext: this.boolean(raw.includeSourcesInContext, 'preferences.includeSourcesInContext'),
      includeCompletedTasks: this.boolean(raw.includeCompletedTasks, 'preferences.includeCompletedTasks'),
      confirmBeforeDelete: this.boolean(raw.confirmBeforeDelete, 'preferences.confirmBeforeDelete'),
    };
  }
}

export function validateWorkbench(value: unknown): Result<Workbench> {
  const reader = new Reader();
  const raw = reader.object(value, 'workspace');
  if (raw.version !== 1) reader.issue('version', 'Unsupported workbench version.');
  const state: Workbench = {
    version: 1,
    id: reader.id(raw.id, 'id'),
    revision: reader.integer(raw.revision, 'revision', 0),
    createdAt: reader.number(raw.createdAt, 'createdAt', 0, 8.64e15),
    updatedAt: reader.number(raw.updatedAt, 'updatedAt', 0, 8.64e15),
    activeProjectId: reader.nullableId(raw.activeProjectId, 'activeProjectId'),
    projects: reader.list(raw.projects, 'projects', LIMITS.projects, reader.project),
    tasks: reader.list(raw.tasks, 'tasks', LIMITS.tasks, reader.task),
    notes: reader.list(raw.notes, 'notes', LIMITS.notes, reader.note),
    sources: reader.list(raw.sources, 'sources', LIMITS.sources, reader.source),
    cards: reader.list(raw.cards, 'cards', LIMITS.cards, reader.card),
    reviews: reader.list(raw.reviews, 'reviews', LIMITS.reviews, reader.review),
    prompts: reader.list(raw.prompts, 'prompts', LIMITS.prompts, reader.prompt),
    sessions: reader.list(raw.sessions, 'sessions', LIMITS.sessions, reader.session),
    events: reader.list(raw.events, 'events', LIMITS.events, reader.event),
    preferences: reader.preferences(raw.preferences),
  };
  const collections = [state.projects, state.tasks, state.notes, state.sources, state.cards, state.reviews, state.prompts, state.sessions, state.events];
  const allIds = new Set<string>();
  for (const collection of collections) {
    for (const item of collection) {
      if (allIds.has(item.id)) reader.issue(item.id, 'Record IDs must be globally unique.');
      allIds.add(item.id);
    }
  }
  const projects = new Set(state.projects.map(item => item.id));
  if (state.activeProjectId && !projects.has(state.activeProjectId)) {
    reader.issue('activeProjectId', 'The selected project does not exist.');
  }
  for (const collection of [state.tasks, state.notes, state.sources, state.cards, state.reviews, state.prompts, state.sessions]) {
    for (const item of collection) {
      if (item.projectId !== null && !projects.has(item.projectId)) reader.issue(item.id, 'The parent project does not exist.');
    }
  }
  return reader.issues.length ? { ok: false, issues: reader.issues } : { ok: true, value: state };
}

export function parseWorkbench(raw: string): Result<Workbench> {
  if (raw.length > LIMITS.stateCharacters) {
    return { ok: false, issues: [{ path: 'workspace', message: 'Saved workspace exceeds the storage budget.' }] };
  }
  try {
    return validateWorkbench(JSON.parse(raw));
  } catch {
    return { ok: false, issues: [{ path: 'workspace', message: 'The workspace is not valid JSON.' }] };
  }
}
