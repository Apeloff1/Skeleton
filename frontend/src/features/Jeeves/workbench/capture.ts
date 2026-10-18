import type { Command } from './domain';
import type { Message, Conversation } from '../workspace';
import type { Workbench, MutationContext, NoteKind } from './types';
import { applyCommand } from './domain';
import { assertText, WorkbenchError } from './validation';

export interface CaptureInput {
  projectId: string;
  title: string;
  text: string;
  kind: NoteKind;
  conversationId: string;
  conversationTitle: string;
  messageId: string;
  role: 'user' | 'assistant';
  model: string | null;
}

export interface CaptureResult {
  state: Workbench;
  noteId: string;
  sourceId: string;
  duplicate: boolean;
}

export function captureInput(conversation: Conversation, message: Message, projectId: string): CaptureInput {
  if (message.status !== 'complete') throw new WorkbenchError('Wait for a complete message before saving it to the notebook.');
  if (!message.text.trim()) throw new WorkbenchError('This message has no text to save.');
  return {
    projectId,
    title: message.text.split('\n').find(line => line.trim())?.replace(/^#+\s*/, '').slice(0, 160) || 'Conversation note',
    text: message.text,
    kind: 'note',
    conversationId: conversation.id,
    conversationTitle: conversation.title,
    messageId: message.id,
    role: message.role === 'user' ? 'user' : 'assistant',
    model: message.model || null,
  };
}

export function captureMessage(state: Workbench, input: CaptureInput, context: MutationContext): CaptureResult {
  const project = state.projects.find(item => item.id === input.projectId);
  if (!project) throw new WorkbenchError('Choose an existing project.', 'missing');
  if (project.status === 'archived') throw new WorkbenchError('Restore the project before saving notes.', 'blocked');
  const title = assertText(input.title.trim(), 'Note title', 160, true);
  const body = assertText(input.text, 'Note text', 30000, true);
  const locator = `jeeves-conversation:${encodeURIComponent(input.conversationId)}#${encodeURIComponent(input.messageId)}`;
  const existingSource = state.sources.find(source => source.projectId === project.id && source.kind === 'conversation' && source.locator === locator);
  const existingNote = existingSource && state.notes.find(note => note.projectId === project.id && note.sourceIds.includes(existingSource.id) && note.body === body);
  if (existingSource && existingNote) return { state, sourceId: existingSource.id, noteId: existingNote.id, duplicate: true };
  let next = state;
  let sourceId = existingSource?.id;
  if (!sourceId) {
    const command: Command = {
      type: 'source.create',
      input: {
        projectId: project.id,
        title: `Chat: ${input.conversationTitle}`.slice(0, 160),
        kind: 'conversation',
        locator,
        author: input.role === 'assistant' ? `Jeeves${input.model ? ` (${input.model})` : ''}`.slice(0, 160) : 'You',
        excerpt: body.slice(0, 8000),
        tags: ['chat-capture'],
      },
    };
    const result = applyCommand(next, command, context);
    next = result.state;
    sourceId = result.createdId!;
  }
  const result = applyCommand(next, {
    type: 'note.create',
    input: { projectId: project.id, title, body, kind: input.kind, confidence: 'unverified', sourceIds: [sourceId], tags: ['chat-capture'] },
  }, context);
  return { state: result.state, sourceId, noteId: result.createdId!, duplicate: false };
}
