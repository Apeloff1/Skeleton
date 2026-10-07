import { API_BASE as CANONICAL_API_BASE } from '../utils/apiBase';
/**
 * /jeeves-hub — Jeeves operator console.
 *
 * Probes the public Jeeves service surface, records latency, classifies service
 * health and gives the operator focused retry/inspection controls. This stays
 * on the already-registered /jeeves-hub route so route coverage and existing
 * deep links remain stable.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Modal,
  RefreshControl,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useFeatureFlag } from '../utils/featureFlags';
import { jeevesSpeak } from '../features/Academy/jeevesTts';

const BACKEND = CANONICAL_API_BASE || '';
const USER_ID = 'default_user';
const REQUEST_TIMEOUT_MS = 10_000;
const SLOW_THRESHOLD_MS = 1_500;

type Health = 'loading' | 'healthy' | 'slow' | 'down';
type Filter = 'all' | 'healthy' | 'issues';

type Service = {
  id: string;
  title: string;
  description: string;
  endpoint: string;
  icon: keyof typeof Ionicons.glyphMap;
  accent: string;
  voiceOnly?: boolean;
};

type Result = {
  loading: boolean;
  data?: unknown;
  error?: string;
  latencyMs?: number;
  checkedAt?: number;
};

const SERVICES: Service[] = [
  {
    id: 'persona',
    title: 'Jeeves Persona',
    description: 'Biography, mannerisms, catchphrases and persona knowledge.',
    endpoint: '/api/jeeves/persona',
    icon: 'happy-outline',
    accent: '#A78BFA',
  },
  {
    id: 'eq',
    title: 'Jeeves EQ',
    description: 'Emotion-aware tutoring and response capabilities.',
    endpoint: '/api/jeeves-eq/info',
    icon: 'heart-outline',
    accent: '#8B5CF6',
  },
  {
    id: 'voice',
    title: 'Jeeves Voice',
    description: 'Voice personality and synthesis configuration.',
    endpoint: '/api/jeeves-voice/personality',
    icon: 'mic-outline',
    accent: '#3B82F6',
    voiceOnly: true,
  },
  {
    id: 'hyperion',
    title: 'Jeeves Hyperion',
    description: 'Knowledge-base domains and archive statistics.',
    endpoint: '/api/jeeves-hyperion/knowledge-base/stats',
    icon: 'planet-outline',
    accent: '#FBBF24',
  },
  {
    id: 'synergy',
    title: 'Jeeves Synergy',
    description: 'Cross-module orchestration overview.',
    endpoint: '/api/jeeves-synergy/overview',
    icon: 'git-network-outline',
    accent: '#10B981',
  },
  {
    id: 'masterbuild',
    title: 'Master Game Builder',
    description: 'Genre catalogue for the spec-to-playable pipeline.',
    endpoint: '/api/jeeves-build/genres',
    icon: 'build-outline',
    accent: '#8B5CF6',
  },
  {
    id: 'camera',
    title: 'Jeeves Camera',
    description: 'Camera-driven learning and visual knowledge topics.',
    endpoint: '/api/jeeves/camera/knowledge',
    icon: 'camera-outline',
    accent: '#F472B6',
  },
  {
    id: 'daily',
    title: 'Daily Challenge',
    description: 'Current challenge feed for the default operator profile.',
    endpoint: `/api/daily/challenge?user_id=${USER_ID}`,
    icon: 'flame-outline',
    accent: '#EF4444',
  },
  {
    id: 'leaderboards',
    title: 'Leaderboards',
    description: 'Live leaderboard definitions and periods.',
    endpoint: '/api/leaderboards/boards',
    icon: 'trophy-outline',
    accent: '#FBBF24',
  },
  {
    id: 'gamification',
    title: 'XP · Level · Achievements',
    description: 'Gamification profile, progression and achievements.',
    endpoint: `/api/gamification/profile/${USER_ID}`,
    icon: 'medal-outline',
    accent: '#A3E635',
  },
];

function healthFor(result?: Result): Health {
  if (!result || result.loading) return 'loading';
  if (result.error) return 'down';
  if ((result.latencyMs ?? 0) > SLOW_THRESHOLD_MS) return 'slow';
  return 'healthy';
}

function healthColor(health: Health): string {
  if (health === 'healthy') return '#10B981';
  if (health === 'slow') return '#F59E0B';
  if (health === 'down') return '#EF4444';
  return '#64748B';
}

function healthLabel(health: Health): string {
  if (health === 'healthy') return 'HEALTHY';
  if (health === 'slow') return 'SLOW';
  if (health === 'down') return 'DOWN';
  return 'CHECKING';
}

function compactJson(value: unknown, limit = 180): string {
  try {
    const encoded = JSON.stringify(value);
    return (encoded ?? String(value)).slice(0, limit);
  } catch {
    return String(value).slice(0, limit);
  }
}

function payloadSummary(data: unknown): string {
  if (Array.isArray(data)) return `${data.length} record${data.length === 1 ? '' : 's'} returned`;
  if (data && typeof data === 'object') {
    const count = Object.keys(data as Record<string, unknown>).length;
    return `${count} top-level field${count === 1 ? '' : 's'} returned`;
  }
  if (data == null) return 'No payload returned';
  return String(data).slice(0, 120);
}

function payloadRows(data: unknown): { label: string; value: string }[] {
  if (Array.isArray(data)) {
    return data.slice(0, 8).map((item, index) => ({
      label: `Item ${index + 1}`,
      value: typeof item === 'string' ? item.slice(0, 180) : compactJson(item),
    }));
  }
  if (!data || typeof data !== 'object') {
    return data == null ? [] : [{ label: 'Value', value: String(data) }];
  }
  return Object.entries(data as Record<string, unknown>)
    .slice(0, 12)
    .map(([key, value]) => {
      let rendered: string;
      if (value == null) rendered = '—';
      else if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') rendered = String(value);
      else if (Array.isArray(value)) rendered = `${value.length} item${value.length === 1 ? '' : 's'}`;
      else rendered = compactJson(value);
      return { label: key.replace(/_/g, ' '), value: rendered };
    });
}

function formatCheckedAt(timestamp?: number): string {
  if (!timestamp) return 'Not checked yet';
  try {
    return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch {
    return 'Checked recently';
  }
}

async function fetchJsonWithTimeout(url: string): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(url, { signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error: any) {
    if (error?.name === 'AbortError') throw new Error(`Timed out after ${REQUEST_TIMEOUT_MS / 1000}s`);
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

export default function JeevesHubScreen() {
  const router = useRouter();
  const flagVoice = useFeatureFlag('experimental_voice');
  const flagAudioTest = useFeatureFlag('jeeves_audio_test');
  const generations = useRef<Record<string, number>>({});
  const [results, setResults] = useState<Record<string, Result>>(() =>
    Object.fromEntries(SERVICES.map(service => [service.id, { loading: true }])),
  );
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<Filter>('all');
  const [openId, setOpenId] = useState<string | null>(null);

  const visibleServices = useMemo(
    () => SERVICES.filter(service => !service.voiceOnly || flagVoice),
    [flagVoice],
  );

  const checkService = useCallback(async (service: Service) => {
    const generation = (generations.current[service.id] ?? 0) + 1;
    generations.current[service.id] = generation;

    setResults(previous => ({
      ...previous,
      [service.id]: {
        ...previous[service.id],
        loading: true,
        error: undefined,
      },
    }));

    const startedAt = Date.now();
    try {
      const data = await fetchJsonWithTimeout(`${BACKEND}${service.endpoint}`);
      if (generations.current[service.id] !== generation) return;
      setResults(previous => ({
        ...previous,
        [service.id]: {
          loading: false,
          data,
          latencyMs: Date.now() - startedAt,
          checkedAt: Date.now(),
        },
      }));
    } catch (error: any) {
      if (generations.current[service.id] !== generation) return;
      setResults(previous => ({
        ...previous,
        [service.id]: {
          loading: false,
          error: String(error?.message || error || 'Unknown error').slice(0, 120),
          latencyMs: Date.now() - startedAt,
          checkedAt: Date.now(),
        },
      }));
    }
  }, []);

  const checkAll = useCallback(async () => {
    setRefreshing(true);
    try {
      await Promise.all(visibleServices.map(checkService));
    } finally {
      setRefreshing(false);
    }
  }, [checkService, visibleServices]);

  useEffect(() => {
    checkAll().catch(() => {});
  }, [checkAll]);

  const stats = useMemo(() => {
    let healthy = 0;
    let slow = 0;
    let down = 0;
    const latencies: number[] = [];

    visibleServices.forEach(service => {
      const result = results[service.id];
      const health = healthFor(result);
      if (health === 'healthy') healthy += 1;
      if (health === 'slow') slow += 1;
      if (health === 'down') down += 1;
      if (!result?.error && typeof result?.latencyMs === 'number' && !result.loading) {
        latencies.push(result.latencyMs);
      }
    });

    const averageMs = latencies.length
      ? Math.round(latencies.reduce((sum, value) => sum + value, 0) / latencies.length)
      : null;

    return { healthy, slow, down, total: visibleServices.length, averageMs };
  }, [results, visibleServices]);

  const filteredServices = useMemo(() => {
    if (filter === 'all') return visibleServices;
    if (filter === 'healthy') {
      return visibleServices.filter(service => healthFor(results[service.id]) === 'healthy');
    }
    return visibleServices.filter(service => {
      const health = healthFor(results[service.id]);
      return health === 'slow' || health === 'down';
    });
  }, [filter, results, visibleServices]);

  const openService = useMemo(
    () => visibleServices.find(service => service.id === openId) || null,
    [openId, visibleServices],
  );
  const openResult = openService ? results[openService.id] : undefined;
  const openHealth = healthFor(openResult);

  const openDetails = (service: Service) => {
    setOpenId(service.id);
    const health = healthFor(results[service.id]);
    try {
      jeevesSpeak(
        `${service.title}. Service status ${healthLabel(health).toLowerCase()}.`,
        { context: 'lesson', prependCatchphrase: false },
      );
    } catch {}
  };

  return (
    <SafeAreaView style={styles.root}>
      <StatusBar barStyle="light-content" />

      <View style={styles.header}>
        <TouchableOpacity
          onPress={() => router.back()}
          style={styles.headerButton}
          accessibilityRole="button"
          accessibilityLabel="Go back"
        >
          <Ionicons name="chevron-back" size={22} color="#A78BFA" />
        </TouchableOpacity>
        <View style={styles.headerCopy}>
          <Text style={styles.eyebrow}>JEEVES CONTROL PLANE</Text>
          <Text style={styles.title}>Powerhouse Operator Hub</Text>
          <Text style={styles.subtitle}>Live health, latency and recovery controls</Text>
        </View>
        <TouchableOpacity
          onPress={() => checkAll()}
          style={styles.headerButton}
          accessibilityRole="button"
          accessibilityLabel="Refresh all Jeeves services"
          disabled={refreshing}
        >
          <Ionicons name={refreshing ? 'sync' : 'refresh'} size={20} color="#A78BFA" />
        </TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={(
          <RefreshControl
            refreshing={refreshing}
            onRefresh={checkAll}
            tintColor="#A78BFA"
          />
        )}
      >
        <View style={styles.summaryCard}>
          <View style={styles.summaryTopRow}>
            <View>
              <Text style={styles.summaryLabel}>Fleet health</Text>
              <Text style={styles.summaryValue}>{stats.healthy}/{stats.total} healthy</Text>
            </View>
            <View style={styles.latencyBox}>
              <Text style={styles.latencyLabel}>AVG LATENCY</Text>
              <Text style={styles.latencyValue}>{stats.averageMs == null ? '—' : `${stats.averageMs} ms`}</Text>
            </View>
          </View>

          <View style={styles.meterTrack}>
            <View
              style={[
                styles.meterFill,
                {
                  width: `${stats.total ? Math.round((stats.healthy / stats.total) * 100) : 0}%` as `${number}%`,
                },
              ]}
            />
          </View>

          <View style={styles.summaryStatusRow}>
            <Text style={styles.healthyText}>● {stats.healthy} healthy</Text>
            <Text style={styles.slowText}>● {stats.slow} slow</Text>
            <Text style={styles.downText}>● {stats.down} down</Text>
          </View>
        </View>

        <View style={styles.quickActions}>
          <QuickAction
            icon="chatbubble-ellipses-outline"
            label="Chat"
            onPress={() => router.push('/jeeves' as any)}
          />
          <QuickAction
            icon="analytics-outline"
            label="Telemetry"
            onPress={() => router.push('/telemetry' as any)}
          />
          <QuickAction
            icon="options-outline"
            label="Settings"
            onPress={() => router.push('/settings/jeeves' as any)}
          />
          {flagAudioTest && (
            <QuickAction
              icon="volume-high-outline"
              label="Audio"
              onPress={() => router.push('/jeeves-audio-test' as any)}
            />
          )}
        </View>

        <View style={styles.filterRow}>
          <FilterChip label={`All ${stats.total}`} active={filter === 'all'} onPress={() => setFilter('all')} />
          <FilterChip label={`Healthy ${stats.healthy}`} active={filter === 'healthy'} onPress={() => setFilter('healthy')} />
          <FilterChip label={`Issues ${stats.slow + stats.down}`} active={filter === 'issues'} onPress={() => setFilter('issues')} />
        </View>

        {filteredServices.length === 0 ? (
          <View style={styles.emptyState}>
            <Ionicons name="checkmark-circle-outline" size={28} color="#10B981" />
            <Text style={styles.emptyTitle}>No services in this view</Text>
            <Text style={styles.emptyText}>Change the filter or run another health check.</Text>
          </View>
        ) : (
          filteredServices.map(service => {
            const result = results[service.id];
            const health = healthFor(result);
            const color = healthColor(health);
            return (
              <TouchableOpacity
                key={service.id}
                activeOpacity={0.84}
                onPress={() => openDetails(service)}
                style={[styles.serviceCard, { borderColor: `${service.accent}55` }]}
                accessibilityRole="button"
                accessibilityLabel={`${service.title}, ${healthLabel(health)}`}
              >
                <View style={[styles.serviceIcon, { borderColor: service.accent, backgroundColor: `${service.accent}1F` }]}>
                  <Ionicons name={service.icon} size={21} color={service.accent} />
                </View>

                <View style={styles.serviceBody}>
                  <View style={styles.serviceTitleRow}>
                    <Text style={styles.serviceTitle} numberOfLines={1}>{service.title}</Text>
                    <View style={[styles.statusPill, { borderColor: `${color}66`, backgroundColor: `${color}1A` }]}>
                      <View style={[styles.statusDot, { backgroundColor: color }]} />
                      <Text style={[styles.statusText, { color }]}>{healthLabel(health)}</Text>
                    </View>
                  </View>
                  <Text style={styles.serviceDescription} numberOfLines={2}>{service.description}</Text>
                  <View style={styles.serviceMetaRow}>
                    <Text style={styles.serviceMeta} numberOfLines={1}>{service.endpoint}</Text>
                    <Text style={[styles.serviceLatency, { color }]}>
                      {result?.loading ? 'checking…' : typeof result?.latencyMs === 'number' ? `${result.latencyMs} ms` : '—'}
                    </Text>
                  </View>
                  {result?.error ? <Text style={styles.errorText} numberOfLines={2}>⚠ {result.error}</Text> : null}
                </View>

                <TouchableOpacity
                  onPress={event => {
                    event.stopPropagation();
                    checkService(service).catch(() => {});
                  }}
                  style={styles.retryButton}
                  accessibilityRole="button"
                  accessibilityLabel={`Retry ${service.title}`}
                >
                  <Ionicons name="refresh" size={17} color="#CBD5E1" />
                </TouchableOpacity>
              </TouchableOpacity>
            );
          })
        )}

        <Text style={styles.footerText}>
          Slow threshold {SLOW_THRESHOLD_MS} ms · request timeout {REQUEST_TIMEOUT_MS / 1000}s
        </Text>
      </ScrollView>

      <Modal
        visible={!!openService}
        transparent
        animationType="slide"
        onRequestClose={() => setOpenId(null)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <View style={styles.modalHeader}>
              <View style={[styles.serviceIcon, { borderColor: openService?.accent || '#A78BFA', backgroundColor: `${openService?.accent || '#A78BFA'}1F` }]}>
                <Ionicons name={openService?.icon || 'pulse-outline'} size={20} color={openService?.accent || '#A78BFA'} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.modalTitle}>{openService?.title}</Text>
                <Text style={[styles.modalStatus, { color: healthColor(openHealth) }]}>
                  {healthLabel(openHealth)}{typeof openResult?.latencyMs === 'number' ? ` · ${openResult.latencyMs} ms` : ''}
                </Text>
              </View>
              <TouchableOpacity
                onPress={() => setOpenId(null)}
                style={styles.modalClose}
                accessibilityRole="button"
                accessibilityLabel="Close service details"
              >
                <Ionicons name="close" size={22} color="#94A3B8" />
              </TouchableOpacity>
            </View>

            <ScrollView style={styles.modalScroll} contentContainerStyle={styles.modalContent}>
              <Text style={styles.modalDescription}>{openService?.description}</Text>
              <Text style={styles.endpointLabel}>ENDPOINT</Text>
              <Text style={styles.endpointText}>{openService?.endpoint}</Text>
              <Text style={styles.checkedText}>{formatCheckedAt(openResult?.checkedAt)}</Text>

              {openResult?.error ? (
                <View style={styles.errorBox}>
                  <Text style={styles.errorBoxTitle}>Probe failed</Text>
                  <Text style={styles.errorBoxText}>{openResult.error}</Text>
                </View>
              ) : openResult?.data !== undefined ? (
                <>
                  <Text style={styles.payloadSummary}>{payloadSummary(openResult.data)}</Text>
                  {payloadRows(openResult.data).map((row, index) => (
                    <View key={`${row.label}-${index}`} style={styles.detailRow}>
                      <Text style={styles.detailLabel}>{row.label}</Text>
                      <Text style={styles.detailValue} numberOfLines={4}>{row.value}</Text>
                    </View>
                  ))}
                </>
              ) : (
                <Text style={styles.payloadSummary}>No payload captured yet.</Text>
              )}
            </ScrollView>

            <View style={styles.modalActions}>
              <TouchableOpacity
                style={styles.primaryButton}
                onPress={() => openService && checkService(openService).catch(() => {})}
                accessibilityRole="button"
              >
                <Ionicons name="refresh" size={17} color="#FFFFFF" />
                <Text style={styles.primaryButtonText}>Retry service</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.secondaryButton}
                onPress={() => router.push('/telemetry' as any)}
                accessibilityRole="button"
              >
                <Ionicons name="analytics-outline" size={17} color="#A78BFA" />
                <Text style={styles.secondaryButtonText}>Open telemetry</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function QuickAction({
  icon,
  label,
  onPress,
}: {
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  onPress: () => void;
}) {
  return (
    <TouchableOpacity
      onPress={onPress}
      style={styles.quickAction}
      accessibilityRole="button"
      accessibilityLabel={label}
    >
      <Ionicons name={icon} size={18} color="#A78BFA" />
      <Text style={styles.quickActionText}>{label}</Text>
    </TouchableOpacity>
  );
}

function FilterChip({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <TouchableOpacity
      onPress={onPress}
      style={[styles.filterChip, active && styles.filterChipActive]}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
    >
      <Text style={[styles.filterChipText, active && styles.filterChipTextActive]}>{label}</Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#08090B' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 12,
    paddingVertical: 11,
    borderBottomWidth: 1,
    borderBottomColor: '#1B1D22',
  },
  headerButton: {
    width: 38,
    height: 38,
    borderRadius: 12,
    backgroundColor: '#12141A',
    borderWidth: 1,
    borderColor: '#242731',
    alignItems: 'center',
    justifyContent: 'center',
  },
  headerCopy: { flex: 1 },
  eyebrow: { color: '#7C6CA8', fontSize: 9, fontWeight: '900', letterSpacing: 1.2 },
  title: { color: '#F8FAFC', fontSize: 18, fontWeight: '900', marginTop: 1 },
  subtitle: { color: '#94A3B8', fontSize: 10, marginTop: 1 },
  content: { padding: 12, paddingBottom: 34 },
  summaryCard: {
    backgroundColor: '#11131A',
    borderRadius: 16,
    borderWidth: 1,
    borderColor: '#2B2540',
    padding: 14,
    marginBottom: 10,
  },
  summaryTopRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  summaryLabel: { color: '#94A3B8', fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.8 },
  summaryValue: { color: '#F8FAFC', fontSize: 22, fontWeight: '900', marginTop: 2 },
  latencyBox: { alignItems: 'flex-end' },
  latencyLabel: { color: '#64748B', fontSize: 9, fontWeight: '800', letterSpacing: 0.7 },
  latencyValue: { color: '#C4B5FD', fontSize: 15, fontWeight: '900', marginTop: 3 },
  meterTrack: { height: 7, borderRadius: 999, backgroundColor: '#232631', overflow: 'hidden', marginTop: 13 },
  meterFill: { height: '100%', borderRadius: 999, backgroundColor: '#10B981' },
  summaryStatusRow: { flexDirection: 'row', gap: 13, marginTop: 10, flexWrap: 'wrap' },
  healthyText: { color: '#6EE7B7', fontSize: 10, fontWeight: '700' },
  slowText: { color: '#FBBF24', fontSize: 10, fontWeight: '700' },
  downText: { color: '#F87171', fontSize: 10, fontWeight: '700' },
  quickActions: { flexDirection: 'row', gap: 7, marginBottom: 10, flexWrap: 'wrap' },
  quickAction: {
    minWidth: 74,
    flexGrow: 1,
    flexBasis: 74,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 10,
    paddingHorizontal: 9,
    backgroundColor: '#11131A',
    borderRadius: 11,
    borderWidth: 1,
    borderColor: '#242731',
  },
  quickActionText: { color: '#CBD5E1', fontSize: 10, fontWeight: '800' },
  filterRow: { flexDirection: 'row', gap: 7, marginBottom: 10 },
  filterChip: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#2A2D36',
    backgroundColor: '#111318',
  },
  filterChipActive: { borderColor: '#7C5CE7', backgroundColor: '#6D4FD322' },
  filterChipText: { color: '#94A3B8', fontSize: 10, fontWeight: '800' },
  filterChipTextActive: { color: '#C4B5FD' },
  serviceCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    padding: 11,
    marginBottom: 8,
    borderRadius: 14,
    borderWidth: 1,
    backgroundColor: '#111318',
  },
  serviceIcon: {
    width: 40,
    height: 40,
    borderRadius: 13,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  serviceBody: { flex: 1, minWidth: 0 },
  serviceTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  serviceTitle: { color: '#F1F5F9', fontSize: 13, fontWeight: '900', flex: 1 },
  serviceDescription: { color: '#94A3B8', fontSize: 10, lineHeight: 14, marginTop: 3 },
  serviceMetaRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 6 },
  serviceMeta: { color: '#596273', fontSize: 9, fontFamily: 'monospace', flex: 1 },
  serviceLatency: { fontSize: 9, fontWeight: '900' },
  statusPill: { flexDirection: 'row', alignItems: 'center', gap: 4, borderWidth: 1, borderRadius: 999, paddingHorizontal: 6, paddingVertical: 3 },
  statusDot: { width: 5, height: 5, borderRadius: 3 },
  statusText: { fontSize: 8, fontWeight: '900', letterSpacing: 0.45 },
  errorText: { color: '#F87171', fontSize: 9, lineHeight: 13, marginTop: 5 },
  retryButton: {
    width: 34,
    height: 34,
    borderRadius: 10,
    backgroundColor: '#1A1D24',
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyState: {
    alignItems: 'center',
    paddingVertical: 28,
    paddingHorizontal: 20,
    backgroundColor: '#111318',
    borderRadius: 14,
    borderWidth: 1,
    borderColor: '#232631',
  },
  emptyTitle: { color: '#E2E8F0', fontSize: 13, fontWeight: '900', marginTop: 8 },
  emptyText: { color: '#64748B', fontSize: 10, marginTop: 3, textAlign: 'center' },
  footerText: { color: '#475569', fontSize: 9, textAlign: 'center', marginTop: 10 },
  modalBackdrop: { flex: 1, justifyContent: 'flex-end', backgroundColor: '#000000B8' },
  modalCard: {
    maxHeight: '80%',
    backgroundColor: '#111318',
    borderTopLeftRadius: 22,
    borderTopRightRadius: 22,
    borderTopWidth: 1,
    borderColor: '#2C303A',
  },
  modalHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 14, borderBottomWidth: 1, borderBottomColor: '#242731' },
  modalTitle: { color: '#F8FAFC', fontSize: 15, fontWeight: '900' },
  modalStatus: { fontSize: 9, fontWeight: '900', marginTop: 2, letterSpacing: 0.55 },
  modalClose: { width: 34, height: 34, alignItems: 'center', justifyContent: 'center' },
  modalScroll: { maxHeight: 470 },
  modalContent: { padding: 14, paddingBottom: 18 },
  modalDescription: { color: '#CBD5E1', fontSize: 11, lineHeight: 17, marginBottom: 12 },
  endpointLabel: { color: '#64748B', fontSize: 8, fontWeight: '900', letterSpacing: 0.8 },
  endpointText: { color: '#A78BFA', fontSize: 10, fontFamily: 'monospace', marginTop: 3 },
  checkedText: { color: '#64748B', fontSize: 9, marginTop: 4, marginBottom: 12 },
  payloadSummary: { color: '#94A3B8', fontSize: 10, marginBottom: 8 },
  detailRow: { flexDirection: 'row', gap: 12, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: '#20232A' },
  detailLabel: { width: '34%', color: '#94A3B8', fontSize: 10, fontWeight: '700', textTransform: 'capitalize' },
  detailValue: { flex: 1, color: '#E2E8F0', fontSize: 10, lineHeight: 14, textAlign: 'right' },
  errorBox: { padding: 12, backgroundColor: '#EF444414', borderWidth: 1, borderColor: '#EF444444', borderRadius: 12 },
  errorBoxTitle: { color: '#FCA5A5', fontSize: 11, fontWeight: '900' },
  errorBoxText: { color: '#F87171', fontSize: 10, lineHeight: 15, marginTop: 4 },
  modalActions: { flexDirection: 'row', gap: 8, padding: 12, paddingBottom: 22, borderTopWidth: 1, borderTopColor: '#242731' },
  primaryButton: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, paddingVertical: 11, borderRadius: 11, backgroundColor: '#6D4FD3' },
  primaryButtonText: { color: '#FFFFFF', fontSize: 11, fontWeight: '900' },
  secondaryButton: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, paddingVertical: 11, borderRadius: 11, backgroundColor: '#181B22', borderWidth: 1, borderColor: '#2B2F39' },
  secondaryButtonText: { color: '#C4B5FD', fontSize: 11, fontWeight: '900' },
});
