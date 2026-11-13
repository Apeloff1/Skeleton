/** Settings tab: language (shared src/i18n locale), account, and the full settings area. */
import { useRouter } from 'expo-router';
import { ScrollView } from 'react-native';
import { useI18n } from '../../../src/i18n';
import { AppText, Button, Row, Screen, Stack, useT } from '../../../src/foundation';

const LANGS: { id: string; label: string }[] = [{ id: 'en', label: 'English' }, { id: 'nb', label: 'Norsk bokmål' }];

export default function SettingsTab() {
  const { t, locale } = useT();
  const { setLocale } = useI18n();
  const router = useRouter();
  return (
    <Screen>
      <ScrollView contentContainerStyle={{ flexGrow: 1 }}>
        <Stack gap="lg" padding="xl">
          <AppText variant="h1">{t('settings.title')}</AppText>
          <AppText variant="h3">{t('settings.language')}</AppText>
          <Row gap="sm" wrap accessibilityRole="radiogroup">
            {LANGS.map(l => (
              <Button
                key={l.id}
                label={l.label}
                variant={locale === l.id ? 'primary' : 'secondary'}
                onPress={() => setLocale(l.id)}
                accessibilityLabel={`${t('settings.language')}: ${l.label}`}
              />
            ))}
          </Row>
          <Button label={t('settings.account')} variant="secondary" onPress={() => router.push('/account')} fullWidth />
          <Button label={t('settings.all')} variant="ghost" onPress={() => router.push('/settings')} fullWidth />
        </Stack>
      </ScrollView>
    </Screen>
  );
}
