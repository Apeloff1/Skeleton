import React, { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import {
  ActivityIndicator, Alert, Image, KeyboardAvoidingView, Modal, Platform, SafeAreaView,
  ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View, useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Clipboard from 'expo-clipboard';
import * as ImagePicker from 'expo-image-picker';
import * as DocumentPicker from 'expo-document-picker';
import * as FileSystem from 'expo-file-system/legacy';
import api from '../../src/utils/apiClient';
import { WorkspaceController } from './WorkspaceController';
import MessageContent from './MessageContent';
import type { ChatHistoryResponse, ChatResponse } from './WorkspaceController';
import { MAX_CONTEXT, MAX_TEXT, searchConversations } from './workspace';
import type { Artifact, Attachment, Conversation, Message } from './workspace';
import { exportTranscript, MAX_ATTACHMENT_BYTES, saveArtifact, validateAttachment } from './chatFiles';
import { consumeHandoff } from './workbench/handoff';
import CaptureEditor from './workbench/CaptureEditor';
import { captureInput } from './workbench/capture';
import type { CaptureInput } from './workbench/capture';

const C = { bg: '#0b1220', card: '#111a2e', edge: '#28364e', text: '#e2e8f0', muted: '#94a3b8', purple: '#a78bfa', green: '#86efac', red: '#fca5a5' };
type Icon = keyof typeof Ionicons.glyphMap;
const STARTERS: { icon: Icon; title: string; detail: string; prompt: string }[] = [
  { icon: 'map-outline', title: 'Plan a game', detail: 'Turn an idea into achievable milestones.', prompt: 'Help me plan a small playable game. First ask about my game idea, engine, experience and time budget.' },
  { icon: 'bug-outline', title: 'Debug together', detail: 'Work through a problem step by step.', prompt: 'Help me debug a problem. Ask me for the error, relevant code, expected behavior and what I already tried.' },
  { icon: 'school-outline', title: 'Learn a concept', detail: 'Build understanding with a worked example.', prompt: 'Teach me a game development concept. Ask about my current level and what I want to understand, then give me a small practice task.' },
  { icon: 'git-compare-outline', title: 'Review a design', detail: 'Explore tradeoffs before building.', prompt: 'Review my game design. Ask for the core loop, audience and constraints, then identify risks and a small prototype to test the idea.' },
];

function Button({ icon, label, onPress, disabled = false, selected = false }: {
  icon: Icon; label: string; onPress: () => void; disabled?: boolean; selected?: boolean;
}) {
  return <TouchableOpacity onPress={onPress} disabled={disabled} accessibilityRole="button"
    accessibilityLabel={label} accessibilityState={{ disabled, selected }}
    style={[s.button, selected && s.selected, disabled && s.disabled]}>
    <Ionicons name={icon} size={17} color={selected ? C.purple : C.text} />
    <Text style={s.buttonText}>{label}</Text>
  </TouchableOpacity>;
}

function ArtifactCard({ artifact, notify }: { artifact: Artifact; notify: (message: string) => void }) {
  const image = ['image/png', 'image/jpeg', 'image/webp'].includes(artifact.mime);
  return <View style={s.artifact}>
    <Text style={s.label}>{artifact.title || artifact.filename || artifact.type}</Text>
    {image && <Image source={{ uri: `data:${artifact.mime};base64,${artifact.base64}` }} style={s.artifactImage} resizeMode="contain" accessibilityLabel={artifact.title || 'Generated image'} />}
    <Button icon="download-outline" label="Save file" onPress={() => {
      void saveArtifact(artifact).catch(error => notify(error instanceof Error ? error.message : 'Could not save this file.'));
    }} />
  </View>;
}

function MessageCard({ message, controller, busy }: { message: Message; controller: WorkspaceController; busy: boolean }) {
  const [capture, setCapture] = useState<CaptureInput | null>(null);
  const user = message.role === 'user';
  const failed = message.status === 'failed' || message.status === 'cancelled';
  return <View style={[s.messageRow, user && s.userRow]}>
    <View style={[s.message, user && s.userMessage]}>
      <View style={s.row}>
        <Ionicons name={user ? 'person-outline' : 'sparkles-outline'} color={user ? C.text : C.purple} size={15} />
        <Text style={s.messageAuthor}>{user ? 'You' : 'Jeeves'}</Text>
        <Text style={s.small}>{new Date(message.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</Text>
      </View>
      {!user && message.model && <Text style={s.metadata}>{message.model}{message.tier ? ` · ${message.tier}` : ''}</Text>}
      <MessageContent text={message.text} notify={controller.notify} />
      {message.attachmentName && <Text style={s.metadata}>Attachment · {message.attachmentName}</Text>}
      {(message.artifacts || []).map((artifact, i) => <ArtifactCard key={`${artifact.type}-${i}`} artifact={artifact} notify={controller.notify} />)}
      {!message.artifacts?.length && !!message.artifactCount && <Text style={s.metadata}>{message.artifactCount} artifact(s) from an earlier visit. File contents are not stored locally.</Text>}
      <View style={s.messageActions}>
        <Button icon="copy-outline" label="Copy" onPress={() => {
          void Clipboard.setStringAsync(message.text).then(() => controller.notify('Message copied.')).catch(() => controller.notify('Clipboard is unavailable. Select the message text to copy it.'));
        }} />
        {failed && <Button icon="refresh-outline" label="Retry" disabled={busy} onPress={() => { void controller.retry(message.id); }} />}
        {message.status === 'complete' && !!message.text.trim() && <Button icon="book-outline" label="Save note" onPress={() => setCapture(captureInput(controller.active, message, ''))} />}
      </View>
      {failed && <Text accessibilityRole="alert" style={s.error}>{message.error || 'Reply was not delivered.'}</Text>}
      {capture && <CaptureEditor input={capture} close={() => setCapture(null)} />}
    </View>
  </View>;
}

function Library({ controller, close }: { controller: WorkspaceController; close: () => void }) {
  const snapshot = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const [query, setQuery] = useState('');
  const [archived, setArchived] = useState(false);
  const chats = searchConversations(snapshot.workspace, query, archived);
  const remove = (conversation: Conversation) => {
    const action = () => controller.remove(conversation.id);
    const question = `Delete "${conversation.title}" from this device? Export it first if you want to keep a copy.`;
    if (Platform.OS === 'web') { if (globalThis.confirm(question)) action(); }
    else Alert.alert('Delete conversation?', question, [{ text: 'Cancel', style: 'cancel' }, { text: 'Delete', style: 'destructive', onPress: action }]);
  };
  return <View style={s.library}>
    <View style={s.sectionHeader}><Text style={s.sectionTitle}>Conversations</Text><Button icon="close" label="Close" onPress={close} /></View>
    <Button icon="add-outline" label="New conversation" onPress={() => { controller.create(); close(); }} />
    <TextInput value={query} onChangeText={setQuery} placeholder="Search titles and messages" placeholderTextColor={C.muted} style={s.field} accessibilityLabel="Search conversations" />
    <View style={s.row}>
      <Button icon="chatbubbles-outline" label="Active" selected={!archived} onPress={() => setArchived(false)} />
      <Button icon="archive-outline" label="Archived" selected={archived} onPress={() => setArchived(true)} />
    </View>
    <Text style={s.small}>{snapshot.workspace.conversations.length} / 30 saved on this device</Text>
    <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={s.libraryList}>
      {!chats.length && <Text style={s.emptyText}>{query ? 'No matching conversations.' : 'No conversations here yet.'}</Text>}
      {chats.map(conversation => <View key={conversation.id} style={[s.chatItem, conversation.id === snapshot.workspace.activeId && s.selected]}>
        <TouchableOpacity onPress={() => { controller.select(conversation.id); close(); }} accessibilityRole="button" accessibilityLabel={`Open ${conversation.title}`} style={s.chatItemMain}>
          <Text numberOfLines={2} style={s.chatTitle}>{conversation.pinned ? '★ ' : ''}{conversation.title}</Text>
          <Text style={s.small}>{conversation.messages.length} messages · {new Date(conversation.updatedAt).toLocaleDateString()}</Text>
          <Text numberOfLines={2} style={s.chatPreview}>{conversation.draft ? `Draft: ${conversation.draft}` : conversation.messages.at(-1)?.text || 'Ready for your first question'}</Text>
        </TouchableOpacity>
        <View style={s.row}>
          <Button icon={archived ? 'arrow-undo-outline' : 'archive-outline'} label={archived ? 'Restore' : 'Archive'} onPress={() => controller.archive(conversation.id, !archived)} />
          <Button icon="trash-outline" label="Delete" onPress={() => remove(conversation)} />
        </View>
      </View>)}
    </ScrollView>
    <Text style={s.small}>The server owns conversation history. Drafts and a rebuildable cache stay on this device; attachments last only for this visit.</Text>
  </View>;
}

export default function ChatWorkspace() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const [controller] = useState(() => new WorkspaceController(
    AsyncStorage,
    async (body, signal) => {
      const result = await api.post<ChatResponse>(
        '/api/jeeves/chat',
        body,
        { signal, timeoutMs: 60000, retries: 0 },
      );
      if (!result.ok || !result.data) {
        const message = result.status === 429 ? 'Jeeves is busy. Wait a moment and retry.'
          : result.status === 408 ? 'Jeeves took too long to answer. Try again.'
            : result.status >= 500 ? 'Jeeves is temporarily unavailable on the server.'
              : result.status === 413 ? 'This attachment is too large.'
                : result.status === 422 ? 'Jeeves could not accept this message. Check its length and attachments.'
                  : 'The connection to Jeeves was interrupted. Check your connection and retry.';
        throw new Error(message);
      }
      return result.data;
    },
    async sessionId => {
      const result = await api.get<ChatHistoryResponse>(
        '/api/jeeves/chat/' + encodeURIComponent(sessionId) + '?limit=50',
        { timeoutMs: 20000, retries: 1 },
      );
      if (!result.ok || !result.data) {
        throw new Error('Canonical Jeeves history is unavailable.');
      }
      return result.data;
    },
  ));
  const snapshot = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const conversation = controller.active;
  const busy = snapshot.busyId !== null;
  const [library, setLibrary] = useState(false);
  const [settings, setSettings] = useState(false);
  const [title, setTitle] = useState('');
  const [context, setContext] = useState('');
  const [attachment, setAttachment] = useState<Attachment | undefined>();
  const [picking, setPicking] = useState(false);
  const scroll = useRef<React.ElementRef<typeof ScrollView>>(null);
  const pickerGeneration = useRef(0);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    void controller.initialize();
    return () => { mounted.current = false; pickerGeneration.current++; controller.cancel(); };
  }, [controller]);

  useEffect(() => { setAttachment(undefined); pickerGeneration.current++; setPicking(false); }, [conversation.id]);
  useFocusEffect(React.useCallback(() => {
    if (snapshot.ready) {
      void consumeHandoff(AsyncStorage, controller);
      void controller.refreshCanonical();
    }
  }, [controller, snapshot.ready]));
  useEffect(() => {
    const timer = setTimeout(() => {
      if (conversation.messages.length) scroll.current?.scrollToEnd({ animated: true });
      else scroll.current?.scrollTo({ y: 0, animated: false });
    }, 80);
    return () => clearTimeout(timer);
  }, [conversation.id, conversation.messages.length, busy]);

  const storageLabel = useMemo(() => ({ loading: 'Opening chat cache…', saving: 'Caching…', saved: 'Synced · cache saved', error: 'Cache not saved' })[snapshot.saveState], [snapshot.saveState]);

  const pick = async (kind: 'image' | 'pdf') => {
    if (picking || busy) return;
    const generation = ++pickerGeneration.current;
    setPicking(true);
    try {
      let next: Attachment | undefined;
      if (kind === 'image') {
        const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
        if (!permission.granted) { controller.notify('Allow photo access in device settings to attach an image.'); return; }
        const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], base64: true, quality: 0.6 });
        const asset = !result.canceled ? result.assets[0] : null;
        if (asset?.base64) next = { modality: 'image', base64: asset.base64, name: asset.fileName || 'image.jpg' };
      } else {
        const result = await DocumentPicker.getDocumentAsync({ type: 'application/pdf', copyToCacheDirectory: true });
        const asset = !result.canceled ? result.assets[0] : null;
        if (asset) {
          if ((asset.size || 0) > MAX_ATTACHMENT_BYTES) throw new Error('Choose a PDF smaller than 5 MB.');
          let base64: string;
          if (Platform.OS === 'web') {
            const blob = asset.file || await (await fetch(asset.uri)).blob();
            if (blob.size > MAX_ATTACHMENT_BYTES) throw new Error('Choose a PDF smaller than 5 MB.');
            base64 = await new Promise<string>((resolve, reject) => {
              const reader = new FileReader();
              reader.onload = () => resolve(String(reader.result).split(',')[1] || '');
              reader.onerror = () => reject(new Error('Could not read the PDF.'));
              reader.onabort = () => reject(new Error('Reading the PDF was cancelled.'));
              reader.readAsDataURL(blob);
            });
          } else base64 = await FileSystem.readAsStringAsync(asset.uri, { encoding: FileSystem.EncodingType.Base64 });
          next = { modality: 'pdf', base64, name: asset.name || 'document.pdf' };
        }
      }
      if (next) validateAttachment(next.base64);
      if (mounted.current && pickerGeneration.current === generation && next) setAttachment(next);
    } catch (error) {
      if (mounted.current && pickerGeneration.current === generation) controller.notify(error instanceof Error ? error.message : 'Could not open this attachment.');
    } finally {
      if (mounted.current && pickerGeneration.current === generation) setPicking(false);
    }
  };

  const send = () => {
    if (!snapshot.ready || busy || picking || (!conversation.draft.trim() && !attachment)) return;
    const pending = controller.send(attachment);
    // A full conversation is rejected before its draft is cleared.
    if (!controller.active.draft) setAttachment(undefined);
    void pending;
  };

  return <SafeAreaView style={s.safe}>
    <View style={s.header}>
      <TouchableOpacity onPress={() => router.back()} accessibilityLabel="Back" accessibilityRole="button" style={s.back} testID="back-btn"><Ionicons name="chevron-back" size={24} color={C.text} /></TouchableOpacity>
      <View style={s.brand}><Text style={s.brandTitle}>Jeeves</Text><Text style={s.small}>{storageLabel}</Text></View>
      <Button icon="chatbubbles-outline" label={width > 600 ? 'Conversations' : 'Chats'} onPress={() => setLibrary(true)} disabled={!snapshot.ready} />
      <Button icon="folder-outline" label="Workbench" onPress={() => router.push('/jeeves-workbench')} />
      {width > 650 && <Button icon="add-outline" label="New chat" onPress={() => controller.create()} disabled={!snapshot.ready} />}
    </View>
    {!snapshot.ready ? <View style={s.loading}>
      {snapshot.loadError ? <><Text accessibilityRole="alert" style={s.error}>{snapshot.loadError}</Text><Button icon="refresh-outline" label="Retry opening chats" onPress={() => { void controller.initialize(); }} /></> : <ActivityIndicator color={C.purple} />}
    </View> : <KeyboardAvoidingView style={s.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={s.chatToolbar}>
        <View style={s.flex}><Text numberOfLines={1} style={s.chatTitle}>{conversation.title}</Text><Text style={s.small}>{conversation.messages.length} / 100 messages{conversation.context ? ' · Project context attached' : ''}</Text></View>
        <Button icon={conversation.pinned ? 'star' : 'star-outline'} label="Pin" selected={conversation.pinned} onPress={() => controller.edit({ pinned: !conversation.pinned })} />
        <Button icon="options-outline" label="Details" onPress={() => { setTitle(conversation.title); setContext(conversation.context); setSettings(true); }} />
      </View>
      {(snapshot.notice || snapshot.saveState === 'error') && <View style={s.notice} accessibilityRole="alert">
        <Text style={[s.small, s.flex]}>{snapshot.notice || 'Changes could not be saved to this device.'}</Text>
        {snapshot.saveState === 'error' ? <Button icon="refresh-outline" label="Save again" onPress={controller.retrySave} /> : <TouchableOpacity accessibilityLabel="Dismiss notice" onPress={controller.dismissNotice}><Ionicons name="close" size={20} color={C.text} /></TouchableOpacity>}
      </View>}
      <ScrollView ref={scroll} style={s.flex} contentContainerStyle={s.transcript} keyboardShouldPersistTaps="handled" testID="jeeves-transcript">
        {!conversation.messages.length && <View style={s.welcome}>
          <View style={s.crest}><Ionicons name="sparkles-outline" size={34} color={C.purple} /></View>
          <Text style={s.welcomeTitle}>What shall we work on?</Text>
          <Text style={s.welcomeSubtitle}>Your companion for building, debugging and learning. Give Jeeves a goal and a little context to get started.</Text>
          <View style={s.starters}>{STARTERS.map(starter => <TouchableOpacity key={starter.title} style={[s.starter, { width: width > 600 ? '48%' : '100%' }]} accessibilityRole="button" onPress={() => controller.edit({ draft: starter.prompt })}>
            <Ionicons name={starter.icon} color={C.purple} size={23} /><Text style={s.chatTitle}>{starter.title}</Text><Text style={s.small}>{starter.detail}</Text>
          </TouchableOpacity>)}</View>
          <Text style={s.emptyText}>Responses use the server’s configured provider and available knowledge. Local extractive responses may be limited.</Text>
        </View>}
        {conversation.messages.map(message => <MessageCard key={message.id} message={message} controller={controller} busy={busy} />)}
        {busy && <View style={s.composing}><ActivityIndicator color={C.purple} /><Text style={s.small}>Jeeves is composing…</Text><Button icon="stop-outline" label="Stop" onPress={controller.cancel} /></View>}
      </ScrollView>
      <View style={s.composer}>
        {attachment && <View style={s.row}><Ionicons name="attach" color={C.green} size={18} /><Text numberOfLines={1} style={[s.small, s.flex]}>{attachment.name}</Text><Button icon="close" label="Remove" onPress={() => setAttachment(undefined)} /></View>}
        <TextInput value={conversation.draft} onChangeText={draft => controller.edit({ draft })} style={s.composerInput} multiline maxLength={MAX_TEXT}
          placeholder="Ask Jeeves about your next step…" placeholderTextColor={C.muted} accessibilityLabel="Message Jeeves" testID="chat-input" />
        <View style={s.composerActions}>
          <Button icon="image-outline" label="Image" disabled={busy || picking} onPress={() => { void pick('image'); }} />
          <Button icon="document-attach-outline" label="PDF" disabled={busy || picking} onPress={() => { void pick('pdf'); }} />
          <Button icon="layers-outline" label="All forms" selected={conversation.allForms} onPress={() => controller.edit({ allForms: !conversation.allForms })} />
          <View style={s.flex} />
          <TouchableOpacity onPress={send} disabled={busy || picking || (!conversation.draft.trim() && !attachment)} style={[s.send, (busy || picking || (!conversation.draft.trim() && !attachment)) && s.disabled]} accessibilityRole="button" accessibilityLabel="Send message" testID="chat-send"><Ionicons name="arrow-up" size={22} color={C.bg} /></TouchableOpacity>
        </View>
        <Text style={s.composerHint}>{picking ? 'Reading attachment…' : `${conversation.draft.length.toLocaleString()} / 16,000 · Attachments up to 5 MB`}</Text>
      </View>
    </KeyboardAvoidingView>}
    <Modal visible={library} animationType="slide" onRequestClose={() => setLibrary(false)}><SafeAreaView style={s.safe}><Library controller={controller} close={() => setLibrary(false)} /></SafeAreaView></Modal>
    <Modal visible={settings} animationType="slide" onRequestClose={() => setSettings(false)}><SafeAreaView style={s.safe}><ScrollView contentContainerStyle={s.details} keyboardShouldPersistTaps="handled">
      <View style={s.sectionHeader}><Text style={s.sectionTitle}>Conversation details</Text><Button icon="close" label="Cancel" onPress={() => setSettings(false)} /></View>
      <Text style={s.label}>Title</Text><TextInput value={title} onChangeText={setTitle} maxLength={100} style={s.field} accessibilityLabel="Conversation title" />
      <Text style={s.label}>Project context</Text><Text style={s.small}>Describe your engine, goals, experience and constraints. This text is sent with each message in this conversation.</Text>
      <TextInput value={context} onChangeText={setContext} maxLength={MAX_CONTEXT} multiline style={[s.field, s.contextField]} placeholder="Godot 4 · first 2D platformer · beginner · one weekend" placeholderTextColor={C.muted} accessibilityLabel="Project context" />
      <Text style={s.small}>{context.length} / {MAX_CONTEXT}</Text>
      <Button icon="checkmark-outline" label="Save details" onPress={() => { controller.edit({ title, context }); setSettings(false); }} />
      <View style={s.divider} /><Text style={s.label}>Keep a copy</Text><Text style={s.small}>Export a Markdown transcript. Attachment and generated file contents are excluded.</Text>
      <Button icon="download-outline" label="Export transcript" onPress={() => { void exportTranscript(conversation).catch(() => controller.notify('Could not export the transcript. Try copying individual messages.')); }} />
      <Text style={s.small}>Chats are stored on this device, without account synchronization. Server history depends on backend availability.</Text>
    </ScrollView></SafeAreaView></Modal>
  </SafeAreaView>;
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg }, flex: { flex: 1 }, disabled: { opacity: 0.4 },
  header: { flexDirection: 'row', alignItems: 'center', padding: 14, gap: 12, borderBottomWidth: 1, borderColor: C.edge },
  back: { padding: 7 }, brand: { flex: 1 }, brandTitle: { fontSize: 22, fontWeight: '800', color: C.text },
  small: { color: C.muted, fontSize: 12, lineHeight: 18 }, row: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  button: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 10, borderWidth: 1, borderColor: C.edge, borderRadius: 9, minHeight: 40 },
  buttonText: { color: C.text, fontSize: 12, fontWeight: '600' }, selected: { backgroundColor: '#292042', borderColor: '#6d52a4' },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 20, padding: 32 },
  chatToolbar: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 18, paddingVertical: 12, gap: 8, borderBottomWidth: 1, borderColor: C.edge },
  chatTitle: { color: C.text, fontSize: 15, fontWeight: '700', lineHeight: 21 },
  notice: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#26223c', padding: 12 },
  transcript: { padding: 18, paddingBottom: 30, width: '100%', maxWidth: 960, alignSelf: 'center', flexGrow: 1 },
  welcome: { alignItems: 'center', justifyContent: 'center', paddingVertical: 30, gap: 16 },
  crest: { padding: 20, backgroundColor: '#241c38', borderRadius: 24, borderWidth: 1, borderColor: '#463362' },
  welcomeTitle: { fontSize: 28, fontWeight: '700', color: C.text, textAlign: 'center' },
  welcomeSubtitle: { color: C.muted, fontSize: 15, lineHeight: 23, maxWidth: 520, textAlign: 'center' },
  starters: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, maxWidth: 650, width: '100%', marginTop: 12 },
  starter: { backgroundColor: C.card, borderWidth: 1, borderColor: C.edge, borderRadius: 14, padding: 18, gap: 8 },
  emptyText: { color: C.muted, fontSize: 12, textAlign: 'center', padding: 18, maxWidth: 600, lineHeight: 19 },
  messageRow: { alignItems: 'flex-start', marginBottom: 18 }, userRow: { alignItems: 'flex-end' },
  message: { maxWidth: '94%', minWidth: 170, backgroundColor: C.card, borderColor: C.edge, borderWidth: 1, padding: 16, borderRadius: 16, gap: 10 },
  userMessage: { backgroundColor: '#28203f', borderColor: '#493568' }, messageAuthor: { color: C.text, fontWeight: '700', fontSize: 12, flex: 1 },
  messageText: { color: C.text, fontSize: 15, lineHeight: 23 }, metadata: { color: C.muted, fontSize: 11, lineHeight: 17 },
  messageActions: { flexDirection: 'row', gap: 8, marginTop: 4 }, error: { color: C.red, fontSize: 13, lineHeight: 20 },
  artifact: { padding: 12, backgroundColor: C.bg, borderWidth: 1, borderColor: C.edge, borderRadius: 12, gap: 10 },
  artifactImage: { width: '100%', minWidth: 210, height: 210 }, composing: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 10 },
  composer: { marginHorizontal: 14, marginBottom: 10, padding: 12, backgroundColor: C.card, borderWidth: 1, borderColor: C.edge, borderRadius: 18, gap: 8 },
  composerInput: { color: C.text, fontSize: 15, lineHeight: 22, padding: 8, minHeight: 54, maxHeight: 160, textAlignVertical: 'top' },
  composerActions: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 6 }, send: { backgroundColor: C.green, width: 42, height: 42, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  composerHint: { color: C.muted, fontSize: 10, paddingHorizontal: 5 },
  library: { flex: 1, padding: 20, gap: 14, maxWidth: 800, width: '100%', alignSelf: 'center' },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 }, sectionTitle: { color: C.text, fontSize: 20, fontWeight: '700', flex: 1 },
  field: { color: C.text, padding: 14, backgroundColor: C.card, borderColor: C.edge, borderWidth: 1, borderRadius: 10, fontSize: 14 },
  libraryList: { gap: 12, paddingBottom: 24 }, chatItem: { borderWidth: 1, borderColor: C.edge, borderRadius: 14, padding: 14, gap: 12, backgroundColor: C.card },
  chatItemMain: { gap: 6 }, chatPreview: { color: C.muted, fontSize: 13, lineHeight: 19 },
  details: { padding: 24, gap: 16, maxWidth: 760, width: '100%', alignSelf: 'center' }, label: { color: C.text, fontSize: 14, fontWeight: '700' },
  contextField: { minHeight: 160, textAlignVertical: 'top' }, divider: { height: 1, backgroundColor: C.edge, marginVertical: 10 },
});
