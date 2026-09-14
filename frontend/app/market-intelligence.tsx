import { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { AppHeader, Button, Chip, Screen, SectionHeader } from '../components/UI';
import theme from '../theme/tokens';
import {
  MarketSignal,
  MarketSourceKind,
  MarketWorkspaceSnapshot,
  addSignal,
  addSource,
  addWatchItem,
  emptyMarketWorkspace,
  loadMarketWorkspace,
  normalizeSymbol,
  removeSource,
  saveMarketWorkspace,
} from '../src/workspaces/marketStore';

const EMPTY: MarketWorkspaceSnapshot = emptyMarketWorkspace();
const SIGNALS: MarketSignal['signal'][] = ['bullish', 'neutral', 'bearish'];
const SOURCE_KINDS: MarketSourceKind[] = ['url', 'news', 'filing', 'research', 'note'];
const SIGNAL_META: Record<MarketSignal['signal'], { color: string; icon: string; label: string }> = {
  bullish: { color: theme.colors.success, icon: 'trending-up', label: 'Bullish' },
  neutral: { color: theme.colors.warning, icon: 'remove', label: 'Neutral' },
  bearish: { color: theme.colors.danger, icon: 'trending-down', label: 'Bearish' },
};
const SOURCE_META: Record<MarketSourceKind, { icon: string; label: string }> = {
  url: { icon: 'link', label: 'URL' },
  news: { icon: 'newspaper', label: 'News' },
  filing: { icon: 'document-text', label: 'Filing' },
  research: { icon: 'library', label: 'Research' },
  note: { icon: 'create', label: 'Note' },
};

export default function MarketIntelligenceScreen() {
  const router = useRouter();
  const [snapshot, setSnapshot] = useState<MarketWorkspaceSnapshot>(EMPTY);
  const [symbol, setSymbol] = useState('');
  const [thesis, setThesis] = useState('');
  const [sourceTitle, setSourceTitle] = useState('');
  const [sourceLocator, setSourceLocator] = useState('');
  const [sourceKind, setSourceKind] = useState<MarketSourceKind>('url');
  const [signalSymbol, setSignalSymbol] = useState('');
  const [evidence, setEvidence] = useState('');
  const [signal, setSignal] = useState<MarketSignal['signal']>('neutral');
  const [selectedSourceIds, setSelectedSourceIds] = useState<string[]>([]);

  useEffect(() => {
    loadMarketWorkspace().then(setSnapshot).catch(() => {});
  }, []);

  const persist = async (next: MarketWorkspaceSnapshot) => {
    setSnapshot(next);
    await saveMarketWorkspace(next);
  };

  const addToWatchlist = async () => {
    const normalized = normalizeSymbol(symbol);
    if (!normalized) return;
    const next = addWatchItem(snapshot, normalized, thesis);
    if (next === snapshot) return;
    await persist(next);
    setSymbol('');
    setThesis('');
  };

  const recordSource = async () => {
    if (!sourceTitle.trim() && !sourceLocator.trim()) return;
    const next = addSource(snapshot, sourceTitle, sourceLocator, sourceKind);
    if (next === snapshot) return;
    const created = next.sources[0];
    await persist(next);
    if (created) setSelectedSourceIds(ids => [created.id, ...ids].slice(0, 20));
    setSourceTitle('');
    setSourceLocator('');
    setSourceKind('url');
  };

  const recordSignal = async () => {
    const normalized = normalizeSymbol(signalSymbol);
    if (!normalized || !evidence.trim()) return;
    const next = addSignal(snapshot, normalized, signal, evidence, selectedSourceIds);
    await persist(next);
    setSignalSymbol('');
    setEvidence('');
    setSignal('neutral');
    setSelectedSourceIds([]);
  };

  const signalCounts = useMemo(() => snapshot.signals.reduce(
    (acc, item) => {
      acc[item.signal] += 1;
      return acc;
    },
    { bullish: 0, neutral: 0, bearish: 0 } as Record<MarketSignal['signal'], number>,
  ), [snapshot.signals]);

  const sourceById = useMemo(
    () => new Map(snapshot.sources.map(source => [source.id, source])),
    [snapshot.sources],
  );

  const toggleSource = (sourceId: string) => {
    setSelectedSourceIds(current => current.includes(sourceId)
      ? current.filter(id => id !== sourceId)
      : [sourceId, ...current].slice(0, 20));
  };

  return (
    <Screen edges={['top', 'left', 'right']}>
      <AppHeader
        title="Market Intelligence"
        subtitle="Evidence first · provenance explicit · prediction separated"
        onBack={() => router.back()}
      />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.migrationBanner}>
          <View style={styles.bannerIcon}>
            <Ionicons name="git-merge" size={20} color={theme.colors.warning} />
          </View>
          <View style={styles.bannerBody}>
            <Text style={styles.bannerTitle}>Legacy Jeeves market interface is being absorbed here</Text>
            <Text style={styles.bannerText}>
              Watchlists, source provenance and evidence journaling are local-first. Real-time prices, RSS ingestion and provider-backed ticks stay disabled until their connectors are wired and verified.
            </Text>
          </View>
        </View>

        <View style={styles.metrics}>
          <Metric label="Watchlist" value={snapshot.watchlist.length} color={theme.colors.info} />
          <Metric label="Sources" value={snapshot.sources.length} color={theme.colors.primaryHover} />
          <Metric label="Bullish" value={signalCounts.bullish} color={theme.colors.success} />
          <Metric label="Bearish" value={signalCounts.bearish} color={theme.colors.danger} />
        </View>

        <SectionHeader title="Watchlist" subtitle="Symbols and your thesis · no fabricated market data" />
        <View style={styles.formCard}>
          <TextInput
            value={symbol}
            onChangeText={value => setSymbol(normalizeSymbol(value))}
            autoCapitalize="characters"
            placeholder="Symbol e.g. AAPL"
            placeholderTextColor={theme.colors.textDisabled}
            style={styles.input}
          />
          <TextInput
            value={thesis}
            onChangeText={setThesis}
            placeholder="Why is this worth watching?"
            placeholderTextColor={theme.colors.textDisabled}
            style={styles.input}
          />
          <Button title="Add symbol" icon="add-circle" onPress={() => addToWatchlist().catch(() => {})} />
        </View>

        <View style={styles.watchlist}>
          {snapshot.watchlist.length === 0 ? (
            <Empty icon="eye-outline" title="Watchlist empty" text="Add a symbol to start rebuilding the old stock assistant around explicit evidence and verified data boundaries." />
          ) : snapshot.watchlist.map(item => (
            <View key={item.id} style={styles.watchRow}>
              <View style={styles.symbolBadge}><Text style={styles.symbolText}>{item.symbol}</Text></View>
              <View style={styles.rowBody}>
                <Text style={styles.rowTitle}>{item.thesis || 'No thesis recorded'}</Text>
                <Text style={styles.rowSub}>Added {new Date(item.createdAt).toLocaleDateString()}</Text>
              </View>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel={`Remove ${item.symbol}`}
                onPress={() => persist({ ...snapshot, watchlist: snapshot.watchlist.filter(row => row.id !== item.id) }).catch(() => {})}
                hitSlop={8}
                style={styles.deleteButton}
              >
                <Ionicons name="close" size={17} color={theme.colors.textDim} />
              </Pressable>
            </View>
          ))}
        </View>

        <SectionHeader title="Source Ledger" subtitle="Record provenance before automation starts consuming external feeds" />
        <View style={styles.formCard}>
          <View style={styles.signalPicker}>
            {SOURCE_KINDS.map(value => (
              <Chip
                key={value}
                label={SOURCE_META[value].label}
                selected={sourceKind === value}
                onPress={() => setSourceKind(value)}
              />
            ))}
          </View>
          <TextInput
            value={sourceTitle}
            onChangeText={setSourceTitle}
            placeholder="Source title or description"
            placeholderTextColor={theme.colors.textDisabled}
            style={styles.input}
          />
          <TextInput
            value={sourceLocator}
            onChangeText={setSourceLocator}
            placeholder="URL, filing identifier, publication, or source note"
            placeholderTextColor={theme.colors.textDisabled}
            style={styles.input}
          />
          <Button title="Record source" icon="link" onPress={() => recordSource().catch(() => {})} />
        </View>

        <View style={styles.sourceList}>
          {snapshot.sources.length === 0 ? (
            <Empty icon="library-outline" title="No sources recorded" text="Create provenance records manually now; automated RSS and market-provider ingestion can target the same ledger later." />
          ) : snapshot.sources.slice(0, 30).map(source => {
            const meta = SOURCE_META[source.kind];
            return (
              <View key={source.id} style={styles.sourceRow}>
                <View style={styles.sourceIcon}>
                  <Ionicons name={meta.icon as any} size={16} color={theme.colors.primaryHover} />
                </View>
                <View style={styles.rowBody}>
                  <View style={styles.sourceTitleRow}>
                    <Text style={styles.rowTitle}>{source.title}</Text>
                    <Text style={styles.sourceKind}>{meta.label}</Text>
                  </View>
                  {source.locator ? <Text style={styles.locator} numberOfLines={2}>{source.locator}</Text> : null}
                  <Text style={styles.rowSub}>Observed {new Date(source.observedAt).toLocaleString()}</Text>
                </View>
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={`Remove source ${source.title}`}
                  onPress={() => {
                    const next = removeSource(snapshot, source.id);
                    setSelectedSourceIds(ids => ids.filter(id => id !== source.id));
                    persist(next).catch(() => {});
                  }}
                  hitSlop={8}
                  style={styles.deleteButton}
                >
                  <Ionicons name="close" size={17} color={theme.colors.textDim} />
                </Pressable>
              </View>
            );
          })}
        </View>

        <SectionHeader title="Signal Journal" subtitle="Analytical claims carry evidence and can link to provenance records" />
        <View style={styles.formCard}>
          <TextInput
            value={signalSymbol}
            onChangeText={value => setSignalSymbol(normalizeSymbol(value))}
            autoCapitalize="characters"
            placeholder="Symbol"
            placeholderTextColor={theme.colors.textDisabled}
            style={styles.input}
          />
          <View style={styles.signalPicker}>
            {SIGNALS.map(value => (
              <Chip
                key={value}
                label={SIGNAL_META[value].label}
                selected={signal === value}
                color={signal === value ? SIGNAL_META[value].color : undefined}
                onPress={() => setSignal(value)}
              />
            ))}
          </View>
          <TextInput
            value={evidence}
            onChangeText={setEvidence}
            multiline
            placeholder="Evidence: factual observation or measured condition"
            placeholderTextColor={theme.colors.textDisabled}
            style={[styles.input, styles.evidenceInput]}
          />
          {snapshot.sources.length > 0 ? (
            <View>
              <Text style={styles.linkLabel}>LINK SOURCES · {selectedSourceIds.length} SELECTED</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.sourceChips}>
                {snapshot.sources.slice(0, 30).map(source => (
                  <Chip
                    key={source.id}
                    label={source.title}
                    selected={selectedSourceIds.includes(source.id)}
                    onPress={() => toggleSource(source.id)}
                  />
                ))}
              </ScrollView>
            </View>
          ) : null}
          <Button title="Record evidence-backed signal" icon="document-text" onPress={() => recordSignal().catch(() => {})} />
        </View>

        <View style={styles.signalList}>
          {snapshot.signals.length === 0 ? (
            <Empty icon="analytics-outline" title="No signals recorded" text="The rebuilt interface keeps facts, analytical interpretation and future prediction separate instead of presenting guesses as ticks." />
          ) : snapshot.signals.slice(0, 50).map(item => {
            const meta = SIGNAL_META[item.signal];
            const linkedSources = item.sourceIds.map(id => sourceById.get(id)).filter(Boolean);
            return (
              <View key={item.id} style={styles.signalRow}>
                <View style={[styles.signalIcon, { backgroundColor: `${meta.color}1F` }]}>
                  <Ionicons name={meta.icon as any} size={17} color={meta.color} />
                </View>
                <View style={styles.rowBody}>
                  <View style={styles.signalTitleRow}>
                    <Text style={styles.signalSymbol}>{item.symbol}</Text>
                    <Text style={[styles.signalLabel, { color: meta.color }]}>{meta.label}</Text>
                  </View>
                  <Text style={styles.evidenceText}>{item.evidence}</Text>
                  {linkedSources.length > 0 ? (
                    <Text style={styles.provenanceText}>
                      {linkedSources.length} linked source{linkedSources.length === 1 ? '' : 's'} · {linkedSources.slice(0, 2).map(source => source?.title).join(' · ')}
                    </Text>
                  ) : (
                    <Text style={styles.unlinkedText}>No source record linked</Text>
                  )}
                  <Text style={styles.rowSub}>{new Date(item.createdAt).toLocaleString()}</Text>
                </View>
              </View>
            );
          })}
        </View>
      </ScrollView>
    </Screen>
  );
}

function Metric({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <View style={styles.metric}>
      <Text style={[styles.metricValue, { color }]}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

function Empty({ icon, title, text }: { icon: string; title: string; text: string }) {
  return (
    <View style={styles.empty}>
      <Ionicons name={icon as any} size={26} color={theme.colors.textDim} />
      <Text style={styles.emptyTitle}>{title}</Text>
      <Text style={styles.emptyText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: { padding: theme.spacing.base, paddingBottom: 80, gap: theme.spacing.md },
  migrationBanner: { flexDirection: 'row', gap: theme.spacing.md, padding: theme.spacing.base, borderRadius: theme.radii.xl, borderWidth: 1, borderColor: `${theme.colors.warning}55`, backgroundColor: `${theme.colors.warning}10` },
  bannerIcon: { width: 40, height: 40, borderRadius: theme.radii.md, alignItems: 'center', justifyContent: 'center', backgroundColor: `${theme.colors.warning}18` },
  bannerBody: { flex: 1 },
  bannerTitle: { ...theme.typography.h4, color: theme.colors.text },
  bannerText: { ...theme.typography.body, color: theme.colors.textMuted, marginTop: 4 },
  metrics: { flexDirection: 'row', gap: theme.spacing.sm },
  metric: { flex: 1, minHeight: 68, alignItems: 'center', justifyContent: 'center', borderRadius: theme.radii.lg, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface },
  metricValue: { ...theme.typography.h3 },
  metricLabel: { ...theme.typography.caption, color: theme.colors.textMuted, marginTop: 2 },
  formCard: { gap: theme.spacing.md, padding: theme.spacing.base, borderRadius: theme.radii.xl, borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface },
  input: { minHeight: 46, borderRadius: theme.radii.md, borderWidth: 1, borderColor: theme.colors.borderStrong, backgroundColor: theme.colors.bgSubtle, color: theme.colors.text, paddingHorizontal: theme.spacing.md, ...theme.typography.body },
  evidenceInput: { minHeight: 96, paddingTop: theme.spacing.md, textAlignVertical: 'top' },
  signalPicker: { flexDirection: 'row', flexWrap: 'wrap', gap: theme.spacing.sm },
  watchlist: { borderRadius: theme.radii.xl, overflow: 'hidden', borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface },
  watchRow: { minHeight: 66, flexDirection: 'row', alignItems: 'center', padding: theme.spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: theme.colors.border },
  symbolBadge: { minWidth: 64, height: 36, borderRadius: theme.radii.md, paddingHorizontal: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: theme.colors.primarySoft },
  symbolText: { ...theme.typography.monoSm, color: theme.colors.primaryHover, fontWeight: '700' },
  rowBody: { flex: 1, paddingHorizontal: 10 },
  rowTitle: { ...theme.typography.body, color: theme.colors.text },
  rowSub: { ...theme.typography.caption, color: theme.colors.textMuted, marginTop: 3 },
  deleteButton: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  sourceList: { borderRadius: theme.radii.xl, overflow: 'hidden', borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface },
  sourceRow: { minHeight: 72, flexDirection: 'row', alignItems: 'flex-start', padding: theme.spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: theme.colors.border },
  sourceIcon: { width: 34, height: 34, borderRadius: theme.radii.md, alignItems: 'center', justifyContent: 'center', backgroundColor: theme.colors.primarySoft },
  sourceTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sourceKind: { ...theme.typography.micro, color: theme.colors.primaryHover, textTransform: 'uppercase' },
  locator: { ...theme.typography.caption, color: theme.colors.textMuted, marginTop: 3 },
  linkLabel: { ...theme.typography.micro, color: theme.colors.textDim, marginBottom: 7 },
  sourceChips: { gap: theme.spacing.sm, paddingRight: theme.spacing.md },
  signalList: { borderRadius: theme.radii.xl, overflow: 'hidden', borderWidth: 1, borderColor: theme.colors.border, backgroundColor: theme.colors.surface },
  signalRow: { flexDirection: 'row', alignItems: 'flex-start', padding: theme.spacing.md, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: theme.colors.border },
  signalIcon: { width: 36, height: 36, borderRadius: theme.radii.md, alignItems: 'center', justifyContent: 'center' },
  signalTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  signalSymbol: { ...theme.typography.mono, color: theme.colors.text, fontWeight: '700' },
  signalLabel: { ...theme.typography.caption, textTransform: 'uppercase' },
  evidenceText: { ...theme.typography.body, color: theme.colors.textMuted, marginTop: 5 },
  provenanceText: { ...theme.typography.caption, color: theme.colors.primaryHover, marginTop: 6 },
  unlinkedText: { ...theme.typography.caption, color: theme.colors.textDim, marginTop: 6 },
  empty: { padding: theme.spacing.xl, alignItems: 'center' },
  emptyTitle: { ...theme.typography.h4, color: theme.colors.text, marginTop: 8 },
  emptyText: { ...theme.typography.body, color: theme.colors.textMuted, textAlign: 'center', marginTop: 5 },
});
