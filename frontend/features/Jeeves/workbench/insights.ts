import type { Note, Project, ReviewGrade, Task, Workbench } from './types';
import { addCalendarDays, dayStart, localDayKey, MINUTE } from './review';
import { elapsedFocus, formatMinutes } from './selectors';
import { canStart, dependants, isTerminal } from './planning';
import { WorkbenchError } from './validation';

export interface WeekWindow {
  start: number;
  end: number;
  label: string;
}

export interface WeekMetrics {
  window: WeekWindow;
  completedTasks: Task[];
  createdNotes: Note[];
  focusMinutes: number;
  completedSessions: number;
  abandonedSessions: number;
  reviewedCards: number;
  reviewCount: number;
  grades: Record<ReviewGrade, number>;
  reflections: { id: string; text: string; endedAt: number }[];
}

export interface EvidenceGap {
  noteId: string;
  title: string;
  reason: 'unsupported' | 'unverified' | 'contradicted' | 'stale';
  detail: string;
}

export interface BlockerChain {
  taskId: string;
  title: string;
  blockedBy: string[];
  missing: string[];
  downstream: number;
  manual: boolean;
}

export interface WeeklyReview {
  project: Project;
  current: WeekMetrics;
  previous: WeekMetrics;
  focusChange: number;
  completionChange: number;
  openTasks: number;
  overdueTasks: Task[];
  staleTasks: Task[];
  readyTasks: Task[];
  blockers: BlockerChain[];
  evidenceGaps: EvidenceGap[];
  uncitedSources: string[];
  prompts: string[];
}

export function weekWindow(now: number, weekStartsOn: 'monday' | 'sunday', offset = 0): WeekWindow {
  const day = new Date(now).getDay();
  const distance = weekStartsOn === 'monday' ? (day + 6) % 7 : day;
  const start = dayStart(addCalendarDays(now, -distance + offset * 7));
  const end = dayStart(addCalendarDays(start, 7));
  return { start, end, label: `${localDayKey(start)} – ${localDayKey(addCalendarDays(end, -1))}` };
}

export function weekMetrics(state: Workbench, projectId: string, window: WeekWindow, now: number): WeekMetrics {
  const inWindow = (time: number) => time >= window.start && time < window.end && time <= now;
  const tasks = state.tasks.filter(task => task.projectId === projectId && task.status === 'done' && task.completedAt !== null && inWindow(task.completedAt));
  const notes = state.notes.filter(note => note.projectId === projectId && inWindow(note.createdAt));
  const sessions = state.sessions.filter(session => session.projectId === projectId && session.endedAt !== null && inWindow(session.endedAt));
  const completed = sessions.filter(session => session.outcome === 'completed');
  const reviews = state.reviews.filter(review => review.projectId === projectId && inWindow(review.reviewedAt));
  const grades: Record<ReviewGrade, number> = { again: 0, hard: 0, good: 0, easy: 0 };
  for (const review of reviews) grades[review.grade]++;
  return {
    window,
    completedTasks: [...tasks].sort((a, b) => (b.completedAt || 0) - (a.completedAt || 0)),
    createdNotes: [...notes].sort((a, b) => b.createdAt - a.createdAt),
    focusMinutes: Math.round(completed.reduce((sum, session) => sum + elapsedFocus(session, now), 0) / MINUTE),
    completedSessions: completed.length,
    abandonedSessions: sessions.filter(session => session.outcome === 'abandoned').length,
    reviewedCards: new Set(reviews.map(review => review.cardId)).size,
    reviewCount: reviews.length,
    grades,
    reflections: sessions.filter(session => session.reflection.trim()).map(session => ({ id: session.id, text: session.reflection, endedAt: session.endedAt! })),
  };
}

export function blockerChains(tasks: Task[]): BlockerChain[] {
  const byId = new Map(tasks.map(task => [task.id, task]));
  const results: BlockerChain[] = [];
  for (const task of tasks) {
    if (isTerminal(task)) continue;
    const pending = [...task.dependencies];
    const seen = new Set<string>();
    const blockedBy: string[] = [];
    const missing: string[] = [];
    while (pending.length) {
      const id = pending.pop()!;
      if (seen.has(id)) continue;
      seen.add(id);
      const dependency = byId.get(id);
      if (!dependency) { missing.push(id); continue; }
      if (dependency.status === 'done') continue;
      blockedBy.push(id);
      pending.push(...dependency.dependencies);
    }
    if (blockedBy.length || missing.length || task.status === 'blocked') {
      results.push({
        taskId: task.id,
        title: task.title,
        blockedBy,
        missing,
        downstream: dependants(task.id, tasks, true).filter(item => !isTerminal(item)).length,
        manual: task.status === 'blocked',
      });
    }
  }
  return results.sort((a, b) => b.downstream - a.downstream || b.blockedBy.length - a.blockedBy.length || a.title.localeCompare(b.title));
}

export function evidenceGaps(state: Workbench, projectId: string, now: number): EvidenceGap[] {
  const cutoff = addCalendarDays(now, -30);
  const gaps: EvidenceGap[] = [];
  for (const note of state.notes.filter(item => item.projectId === projectId && !item.archived)) {
    if (note.confidence === 'contradicted') {
      gaps.push({ noteId: note.id, title: note.title, reason: 'contradicted', detail: 'Recorded as contradicted. Update the conclusion or keep the contradiction explicit.' });
    } else if (note.confidence === 'supported' && !note.sourceIds.length) {
      gaps.push({ noteId: note.id, title: note.title, reason: 'unsupported', detail: 'Marked supported, but no source is linked.' });
    } else if (note.confidence === 'unverified') {
      gaps.push({ noteId: note.id, title: note.title, reason: 'unverified', detail: 'No verification has been recorded yet.' });
    } else if (note.kind === 'experiment' && note.updatedAt < cutoff) {
      gaps.push({ noteId: note.id, title: note.title, reason: 'stale', detail: 'This experiment has not been updated for 30 days. Record a result or a next step.' });
    }
  }
  return gaps;
}

export function weeklyReview(state: Workbench, projectId: string, now: number, offset = 0): WeeklyReview {
  const project = state.projects.find(item => item.id === projectId);
  if (!project) throw new WorkbenchError('The project no longer exists.', 'missing');
  if (!Number.isInteger(offset) || offset > 0 || offset < -52) throw new WorkbenchError('Choose one of the last 53 weeks.');
  const current = weekMetrics(state, projectId, weekWindow(now, state.preferences.weekStartsOn, offset), now);
  const previous = weekMetrics(state, projectId, weekWindow(now, state.preferences.weekStartsOn, offset - 1), now);
  const tasks = state.tasks.filter(task => task.projectId === projectId);
  const open = tasks.filter(task => !isTerminal(task));
  const today = localDayKey(now);
  const staleBefore = addCalendarDays(now, -14);
  const cited = new Set([
    ...state.notes.filter(note => note.projectId === projectId).flatMap(note => note.sourceIds),
    ...state.cards.filter(card => card.projectId === projectId).flatMap(card => card.sourceIds),
  ]);
  const overdueTasks = open.filter(task => task.dueDate && task.dueDate < today);
  const staleTasks = open.filter(task => task.updatedAt < staleBefore);
  const blockers = blockerChains(tasks);
  const gaps = evidenceGaps(state, projectId, now);
  const prompts = [
    current.completedTasks.length ? 'Which completed task most improved the playable experience, and how did you verify it?' : 'What is the smallest verifiable outcome you can finish next week?',
    current.abandonedSessions ? 'What interrupted focus, and which interruption can you reduce?' : 'Did your focus sessions work on the most important uncertainty?',
    blockers.length ? 'Which prerequisite would unlock the most useful next work?' : 'Which assumption should you test before adding more scope?',
    gaps.length ? 'Which note needs evidence, correction or an experiment result?' : 'Which observation deserves to become a reusable note or study card?',
    overdueTasks.length ? 'Which overdue task should be rescheduled, reduced or cancelled?' : 'Does your next week fit the time you actually have available?',
  ];
  return {
    project, current, previous,
    focusChange: current.focusMinutes - previous.focusMinutes,
    completionChange: current.completedTasks.length - previous.completedTasks.length,
    openTasks: open.length,
    overdueTasks,
    staleTasks,
    readyTasks: open.filter(task => canStart(task, tasks)),
    blockers,
    evidenceGaps: gaps,
    uncitedSources: state.sources.filter(source => source.projectId === projectId && !cited.has(source.id)).map(source => source.id),
    prompts,
  };
}

export function weeklyReviewMarkdown(review: WeeklyReview): string {
  const lines = [
    `# Weekly review: ${review.project.title.replace(/[\r\n]/g, ' ')}`,
    '',
    review.current.window.label,
    '',
    `Goal: ${review.project.goal || 'Not recorded'}`,
    '',
    '## Recorded activity',
    '',
    `- Completed tasks: ${review.current.completedTasks.length}`,
    `- Completed focus: ${formatMinutes(review.current.focusMinutes)} in ${review.current.completedSessions} sessions`,
    `- Abandoned sessions: ${review.current.abandonedSessions}`,
    `- Study: ${review.current.reviewCount} answers across ${review.current.reviewedCards} cards`,
    `- New notes: ${review.current.createdNotes.length}`,
    '',
    '## Completed work',
    '',
    ...review.current.completedTasks.map(task => `- ${task.title}`),
    '',
    '## Reflections',
    '',
    ...review.current.reflections.map(item => `### ${new Date(item.endedAt).toLocaleDateString()}\n\n${item.text}\n`),
    '## Current unresolved work',
    '',
    `- Open tasks: ${review.openTasks}`,
    `- Overdue tasks: ${review.overdueTasks.length}`,
    `- Blocked tasks: ${review.blockers.length}`,
    `- Notes needing review: ${review.evidenceGaps.length}`,
    '',
    '## Reflection questions',
    '',
    ...review.prompts.map(prompt => `- ${prompt}`),
    '',
    'Activity is calculated from retained local records. Current unresolved work reflects today, even when viewing a past week. Review grades are self-assessments, not measured retention.',
  ];
  return lines.join('\n');
}
