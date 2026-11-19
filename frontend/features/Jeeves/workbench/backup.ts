import { LIMITS } from './types';
import type { BackupEnvelope, ImportPreview, MutationContext, Result, Workbench } from './types';
import { inspectIntegrity, orphanWarnings } from './integrity';
import { isRecord, validateWorkbench, WorkbenchError } from './validation';

export function recordCount(state: Workbench): number {
  return state.projects.length + state.tasks.length + state.notes.length
    + state.sources.length + state.cards.length + state.reviews.length
    + state.prompts.length + state.sessions.length;
}

export function backupEnvelope(state: Workbench, now: number): BackupEnvelope {
  return {
    format: 'jeeves-workbench',
    version: 1,
    exportedAt: now,
    recordCount: recordCount(state),
    workspace: state,
  };
}

export function encodeBackup(state: Workbench, now: number): string {
  const result = validateWorkbench(state);
  if (!result.ok) throw new WorkbenchError('The workbench contains invalid records and cannot be exported.');
  const issues = inspectIntegrity(result.value);
  if (issues.length) throw new WorkbenchError('The workbench contains broken links. Resolve them before exporting.');
  // Compact JSON keeps portable backups below the documented file budget.
  return JSON.stringify(backupEnvelope(result.value, now));
}

export function previewBackup(raw: string): Result<ImportPreview> {
  if (new TextEncoder().encode(raw).byteLength > LIMITS.backupBytes) {
    return { ok: false, issues: [{ path: 'backup', message: 'The backup exceeds 12 MB.' }] };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { ok: false, issues: [{ path: 'backup', message: 'This file is not valid JSON.' }] };
  }
  if (!isRecord(parsed) || parsed.format !== 'jeeves-workbench' || parsed.version !== 1) {
    return { ok: false, issues: [{ path: 'backup', message: 'This is not a supported Jeeves workbench backup.' }] };
  }
  if (typeof parsed.exportedAt !== 'number' || !Number.isFinite(parsed.exportedAt) || parsed.exportedAt < 0) {
    return { ok: false, issues: [{ path: 'exportedAt', message: 'The export timestamp is invalid.' }] };
  }
  const result = validateWorkbench(parsed.workspace);
  if (!result.ok) return result;
  const state = result.value;
  const issues = inspectIntegrity(state);
  if (issues.length) return { ok: false, issues };
  if (JSON.stringify(state).length > LIMITS.stateCharacters) {
    return { ok: false, issues: [{ path: 'workspace', message: 'The imported workspace exceeds the local storage budget.' }] };
  }
  const warnings = orphanWarnings(state);
  if (parsed.recordCount !== recordCount(state)) warnings.push('The declared record count differs from the validated contents. Validated contents will be used.');
  if (state.sessions.some(session => session.outcome === 'running')) {
    warnings.push('Running focus sessions will be imported as abandoned so they cannot accidentally resume on another device.');
  }
  return {
    ok: true,
    value: {
      imported: state,
      counts: {
        project: state.projects.length,
        task: state.tasks.length,
        note: state.notes.length,
        source: state.sources.length,
        card: state.cards.length,
        review: state.reviews.length,
        prompt: state.prompts.length,
        session: state.sessions.length,
      },
      warnings,
    },
  };
}

function stopImportedSessions(state: Workbench): Workbench {
  return {
    ...state,
    sessions: state.sessions.map(session => {
      if (session.outcome !== 'running') return session;
      // Last recorded update is the latest evidenced time, not the import time.
      const endedAt = Math.max(session.startedAt, session.pausedAt ?? session.updatedAt);
      return {
        ...session,
        outcome: 'abandoned' as const,
        endedAt,
        pausedAt: null,
        reflection: session.reflection || 'Stopped during backup import; elapsed time after the last saved update is unknown.',
      };
    }),
  };
}

export function replaceFromBackup(current: Workbench, imported: Workbench, context: MutationContext): Workbench {
  const candidate = stopImportedSessions({
    ...imported,
    id: current.id,
    revision: current.revision + 1,
    createdAt: current.createdAt,
    updatedAt: Math.max(current.updatedAt, context.now),
  });
  return validateCandidate(candidate);
}

export function mergeBackup(current: Workbench, imported: Workbench, context: MutationContext): Workbench {
  const safe = stopImportedSessions(imported);
  const mapping = new Map<string, string>();
  const used = new Set([
    current.id,
    ...current.projects.map(item => item.id),
    ...current.tasks.map(item => item.id),
    ...current.notes.map(item => item.id),
    ...current.sources.map(item => item.id),
    ...current.cards.map(item => item.id),
    ...current.reviews.map(item => item.id),
    ...current.prompts.map(item => item.id),
    ...current.sessions.map(item => item.id),
    ...current.events.map(item => item.id),
  ]);
  const newId = (oldId: string): string => {
    const existing = mapping.get(oldId);
    if (existing) return existing;
    let id = context.id();
    let attempts = 0;
    while (used.has(id)) {
      if (++attempts > 20) throw new WorkbenchError('Could not generate unique import IDs.');
      id = context.id();
    }
    used.add(id);
    mapping.set(oldId, id);
    return id;
  };
  const nullable = (id: string | null) => id === null ? null : newId(id);
  const common = <T extends { id: string }>(item: T): T => ({ ...item, id: newId(item.id) });
  const projects = safe.projects.map(project => ({
    ...common(project),
    title: current.projects.some(item => item.title === project.title)
      ? `${project.title.slice(0, LIMITS.title - 11)} (imported)` : project.title,
  }));
  const tasks = safe.tasks.map(task => ({
    ...common(task),
    projectId: newId(task.projectId),
    dependencies: task.dependencies.map(newId),
    noteIds: task.noteIds.map(newId),
    checklist: task.checklist.map(item => ({ ...item, id: newId(item.id) })),
  }));
  const notes = safe.notes.map(note => ({
    ...common(note),
    projectId: newId(note.projectId),
    sourceIds: note.sourceIds.map(newId),
    relatedNoteIds: note.relatedNoteIds.map(newId),
  }));
  const sources = safe.sources.map(source => ({
    ...common(source),
    projectId: newId(source.projectId),
  }));
  const cards = safe.cards.map(card => ({
    ...common(card),
    projectId: newId(card.projectId),
    noteId: nullable(card.noteId),
    sourceIds: card.sourceIds.map(newId),
  }));
  const reviews = safe.reviews.map(review => ({
    ...common(review),
    projectId: newId(review.projectId),
    cardId: newId(review.cardId),
    sessionId: nullable(review.sessionId),
  }));
  const prompts = safe.prompts.map(prompt => ({
    ...common(prompt),
    projectId: nullable(prompt.projectId),
  }));
  const sessions = safe.sessions.map(session => ({
    ...common(session),
    projectId: newId(session.projectId),
    taskId: nullable(session.taskId),
  }));
  // Audit references may refer to deleted records; remap them without recreating those records.
  const events = safe.events.map(item => ({
    ...item,
    id: newId(item.id),
    projectId: nullable(item.projectId),
    entityId: newId(item.entityId),
  }));
  const candidate: Workbench = {
    ...current,
    revision: current.revision + 1,
    updatedAt: Math.max(current.updatedAt, context.now),
    activeProjectId: current.activeProjectId || nullable(safe.activeProjectId),
    projects: [...current.projects, ...projects],
    tasks: [...current.tasks, ...tasks],
    notes: [...current.notes, ...notes],
    sources: [...current.sources, ...sources],
    cards: [...current.cards, ...cards],
    reviews: [...current.reviews, ...reviews].sort((a, b) => a.reviewedAt - b.reviewedAt).slice(-LIMITS.reviews),
    prompts: [...current.prompts, ...prompts],
    sessions: [...current.sessions, ...sessions],
    events: [...current.events, ...events].sort((a, b) => a.at - b.at).slice(-LIMITS.events),
  };
  return validateCandidate(candidate);
}

function validateCandidate(candidate: Workbench): Workbench {
  const result = validateWorkbench(candidate);
  if (!result.ok) throw new WorkbenchError(result.issues.map(issue => `${issue.path}: ${issue.message}`).join('\n'), 'limit');
  const issues = inspectIntegrity(result.value);
  if (issues.length) throw new WorkbenchError(issues.map(issue => issue.message).join('\n'));
  if (JSON.stringify(result.value).length > LIMITS.stateCharacters) throw new WorkbenchError('The combined workspace exceeds the local storage budget.', 'limit');
  return result.value;
}

export function projectBackup(state: Workbench, projectId: string): Workbench {
  const project = state.projects.find(item => item.id === projectId);
  if (!project) throw new WorkbenchError('The project no longer exists.', 'missing');
  return {
    ...state,
    activeProjectId: projectId,
    projects: [project],
    tasks: state.tasks.filter(item => item.projectId === projectId),
    notes: state.notes.filter(item => item.projectId === projectId),
    sources: state.sources.filter(item => item.projectId === projectId),
    cards: state.cards.filter(item => item.projectId === projectId),
    reviews: state.reviews.filter(item => item.projectId === projectId),
    prompts: state.prompts.filter(item => item.projectId === projectId),
    sessions: state.sessions.filter(item => item.projectId === projectId),
    events: state.events.filter(item => item.projectId === projectId),
  };
}
