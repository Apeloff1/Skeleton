/**
 * /jeeves-chat — SOTA 2026 Jeeves chat.
 * Free-tier-cascade backed conversation where Jeeves can reply in MANY forms in
 * a single parse: text + charts + graph + visual + PDF + spreadsheet. Supports
 * multimodal attach (image / PDF) and renders artifacts inline.
 */
import React from 'react';
import {
  View, Text, StyleSheet, SafeAreaView, ScrollView, TouchableOpacity,
  ActivityIndicator, TextInput, Image, KeyboardAvoidingView, Platform, Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import api from '../src/utils/apiClient';

const BG = '#0b1220';
const CARD = '#111a2e';
const PURPLE = '#7c3aed';
const GREEN = '#22c55e';
const AMBER = '#f59e0b';
const MUTE = '#64748b';
const FG = '#e2e8f0';

type Artifact = { type: string; kind?: string; title?: string; mime: string; base64: string; filename?: string };
type Msg = { role: 'user' | 'jeeves'; text: string; tier?: string; artifacts?: Artifact[]; forms?: string[] };

function TierBadge({ tier }: { tier?: string }) {
  if (!tier) return null;
  const color = tier === 'paid' ? AMBER : tier === 'free' ? GREEN : PURPLE;
  const label = tier === 'paid' ? 'paid · escalated' : tier === 'free' ? 'free tier' : 'local · free';
  return (
    <View style={[st.badge, { backgroundColor: color + '22' }]}>
      <Ionicons name="flash-outline" size={10} color={color} />
      <Text style={[st.badgeTxt, { color }]}>{label}</Text>
    </View>
  );
}

function ArtifactView({ a }: { a: Artifact }) {
  const isImg = a.mime?.startsWith('image/');
  const open = () => {
    const uri = `data:${a.mime};base64,${a.base64}`;
    if (Platform.OS === 'web') {
      const w = (globalThis as any).window;
      if (w) { const link = w.document.createElement('a'); link.href = uri; link.download = a.filename || 'jeeves-file'; link.click(); }
    } else {
      Linking.openURL(uri).catch(() => {});
    }
  };
  if (isImg) {
    return (
      <View style={st.artCard}>
        <Text style={st.artLabel}>{(a.kind || a.type).toUpperCase()}{a.title ? ` · ${a.title}` : ''}</Text>
        <Image source={{ uri: `data:${a.mime};base64,${a.base64}` }}
          style={st.artImg} resizeMode="contain" />
      </View>
    );
  }
  const icon = a.type === 'pdf' ? 'document-text' : 'grid';
  const color = a.type === 'pdf' ? '#ef4444' : GREEN;
  return (
    <TouchableOpacity style={st.fileChip} onPress={open} testID={`artifact-${a.type}`}>
      <Ionicons name={icon as any} size={20} color={color} />
      <View style={{ flex: 1 }}>
        <Text style={st.fileName} numberOfLines={1}>{a.filename || a.title || a.type}</Text>
        <Text style={st.fileMeta}>{a.type.toUpperCase()} · tap to save</Text>
      </View>
      <Ionicons name="download-outline" size={18} color={MUTE} />
    </TouchableOpacity>
  );
}

export default function JeevesChat() {
  const router = useRouter();
  const [sid, setSid] = React.useState<string | null>(null);
  const [msgs, setMsgs] = React.useState<Msg[]>([{
    role: 'jeeves', tier: 'local',
    text: "I'm Jeeves. Ask me anything about your game build — I can reply in text, charts, graphs, visuals, PDFs and spreadsheets, all at once. Try: \"give me everything about the fire dragon boss\".",
  }]);
  const [input, setInput] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [attach, setAttach] = React.useState<any>(null);
  const [allForms, setAllForms] = React.useState(false);
  const scrollRef = React.useRef<ScrollView>(null);

  const send = async () => {
    if ((!input.trim() && !attach) || busy) return;
    const userText = input.trim() || (attach ? `Analyze this ${attach.modality}` : '');
    setMsgs((m) => [...m, { role: 'user', text: userText, forms: attach ? [attach.modality] : undefined }]);
    setInput(''); setBusy(true);
    const body: any = { message: userText, force_all_forms: allForms };
    if (sid) body.session_id = sid;
    if (attach?.modality === 'image') body.image_base64 = attach.base64;
    if (attach?.modality === 'pdf') body.pdf_base64 = attach.base64;
    setAttach(null);
    const r = await api.post<any>('/api/jeeves/chat', body, { timeoutMs: 60000 });
    if (r.ok) {
      if (!sid) setSid(r.data.session_id);
      setMsgs((m) => [...m, { role: 'jeeves', text: r.data.reply, tier: r.data.tier,
        artifacts: r.data.artifacts || [], forms: r.data.forms }]);
    } else {
      setMsgs((m) => [...m, { role: 'jeeves', text: 'Jeeves could not respond right now.', tier: 'local' }]);
    }
    setBusy(false);
    setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 120);
  };

  const pickImage = async () => {
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) return;
      const res = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images, base64: true, quality: 0.6 });
      if (!res.canceled && res.assets?.[0]?.base64)
        setAttach({ modality: 'image', base64: res.assets[0].base64, name: 'image' });
    } catch { /* no-op */ }
  };

  const pickDoc = async () => {
    try {
      const res = await DocumentPicker.getDocumentAsync({ type: 'application/pdf', copyToCacheDirectory: true });
      if (res.canceled || !res.assets?.[0]) return;
      const a = res.assets[0];
      let b64 = '';
      if (Platform.OS === 'web') {
        const f = (a as any).file as File;
        const blob = f || await (await fetch(a.uri)).blob();
        b64 = await new Promise<string>((resolve) => {
          const rd = new FileReader(); rd.onload = () => resolve(String(rd.result).split(',')[1] || ''); rd.readAsDataURL(blob);
        });
      } else {
        b64 = await FileSystem.readAsStringAsync(a.uri, { encoding: 'base64' as any });
      }
      if (b64) setAttach({ modality: 'pdf', base64: b64, name: a.name || 'document.pdf' });
    } catch { /* no-op */ }
  };

  return (
    <SafeAreaView style={st.safe}>
      <View style={st.header}>
        <TouchableOpacity onPress={() => router.back()} testID="back-btn">
          <Ionicons name="chevron-back" size={26} color={FG} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={st.title}>Jeeves</Text>
          <Text style={st.sub}>SOTA multi-format · free-tier cascade</Text>
        </View>
        <TouchableOpacity onPress={() => setAllForms((v) => !v)} testID="all-forms-toggle"
          style={[st.allBtn, allForms && { backgroundColor: PURPLE }]}>
          <Text style={[st.allTxt, allForms && { color: '#fff' }]}>ALL FORMS</Text>
        </TouchableOpacity>
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView ref={scrollRef} style={{ flex: 1 }} contentContainerStyle={{ padding: 12, paddingBottom: 20 }}>
          {msgs.map((m, i) => (
            <View key={i} style={[st.row, m.role === 'user' ? st.rowUser : st.rowJeeves]}>
              <View style={[st.bubble, m.role === 'user' ? st.bubbleUser : st.bubbleJeeves]}>
                {m.role === 'jeeves' && <TierBadge tier={m.tier} />}
                <Text style={m.role === 'user' ? st.txtUser : st.txtJeeves}>{m.text}</Text>
                {(m.artifacts || []).map((a, j) => <ArtifactView key={j} a={a} />)}
                {m.role === 'jeeves' && (m.artifacts?.length || 0) > 0 && (
                  <Text style={st.formsMeta}>{m.artifacts!.length} artifact(s) · {(m.forms || []).join(' · ')}</Text>
                )}
              </View>
            </View>
          ))}
          {busy && (
            <View style={[st.row, st.rowJeeves]}>
              <View style={[st.bubble, st.bubbleJeeves, { flexDirection: 'row', gap: 8 }]}>
                <ActivityIndicator size="small" color={PURPLE} />
                <Text style={st.txtJeeves}>Jeeves is composing…</Text>
              </View>
            </View>
          )}
        </ScrollView>

        {attach && (
          <View style={st.attachRow}>
            <Ionicons name="attach" size={14} color={GREEN} />
            <Text style={[st.fileMeta, { color: GREEN, flex: 1 }]} numberOfLines={1}>{attach.modality.toUpperCase()} · {attach.name}</Text>
            <TouchableOpacity onPress={() => setAttach(null)}><Ionicons name="close-circle" size={16} color={MUTE} /></TouchableOpacity>
          </View>
        )}
        <View style={st.inputBar}>
          <TouchableOpacity onPress={pickImage} style={st.iconBtn} testID="chat-attach-image"><Ionicons name="image-outline" size={20} color={AMBER} /></TouchableOpacity>
          <TouchableOpacity onPress={pickDoc} style={st.iconBtn} testID="chat-attach-doc"><Ionicons name="document-attach-outline" size={20} color={AMBER} /></TouchableOpacity>
          <TextInput style={st.input} value={input} onChangeText={setInput} testID="chat-input"
            placeholder="Ask Jeeves…" placeholderTextColor={MUTE} multiline onSubmitEditing={send} />
          <TouchableOpacity onPress={send} disabled={busy} style={[st.sendBtn, busy && { opacity: 0.5 }]} testID="chat-send">
            <Ionicons name="send" size={18} color="#0b1220" />
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  safe: { flex: 1, backgroundColor: BG },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 12, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1f2937' },
  title: { color: FG, fontSize: 18, fontWeight: '800' },
  sub: { color: MUTE, fontSize: 11 },
  allBtn: { borderColor: PURPLE, borderWidth: 1, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 },
  allTxt: { color: PURPLE, fontSize: 11, fontWeight: '700' },
  row: { marginBottom: 12, flexDirection: 'row' },
  rowUser: { justifyContent: 'flex-end' },
  rowJeeves: { justifyContent: 'flex-start' },
  bubble: { maxWidth: '88%', borderRadius: 14, padding: 12 },
  bubbleUser: { backgroundColor: PURPLE },
  bubbleJeeves: { backgroundColor: CARD, borderColor: '#1f2937', borderWidth: 1 },
  txtUser: { color: '#fff', fontSize: 14, lineHeight: 20 },
  txtJeeves: { color: FG, fontSize: 14, lineHeight: 20 },
  badge: { flexDirection: 'row', alignItems: 'center', gap: 4, alignSelf: 'flex-start', borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2, marginBottom: 6 },
  badgeTxt: { fontSize: 10, fontWeight: '700' },
  formsMeta: { color: MUTE, fontSize: 10, marginTop: 8 },
  artCard: { marginTop: 10, backgroundColor: BG, borderRadius: 10, padding: 8 },
  artLabel: { color: MUTE, fontSize: 10, marginBottom: 6, fontWeight: '700' },
  artImg: { width: '100%', height: 170, borderRadius: 6, backgroundColor: BG },
  fileChip: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 10, backgroundColor: BG, borderRadius: 10, padding: 10 },
  fileName: { color: FG, fontSize: 13, fontWeight: '600' },
  fileMeta: { color: MUTE, fontSize: 11 },
  attachRow: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 6 },
  inputBar: { flexDirection: 'row', alignItems: 'flex-end', gap: 6, padding: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#1f2937' },
  iconBtn: { width: 38, height: 40, alignItems: 'center', justifyContent: 'center' },
  input: { flex: 1, maxHeight: 120, backgroundColor: CARD, borderColor: '#334155', borderWidth: 1, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, color: FG, fontSize: 14 },
  sendBtn: { backgroundColor: GREEN, width: 44, height: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
});
