export class ConversationProjectionError extends Error {
  readonly code: string;
  constructor(message: string, input: { code: string }) {
    super(message);
    this.name = 'ConversationProjectionError';
    this.code = input.code;
  }
}

export type CanonicalThreadProjection = {
  thread_id: string;
  message_sequence: number;
};

export type CanonicalMessageProjection = {
  thread_id: string;
  sequence: number;
  message_id?: string;
};

export type ValidatedConversationProjection<TMessage extends CanonicalMessageProjection> = {
  messages: TMessage[];
  lastSequence: number;
};

export function validateConversationProjection<TMessage extends CanonicalMessageProjection>(
  thread: CanonicalThreadProjection,
  sourceMessages: readonly TMessage[],
): ValidatedConversationProjection<TMessage> {
  if (!thread || typeof thread.thread_id !== 'string' || !thread.thread_id
    || !Number.isSafeInteger(thread.message_sequence) || thread.message_sequence < 0
    || !Array.isArray(sourceMessages) || sourceMessages.length > 10000) {
    throw new ConversationProjectionError('Canonical conversation projection is invalid.', { code: 'invalid_projection' });
  }
  // Validate before sorting: a malformed/null element must produce a stable
  // projection error rather than throwing from the comparator.
  for (const message of sourceMessages) {
    if (!message || typeof message !== 'object') {
      throw new ConversationProjectionError('Canonical message must be an object.', { code: 'invalid_message' });
    }
    if (!Number.isSafeInteger(message.sequence) || message.sequence < 1) {
      throw new ConversationProjectionError('Conversation projection contains an invalid sequence.', { code: 'invalid_sequence' });
    }
  }
  const messages = [...sourceMessages].sort((left, right) => left.sequence - right.sequence);
  const ids = new Set<string>();
  let previous = 0;
  for (const message of messages) {
    if (!message || typeof message !== 'object') {
      throw new ConversationProjectionError('Canonical message must be an object.', { code: 'invalid_message' });
    }
    if (message.thread_id !== thread.thread_id) {
      throw new ConversationProjectionError('Conversation projection contains a foreign thread message.', { code: 'foreign_thread' });
    }
    if (!Number.isSafeInteger(message.sequence) || message.sequence < 1) {
      throw new ConversationProjectionError('Conversation projection contains an invalid sequence.', { code: 'invalid_sequence' });
    }
    if (message.sequence <= previous) {
      throw new ConversationProjectionError('Conversation projection is not strictly ordered.', { code: 'invalid_sequence' });
    }
    if (message.sequence > thread.message_sequence) {
      throw new ConversationProjectionError('Conversation projection is ahead of canonical thread state.', { code: 'stale_projection' });
    }
    if (message.message_id !== undefined) {
      if (typeof message.message_id !== 'string' || !message.message_id || ids.has(message.message_id)) {
        throw new ConversationProjectionError('Conversation projection contains a duplicate or invalid message identity.', { code: 'invalid_message' });
      }
      ids.add(message.message_id);
    }
    previous = message.sequence;
  }
  return { messages, lastSequence: previous };
}
