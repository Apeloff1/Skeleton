/**
 * /music — AI Music Pipeline
 * POST /api/music/generate → score / SFX / adaptive
 */
import { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TextInput, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, StatusBar, SafeAreaView, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { jeevesSpeak } from '../features/Academy/jeevesTts';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const GENRES = ['orchestral', 'electronic', 'ambient', 'rock', 'jazz', 'lofi', 'chiptune', 'cinematic'];
const MOODS = ['epic', 'mysterious', 'energetic', 'calm', 'sad', 'tense', 'triumphant', 'eerie'];
const DURATIONS = [30, 60, 90, 180];

export default function MusicScreen() {
  const router = useRouter();
  const [presets, setPresets] = useState<any[]>([]);
  const [genre, setGenre] = useState('orchestral');
  const [mood, setMood] = useState('epic');
  const [tempo, setTempo] = useState(120);
  const [duration, setDuration] = useState(60);
  const [loopable, setLoopable] = useState(true);
  const [description, setDescription] = useState('A grand orchestral overture for a fantasy castle');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState('');

  useEffect(() => {
    fetch(`${BACKEND}/api/music/presets`).then(r => r.json()).then(j => setPresets(j?.presets || [])).catch(() => {});
  }, []);

  const applyPreset = (p: any) => {
    setGenre(p.genre); setMood(p.mood); setTempo(p.tempo); setLoopable(!!p.loopable);
    setDescription(p.description || '');
  };

  const run = useCallback(async () => {
    setBusy(true); setErr(''); setResult(null);
    try {
      const r = await fetch(`${BACKEND}/api/music/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ description, genre, mood, tempo, duration_seconds: duration, loopable }),
      });
      const j = await r.json();
      setResult(j);
      if (j?.error) setErr(String(j.error).slice(0, 200));
      else jeevesSpeak('Composition complete.', { context: 'celebration', prependCatchphrase: false });
    } catch (e: any) {
      setErr(String(e?.message || e).slice(0, 200));
    } finally { setBusy(false); }
  }, [description, genre, mood, tempo, duration, loopable]);

  return (
    <SafeAreaView style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor="#0A0A0A" />
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={s.header}>
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name="chevron-back" size={22} color="#3B82F6" />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={s.title}>🎵 Music Pipeline</Text>
            <Text style={s.subtitle}>Score · SFX · adaptive game music</Text>
          </View>
        </View>

        <ScrollView contentContainerStyle={{ padding: 14, paddingBottom: 80 }}>
          {presets.length > 0 && (
            <>
              <Text style={s.label}>Presets</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingBottom: 4 }}>
                {presets.map(p => (
                  <TouchableOpacity key={p.id} style={s.preset} onPress={() => applyPreset(p)} activeOpacity={0.8}>
                    <Text style={s.presetName}>{p.name}</Text>
                    <Text style={s.presetMeta}>{p.genre} · {p.mood}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </>
          )}

          <Text style={[s.label, { marginTop: 12 }]}>Genre</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
            {GENRES.map(g => (
              <TouchableOpacity key={g} style={[s.chip, genre === g && s.chipActive]} onPress={() => setGenre(g)}>
                <Text style={[s.chipText, genre === g && s.chipTextActive]}>{g}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <Text style={[s.label, { marginTop: 12 }]}>Mood</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6 }}>
            {MOODS.map(m => (
              <TouchableOpacity key={m} style={[s.chip, mood === m && s.chipActive]} onPress={() => setMood(m)}>
                <Text style={[s.chipText, mood === m && s.chipTextActive]}>{m}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <View style={{ flexDirection: 'row', gap: 12, marginTop: 12 }}>
            <View style={{ flex: 1 }}>
              <Text style={s.label}>Tempo (BPM)</Text>
              <TextInput
                value={String(tempo)}
                onChangeText={t => setTempo(parseInt(t || '0', 10))}
                keyboardType="numeric"
                style={s.numInput}
              />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.label}>Duration (s)</Text>
              <View style={s.chipRow}>
                {DURATIONS.map(d => (
                  <TouchableOpacity key={d} style={[s.chip, duration === d && s.chipActive]} onPress={() => setDuration(d)}>
                    <Text style={[s.chipText, duration === d && s.chipTextActive]}>{d}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            </View>
          </View>

          <TouchableOpacity
            onPress={() => setLoopable(v => !v)}
            style={[s.toggleRow, loopable && s.toggleRowOn]}
            activeOpacity={0.8}
          >
            <Ionicons name={loopable ? 'repeat' : 'remove-outline'} size={14} color={loopable ? '#3B82F6' : '#94a3b8'} />
            <Text style={[s.toggleText, loopable && { color: '#3B82F6', fontWeight: '700' }]}>Loopable</Text>
          </TouchableOpacity>

          <Text style={[s.label, { marginTop: 12 }]}>Description</Text>
          <TextInput
            value={description}
            onChangeText={setDescription}
            multiline
            style={s.editor}
            placeholder="Describe the music…"
            placeholderTextColor="#475569"
            textAlignVertical="top"
          />

          <TouchableOpacity onPress={run} disabled={busy || !description.trim()} style={[s.runBtn, (busy || !description.trim()) && { opacity: 0.4 }]}>
            {busy ? <ActivityIndicator color="#0A0A0A" /> : (
              <>
                <Ionicons name="musical-notes" size={16} color="#0A0A0A" />
                <Text style={s.runText}>Generate composition spec</Text>
              </>
            )}
          </TouchableOpacity>

          {err ? <View style={s.errBox}><Text style={s.errText}>⚠ {err}</Text></View> : null}
          {result && (
            <View style={s.resultBox}>
              <View style={s.resultHead}>
                <Ionicons name="musical-note" size={16} color="#3B82F6" />
                <Text style={s.resultHeadText}>{genre} · {mood} · {tempo} BPM · {duration}s</Text>
              </View>
              {!!result.composition && (
                <Text style={s.resultText}>{String(result.composition).slice(0, 2000)}</Text>
              )}
              {!!result.score_outline && (
                <Text style={s.resultText}>{String(result.score_outline).slice(0, 2000)}</Text>
              )}
              {!result.composition && !result.score_outline && (
                <Text style={s.resultText}>{JSON.stringify(result, null, 2).slice(0, 2000)}</Text>
              )}
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
  preset: { padding: 10, borderRadius: 10, backgroundColor: '#141414', borderWidth: 1, borderColor: '#1F1F1F', minWidth: 110 },
  presetName: { color: '#3B82F6', fontSize: 11, fontWeight: '800' },
  presetMeta: { color: '#94a3b8', fontSize: 9, marginTop: 2 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { paddingHorizontal: 12, paddingVertical: 8, minHeight: 34, borderRadius: 14, backgroundColor: '#141414', borderWidth: 1, borderColor: '#1F1F1F' },
  chipActive: { backgroundColor: '#3B82F633', borderColor: '#3B82F6' },
  chipText: { color: '#94a3b8', fontSize: 11, fontWeight: '600' },
  chipTextActive: { color: '#3B82F6', fontWeight: '700' },
  numInput: { color: '#f1f5f9', fontSize: 13, padding: 10, backgroundColor: '#141414', borderRadius: 10, borderWidth: 1, borderColor: '#1F1F1F' },
  toggleRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10, padding: 10, borderRadius: 8, backgroundColor: '#141414', borderColor: '#1F1F1F', borderWidth: 1, alignSelf: 'flex-start' },
  toggleRowOn: { backgroundColor: '#3B82F622', borderColor: '#3B82F6' },
  toggleText: { color: '#94a3b8', fontSize: 12 },
  editor: { minHeight: 80, color: '#f1f5f9', fontSize: 13, lineHeight: 18, padding: 14, backgroundColor: '#141414', borderRadius: 10, borderWidth: 1, borderColor: '#1F1F1F' },
  runBtn: { marginTop: 14, paddingVertical: 12, borderRadius: 10, backgroundColor: '#3B82F6', alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 8 },
  runText: { color: '#0A0A0A', fontSize: 14, fontWeight: '900' },
  errBox: { marginTop: 10, padding: 10, borderRadius: 8, backgroundColor: '#f8717122', borderColor: '#f87171', borderWidth: 1 },
  errText: { color: '#fecaca', fontSize: 11 },
  resultBox: { marginTop: 12, padding: 14, backgroundColor: '#141414', borderRadius: 12, borderWidth: 1, borderColor: '#3B82F655' },
  resultHead: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  resultHeadText: { color: '#3B82F6', fontSize: 11, fontWeight: '900', textTransform: 'uppercase', letterSpacing: 1 },
  resultText: { color: '#cbd5e1', fontSize: 12, lineHeight: 17, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
});
