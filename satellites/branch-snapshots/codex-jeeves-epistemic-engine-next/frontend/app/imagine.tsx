/**
 * /imagine — AI Image Generation
 * POST /api/imagine/generate → base64 image(s)
 */
import { useState, useCallback } from 'react';
import {
  View, Text, TextInput, ScrollView, TouchableOpacity, ActivityIndicator, Image,
  StyleSheet, StatusBar, SafeAreaView, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { jeevesSpeak } from '../features/Academy/jeevesTts';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const SIZES = ['1024x1024', '1792x1024', '1024x1792', '512x512'];
const PROVIDERS = ['openai', 'gemini'];
const QUALITIES = ['standard', 'hd'];

export default function ImagineScreen() {
  const router = useRouter();
  const [prompt, setPrompt] = useState('A cosy library with floating books, soft golden lamplight, painterly style');
  const [provider, setProvider] = useState('openai');
  const [size, setSize] = useState('1024x1024');
  const [quality, setQuality] = useState('standard');
  const [busy, setBusy] = useState(false);
  const [images, setImages] = useState<string[]>([]);
  const [err, setErr] = useState('');
  const [enhancing, setEnhancing] = useState(false);
  const [enhanced, setEnhanced] = useState('');

  const run = useCallback(async () => {
    setBusy(true); setErr(''); setImages([]);
    try {
      const r = await fetch(`${BACKEND}/api/imagine/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: enhanced || prompt, provider, size, quality }),
      });
      const j = await r.json();
      const imgs = (j?.images || []) as string[];
      setImages(imgs);
      if (j?.error) setErr(String(j.error).slice(0, 200));
      else jeevesSpeak(`${imgs.length} ${imgs.length === 1 ? 'image' : 'images'} generated.`, { context: 'celebration', prependCatchphrase: false });
    } catch (e: any) {
      setErr(String(e?.message || e).slice(0, 200));
    } finally { setBusy(false); }
  }, [prompt, enhanced, provider, size, quality]);

  const enhance = useCallback(async () => {
    setEnhancing(true); setErr('');
    try {
      const r = await fetch(`${BACKEND}/api/imagine/enhance-prompt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
      });
      const j = await r.json();
      setEnhanced(j?.enhanced_prompt || j?.prompt || '');
    } catch (e: any) {
      setErr(String(e?.message || e).slice(0, 200));
    } finally { setEnhancing(false); }
  }, [prompt]);

  return (
    <SafeAreaView style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor="#0A0A0A" />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={s.header}>
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name="chevron-back" size={22} color="#8B5CF6" />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={s.title}>🎨 Imagine</Text>
            <Text style={s.subtitle}>AI image generation · OpenAI gpt-image-1 / Gemini Nano Banana</Text>
          </View>
        </View>

        <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 80 }}>
          <Text style={s.label}>Prompt</Text>
          <TextInput
            value={prompt}
            onChangeText={t => { setPrompt(t); setEnhanced(''); }}
            multiline
            style={s.editor}
            placeholder="Describe what you want to see…"
            placeholderTextColor="#475569"
            textAlignVertical="top"
          />
          <TouchableOpacity onPress={enhance} disabled={enhancing || !prompt.trim()} style={s.enhanceBtn}>
            {enhancing ? <ActivityIndicator color="#8B5CF6" /> : (
              <>
                <Ionicons name="sparkles" size={14} color="#8B5CF6" />
                <Text style={s.enhanceText}>{enhanced ? '✓ Enhanced — tap to re-enhance' : 'Enhance prompt with AI'}</Text>
              </>
            )}
          </TouchableOpacity>
          {!!enhanced && (
            <View style={s.enhancedBox}>
              <Text style={s.enhancedHead}>Enhanced</Text>
              <Text style={s.enhancedText}>{enhanced}</Text>
            </View>
          )}

          <Text style={[s.label, { marginTop: 12 }]}>Provider</Text>
          <View style={s.chipRow}>
            {PROVIDERS.map(p => (
              <TouchableOpacity key={p} style={[s.chip, provider === p && s.chipActive]} onPress={() => setProvider(p)}>
                <Text style={[s.chipText, provider === p && s.chipTextActive]}>{p}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={[s.label, { marginTop: 12 }]}>Size</Text>
          <View style={s.chipRow}>
            {SIZES.map(sz => (
              <TouchableOpacity key={sz} style={[s.chip, size === sz && s.chipActive]} onPress={() => setSize(sz)}>
                <Text style={[s.chipText, size === sz && s.chipTextActive]}>{sz}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={[s.label, { marginTop: 12 }]}>Quality</Text>
          <View style={s.chipRow}>
            {QUALITIES.map(q => (
              <TouchableOpacity key={q} style={[s.chip, quality === q && s.chipActive]} onPress={() => setQuality(q)}>
                <Text style={[s.chipText, quality === q && s.chipTextActive]}>{q}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <TouchableOpacity onPress={run} disabled={busy || !prompt.trim()} style={[s.runBtn, (busy || !prompt.trim()) && { opacity: 0.4 }]}>
            {busy ? <ActivityIndicator color="#0A0A0A" /> : (
              <>
                <Ionicons name="image" size={16} color="#0A0A0A" />
                <Text style={s.runText}>Generate</Text>
              </>
            )}
          </TouchableOpacity>

          {err ? <View style={s.errBox}><Text style={s.errText}>⚠ {err}</Text></View> : null}
          {images.length > 0 && (
            <View style={{ marginTop: 12, gap: 10 }}>
              {images.map((img, i) => (
                <View key={i} style={s.imageCard}>
                  <Image source={{ uri: img.startsWith('data:') ? img : `data:image/png;base64,${img}` }} style={s.image} resizeMode="contain" />
                  <Text style={s.imageMeta}>Image {i + 1} · {size}</Text>
                </View>
              ))}
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
  editor: { minHeight: 90, color: '#f1f5f9', fontSize: 13, lineHeight: 18, padding: 14, backgroundColor: '#141414', borderRadius: 10, borderWidth: 1, borderColor: '#1F1F1F' },
  enhanceBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 8, padding: 10, borderRadius: 8, backgroundColor: '#8B5CF622', borderColor: '#8B5CF6', borderWidth: 1 },
  enhanceText: { color: '#8B5CF6', fontSize: 12, fontWeight: '700' },
  enhancedBox: { marginTop: 8, padding: 10, borderRadius: 8, backgroundColor: '#141414', borderWidth: 1, borderColor: '#8B5CF655' },
  enhancedHead: { color: '#8B5CF6', fontSize: 10, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 4 },
  enhancedText: { color: '#cbd5e1', fontSize: 12, lineHeight: 17 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { paddingHorizontal: 12, paddingVertical: 8, minHeight: 34, borderRadius: 14, backgroundColor: '#141414', borderWidth: 1, borderColor: '#1F1F1F' },
  chipActive: { backgroundColor: '#8B5CF633', borderColor: '#8B5CF6' },
  chipText: { color: '#94a3b8', fontSize: 11, fontWeight: '600' },
  chipTextActive: { color: '#8B5CF6', fontWeight: '700' },
  runBtn: { marginTop: 14, paddingVertical: 12, borderRadius: 10, backgroundColor: '#8B5CF6', alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8 },
  runText: { color: '#0A0A0A', fontSize: 14, fontWeight: '900' },
  errBox: { marginTop: 10, padding: 10, borderRadius: 8, backgroundColor: '#f8717122', borderColor: '#f87171', borderWidth: 1 },
  errText: { color: '#fecaca', fontSize: 11 },
  imageCard: { padding: 8, backgroundColor: '#141414', borderRadius: 10, borderWidth: 1, borderColor: '#1F1F1F' },
  image: { width: '100%', height: 320, borderRadius: 8, backgroundColor: '#000' },
  imageMeta: { color: '#94a3b8', fontSize: 10, marginTop: 6, textAlign: 'center' },
});
