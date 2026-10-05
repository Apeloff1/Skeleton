/**
 * /assets — Asset Pipeline
 * POST /api/assets/generate/sprite → sprite prompt + dalle/sd/midjourney pack
 */
import { useState, useCallback } from 'react';
import {
  View, Text, TextInput, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, StatusBar, SafeAreaView, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { jeevesSpeak } from '../features/Academy/jeevesTts';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const CATEGORIES = ['characters', 'environment', 'ui', 'items', 'effects'];
const TYPES_BY_CAT: Record<string, string[]> = {
  characters: ['player', 'enemy', 'npc', 'boss', 'companion', 'creature'],
  environment: ['tileset', 'background', 'parallax', 'platform', 'obstacle', 'decoration'],
  ui: ['button', 'panel', 'icon', 'cursor', 'health_bar', 'inventory_slot', 'dialog_box'],
  items: ['weapon', 'armor', 'potion', 'key', 'coin', 'gem', 'food', 'tool', 'collectible'],
  effects: ['explosion', 'magic', 'smoke', 'fire', 'water', 'lightning', 'heal', 'buff', 'projectile'],
};
const STYLES = ['pixel_art', 'hand_drawn', 'vector', 'anime', 'realistic', 'chibi', 'isometric'];

export default function AssetsScreen() {
  const router = useRouter();
  const [category, setCategory] = useState('characters');
  const [assetType, setAssetType] = useState('player');
  const [style, setStyle] = useState('pixel_art');
  const [description, setDescription] = useState('Brave hero in shining armour with a glowing sword');
  const [resolution] = useState('512x512');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState('');

  const run = useCallback(async () => {
    setBusy(true); setErr(''); setResult(null);
    try {
      const r = await fetch(`${BACKEND}/api/assets/generate/sprite`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category, asset_type: assetType, style, description, resolution }),
      });
      const j = await r.json();
      setResult(j);
      if (j?.error) setErr(String(j.error).slice(0, 200));
      else jeevesSpeak('Sprite ready for download.', { context: 'celebration', prependCatchphrase: false });
    } catch (e: any) {
      setErr(String(e?.message || e).slice(0, 200));
    } finally { setBusy(false); }
  }, [category, assetType, style, description, resolution]);

  const types = TYPES_BY_CAT[category] || [];

  return (
    <SafeAreaView style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor="#0A0A0A" />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={s.header}>
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name="chevron-back" size={22} color="#A78BFA" />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={s.title}>🖼 Asset Pipeline</Text>
            <Text style={s.subtitle}>Game sprites, tiles, UI, items, effects</Text>
          </View>
        </View>

        <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 80 }}>
          <Text style={s.label}>Category</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
            {CATEGORIES.map(c => (
              <TouchableOpacity key={c} style={[s.chip, category === c && s.chipActive]} onPress={() => { setCategory(c); setAssetType((TYPES_BY_CAT[c] || ['?'])[0]); }}>
                <Text style={[s.chipText, category === c && s.chipTextActive]}>{c}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <Text style={[s.label, { marginTop: 12 }]}>Type</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
            {types.map(t => (
              <TouchableOpacity key={t} style={[s.chip, assetType === t && s.chipActive]} onPress={() => setAssetType(t)}>
                <Text style={[s.chipText, assetType === t && s.chipTextActive]}>{t}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <Text style={[s.label, { marginTop: 12 }]}>Style</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
            {STYLES.map(st => (
              <TouchableOpacity key={st} style={[s.chip, style === st && s.chipActive]} onPress={() => setStyle(st)}>
                <Text style={[s.chipText, style === st && s.chipTextActive]}>{st}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <Text style={[s.label, { marginTop: 12 }]}>Description</Text>
          <TextInput
            value={description}
            onChangeText={setDescription}
            multiline
            style={s.editor}
            placeholder="Describe the sprite…"
            placeholderTextColor="#475569"
            textAlignVertical="top"
          />

          <TouchableOpacity onPress={run} disabled={busy || !description.trim()} style={[s.runBtn, (busy || !description.trim()) && { opacity: 0.4 }]}>
            {busy ? <ActivityIndicator color="#0A0A0A" /> : (
              <>
                <Ionicons name="sparkles" size={16} color="#0A0A0A" />
                <Text style={s.runText}>Generate sprite spec</Text>
              </>
            )}
          </TouchableOpacity>

          {err ? <View style={s.errBox}><Text style={s.errText}>⚠ {err}</Text></View> : null}
          {result && (
            <View style={s.resultBox}>
              <View style={s.resultHead}>
                <Ionicons name="checkmark-circle" size={16} color="#A78BFA" />
                <Text style={s.resultHeadText}>{result.category} · {result.asset_type} · {result.style}</Text>
              </View>
              {!!result.ai_design && (
                <View style={s.subBlock}>
                  <Text style={s.subHead}>AI Design Notes</Text>
                  <Text style={s.subText}>{String(result.ai_design).slice(0, 1500)}</Text>
                </View>
              )}
              {result.prompts && (
                <View style={s.subBlock}>
                  <Text style={s.subHead}>Ready-to-use prompts</Text>
                  {Object.entries(result.prompts).map(([k, v]: [string, any]) => (
                    <View key={k} style={{ marginTop: 6 }}>
                      <Text style={s.promptKey}>{k}</Text>
                      <Text style={s.promptVal}>{String(v).slice(0, 400)}</Text>
                    </View>
                  ))}
                </View>
              )}
              <TouchableOpacity
                style={s.openImagineBtn}
                onPress={() => router.push({ pathname: '/imagine', params: { prompt: result?.prompts?.dalle_prompt || description } } as any)}
              >
                <Ionicons name="image" size={13} color="#8B5CF6" />
                <Text style={s.openImagineText}>Render in Imagine →</Text>
              </TouchableOpacity>
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0A0A0A' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: 14, paddingVertical: 10, borderBottomColor: '#1F1F1F', borderBottomWidth: 1 },
  backBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  title: { color: '#f1f5f9', fontSize: 16, fontWeight: '900' },
  subtitle: { color: '#94a3b8', fontSize: 11, marginTop: 2 },
  label: { color: '#94a3b8', fontSize: 11, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 6 },
  chip: { paddingHorizontal: 12, paddingVertical: 8, minHeight: 34, borderRadius: 14, backgroundColor: '#141414', borderWidth: 1, borderColor: '#1F1F1F' },
  chipActive: { backgroundColor: '#A78BFA33', borderColor: '#A78BFA' },
  chipText: { color: '#94a3b8', fontSize: 11, fontWeight: '600' },
  chipTextActive: { color: '#A78BFA', fontWeight: '700' },
  editor: { minHeight: 80, color: '#f1f5f9', fontSize: 13, lineHeight: 18, padding: 14, backgroundColor: '#141414', borderRadius: 10, borderWidth: 1, borderColor: '#1F1F1F' },
  runBtn: { marginTop: 14, paddingVertical: 12, borderRadius: 10, backgroundColor: '#A78BFA', alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8 },
  runText: { color: '#0A0A0A', fontSize: 14, fontWeight: '900' },
  errBox: { marginTop: 10, padding: 10, borderRadius: 8, backgroundColor: '#f8717122', borderColor: '#f87171', borderWidth: 1 },
  errText: { color: '#fecaca', fontSize: 11 },
  resultBox: { marginTop: 12, padding: 14, backgroundColor: '#141414', borderRadius: 12, borderWidth: 1, borderColor: '#A78BFA55' },
  resultHead: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  resultHeadText: { color: '#A78BFA', fontSize: 11, fontWeight: '900', textTransform: 'uppercase', letterSpacing: 1 },
  subBlock: { marginTop: 8 },
  subHead: { color: '#94a3b8', fontSize: 10, fontWeight: '700', marginBottom: 4 },
  subText: { color: '#cbd5e1', fontSize: 12, lineHeight: 17 },
  promptKey: { color: '#a78bfa', fontSize: 10, fontWeight: '700', marginBottom: 2 },
  promptVal: { color: '#fde68a', fontSize: 11, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', lineHeight: 15 },
  openImagineBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 12, padding: 10, borderRadius: 8, backgroundColor: '#8B5CF622', borderColor: '#8B5CF6', borderWidth: 1 },
  openImagineText: { color: '#8B5CF6', fontSize: 12, fontWeight: '700' },
});
