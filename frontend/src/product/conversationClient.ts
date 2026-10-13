import { CryptoDigestAlgorithm, digestStringAsync } from 'expo-crypto';
import api, { type ApiResult } from '../utils/apiClient';
import { validateConversationProjection } from './conversationProjection';
import { authHeaders } from '../auth/gameforgeAuth';
import { ChatClientError, chatApiError } from './chatErrors';

export type ConversationRequestOptions = {
  signal?: AbortSignal;
  headers?: Record<string, string>;
};

function requestOptions(input: ConversationRequestOptions = {}) {
  return { signal: input.signal, headers: authHeaders(input.headers), retries: 0 };
}

export type ConversationThreadState = 'active' | 'archived' | 'deleting' | 'deleted';
export type ConversationAuthorType = 'user' | 'assistant' | 'tool' | 'system-derived';

export type ConversationThread = {
  schema_version: number;
  thread_id: string;
  tenant_id: string;
  owner_id: string;
  created_at: string;
  updated_at: string;
  version: number;
  message_sequence: number;
  active_branch_id: string;
  state: ConversationThreadState;
  title: string;
  data_class: 'public' | 'internal' | 'confidential' | 'restricted';
};

export type ConversationMessage = {
  schema_version: number;
  message_id: string;
  thread_id: string;
  branch_id: string;
  sequence: number;
  author_type: ConversationAuthorType;
  created_at: string;
  idempotency_key: string;
  content?: string | null;
  content_ref?: string | null;
  parent_message_id?: string | null;
  supersedes_message_id?: string | null;
  causal_user_message_id?: string | null;
  operation_id?: string | null;
  ai_result_id?: string | null;
  context_id?: string | null;
  context_digest?: string | null;
  context_source_snapshot?: [string, string][];
  context_compiler_version?: string | null;
  attachment_refs: string[];
  tool_receipt_refs: string[];
  provider_receipt_refs: string[];
  memory_refs?: string[];
  citation_refs: string[];
  artifact_refs: string[];
  data_class: 'public' | 'internal' | 'confidential' | 'restricted';
};

async function requireData<T>(promise: Promise<ApiResult<T>>, message: string): Promise<T> {
  const result = await promise;
  if (!result.ok || result.data === null) throw chatApiError(result, message);
  return result.data;
}

export async function createConversation(input: {
  title?: string;
  dataClass?: ConversationThread['data_class'];
  signal?: AbortSignal;
  headers?: Record<string, string>;
} = {}): Promise<ConversationThread> {
  const data = await requireData(
    api.post<{ thread: ConversationThread }>('/api/v1/conversations', {
      title: input.title || 'New conversation',
      data_class: input.dataClass || 'confidential',
    }, requestOptions(input)),
    'Could not create conversation.',
  );
  return data.thread;
}

export async function listConversations(input: {
  includeArchived?: boolean;
  limit?: number;
  query?: string;
  cursor?: string;
  signal?: AbortSignal;
  headers?: Record<string, string>;
} = {}): Promise<ConversationThread[]> {
  const params = new URLSearchParams();
  if (input.includeArchived) params.set('include_archived', 'true');
  if (input.limit) params.set('limit', String(input.limit));
  if (input.query) params.set('q', input.query);
  if (input.cursor) params.set('cursor', input.cursor);
  const suffix = params.toString() ? '?' + params.toString() : '';
  const data = await requireData(
    api.get<{ threads: ConversationThread[] }>('/api/v1/conversations' + suffix, requestOptions(input)),
    'Could not load conversations.',
  );
  return data.threads;
}

export async function getConversation(threadId: string, input: ConversationRequestOptions = {}): Promise<ConversationThread> {
  const data = await requireData(
    api.get<{ thread: ConversationThread }>(
      '/api/v1/conversations/' + encodeURIComponent(threadId),
      requestOptions(input),
    ),
    'Could not load conversation.',
  );
  return data.thread;
}

export async function listConversationMessages(
  threadId: string,
  input: { afterSequence?: number; limit?: number; activeOnly?: boolean } & ConversationRequestOptions = {},
): Promise<{
  messages: ConversationMessage[];
  nextAfterSequence: number | null;
}> {
  const params = new URLSearchParams();
  if (input.afterSequence) params.set('after_sequence', String(input.afterSequence));
  if (input.limit) params.set('limit', String(input.limit));
  if (input.activeOnly) params.set('active_only', 'true');
  const suffix = params.toString() ? '?' + params.toString() : '';
  const data = await requireData(
    api.get<{
      messages: ConversationMessage[];
      next_after_sequence: number | null;
    }>(
      '/api/v1/conversations/' + encodeURIComponent(threadId) + '/messages' + suffix,
      requestOptions(input),
    ),
    'Could not load conversation messages.',
  );
  return {
    messages: data.messages,
    nextAfterSequence: data.next_after_sequence,
  };
}


export type ConversationSnapshot = {
  thread: ConversationThread;
  messages: ConversationMessage[];
  lastSequence: number;
};

export async function reconstructConversation(
  threadId: string,
  input: ConversationRequestOptions = {},
): Promise<ConversationSnapshot> {
  // A branch or append during pagination invalidates the entire projection.
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const thread = await getConversation(threadId, input);
    const messages: ConversationMessage[] = [];
    let afterSequence = 0;
    let transcriptCharacters = 0;
    while (true) {
      const page = await listConversationMessages(threadId, {
        ...input, activeOnly: true, limit: 500, afterSequence,
      });
      if (messages.length + page.messages.length > 10000) {
        throw new ChatClientError('This conversation exceeds the supported transcript size.', {
          kind: 'validation', code: 'projection_limit',
        });
      }
      transcriptCharacters += page.messages.reduce((total, message) => total + (message.content?.length ?? 0), 0);
      if (transcriptCharacters > 8 * 1024 * 1024) throw new ChatClientError('Conversation transcript exceeds the supported size.', { kind: 'validation', code: 'projection_limit' });
      messages.push(...page.messages);
      if (page.nextAfterSequence === null) break;
      if (!Number.isSafeInteger(page.nextAfterSequence) || page.nextAfterSequence <= afterSequence) {
        throw new ChatClientError('Conversation pagination did not advance.', { code: 'invalid_cursor' });
      }
      afterSequence = page.nextAfterSequence;
    }
    const current = await getConversation(threadId, input);
    if (current.version !== thread.version || current.active_branch_id !== thread.active_branch_id) continue;
    const projection = validateConversationProjection(current, messages);
    return { thread: current, messages: projection.messages, lastSequence: projection.lastSequence };
  }
  throw new ChatClientError('Conversation changed while loading. Refresh to try again.', {
    kind: 'conflict', code: 'projection_changed', retryable: true,
  });
}

export async function appendConversationMessage(
  thread: ConversationThread,
  input: {
    content: string;
    idempotencyKey: string;
    parentMessageId?: string;
    attachmentRefs?: string[];
    dataClass?: ConversationMessage['data_class'];
    signal?: AbortSignal;
    headers?: Record<string, string>;
  },
): Promise<{ thread: ConversationThread; message: ConversationMessage }> {
  return requireData(
    api.post<{ thread: ConversationThread; message: ConversationMessage }>(
      '/api/v1/conversations/' + encodeURIComponent(thread.thread_id) + '/messages',
      {
        content: input.content,
        idempotency_key: input.idempotencyKey,
        expected_thread_version: thread.version,
        parent_message_id: input.parentMessageId,
        attachment_refs: input.attachmentRefs || [],
        data_class: input.dataClass || thread.data_class,
      },
      { ...requestOptions(input), idempotencyKey: input.idempotencyKey },
    ),
    'Could not append conversation message.',
  );
}

export async function editConversationMessage(
  thread: ConversationThread,
  messageId: string,
  input: { content: string; idempotencyKey: string } & ConversationRequestOptions,
): Promise<{ thread: ConversationThread; message: ConversationMessage }> {
  return requireData(
    api.post<{ thread: ConversationThread; message: ConversationMessage }>(
      '/api/v1/conversations/' + encodeURIComponent(thread.thread_id)
        + '/messages/' + encodeURIComponent(messageId) + '/edit',
      {
        content: input.content,
        idempotency_key: input.idempotencyKey,
        expected_thread_version: thread.version,
      },
      { ...requestOptions(input), idempotencyKey: input.idempotencyKey },
    ),
    'Could not edit conversation message.',
  );
}


export async function regenerateConversationMessage(
  thread: ConversationThread,
  messageId: string,
  input: { idempotencyKey: string; providerId?: string; modelId?: string } & ConversationRequestOptions,
): Promise<{
  thread: ConversationThread;
  message: ConversationMessage;
  regeneratedFrom: string;
  causalUserMessageId: string;
  operationId: string;
  engineExecutionId: string;
  aiResultId: string;
}> {
  const data = await requireData(
    api.post<{
      thread: ConversationThread;
      message: ConversationMessage;
      regenerated_from: string;
      causal_user_message_id: string;
      operation_id: string;
      engine_execution_id: string;
      ai_result_id: string;
    }>(
      '/api/v1/conversations/' + encodeURIComponent(thread.thread_id)
        + '/messages/' + encodeURIComponent(messageId) + '/regenerate',
      {
        idempotency_key: input.idempotencyKey,
        provider_id: input.providerId,
        model_id: input.modelId,
        expected_thread_version: thread.version,
      },
      { ...requestOptions(input), idempotencyKey: input.idempotencyKey },
    ),
    'Could not regenerate conversation message.',
  );
  return {
    thread: data.thread,
    message: data.message,
    regeneratedFrom: data.regenerated_from,
    causalUserMessageId: data.causal_user_message_id,
    operationId: data.operation_id,
    engineExecutionId: data.engine_execution_id,
    aiResultId: data.ai_result_id,
  };
}

export async function updateConversationState(
  thread: ConversationThread,
  state: 'active' | 'archived' | 'deleting',
  input: ConversationRequestOptions = {},
): Promise<ConversationThread> {
  const data = await requireData(
    api.patch<{ thread: ConversationThread }>(
      '/api/v1/conversations/' + encodeURIComponent(thread.thread_id) + '/state',
      {
        state,
        expected_thread_version: thread.version,
      },
      requestOptions(input),
    ),
    'Could not update conversation state.',
  );
  return data.thread;
}

export async function requestConversationDeletion(
  thread: ConversationThread,
  input: ConversationRequestOptions = {},
): Promise<ConversationThread> {
  const path = '/api/v1/conversations/' + encodeURIComponent(thread.thread_id)
    + '?expected_thread_version=' + encodeURIComponent(String(thread.version));
  const data = await requireData(
    api.delete<{ thread: ConversationThread }>(path, requestOptions(input)),
    'Could not request conversation deletion.',
  );
  return data.thread;
}


export type ConversationTurnMemoryPolicy = {
  persist_verified_response?: boolean;
  kind?: 'episodic' | 'semantic' | 'procedural' | 'preference';
  namespace?: string;
  expires_at?: string | null;
};

export type ConversationTurn = {
  success: boolean;
  accepted?: boolean;
  server_resume_available?: boolean;
  terminal?: boolean;
  state?: string;
  cancellation_requested?: boolean;
  failure_code?: string | null;
  response?: string | null;
  ai_generated?: boolean;
  provider?: string | null;
  model?: string | null;
  replayed?: boolean;
  operation_id?: string | null;
  engine_execution_id?: string | null;
  ai_result_id?: string | null;
  engine_runtime_provider?: string | null;
  engine_provider_receipts?: string[];
  engine_tool_receipts?: string[];
  engine_memory_refs?: string[];
  engine_evidence_refs?: string[];
  engine_artifact_refs?: string[];
  thread?: ConversationThread;
  user_message?: ConversationMessage;
  assistant_message?: ConversationMessage;
  terminal_message?: ConversationMessage;
  context?: {
    context_id?: string;
    context_digest?: string;
    source_snapshot?: [string, string][];
    context_source_snapshot?: [string, string][];
    compiler_version?: string;
    context_compiler_version?: string;
    handoff_digest?: string;
    [key: string]: unknown;
  };
  timestamp?: string;
};

export async function startConversationTurn(
  thread: ConversationThread,
  input: {
    message: string;
    idempotencyKey: string;
    context?: string;
    memoryPolicy?: ConversationTurnMemoryPolicy;
    signal?: AbortSignal;
    deferred?: boolean;
    headers?: Record<string, string>;
    providerId?: string;
    modelId?: string;
    attachmentRefs?: string[];
    maxOutputTokens?: number;
    temperature?: number;
  },
): Promise<ConversationTurn> {
  const data = await requireData(
    api.post<ConversationTurn>(
      '/api/ai/chat',
      {
        message: input.message,
        thread_id: thread.thread_id,
        idempotency_key: input.idempotencyKey,
        expected_thread_version: thread.version,
        context: input.context,
        memory_policy: input.memoryPolicy,
        provider_id: input.providerId,
        model_id: input.modelId,
        attachment_refs: input.attachmentRefs ?? [],
        max_output_tokens: input.maxOutputTokens,
        temperature: input.temperature,
        response_mode: input.deferred === false ? 'wait' : 'deferred',
      },
      {
        ...requestOptions(input),
        // The body also carries this key; the transport header makes retries
        // explicitly idempotent at generic HTTP/circuit-breaker layers too.
        idempotencyKey: input.idempotencyKey,
        timeoutMs: input.deferred === false ? 120_000 : 20_000,
      },
    ),
    'Could not start conversation turn.',
  );
  if (
    data.engine_execution_id
    && data.user_message
    && data.user_message.thread_id !== thread.thread_id
  ) {
    throw new Error('Conversation turn returned a foreign thread identity.');
  }
  return data;
}

export async function getConversationTurn(
  threadId: string,
  idempotencyKey: string,
  input: ConversationRequestOptions = {},
): Promise<ConversationTurn> {
  const data = await requireData(
    api.get<ConversationTurn>(
      '/api/ai/chat/turns/'
        + encodeURIComponent(threadId)
        + '?idempotency_key='
        + encodeURIComponent(idempotencyKey),
      {
        ...requestOptions(input),
        timeoutMs: 20_000,
      },
    ),
    'Could not load conversation turn.',
  );
  if (
    data.user_message
    && data.user_message.thread_id !== threadId
  ) {
    throw new Error('Conversation turn status returned a foreign thread identity.');
  }
  return data;
}

export async function resumeConversationTurn(
  threadId: string, idempotencyKey: string, input: ConversationRequestOptions = {},
): Promise<ConversationTurn> {
  return requireData(api.post<ConversationTurn>(
    '/api/ai/chat/turns/' + encodeURIComponent(threadId) + '/resume',
    { idempotency_key: idempotencyKey },
    { ...requestOptions(input), idempotencyKey, timeoutMs: 20000 },
  ), 'Could not resume saved conversation turn.');
}

export async function cancelConversationTurn(
  threadId: string,
  idempotencyKey: string,
  input: {
    reason?: string;
    signal?: AbortSignal;
    headers?: Record<string, string>;
  } = {},
): Promise<ConversationTurn> {
  return requireData(
    api.post<ConversationTurn>(
      '/api/ai/chat/turns/'
        + encodeURIComponent(threadId)
        + '/cancel',
      {
        idempotency_key: idempotencyKey,
        reason: input.reason || 'user_cancelled',
      },
      {
        ...requestOptions(input),
        idempotencyKey: idempotencyKey + ':cancel',
        timeoutMs: 20_000,
      },
    ),
    'Could not cancel conversation turn.',
  );
}

function waitForConversationTurnPoll(
  ms: number,
  signal?: AbortSignal,
): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new Error('aborted'));
      return;
    }
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
      reject(new Error('aborted'));
    };
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}

export async function followConversationTurn(
  threadId: string,
  idempotencyKey: string,
  input: {
    signal?: AbortSignal;
    pollMs?: number;
    timeoutMs?: number;
    onUpdate?: (turn: ConversationTurn) => void;
  } = {},
): Promise<ConversationTurn> {
  const pollMs = Math.max(100, Math.min(10_000, Math.floor(input.pollMs ?? 500)));
  const timeoutMs = Math.max(
    pollMs,
    Math.min(24 * 60 * 60 * 1000, Math.floor(input.timeoutMs ?? 120_000)),
  );
  const startedAt = Date.now();

  while (true) {
    if (input.signal?.aborted) throw new Error('aborted');
    const turn = await getConversationTurn(
      threadId,
      idempotencyKey,
      { signal: input.signal },
    );
    input.onUpdate?.(turn);
    if (turn.terminal) return turn;
    if (Date.now() - startedAt >= timeoutMs) {
      throw new Error('Conversation turn did not reach terminal state in time.');
    }
    await waitForConversationTurnPoll(pollMs, input.signal);
  }
}

export type ConversationPage = {
  threads: ConversationThread[];
  nextCursor: string | null;
};

export async function listConversationPage(input: {
  includeArchived?: boolean; limit?: number; query?: string; cursor?: string;
} & ConversationRequestOptions = {}): Promise<ConversationPage> {
  const params = new URLSearchParams();
  if (input.includeArchived) params.set('include_archived', 'true');
  params.set('limit', String(input.limit ?? 50));
  if (input.query) params.set('q', input.query);
  if (input.cursor) params.set('cursor', input.cursor);
  const data = await requireData(api.get<{
    threads: ConversationThread[]; next_cursor?: string | null;
  }>('/api/v1/conversations?' + params.toString(), requestOptions(input)), 'Could not load conversations.');
  if (!Array.isArray(data.threads) || data.threads.length > 200) {
    throw new ChatClientError('Conversation list is invalid.', { code: 'invalid_projection' });
  }
  return { threads: data.threads, nextCursor: data.next_cursor ?? null };
}

export async function renameConversation(
  thread: ConversationThread, title: string, input: ConversationRequestOptions = {},
): Promise<ConversationThread> {
  if (!title.trim() || title.trim().length > 200) {
    throw new ChatClientError('Conversation title must contain 1 to 200 characters.', { kind: 'validation' });
  }
  const data = await requireData(api.patch<{ thread: ConversationThread }>(
    '/api/v1/conversations/' + encodeURIComponent(thread.thread_id),
    { title: title.trim(), expected_thread_version: thread.version },
    requestOptions(input),
  ), 'Could not rename conversation.');
  return data.thread;
}

export type ConversationRecovery = {
  thread: ConversationThread;
  messages: ConversationMessage[];
  last_sequence: number;
  next_before_message_id: string | null;
  regeneration_requests?: { message_id: string; idempotency_key: string; state?: string }[];
  pending_turn: {
    message_id: string;
    idempotency_key: string;
    sequence: number;
    attachment_refs: string[];
  } | null;
};

export async function getConversationRecovery(
  threadId: string, input: ConversationRequestOptions = {},
): Promise<ConversationRecovery> {
  const data = await requireData(api.get<ConversationRecovery>(
    '/api/v1/conversations/' + encodeURIComponent(threadId) + '/recovery?limit=100',
    requestOptions(input),
  ), 'Could not recover conversation.');
  if (data.thread.thread_id !== threadId
    || data.messages.some(message => message.thread_id !== threadId)) {
    throw new ChatClientError('Recovery returned a different conversation.', { code: 'foreign_thread' });
  }
  validateConversationProjection(data.thread, data.messages);
  return data;
}


export type ConversationExport = {
  filename: string;
  mimeType: string;
  content: string;
  contentDigest: string;
  snapshotVersion: number;
  messageCount: number;
  scope: 'canonical_active_lineage';
};

export async function getConversationExport(
  thread: ConversationThread, format: 'json' | 'markdown', input: ConversationRequestOptions = {},
): Promise<ConversationExport> {
  const data = await requireData(api.get<{
    thread_id: string; snapshot_version: number; scope: string; format: string;
    filename: string; media_type: string; content: string; content_digest: string;
    message_count: number; attachments_embedded: boolean;
  }>('/api/v1/conversations/' + encodeURIComponent(thread.thread_id) + '/export'
    + '?format=' + format + '&expected_thread_version=' + thread.version,
  { ...requestOptions(input), timeoutMs: 30000 }), 'Could not export conversation.');
  if (input.signal?.aborted) throw new ChatClientError('Export detached.', { kind: 'cancelled' });
  if (data.thread_id !== thread.thread_id || data.snapshot_version !== thread.version
    || data.scope !== 'canonical_active_lineage' || data.format !== format
    || data.attachments_embedded !== false || typeof data.content !== 'string'
    || typeof data.media_type !== 'string'
    || typeof data.filename !== 'string' || !data.filename || data.filename.length > 200
    || data.filename.includes('/') || data.filename.includes('\\')
    || !Number.isSafeInteger(data.message_count) || data.message_count < 0 || data.message_count > 10000
    || typeof data.content_digest !== 'string' || !/^[0-9a-f]{64}$/.test(data.content_digest)) {
    throw new ChatClientError('Export returned an invalid canonical identity.', { code: 'invalid_export' });
  }
  let bytes = 0;
  for (const character of data.content) {
    const point = character.codePointAt(0)!;
    bytes += point < 0x80 ? 1 : point < 0x800 ? 2 : point < 0x10000 ? 3 : 4;
    if (bytes > 8 * 1024 * 1024) throw new ChatClientError('Export exceeds the supported file size.', { code: 'export_limit' });
  }
  const measuredDigest = await digestStringAsync(CryptoDigestAlgorithm.SHA256, data.content);
  if (input.signal?.aborted) throw new ChatClientError('Export detached.', { kind: 'cancelled' });
  if (measuredDigest !== data.content_digest) throw new ChatClientError('Export content digest does not match.', { code: 'invalid_export' });
  const expectedMime = format === 'json' ? 'application/json' : 'text/markdown';
  if (!data.media_type.startsWith(expectedMime)) throw new ChatClientError('Export media type is invalid.', { code: 'invalid_export' });
  return { filename: data.filename, mimeType: data.media_type, content: data.content,
    contentDigest: measuredDigest, snapshotVersion: data.snapshot_version,
    messageCount: data.message_count, scope: 'canonical_active_lineage' };
}
