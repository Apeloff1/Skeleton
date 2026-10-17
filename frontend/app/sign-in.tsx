/**
 * Sign-in route for the auth-gated groups. Reuses the existing StudioLoginGate
 * (email/password + Google via the public /api/auth contract); once the gate
 * admits the user, refresh the shared session and return to `returnTo`.
 */
import { useEffect } from 'react';
import { Redirect, useLocalSearchParams } from 'expo-router';
import StudioLoginGate from '../src/auth/StudioLoginGate';
import { safeReturnTo, t, useSession } from '../src/foundation';

export { RouteErrorFallback as ErrorBoundary } from '../src/foundation';

function Admitted({ returnTo }: { returnTo: string }) {
  const status = useSession(s => s.status);
  const refresh = useSession(s => s.refresh);
  useEffect(() => { if (status !== 'authenticated') void refresh(); }, [status, refresh]);
  if (status !== 'authenticated') return null;
  return <Redirect href={returnTo as never} />;
}

export default function SignInScreen() {
  const params = useLocalSearchParams<{ returnTo?: string }>();
  const returnTo = safeReturnTo(params.returnTo);
  return (
    <StudioLoginGate title={t('app.name')} requireAuthenticated>
      <Admitted returnTo={returnTo} />
    </StudioLoginGate>
  );
}
