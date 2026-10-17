/** Home tab: greeting + system health from /api/health/overview (shared cached query). */
import { RefreshControl, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import { useOverview } from '../../../src/hooks/useOverview';
import {
  AppText, AsyncView, Card, color, failingSubsystems, formatUptime, Row, Screen, Stack, useSession, useT,
} from '../../../src/foundation';

const PILL: Record<string, 'success' | 'warning' | 'danger' | 'textMuted'> = {
  green: 'success', yellow: 'warning', red: 'danger', grey: 'textMuted',
};

export default function HomeTab() {
  const { t } = useT();
  const router = useRouter();
  const role = useSession(s => s.role);
  // TODO(realtime, slice 3): replace this poll with useEventStream on Walt's
  // SSE transport (GET /api/v1/events, PR #4101 / ADR-realtime-transport.md),
  // refetching over REST on stream.reset. Do not use the #4085 tunnel heartbeat.
  const overview = useOverview({ intervalMs: 30_000 });
  return (
    <Screen>
      <ScrollView
        contentContainerStyle={{ flexGrow: 1 }}
        refreshControl={<RefreshControl refreshing={overview.query.fetching && overview.query.status === 'success'} onRefresh={() => { void overview.refresh(); }} />}
      >
        <Stack gap="lg" padding="xl">
          <AppText variant="h1">{t('home.title')}</AppText>
          <AppText color="textMuted">{t('auth.role', { role })}</AppText>
          <AppText variant="h3">{t('home.systems')}</AppText>
          <AsyncView query={overview.query}>
            {data => {
              const failing = failingSubsystems(data);
              return (
                <Stack gap="sm" accessible accessibilityLabel={data.all_green ? t('home.allGreen') : t('home.failing', { count: failing.length })}>
                  <Row gap="sm">
                    <AppText variant="h3" color={PILL[overview.colour]}>●</AppText>
                    <AppText variant="bodyLg">{data.all_green ? t('home.allGreen') : t('home.failing', { count: failing.length })}</AppText>
                  </Row>
                  <AppText color="textMuted">{t('home.uptime', { value: formatUptime(data.process?.uptime_s ?? 0) })}</AppText>
                  {failing.map(name => <AppText key={name} color="warning">• {name.replace(/_/g, ' ')}</AppText>)}
                </Stack>
              );
            }}
          </AsyncView>
          <Card title={t('tab.forge')} desc={t('forge.hint')} icon="hammer" color={color.primary} widthPct="100%" onPress={() => router.push('/app/forge')} />
        </Stack>
      </ScrollView>
    </Screen>
  );
}
