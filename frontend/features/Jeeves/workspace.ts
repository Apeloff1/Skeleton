/** Local conversation projection/cache. Server threads/messages are authoritative in product mode; attachment bytes never cross this persistence boundary. */
export const WORKSPACE_KEY = '@tutolage/jeeves-workspace:v1';
export const LEGACY_KEY = '@tutolage/jeeves-chat:v2';
export const MAX_CONVERSATIONS = 30;
export const MAX_MESSAGES = 100;
export const MAX_TEXT = 16_000;
export const MAX_CONTEXT = 4_000;
export const SESSION_TTL = 6 * 60 * 60 * 1000;

export type Artifact = {
  type: string;
  kind?: string;
  title?: string;
  mime: string;
  base64: string;
  filename?: string;
};

export type Message = {
  id: string;
  role: 'user' | 'jeeves';
  text: string;
  createdAt: number;
  status: 'complete' | 'pending' | 'failed' | 'cancelled';
  tier?: string;
  model?: string;
  forms?: string[];
  artifacts?: Artifact[];
  artifactCount?: number;
  attachmentName?: string;
  error?: string;
  idempotencyKey?: string;
  expectedThreadVersion?: number;
};

export type Conversation = {
  id: string;
  handoffId?: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  pinned: boolean;
  archived: boolean;
  draft: string;
  context: string;
  allForms: boolean;
  sessionId: string | null;
  sessionUpdatedAt: number;
  messages: Message[];
  // Canonical server thread version. Local storage is only a cache/preferences
  // projection when this field is present.
  serverVersion?: number;
  serverState?: 'active' | 'archived' | 'deleting' | 'deleted';
};

export type Workspace = {
  version: 1;
  activeId: string;
  conversations: Conversation[];
};

export type Attachment = { modality: 'image' | 'pdf'; base64: string; name: string };
export type ChatBody = {
  message: string;
  session_id: string;
  client_message_id?: string;
  force_all_forms: boolean;
  context: string;
  history: { role: 'user' | 'assistant'; content: string }[];
  image_base64?: string;
  pdf_base64?: string;
};

export function newId(): string {
  return globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

export function createConversation(now = Date.now()): Conversation {
  return {
    id: newId(), title: 'New conversation', createdAt: now, updatedAt: now,
    pinned: false, archived: false, draft: '', context: '', allForms: false,
    sessionId: null, sessionUpdatedAt: 0, messages: [],
  };
}

export function createWorkspace(): Workspace {
  const conversation = createConversation();
  return { version: 1, activeId: conversation.id, conversations: [conversation] };
}

function record(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : null;
}

function text(value: unknown, max = MAX_TEXT): string {
  return typeof value === 'string' ? value.slice(0, max) : '';
}

function timestamp(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : fallback;
}

function restoreMessage(value: unknown, now: number): Message | null {
  const item = record(value);
  if (!item || (item.role !== 'user' && item.role !== 'jeeves') || typeof item.text !== 'string') return null;
  const interrupted = item.status === 'pending';
  const status = interrupted ? 'failed'
    : item.status === 'failed' || item.status === 'cancelled' ? item.status : 'complete';
  return {
    id: text(item.id, 100) || newId(), role: item.role, text: text(item.text),
    createdAt: timestamp(item.createdAt, now), status,
    tier: text(item.tier, 80) || undefined, model: text(item.model, 120) || undefined,
    forms: Array.isArray(item.forms) ? item.forms.filter((x): x is string => typeof x === 'string').slice(0, 10) : undefined,
    artifactCount: typeof item.artifactCount === 'number' ? Math.max(0, Math.min(100, item.artifactCount)) : 0,
    attachmentName: text(item.attachmentName, 200) || undefined,
    error: interrupted ? 'Interrupted when the app closed. You can retry this message.' : text(item.error, 400) || undefined,
    idempotencyKey: text(item.idempotencyKey, 256) || undefined,
    expectedThreadVersion: (
      typeof item.expectedThreadVersion === 'number'
      && Number.isSafeInteger(item.expectedThreadVersion)
      && item.expectedThreadVersion >= 1
    ) ? item.expectedThreadVersion : undefined,
  };
}

function restoreConversation(value: unknown, now: number): Conversation | null {
  const item = record(value);
  if (!item || typeof item.id !== 'string' || !item.id || !Array.isArray(item.messages)) return null;
  const seen = new Set<string>();
  const messages = item.messages.slice(-MAX_MESSAGES).map(x => restoreMessage(x, now))
    .filter((x): x is Message => !!x).map(message => {
      if (seen.has(message.id)) message.id = newId();
      seen.add(message.id);
      return message;
    });
  const sessionUpdatedAt = timestamp(item.sessionUpdatedAt, 0);
  const sessionFresh = now >= sessionUpdatedAt && now - sessionUpdatedAt <= SESSION_TTL;
  return {
    id: text(item.id, 100), title: text(item.title, 100).trim() || 'Untitled conversation',
    handoffId: typeof item.handoffId === 'string' && /^[a-zA-Z0-9_-]{1,120}$/.test(item.handoffId) ? item.handoffId : undefined,
    createdAt: timestamp(item.createdAt, now), updatedAt: timestamp(item.updatedAt, now),
    pinned: item.pinned === true, archived: item.archived === true,
    draft: text(item.draft), context: text(item.context, MAX_CONTEXT), allForms: item.allForms === true,
    sessionId: sessionFresh ? text(item.sessionId, 128) || null : null,
    sessionUpdatedAt: sessionFresh ? sessionUpdatedAt : 0, messages,
    serverVersion: (
      typeof item.serverVersion === 'number'
      && Number.isSafeInteger(item.serverVersion)
      && item.serverVersion >= 1
    ) ? item.serverVersion : undefined,
    serverState: (
      item.serverState === 'active'
      || item.serverState === 'archived'
      || item.serverState === 'deleting'
      || item.serverState === 'deleted'
    ) ? item.serverState : undefined,
  };
}

/** Reject an unknown schema rather than silently overwriting future-version data. */
export function decodeWorkspace(raw: string, now = Date.now()): Workspace {
  const value = record(JSON.parse(raw));
  if (value?.version !== 1 || !Array.isArray(value.conversations)) throw new Error('Unsupported Jeeves workspace format.');
  const seen = new Set<string>();
  const conversations = value.conversations.slice(0, MAX_CONVERSATIONS)
    .map(x => restoreConversation(x, now)).filter((x): x is Conversation => !!x)
    .filter(x => { if (seen.has(x.id)) return false; seen.add(x.id); return true; });
  if (!conversations.length) throw new Error('No readable conversations in the saved workspace.');
  const active = conversations.find(c => c.id === value.activeId && !c.archived)
    || conversations.find(c => !c.archived) || conversations[0];
  active.archived = false;
  return { version: 1, activeId: active.id, conversations };
}

/** Explicit allow-list: excludes base64, untrusted extra properties and response objects. */
export function encodeWorkspace(workspace: Workspace): string {
  return JSON.stringify({
    version: 1, activeId: workspace.activeId,
    conversations: workspace.conversations.slice(0, MAX_CONVERSATIONS).map(c => ({
      id: c.id, title: c.title, createdAt: c.createdAt, updatedAt: c.updatedAt,
      handoffId: c.handoffId,
      pinned: c.pinned, archived: c.archived, draft: c.draft.slice(0, MAX_TEXT),
      context: c.context.slice(0, MAX_CONTEXT), allForms: c.allForms,
      sessionId: c.sessionId, sessionUpdatedAt: c.sessionUpdatedAt,
      serverVersion: c.serverVersion, serverState: c.serverState,
      messages: c.messages.slice(-MAX_MESSAGES).map(m => ({
        id: m.id, role: m.role, text: m.text.slice(0, MAX_TEXT), createdAt: m.createdAt,
        status: m.status, tier: m.tier, model: m.model, forms: m.forms,
        artifactCount: m.artifacts?.length || m.artifactCount || 0,
        attachmentName: m.attachmentName, error: m.error,
        idempotencyKey: m.idempotencyKey,
        expectedThreadVersion: m.expectedThreadVersion,
      })),
    })),
  });
}

export function migrateLegacy(raw: string, now = Date.now()): Workspace {
  const old = record(JSON.parse(raw));
  if (old?.version !== 2 || !Array.isArray(old.messages)) throw new Error('Unsupported legacy conversation.');
  const conversation = restoreConversation({
    ...createConversation(now), title: 'Previous conversation', ...old, id: newId(),
  }, now)!;
  return { version: 1, activeId: conversation.id, conversations: [conversation] };
}

export function updateConversation(workspace: Workspace, id: string, update: (c: Conversation) => Conversation): Workspace {
  return { ...workspace, conversations: workspace.conversations.map(c => c.id === id ? update(c) : c) };
}

export function addConversation(workspace: Workspace): Workspace {
  if (workspace.conversations.length >= MAX_CONVERSATIONS) throw new Error(`You have ${MAX_CONVERSATIONS} conversations. Export and delete one to make room.`);
  const conversation = createConversation();
  return { ...workspace, activeId: conversation.id, conversations: [conversation, ...workspace.conversations] };
}

export function deleteConversation(workspace: Workspace, id: string): Workspace {
  const conversations = workspace.conversations.filter(c => c.id !== id);
  if (!conversations.length) return createWorkspace();
  const active = conversations.find(c => c.id === workspace.activeId) || conversations.find(c => !c.archived) || conversations[0];
  return { ...workspace, activeId: active.id, conversations: conversations.map(c => c.id === active.id ? { ...c, archived: false } : c) };
}

export function searchConversations(workspace: Workspace, query: string, archived = false): Conversation[] {
  const needle = query.trim().toLocaleLowerCase();
  return workspace.conversations.filter(c => c.archived === archived && (!needle ||
    [c.title, c.context, ...c.messages.map(m => m.text)].some(s => s.toLocaleLowerCase().includes(needle))))
    .sort((a, b) => Number(b.pinned) - Number(a.pinned) || b.updatedAt - a.updatedAt);
}

export function transcript(conversation: Conversation): string {
  const header = `# ${conversation.title}\n\nExported ${new Date().toISOString()}\n`;
  const context = conversation.context ? `\n## Project context\n\n${conversation.context}\n` : '';
  return header + context + conversation.messages.map(m =>
    `\n## ${m.role === 'user' ? 'You' : 'Jeeves'}\n\n${m.text}\n` +
    (m.status !== 'complete' ? `\n_Status: ${m.status}_\n` : '') +
    (m.attachmentName ? `\n_Attachment: ${m.attachmentName} (file not included)_\n` : '') +
    ((m.artifacts?.length || m.artifactCount) ? '\n_Artifacts are not included in this text export._\n' : '')
  ).join('');
}

export function buildChatBody(
  conversation: Conversation,
  message: string,
  attachment?: Attachment,
  now = Date.now(),
  clientMessageId?: string,
): ChatBody {
  // Only completed user/assistant exchanges enter the history; omit failed and in-flight turns.
  const history = conversation.messages.filter(m => m.status === 'complete').slice(-20)
    .map(m => ({ role: m.role === 'jeeves' ? 'assistant' as const : 'user' as const, content: m.text.slice(0, 4000) }));
  // Preserve the newest context while keeping the whole request under 24k history characters.
  let remaining = 24_000;
  const bounded = history.reverse().filter(m => {
    if (m.content.length > remaining) return false;
    remaining -= m.content.length;
    return true;
  }).reverse();
  const serverSessionId = (
    conversation.sessionId
    && now >= conversation.sessionUpdatedAt
    && now - conversation.sessionUpdatedAt <= SESSION_TTL
  ) ? conversation.sessionId : conversation.id;
  return {
    message,
    session_id: serverSessionId,
    ...(clientMessageId ? { client_message_id: clientMessageId } : {}),
    force_all_forms: conversation.allForms,
    context: conversation.context,
    history: bounded,
    ...(attachment?.modality === 'image' ? { image_base64: attachment.base64 } : {}),
    ...(attachment?.modality === 'pdf' ? { pdf_base64: attachment.base64 } : {}),
  };
}
