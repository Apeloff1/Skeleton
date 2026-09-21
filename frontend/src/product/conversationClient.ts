import api from '../utils/apiClient';

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

type ApiResult<T> = { ok: boolean; status: number; data?: T; error?: unknown };

async function requireData<T>(promise: Promise<ApiResult<T>>, message: string): Promise<T> {
  const result = await promise;
  if (!result.ok || !result.data) throw new Error(message);
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
