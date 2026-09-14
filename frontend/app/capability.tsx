import React, { useMemo } from 'react';
import {
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';

import { capabilityById } from '../src/product/productCatalog';

const PILLAR_COPY = {
  create: 'CREATE',
  play: 'PLAY',
  learn: 'LEARN',
  operate: 'OPERATE',
} as const;

export default function CapabilityRoute() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string | string[] }>();
  const id = Array.isArray(params.id) ? params.id[0] : params.id;
  const capability = useMemo(() => (id ? capabilityById(id) : undefined), [id]);

  if (!capability) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.empty}>
          <Text style={styles.eyebrow}>SKELETON</Text>
          <Text style={styles.title}>Unknown capability</Text>
          <Text style={styles.description}>This product surface is not part of the canonical capability catalog.</Text>
          <TouchableOpacity style={styles.primaryButton} onPress={() => router.replace('/product' as never)}>
            <Text style={styles.primaryButtonText}>Back to product</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.page}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={12}>
          <Text style={styles.back}>‹ Product</Text>
        </TouchableOpacity>

        <View style={styles.hero}>
          <Text style={styles.eyebrow}>{PILLAR_COPY[capability.pillar]}</Text>
          <Text style={styles.title}>{capability.title}</Text>
          <Text style={styles.description}>{capability.description}</Text>
          <View style={styles.contractRow}>
            <Text style={styles.contractLabel}>Backend contract</Text>
            <Text style={styles.contractValue}>{capability.backendSurface ?? 'local runtime'}</Text>
          </View>
        </View>

        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>Actions</Text>
          <Text style={styles.sectionMeta}>{capability.actions.length} canonical</Text>
        </View>

        {capability.actions.map((action) => (
          <View key={action.id} style={styles.actionCard}>
            <Text style={styles.actionTitle}>{action.title}</Text>
            <Text style={styles.actionDescription}>{action.description}</Text>
            <View style={styles.operationPill}>
              <Text style={styles.operationText}>{action.operation}</Text>
            </View>
            <View style={styles.buttonRow}>
              <TouchableOpacity
                style={[styles.actionButton, { flex: 1 }]}
                onPress={() => router.push(`/operation?capability=${encodeURIComponent(capability.id)}&action=${encodeURIComponent(action.id)}` as never)}
                activeOpacity={0.8}
              >
                <Text style={styles.actionButtonText}>Governed action</Text>
              </TouchableOpacity>
              {action.legacyHref ? (
                <TouchableOpacity
                  style={[styles.legacyActionButton, { flex: 1 }]}
                  onPress={() => router.push(action.legacyHref as never)}
                  activeOpacity={0.8}
                >
                  <Text style={styles.legacyActionButtonText}>Legacy UI</Text>
                </TouchableOpacity>
              ) : null}
            </View>
          </View>
        ))}

        <View style={styles.footerCard}>
          <Text style={styles.footerTitle}>Compatibility escape hatch</Text>
          <Text style={styles.footerText}>
            The legacy hub remains available while individual systems are promoted behind canonical capability contracts.
          </Text>
          <TouchableOpacity style={styles.secondaryButton} onPress={() => router.push('/hub' as never)}>
            <Text style={styles.secondaryButtonText}>Open legacy hub</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#080A0F' },
  page: { paddingHorizontal: 18, paddingTop: 18, paddingBottom: 48, gap: 14 },
  back: { color: '#99A7FF', fontSize: 13, fontWeight: '800', paddingVertical: 5 },
  hero: { borderWidth: 1, borderColor: '#232838', borderRadius: 24, padding: 22, backgroundColor: '#0D111A' },
  eyebrow: { color: '#8B9AFF', fontSize: 11, fontWeight: '900', letterSpacing: 2.2, marginBottom: 8 },
  title: { color: '#F8FAFC', fontSize: 30, lineHeight: 35, fontWeight: '900' },
  description: { color: '#AAB3C5', fontSize: 14, lineHeight: 21, marginTop: 9 },
  contractRow: { marginTop: 18, paddingTop: 14, borderTopWidth: 1, borderTopColor: '#202737' },
  contractLabel: { color: '#69758A', fontSize: 10, textTransform: 'uppercase', letterSpacing: 0.8 },
  contractValue: { color: '#B5C0D3', fontSize: 11, fontFamily: 'monospace', marginTop: 5 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 4 },
  sectionTitle: { color: '#F1F5F9', fontSize: 19, fontWeight: '900' },
  sectionMeta: { color: '#69758A', fontSize: 11, fontWeight: '700' },
  actionCard: { borderWidth: 1, borderColor: '#202737', borderRadius: 18, backgroundColor: '#0F141F', padding: 16 },
  actionTitle: { color: '#F8FAFC', fontSize: 16, fontWeight: '850' },
  actionDescription: { color: '#95A1B4', fontSize: 12, lineHeight: 18, marginTop: 5 },
  operationPill: { alignSelf: 'flex-start', marginTop: 12, borderRadius: 9, backgroundColor: '#151B2B', paddingHorizontal: 9, paddingVertical: 6 },
  operationText: { color: '#8F9DFF', fontFamily: 'monospace', fontSize: 10 },
  buttonRow: { flexDirection: 'row', gap: 8, marginTop: 14 },
  actionButton: { borderRadius: 12, backgroundColor: '#6D5CE7', paddingHorizontal: 14, paddingVertical: 11, alignItems: 'center' },
  actionButtonText: { color: '#FFFFFF', fontSize: 12, fontWeight: '850' },
  legacyActionButton: { borderRadius: 12, borderWidth: 1, borderColor: '#334059', paddingHorizontal: 14, paddingVertical: 11, alignItems: 'center' },
  legacyActionButtonText: { color: '#AAB4C7', fontSize: 12, fontWeight: '800' },
  footerCard: { marginTop: 6, borderRadius: 18, borderWidth: 1, borderColor: '#30374A', padding: 16, backgroundColor: '#111622' },
  footerTitle: { color: '#DDE3EE', fontSize: 14, fontWeight: '850' },
  footerText: { color: '#7E899B', fontSize: 11, lineHeight: 17, marginTop: 5 },
  secondaryButton: { marginTop: 13, borderRadius: 12, borderWidth: 1, borderColor: '#343D54', paddingVertical: 11, alignItems: 'center' },
  secondaryButtonText: { color: '#AAB4C7', fontSize: 12, fontWeight: '800' },
  empty: { flex: 1, justifyContent: 'center', paddingHorizontal: 26 },
  primaryButton: { marginTop: 22, borderRadius: 14, backgroundColor: '#6D5CE7', paddingVertical: 13, alignItems: 'center' },
  primaryButtonText: { color: '#FFFFFF', fontWeight: '850' },
});
