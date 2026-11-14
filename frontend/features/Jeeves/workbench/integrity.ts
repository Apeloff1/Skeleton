import type { ValidationIssue, Workbench } from './types';
import { dependencyCycle, isTerminal } from './planning';

/** Cross-record checks are separate from field parsing so imports and mutations share the same rules. */
export function inspectIntegrity(state: Workbench): ValidationIssue[] {
  const issues: ValidationIssue[] = [];
  const tasks = new Map(state.tasks.map(item => [item.id, item]));
  const notes = new Map(state.notes.map(item => [item.id, item]));
  const sources = new Map(state.sources.map(item => [item.id, item]));
  const cards = new Map(state.cards.map(item => [item.id, item]));
  const sessions = new Map(state.sessions.map(item => [item.id, item]));
  const issue = (path: string, message: string) => {
    if (issues.length < 100) issues.push({ path, message });
  };
  const link = (
    id: string,
    records: Map<string, { projectId: string }>,
    projectId: string,
    path: string,
  ) => {
    const target = records.get(id);
    if (!target) issue(path, 'Linked record does not exist.');
    else if (target.projectId !== projectId) issue(path, 'Linked record belongs to another project.');
  };
  for (const task of state.tasks) {
    for (const id of task.dependencies) link(id, tasks, task.projectId, `tasks.${task.id}.dependencies`);
    for (const id of task.noteIds) link(id, notes, task.projectId, `tasks.${task.id}.noteIds`);
    if (task.dependencies.includes(task.id)) issue(task.id, 'A task cannot depend on itself.');
    if (new Set(task.checklist.map(item => item.id)).size !== task.checklist.length) {
      issue(task.id, 'Checklist IDs must be unique within a task.');
    }
    if (task.status === 'done' && task.completedAt === null) issue(task.id, 'Completed tasks need a completion timestamp.');
    if (task.status !== 'done' && task.completedAt !== null) issue(task.id, 'Only completed tasks may have a completion timestamp.');
    if (task.status === 'done' && task.checklist.some(item => !item.done)) issue(task.id, 'A completed task has unfinished checklist items.');
    if (task.status === 'done' && task.dependencies.some(id => tasks.get(id)?.status !== 'done')) issue(task.id, 'A completed task has unfinished dependencies.');
  }
  const cycle = dependencyCycle(state.tasks);
  if (cycle) issue('tasks', `Dependency cycle: ${cycle.join(' → ')}`);
  for (const note of state.notes) {
    for (const id of note.sourceIds) link(id, sources, note.projectId, `notes.${note.id}.sourceIds`);
    for (const id of note.relatedNoteIds) link(id, notes, note.projectId, `notes.${note.id}.relatedNoteIds`);
    if (note.relatedNoteIds.includes(note.id)) issue(note.id, 'A note cannot link to itself.');
  }
  for (const card of state.cards) {
    if (card.noteId) link(card.noteId, notes, card.projectId, `cards.${card.id}.noteId`);
    for (const id of card.sourceIds) link(id, sources, card.projectId, `cards.${card.id}.sourceIds`);
    const schedule = card.schedule;
    if (schedule.state === 'suspended' && schedule.suspendedFrom === null) issue(card.id, 'Suspended cards must remember their prior state.');
    if (schedule.state !== 'suspended' && schedule.suspendedFrom !== null) issue(card.id, 'Only suspended cards may carry a suspended state.');
    if (schedule.lastReviewedAt === null && schedule.repetitions > 0) issue(card.id, 'Reviewed cards need a last review timestamp.');
  }
  for (const review of state.reviews) {
    link(review.cardId, cards, review.projectId, `reviews.${review.id}.cardId`);
    if (review.sessionId) link(review.sessionId, sessions, review.projectId, `reviews.${review.id}.sessionId`);
    if (review.previous.state === 'suspended') issue(review.id, 'Suspended cards cannot be reviewed.');
    if (review.next.lastReviewedAt !== review.reviewedAt) issue(review.id, 'Review timestamp does not match its schedule.');
  }
  let running = 0;
  for (const session of state.sessions) {
    if (session.taskId) link(session.taskId, tasks, session.projectId, `sessions.${session.id}.taskId`);
    if (session.outcome === 'running') {
      running++;
      if (session.endedAt !== null) issue(session.id, 'Running sessions cannot have an end time.');
    } else {
      if (session.endedAt === null) issue(session.id, 'Finished sessions need an end time.');
      if (session.pausedAt !== null) issue(session.id, 'Finished sessions cannot remain paused.');
    }
    if (session.endedAt !== null && session.endedAt < session.startedAt) issue(session.id, 'Session end time precedes its start.');
    if (session.pausedAt !== null && session.pausedAt < session.startedAt) issue(session.id, 'Pause time precedes session start.');
    if (session.endedAt !== null && session.pausedMilliseconds > session.endedAt - session.startedAt) {
      issue(session.id, 'Paused time exceeds the session duration.');
    }
  }
  if (running > 1) issue('sessions', 'Only one focus session can run at a time.');
  for (const prompt of state.prompts) {
    const keys = prompt.variables.map(variable => variable.key);
    if (new Set(keys).size !== keys.length) issue(prompt.id, 'Prompt variable keys must be unique.');
    const placeholders = [...prompt.template.matchAll(/\{\{\s*([a-z][a-z0-9_]*)\s*\}\}/g)].map(match => match[1]);
    for (const key of placeholders) {
      if (!keys.includes(key)) issue(prompt.id, `Missing definition for prompt variable ${key}.`);
    }
  }
  for (const collection of [state.projects, state.tasks, state.notes, state.sources, state.cards, state.prompts, state.sessions]) {
    for (const item of collection) {
      if (item.updatedAt < item.createdAt) issue(item.id, 'Updated timestamp precedes creation.');
    }
  }
  return issues;
}

export interface DeletionImpact {
  tasks: number;
  notes: number;
  sources: number;
  cards: number;
  reviews: number;
  prompts: number;
  sessions: number;
  total: number;
  runningSession: boolean;
}

export function projectDeletionImpact(state: Workbench, projectId: string): DeletionImpact {
  const count = (items: { projectId: string | null }[]) => items.filter(item => item.projectId === projectId).length;
  const values = {
    tasks: count(state.tasks),
    notes: count(state.notes),
    sources: count(state.sources),
    cards: count(state.cards),
    reviews: count(state.reviews),
    prompts: count(state.prompts),
    sessions: count(state.sessions),
  };
  return {
    ...values,
    total: Object.values(values).reduce((sum, value) => sum + value, 0),
    runningSession: state.sessions.some(session => session.projectId === projectId && session.outcome === 'running'),
  };
}

export function orphanWarnings(state: Workbench): string[] {
  const warnings: string[] = [];
  const usedSources = new Set([...state.notes.flatMap(note => note.sourceIds), ...state.cards.flatMap(card => card.sourceIds)]);
  const unusedSources = state.sources.filter(source => !usedSources.has(source.id));
  const unsupportedNotes = state.notes.filter(note => note.confidence === 'supported' && note.sourceIds.length === 0);
  const lonelyTasks = state.tasks.filter(task => !isTerminal(task) && !task.description.trim() && task.checklist.length === 0);
  if (unusedSources.length) warnings.push(`${unusedSources.length} source(s) are not linked to notes or cards.`);
  if (unsupportedNotes.length) warnings.push(`${unsupportedNotes.length} supported note(s) do not cite a source.`);
  if (lonelyTasks.length) warnings.push(`${lonelyTasks.length} task(s) have no description or checklist.`);
  return warnings;
}
