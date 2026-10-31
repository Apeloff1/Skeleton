import React, { useEffect } from 'react';
import { ActivityIndicator } from 'react-native';
import { Redirect, usePathname } from 'expo-router';
import { ErrorState } from '../components/primitives';
import { AppText } from './AppText';
import { Stack } from './Stack';
import { color } from './tokens';
import { t } from './strings';
import { decideGate } from './sessionGate';
import { selectSnapshot, useSession } from './sessionStore';
import { useShallow } from 'zustand/react/shallow';

/** Renders children only when the session gate allows; otherwise waits, errors, or redirects to sign-in. */
export function AuthGate({ children, requiredRole }: { children: React.ReactNode; requiredRole?: string }) {
  const pathname = usePathname();
  const snapshot = useSession(useShallow(selectSnapshot));
  const refresh = useSession(s => s.refresh);

  useEffect(() => {
    if (snapshot.status === 'unknown') void refresh();
  }, [snapshot.status, refresh]);

  const decision = decideGate(snapshot, pathname || '/', { requiredRole });
  switch (decision.kind) {
    case 'allow':
      return <>{children}</>;
    case 'redirect':
      return <Redirect href={decision.to as never} />;
    case 'error':
      return <ErrorState title={t('auth.unavailable')} message={decision.message} onRetry={() => { void refresh(); }} />;
    default:
      return (
        <Stack align="center" justify="center" padding="xl" gap="sm" style={{ flex: 1, backgroundColor: color.bg }}
          accessibilityRole="progressbar" accessibilityLabel={t('auth.checking')}>
          <ActivityIndicator color={color.primary} />
          <AppText color="textMuted">{t('auth.checking')}</AppText>
        </Stack>
      );
  }
}

export default AuthGate;
