import type {
  Dashboard,
  FocusSession,
  Note,
  NoteFilter,
  Project,
  Task,
  TaskFilter,
  TaskStatus,
  Workbench,
} from './types';
import { buildReviewQueue, DAY, localDayKey, MINUTE, addCalendarDays, dayStart } from './review';
import { canStart, isTerminal, PRIORITY_WEIGHT, unmetDependencies } from './planning';

export function selectedProject(state: Workbench): Project | null {
  return state.projects.find(project => project.id === state.activeProjectId) || null;
}

export function projectsByRecency(state: Workbench, includeArchived = false): Project[] {
  return state.projects.filter(project => includeArchived || project.status !== 'archived')
    .sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.updatedAt - a.updatedAt || a.id.localeCompare(b.id));
}

export function projectTasks(state: Workbench, projectId: string): Task[] {
  return state.tasks.filter(task => task.projectId === projectId);
}

export function taskProgress(task: Task): number {
  if (task.status === 'done') return 100;
  if (!task.checklist.length) return 0;
  return Math.round(task.checklist.filter(item => item.done).length / task.checklist.length * 100);
}

export function filterTasks(state: Workbench, projectId: string, filter: TaskFilter, now: number): Task[] {
  const query = filter.query?.trim().toLocaleLowerCase() || '';
  const today = localDayKey(now);
  const week = localDayKey(addCalendarDays(now, 7));
  const tasks = projectTasks(state, projectId).filter(task => {
    if (filter.statuses?.length && !filter.statuses.includes(task.status)) return false;
    if (filter.priorities?.length && !filter.priorities.includes(task.priority)) return false;
    if (filter.tag && !task.tags.includes(filter.tag)) return false;
    if (query && ![task.title, task.description, ...task.tags, ...task.checklist.map(item => item.text)].some(value => value.toLocaleLowerCase().includes(query))) return false;
    if (filter.due === 'none' && task.dueDate !== null) return false;
    if (filter.due === 'overdue' && (!task.dueDate || task.dueDate >= today || isTerminal(task))) return false;
    if (filter.due === 'today' && task.dueDate !== today) return false;
    if (filter.due === 'week' && (!task.dueDate || task.dueDate < today || task.dueDate > week)) return false;
    return true;
  });
  const fallback = (a: Task, b: Task) => a.order - b.order || a.id.localeCompare(b.id);
  return tasks.sort((a, b) => {
    switch (filter.sort) {
      case 'priority': return PRIORITY_WEIGHT[b.priority] - PRIORITY_WEIGHT[a.priority] || fallback(a, b);
      case 'due': return (a.dueDate || '9999').localeCompare(b.dueDate || '9999') || fallback(a, b);
      case 'updated': return b.updatedAt - a.updatedAt || fallback(a, b);
      case 'estimate': return a.estimateMinutes - b.estimateMinutes || fallback(a, b);
      default: return fallback(a, b);
    }
  });
}

export function taskColumns(tasks: Task[]): Record<TaskStatus, Task[]> {
  const columns: Record<TaskStatus, Task[]> = {
    inbox: [],
    ready: [],
    doing: [],
    blocked: [],
    done: [],
    cancelled: [],
  };
  for (const task of tasks) columns[task.status].push(task);
  return columns;
}

export function filterNotes(state: Workbench, projectId: string, filter: NoteFilter): Note[] {
  const query = filter.query?.trim().toLocaleLowerCase() || '';
  return state.notes.filter(note => {
    if (note.projectId !== projectId) return false;
    if (note.archived !== (filter.archived || false)) return false;
    if (filter.kind && note.kind !== filter.kind) return false;
    if (filter.confidence && note.confidence !== filter.confidence) return false;
    if (filter.tag && !note.tags.includes(filter.tag)) return false;
    if (query && ![note.title, note.body, ...note.tags].some(value => value.toLocaleLowerCase().includes(query))) return false;
    return true;
  }).sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.updatedAt - a.updatedAt || a.id.localeCompare(b.id));
}

export function elapsedFocus(session: FocusSession, now: number): number {
  const end = session.endedAt ?? session.pausedAt ?? now;
  return Math.max(0, end - session.startedAt - session.pausedMilliseconds);
}

export function remainingFocus(session: FocusSession, now: number): number {
  return Math.max(0, session.plannedMinutes * MINUTE - elapsedFocus(session, now));
}

export function formatDuration(milliseconds: number): string {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}

export function formatMinutes(minutes: number): string {
  const rounded = Math.max(0, Math.round(minutes));
  if (rounded < 60) return `${rounded}m`;
  const hours = Math.floor(rounded / 60);
  const remainder = rounded % 60;
  return remainder ? `${hours}h ${remainder}m` : `${hours}h`;
}

export function relativeTime(timestamp: number, now: number): string {
  const delta = now - timestamp;
  if (delta < 0) return 'in the future';
  if (delta < MINUTE) return 'just now';
  if (delta < 60 * MINUTE) return `${Math.floor(delta / MINUTE)}m ago`;
  if (delta < DAY) return `${Math.floor(delta / (60 * MINUTE))}h ago`;
  if (delta < 7 * DAY) return `${Math.floor(delta / DAY)}d ago`;
  return new Date(timestamp).toLocaleDateString();
}

export function dashboard(state: Workbench, projectId: string, now: number): Dashboard | null {
  const project = state.projects.find(item => item.id === projectId);
  if (!project) return null;
  const tasks = projectTasks(state, projectId);
  const counted = tasks.filter(task => task.status !== 'cancelled');
  const completed = tasks.filter(task => task.status === 'done');
  const notes = state.notes.filter(note => note.projectId === projectId && !note.archived);
  const today = localDayKey(now);
  const queue = buildReviewQueue(state, projectId, now);
  const focus = state.sessions.filter(session => session.projectId === projectId && session.outcome === 'completed');
  return {
    project,
    taskCount: tasks.length,
    completedTasks: completed.length,
    overdueTasks: tasks.filter(task => !isTerminal(task) && task.dueDate && task.dueDate < today).length,
    blockedTasks: tasks.filter(task => !isTerminal(task) && (task.status === 'blocked' || unmetDependencies(task, tasks).length > 0)).length,
    estimatedMinutes: tasks.filter(task => !isTerminal(task)).reduce((sum, task) => sum + task.estimateMinutes, 0),
    focusMinutes: Math.round(focus.reduce((sum, session) => sum + elapsedFocus(session, now), 0) / MINUTE),
    notes: notes.length,
    sources: state.sources.filter(source => source.projectId === projectId).length,
    cards: state.cards.filter(card => card.projectId === projectId).length,
    dueCards: queue.cards.length,
    reviewedToday: state.reviews.filter(review => review.projectId === projectId && localDayKey(review.reviewedAt) === today).length,
    completionPercent: counted.length ? Math.round(completed.length / counted.length * 100) : 0,
    nextTasks: tasks.filter(task => canStart(task, tasks)).sort((a, b) => PRIORITY_WEIGHT[b.priority] - PRIORITY_WEIGHT[a.priority] || a.order - b.order).slice(0, 5),
    recentNotes: [...notes].sort((a, b) => b.updatedAt - a.updatedAt).slice(0, 5),
    recentEvents: state.events.filter(event => event.projectId === projectId).slice(-10).reverse(),
  };
}

export interface ActivityDay {
  date: string;
  completedTasks: number;
  focusMinutes: number;
  reviews: number;
  notesCreated: number;
}

export function activityDays(state: Workbench, projectId: string, now: number, days = 14): ActivityDay[] {
  const count = Math.min(366, Math.max(1, Math.floor(days)));
  return Array.from({ length: count }, (_, index) => {
    const time = addCalendarDays(now, index - count + 1);
    const start = dayStart(time);
    const end = Math.min(now + 1, dayStart(addCalendarDays(time, 1)));
    const date = localDayKey(time);
    const sessions = state.sessions.filter(session => session.projectId === projectId && session.outcome === 'completed' && session.endedAt !== null && localDayKey(session.endedAt) === date);
    return {
      date,
      completedTasks: state.tasks.filter(task => task.projectId === projectId && task.completedAt !== null && task.completedAt >= start && task.completedAt < end).length,
      focusMinutes: Math.round(sessions.reduce((sum, session) => sum + elapsedFocus(session, now), 0) / MINUTE),
      reviews: state.reviews.filter(review => review.projectId === projectId && review.reviewedAt >= start && review.reviewedAt < end).length,
      notesCreated: state.notes.filter(note => note.projectId === projectId && note.createdAt >= start && note.createdAt < end).length,
    };
  });
}

export function projectTags(state: Workbench, projectId: string): { tag: string; count: number }[] {
  const counts = new Map<string, number>();
  const records = [...state.tasks, ...state.notes, ...state.cards, ...state.sources].filter(item => item.projectId === projectId);
  for (const record of records) {
    for (const tag of record.tags) counts.set(tag, (counts.get(tag) || 0) + 1);
  }
  return [...counts].map(([tag, count]) => ({ tag, count })).sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag));
}

export function noteBacklinks(state: Workbench, noteId: string) {
  return {
    notes: state.notes.filter(note => note.relatedNoteIds.includes(noteId)),
    tasks: state.tasks.filter(task => task.noteIds.includes(noteId)),
    cards: state.cards.filter(card => card.noteId === noteId),
  };
}

export function sourceBacklinks(state: Workbench, sourceId: string) {
  return {
    notes: state.notes.filter(note => note.sourceIds.includes(sourceId)),
    cards: state.cards.filter(card => card.sourceIds.includes(sourceId)),
  };
}

export function workbenchCounts(state: Workbench): Record<string, number> {
  return {
    projects: state.projects.length,
    tasks: state.tasks.length,
    notes: state.notes.length,
    sources: state.sources.length,
    cards: state.cards.length,
    reviews: state.reviews.length,
    prompts: state.prompts.length,
    sessions: state.sessions.length,
    events: state.events.length,
  };
}

export function capacityForecast(state: Workbench, projectId: string): { weeks: number | null; minutes: number; unestimated: number } {
  const project = state.projects.find(item => item.id === projectId);
  const active = state.tasks.filter(task => task.projectId === projectId && !isTerminal(task));
  const minutes = active.reduce((sum, task) => sum + task.estimateMinutes, 0);
  return {
    weeks: project?.weeklyMinutes ? Math.ceil(minutes / project.weeklyMinutes) : null,
    minutes,
    unestimated: active.filter(task => !task.estimateMinutes).length,
  };
}
