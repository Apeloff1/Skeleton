const LABELS: Record<string, string> = {
  connecting: 'Connecting to your conversation…', prepared: 'Conversation saved; preparing admission…',
  reconnecting: 'Reconnecting to the saved turn…', awaiting_admission: 'Saved; waiting for engine admission…',
  received: 'Message received', admitted: 'Turn admitted', accepted: 'Turn accepted',
  user_message_committed: 'Your message is saved', context_compiling: 'Preparing the authorized context…',
  routing: 'Selecting the configured model…', model_running: 'The configured model is running…',
  verifying: 'Checking the recorded result…', finalizing: 'Saving the final answer…',
  finalization_in_progress: 'Saving the final answer…', assistant_message_committed: 'Answer saved; settling the turn…',
  complete: 'The turn is complete', completed: 'The turn is complete', cancelling: 'Stop requested; waiting for confirmation…',
  cancel_requested: 'Stop requested; waiting for confirmation…', cancellation_unconfirmed: 'Stop not confirmed; checking the server…',
  waiting_approval: 'Waiting for your approval', waiting_input: 'Waiting for the requested input',
};

export function chatProgressLabel(state?: string): string {
  return LABELS[state || ''] || (state && /^[a-z0-9_.-]{1,80}$/i.test(state)
    ? `Recorded state: ${state.replaceAll('_', ' ').replaceAll('.', ' ')}` : 'Following the saved turn…');
}
