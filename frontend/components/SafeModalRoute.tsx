/**
 * SafeModalRoute — universal wrapper for converting a legacy modal into
 * a native expo-router route with crash isolation.
 *
 * Usage:
 *   import { makeModalRoute } from '../components/SafeModalRoute';
 *   import { FooModal } from '../features/Foo/FooModal';
 *   export default makeModalRoute(FooModal, 'FooRoute');
 *
 * What it does:
 *   1. Renders the modal with visible={true} so it's always shown.
 *   2. Wires onClose → router.back() with /hub fallback.
 *   3. Wraps the whole thing in withScreenGuard so a render crash
 *      shows a recoverable trace instead of taking down the app.
 *   4. Passes safe defaults for the common optional props (colors,
 *      code, language) so most legacy modals "just work".
 *
 * If a modal needs MORE than these defaults, override with a custom
 * wrapper file (see /app/leaderboard.tsx for a 1-off example).
 */
import React from 'react';
import { View, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { withScreenGuard } from './withScreenGuard';
import theme from '../theme/tokens';

interface ModalProps {
  visible:   boolean;
  onClose:   () => void;
  colors?:   any;
  code?:     string;
  language?: string;
  [k: string]: any;
}

// Shared close handler: router.back() with a /hub fallback.
function useModalClose() {
  const router = useRouter();
  return () => {
    try {
      if (router.canGoBack()) router.back();
      else router.replace('/hub');
    } catch {
      try { router.replace('/hub'); } catch { /* swallow */ }
    }
  };
}

export function makeModalRoute<P extends ModalProps>(
  ModalComponent: React.ComponentType<P>,
  routeName:      string,
  extraProps?:    Partial<P>,
): React.FC {
  function ModalRouteShim() {
    const close = useModalClose();
    const defaults: ModalProps = {
      visible:  true,
      onClose:  close,
      colors:   theme.colors as any,
      code:     '',
      language: 'python',
      ...(extraProps as any),
    };
    return <ModalComponent {...(defaults as any)} />;
  }
  ModalRouteShim.displayName = routeName;
  return withScreenGuard(ModalRouteShim, routeName);
}

/**
 * makeLazyModalRoute — same as makeModalRoute, but the heavy modal module is
 * loaded LAZILY via a dynamic import wrapped in React.lazy + Suspense.
 *
 * This keeps the modal's code (and its transitive deps) OUT of the boot-time
 * `require.context` evaluation that expo-router runs over every route file —
 * the root cause of on-device OOM crashes. The module only evaluates when the
 * route is actually visited.
 *
 * Usage:
 *   export default makeLazyModalRoute(() => import('../features/Foo/FooModal'), 'FooRoute', 'FooModal');
 */
export function makeLazyModalRoute(
  loader:      () => Promise<any>,
  routeName:   string,
  exportKey?:  string,
  extraProps?: Record<string, any>,
): React.FC {
  const Lazy = React.lazy(() =>
    loader().then((m: any) => {
      const C = (exportKey && m[exportKey]) || m.default || Object.values(m).find((v) => typeof v === 'function');
      if (!C) {
        console.error(`[makeLazyModalRoute] '${routeName}': export '${exportKey}' not found in module`, Object.keys(m));
      }
      return { default: C };
    }),
  );
  function LazyModalRouteShim() {
    const close = useModalClose();
    const defaults: ModalProps = {
      visible:  true,
      onClose:  close,
      colors:   theme.colors as any,
      code:     '',
      language: 'python',
      ...(extraProps as any),
    };
    return (
      <React.Suspense
        fallback={
          <View style={{ flex: 1, backgroundColor: '#05070d', alignItems: 'center', justifyContent: 'center' }}>
            <ActivityIndicator color="#A78BFA" />
          </View>
        }
      >
        <Lazy {...(defaults as any)} />
      </React.Suspense>
    );
  }
  LazyModalRouteShim.displayName = routeName;
  return withScreenGuard(LazyModalRouteShim, routeName);
}
