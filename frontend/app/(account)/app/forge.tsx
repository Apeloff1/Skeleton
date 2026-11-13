/** Forge tab: entry to the forge operator (Pack F) and the GameForge studio. */
import { useRouter } from 'expo-router';
import { ScrollView } from 'react-native';
import { AppText, Button, Screen, Stack, useT } from '../../../src/foundation';

export default function ForgeTab() {
  const { t } = useT();
  const router = useRouter();
  return (
    <Screen>
      <ScrollView contentContainerStyle={{ flexGrow: 1 }}>
        <Stack gap="lg" padding="xl">
          <AppText variant="h1">{t('forge.title')}</AppText>
          <AppText color="textMuted">{t('forge.hint')}</AppText>
          <Button label={t('forge.open')} icon="hammer" onPress={() => router.push('/forge-operator')} fullWidth />
          <Button label="GameForge Studio" variant="secondary" onPress={() => router.push('/gameforge-studio')} fullWidth />
        </Stack>
      </ScrollView>
    </Screen>
  );
}
