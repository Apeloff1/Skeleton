import React, { useMemo } from 'react';
import { SafeAreaView, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useRouter } from 'expo-router';

import {
  PRODUCT_CAPABILITIES,
  ProductPillar,
  capabilitiesFor,
} from '../src/product/productCatalog';

const PILLARS: readonly { id: ProductPillar; title: string; subtitle: string }[] = [
  { id: 'create', title: 'Create', subtitle: 'Design, generate and ship worlds and playable projects.' },
  { id: 'play', title: 'Play', subtitle: 'Launch builds, simulations and generated game experiences.' },
  { id: 'learn', title: 'Learn', subtitle: 'Use Jeeves and Academy to reason, practice and improve.' },
  { id: 'operate', title: 'Operate', subtitle: 'Observe agents, builds, policy, audit and runtime health.' },
];

export default function ProductShellRoute() {
  const router = useRouter();
  const counts = useMemo(
    () => Object.fromEntries(PILLARS.map((pillar) => [pillar.id, capabilitiesFor(pillar.id).length])),
    [],
  );

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.page}>
        <View style={styles.hero}>
          <Text style={styles.eyebrow}>SKELETON</Text>
          <Text style={styles.title}>One product. Four pillars.</Text>
          <Text style={styles.subtitle}>
            The consolidated runtime is surfaced as Create, Play, Learn and Operate while mined systems remain behind stable product contracts.
          </Text>
          <View style={styles.metricsRow}>
            <Metric label="Capabilities" value={String(PRODUCT_CAPABILITIES.length)} />
            <Metric label="Pillars" value="4" />
            <Metric label="Shell" value="Unified" />
          </View>
        </View>

        {PILLARS.map((pillar) => (
          <View key={pillar.id} style={styles.section}>
            <View style={styles.sectionHeader}>
              <View style={styles.sectionCopy}>
                <Text style={styles.sectionTitle}>{pillar.title}</Text>
                <Text style={styles.sectionSubtitle}>{pillar.subtitle}</Text>
              </View>
              <Text style={styles.count}>{counts[pillar.id]}</Text>
            </View>
            <View style={styles.grid}>
              {capabilitiesFor(pillar.id).map((capability) => (
                <TouchableOpacity
                  key={capability.id}
                  style={styles.card}
                  activeOpacity={0.78}
                  onPress={() => router.push(capability.href as never)}
                >
                  <View style={styles.cardTop}>
                    <Text style={styles.cardTitle}>{capability.title}</Text>
                    {capability.experimental ? <Text style={styles.badge}>LAB</Text> : null}
                  </View>
                  <Text style={styles.cardDescription}>{capability.description}</Text>
                  <Text style={styles.surface}>{capability.backendSurface ?? 'local runtime'}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        ))}

        <TouchableOpacity style={styles.legacyButton} onPress={() => router.push('/hub' as never)}>
          <Text style={styles.legacyTitle}>Open full legacy hub</Text>
          <Text style={styles.legacySubtitle}>All accumulated tools remain available while they are progressively folded behind the product pillars.</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metric}>
      <Text style={styles.metricValue}>{value}</Text>
      <Text style={styles.metricLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#080A0F' },
  page: { paddingHorizontal: 18, paddingTop: 22, paddingBottom: 48, gap: 22 },
  hero: { borderWidth: 1, borderColor: '#232838', borderRadius: 24, padding: 22, backgroundColor: '#0D111A' },
  eyebrow: { color: '#8B9AFF', fontSize: 11, fontWeight: '800', letterSpacing: 2.2, marginBottom: 8 },
  title: { color: '#F8FAFC', fontSize: 30, lineHeight: 35, fontWeight: '800' },
  subtitle: { color: '#AAB3C5', fontSize: 14, lineHeight: 21, marginTop: 10 },
  metricsRow: { flexDirection: 'row', gap: 8, marginTop: 20 },
  metric: { flex: 1, borderRadius: 14, backgroundColor: '#121827', paddingHorizontal: 12, paddingVertical: 12 },
  metricValue: { color: '#F8FAFC', fontSize: 16, fontWeight: '800' },
  metricLabel: { color: '#748096', fontSize: 10, marginTop: 3, textTransform: 'uppercase', letterSpacing: 0.7 },
  section: { gap: 12 },
  sectionHeader: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  sectionCopy: { flex: 1 },
  sectionTitle: { color: '#F1F5F9', fontSize: 21, fontWeight: '800' },
  sectionSubtitle: { color: '#8490A5', fontSize: 12, lineHeight: 18, marginTop: 3 },
  count: { minWidth: 32, textAlign: 'center', color: '#A9B2FF', backgroundColor: '#171C31', borderRadius: 10, paddingVertical: 7, overflow: 'hidden', fontWeight: '800' },
  grid: { gap: 10 },
  card: { backgroundColor: '#0F141F', borderWidth: 1, borderColor: '#202737', borderRadius: 18, padding: 16 },
  cardTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  cardTitle: { color: '#F8FAFC', fontSize: 16, fontWeight: '800' },
  badge: { color: '#FBBF24', fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  cardDescription: { color: '#9AA6BA', fontSize: 12, lineHeight: 18, marginTop: 7 },
  surface: { color: '#69758A', fontSize: 10, marginTop: 12, fontFamily: 'monospace' },
  legacyButton: { borderRadius: 18, borderWidth: 1, borderColor: '#30374A', padding: 16, backgroundColor: '#111622' },
  legacyTitle: { color: '#DDE3EE', fontSize: 14, fontWeight: '800' },
  legacySubtitle: { color: '#7E899B', fontSize: 11, lineHeight: 17, marginTop: 5 },
});
