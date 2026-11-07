/**
 * Auth-gated route group. Every screen under app/(account) requires a session;
 * anonymous users are redirected to /sign-in?returnTo=<path>.
 */
import { Stack } from 'expo-router';
import { AuthGate, color } from '../../src/foundation';

export { RouteErrorFallback as ErrorBoundary } from '../../src/foundation';

export default function AccountGroupLayout() {
  return (
    <AuthGate>
      <Stack screenOptions={{ headerShown: false, animation: 'slide_from_right', contentStyle: { backgroundColor: color.bg } }} />
    </AuthGate>
  );
}
