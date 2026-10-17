/**
 * Home tab: system health (/api/health/overview) + live build progress.
 * Live data comes from the canonical SSE stream (ADR-realtime-transport v1);
 * the overview REST poll only runs while the stream is not open, and
 * `stream.reset` invalidates the cached queries so they refetch over REST.
 */
import { useCallback, useState } from 'react';
import { Pressable, RefreshControl, ScrollView } from 'react-native';
import { useRouter } from 'expo-router';
import { useOverview } from '../../../src/hooks/useOverview';
import {
  AppText, AsyncView, BuildProgress, Card, color, Envelope, failingSubsystems, formatUptime, minTouch,
  overviewKey, reduceBuildProgress, Row, Screen, Stack, useEventStream, useSession, useT, vaultKey,
} from '../../../src/foundation';

const PILL: Record<string, 'success' | 'warning' | 'danger' | 'textMuted'> = {
  green: 'success', yellow: 'warning', red: 'danger', grey: 'textMuted',
};
const BUILD_TONE: Record<BuildProgress['status'], 'textMuted' | 'success' | 'danger'> = {
  running: 'textMuted', completed: 'success', failed: 'danger',
};

export default function HomeTab() {
  const { t } = useT();
  const router = useRouter();
  const role = useSession(s => s.role);
  const [builds, setBuilds] = useState<Record<string, BuildProgress>>({});
  const onEvent = useCallback((env: Envelope) => setBuilds(prev => reduceBuildProgress(prev, env)), []);
  const stream = useEventStream({ channels: ['build', 'agent'], onEvent, invalidateOnReset: [overviewKey, vaultKey(80)] });
  // Polling fallback: REST poll only while the realtime stream is not open.
  const overview = useOverview({ intervalMs: stream.connected ? 0 : 30_000 });
  const recent = Object.values(builds).sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1)).slice(0, 5);

  return (
    <Screen>
      <ScrollView
        contentContainerStyle={{ flexGrow: 1 }}
        refreshControl={<RefreshControl refreshing={overview.query.fetching && overview.query.status === 'success'} onRefresh={() => { void overview.refresh(); }} />}
      >
        <Stack gap="lg" padding="xl">
          <AppText variant="h1">{t('home.title')}</AppText>
          <Row gap="sm" accessible accessibilityLabel={stream.connected ? t('live.connected') : t('live.offline')}>
            <AppText color={stream.connected ? 'success' : 'textMuted'}>●</AppText>
            <AppText color="textMuted">{stream.connected ? t('live.connected') : t('live.offline')} · {t('auth.role', { role })}</AppText>
          </Row>
          {stream.laggedNotice !== null ? (
            <Pressable accessibilityRole="button" accessibilityLabel={t('live.lagged')} onPress={stream.dismissLagged} style={{ minHeight: minTouch, justifyContent: 'center' }}>
              <AppText color="warning">{t('live.lagged')}</AppText>
            </Pressable>
          ) : null}

          <AppText variant="h3">{t('home.systems')}</AppText>
          <AsyncView query={overview.query}>
            {data => {
              const failing = failingSubsystems(data);
              const summary = data.all_green ? t('home.allGreen') : t('home.failing', { count: failing.length });
              return (
                <Stack gap="sm" accessible accessibilityLabel={summary}>
                  <Row gap="sm">
                    <AppText variant="h3" color={PILL[overview.colour]}>●</AppText>
                    <AppText variant="bodyLg">{summary}</AppText>
                  </Row>
                  <AppText color="textMuted">{t('home.uptime', { value: formatUptime(data.process?.uptime_s ?? 0) })}</AppText>
                  {failing.map(name => <AppText key={name} color="warning">• {name.replace(/_/g, ' ')}</AppText>)}
                </Stack>
              );
            }}
          </AsyncView>

          <AppText variant="h3">{t('home.builds')}</AppText>
          {recent.length === 0 ? (
            <AppText color="textMuted">{t('home.noBuilds')}</AppText>
          ) : recent.map(b => (
            <Stack key={b.jobId} gap="xs" accessible accessibilityRole="progressbar"
              accessibilityLabel={`${b.jobId}: ${b.message || b.status}`}
              accessibilityValue={b.percent === null ? undefined : { min: 0, max: 100, now: b.percent }}>
              <Row gap="sm" justify="space-between">
                <AppText numberOfLines={1} style={{ flex: 1 }}>{b.message || b.jobId}</AppText>
                <AppText color={BUILD_TONE[b.status]}>{b.percent === null ? b.status : `${b.percent}%`}</AppText>
              </Row>
            </Stack>
          ))}

          <Card title={t('tab.forge')} desc={t('forge.hint')} icon="hammer" color={color.primary} widthPct="100%" onPress={() => router.push('/app/forge')} />
        </Stack>
      </ScrollView>
    </Screen>
  );
}
