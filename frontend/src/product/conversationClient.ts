import api, { type ApiResult } from '../utils/apiClient';
import { validateConversationProjection } from './conversationProjection';

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
  if (!result.ok || result.data === null) throw new Error(message);
  return result.data;
}

export async function createConversation(input: {
  title?: string;
  dataClass?: ConversationThread['data_class'];
} = {}): Promise<ConversationThread> {
  const data = await requireData(
    api.post<{ thread: ConversationThread }>('/api/v1/conversations', {
      title: input.title || 'New conversation',
      data_class: input.dataClass || 'confidential',
    }),
    'Could not create conversation.',
  );
  return data.thread;
}

export async function listConversations(input: {
  includeArchived?: boolean;
  limit?: number;
} = {}): Promise<ConversationThread[]> {
  const params = new URLSearchParams();
  if (input.includeArchived) params.set('include_archived', 'true');
  if (input.limit) params.set('limit', String(input.limit));
  const suffix = params.toString() ? '?' + params.toString() : '';
  const data = await requireData(
    api.get<{ threads: ConversationThread[] }>('/api/v1/conversations' + suffix),
    'Could not load conversations.',
  );
  return data.threads;
}

export async function getConversation(threadId: string): Promise<ConversationThread> {
  const data = await requireData(
    api.get<{ thread: ConversationThread }>(
      '/api/v1/conversations/' + encodeURIComponent(threadId),
    ),
    'Could not load conversation.',
  );
  return data.thread;
}

export async function listConversationMessages(
  threadId: string,
  input: { afterSequence?: number; limit?: number; activeOnly?: boolean } = {},
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
): Promise<ConversationSnapshot> {
  const [thread, page] = await Promise.all([
    getConversation(threadId),
    listConversationMessages(threadId, {
      activeOnly: true,
      limit: 500,
    }),
  ]);
  const projection = validateConversationProjection(
    thread,
    page.messages,
  );
  return {
    thread,
    messages: projection.messages,
    lastSequence: projection.lastSequence,
  };
}

export async function appendConversationMessage(
  thread: ConversationThread,
  input: {
    content: string;
    idempotencyKey: string;
    parentMessageId?: string;
    attachmentRefs?: string[];
    dataClass?: ConversationMessage['data_class'];
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
    ),
    'Could not append conversation message.',
  );
}

export async function editConversationMessage(
  thread: ConversationThread,
  messageId: string,
  input: { content: string; idempotencyKey: string },
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
    ),
    'Could not edit conversation message.',
  );
}


export async function regenerateConversationMessage(
  thread: ConversationThread,
  messageId: string,
  input: { idempotencyKey: string },
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
        expected_thread_version: thread.version,
      },
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
): Promise<ConversationThread> {
  const data = await requireData(
    api.patch<{ thread: ConversationThread }>(
      '/api/v1/conversations/' + encodeURIComponent(thread.thread_id) + '/state',
      {
        state,
        expected_thread_version: thread.version,
      },
    ),
    'Could not update conversation state.',
  );
  return data.thread;
}

export async function requestConversationDeletion(
  thread: ConversationThread,
): Promise<ConversationThread> {
  const path = '/api/v1/conversations/' + encodeURIComponent(thread.thread_id)
    + '?expected_thread_version=' + encodeURIComponent(String(thread.version));
  const data = await requireData(
    api.delete<{ thread: ConversationThread }>(path),
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
  },
): Promise<ConversationTurn> {
  const data = await requireData(
    api.post<ConversationTurn>(
      '/api/v1/ai/chat',
      {
        message: input.message,
        thread_id: thread.thread_id,
        idempotency_key: input.idempotencyKey,
        expected_thread_version: thread.version,
        context: input.context,
        memory_policy: input.memoryPolicy,
        response_mode: input.deferred === false ? 'wait' : 'deferred',
      },
      {
        signal: input.signal,
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
  input: { signal?: AbortSignal } = {},
): Promise<ConversationTurn> {
  const data = await requireData(
    api.get<ConversationTurn>(
      '/api/v1/ai/chat/turns/'
        + encodeURIComponent(threadId)
        + '/'
        + encodeURIComponent(idempotencyKey),
      {
        signal: input.signal,
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

export async function cancelConversationTurn(
  threadId: string,
  idempotencyKey: string,
  input: {
    reason?: string;
    signal?: AbortSignal;
  } = {},
): Promise<ConversationTurn> {
  return requireData(
    api.post<ConversationTurn>(
      '/api/v1/ai/chat/turns/'
        + encodeURIComponent(threadId)
        + '/'
        + encodeURIComponent(idempotencyKey)
        + '/cancel',
      {
        reason: input.reason || 'user_cancelled',
      },
      {
        signal: input.signal,
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
