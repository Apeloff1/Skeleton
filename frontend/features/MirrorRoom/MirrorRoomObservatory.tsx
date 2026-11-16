import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import Svg, { Circle, Line, Polyline } from 'react-native-svg';

import { Screen, AppHeader } from '../../components/UI';
import { api } from '../../utils/apiController';
import type {
  MirrorAttemptView,
  MirrorMetricView,
  MirrorRoomObservatoryPayload,
  MirrorTreeNode,
} from './types';

const ACCENT = '#A78BFA';
const ACCEPT = '#22C55E';
const REJECT = '#EF4444';
const GOLD = '#F5C451';
const CYAN = '#22D3EE';
const SURFACE = '#1D1D22';
const SURFACE_ALT = '#26262D';
const BORDER = '#3A3A44';
const TEXT = '#F8FAFC';
const MUTED = '#94A3B8';

function pct(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${(value * 100).toFixed(1)}%`;
}

function signed(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return '—';
  const prefix = value >= 0 ? '+' : '';
  return `${prefix}${(value * 100).toFixed(2)}%`;
}

function MetricBar({
  label,
  value,
  accent,
}: {
  label: string;
  value: number | null;
  accent: string;
}) {
  const width = Math.max(0, Math.min(100, (value ?? 0) * 100));
  return (
    <View style={styles.metricBlock}>
      <View style={styles.metricHead}>
        <Text style={styles.metricLabel}>{label}</Text>
        <Text style={[styles.metricValue, { color: accent }]}>
          {pct(value)}
        </Text>
      </View>
      <View style={styles.metricTrack}>
        <View
          style={[
            styles.metricFill,
            { width: `${width}%`, backgroundColor: accent },
          ]}
        />
      </View>
    </View>
  );
}

function QualityGraph({ attempts }: { attempts: MirrorAttemptView[] }) {
  const width = 650;
  const height = 180;
  const pad = 18;
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  const points = (
    key: 'effective_quality_score' | 'effective_detail_score',
  ) => attempts.map((attempt, index) => {
    const x = pad + (index / Math.max(1, attempts.length - 1)) * innerW;
    const y = pad + (1 - Math.max(0, Math.min(1, attempt[key]))) * innerH;
    return `${x},${y}`;
  }).join(' ');

  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false}>
      <Svg width={width} height={height}>
        {[0, 0.25, 0.5, 0.75, 1].map((value) => {
          const y = pad + (1 - value) * innerH;
          return (
            <Line
              key={value}
              x1={pad}
              x2={width - pad}
              y1={y}
              y2={y}
              stroke={BORDER}
              strokeWidth={1}
            />
          );
        })}
        {attempts.length > 1 ? (
          <>
            <Polyline
              points={points('effective_quality_score')}
              fill="none"
              stroke={GOLD}
              strokeWidth={3}
            />
            <Polyline
              points={points('effective_detail_score')}
              fill="none"
              stroke={CYAN}
              strokeWidth={3}
            />
          </>
        ) : null}
        {attempts.map((attempt, index) => {
          const x = pad + (index / Math.max(1, attempts.length - 1)) * innerW;
          const y = pad
            + (1 - Math.max(0, Math.min(1, attempt.effective_quality_score)))
            * innerH;
          return (
            <Circle
              key={attempt.attempt}
              cx={x}
              cy={y}
              r={attempt.accepted ? 3.4 : 2.2}
              fill={attempt.accepted ? ACCEPT : REJECT}
            />
          );
        })}
      </Svg>
    </ScrollView>
  );
}

function FileTreeNode({
  node,
  depth = 0,
}: {
  node: MirrorTreeNode;
  depth?: number;
}) {
  return (
    <View>
      <View style={[styles.treeRow, { paddingLeft: 10 + depth * 16 }]}>
        <Ionicons
          name={
            node.children?.length
              ? 'folder-open-outline'
              : 'document-text-outline'
          }
          size={14}
          color={node.kind === 'mirror' ? CYAN : ACCENT}
        />
        <View style={{ flex: 1 }}>
          <Text style={styles.treeName}>{node.name}</Text>
          {node.path ? <Text style={styles.treePath}>{node.path}</Text> : null}
        </View>
        <Text style={styles.treeKind}>{node.kind}</Text>
      </View>
      {node.children?.map((child) => (
        <FileTreeNode
          key={`${node.path || node.name}/${child.path || child.name}`}
          node={child}
          depth={depth + 1}
        />
      ))}
    </View>
  );
}

function DimensionRow({ metric }: { metric: MirrorMetricView }) {
  const base = Math.max(0, Math.min(100, metric.baseline_score * 100));
  const candidate = Math.max(0, Math.min(100, metric.candidate_score * 100));
  return (
    <View style={styles.dimensionRow}>
      <View style={styles.dimensionHead}>
        <Text style={styles.dimensionName}>
          {metric.metric_id.replace(/^content\./, '').replaceAll('_', ' ')}
        </Text>
        <Text
          style={[
            styles.dimensionDelta,
            { color: metric.delta >= 0 ? ACCEPT : REJECT },
          ]}
        >
          {signed(metric.delta)}
        </Text>
      </View>
      <View style={styles.dualTrack}>
        <View style={[styles.dualFillBase, { width: `${base}%` }]} />
        <View style={[styles.dualFillCandidate, { width: `${candidate}%` }]} />
      </View>
      <View style={styles.dimensionValues}>
        <Text style={styles.dimensionBase}>baseline {pct(metric.baseline_score)}</Text>
        <Text style={styles.dimensionCandidate}>
          challenger {pct(metric.candidate_score)}
        </Text>
      </View>
    </View>
  );
}

function Gate({ label, pass }: { label: string; pass: boolean }) {
  return (
    <View style={styles.gateRow}>
      <Ionicons
        name={pass ? 'checkmark-circle' : 'lock-closed-outline'}
        size={18}
        color={pass ? ACCEPT : MUTED}
      />
      <Text style={styles.gateLabel}>{label}</Text>
      <Text style={[styles.gateState, { color: pass ? ACCEPT : MUTED }]}>
        {pass ? 'PASS' : 'LOCKED'}
      </Text>
    </View>
  );
}

export default function MirrorRoomObservatory() {
  const router = useRouter();
  const [payload, setPayload] =
    useState<MirrorRoomObservatoryPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedAttempt, setSelectedAttempt] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      const next = await api.get<MirrorRoomObservatoryPayload>(
        '/api/mirror-room/observatory',
        {
          tag: 'mirror-room.observatory',
          cacheTtlMs: 0,
          timeoutMs: 5000,
        },
      );
      setPayload(next);
      setError(null);
    } catch (err: any) {
      setError(err?.message || 'Mirror Room observatory unavailable');
    }
  }, []);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      if (!active) return;
      await load();
    };
    refresh();
    const timer = setInterval(refresh, 1200);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [load]);

  const status = payload?.status;
  const attempts = status?.attempts ?? [];
  const selected = useMemo(() => {
    if (!attempts.length) return null;
    if (selectedAttempt == null) return attempts[attempts.length - 1];
    return attempts.find((item) => item.attempt === selectedAttempt)
      ?? attempts[attempts.length - 1];
  }, [attempts, selectedAttempt]);

  const progress = Math.max(0, Math.min(1, status?.progress ?? 0));
  const deliveryLocked = !status?.delivery_ready;
  const qualityLift = status?.quality_lift ?? null;
  const detailLift = status?.detail_lift ?? null;

  return (
    <Screen edges={['top']}>
      <AppHeader
        title="Mirror Room Observatory"
        subtitle="100-stage adversarial quality ratchet"
        onBack={() => router.back()}
        right={
          <TouchableOpacity onPress={load} style={styles.headerButton}>
            <Ionicons name="refresh" size={20} color={ACCENT} />
          </TouchableOpacity>
        }
      />
      <ScrollView contentContainerStyle={styles.page}>
        <View style={styles.hero}>
          <View style={styles.heroTop}>
            <View style={{ flex: 1 }}>
              <Text style={styles.eyebrow}>LIVE QUALITY FORGE</Text>
              <Text style={styles.heroTitle}>
                Attempt {status?.attempts_completed ?? 0} /{' '}
                {status?.attempts_required ?? 100}
              </Text>
              <Text style={styles.heroSubtitle}>
                {status?.current_baseline_id
                  ? `Current ratchet baseline: ${status.current_baseline_id}`
                  : 'Waiting for an adversarial campaign'}
              </Text>
            </View>
            <View
              style={[
                styles.lockBadge,
                { borderColor: deliveryLocked ? GOLD : ACCEPT },
              ]}
            >
              <Ionicons
                name={deliveryLocked ? 'lock-closed' : 'shield-checkmark'}
                size={16}
                color={deliveryLocked ? GOLD : ACCEPT}
              />
              <Text
                style={[
                  styles.lockText,
                  { color: deliveryLocked ? GOLD : ACCEPT },
                ]}
              >
                {deliveryLocked ? 'Delivery locked' : 'Delivery ready'}
              </Text>
            </View>
          </View>

          <View style={styles.progressTrack}>
            <View
              style={[styles.progressFill, { width: `${progress * 100}%` }]}
            />
          </View>
          <View style={styles.heroStats}>
            <Text style={styles.heroStat}>
              {Math.round(progress * 100)}% complete
            </Text>
            <Text style={styles.heroStat}>
              {status?.accepted_upgrades ?? 0} upgrades ratcheted
            </Text>
            <Text style={styles.heroStat}>
              {status?.retained_scenarios ?? 0} retained adversarial tests
            </Text>
          </View>
        </View>

        <View style={styles.liftGrid}>
          <View style={styles.liftCard}>
            <Text style={styles.liftLabel}>QUALITY LIFT</Text>
            <Text style={[styles.liftValue, { color: GOLD }]}>
              {signed(qualityLift)}
            </Text>
            <Text style={styles.liftSub}>
              {pct(status?.start_quality_score)} → {pct(status?.quality_score)}
            </Text>
          </View>
          <View style={styles.liftCard}>
            <Text style={styles.liftLabel}>DETAIL LIFT</Text>
            <Text style={[styles.liftValue, { color: CYAN }]}>
              {signed(detailLift)}
            </Text>
            <Text style={styles.liftSub}>
              {pct(status?.start_detail_score)} → {pct(status?.detail_score)}
            </Text>
          </View>
        </View>

        {error ? (
          <TouchableOpacity style={styles.errorCard} onPress={load}>
            <Ionicons name="warning-outline" size={18} color={GOLD} />
            <Text style={styles.errorText}>{error} · tap to retry</Text>
          </TouchableOpacity>
        ) : null}

        {!payload ? (
          <View style={styles.loading}>
            <ActivityIndicator color={ACCENT} />
            <Text style={styles.loadingText}>Connecting to Mirror Room…</Text>
          </View>
        ) : (
          <>
            <View style={styles.section}>
              <View style={styles.sectionHead}>
                <Text style={styles.sectionTitle}>Quality ascent</Text>
                <View style={styles.legendRow}>
                  <View style={[styles.legendDot, { backgroundColor: GOLD }]} />
                  <Text style={styles.legendText}>Quality</Text>
                  <View style={[styles.legendDot, { backgroundColor: CYAN }]} />
                  <Text style={styles.legendText}>Detail</Text>
                </View>
              </View>
              <MetricBar
                label="Current accepted quality"
                value={status?.quality_score ?? null}
                accent={GOLD}
              />
              <MetricBar
                label="Current accepted detail"
                value={status?.detail_score ?? null}
                accent={CYAN}
              />
              <QualityGraph attempts={attempts} />
            </View>

            <View style={styles.section}>
              <Text style={styles.sectionTitle}>100-attempt ratchet</Text>
              <Text style={styles.sectionCopy}>
                Green challengers became the next baseline. Red challengers
                were defeated and could not lower the current standard.
              </Text>
              <View style={styles.attemptGrid}>
                {Array.from(
                  { length: status?.attempts_required ?? 100 },
                  (_, index) => {
                    const n = index + 1;
                    const attempt = attempts[index];
                    const current =
                      n === (status?.attempts_completed ?? 0) + 1
                      && status?.status === 'running';
                    const backgroundColor = attempt
                      ? attempt.accepted ? ACCEPT : REJECT
                      : current ? GOLD : '#35353E';
                    return (
                      <TouchableOpacity
                        key={n}
                        onPress={() => attempt && setSelectedAttempt(n)}
                        disabled={!attempt}
                        style={[
                          styles.attemptCell,
                          { backgroundColor },
                          selected?.attempt === n
                            && styles.attemptCellSelected,
                        ]}
                      >
                        <Text style={styles.attemptCellText}>{n}</Text>
                      </TouchableOpacity>
                    );
                  },
                )}
              </View>
            </View>

            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Selected duel</Text>
              {selected ? (
                <>
                  <View style={styles.duelRow}>
                    <View style={styles.duelSide}>
                      <Text style={styles.duelLabel}>BASELINE</Text>
                      <Text style={styles.duelName} numberOfLines={2}>
                        {selected.baseline_before_id}
                      </Text>
                    </View>
                    <Ionicons
                      name="git-compare-outline"
                      size={24}
                      color={ACCENT}
                    />
                    <View style={styles.duelSide}>
                      <Text style={styles.duelLabel}>CHALLENGER</Text>
                      <Text style={styles.duelName} numberOfLines={2}>
                        {selected.candidate_id}
                      </Text>
                    </View>
                  </View>

                  <View style={styles.comparisonGrid}>
                    <View style={styles.compareCard}>
                      <Text style={styles.compareLabel}>Quality</Text>
                      <Text style={styles.compareBase}>
                        {pct(selected.baseline_quality_score)}
                      </Text>
                      <Ionicons name="arrow-forward" size={14} color={MUTED} />
                      <Text style={[styles.compareNext, { color: GOLD }]}>
                        {pct(selected.candidate_quality_score)}
                      </Text>
                    </View>
                    <View style={styles.compareCard}>
                      <Text style={styles.compareLabel}>Detail</Text>
                      <Text style={styles.compareBase}>
                        {pct(selected.baseline_detail_score)}
                      </Text>
                      <Ionicons name="arrow-forward" size={14} color={MUTED} />
                      <Text style={[styles.compareNext, { color: CYAN }]}>
                        {pct(selected.candidate_detail_score)}
                      </Text>
                    </View>
                  </View>

                  <View style={styles.duelMetrics}>
                    <View style={styles.miniCard}>
                      <Text style={styles.miniLabel}>Weighted gain</Text>
                      <Text
                        style={[
                          styles.miniValue,
                          { color: selected.accepted ? ACCEPT : REJECT },
                        ]}
                      >
                        {signed(selected.weighted_gain)}
                      </Text>
                    </View>
                    <View style={styles.miniCard}>
                      <Text style={styles.miniLabel}>Retention suite</Text>
                      <Text style={[styles.miniValue, { color: ACCENT }]}>
                        {selected.retained_scenarios}
                      </Text>
                    </View>
                  </View>

                  <View style={styles.thresholdRow}>
                    <Text style={styles.thresholdText}>
                      gain bar {signed(selected.required_weighted_gain)}
                    </Text>
                    <Text style={styles.thresholdText}>
                      strict metric bar{' '}
                      {signed(selected.required_strict_metric_gain)}
                    </Text>
                  </View>

                  <View
                    style={[
                      styles.verdict,
                      { borderColor: selected.accepted ? ACCEPT : REJECT },
                    ]}
                  >
                    <Ionicons
                      name={
                        selected.accepted
                          ? 'arrow-up-circle'
                          : 'close-circle'
                      }
                      size={18}
                      color={selected.accepted ? ACCEPT : REJECT}
                    />
                    <Text style={styles.verdictText}>
                      {selected.accepted
                        ? `Accepted — ${selected.baseline_after_id} became the new baseline`
                        : `Rejected — baseline remained ${selected.baseline_after_id}`}
                    </Text>
                  </View>

                  {!selected.accepted
                    && selected.rejection_reasons.length ? (
                    <Text style={styles.rejectionText}>
                      {selected.rejection_reasons.join(' · ')}
                    </Text>
                  ) : null}
                </>
              ) : (
                <Text style={styles.emptyText}>
                  The first challenger has not been evaluated yet.
                </Text>
              )}
            </View>

            {selected?.dimensions.length ? (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Quality anatomy</Text>
                <Text style={styles.sectionCopy}>
                  Each bar compares the selected attempt's baseline against its
                  challenger. The candidate only ratchets upward when the full
                  gate accepts it.
                </Text>
                {selected.dimensions.map((metric) => (
                  <DimensionRow key={metric.metric_id} metric={metric} />
                ))}
              </View>
            ) : null}

            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Delivery gates</Text>
              <Gate
                label="100 adversarial attempts complete"
                pass={
                  (status?.attempts_completed ?? 0)
                  === (status?.attempts_required ?? 100)
                }
              />
              <Gate
                label="Cumulative adversarial gauntlet"
                pass={Boolean(status?.gauntlet_passed)}
              />
              <Gate
                label="Sealed holdout"
                pass={Boolean(status?.holdout_passed)}
              />
              <Gate
                label="High-end delivery unlocked"
                pass={Boolean(status?.delivery_ready)}
              />
            </View>

            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Integrated file tree</Text>
              <Text style={styles.sectionCopy}>
                Learning, governed AI mirror, observability API, visual product
                surface, focused tests, and CI are one bounded system. The UI is
                read-only and cannot influence the ratchet.
              </Text>
              <FileTreeNode node={payload.file_tree} />
            </View>

            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Recent ratchet events</Text>
              {attempts.slice(-10).reverse().map((attempt) => (
                <TouchableOpacity
                  key={attempt.attempt}
                  onPress={() => setSelectedAttempt(attempt.attempt)}
                  style={styles.attemptRow}
                >
                  <View
                    style={[
                      styles.statusDot,
                      {
                        backgroundColor:
                          attempt.accepted ? ACCEPT : REJECT,
                      },
                    ]}
                  />
                  <Text style={styles.attemptName}>#{attempt.attempt}</Text>
                  <Text style={styles.attemptBaseline} numberOfLines={1}>
                    {attempt.baseline_after_id}
                  </Text>
                  <Text
                    style={[
                      styles.attemptGain,
                      { color: attempt.accepted ? ACCEPT : REJECT },
                    ]}
                  >
                    {signed(attempt.weighted_gain)}
                  </Text>
                </TouchableOpacity>
              ))}
              {!attempts.length ? (
                <Text style={styles.emptyText}>No attempts recorded yet.</Text>
              ) : null}
            </View>
          </>
        )}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  page: {
    padding: 16,
    paddingBottom: 80,
    gap: 12,
    backgroundColor: '#111116',
  },
  headerButton: {
    width: 42,
    height: 42,
    alignItems: 'center',
    justifyContent: 'center',
  },
  hero: {
    backgroundColor: SURFACE,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: '#4C3F66',
    padding: 18,
  },
  heroTop: {
    flexDirection: 'row',
    gap: 12,
    alignItems: 'flex-start',
  },
  eyebrow: {
    color: ACCENT,
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 1.5,
  },
  heroTitle: {
    color: TEXT,
    fontSize: 28,
    fontWeight: '900',
    marginTop: 4,
  },
  heroSubtitle: {
    color: MUTED,
    fontSize: 12,
    marginTop: 5,
  },
  lockBadge: {
    flexDirection: 'row',
    gap: 6,
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 7,
    borderRadius: 999,
    borderWidth: 1,
  },
  lockText: {
    fontSize: 10,
    fontWeight: '800',
  },
  progressTrack: {
    height: 10,
    backgroundColor: '#303039',
    borderRadius: 999,
    overflow: 'hidden',
    marginTop: 18,
  },
  progressFill: {
    height: '100%',
    backgroundColor: ACCENT,
    borderRadius: 999,
  },
  heroStats: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    marginTop: 9,
  },
  heroStat: {
    color: '#CBD5E1',
    fontSize: 11,
    fontWeight: '700',
  },
  liftGrid: {
    flexDirection: 'row',
    gap: 10,
  },
  liftCard: {
    flex: 1,
    backgroundColor: SURFACE,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: BORDER,
    padding: 14,
  },
  liftLabel: {
    color: MUTED,
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 1,
  },
  liftValue: {
    fontSize: 24,
    fontWeight: '900',
    marginTop: 5,
  },
  liftSub: {
    color: MUTED,
    fontSize: 10,
    marginTop: 3,
  },
  section: {
    backgroundColor: SURFACE,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: BORDER,
    padding: 16,
  },
  sectionHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  sectionTitle: {
    color: TEXT,
    fontSize: 17,
    fontWeight: '800',
    marginBottom: 10,
  },
  sectionCopy: {
    color: MUTED,
    fontSize: 12,
    lineHeight: 18,
    marginBottom: 14,
  },
  legendRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    marginBottom: 8,
  },
  legendDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
  },
  legendText: {
    color: MUTED,
    fontSize: 10,
    marginRight: 4,
  },
  metricBlock: {
    marginBottom: 12,
  },
  metricHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 5,
  },
  metricLabel: {
    color: '#CBD5E1',
    fontSize: 12,
    fontWeight: '700',
  },
  metricValue: {
    fontSize: 13,
    fontWeight: '900',
  },
  metricTrack: {
    height: 7,
    backgroundColor: '#303039',
    borderRadius: 99,
    overflow: 'hidden',
  },
  metricFill: {
    height: '100%',
    borderRadius: 99,
  },
  attemptGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 5,
  },
  attemptCell: {
    width: 28,
    height: 28,
    borderRadius: 7,
    alignItems: 'center',
    justifyContent: 'center',
  },
  attemptCellSelected: {
    borderWidth: 2,
    borderColor: '#FFFFFF',
  },
  attemptCellText: {
    color: TEXT,
    fontSize: 9,
    fontWeight: '800',
  },
  duelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  duelSide: {
    flex: 1,
    padding: 12,
    borderRadius: 12,
    backgroundColor: SURFACE_ALT,
  },
  duelLabel: {
    color: MUTED,
    fontSize: 9,
    fontWeight: '900',
    letterSpacing: 1,
  },
  duelName: {
    color: TEXT,
    fontSize: 12,
    fontWeight: '800',
    marginTop: 5,
  },
  comparisonGrid: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
  },
  compareCard: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: SURFACE_ALT,
    borderRadius: 10,
    padding: 10,
  },
  compareLabel: {
    color: MUTED,
    fontSize: 9,
    fontWeight: '800',
  },
  compareBase: {
    color: '#CBD5E1',
    fontSize: 12,
    fontWeight: '800',
  },
  compareNext: {
    fontSize: 12,
    fontWeight: '900',
  },
  duelMetrics: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 8,
  },
  miniCard: {
    flex: 1,
    backgroundColor: SURFACE_ALT,
    borderRadius: 10,
    padding: 10,
  },
  miniLabel: {
    color: MUTED,
    fontSize: 9,
    textTransform: 'uppercase',
    fontWeight: '800',
  },
  miniValue: {
    fontSize: 17,
    fontWeight: '900',
    marginTop: 3,
  },
  thresholdRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 10,
  },
  thresholdText: {
    color: MUTED,
    fontSize: 10,
    backgroundColor: '#202027',
    paddingHorizontal: 8,
    paddingVertical: 5,
    borderRadius: 7,
  },
  verdict: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
    borderRadius: 10,
    padding: 10,
    marginTop: 12,
  },
  verdictText: {
    flex: 1,
    color: TEXT,
    fontSize: 11,
    fontWeight: '700',
  },
  rejectionText: {
    color: '#FCA5A5',
    fontSize: 10,
    marginTop: 8,
    lineHeight: 15,
  },
  dimensionRow: {
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#292931',
  },
  dimensionHead: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
  },
  dimensionName: {
    flex: 1,
    color: '#E2E8F0',
    fontSize: 11,
    textTransform: 'capitalize',
    fontWeight: '700',
  },
  dimensionDelta: {
    fontSize: 10,
    fontWeight: '900',
  },
  dualTrack: {
    height: 9,
    borderRadius: 99,
    backgroundColor: '#303039',
    overflow: 'hidden',
    marginTop: 7,
  },
  dualFillBase: {
    position: 'absolute',
    height: '100%',
    backgroundColor: '#64748B',
    opacity: 0.65,
  },
  dualFillCandidate: {
    position: 'absolute',
    height: 4,
    top: 2.5,
    backgroundColor: ACCENT,
  },
  dimensionValues: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: 4,
  },
  dimensionBase: {
    color: MUTED,
    fontSize: 9,
  },
  dimensionCandidate: {
    color: ACCENT,
    fontSize: 9,
    fontWeight: '700',
  },
  gateRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#2C2C34',
  },
  gateLabel: {
    flex: 1,
    color: '#D4D4D8',
    fontSize: 12,
  },
  gateState: {
    fontSize: 10,
    fontWeight: '900',
    letterSpacing: 0.6,
  },
  treeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 7,
    borderBottomWidth: 1,
    borderBottomColor: '#292931',
  },
  treeName: {
    color: TEXT,
    fontSize: 11,
    fontWeight: '700',
  },
  treePath: {
    color: MUTED,
    fontSize: 9,
    marginTop: 1,
  },
  treeKind: {
    color: '#71717A',
    fontSize: 9,
    textTransform: 'uppercase',
  },
  attemptRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 9,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#292931',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  attemptName: {
    color: TEXT,
    width: 36,
    fontSize: 11,
    fontWeight: '800',
  },
  attemptBaseline: {
    color: MUTED,
    flex: 1,
    fontSize: 10,
  },
  attemptGain: {
    fontSize: 11,
    fontWeight: '900',
  },
  errorCard: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'center',
    backgroundColor: '#3B2A16',
    borderRadius: 12,
    padding: 12,
    borderWidth: 1,
    borderColor: '#6B4E20',
  },
  errorText: {
    color: '#FDE68A',
    flex: 1,
    fontSize: 11,
  },
  loading: {
    padding: 28,
    alignItems: 'center',
    gap: 10,
  },
  loadingText: {
    color: MUTED,
    fontSize: 12,
  },
  emptyText: {
    color: MUTED,
    fontSize: 12,
  },
});
