/**
 * YourChoicesCard — pre-Build summary card for Galaxy Studio.
 * Surfaces every key configuration value so the user can review before clicking Build.
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { ProductionState } from './productionSections';

interface Props {
  title: string;
  genre?: string | null;
  description: string;
  eraLabel?: string;
  eraYear?: number | string;
  ageTarget?: string;
  complexity: number;
  extraParams: Record<string, number>;
  production: ProductionState;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function fmtSlider(v?: number) {
  if (v === undefined || v === null) return '—';
  return `${v}`;
}

function tierFor(v: number, max = 100) {
  if (v <= 0) return 'Off';
  const tiers = ['Off', 'Minimal', 'Low', 'Medium', 'High', 'Very High', 'Ultra', 'Max'];
  const idx = Math.min(tiers.length - 1, Math.max(1, Math.ceil((v / max) * (tiers.length - 1))));
  return tiers[idx];
}

export const YourChoicesCard: React.FC<Props> = ({
  title, genre, description, eraLabel, eraYear, ageTarget,
  complexity, extraParams, production,
}) => {
  const productionSlidersCount = Object.keys(production.sliders).length;
  const topProduction = Object.entries(production.sliders).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const extraNonZero = Object.entries(extraParams).filter(([k, v]) => k !== 'production' && typeof v === 'number' && v > 0).length;
  return (
    <View style={s.card}>
      <View style={s.header}>
        <Ionicons name="checkbox" size={18} color="#10B981" />
        <Text style={s.headerTitle}>Your Choices</Text>
        <Text style={s.headerSub}>review before Build</Text>
      </View>
      <Row label="Title" value={title || '—'} />
      <Row label="Genre" value={genre || '—'} />
      <Row label="Era" value={eraLabel ? `${eraLabel} (${eraYear})` : '—'} />
      <Row label="Age target" value={ageTarget || '—'} />
      <Row label="Complexity" value={`${complexity}/10`} />
      <Row label="Description" value={description ? `${description.slice(0, 80)}${description.length > 80 ? '…' : ''}` : '—'} />
      <Divider />
      <Text style={s.sectionTitle}>Art &amp; Storytelling</Text>
      <Row label="Art direction" value={production.artDirection} />
      <Row label="Tone" value={production.gameTone} />
      <Row label="Narrative" value={production.narrativeStructure} />
      <Row label="Perspective" value={production.perspective} />
      <Divider />
      <Text style={s.sectionTitle}>Production &amp; Targets</Text>
      <Row label="Monetization" value={production.monetization} />
      <Row label="Save system" value={production.saveSystem} />
      <Row label="Network mode" value={production.networkMode} />
      <Row label="Platforms" value={production.platforms.length ? production.platforms.join(', ') : '—'} />
      <Row label="Languages" value={production.languages.length ? production.languages.join(', ') : '—'} />
      <Divider />
      <Text style={s.sectionTitle}>Sliders engaged</Text>
      <View style={s.statsRow}>
        <Stat label="Production" value={`${productionSlidersCount}`} accent="#2563EB" />
        <Stat label="Detailed (1-10)" value={`${extraNonZero}`} accent="#A855F7" />
        <Stat label="Total set" value={`${productionSlidersCount + extraNonZero}`} accent="#FBBF24" />
      </View>
      {topProduction.length > 0 && (
        <>
          <Divider />
          <Text style={s.sectionTitle}>Top intensity sliders</Text>
          {topProduction.map(([k, v]) => (
            <View key={k} style={s.miniRow}>
              <Text style={s.miniKey}>{k.replace(/_/g, ' ')}</Text>
              <View style={s.miniTrack}>
                <View style={[s.miniFill, { width: `${v}%` }]} />
              </View>
              <Text style={s.miniVal}>{v} · {tierFor(v)}</Text>
            </View>
          ))}
        </>
      )}
    </View>
  );
};

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={s.row}>
      <Text style={s.rowLabel}>{label}</Text>
      <Text style={s.rowValue} numberOfLines={2}>{value}</Text>
    </View>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <View style={s.stat}>
      <Text style={[s.statValue, { color: accent }]}>{value}</Text>
      <Text style={s.statLabel}>{label}</Text>
    </View>
  );
}

function Divider() {
  return <View style={s.divider} />;
}

const s = StyleSheet.create({
  card: { backgroundColor: '#1E293B', borderRadius: 12, padding: 14, marginTop: 16, marginBottom: 14, borderWidth: 1, borderColor: '#10B981' + '55' },
  header: { flexDirection: 'row', alignItems: 'center', marginBottom: 12, gap: 8 },
  headerTitle: { color: '#10B981', fontSize: 14, fontWeight: '800' },
  headerSub: { color: '#64748B', fontSize: 10, marginLeft: 'auto', fontStyle: 'italic' },
  sectionTitle: { color: '#CBD5E1', fontSize: 12, fontWeight: '700', letterSpacing: 0.2, marginBottom: 10, marginTop: 4 },
  row: { flexDirection: 'row', paddingVertical: 4 },
  rowLabel: { color: '#94A3B8', fontSize: 11, fontWeight: '600', width: 110 },
  rowValue: { color: '#F8FAFC', fontSize: 12, fontWeight: '700', flex: 1 },
  divider: { height: 1, backgroundColor: '#334155', marginVertical: 10 },
  statsRow: { flexDirection: 'row', gap: 8 },
  stat: { flex: 1, alignItems: 'center', backgroundColor: '#0F172A', borderRadius: 8, padding: 10, borderWidth: 1, borderColor: '#334155' },
  statValue: { fontSize: 18, fontWeight: '800' },
  statLabel: { color: '#94A3B8', fontSize: 9, marginTop: 2, textTransform: 'uppercase' },
  miniRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 },
  miniKey: { color: '#CBD5E1', fontSize: 10, width: 110, textTransform: 'capitalize' },
  miniTrack: { flex: 1, height: 6, backgroundColor: '#0F172A', borderRadius: 3, overflow: 'hidden' },
  miniFill: { height: '100%', backgroundColor: '#2563EB', borderRadius: 3 },
  miniVal: { color: '#94A3B8', fontSize: 10, width: 90, textAlign: 'right' },
});
