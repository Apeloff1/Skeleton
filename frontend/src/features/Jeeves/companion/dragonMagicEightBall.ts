/** Software-only waiting toy. It never interprets a request or answers it. */
export const DRAGON_WAIT_PHRASES = Object.freeze([
  'Toy says yes. Your real answer is still coming.',
  'Toy says no. Your real answer is still coming.',
  'Toy says maybe. Your real answer is still coming.',
  'I have to think about that.',
  'Your request is next.', 'I am making room for that.', 'A tiny thinking pause.',
  'Let me catch my breath.', 'I am listening.', 'Time to put on my glasses.',
  'Let me settle my wings.', 'I will take a closer look.', 'Just gathering my thoughts.',
  'Your turn comes first.', 'Let me finish this small step.', 'One moment, adventurer.',
  'I have that in mind.', 'Let me switch gears.', 'A little patience, please.',
  'I am getting ready.', 'I am keeping your place.',
  'The crystal ball is warming up.', 'Let me pause my practice.', 'Thinking time is coming.',
] as const);

export function dragonWaitingBubble(requestId: string): string {
  // No timer, LLM, network, storage, request-text analysis or allocation loop.
  if (!requestId || requestId.length > 128) return DRAGON_WAIT_PHRASES[0];
  let hash = 2166136261;
  for (let i = 0; i < requestId.length; i++) hash = Math.imul(hash ^ requestId.charCodeAt(i), 16777619);
  return DRAGON_WAIT_PHRASES[(hash >>> 0) % DRAGON_WAIT_PHRASES.length];
}
