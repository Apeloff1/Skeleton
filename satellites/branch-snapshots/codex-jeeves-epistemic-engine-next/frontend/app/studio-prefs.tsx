/**
 * /studio-prefs — Per-creator "Studio Preferences" (creative constitution).
 * Durable preferences (genres, art style, difficulty, tone, constitution, avoid)
 * that bias every future game this creator generates.
 * Backed by GET/PUT /api/creator/preferences/{creator_id}.
 */
import { useState, useEffect, useCallback } from 'react';
import {
  View, Text, ScrollView, TextInput, TouchableOpacity, ActivityIndicator,
  StyleSheet, SafeAreaView, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { getVisitorId } from '../src/utils/liveops';
import { C, S, R } from '../src/theme/deluxe';

type Prefs = { genres: string[]; art_style: string; difficulty: string; tone: string; constitution: string; avoid: string };
type Options = { art_styles: string[]; difficulties: string[]; tones: string[] };

const GENRE_CHOICES = ['arcade', 'puzzle', 'platformer', 'shooter', 'runner', 'strategy', 'rpg', 'rhythm'];

export default function StudioPrefs() {
  const router = useRouter();
  const [prefs, setPrefs] = useState<Prefs>({ genres: [], art_style: 'any', difficulty: 'balanced', tone: 'any', constitution: '', avoid: '' });
  const [opts, setOpts] = useState<Options>({ art_styles: [], difficulties: [], tones: [] });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState('');

  useEffect(() => {
    (async () => {
      const cid = await getVisitorId();
      const r = await api.get<{ preferences: Prefs; options: Options }>(`/api/creator/preferences/${cid}`, { timeoutMs: 12000 });
      if (r.ok && r.data) { setPrefs(r.data.preferences); setOpts(r.data.options); }
      setLoading(false);
    })();
  }, []);

  const save = useCallback(async () => {
    setSaving(true); setSavedMsg('');
    const cid = await getVisitorId();
    const r = await api.put(`/api/creator/preferences/${cid}`, prefs, { timeoutMs: 12000 });
    setSaving(false);
    setSavedMsg(r.ok ? '✓ Saved — future games will follow these preferences.' : 'Could not save. Try again.');
  }, [prefs]);

  const preview = useCallback(async () => {
    setSaving(true); setSavedMsg('');
    const cid = await getVisitorId();
    await api.put(`/api/creator/preferences/${cid}`, prefs, { timeoutMs: 12000 });
    setSaving(false);
    const g = prefs.genres[0] || 'arcade';
    const brief = `a fun ${prefs.difficulty !== 'any' ? prefs.difficulty + ' ' : ''}${g} game showcasing my studio style`;
    router.push(`/playable?brief=${encodeURIComponent(brief)}` as any);
  }, [prefs, router]);

  const toggleGenre = (g: string) => setPrefs((p) => ({
    ...p, genres: p.genres.includes(g) ? p.genres.filter((x) => x !== g) : (p.genres.length < 6 ? [...p.genres, g] : p.genres),
  }));

  return (
    <SafeAreaView style={styles.safe} testID="studio-prefs-screen">
      <View style={styles.header}>
        <TouchableOpacity testID="prefs-back" onPress={() => router.back()} style={styles.backBtn}><Text style={styles.backTxt}>‹ Back</Text></TouchableOpacity>
        <Text style={styles.title}>🎛️ Studio Preferences</Text>
      </View>
      {loading ? <ActivityIndicator color={C.brand} style={{ marginTop: S.xxl }} /> : (
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <ScrollView contentContainerStyle={{ padding: S.lg, paddingBottom: S.xxxl }} keyboardShouldPersistTaps="handled">
            <Text style={styles.lead}>These bias every game you generate. The brief always wins when it conflicts.</Text>

            <Text style={styles.section}>FAVOURITE GENRES <Text style={styles.dim}>(up to 6)</Text></Text>
            <View style={styles.chipWrap}>
              {GENRE_CHOICES.map((g) => {
                const on = prefs.genres.includes(g);
                return (
                  <TouchableOpacity key={g} testID={`prefs-genre-${g}`} onPress={() => toggleGenre(g)} style={[styles.chip, on && styles.chipOn]}>
                    <Text style={[styles.chipTxt, on && styles.chipTxtOn]}>{g}</Text>
                  </TouchableOpacity>
                );
              })}
            </View>

            <Picker label="ART STYLE" value={prefs.art_style} options={opts.art_styles} onPick={(v) => setPrefs((p) => ({ ...p, art_style: v }))} idPrefix="prefs-art" />
            <Picker label="DIFFICULTY" value={prefs.difficulty} options={opts.difficulties} onPick={(v) => setPrefs((p) => ({ ...p, difficulty: v }))} idPrefix="prefs-diff" />
            <Picker label="TONE" value={prefs.tone} options={opts.tones} onPick={(v) => setPrefs((p) => ({ ...p, tone: v }))} idPrefix="prefs-tone" />

            <Text style={styles.section}>CONSTITUTION <Text style={styles.dim}>(standing creative guidance)</Text></Text>
            <TextInput
              testID="prefs-constitution"
              style={styles.input}
              placeholder="e.g. Always add a combo meter, juicy screen shake, and a satisfying win screen."
              placeholderTextColor={C.textMute}
              value={prefs.constitution}
              onChangeText={(t) => setPrefs((p) => ({ ...p, constitution: t }))}
              multiline maxLength={600}
            />

            <Text style={styles.section}>NEVER INCLUDE</Text>
            <TextInput
              testID="prefs-avoid"
              style={[styles.input, { minHeight: 56 }]}
              placeholder="e.g. no gore, no jump-scares"
              placeholderTextColor={C.textMute}
              value={prefs.avoid}
              onChangeText={(t) => setPrefs((p) => ({ ...p, avoid: t }))}
              multiline maxLength={300}
            />

            {savedMsg ? <Text style={styles.savedMsg}>{savedMsg}</Text> : null}
            <TouchableOpacity testID="prefs-save" disabled={saving} style={[styles.saveBtn, saving && { opacity: 0.6 }]} onPress={save}>
              <Text style={styles.saveTxt}>{saving ? 'Saving…' : 'Save preferences'}</Text>
            </TouchableOpacity>
            <TouchableOpacity testID="prefs-preview" disabled={saving} style={[styles.previewBtn, saving && { opacity: 0.6 }]} onPress={preview}>
              <Text style={styles.previewTxt}>⚡ Preview your preferences →</Text>
            </TouchableOpacity>
          </ScrollView>
        </KeyboardAvoidingView>
      )}
    </SafeAreaView>
  );
}

function Picker({ label, value, options, onPick, idPrefix }: { label: string; value: string; options: string[]; onPick: (v: string) => void; idPrefix: string }) {
  return (
    <View>
      <Text style={styles.section}>{label}</Text>
      <View style={styles.chipWrap}>
        {options.map((o) => {
          const on = o === value;
          return (
            <TouchableOpacity key={o} testID={`${idPrefix}-${o}`} onPress={() => onPick(o)} style={[styles.chip, on && styles.chipOn]}>
              <Text style={[styles.chipTxt, on && styles.chipTxtOn]}>{o}</Text>
            </TouchableOpacity>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: S.lg, paddingVertical: S.md, borderBottomWidth: 1, borderBottomColor: C.border },
  backBtn: { paddingVertical: 6, paddingRight: S.md, minHeight: 44, justifyContent: 'center' }, backTxt: { color: C.textMute, fontSize: 15, fontWeight: '600' },
  title: { flex: 1, color: C.text, fontSize: 20, fontWeight: '800', letterSpacing: 0.3 },
  lead: { color: C.textDim, fontSize: 13, lineHeight: 19, marginBottom: S.md },
  section: { color: C.textDim, fontSize: 12, fontWeight: '800', letterSpacing: 1.2, marginTop: S.lg, marginBottom: S.sm },
  dim: { color: C.textMute, fontWeight: '600', letterSpacing: 0 },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: S.sm },
  chip: { backgroundColor: C.surface, borderRadius: R.md, borderWidth: 1, borderColor: C.border, paddingHorizontal: 14, minHeight: 44, justifyContent: 'center' },
  chipOn: { backgroundColor: C.brand, borderColor: C.brand },
  chipTxt: { color: C.textDim, fontSize: 13, fontWeight: '700', textTransform: 'capitalize' },
  chipTxtOn: { color: '#04141f', fontWeight: '800' },
  input: { backgroundColor: C.surface, borderRadius: R.md, borderWidth: 1, borderColor: C.border, color: C.text, fontSize: 14, padding: 12, minHeight: 90, textAlignVertical: 'top' },
  savedMsg: { color: C.success, fontSize: 13, fontWeight: '700', marginTop: S.lg, textAlign: 'center' },
  saveBtn: { backgroundColor: C.brand, borderRadius: R.lg, paddingVertical: 15, alignItems: 'center', marginTop: S.lg, minHeight: 50, justifyContent: 'center' },
  saveTxt: { color: '#04141f', fontSize: 16, fontWeight: '800', letterSpacing: 0.3 },
  previewBtn: { borderWidth: 1, borderColor: C.brand, borderRadius: R.lg, paddingVertical: 14, alignItems: 'center', marginTop: S.md, minHeight: 48, justifyContent: 'center' },
  previewTxt: { color: C.brand, fontSize: 15, fontWeight: '800', letterSpacing: 0.3 },
});
