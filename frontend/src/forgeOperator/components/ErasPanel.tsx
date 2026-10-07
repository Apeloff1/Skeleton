/**
 * Eras screen — EraViewer grid plus operator catalog / detail readout.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import EraViewer from '../../skeletonForge/components/EraViewer';
import { Card, Chip, SectionTitle, StatusPill } from '../../skeletonForge/components/primitives';
import { C } from '../../skeletonForge/components/theme';
import {
  filterEras,
  humanizePhilosophy,
  listPhilosophies,
  summarizeEra,
  summarizeErasCatalog,
} from '../eraSummary';
import type { EraRow } from '../types';

export interface ErasPanelProps {
  eras: EraRow[];
  loading: boolean;
  error: string | null;
  onReload: () => void;
  resultEra?: string | null;
  pinnedEra?: string | null;
  onUseInForge?: (era: string) => void;
  testID?: string;
}

function resolveEraId(id: string | null | undefined): string | null {
  if (!id) return null;
  return String(id).split('~')[0].split('@')[0] || null;
}

function findEra(eras: EraRow[], id: string | null | undefined): EraRow | null {
  const key = resolveEraId(id);
  if (!key) return null;
  return eras.find((e) => e.id === key) ?? null;
}

export default function ErasPanel({
  eras,
  loading,
  error,
  onReload,
  resultEra,
  pinnedEra,
  onUseInForge,
  testID,
}: ErasPanelProps) {
  const [selected, setSelected] = React.useState<string | null>(null);
  const [philosophy, setPhilosophy] = React.useState<string | null>(null);

  const catalog = React.useMemo(() => summarizeErasCatalog(eras), [eras]);
  const philosophies = React.useMemo(() => listPhilosophies(eras), [eras]);
  const filtered = React.useMemo(
    () => filterEras(eras, { philosophy }),
    [eras, philosophy],
  );

  const focusId = selected || pinnedEra || resolveEraId(resultEra);
  const focusRow = React.useMemo(() => {
    if (selected) return findEra(eras, selected);
    if (pinnedEra) return findEra(eras, pinnedEra);
    return findEra(eras, resultEra);
  }, [eras, selected, pinnedEra, resultEra]);
  const detail = React.useMemo(() => summarizeEra(focusRow), [focusRow]);

  const togglePhilosophy = React.useCallback((p: string) => {
    setPhilosophy((prev) => (prev === p ? null : p));
  }, []);

  return (
    <View testID={testID ?? 'operator-eras'}>
      <SectionTitle hint={`${catalog.count} eras · GET /api/skeleton/eras`}>🕰 Eras catalog</SectionTitle>
      <Card testID="operator-eras-filter">
        <Text style={st.catalogLine}>
          {catalog.count} era{catalog.count === 1 ? '' : 's'}
          {catalog.fastestId ? ` · fastest ${catalog.fastestId}` : ''}
          {catalog.glassiestId ? ` · glassiest ${catalog.glassiestId}` : ''}
        </Text>
        {philosophies.length ? (
          <View style={st.chips} accessibilityRole="radiogroup" accessibilityLabel="Filter by philosophy">
            {philosophies.map((p) => (
              <Chip
                key={p}
                label={humanizePhilosophy(p) || p}
                selected={philosophy === p}
                color={C.green}
                onPress={() => togglePhilosophy(p)}
                testID={`operator-eras-phil-${p}`}
                a11yLabel={`${humanizePhilosophy(p) || p}${philosophy === p ? ', selected' : ''}`}
              />
            ))}
          </View>
        ) : null}
        {philosophy ? (
          <Text style={st.filterHint}>
            Showing {filtered.length} / {catalog.count} · {humanizePhilosophy(philosophy)}
          </Text>
        ) : null}
      </Card>

      {detail ? (
        <Card testID="operator-eras-detail" label={detail.id}>
          <View style={st.pills}>
            {selected && focusId === selected ? <StatusPill tone="ok" label="selected" /> : null}
            {pinnedEra && resolveEraId(pinnedEra) === detail.id ? (
              <StatusPill tone="warn" label="pinned" />
            ) : null}
            {resolveEraId(resultEra) === detail.id ? <StatusPill tone="ok" label="last result" /> : null}
          </View>
          <Fact k="Era" v={detail.id} />
          <Fact k="Philosophy" v={detail.philosophyLabel} />
          <Fact k="Stats" v={detail.statsLabel} />
          <Fact k="TTK" v={detail.ttkLabel} />
        </Card>
      ) : null}

      <EraViewer
        eras={filtered}
        loading={loading}
        error={error}
        onReload={onReload}
        resultEra={resultEra}
        pinnedEra={pinnedEra}
        selected={selected}
        onSelect={setSelected}
        onUseInForge={onUseInForge}
      />
    </View>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <View style={st.fact}>
      <Text style={st.k}>{k}</Text>
      <Text style={st.v}>{v}</Text>
    </View>
  );
}

const st = StyleSheet.create({
  catalogLine: { color: C.mute, fontSize: 13, marginBottom: 8 },
  chips: { flexDirection: 'row', flexWrap: 'wrap' },
  filterHint: { color: C.dim, fontSize: 12, marginTop: 8 },
  pills: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 8 },
  fact: { marginBottom: 8 },
  k: { color: C.dim, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  v: { color: C.text, fontSize: 14 },
});
