import { AppState, Platform } from 'react-native';
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import { getAuthToken } from '../auth/gameforgeAuth';
import { ChatController, type ChatControllerOptions } from './chatController';

export function useChatController(options: ChatControllerOptions = {}) {
  const headersKey = JSON.stringify(options.headers ?? {});
  const authToken = getAuthToken();
  const seenAuthToken = useRef(authToken);
  const [, refreshAuthView] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => {
      const current = getAuthToken();
      if (current !== seenAuthToken.current) {
        seenAuthToken.current = current;
        refreshAuthView(value => value + 1);
      }
    }, 500);
    return () => clearInterval(timer);
  }, []);
  const controller = useMemo(() => new ChatController({
    initialThreadId: options.initialThreadId,
    headers: JSON.parse(headersKey) as Record<string, string>,
  }), [options.initialThreadId, headersKey, authToken]);
  const mounts = useRef(new Map<ChatController, number>());
  const state = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  useEffect(() => {
    const activeMounts = mounts.current;
    activeMounts.set(controller, (activeMounts.get(controller) ?? 0) + 1);
    void controller.initialize();
    const reconnect = () => {
      const current = controller.getSnapshot();
      if (current.pending && current.status === 'error') void controller.reconnect().catch(() => {});
    };
    const appStateSubscription = AppState.addEventListener('change', state => { if (state === 'active') reconnect(); });
    if (Platform.OS === 'web' && typeof window !== 'undefined') window.addEventListener('online', reconnect);
    return () => {
      appStateSubscription.remove();
      if (Platform.OS === 'web' && typeof window !== 'undefined') window.removeEventListener('online', reconnect);
      // React's strict effect remount reuses the store. Dispose only if it stays detached.
      activeMounts.set(controller, (activeMounts.get(controller) ?? 1) - 1);
      Promise.resolve().then(() => {
        if (activeMounts.get(controller) === 0) {
          activeMounts.delete(controller);
          controller.dispose();
        }
      });
    };
  }, [controller]);
  return { controller, state };
}

export type { ChatControllerState, PendingChatTurn, SendChatOptions } from './chatController';
export type { ChatModel } from './aiChatClient';
export { ChatClientError } from './chatErrors';
