import type { Note, Project, Source, StudyCard, Task, Workbench } from './types';
import { elapsedFocus, formatMinutes, taskProgress } from './selectors';
import { MINUTE } from './review';
import { WorkbenchError } from './validation';

function title(value: string): string {
  return value.replace(/[\r\n]/g, ' ').trim();
}

function section(name: string, body: string): string {
  return `\n## ${name}\n\n${body}\n`;
}

export function csvCell(value: string | number | boolean | null): string {
  let text = value === null ? '' : String(value);
  // Neutralize spreadsheet formulas while retaining a readable text value.
  if (/^[\s]*[=+@-]/.test(text) || /^[\t\r]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

function csv(rows: (string | number | boolean | null)[][]): string {
  return rows.map(row => row.map(csvCell).join(',')).join('\r\n');
}

export function tasksCsv(tasks: Task[], projects: Project[]): string {
  const names = new Map(projects.map(project => [project.id, project.title]));
  const taskNames = new Map(tasks.map(task => [task.id, task.title]));
  return csv([
    ['Project', 'Title', 'Status', 'Priority', 'Estimate minutes', 'Due date', 'Progress percent', 'Dependencies', 'Tags', 'Description'],
    ...tasks.map(task => [
      names.get(task.projectId) || task.projectId,
      task.title,
      task.status,
      task.priority,
      task.estimateMinutes,
      task.dueDate,
      taskProgress(task),
      task.dependencies.map(id => taskNames.get(id) || id).join('; '),
      task.tags.join('; '),
      task.description,
    ]),
  ]);
}

export function cardsCsv(cards: StudyCard[]): string {
  return csv([
    ['Question', 'Answer', 'Hint', 'Explanation', 'Tags', 'State', 'Next review', 'Repetitions', 'Lapses'],
    ...cards.map(card => [
      card.question,
      card.answer,
      card.hint,
      card.explanation,
      card.tags.join('; '),
      card.schedule.state,
      new Date(card.schedule.dueAt).toISOString(),
      card.schedule.repetitions,
      card.schedule.lapses,
    ]),
  ]);
}

export function noteMarkdown(note: Note, sources: Source[] = []): string {
  const citations = note.sourceIds.map(id => sources.find(source => source.id === id)).filter((source): source is Source => !!source);
  const metadata = [
    `Kind: ${note.kind}`,
    `Confidence: ${note.confidence}`,
    `Updated: ${new Date(note.updatedAt).toISOString()}`,
    note.tags.length ? `Tags: ${note.tags.join(', ')}` : '',
  ].filter(Boolean).join('  \n');
  const references = citations.map((source, index) => [
    `${index + 1}. ${title(source.title)}`,
    source.author ? `   Author: ${source.author}` : '',
    source.locator ? `   Location: ${source.locator}` : '',
    source.excerpt ? `   Excerpt: ${source.excerpt.replace(/\n/g, '\n   ')}` : '',
  ].filter(Boolean).join('\n')).join('\n\n');
  return `# ${title(note.title)}\n\n${metadata}\n\n${note.body}\n`
    + (references ? section('Sources', references) : '');
}

export function projectMarkdown(state: Workbench, projectId: string, now: number): string {
  const project = state.projects.find(item => item.id === projectId);
  if (!project) throw new WorkbenchError('The project no longer exists.', 'missing');
  const tasks = state.tasks.filter(item => item.projectId === projectId).sort((a, b) => a.order - b.order);
  const notes = state.notes.filter(item => item.projectId === projectId && !item.archived);
  const sources = state.sources.filter(item => item.projectId === projectId);
  const sessions = state.sessions.filter(item => item.projectId === projectId && item.outcome === 'completed');
  const cards = state.cards.filter(item => item.projectId === projectId);
  const taskText = tasks.map(task => {
    const completed = task.status === 'done' ? 'x' : ' ';
    const attributes = [task.status, task.priority, formatMinutes(task.estimateMinutes), task.dueDate ? `due ${task.dueDate}` : ''].filter(Boolean);
    return `- [${completed}] ${title(task.title)} (${attributes.join(' · ')})`
      + (task.description ? `\n  ${task.description.replace(/\n/g, '\n  ')}` : '')
      + task.checklist.map(item => `\n  - [${item.done ? 'x' : ' '}] ${title(item.text)}`).join('');
  }).join('\n\n');
  const focused = sessions.reduce((sum, session) => sum + elapsedFocus(session, now), 0);
  return [
    `# ${title(project.title)}\n\nExported ${new Date(now).toISOString()}\n`,
    `Status: ${project.status}  \nEngine: ${project.engine || 'Not specified'}  \nExperience: ${project.experience}\n`,
    section('Goal', project.goal || 'Not specified'),
    section('Summary', project.summary || 'Not specified'),
    section('Project context', project.context || 'No additional context'),
    section('Tasks', taskText || 'No tasks'),
    section('Learning and focus', `${cards.length} study cards\n${sessions.length} completed focus sessions\n${formatMinutes(focused / MINUTE)} recorded focus time`),
    section('Notes', notes.map(note => `### ${title(note.title)}\n\nConfidence: ${note.confidence}\n\n${note.body}`).join('\n\n---\n\n') || 'No notes'),
    section('Sources', sources.map(source => `- ${title(source.title)}${source.locator ? ` — ${source.locator}` : ''}`).join('\n') || 'No sources'),
    '\nThis export reflects manually recorded project data. It does not certify completion, correctness or source accuracy.\n',
  ].join('\n');
}

export function studyMarkdown(cards: StudyCard[]): string {
  return '# Jeeves study cards\n\n' + cards.map((card, index) => [
    `## ${index + 1}. ${title(card.question)}`,
    card.hint ? `Hint: ${card.hint}` : '',
    '### Answer',
    card.answer,
    card.explanation ? `### Explanation\n\n${card.explanation}` : '',
    card.tags.length ? `Tags: ${card.tags.join(', ')}` : '',
  ].filter(Boolean).join('\n\n')).join('\n\n---\n\n');
}

export function focusCsv(state: Workbench, projectId: string, now: number): string {
  const taskNames = new Map(state.tasks.map(task => [task.id, task.title]));
  return csv([
    ['Started', 'Ended', 'Outcome', 'Task', 'Planned minutes', 'Recorded active minutes', 'Reflection'],
    ...state.sessions.filter(session => session.projectId === projectId).map(session => [
      new Date(session.startedAt).toISOString(),
      session.endedAt === null ? '' : new Date(session.endedAt).toISOString(),
      session.outcome,
      session.taskId ? taskNames.get(session.taskId) || '' : '',
      session.plannedMinutes,
      Math.round(elapsedFocus(session, now) / MINUTE),
      session.reflection,
    ]),
  ]);
}

export function sourceBibliography(state: Workbench, projectId: string): string {
  const sources = state.sources.filter(source => source.projectId === projectId).sort((a, b) => a.title.localeCompare(b.title));
  return '# Project sources\n\n' + sources.map((source, index) => {
    const lines = [
      `## ${index + 1}. ${title(source.title)}`,
      `Kind: ${source.kind}`,
      source.author ? `Author: ${source.author}` : '',
      source.locator ? `Location: ${source.locator}` : '',
      `Recorded access: ${new Date(source.accessedAt).toISOString()}`,
      source.excerpt ? `### Recorded excerpt\n\n${source.excerpt}` : '',
    ];
    return lines.filter(Boolean).join('\n\n');
  }).join('\n\n---\n\n');
}
