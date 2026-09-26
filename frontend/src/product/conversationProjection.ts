export type CanonicalThreadProjection = {
  thread_id: string;
  message_sequence: number;
};

export type CanonicalMessageProjection = {
  thread_id: string;
  sequence: number;
};

export type ValidatedConversationProjection<TMessage extends CanonicalMessageProjection> = {
  messages: TMessage[];
  lastSequence: number;
};

export function validateConversationProjection<TMessage extends CanonicalMessageProjection>(
  thread: CanonicalThreadProjection,
  sourceMessages: readonly TMessage[],
): ValidatedConversationProjection<TMessage> {
  const messages = [...sourceMessages].sort(
    (left, right) => left.sequence - right.sequence,
  );

  let previous = 0;
  for (const message of messages) {
    if (message.thread_id !== thread.thread_id) {
      throw new Error('Conversation projection contains a foreign thread message.');
    }
    if (!Number.isInteger(message.sequence) || message.sequence < 1) {
      throw new Error('Conversation projection contains an invalid sequence.');
    }
    if (message.sequence <= previous) {
      throw new Error('Conversation projection is not strictly ordered.');
    }
    if (message.sequence > thread.message_sequence) {
      throw new Error('Conversation projection is ahead of canonical thread state.');
    }
    previous = message.sequence;
  }

  return {
    messages,
    lastSequence: previous,
  };
}
