/**
 * /multiplayer — 🛰️ Netcode Studio (Cosmic Backlog V.4).
 * Generate a complete multiplayer scaffold (server + client + protocol + lobby)
 * for a game, with the right sync model (authoritative / rollback / lockstep /
 * relay). Pure codegen — instant. View & copy each generated file.
 */
import React from 'react';
import {
  View, Text, StyleSheet, ScrollView, SafeAreaView, TouchableOpacity,
  ActivityIndicator, TextInput, Modal, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Clipboard from 'expo-clipboard';
import { toast } from '../components/Toast';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Model = { id: string; label: string; desc: string; best_for: string[]; tradeoffs: string; recommended_tick: number };
type File = { path: string; lang: string; content: string };

const MODEL_ICON: Record<string, string> = {
  authoritative: 'server', rollback: 'flash', lockstep: 'sync', relay: 'git-network',
};

export default function NetcodeStudio() {
  const router = useRouter();
  const [game, setGame] = React.useState('Skybreakers');
  const [genre, setGenre] = React.useState('fast-pvp arena');
  const [models, setModels] = React.useState<Model[]>([]);
  const [recommended, setRecommended] = React.useState<string>('');
  const [selected, setSelected] = React.useState<string>('');
  const [players, setPlayers] = React.useState(8);
  const [loading, setLoading] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [files, setFiles] = React.useState<File[]>([]);
  const [meta, setMeta] = React.useState<any>(null);
  const [openFile, setOpenFile] = React.useState<File | null>(null);

  const loadModels = React.useCallback(async (g: string) => {
    try {
      const r = await fetch(`${BACKEND}/api/multiplayer/models?genre=${encodeURIComponent(g)}`);
      const j = await r.json();
      setModels(j.models || []);
      setRecommended(j.recommended || '');
      setSelected((prev) => prev || j.recommended || (j.models?.[0]?.id ?? ''));
    } catch { /* keep prior */ }
    setLoading(false);
  }, []);

  React.useEffect(() => { loadModels(genre); }, [loadModels]); // eslint-disable-line react-hooks/exhaustive-deps

  const onGenerate = async () => {
    setBusy(true); setFiles([]); setMeta(null);
    try {
      const r = await fetch(`${BACKEND}/api/multiplayer/scaffold`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game: game.trim() || 'Your Game', genre, model: selected, max_players: players }),
      });
      const j = await r.json();
      setFiles(j.files || []);
      setMeta(j);
      if (!j.files?.length) toast.warn('No files generated');
    } catch {
      toast.warn('Could not generate — check connection');
    }
    setBusy(false);
  };

  const copyFile = async (f: File) => {
    await Clipboard.setStringAsync(f.content);
    toast.success(`Copied ${f.path}`);
  };

  const onExportZip = async () => {
    try {
      const r = await fetch(`${BACKEND}/api/multiplayer/scaffold/zip`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game: game.trim() || 'Your Game', genre, model: selected, max_players: players }),
      });
      const j = await r.json();
      if (!j.zip_base64) { toast.warn('Export failed'); return; }
      if (Platform.OS === 'web') {
        const bin = atob(j.zip_base64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const url = URL.createObjectURL(new Blob([bytes], { type: 'application/zip' }));
        const a = document.createElement('a');
        a.href = url; a.download = j.filename; a.click();
        URL.revokeObjectURL(url);
        toast.success(`Downloaded ${j.filename}`);
      } else {
        // eslint-disable-next-line @typescript-eslint/no-require-imports
        const FS = require('expo-file-system/legacy');
        const uri = `${FS.cacheDirectory}${j.filename}`;
        await FS.writeAsStringAsync(uri, j.zip_base64, { encoding: 'base64' });
        toast.success(`Saved ${j.filename}`);
      }
    } catch {
      toast.warn('Export failed — check connection');
    }
  };

  return (
    <SafeAreaView style={s.root}>
      <View style={s.header}>
        <TouchableOpacity testID="mp-back" onPress={() => router.back()} style={s.hBtn}>
          <Ionicons name="arrow-back" size={24} color="#F8FAFC" />
        </TouchableOpacity>
        <Text style={s.hTitle}>🛰️ Netcode Studio</Text>
        <View style={s.hBtn} />
      </View>

      <ScrollView contentContainerStyle={{ padding: 16, paddingBottom: 60 }}>
        <Text style={s.intro}>Generate a ready-to-run multiplayer scaffold — authoritative server, client sync, wire protocol, lobby & matchmaking — tuned to your game.</Text>

        <Text style={s.lbl}>Game</Text>
        <TextInput testID="mp-game" value={game} onChangeText={setGame} style={s.input} placeholder="Game name" placeholderTextColor="#64748b" />
        <Text style={s.lbl}>Genre</Text>
        <TextInput
          testID="mp-genre" value={genre}
          onChangeText={(t) => { setGenre(t); }}
          onBlur={() => loadModels(genre)}
          onSubmitEditing={() => loadModels(genre)}
          style={s.input} placeholder="e.g. fighting, rts, co-op" placeholderTextColor="#64748b"
        />

        <View style={s.rowBetween}>
          <Text style={s.section}>Sync model</Text>
          {!!recommended && <Text style={s.recHint}>★ recommended: {recommended}</Text>}
        </View>

        {loading ? <ActivityIndicator color="#3B82F6" style={{ marginTop: 16 }} /> : (
          <View style={{ gap: 10 }}>
            {models.map((m) => {
              const on = m.id === selected;
              const rec = m.id === recommended;
              return (
                <TouchableOpacity key={m.id} testID={`model-${m.id}`} activeOpacity={0.85}
                  onPress={() => setSelected(m.id)} style={[s.modelCard, on && s.modelOn]}>
                  <View style={s.modelHead}>
                    <Ionicons name={(MODEL_ICON[m.id] || 'cube') as any} size={18} color={on ? '#3B82F6' : '#94a3b8'} />
                    <Text style={[s.modelName, on && { color: '#3B82F6' }]}>{m.label}</Text>
                    {rec && <View style={s.recPill}><Text style={s.recPillTxt}>★</Text></View>}
                  </View>
                  <Text style={s.modelDesc}>{m.desc}</Text>
                  <Text style={s.modelMeta}>Best for: {m.best_for.slice(0, 4).join(', ')} · {m.recommended_tick}Hz</Text>
                </TouchableOpacity>
              );
            })}
          </View>
        )}

        <Text style={[s.section, { marginTop: 18 }]}>Max players · {players}</Text>
        <View style={s.stepper}>
          <TouchableOpacity testID="mp-minus" style={s.stepBtn} onPress={() => setPlayers(p => Math.max(2, p - 1))}>
            <Ionicons name="remove" size={20} color="#fff" />
          </TouchableOpacity>
          <Text style={s.stepVal}>{players}</Text>
          <TouchableOpacity testID="mp-plus" style={s.stepBtn} onPress={() => setPlayers(p => Math.min(64, p + 1))}>
            <Ionicons name="add" size={20} color="#fff" />
          </TouchableOpacity>
        </View>

        <TouchableOpacity testID="mp-generate" onPress={onGenerate} style={s.genBtn} activeOpacity={0.9}>
          {busy ? <ActivityIndicator color="#fff" /> : <><Ionicons name="construct" size={18} color="#fff" /><Text style={s.genTxt}>Generate scaffold</Text></>}
        </TouchableOpacity>

        {!!meta && (
          <View style={s.resultHead}>
            <Text style={s.resultTitle}>{meta.model_label}</Text>
            <Text style={s.resultMeta}>{meta.max_players} players · {meta.tick_rate}Hz tick · {meta.snapshot_rate}Hz snapshots · {meta.file_count} files</Text>
            <TouchableOpacity testID="mp-export-zip" onPress={onExportZip} style={s.zipBtn} activeOpacity={0.9}>
              <Ionicons name="download-outline" size={16} color="#fff" />
              <Text style={s.zipTxt}>Export .zip</Text>
            </TouchableOpacity>
          </View>
        )}

        {files.map((f) => (
          <View key={f.path} style={s.fileRow}>
            <TouchableOpacity testID={`file-${f.path}`} style={{ flex: 1 }} onPress={() => setOpenFile(f)}>
              <Text style={s.filePath}>{f.path}</Text>
              <Text style={s.fileLang}>{f.lang} · {f.content.split('\n').length} lines</Text>
            </TouchableOpacity>
            <TouchableOpacity testID={`copy-${f.path}`} style={s.copyBtn} onPress={() => copyFile(f)}>
              <Ionicons name="copy-outline" size={16} color="#3B82F6" />
            </TouchableOpacity>
          </View>
        ))}
      </ScrollView>

      <Modal visible={!!openFile} animationType="slide" onRequestClose={() => setOpenFile(null)}>
        <SafeAreaView style={s.root}>
          <View style={s.header}>
            <TouchableOpacity onPress={() => setOpenFile(null)} style={s.hBtn}>
              <Ionicons name="close" size={24} color="#F8FAFC" />
            </TouchableOpacity>
            <Text style={s.hTitle} numberOfLines={1}>{openFile?.path}</Text>
            <TouchableOpacity onPress={() => openFile && copyFile(openFile)} style={s.hBtn}>
              <Ionicons name="copy-outline" size={22} color="#3B82F6" />
            </TouchableOpacity>
          </View>
          <ScrollView style={{ flex: 1 }} contentContainerStyle={{ padding: 14 }}>
            <ScrollView horizontal showsHorizontalScrollIndicator>
              <Text style={s.code} selectable>{openFile?.content}</Text>
            </ScrollView>
          </ScrollView>
        </SafeAreaView>
      </Modal>
    </SafeAreaView>
  );
}

const mono = Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' });
const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0a0f1f' },
  header: { flexDirection: 'row', alignItems: 'center', padding: 12, backgroundColor: '#0f1830', borderBottomWidth: 1, borderBottomColor: '#1e293b' },
  hBtn: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  hTitle: { flex: 1, textAlign: 'center', fontSize: 17, fontWeight: '800', color: '#F8FAFC' },
  intro: { color: '#94a3b8', fontSize: 13, lineHeight: 19, marginBottom: 14 },
  lbl: { color: '#cbd5e1', fontSize: 12, fontWeight: '700', marginBottom: 6, marginTop: 6 },
  input: { backgroundColor: '#0f1830', borderRadius: 10, borderWidth: 1, borderColor: '#1e293b', color: '#e2e8f0', fontSize: 14, paddingHorizontal: 12, paddingVertical: 11, marginBottom: 6 },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 16, marginBottom: 10 },
  section: { color: '#3B82F6', fontSize: 12, fontWeight: '800', letterSpacing: 0.6, textTransform: 'uppercase' },
  recHint: { color: '#fbbf24', fontSize: 11, fontWeight: '700' },
  modelCard: { backgroundColor: '#0f1830', borderRadius: 14, borderWidth: 2, borderColor: '#ffffff10', padding: 14 },
  modelOn: { borderColor: '#3B82F6' },
  modelHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  modelName: { flex: 1, color: '#F8FAFC', fontSize: 14, fontWeight: '800' },
  recPill: { backgroundColor: '#fbbf24', borderRadius: 8, paddingHorizontal: 6, paddingVertical: 1 },
  recPillTxt: { color: '#1f2937', fontSize: 10, fontWeight: '900' },
  modelDesc: { color: '#94a3b8', fontSize: 12, lineHeight: 17 },
  modelMeta: { color: '#64748b', fontSize: 11, marginTop: 6 },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 18, marginTop: 8 },
  stepBtn: { width: 44, height: 44, borderRadius: 12, backgroundColor: '#1e293b', alignItems: 'center', justifyContent: 'center' },
  stepVal: { color: '#F8FAFC', fontSize: 20, fontWeight: '800', minWidth: 36, textAlign: 'center' },
  genBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#1D4ED8', borderRadius: 14, paddingVertical: 15, marginTop: 20 },
  genTxt: { color: '#fff', fontSize: 15, fontWeight: '800' },
  resultHead: { marginTop: 22, marginBottom: 8 },
  resultTitle: { color: '#3B82F6', fontSize: 15, fontWeight: '800' },
  resultMeta: { color: '#94a3b8', fontSize: 12, marginTop: 3 },
  zipBtn: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', gap: 6, backgroundColor: '#7c3aed', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8, marginTop: 10 },
  zipTxt: { color: '#fff', fontSize: 13, fontWeight: '800' },
  fileRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#0f1830', borderRadius: 12, borderWidth: 1, borderColor: '#1e293b', padding: 12, marginTop: 8 },
  filePath: { color: '#e2e8f0', fontSize: 13, fontWeight: '700', fontFamily: mono },
  fileLang: { color: '#64748b', fontSize: 11, marginTop: 2 },
  copyBtn: { width: 38, height: 38, borderRadius: 19, backgroundColor: '#3B82F618', borderWidth: 1, borderColor: '#3B82F644', alignItems: 'center', justifyContent: 'center' },
  code: { color: '#cbd5e1', fontSize: 11, lineHeight: 17, fontFamily: mono },
});
