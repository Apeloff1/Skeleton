import React from 'react';
import { useLocalSearchParams } from 'expo-router';
import ChatWorkspace from '../features/Jeeves/ChatWorkspace';

export default function AIChatRoute() {
  const params = useLocalSearchParams<{ thread?: string | string[] }>();
  const raw = Array.isArray(params.thread) ? params.thread[0] : params.thread;
  const thread = typeof raw === 'string' && /^[0-9a-f-]{36}$/i.test(raw) ? raw : undefined;
  return <ChatWorkspace initialThreadId={thread} />;
}
