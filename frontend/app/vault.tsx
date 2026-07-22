/**
 * /vault — Unified Vault (mirrored).
 * Shows the exact same aggregated vault as every other vault surface.
 */
import React from 'react';
import { View, Text, StyleSheet, SafeAreaView, TouchableOpacity } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import UnifiedVault from '../src/components/UnifiedVault';

const GREEN = '#22c55e';
const BG = '#0b1220';
const MUTE = '#94a3b8';

export default function VaultRoute() {
  const router = useRouter();
  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity testID="vault-back" onPress={() => router.back()} style={{ padding: 4 }} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
          <Ionicons name="chevron-back" size={22} color={GREEN} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>🔒 Vault</Text>
          <Text style={s.sub}>Mirrored across Boardroom · Agents · Worldforge</Text>
        </View>
      </View>
      <UnifiedVault />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: BG },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1f2937' },
  title: { color: '#f1f5f9', fontSize: 17, fontWeight: '700' },
  sub: { color: MUTE, fontSize: 12, marginTop: 1 },
});
