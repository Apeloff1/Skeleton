import type { ChatHandoff, ContextBundle, ContextSection, ContextSelection, MutationContext, Workbench } from './types';
import { isTerminal } from './planning';
import { assertInteger, assertText, isRecord, WorkbenchError } from './validation';
import { LIMITS } from './types';

function heading(value: string): string {
  return value.replace(/[\r\n\[\]]/g, ' ').trim();
}

export function defaultContextSelection(state: Workbench, projectId: string): ContextSelection {
  const notes = state.notes.filter(note => note.projectId === projectId && !note.archived)
    .sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.updatedAt - a.updatedAt);
  const tasks = state.tasks.filter(task => task.projectId === projectId &&
    (state.preferences.includeCompletedTasks || !isTerminal(task)))
    .sort((a, b) => Number(b.status === 'doing') - Number(a.status === 'doing') || a.order - b.order);
  const noteIds = notes.slice(0, 4).map(note => note.id);
  const sourceIds = state.preferences.includeSourcesInContext
    ? [...new Set(notes.filter(note => noteIds.includes(note.id)).flatMap(note => note.sourceIds))].slice(0, 5)
    : [];
  return {
    projectId,
    includeProject: true,
    noteIds,
    taskIds: tasks.slice(0, 5).map(task => task.id),
    sourceIds,
    maxCharacters: 4000,
  };
}

export function buildContext(state: Workbench, selection: ContextSelection): ContextBundle {
  assertInteger(selection.maxCharacters, 'Context budget', 200, 4000);
  const project = state.projects.find(item => item.id === selection.projectId);
  if (!project) throw new WorkbenchError('Choose a project before building context.', 'missing');
  const candidates: ContextSection[] = [];
  const omitted: string[] = [];
  if (selection.includeProject) {
    candidates.push({
      id: project.id,
      kind: 'project',
      label: `Project: ${heading(project.title)}`,
      truncated: false,
      text: [
        `Goal: ${project.goal || 'Not specified'}`,
        project.engine ? `Engine: ${project.engine}` : '',
        `Experience: ${project.experience}`,
        project.summary,
        project.context,
      ].filter(Boolean).join('\n'),
    });
  }
  for (const id of [...new Set(selection.taskIds)]) {
    const task = state.tasks.find(item => item.id === id && item.projectId === project.id);
    if (!task) {
      omitted.push(`Task ${id}: missing or belongs to another project`);
      continue;
    }
    candidates.push({
      id,
      kind: 'task',
      label: `Task: ${heading(task.title)}`,
      truncated: false,
      text: [
        `Status: ${task.status}; priority: ${task.priority}`,
        task.description,
        ...task.checklist.map(item => `${item.done ? '[x]' : '[ ]'} ${item.text}`),
      ].filter(Boolean).join('\n'),
    });
  }
  for (const id of [...new Set(selection.noteIds)]) {
    const note = state.notes.find(item => item.id === id && item.projectId === project.id && !item.archived);
    if (!note) {
      omitted.push(`Note ${id}: missing, archived or belongs to another project`);
      continue;
    }
    candidates.push({
      id,
      kind: 'note',
      label: `Note: ${heading(note.title)}`,
      truncated: false,
      text: `Kind: ${note.kind}; confidence: ${note.confidence}\n${note.body}`,
    });
  }
  for (const id of [...new Set(selection.sourceIds)]) {
    const source = state.sources.find(item => item.id === id && item.projectId === project.id);
    if (!source) {
      omitted.push(`Source ${id}: missing or belongs to another project`);
      continue;
    }
    candidates.push({
      id,
      kind: 'source',
      label: `Source: ${heading(source.title)}`,
      truncated: false,
      text: [
        `Type: ${source.kind}`,
        source.author ? `Author: ${source.author}` : '',
        source.locator ? `Location: ${source.locator}` : '',
        source.excerpt,
      ].filter(Boolean).join('\n'),
    });
  }
  const prefix = 'USER PROJECT MATERIAL — notes and source excerpts may be incomplete or unverified.\n';
  let remaining = selection.maxCharacters - prefix.length;
  const sections: ContextSection[] = [];
  const chunks: string[] = [];
  for (const candidate of candidates) {
    const header = `\n[${candidate.kind.toUpperCase()} ${sections.length + 1}] ${candidate.label}\n`;
    const available = remaining - header.length;
    if (available < 60) {
      omitted.push(`${candidate.label}: context budget exhausted`);
      continue;
    }
    // Give subsequent selected records a fair share rather than letting the first long note consume everything.
    const remainingCandidates = candidates.length - candidates.indexOf(candidate);
    const fairShare = Math.max(120, Math.floor(remaining / Math.min(4, remainingCandidates)) - header.length);
    const contentBudget = Math.min(available, fairShare);
    const truncated = candidate.text.length > contentBudget;
    const body = truncated ? `${candidate.text.slice(0, Math.max(0, contentBudget - 14))}\n[truncated]` : candidate.text;
    const section = { ...candidate, text: body, truncated };
    const chunk = header + body;
    sections.push(section);
    chunks.push(chunk);
    remaining -= chunk.length;
  }
  const text = sections.length ? prefix + chunks.join('') : '';
  return {
    text,
    sections,
    omitted,
    characters: text.length,
    budget: selection.maxCharacters,
  };
}

export function makeHandoff(
  state: Workbench,
  selection: ContextSelection,
  draft: string,
  context: MutationContext,
): ChatHandoff {
  const project = state.projects.find(item => item.id === selection.projectId);
  if (!project) throw new WorkbenchError('The project no longer exists.', 'missing');
  const bundle = buildContext(state, selection);
  return {
    version: 1,
    id: context.id(),
    createdAt: context.now,
    projectId: project.id,
    projectTitle: project.title,
    draft: assertText(draft, 'Chat draft', 16000, true),
    context: bundle.text,
    sourceLabels: bundle.sections.map(section => section.label),
  };
}

export function parseHandoff(raw: string, now: number): ChatHandoff | null {
  if (raw.length > 25000) return null;
  try {
    const value: unknown = JSON.parse(raw);
    if (!isRecord(value) || value.version !== 1) return null;
    if (typeof value.createdAt !== 'number' || !Number.isFinite(value.createdAt)) return null;
    if (now < value.createdAt || now - value.createdAt > 30 * 60 * 1000) return null;
    if (typeof value.id !== 'string' || !/^[a-zA-Z0-9_-]{1,120}$/.test(value.id)) return null;
    if (typeof value.projectId !== 'string' || !/^[a-zA-Z0-9_-]{1,120}$/.test(value.projectId)) return null;
    if (typeof value.projectTitle !== 'string' || value.projectTitle.length > LIMITS.title) return null;
    if (typeof value.draft !== 'string' || !value.draft.trim() || value.draft.length > 16000) return null;
    if (typeof value.context !== 'string' || value.context.length > 4000) return null;
    if (!Array.isArray(value.sourceLabels) || value.sourceLabels.length > 100 || value.sourceLabels.some(label => typeof label !== 'string' || label.length > 200)) return null;
    return {
      version: 1,
      id: value.id,
      createdAt: value.createdAt,
      projectId: value.projectId,
      projectTitle: value.projectTitle,
      draft: value.draft,
      context: value.context,
      sourceLabels: value.sourceLabels as string[],
    };
  } catch {
    return null;
  }
}

export function taskDiscussionPrompt(title: string, description: string): string {
  return `Help me work through this task: ${title}\n\n${description.slice(0, 12000)}${description.length > 12000 ? '\n[Description shortened for chat]' : ''}\n\nUse the attached project context. Identify a small next step, explain the tradeoffs, and suggest how I can verify the result. Ask for missing code or facts instead of inventing them.`;
}

export function noteDiscussionPrompt(title: string, body: string): string {
  return `Review this note: ${title}\n\n${body.slice(0, 12000)}\n\nSeparate supported claims from assumptions, point out missing evidence, and suggest a useful experiment or next action.`;
}
