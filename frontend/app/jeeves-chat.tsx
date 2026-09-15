/**
 * /jeeves-chat — SOTA 2026 Jeeves chat.
 * Free-tier-cascade backed conversation where Jeeves can reply in MANY forms in
 * a single parse: text + charts + graph + visual + PDF + spreadsheet. Supports
 * multimodal attach (image / PDF) and renders artifacts inline.
 *
 * Resilience guarantees:
 *   • Text conversation, draft and active session survive route/app remounts.
 *   • Large base64 artifacts/attachments are deliberately never persisted.
 *   • Failed requests remain retryable without duplicating the user's message.
 *   • In-flight work is aborted when the screen unmounts or conversation clears.
 */
import React from 'react';
import {
  View, Text, StyleSheet, SafeAreaView, ScrollView, TouchableOpacity,
  ActivityIndicator, TextInput, Image, KeyboardAvoidingView, Platform, Linking, Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import api from '../src/utils/apiClient';

const BG = '#0b1220';
const CARD = '#111a2e';
const PURPLE = '#7c3aed';
const GREEN = '#22c55e';
const AMBER = '#f59e0b';
const RED = '#ef4444';
const MUTE = '#64748b';
const FG = '#e2e8f0';

const CHAT_STATE_KEY = '@tutolage/jeeves-chat:v2';
const MAX_PERSISTED_MESSAGES = 40;
const SESSION_TTL_MS = 6 * 60 * 60 * 1000;
const SAVE_DEBOUNCE_MS = 250;

const WELCOME_TEXT = "I'm Jeeves. Ask me anything about your game build — I can reply in text, charts, graphs, visuals, PDFs and spreadsheets, all at once. Try: \"give me everything about the fire dragon boss\".";

type Artifact = { type: string; kind?: string; title?: string; mime: string; base64: string; filename?: string };
type Msg = { role: 'user' | 'jeeves'; text: string; tier?: string; artifacts?: Artifact[]; forms?: string[] };
type PersistedMsg = Omit<Msg, 'artifacts'>;
type JeevesResponse = { session_id?: string; reply?: string; tier?: string; artifacts?: Artifact[]; forms?: string[] };
type FailedRequest = { body: Record<string, unknown>; error: string };
type PersistedState = {
  version: 2;
  messages: PersistedMsg[];
  draft: string;
  allForms: boolean;
  sessionId: string | null;
  sessionUpdatedAt: number;
};

const welcomeMessage = (): Msg => ({ role: 'jeeves', tier: 'local', text: WELCOME_TEXT });

function textOnlyHistory(messages: Msg[]): PersistedMsg[] {
  return messages.slice(-MAX_PERSISTED_MESSAGES).map(({ artifacts: _artifacts, ...message }) => message);
}

function readableError(error: string | null, status: number): string {
  if (error === 'circuit_open') return 'Jeeves is temporarily protecting an unhealthy connection. Try again shortly.';
  if (error === 'network_error') return 'The connection to Jeeves was interrupted.';
  if (status === 408 || /timeout/i.test(error || '')) return 'Jeeves took too long to answer.';
  if (status >= 500) return 'Jeeves is temporarily unavailable on the server.';
  if (status === 429) return 'Jeeves is receiving too many requests. Try again shortly.';
  if (status >= 400 && status < 500) return error || `Jeeves rejected the request (${status}).`;
  return error || 'Jeeves could not respond right now.';
}

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
      if (w) {
        const link = w.document.createElement('a');
        link.href = uri;
        link.download = a.filename || 'jeeves-file';
        link.click();
      }
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
  const color = a.type === 'pdf' ? RED : GREEN;
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
  const [sessionUpdatedAt, setSessionUpdatedAt] = React.useState(0);
  const [msgs, setMsgs] = React.useState<Msg[]>([welcomeMessage()]);
  const [input, setInput] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [attach, setAttach] = React.useState<any>(null);
  const [allForms, setAllForms] = React.useState(false);
  const [hydrated, setHydrated] = React.useState(false);
  const [failed, setFailed] = React.useState<FailedRequest | null>(null);
  const scrollRef = React.useRef<ScrollView>(null);
  const abortRef = React.useRef<AbortController | null>(null);

  React.useEffect(() => {
    let active = true;
    const restore = async () => {
      try {
        const raw = await AsyncStorage.getItem(CHAT_STATE_KEY);
        if (!raw || !active) return;
        const saved = JSON.parse(raw) as Partial<PersistedState>;
        if (saved.version !== 2 || !Array.isArray(saved.messages)) return;
        const restored = saved.messages
          .filter((m): m is PersistedMsg => !!m && (m.role === 'user' || m.role === 'jeeves') && typeof m.text === 'string')
          .slice(-MAX_PERSISTED_MESSAGES);
        if (restored.length) setMsgs(restored);
        if (typeof saved.draft === 'string') setInput(saved.draft);
        if (typeof saved.allForms === 'boolean') setAllForms(saved.allForms);
        const updatedAt = typeof saved.sessionUpdatedAt === 'number' ? saved.sessionUpdatedAt : 0;
        if (saved.sessionId && Date.now() - updatedAt <= SESSION_TTL_MS) {
          setSid(saved.sessionId);
          setSessionUpdatedAt(updatedAt);
        }
      } catch {
        // A corrupt local snapshot must never block Jeeves from opening.
      } finally {
        if (active) setHydrated(true);
      }
    };
    restore();
    return () => {
      active = false;
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, []);

  React.useEffect(() => {
    if (!hydrated) return;
    const timer = setTimeout(() => {
      const snapshot: PersistedState = {
        version: 2,
        messages: textOnlyHistory(msgs),
        draft: input,
        allForms,
        sessionId: sid,
        sessionUpdatedAt,
      };
      AsyncStorage.setItem(CHAT_STATE_KEY, JSON.stringify(snapshot)).catch(() => {});
    }, SAVE_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [hydrated, msgs, input, allForms, sid, sessionUpdatedAt]);

  React.useEffect(() => {
    const timer = setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 80);
    return () => clearTimeout(timer);
  }, [msgs.length, busy, failed]);

  const runRequest = React.useCallback(async (body: Record<string, unknown>) => {
    setBusy(true);
    setFailed(null);
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    abortRef.current = controller;
    try {
      const r = await api.post<JeevesResponse>('/api/jeeves/chat', body, {
        timeoutMs: 60000,
        signal: controller?.signal,
      });
      // Clearing the conversation or leaving this route aborts the request.
      // Never let that intentional cancellation resurrect a stale error/reply.
      if (controller?.signal.aborted) return false;
      if (r.ok && r.data) {
        const newSid = r.data.session_id || (typeof body.session_id === 'string' ? body.session_id : null);
        if (newSid) setSid(newSid);
        setSessionUpdatedAt(Date.now());
        setMsgs((m) => [...m, {
          role: 'jeeves',
          text: r.data?.reply || 'Jeeves completed the request.',
          tier: r.data?.tier,
          artifacts: r.data?.artifacts || [],
          forms: r.data?.forms,
        }]);
        return true;
      }
      setFailed({ body: { ...body }, error: readableError(r.error, r.status) });
      return false;
    } catch (error: any) {
      if (!controller?.signal.aborted && error?.name !== 'AbortError') {
        setFailed({ body: { ...body }, error: 'The connection to Jeeves was interrupted.' });
      }
      return false;
    } finally {
      // Only the request that still owns the active controller may clear busy.
      // A cleared/aborted request must not race a newer request back to idle.
      if (abortRef.current === controller) {
        abortRef.current = null;
        setBusy(false);
      }
    }
  }, []);

  const send = async () => {
    if ((!input.trim() && !attach) || busy) return;
    const userText = input.trim() || (attach ? `Analyze this ${attach.modality}` : '');
    const currentAttachment = attach;
    setMsgs((m) => [...m, {
      role: 'user',
      text: userText,
      forms: currentAttachment ? [currentAttachment.modality] : undefined,
    }]);
    setInput('');
    setAttach(null);

    const body: Record<string, unknown> = { message: userText, force_all_forms: allForms };
    if (sid) body.session_id = sid;
    if (currentAttachment?.modality === 'image') body.image_base64 = currentAttachment.base64;
    if (currentAttachment?.modality === 'pdf') body.pdf_base64 = currentAttachment.base64;
    await runRequest(body);
  };

  const retryFailed = async () => {
    if (!failed || busy) return;
    const body = { ...failed.body };
    if (sid) body.session_id = sid;
    await runRequest(body);
  };

  const clearConversation = () => {
    const clear = () => {
      abortRef.current?.abort();
      abortRef.current = null;
      setBusy(false);
      setMsgs([welcomeMessage()]);
      setInput('');
      setAttach(null);
      setFailed(null);
      setSid(null);
      setSessionUpdatedAt(0);
      AsyncStorage.removeItem(CHAT_STATE_KEY).catch(() => {});
    };

    if (Platform.OS === 'web') {
      const w = (globalThis as any).window;
      if (!w?.confirm || w.confirm('Clear this Jeeves conversation and local draft?')) clear();
      return;
    }
    Alert.alert('Clear conversation?', 'This removes the saved Jeeves transcript and draft from this device.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Clear', style: 'destructive', onPress: clear },
    ]);
  };

  const pickImage = async () => {
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) return;
      const res = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images, base64: true, quality: 0.6,
      });
      if (!res.canceled && res.assets?.[0]?.base64) {
        setAttach({ modality: 'image', base64: res.assets[0].base64, name: 'image' });
      }
    } catch { /* picker cancellation/failure should not disrupt chat */ }
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
          const rd = new FileReader();
          rd.onload = () => resolve(String(rd.result).split(',')[1] || '');
          rd.readAsDataURL(blob);
        });
      } else {
        b64 = await FileSystem.readAsStringAsync(a.uri, { encoding: 'base64' as any });
      }
      if (b64) setAttach({ modality: 'pdf', base64: b64, name: a.name || 'document.pdf' });
    } catch { /* picker cancellation/failure should not disrupt chat */ }
  };

  const canSend = !!input.trim() || !!attach;

  return (
    <SafeAreaView style={st.safe}>
      <View style={st.header}>
        <TouchableOpacity onPress={() => router.back()} testID="back-btn" accessibilityLabel="Back">
          <Ionicons name="chevron-back" size={26} color={FG} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={st.title}>Jeeves</Text>
          <Text style={st.sub}>SOTA multi-format · free-tier cascade{hydrated ? ' · saved locally' : ''}</Text>
        </View>
        <TouchableOpacity onPress={clearConversation} style={st.headerIconBtn} testID="chat-clear"
          accessibilityLabel="Clear Jeeves conversation">
          <Ionicons name="trash-outline" size={18} color={MUTE} />
        </TouchableOpacity>
        <TouchableOpacity onPress={() => setAllForms((v) => !v)} testID="all-forms-toggle"
          style={[st.allBtn, allForms && { backgroundColor: PURPLE }]}
          accessibilityRole="button" accessibilityState={{ selected: allForms }}>
          <Text style={[st.allTxt, allForms && { color: '#fff' }]}>ALL FORMS</Text>
        </TouchableOpacity>
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView ref={scrollRef} style={{ flex: 1 }} contentContainerStyle={{ padding: 12, paddingBottom: 20 }}
          keyboardShouldPersistTaps="handled">
          {msgs.map((m, i) => (
            <View key={`${m.role}-${i}-${m.text.slice(0, 16)}`} style={[st.row, m.role === 'user' ? st.rowUser : st.rowJeeves]}>
              <View style={[st.bubble, m.role === 'user' ? st.bubbleUser : st.bubbleJeeves]}>
                {m.role === 'jeeves' && <TierBadge tier={m.tier} />}
                <Text style={m.role === 'user' ? st.txtUser : st.txtJeeves}>{m.text}</Text>
                {(m.artifacts || []).map((a, j) => <ArtifactView key={`${a.type}-${j}`} a={a} />)}
                {m.role === 'jeeves' && (m.artifacts?.length || 0) > 0 && (
                  <Text style={st.formsMeta}>{m.artifacts!.length} artifact(s) · {(m.forms || []).join(' · ')}</Text>
                )}
              </View>
            </View>
          ))}
          {busy && (
            <View style={[st.row, st.rowJeeves]}>
              <View style={[st.bubble, st.bubbleJeeves, st.composing]}>
                <ActivityIndicator size="small" color={PURPLE} />
                <Text style={st.txtJeeves}>Jeeves is composing…</Text>
              </View>
            </View>
          )}
          {failed && !busy && (
            <View style={[st.row, st.rowJeeves]} testID="chat-error">
              <View style={[st.bubble, st.errorBubble]}>
                <View style={st.errorTitleRow}>
                  <Ionicons name="warning-outline" size={16} color={RED} />
                  <Text style={st.errorTitle}>Reply not delivered</Text>
                </View>
                <Text style={st.errorText}>{failed.error}</Text>
                <TouchableOpacity onPress={retryFailed} style={st.retryBtn} testID="chat-retry">
                  <Ionicons name="refresh" size={15} color={FG} />
                  <Text style={st.retryText}>Retry reply</Text>
                </TouchableOpacity>
              </View>
            </View>
          )}
        </ScrollView>

        {attach && (
          <View style={st.attachRow}>
            <Ionicons name="attach" size={14} color={GREEN} />
            <Text style={[st.fileMeta, { color: GREEN, flex: 1 }]} numberOfLines={1}>{attach.modality.toUpperCase()} · {attach.name}</Text>
            <TouchableOpacity onPress={() => setAttach(null)} accessibilityLabel="Remove attachment">
              <Ionicons name="close-circle" size={16} color={MUTE} />
            </TouchableOpacity>
          </View>
        )}
        <View style={st.inputBar}>
          <TouchableOpacity onPress={pickImage} style={st.iconBtn} testID="chat-attach-image" accessibilityLabel="Attach image">
            <Ionicons name="image-outline" size={20} color={AMBER} />
          </TouchableOpacity>
          <TouchableOpacity onPress={pickDoc} style={st.iconBtn} testID="chat-attach-doc" accessibilityLabel="Attach PDF">
            <Ionicons name="document-attach-outline" size={20} color={AMBER} />
          </TouchableOpacity>
          <TextInput style={st.input} value={input} onChangeText={setInput} testID="chat-input"
            placeholder="Ask Jeeves…" placeholderTextColor={MUTE} multiline onSubmitEditing={send}
            accessibilityLabel="Message Jeeves" />
          <TouchableOpacity onPress={send} disabled={busy || !canSend}
            style={[st.sendBtn, (busy || !canSend) && st.disabled]} testID="chat-send" accessibilityLabel="Send message">
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
  headerIconBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
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
  composing: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  errorBubble: { backgroundColor: '#2a1218', borderColor: '#7f1d1d', borderWidth: 1 },
  errorTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 5 },
  errorTitle: { color: '#fecaca', fontSize: 13, fontWeight: '700' },
  errorText: { color: '#fca5a5', fontSize: 12, lineHeight: 18 },
  retryBtn: { marginTop: 10, alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#3f1d25', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 7 },
  retryText: { color: FG, fontSize: 12, fontWeight: '700' },
  attachRow: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 6 },
  inputBar: { flexDirection: 'row', alignItems: 'flex-end', gap: 6, padding: 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#1f2937' },
  iconBtn: { width: 38, height: 40, alignItems: 'center', justifyContent: 'center' },
  input: { flex: 1, maxHeight: 120, backgroundColor: CARD, borderColor: '#334155', borderWidth: 1, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 10, color: FG, fontSize: 14 },
  sendBtn: { backgroundColor: GREEN, width: 44, height: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  disabled: { opacity: 0.45 },
});
