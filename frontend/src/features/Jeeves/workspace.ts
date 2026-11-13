import { normalizeChatCooperation, type ChatCooperationPolicy, type ChatCooperationSummary } from '../../product/chatCooperation';

/** Device-local conversation data. No attachment bytes cross the persistence boundary. */
export const WORKSPACE_KEY = '@tutolage/jeeves-workspace:v1';
export const LEGACY_KEY = '@tutolage/jeeves-chat:v2';
export const MAX_CONVERSATIONS = 30;
export const MAX_MESSAGES = 100;
export const MAX_TEXT = 16_000;
export const MAX_REPLY = 100_000;
export const MAX_CONTEXT = 4_000;
/** @deprecated Canonical server sessions are durable; retained for API compatibility. */
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
  /** Exact non-binary submission parameters; never rebuilt from later edits. */
  retryRequest?: Omit<ChatBody, 'message' | 'client_message_id' | 'image_base64' | 'pdf_base64'>;
  terminal?: boolean;
  error?: string;
  /** Current server observation only; excluded from device persistence. */
  cooperation?: ChatCooperationSummary;
};

export type Conversation = {
  id: string;
  handoffId?: string;
  canonicalThreadId?: string;
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
  image_base64?: string;
  pdf_base64?: string;
  canonical_thread_id?: string;
  provider_id?: string;
  model_id?: string;
  max_output_tokens?: number;
  crawler_context?: { query: string; max_documents: number; max_characters: number };
  cooperation?: ChatCooperationPolicy;
  resume_existing?: boolean;
  resume_only?: boolean;
  resume_cursor?: { operation_id: string; last_seen_sequence: number; last_event_digest: string | null };
};

export type CanonicalChatTurn = {
  session_id: string;
  client_message_id?: string | null;
  role_user?: string | null;
  role_jeeves?: string | null;
  status?: string;
  ts?: number;
  operation_id?: string | null;
  ai_result_id?: string | null;
  engine_execution_id?: string | null;
  canonical_thread_id?: string | null;
  canonical_user_message_id?: string | null;
  canonical_assistant_message_id?: string | null;
  cooperation?: ChatCooperationSummary;
};

export type ChatHistoryProjection = {
  ok?: boolean;
  session_id: string;
  turns: CanonicalChatTurn[];
  count?: number;
  available?: boolean;
  history_source?: string;
  canonical_thread_id?: string | null;
  thread_title?: string;
  thread_state?: string;
  pending_turns?: { client_message_id: string; text: string; created_at: number; terminal: boolean; cooperation?: ChatCooperationSummary }[];
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

function sessionIdentity(value: unknown): string | null {
  return typeof value === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(value)
    ? value : null;
}

function restoreMessage(value: unknown, now: number): Message | null {
  const item = record(value);
  if (!item || (item.role !== 'user' && item.role !== 'jeeves') || typeof item.text !== 'string') return null;
  const interrupted = item.status === 'pending';
  const status = interrupted ? 'failed'
    : item.status === 'failed' || item.status === 'cancelled' ? item.status : 'complete';
  return {
    id: text(item.id, 100) || newId(), role: item.role, text: text(item.text, item.role === 'jeeves' ? MAX_REPLY : MAX_TEXT),
    createdAt: timestamp(item.createdAt, now), status, terminal: item.terminal === true,
    tier: text(item.tier, 80) || undefined, model: text(item.model, 120) || undefined,
    forms: Array.isArray(item.forms) ? item.forms.filter((x): x is string => typeof x === 'string').slice(0, 10) : undefined,
    artifactCount: typeof item.artifactCount === 'number' ? Math.max(0, Math.min(100, item.artifactCount)) : 0,
    attachmentName: text(item.attachmentName, 200) || undefined,
    retryRequest: restoreRetryRequest(item.retryRequest),
    error: interrupted ? 'Interrupted when the app closed. You can retry this message.' : text(item.error, 400) || undefined,
  };
}

function restoreRetryRequest(value: unknown): Message['retryRequest'] {
  const item = record(value);
  if (!item || !sessionIdentity(item.session_id)
      || typeof item.context !== 'string' || item.context.length > MAX_CONTEXT
      || typeof item.force_all_forms !== 'boolean') return undefined;
  let cooperation: ChatCooperationPolicy | undefined;
  let reviewSettingsInvalid = false;
  if (item.cooperation !== undefined) {
    try { cooperation = normalizeChatCooperation(item.cooperation); }
    catch { reviewSettingsInvalid = true; }
  }
  return {
    session_id: item.session_id as string,
    context: item.context,
    force_all_forms: item.force_all_forms,
    ...(typeof item.canonical_thread_id === 'string' && sessionIdentity(item.canonical_thread_id) ? { canonical_thread_id: item.canonical_thread_id } : {}),
    ...(typeof item.provider_id === 'string' && item.provider_id.length <= 128 && typeof item.model_id === 'string' && item.model_id.length <= 256 ? { provider_id: item.provider_id, model_id: item.model_id } : {}),
    ...(Number.isSafeInteger(item.max_output_tokens) && (item.max_output_tokens as number) > 0 && (item.max_output_tokens as number) <= 65536 ? { max_output_tokens: item.max_output_tokens as number } : {}),
    ...(item.resume_existing === true ? { resume_existing: true } : {}),
    ...(item.resume_only === true || reviewSettingsInvalid ? { resume_only: true } : {}),
    ...(cooperation ? { cooperation } : {}),
    ...restoreCrawlerContext(item.crawler_context),
    ...restoreCursor(item.resume_cursor),
  };
}
function restoreCrawlerContext(value: unknown): Pick<ChatBody, 'crawler_context'> {
  const item = record(value);
  return item && typeof item.query === 'string' && item.query.length > 0 && item.query.length <= 1024 && Number.isSafeInteger(item.max_documents) && (item.max_documents as number) >= 1 && (item.max_documents as number) <= 4 && Number.isSafeInteger(item.max_characters) && (item.max_characters as number) >= 1 && (item.max_characters as number) <= 16000
    ? { crawler_context: { query: item.query, max_documents: item.max_documents as number, max_characters: item.max_characters as number } } : {};
}
function restoreCursor(value: unknown): Pick<ChatBody, 'resume_cursor'> {
  const item = record(value);
  return item && typeof item.operation_id === 'string' && item.operation_id.length <= 160 && Number.isSafeInteger(item.last_seen_sequence) && (item.last_seen_sequence as number) > 0 && typeof item.last_event_digest === 'string' && /^[a-f0-9]{64}$/.test(item.last_event_digest)
    ? { resume_cursor: { operation_id: item.operation_id, last_seen_sequence: item.last_seen_sequence as number, last_event_digest: item.last_event_digest } } : {};
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
  const sessionId = sessionIdentity(item.sessionId);
  return {
    id: text(item.id, 100), title: text(item.title, 100).trim() || 'Untitled conversation',
    handoffId: typeof item.handoffId === 'string' && /^[a-zA-Z0-9_-]{1,120}$/.test(item.handoffId) ? item.handoffId : undefined,
    canonicalThreadId: typeof item.canonicalThreadId === 'string' && item.canonicalThreadId.length <= 128 ? item.canonicalThreadId : undefined,
    createdAt: timestamp(item.createdAt, now), updatedAt: timestamp(item.updatedAt, now),
    pinned: item.pinned === true, archived: item.archived === true,
    draft: text(item.draft), context: text(item.context, MAX_CONTEXT), allForms: item.allForms === true,
    sessionId,
    sessionUpdatedAt: sessionId ? sessionUpdatedAt : 0, messages,
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
      handoffId: c.handoffId, canonicalThreadId: c.canonicalThreadId,
      pinned: c.pinned, archived: c.archived, draft: c.draft.slice(0, MAX_TEXT),
      context: c.context.slice(0, MAX_CONTEXT), allForms: c.allForms,
      sessionId: c.sessionId, sessionUpdatedAt: c.sessionUpdatedAt,
      messages: c.messages.slice(-MAX_MESSAGES).map(m => ({
        id: m.id, role: m.role, text: m.text.slice(0, m.role === 'jeeves' ? MAX_REPLY : MAX_TEXT), createdAt: m.createdAt,
        status: m.status, tier: m.tier, model: m.model, forms: m.forms, terminal: m.terminal,
        artifactCount: m.artifacts?.length || m.artifactCount || 0,
        attachmentName: m.attachmentName, error: m.error,
        retryRequest: m.status === 'complete' ? undefined : restoreRetryRequest(m.retryRequest),
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
  _now = Date.now(),
  clientMessageId?: string,
): ChatBody {
  // Canonical ConversationThread/ConversationMessage is the transcript owner.
  // The browser cache never sends its transcript back as provider context.
  const serverSessionId = conversation.sessionId || conversation.id;
  return {
    message,
    session_id: serverSessionId,
    canonical_thread_id: conversation.canonicalThreadId,
    ...(clientMessageId ? { client_message_id: clientMessageId } : {}),
    force_all_forms: conversation.allForms,
    context: conversation.context,
    ...(attachment?.modality === 'image' ? { image_base64: attachment.base64 } : {}),
    ...(attachment?.modality === 'pdf' ? { pdf_base64: attachment.base64 } : {}),
  };
}

function canonicalTurnText(value: unknown, field: string): string {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(`Canonical Jeeves history has invalid ${field}.`);
  }
  return value.slice(0, MAX_REPLY);
}

function canonicalTurnId(value: unknown, fallback: string): string {
  if (typeof value === 'string' && /^[A-Za-z0-9:_-]{1,160}$/.test(value)) return value;
  return fallback;
}

export function projectCanonicalHistory(
  conversation: Conversation,
  projection: ChatHistoryProjection,
  now = Date.now(),
): Conversation {
  const expectedSession = conversation.sessionId || conversation.id;
  if (projection.session_id !== expectedSession) {
    throw new Error('Canonical Jeeves history belongs to a different session.');
  }
  if (projection.ok === false || projection.available === false) return conversation;
  if (!Array.isArray(projection.turns)) {
    throw new Error('Canonical Jeeves history is malformed.');
  }

  const localById = new Map(conversation.messages.map(message => [message.id, message]));
  const projected: Message[] = [];
  const canonicalIds = new Set<string>();
  let previousTimestamp = 0;

  projection.turns.forEach((turn, index) => {
    if (!turn || turn.session_id !== expectedSession) {
      throw new Error('Canonical Jeeves history contains a foreign session turn.');
    }
    if (turn.status && turn.status !== 'complete') {
      throw new Error('Canonical Jeeves history contains a non-terminal turn.');
    }
    const userText = canonicalTurnText(turn.role_user, 'user text');
    const assistantText = canonicalTurnText(turn.role_jeeves, 'assistant text');
    const userId = canonicalTurnId(
      turn.client_message_id,
      canonicalTurnId(turn.canonical_user_message_id, `canonical-user-${index}`),
    );
    const assistantId = canonicalTurnId(
      turn.canonical_assistant_message_id,
      `${userId}:assistant`,
    );
    if (canonicalIds.has(userId) || canonicalIds.has(assistantId) || userId === assistantId) {
      throw new Error('Canonical Jeeves history contains duplicate message identity.');
    }
    canonicalIds.add(userId);
    canonicalIds.add(assistantId);

    const seconds = (
      typeof turn.ts === 'number'
      && Number.isFinite(turn.ts)
      && turn.ts >= 0
    ) ? turn.ts : 0;
    const baseTimestamp = seconds > 0
      ? Math.floor(seconds * 1000)
      : Math.max(now, previousTimestamp + 2);
    if (baseTimestamp < previousTimestamp) {
      throw new Error('Canonical Jeeves history is not ordered.');
    }
    previousTimestamp = baseTimestamp + 1;

    const localUser = localById.get(userId);
    projected.push({
      ...(localUser || {}),
      id: userId,
      role: 'user',
      text: userText,
      createdAt: baseTimestamp,
      status: 'complete',
      error: undefined,
      retryRequest: undefined,
      cooperation: undefined,
    });

    const localAssistant = localById.get(assistantId);
    projected.push({
      ...(localAssistant || {}),
      id: assistantId,
      role: 'jeeves',
      text: assistantText,
      createdAt: baseTimestamp + 1,
      status: 'complete',
      error: undefined,
      cooperation: turn.cooperation,
    });
  });

  const pending = projection.pending_turns || [];
  const unresolved = conversation.messages.filter(message => (
    message.role === 'user'
    && message.status !== 'complete'
    && !canonicalIds.has(message.id)
  ));
  for (const turn of pending) {
    if (!turn || typeof turn.client_message_id !== 'string' || typeof turn.text !== 'string' || !Number.isFinite(turn.created_at) || canonicalIds.has(turn.client_message_id)) continue;
    const index = unresolved.findIndex(message => message.id === turn.client_message_id);
    const previous = index >= 0 ? unresolved[index] : undefined;
    const message: Message = { ...previous, id: turn.client_message_id, role: 'user', text: turn.text.slice(0, MAX_TEXT), createdAt: turn.created_at, status: 'failed', terminal: turn.terminal,
      cooperation: turn.cooperation ?? previous?.cooperation,
      error: turn.terminal ? 'This turn ended without a reply. You can send a new message.' : 'This saved turn has no confirmed answer yet. Resume to follow its actual state.',
      retryRequest: previous?.retryRequest || { session_id: projection.session_id, canonical_thread_id: projection.session_id, context: '', force_all_forms: false, resume_existing: true, resume_only: true } };
    if (index >= 0) unresolved[index] = message; else unresolved.push(message);
  }
  const messages = [...projected, ...unresolved].slice(-MAX_MESSAGES);
  const updatedAt = messages.reduce(
    (latest, item) => Math.max(latest, item.createdAt),
    conversation.updatedAt,
  );
  return {
    ...conversation,
    title: projection.thread_title || conversation.title,
    archived: projection.thread_state ? projection.thread_state === 'archived' : conversation.archived,
    canonicalThreadId: projection.canonical_thread_id || conversation.canonicalThreadId,
    sessionId: projection.session_id,
    sessionUpdatedAt: now,
    updatedAt,
    messages,
  };
}
