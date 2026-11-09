/**
 * /cover-studio — 🖼️ Cover Art Studio.
 * Generate cinematic key-art for a game via the REAL Nano Banana pipeline
 * (POST /api/imagine/cover). Pick a one-tap style preset, generate, roll a
 * fresh variant (regenerate), and save it to the build's cover.
 * Launch standalone or with params { pid, title, genre } from My Builds.
 */
import React from 'react';
import {
  View, Text, StyleSheet, ScrollView, SafeAreaView, TouchableOpacity,
  ActivityIndicator, TextInput, Image, Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams } from 'expo-router';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Preset = { id: string; label: string };

export default function CoverStudio() {
  const router = useRouter();
  const params = useLocalSearchParams<{ pid?: string; title?: string; genre?: string }>();
  const pid = typeof params.pid === 'string' ? params.pid : undefined;

  const [title, setTitle] = React.useState<string>(
    typeof params.title === 'string' && params.title ? params.title : 'Your Game');
  const [genre, setGenre] = React.useState<string>(
    typeof params.genre === 'string' ? params.genre : '');
  const [presets, setPresets] = React.useState<Preset[]>([]);
  const [preset, setPreset] = React.useState<string>('photoreal');
  const [cover, setCover] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [cached, setCached] = React.useState(false);
  const [saved, setSaved] = React.useState(false);

  React.useEffect(() => {
    (async () => {
      try {
        const r = await fetch(`${BACKEND}/api/imagine/presets`);
        const j = await r.json();
        if (Array.isArray(j?.presets)) setPresets(j.presets);
      } catch { /* non-fatal */ }
    })();
  }, []);

  const generate = React.useCallback(async (regenerate: boolean) => {
    setBusy(true);
    setSaved(false);
    try {
      const r = await fetch(`${BACKEND}/api/imagine/cover`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pid, title: title.trim() || 'Your Game', genre: genre.trim(),
          style_preset: preset, regenerate,
        }),
      });
      const j = await r.json();
      const data = (j?.images || [])[0]?.data;
      if (j?.status === 'success' && data) {
        setCover(data);
        setCached(!!j?.cached);
        setSaved(!!j?.stored);
      } else {
        Alert.alert('Generation failed', j?.error || 'No image was returned. Try again.');
      }
    } catch (e: any) {
      Alert.alert('Network error', String(e?.message || e));
    }
    setBusy(false);
  }, [pid, title, genre, preset]);

  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity testID="cover-back" onPress={() => router.back()} style={s.hBtn}>
          <Ionicons name="arrow-back" size={24} color="#F8FAFC" />
        </TouchableOpacity>
        <Text style={s.hTitle}>🖼️ Cover Art Studio</Text>
        <View style={s.hBtn} />
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 48 }}>
        <Text style={s.label}>Game title</Text>
        <TextInput
          testID="cover-title"
          value={title}
          onChangeText={setTitle}
          placeholder="Your Game"
          placeholderTextColor="#6b7280"
          style={s.input}
        />

        <Text style={s.label}>Genre / theme (optional)</Text>
        <TextInput
          testID="cover-genre"
          value={genre}
          onChangeText={setGenre}
          placeholder="e.g. neon cyberpunk roguelike"
          placeholderTextColor="#6b7280"
          style={s.input}
        />

        <Text style={s.label}>Style preset</Text>
        <View style={s.chips}>
          {presets.map((p) => (
            <TouchableOpacity
              key={p.id}
              testID={`preset-${p.id}`}
              onPress={() => setPreset(p.id)}
              style={[s.chip, preset === p.id && s.chipActive]}
            >
              <Text style={[s.chipTxt, preset === p.id && s.chipTxtActive]}>{p.label}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Preview */}
        <View style={s.previewWrap}>
          {busy ? (
            <View style={s.previewEmpty}>
              <ActivityIndicator color="#a78bfa" />
              <Text style={s.muted}>Painting your key art…</Text>
            </View>
          ) : cover ? (
            <Image
              testID="cover-image"
              source={{ uri: `data:image/png;base64,${cover}` }}
              style={s.preview}
              resizeMode="cover"
            />
          ) : (
            <View style={s.previewEmpty}>
              <Text style={{ fontSize: 40 }}>🎨</Text>
              <Text style={s.muted}>Pick a style and generate a cover.</Text>
            </View>
          )}
        </View>

        {cover ? (
          <Text style={s.metaLine}>
            {cached ? 'Reused from cache' : 'Freshly generated'}{saved ? ' · saved to build' : ''}
          </Text>
        ) : null}

        {/* Actions */}
        <TouchableOpacity
          testID="cover-generate"
          onPress={() => generate(false)}
          disabled={busy}
          style={[s.btn, s.btnPrimary, busy && { opacity: 0.5 }]}
        >
          <Ionicons name="sparkles-outline" size={16} color="#0b0b12" />
          <Text style={s.btnPrimaryTxt}>{cover ? 'Generate' : 'Generate Cover'}</Text>
        </TouchableOpacity>

        {cover ? (
          <TouchableOpacity
            testID="cover-regenerate"
            onPress={() => generate(true)}
            disabled={busy}
            style={[s.btn, s.btnGhost, busy && { opacity: 0.5 }]}
          >
            <Ionicons name="refresh-outline" size={16} color="#a78bfa" />
            <Text style={s.btnGhostTxt}>Roll a fresh variant</Text>
          </TouchableOpacity>
        ) : null}

        {!pid ? (
          <Text style={s.hint}>Open this from a build in My Builds to save the cover to that game.</Text>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0b0b12' },
  header: { flexDirection: 'row', alignItems: 'center', padding: 12, backgroundColor: '#15131f', borderBottomWidth: 1, borderBottomColor: '#2a2640' },
  hBtn: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  hTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '800', color: '#F8FAFC' },
  label: { color: '#c4b5fd', fontSize: 12, fontWeight: '700', marginTop: 16, marginBottom: 6 },
  input: { backgroundColor: '#15131f', borderRadius: 10, borderWidth: 1, borderColor: '#2a2640', color: '#F8FAFC', paddingHorizontal: 12, paddingVertical: 10, fontSize: 14 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 18, backgroundColor: '#15131f', borderWidth: 1, borderColor: '#2a2640' },
  chipActive: { backgroundColor: '#a78bfa22', borderColor: '#a78bfa' },
  chipTxt: { color: '#9ca3af', fontSize: 12, fontWeight: '700' },
  chipTxtActive: { color: '#c4b5fd' },
  previewWrap: { marginTop: 18, aspectRatio: 3 / 4, borderRadius: 16, overflow: 'hidden', backgroundColor: '#15131f', borderWidth: 1, borderColor: '#2a2640' },
  preview: { width: '100%', height: '100%' },
  previewEmpty: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10 },
  muted: { color: '#9ca3af', fontSize: 13, textAlign: 'center', paddingHorizontal: 24 },
  metaLine: { color: '#6b7280', fontSize: 11, marginTop: 8, textAlign: 'center' },
  btn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 12, paddingVertical: 14, marginTop: 14 },
  btnPrimary: { backgroundColor: '#a78bfa' },
  btnPrimaryTxt: { color: '#0b0b12', fontSize: 15, fontWeight: '800' },
  btnGhost: { backgroundColor: 'transparent', borderWidth: 1, borderColor: '#a78bfa55' },
  btnGhostTxt: { color: '#a78bfa', fontSize: 14, fontWeight: '700' },
  hint: { color: '#6b7280', fontSize: 12, textAlign: 'center', marginTop: 16, lineHeight: 18 },
});
