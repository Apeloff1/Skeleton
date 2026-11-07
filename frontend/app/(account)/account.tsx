/** Account overview — first screen on the app-foundation shell (gated). */
import { useRouter } from 'expo-router';
import { ScrollView } from 'react-native';
import { AppText, Button, Screen, Stack, t, useSession } from '../../src/foundation';

function displayName(user: unknown): string {
  if (user && typeof user === 'object') {
    const u = user as { name?: unknown; email?: unknown };
    if (typeof u.name === 'string' && u.name) return u.name;
    if (typeof u.email === 'string' && u.email) return u.email;
  }
  return t('app.name');
}

export default function AccountScreen() {
  const router = useRouter();
  const user = useSession(s => s.user);
  const role = useSession(s => s.role);
  const signOut = useSession(s => s.signOut);
  return (
    <Screen>
      <ScrollView contentContainerStyle={{ flexGrow: 1 }}>
        <Stack gap="lg" padding="xl">
          <AppText variant="h1">{t('nav.account')}</AppText>
          <Stack gap="xs">
            <AppText variant="bodyLg">{t('auth.signedInAs', { name: displayName(user) })}</AppText>
            <AppText color="textMuted">{t('auth.role', { role })}</AppText>
          </Stack>
          <Button label={t('nav.settings')} variant="secondary" onPress={() => router.push('/settings')} accessibilityLabel={t('nav.settings')} />
          <Button
            label={t('auth.signOut')}
            variant="destructive"
            onPress={() => { void signOut().then(() => router.replace('/sign-in')); }}
            accessibilityLabel={t('auth.signOut')}
          />
        </Stack>
      </ScrollView>
    </Screen>
  );
}
