/**
 * /settings/appearance — 🎨 App Reskinner. Pick from 30 skins (default Hyperwave),
 * live preview, persisted app-wide. Big win: full visual personalization.
 */
import React from 'react';
import { View, Text, ScrollView, TouchableOpacity, StyleSheet, SafeAreaView, TextInput } from 'react-native';
import { useRouter } from 'expo-router';
import { SKINS, SKIN_BY_ID, DEFAULT_SKIN } from '../../theme/skins';
import { applySkin, useActiveSkin } from '../../src/utils/skinStore';

export default function Appearance() {
  const router = useRouter();
  const { id } = useActiveSkin();
  const [q, setQ] = React.useState('');
  const active = SKIN_BY_ID[id] || SKIN_BY_ID[DEFAULT_SKIN];

  const list = React.useMemo(() => {
    const s = q.trim().toLowerCase();
    return s ? SKINS.filter((k) => k.name.toLowerCase().includes(s) || k.id.includes(s)) : SKINS;
  }, [q]);

  const randomize = () => {
    const pick = SKINS[Math.floor(Math.random() * SKINS.length)];
    applySkin(pick.id);
  };

  return (
    <SafeAreaView style={[styles.root, { backgroundColor: active.colors.bg }]}>
      <View style={[styles.header, { borderBottomColor: active.colors.bgElevated }]}>
        <TouchableOpacity testID="appearance-back" onPress={() => router.back()} style={styles.back}>
          <Text style={[styles.backTxt, { color: active.colors.primary }]}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>🎨 App Skin</Text>
        <TouchableOpacity testID="skin-random" onPress={randomize} style={[styles.randBtn, { backgroundColor: active.colors.primary }]}>
          <Text style={styles.randTxt}>🎲 Random</Text>
        </TouchableOpacity>
      </View>

      {/* live preview hero */}
      <View testID="skin-preview" style={[styles.preview, { backgroundColor: active.colors.bgElevated, borderColor: active.colors.primary }]}>
        <Text style={styles.previewEmoji}>{active.emoji}</Text>
        <View style={{ flex: 1 }}>
          <Text style={styles.previewName}>{active.name}{id === DEFAULT_SKIN ? '  ·  default' : ''}</Text>
          <View style={styles.swatchRow}>
            {[active.colors.primary, active.colors.accentCyan, active.colors.accentPink, active.colors.accentGold].map((c, i) => (
              <View key={i} style={[styles.swatch, { backgroundColor: c }]} />
            ))}
          </View>
        </View>
      </View>

      <View style={[styles.search, { backgroundColor: active.colors.bgElevated }]}>
        <TextInput testID="skin-search" value={q} onChangeText={setQ} placeholder="Search 30 skins…"
          placeholderTextColor="#64748b" style={styles.searchInput} autoCorrect={false} />
      </View>

      <ScrollView contentContainerStyle={styles.grid}>
        {list.map((sk) => {
          const on = sk.id === id;
          return (
            <TouchableOpacity key={sk.id} testID={`skin-${sk.id}`} activeOpacity={0.85}
              onPress={() => applySkin(sk.id)}
              style={[styles.card, { backgroundColor: sk.colors.bgElevated, borderColor: on ? sk.colors.primary : '#ffffff14' }]}>
              <View style={[styles.cardBg, { backgroundColor: sk.colors.bg }]}>
                <Text style={styles.cardEmoji}>{sk.emoji}</Text>
                <View style={styles.cardSwatches}>
                  {[sk.colors.primary, sk.colors.accentCyan, sk.colors.accentPink].map((c, i) => (
                    <View key={i} style={[styles.cardDot, { backgroundColor: c }]} />
                  ))}
                </View>
              </View>
              <Text style={styles.cardName} numberOfLines={1}>{sk.name}</Text>
              {on && <View style={[styles.activePill, { backgroundColor: sk.colors.primary }]}><Text style={styles.activeTxt}>ACTIVE</Text></View>}
              {sk.id === DEFAULT_SKIN && !on && <Text style={styles.defTag}>default</Text>}
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0b0820' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 12, borderBottomWidth: 1, gap: 8 },
  back: { paddingVertical: 6, paddingHorizontal: 4 },
  backTxt: { fontSize: 15, fontWeight: '700' },
  title: { color: '#F8FAFC', fontSize: 18, fontWeight: '800', flex: 1 },
  randBtn: { borderRadius: 9, paddingHorizontal: 12, paddingVertical: 7 },
  randTxt: { color: '#fff', fontWeight: '800', fontSize: 12 },
  preview: { flexDirection: 'row', alignItems: 'center', gap: 14, margin: 14, marginBottom: 8, borderRadius: 16, borderWidth: 2, padding: 16 },
  previewEmoji: { fontSize: 40 },
  previewName: { color: '#F8FAFC', fontSize: 18, fontWeight: '800', textTransform: 'capitalize' },
  swatchRow: { flexDirection: 'row', gap: 6, marginTop: 8 },
  swatch: { width: 34, height: 14, borderRadius: 4 },
  search: { marginHorizontal: 14, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8, marginBottom: 6 },
  searchInput: { color: '#e2e8f0', fontSize: 13 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, padding: 14, justifyContent: 'space-between' },
  card: { width: '31%', borderRadius: 12, borderWidth: 2, padding: 6, alignItems: 'center' },
  cardBg: { width: '100%', height: 56, borderRadius: 8, alignItems: 'center', justifyContent: 'center', marginBottom: 6 },
  cardEmoji: { fontSize: 22 },
  cardSwatches: { flexDirection: 'row', gap: 4, marginTop: 4 },
  cardDot: { width: 8, height: 8, borderRadius: 4 },
  cardName: { color: '#e2e8f0', fontSize: 11, fontWeight: '700' },
  activePill: { borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2, marginTop: 3 },
  activeTxt: { color: '#fff', fontSize: 8, fontWeight: '900' },
  defTag: { color: '#94a3b8', fontSize: 9, marginTop: 3 },
});
