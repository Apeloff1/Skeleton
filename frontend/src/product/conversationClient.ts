import api, { type ApiResult } from '../utils/apiClient';

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
  attachment_refs: string[];
  tool_receipt_refs: string[];
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

export async function getConversationSnapshot(
  threadId: string,
  input: { activeOnly?: boolean } = {},
): Promise<{
  thread: ConversationThread;
  messages: ConversationMessage[];
  projection: 'active' | 'all';
  snapshotVersion: number;
  snapshotSequence: number;
}> {
  const suffix = input.activeOnly ? '?active_only=true' : '';
  const data = await requireData(
    api.get<{
      thread: ConversationThread;
      messages: ConversationMessage[];
      projection: 'active' | 'all';
      snapshot_version: number;
      snapshot_sequence: number;
    }>(
      '/api/v1/conversations/' + encodeURIComponent(threadId) + '/snapshot' + suffix,
    ),
    'Could not load conversation snapshot.',
  );
  if (
    data.snapshot_version !== data.thread.version
    || data.snapshot_sequence !== data.thread.message_sequence
  ) {
    throw new Error('Conversation snapshot metadata is inconsistent.');
  }
  return {
    thread: data.thread,
    messages: data.messages,
    projection: data.projection,
    snapshotVersion: data.snapshot_version,
    snapshotSequence: data.snapshot_sequence,
  };
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


export type CanonicalChatResult = {
  success: boolean;
  approval_required?: boolean;
  response?: string;
  provider?: string;
  model?: string;
  engine_execution_id?: string;
  engine_result_ref?: string;
  verification?: string | null;
  verification_receipt?: Record<string, unknown> | null;
  evidence_refs?: string[];
  usage?: Record<string, unknown>;
  thread: ConversationThread;
  user_message: ConversationMessage;
  assistant_message?: ConversationMessage;
  pending_approvals?: Array<{
    call_id: string;
    tool_id: string;
    arguments_digest: string;
  }>;
};

export async function listAllConversationMessages(
  threadId: string,
  input: { activeOnly?: boolean; pageSize?: number } = {},
): Promise<ConversationMessage[]> {
  const pageSize = Math.max(1, Math.min(500, input.pageSize || 200));
  const messages: ConversationMessage[] = [];
  let afterSequence = 0;
  const seen = new Set<number>();

  for (;;) {
    const page = await listConversationMessages(threadId, {
      afterSequence,
      limit: pageSize,
      activeOnly: input.activeOnly,
    });
    for (const message of page.messages) {
      if (seen.has(message.sequence)) continue;
      seen.add(message.sequence);
      messages.push(message);
    }
    if (page.nextAfterSequence === null) break;
    if (
      !Number.isSafeInteger(page.nextAfterSequence)
      || page.nextAfterSequence <= afterSequence
    ) {
      throw new Error('Conversation pagination did not advance.');
    }
    afterSequence = page.nextAfterSequence;
  }

  return messages.sort((left, right) => left.sequence - right.sequence);
}

export async function sendCanonicalConversationTurn(
  input: {
    threadId: string;
    expectedThreadVersion: number;
    message: string;
    idempotencyKey: string;
    context?: string;
    signal?: AbortSignal;
  },
): Promise<CanonicalChatResult> {
  const data = await requireData(
    api.post<CanonicalChatResult>(
      '/api/ai/chat',
      {
        message: input.message,
        thread_id: input.threadId,
        idempotency_key: input.idempotencyKey,
        expected_thread_version: input.expectedThreadVersion,
        context: input.context || undefined,
        conversation_history: [],
      },
      {
        signal: input.signal,
        timeoutMs: 95_000,
        retries: 0,
      },
    ),
    'Could not complete the conversation turn.',
  );
  if (!data.thread || !data.user_message) {
    throw new Error('Conversation response is missing canonical lineage.');
  }
  return data;
}

export async function sendCanonicalConversationMessage(
  thread: ConversationThread,
  input: {
    message: string;
    idempotencyKey: string;
    context?: string;
    signal?: AbortSignal;
  },
): Promise<CanonicalChatResult> {
  return sendCanonicalConversationTurn({
    threadId: thread.thread_id,
    expectedThreadVersion: thread.version,
    message: input.message,
    idempotencyKey: input.idempotencyKey,
    context: input.context,
    signal: input.signal,
  });
}

export async function setConversationStateById(
  threadId: string,
  expectedThreadVersion: number,
  state: 'active' | 'archived' | 'deleting',
): Promise<ConversationThread> {
  const data = await requireData(
    api.patch<{ thread: ConversationThread }>(
      '/api/v1/conversations/' + encodeURIComponent(threadId) + '/state',
      {
        state,
        expected_thread_version: expectedThreadVersion,
      },
    ),
    'Could not update conversation state.',
  );
  return data.thread;
}

export async function requestConversationDeletionById(
  threadId: string,
  expectedThreadVersion: number,
): Promise<ConversationThread> {
  const path = '/api/v1/conversations/' + encodeURIComponent(threadId)
    + '?expected_thread_version='
    + encodeURIComponent(String(expectedThreadVersion));
  const data = await requireData(
    api.delete<{ thread: ConversationThread }>(path),
    'Could not request conversation deletion.',
  );
  return data.thread;
}

export async function exportConversationSnapshot(
  threadId: string,
): Promise<{
  thread: ConversationThread;
  messages: ConversationMessage[];
}> {
  const snapshot = await getConversationSnapshot(threadId, {
    activeOnly: false,
  });
  return {
    thread: snapshot.thread,
    messages: snapshot.messages,
  };
}
