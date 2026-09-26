/**
 * Era viewer over GET /api/skeleton/eras: searchable, sortable comparison
 * grid (DPS, move speed, trash TTK relative to the strongest era) with a
 * detail card and "use in forge". The last run's era is badged.
 */
import React from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View, type LayoutChangeEvent } from 'react-native';
import { ERA_SORTS, baseEra, describeEra, eraViews, filterEras, sortEras, type EraSortKey, type EraView } from '../eras';
import type { EraRow } from '../types';
import { Banner, Button, Card, Chip, Meter, SectionTitle } from './primitives';
import { C, TOUCH } from './theme';

export interface EraViewerProps {
  eras: EraRow[];
  loading?: boolean;
  error?: string | null;
  onReload?: () => void;
  /** Era produced by the last forge run (blend ids resolve to their base). */
  resultEra?: string | null;
  /** Era currently pinned in the questionnaire. */
  pinnedEra?: string | null;
  selected?: string | null;
  onSelect?: (id: string | null) => void;
  onUseInForge?: (id: string) => void;
  initialWidth?: number;
  testID?: string;
}

export function columnsFor(width: number): number {
  return width >= 900 ? 3 : width >= 520 ? 2 : 1;
}

export default function EraViewer({ eras, loading, error, onReload, resultEra, pinnedEra, selected, onSelect, onUseInForge, initialWidth = 360, testID }: EraViewerProps) {
  const [query, setQuery] = React.useState('');
  const [sort, setSort] = React.useState<EraSortKey>('name');
  const [width, setWidth] = React.useState(initialWidth);
  const onLayout = (e: LayoutChangeEvent) => {
    const w = Math.round(e.nativeEvent.layout.width);
    if (w > 0 && Math.abs(w - width) > 4) setWidth(w);
  };
  const all = React.useMemo(() => eraViews(eras), [eras]);
  const shown = React.useMemo(() => sortEras(filterEras(all, query), sort), [all, query, sort]);
  const result = baseEra(resultEra);
  const cols = columnsFor(width);
  const detail = selected ? all.find((v) => v.id === selected) ?? null : null;

  return (
    <View testID={testID} onLayout={onLayout}>
      <SectionTitle hint={`${all.length} eras · GET /api/skeleton/eras`}>🕰 Era viewer</SectionTitle>
      {error ? (
        <Banner tone="bad" testID="era-error">Could not load eras: {error}</Banner>
      ) : null}
      {error && onReload ? <Button label="Retry" tone="secondary" compact onPress={onReload} testID="era-retry" /> : null}
      {detail ? <EraDetail v={detail} isResult={detail.id === result} isPinned={detail.id === pinnedEra} onClose={onSelect ? () => onSelect(null) : undefined} onUse={onUseInForge} /> : null}
      <TextInput
        testID="era-search"
        value={query}
        onChangeText={setQuery}
        placeholder="Search eras or philosophies"
        placeholderTextColor={C.dim}
        accessibilityLabel="Search eras"
        style={st.search}
      />
      <View style={st.sorts} accessibilityRole="radiogroup" accessibilityLabel="Sort eras by">
        {ERA_SORTS.map((o) => (
          <Chip key={o.id} label={o.label} selected={sort === o.id} onPress={() => setSort(o.id)} testID={`era-sort-${o.id}`} />
        ))}
      </View>
      {loading && !all.length ? <ActivityIndicator color={C.accent} accessibilityLabel="Loading eras" style={{ marginVertical: 20 }} /> : null}
      {!loading && !error && !shown.length ? <Text style={st.empty}>{all.length ? `No eras match “${query}”.` : 'No eras available.'}</Text> : null}
      <View style={st.grid} accessibilityRole="list" accessibilityLabel={`${shown.length} eras`}>
        {shown.map((v) => (
          <EraCard
            key={v.id}
            v={v}
            cols={cols}
            isResult={v.id === result}
            isPinned={v.id === pinnedEra}
            selected={v.id === selected}
            onPress={onSelect ? () => onSelect(v.id === selected ? null : v.id) : undefined}
          />
        ))}
      </View>
    </View>
  );
}

function EraCard({ v, cols, isResult, isPinned, selected, onPress }: { v: EraView; cols: number; isResult: boolean; isPinned: boolean; selected: boolean; onPress?: () => void }) {
  const badges = [isResult ? 'last forge result' : '', isPinned ? 'pinned' : ''].filter(Boolean);
  return (
    <Pressable
      testID={`era-card-${v.id}`}
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`${describeEra(v)}${badges.length ? ` ${badges.join(', ')}.` : ''}${selected ? ' Selected.' : ''}`}
      accessibilityState={{ selected }}
      style={({ pressed }) => [
        st.card,
        { width: cols === 1 ? '100%' : cols === 2 ? '48.5%' : '32%' },
        isResult && { borderColor: C.green },
        selected && { borderColor: C.accent, backgroundColor: C.accent + '14' },
        pressed && { opacity: 0.8 },
      ]}
    >
      <View style={st.cardHead}>
        <Text style={st.name} numberOfLines={1}>{v.label}</Text>
        {isResult ? <Text style={[st.badge, { color: C.green, borderColor: C.green }]}>RESULT</Text> : null}
        {isPinned ? <Text style={[st.badge, { color: C.amber, borderColor: C.amber }]}>PINNED</Text> : null}
      </View>
      <Text style={st.phil} numberOfLines={1}>{v.philosophy || '—'}</Text>
      <Stat k="DPS" v={String(v.dps)} ratio={v.dpsRatio} color={C.red} />
      <Stat k="Speed" v={String(v.speed)} ratio={v.speedRatio} color={C.blue} />
      <Stat k="Trash TTK" v={v.ttkTrash === null ? '—' : `${v.ttkTrash}s`} ratio={v.ttkRatio} color={C.amber} />
    </Pressable>
  );
}

function Stat({ k, v, ratio, color }: { k: string; v: string; ratio: number; color: string }) {
  return (
    <View style={st.stat} importantForAccessibility="no-hide-descendants" accessibilityElementsHidden>
      <View style={st.statHead}>
        <Text style={st.statK}>{k}</Text>
        <Text style={st.statV}>{v}</Text>
      </View>
      <Meter ratio={ratio} color={color} label={`${k} ${v}`} height={4} />
    </View>
  );
}

function EraDetail({ v, isResult, isPinned, onClose, onUse }: { v: EraView; isResult: boolean; isPinned: boolean; onClose?: () => void; onUse?: (id: string) => void }) {
  return (
    <Card testID="era-detail" label={`Era details: ${v.label}`}>
      <View style={st.cardHead}>
        <Text style={st.detailName} accessibilityRole="header">{v.label}</Text>
        {isResult ? <Text style={[st.badge, { color: C.green, borderColor: C.green }]}>RESULT</Text> : null}
      </View>
      <Text style={st.phil}>{v.philosophy || 'No stated philosophy'} · <Text style={st.mono}>{v.id}</Text></Text>
      <View style={st.ttkRow}>
        <Ttk k="Trash" v={v.ttkTrash} />
        <Ttk k="Elite" v={v.ttkElite} />
        <Ttk k="Boss" v={v.ttkBoss} />
      </View>
      <View style={st.detailBtns}>
        {onUse ? <Button label={isPinned ? 'Pinned for next forge' : 'Use in forge'} tone="primary" compact disabled={isPinned} onPress={() => onUse(v.id)} testID="era-use" /> : null}
        {onClose ? <Button label="Close" tone="ghost" compact onPress={onClose} testID="era-close" /> : null}
      </View>
    </Card>
  );
}

function Ttk({ k, v }: { k: string; v: number | null }) {
  return (
    <View style={st.ttk} accessible accessibilityLabel={`${k} time to kill: ${v === null ? 'unknown' : `${v} seconds`}`}>
      <Text style={st.statK}>{k} TTK</Text>
      <Text style={st.ttkV}>{v === null ? '—' : `${v}s`}</Text>
    </View>
  );
}

const st = StyleSheet.create({
  search: { minHeight: TOUCH, color: C.text, backgroundColor: C.card, borderWidth: 1, borderColor: C.borderStrong, borderRadius: 10, paddingHorizontal: 12, fontSize: 14, marginBottom: 8 },
  sorts: { flexDirection: 'row', flexWrap: 'wrap', marginBottom: 4 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between' },
  card: { backgroundColor: C.card, borderWidth: 1, borderColor: C.border, borderRadius: 12, padding: 12, marginBottom: 10, minHeight: TOUCH },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  name: { color: C.textStrong, fontSize: 15, fontWeight: '800', flexShrink: 1 },
  badge: { borderWidth: 1, borderRadius: 4, fontSize: 9, fontWeight: '900', paddingHorizontal: 4, letterSpacing: 0.6 },
  phil: { color: C.mute, fontSize: 12, marginTop: 2, marginBottom: 8 },
  stat: { marginTop: 4 },
  statHead: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 3 },
  statK: { color: C.dim, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.5 },
  statV: { color: C.text, fontSize: 11, fontWeight: '700' },
  empty: { color: C.mute, fontSize: 13, marginVertical: 12 },
  detailName: { color: C.textStrong, fontSize: 20, fontWeight: '900' },
  mono: { fontFamily: 'monospace', fontSize: 11 },
  ttkRow: { flexDirection: 'row', gap: 8, marginTop: 4 },
  ttk: { flex: 1, backgroundColor: C.cardAlt, borderRadius: 8, borderWidth: 1, borderColor: C.border, padding: 8 },
  ttkV: { color: C.textStrong, fontSize: 16, fontWeight: '800', marginTop: 2 },
  detailBtns: { flexDirection: 'row', gap: 8, marginTop: 12, flexWrap: 'wrap' },
});
