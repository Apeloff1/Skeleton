import React from 'react';
import { useRouter } from 'expo-router';
import { ErrorState, Screen } from '../components/primitives';
import { t } from './strings';

/**
 * Per-route error fallback matching expo-router's `ErrorBoundary` export
 * contract. Re-export from a route or layout:
 *   export { RouteErrorFallback as ErrorBoundary } from '../src/foundation';
 */
export function RouteErrorFallback({ error, retry }: { error: Error; retry: () => Promise<void> }) {
  const router = useRouter();
  return (
    <Screen gradient={false}>
      <ErrorState
        title={t('error.route')}
        message={t('error.routeHint')}
        error={error}
        onRetry={() => { void retry(); }}
        fallbackAction={{ label: t('error.home'), onPress: () => router.replace('/') }}
      />
    </Screen>
  );
}

export default RouteErrorFallback;
