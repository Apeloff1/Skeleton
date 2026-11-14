import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator, KeyboardAvoidingView, Modal, Platform, SafeAreaView,
  ScrollView, Text, TextInput, TouchableOpacity, View, useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Clipboard from 'expo-clipboard';
import * as DocumentPicker from 'expo-document-picker';
import { useChatController } from '../../src/product/useChatController';
import { getAuthToken } from '../../src/auth/gameforgeAuth';
import type { ConversationMessage, ConversationThread } from '../../src/product/governedConversationClient';
import { attachmentCapabilities, CHAT_ATTACHMENT_MIMES, deleteChatAttachment, readPickedAttachment, uploadChatAttachment } from './chatFiles';
import MessageContent from './MessageContent';
import JeevesRuntimeStatus from './JeevesRuntimeStatus';
import ChatTaskActions from './workbench/ChatTaskActions';
import ChatSceneActions from './ChatSceneActions';
import ChatStoryActions from './ChatStoryActions';
import DragonCompanionPanel from './companion/DragonCompanionPanel';
import DragonDemoPlayer from './companion/DragonDemoPlayer';
import { useDragonAcademy } from './companion/useDragonAcademy';
import ChatAttachments from './ChatAttachments';
import { saveChatExport } from './ChatExport';
import s, { colors as C } from './ChatWorkspace.styles';

const MAX_MESSAGE_LENGTH = 32000;
const ACCEPTED_FILES: string[] = [...CHAT_ATTACHMENT_MIMES];
const STARTERS: { icon: Icon; title: string; detail: string; prompt: string }[] = [
  { icon: 'bulb-outline', title: 'Explore an idea', detail: 'Find a practical way to get started.', prompt: 'Help me think through an idea. Ask me what I want to build and what constraints matter.' },
  { icon: 'code-slash-outline', title: 'Work through code', detail: 'Explain, improve, or debug a problem.', prompt: 'Help me work through a coding problem. Ask me for the code, what I expect, and what happens instead.' },
  { icon: 'school-outline', title: 'Learn something', detail: 'Build understanding, one step at a time.', prompt: 'Help me learn a topic. First ask what I want to understand and how much I already know.' },
  { icon: 'list-outline', title: 'Make a plan', detail: 'Turn a goal into manageable next steps.', prompt: 'Help me make a realistic plan. Ask about my goal, available time, and the main obstacles.' },
];
type Icon = keyof typeof Ionicons.glyphMap;
type UploadedFile = Awaited<ReturnType<typeof uploadChatAttachment>>;
type ManageAction = 'menu' | 'rename' | 'delete' | 'export';

function Button({ icon, label, onPress, disabled = false, primary = false, danger = false }: {
  icon?: Icon; label: string; onPress: () => void; disabled?: boolean; primary?: boolean; danger?: boolean;
}) {
  return <TouchableOpacity accessibilityRole="button" accessibilityLabel={label}
    accessibilityState={{ disabled }} onPress={onPress} disabled={disabled}
    style={[s.button, primary && s.primaryButton, danger && s.dangerButton, disabled && s.disabled]}>
    {icon && <Ionicons name={icon} size={17} color={danger ? C.danger : C.text} />}
    <Text style={[s.buttonText, danger && s.dangerText]}>{label}</Text>
  </TouchableOpacity>;
}

function IconButton({ icon, label, onPress, disabled = false }: {
  icon: Icon; label: string; onPress: () => void; disabled?: boolean;
}) {
  return <TouchableOpacity accessibilityRole="button" accessibilityLabel={label}
    accessibilityState={{ disabled }} disabled={disabled} onPress={onPress}
    style={[s.iconButton, disabled && s.disabled]}>
    <Ionicons name={icon} size={20} color={C.textMuted} />
  </TouchableOpacity>;
}

function MiniButton({ icon, label, onPress, disabled = false }: {
  icon: Icon; label: string; onPress: () => void; disabled?: boolean;
}) {
  return <TouchableOpacity accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled }}
    onPress={onPress} disabled={disabled} style={[s.miniButton, disabled && s.disabled]}>
    <Ionicons name={icon} size={15} color={C.textMuted} /><Text style={s.miniText}>{label}</Text>
  </TouchableOpacity>;
}

function Dialog({ title, close, children }: { title: string; close: () => void; children: React.ReactNode }) {
  return <Modal transparent animationType="fade" onRequestClose={close} visible>
    <KeyboardAvoidingView style={s.modalKeyboard} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
    <View style={s.overlay}><View style={s.dialog} accessibilityViewIsModal>
      <View style={s.between}><Text accessibilityRole="header" style={s.dialogTitle}>{title}</Text>
        <IconButton icon="close-outline" label={`Close ${title}`} onPress={close} /></View>
      {children}
    </View></View></KeyboardAvoidingView>
  </Modal>;
}

function MessageCard({ message, busy, notify, edit, regenerate }: {
  message: ConversationMessage; busy: boolean; notify: (text: string) => void;
  edit: (id: string, text: string) => Promise<void>; regenerate: (id: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(message.content || '');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const user = message.author_type === 'user';
  const text = message.content || '';
  const attachmentRefs = message.attachment_refs.filter(reference => reference.startsWith('chat-attachment://'));
  const save = async () => {
    if (!draft.trim() || saving) return;
    setSaving(true); setError(null);
    try { await edit(message.message_id, draft.trim()); setEditing(false); }
    catch (caught) { setError(caught instanceof Error ? caught.message : 'This message could not be edited.'); }
    finally { setSaving(false); }
  };
  return <View style={[s.message, user ? s.userMessage : s.assistantMessage]}>
    <View style={s.row}>
      {!user && <View style={s.avatar}><Ionicons name="sparkles-outline" size={14} color={C.primaryHover} /></View>}
      <Text style={s.messageAuthor}>{user ? 'You' : 'Jeeves'}</Text>
    </View>
    {editing ? <>
      <TextInput value={draft} onChangeText={setDraft} multiline maxLength={MAX_MESSAGE_LENGTH}
        autoFocus editable={!saving} accessibilityLabel="Edit your message" style={s.editInput} />
      {error && <Text accessibilityRole="alert" style={s.errorText}>{error}</Text>}
      <View style={s.dialogActions}>
        <Button label="Cancel" disabled={saving} onPress={() => { setEditing(false); setError(null); }} />
        <Button label={saving ? 'Sending…' : 'Save & resend'} primary disabled={saving || !draft.trim() || busy}
          onPress={() => { void save(); }} />
      </View>
    </> : <>
      {user ? <Text selectable style={s.userText}>{text}</Text> : <MessageContent text={text} notify={notify} />}
      {!!attachmentRefs.length && <ChatAttachments references={attachmentRefs} threadId={message.thread_id} />}
      {!user && !!text.trim() && <>
        <ChatTaskActions text={text} conversationId={message.thread_id}
          messageId={message.message_id} notify={notify} />
        <ChatSceneActions text={text} conversationId={message.thread_id}
          messageId={message.message_id} notify={notify} />
        <ChatStoryActions text={text} conversationId={message.thread_id}
          messageId={message.message_id} notify={notify} />
      </>}
      <View style={s.messageActions}>
        <MiniButton icon={copied ? 'checkmark-outline' : 'copy-outline'} label={copied ? 'Copied' : 'Copy'}
          onPress={() => { void Clipboard.setStringAsync(text).then(() => setCopied(true)).catch(() => notify('Clipboard unavailable. Select the message text to copy it.')); }} />
        {user && <MiniButton icon="create-outline" label="Edit" disabled={busy}
          onPress={() => { setDraft(text); setEditing(true); }} />}
        {!user && <MiniButton icon="refresh-outline" label="Regenerate" disabled={busy}
          onPress={() => { void regenerate(message.message_id).catch(caught => notify(caught instanceof Error ? caught.message : 'The reply could not be regenerated.')); }} />}
      </View>
    </>}
  </View>;
}

function groupThreads(threads: ConversationThread[]) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const week = today.getTime() - 6 * 86400000;
  const groups: { title: string; threads: ConversationThread[] }[] = [
    { title: 'Today', threads: [] }, { title: 'Previous 7 days', threads: [] }, { title: 'Earlier', threads: [] },
  ];
  for (const thread of [...threads].sort((a, b) => b.updated_at.localeCompare(a.updated_at))) {
    const timestamp = new Date(thread.updated_at).getTime();
    groups[timestamp >= today.getTime() ? 0 : timestamp >= week ? 1 : 2].threads.push(thread);
  }
  return groups.filter(group => group.threads.length);
}

function inferredMime(filename: string, supplied?: string) {
  const extension = filename.toLowerCase().split('.').at(-1);
  const types: Record<string, string> = {
    txt: 'text/plain', md: 'text/markdown', markdown: 'text/markdown', csv: 'text/csv',
    json: 'application/json', pdf: 'application/pdf', png: 'image/png', jpg: 'image/jpeg',
    jpeg: 'image/jpeg', webp: 'image/webp', wav: 'audio/wav',
  };
  return supplied && ACCEPTED_FILES.includes(supplied) ? supplied : types[extension || ''] || supplied || 'application/octet-stream';
}

export type ChatWorkspaceProps = { initialThreadId?: string };

export default function ChatWorkspace({ initialThreadId }: ChatWorkspaceProps = {}) {
  const router = useRouter();
  const { controller, state } = useChatController({ initialThreadId });
  const dragonAcademy = useDragonAcademy();
  const { width } = useWindowDimensions();
  const compact = width < 900;
  const narrow = width < 560;
  const [companionOpen, setCompanionOpen] = useState(width >= 900);
  const [composerHeight, setComposerHeight] = useState(180);
  const [headerHeight, setHeaderHeight] = useState(160);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [archived, setArchived] = useState(false);
  const [modelsOpen, setModelsOpen] = useState(false);
  const [manage, setManage] = useState<{ thread: ConversationThread; action: ManageAction } | null>(null);
  const [renameTitle, setRenameTitle] = useState('');
  const [exportFormat, setExportFormat] = useState<'json' | 'markdown'>('markdown');
  const [mutationBusy, setMutationBusy] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [files, setFiles] = useState<Record<string, UploadedFile[]>>({});
  const [attachmentConsent, setAttachmentConsent] = useState(false);
  const [consentChecked, setConsentChecked] = useState(false);
  const [attachmentTypes, setAttachmentTypes] = useState<string[]>([]);
  const [checkingAttachments, setCheckingAttachments] = useState(false);
  const [capabilitiesError, setCapabilitiesError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [focused, setFocused] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [newBelow, setNewBelow] = useState(false);
  const scroll = useRef<React.ElementRef<typeof ScrollView>>(null);
  const input = useRef<TextInput>(null);
  const searchInput = useRef<TextInput>(null);
  const nearBottom = useRef(true);
  const uploadController = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const sending = useRef(false);
  const creatingRef = useRef(false);
  const accountToken = getAuthToken();
  const previousAccountToken = useRef(accountToken);
  const threadId = state.activeThread?.thread_id || '__new';
  const threadIdRef = useRef(threadId);
  threadIdRef.current = threadId;
  const draft = drafts[threadId] || '';
  const attached = files[threadId] || [];
  const busy = ['submitting', 'streaming', 'reconnecting', 'cancelling'].includes(state.status);
  const loading = state.status === 'loading';
  const selectedModel = state.models.find(model => model.id === state.selectedModelId);
  const modelReady = !!selectedModel?.available && selectedModel.selectable;
  const canSend = !!draft.trim() && !state.pending && !busy && !loading && !uploading && !creating && state.ready && modelReady && state.activeThread?.state !== 'archived';
  const messages = state.messages.filter(message => message.author_type === 'user' || message.author_type === 'assistant');
  const pending = state.pending?.threadId === state.activeThread?.thread_id ? state.pending : null;
  const threadGroups = useMemo(() => groupThreads(state.threads.filter(thread =>
    thread.state === (archived ? 'archived' : 'active') && (!query.trim() || thread.title.toLowerCase().includes(query.trim().toLowerCase()))
  )), [state.threads, archived, query]);
  const notify = useCallback((text: string) => setToast(text), []);
  const run = useCallback((action: () => Promise<void>) => {
    void action().catch(caught => notify(caught instanceof Error ? caught.message : 'This action could not be completed.'));
  }, [notify]);
  const setDraft = (value: string) => setDrafts(current => ({ ...current, [threadId]: value }));
  const scrollToBottom = useCallback((animated = true) => {
    scroll.current?.scrollToEnd({ animated }); nearBottom.current = true; setNewBelow(false);
  }, []);
  const createConversation = useCallback(async () => {
    if (creatingRef.current || busy || loading || uploading) return;
    creatingRef.current = true; setCreating(true); setSidebarOpen(false);
    try { await controller.newConversation(); input.current?.focus(); }
    finally { creatingRef.current = false; if (mounted.current) setCreating(false); }
  }, [controller, busy, loading, uploading]);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; uploadController.current?.abort(); };
  }, []);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(null), 3500);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    if (state.error?.kind !== 'authorization') return;
    uploadController.current?.abort();
    setDrafts({}); setFiles({}); setManage(null); setAttachmentConsent(false);
  }, [state.error?.kind]);
  useEffect(() => {
    if (previousAccountToken.current === accountToken) return;
    previousAccountToken.current = accountToken;
    uploadController.current?.abort();
    setDrafts({}); setFiles({}); setManage(null); setAttachmentConsent(false);
  }, [accountToken]);
  useEffect(() => {
    if (!attachmentConsent) return;
    const abort = new AbortController();
    setCheckingAttachments(true); setCapabilitiesError(null); setAttachmentTypes([]);
    void attachmentCapabilities({ signal: abort.signal }).then(result => {
      if (abort.signal.aborted) return;
      if (!Array.isArray(result?.types) || result.types.length > 32) throw new Error('File attachment availability could not be read.');
      const available = [...new Set<string>(result.types.filter((entry: { media_type?: unknown; available?: unknown }) =>
        entry?.available === true && typeof entry.media_type === 'string' && ACCEPTED_FILES.includes(entry.media_type)
      ).map((entry: { media_type: string }) => entry.media_type))];
      setAttachmentTypes(available);
      if (!available.length) setCapabilitiesError('Files cannot be attached right now. Try again later.');
    }).catch(caught => { if (!abort.signal.aborted) setCapabilitiesError(caught instanceof Error ? caught.message : 'File attachments are unavailable.'); })
      .finally(() => { if (!abort.signal.aborted) setCheckingAttachments(false); });
    return () => abort.abort();
  }, [attachmentConsent]);
  useEffect(() => {
    if (!state.ready) return;
    const timer = setTimeout(() => run(() => controller.refreshThreads({ query: query.trim(), includeArchived: archived })), 250);
    return () => clearTimeout(timer);
  }, [archived, controller, query, run, state.ready]);
  useEffect(() => {
    nearBottom.current = true; setNewBelow(false); setUploadError(null);
    const timer = setTimeout(() => scrollToBottom(false), 30);
    return () => clearTimeout(timer);
  }, [threadId, scrollToBottom]);
  useEffect(() => {
    if (nearBottom.current) {
      const timer = setTimeout(() => scrollToBottom(false), 40);
      return () => clearTimeout(timer);
    }
    setNewBelow(true);
  }, [messages.length, pending?.streamText, scrollToBottom]);
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return;
    const handler = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'o') {
        event.preventDefault();
        run(createConversation);
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        if (compact) setSidebarOpen(true);
        else searchInput.current?.focus();
      }
      if (event.key === 'Escape') {
        setModelsOpen(false); setSidebarOpen(false);
        if (!mutationBusy) setManage(null);
        setAttachmentConsent(false);
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [createConversation, compact, mutationBusy, run]);

  const send = async () => {
    if (!canSend || sending.current) return;
    sending.current = true;
    const sendingAccount = getAuthToken();
    const text = draft.trim();
    const origin = threadId;
    const attachments = attached.map(file => file.attachmentRef);
    setDrafts(current => ({ ...current, [origin]: '' }));
    nearBottom.current = true; setNewBelow(false);
    try {
      await controller.send(text, { attachmentRefs: attachments });
      const next = controller.getSnapshot();
      if (next.pending?.accepted || next.status === 'idle') setFiles(current => ({ ...current, [origin]: [] }));
      else if (next.error && !next.pending?.accepted && sendingAccount === getAuthToken()) setDrafts(current => current[origin] ? current : { ...current, [origin]: text });
    } catch (caught) {
      if (sendingAccount === getAuthToken()) setDrafts(current => current[origin] ? current : { ...current, [origin]: text });
      notify(caught instanceof Error ? caught.message : 'The message could not be sent.');
    } finally { sending.current = false; }
  };

  const pickAttachment = async () => {
    if (uploading || busy || creatingRef.current || !attachmentTypes.length) return;
    setUploading(true); setUploadError(null);
    const origin = threadIdRef.current;
    const uploadingAccount = getAuthToken();
    const abort = new AbortController(); uploadController.current = abort;
    try {
      const result = await DocumentPicker.getDocumentAsync({ type: attachmentTypes, copyToCacheDirectory: true, multiple: false });
      if (result.canceled) return;
      const file = result.assets[0];
      const base64 = await readPickedAttachment(file);
      if (abort.signal.aborted) return;
      if (uploadingAccount !== getAuthToken()) throw new Error('Your account changed. Choose the file again in the intended conversation.');
      let thread = controller.getSnapshot().activeThread;
      if (origin === '__new') {
        if (thread) throw new Error('The conversation changed. Choose the file again in the intended chat.');
        await controller.newConversation();
        thread = controller.getSnapshot().activeThread;
      } else if (thread?.thread_id !== origin) {
        throw new Error('The conversation changed. Choose the file again in the intended chat.');
      }
      if (!thread || thread.state !== 'active') throw new Error('Open an active conversation before attaching a file.');
      const uploadThreadId = thread.thread_id;
      if (uploadingAccount !== getAuthToken()) throw new Error('Your account changed. Choose the file again in the intended conversation.');
      if (origin === '__new') setDrafts(current => ({ ...current, [uploadThreadId]: current.__new || '', __new: '' }));
      if ((files[thread.thread_id] || []).length >= 4) throw new Error('You can attach up to four files per message.');
      const uploaded = await uploadChatAttachment({ threadId: thread.thread_id, filename: file.name,
        mimeType: inferredMime(file.name, file.mimeType), base64, rightsAcknowledged: true, signal: abort.signal });
      if (!mounted.current || abort.signal.aborted || uploadingAccount !== getAuthToken()) return;
      setFiles(current => ({ ...current, [uploadThreadId]: [...(current[uploadThreadId] || []), uploaded] }));
      input.current?.focus();
    } catch (caught) {
      if (mounted.current && !abort.signal.aborted) setUploadError(caught instanceof Error ? caught.message : 'This file could not be attached.');
    } finally {
      if (mounted.current) setUploading(false);
      if (uploadController.current === abort) uploadController.current = null;
    }
  };

  const removeAttachment = (file: UploadedFile) => {
    if (!state.activeThread) return;
    const origin = state.activeThread.thread_id;
    run(async () => {
      await deleteChatAttachment(file.attachmentRef, origin);
      setFiles(current => ({ ...current, [origin]: (current[origin] || []).filter(item => item.attachmentRef !== file.attachmentRef) }));
    });
  };

  const manageAction = async (action: 'rename' | 'archive' | 'delete' | 'export') => {
    if (!manage || mutationBusy) return;
    setMutationBusy(true); setDialogError(null);
    const managingAccount = getAuthToken();
    try {
      if (controller.getSnapshot().activeThread?.thread_id !== manage.thread.thread_id) await controller.openConversation(manage.thread.thread_id);
      const selected = controller.getSnapshot();
      if (selected.activeThread?.thread_id !== manage.thread.thread_id) throw new Error('This conversation could not be opened. Refresh and try again.');
      if (selected.pending && action !== 'export') throw new Error('Finish or stop the reply before changing this conversation.');
      if (action === 'rename') await controller.rename(renameTitle.trim());
      else if (action === 'archive') await controller.archive(manage.thread.state !== 'archived');
      else if (action === 'export') {
        const document = await controller.exportConversation(exportFormat);
        if (managingAccount !== getAuthToken()) throw new Error('Your account changed. Open the conversation again to export it.');
        await saveChatExport(document);
        notify(Platform.OS === 'web' ? 'Conversation download started.' : 'Conversation export prepared.');
      }
      else {
        await controller.remove();
        const removed = manage.thread.thread_id;
        setDrafts(current => { const next = { ...current }; delete next[removed]; return next; });
        setFiles(current => { const next = { ...current }; delete next[removed]; return next; });
      }
      setManage(null);
      if (action !== 'export') await controller.refreshThreads({ query: query.trim(), includeArchived: archived });
    } catch (caught) { setDialogError(caught instanceof Error ? caught.message : 'This conversation could not be updated.'); }
    finally { setMutationBusy(false); }
  };

  const sidebar = <View style={[s.sidebar, compact && s.mobileSidebar]}>
    <View style={s.between}><View style={s.row}><View style={s.brandMark}><Ionicons name="sparkles-outline" size={20} color={C.primaryHover} /></View><Text style={s.brand}>Jeeves</Text></View>
      {compact && <IconButton icon="close-outline" label="Close conversations" onPress={() => setSidebarOpen(false)} />}</View>
    <Button icon="add-outline" label={creating ? 'Creating…' : 'New conversation'} primary disabled={busy || uploading || loading || creating}
      onPress={() => run(createConversation)} />
    <View style={s.searchBox}><Ionicons name="search-outline" size={17} color={C.textDim} />
      <TextInput ref={searchInput} value={query} onChangeText={setQuery} placeholder="Search conversations" placeholderTextColor={C.textDim}
        accessibilityLabel="Search conversation titles" style={s.search} maxLength={200} autoCapitalize="none" autoCorrect={false} />
      {!!query && <IconButton icon="close-outline" label="Clear search" onPress={() => setQuery('')} />}</View>
    <View style={s.tabs}>{['Chats', 'Archived'].map((label, index) => <TouchableOpacity key={label} accessibilityRole="tab"
      accessibilityState={{ selected: archived === !!index }} onPress={() => setArchived(!!index)} style={[s.tab, archived === !!index && s.activeTab]}>
      <Text style={[s.tabText, archived === !!index && s.selectedText]}>{label}</Text></TouchableOpacity>)}</View>
    <ScrollView style={s.threadList} contentContainerStyle={s.threadListContent} keyboardShouldPersistTaps="handled">
      {!state.ready && <ActivityIndicator color={C.primaryHover} />}
      {state.ready && !threadGroups.length && <Text style={s.muted}>{query ? 'No matching conversations.' : archived ? 'No archived conversations.' : 'Your conversations will appear here.'}</Text>}
      {threadGroups.map(group => <View key={group.title}><Text style={s.groupLabel}>{group.title}</Text>{group.threads.map(thread =>
        <View key={thread.thread_id} style={[s.thread, thread.thread_id === state.activeThread?.thread_id && s.selectedThread]}>
          <TouchableOpacity accessibilityRole="button" accessibilityLabel={`Open ${thread.title}`}
            accessibilityState={{ selected: thread.thread_id === state.activeThread?.thread_id, disabled: busy || uploading || loading || creating }}
            disabled={busy || uploading || loading || creating} style={s.threadMain} onPress={() => { setSidebarOpen(false); run(() => controller.openConversation(thread.thread_id)); }}>
            <Text numberOfLines={2} style={s.threadTitle}>{thread.title || 'Untitled conversation'}</Text>
            <Text style={s.threadDate}>{new Date(thread.updated_at).toLocaleDateString([], { month: 'short', day: 'numeric' })}</Text>
          </TouchableOpacity>
          <IconButton icon="ellipsis-horizontal" label={`Options for ${thread.title}`} disabled={busy || uploading || loading || creating}
            onPress={() => { setManage({ thread, action: 'menu' }); setDialogError(null); }} />
        </View>)}</View>)}
      {state.hasMoreThreads && <Button label="Load more" onPress={() => run(() => controller.refreshThreads({ query: query.trim(), includeArchived: archived, loadMore: true }))} />}
    </ScrollView>
    <View style={s.between}><IconButton icon="home-outline" label="Return home" onPress={() => router.replace('/product')} /><Text style={s.sidebarFooter}>Conversation history</Text>
      <IconButton icon="refresh-outline" label="Refresh conversations" disabled={busy} onPress={() => run(() => controller.refreshThreads({ query: query.trim(), includeArchived: archived }))} /></View>
  </View>;

  return <SafeAreaView style={s.root}>
    <KeyboardAvoidingView style={s.workspace} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      {!compact && sidebar}
      <View style={s.main}>
        <View onLayout={event => setHeaderHeight(Math.ceil(event.nativeEvent.layout.height))}>
        <View style={[s.header, compact && s.compactHeader]}>
          {compact && <IconButton icon="menu-outline" label="Open conversations" onPress={() => setSidebarOpen(true)} />}
          <View style={s.headerTitles}><Text numberOfLines={1} style={s.headerTitle}>{state.activeThread?.title || 'New conversation'}</Text>
            {!narrow && <Text style={s.muted}>{state.activeThread?.state === 'archived' ? 'Archived conversation' : 'Think, build, and learn together'}</Text>}</View>
          <TouchableOpacity accessibilityRole="button" accessibilityLabel={`Choose model. ${selectedModel?.label || 'No model selected'}`}
            onPress={() => setModelsOpen(true)} style={s.modelButton}>
            <View style={[s.dot, !modelReady && s.unavailableDot]} />
            <Text numberOfLines={1} style={s.modelLabel}>{selectedModel?.label || 'Choose a model'}</Text>
            <Ionicons name="chevron-down-outline" size={14} color={C.textMuted} />
          </TouchableOpacity>
          {state.activeThread && !narrow && <IconButton icon="ellipsis-horizontal" label="Conversation options" disabled={busy}
            onPress={() => { setManage({ thread: state.activeThread!, action: 'menu' }); setDialogError(null); }} />}
        </View>
        <JeevesRuntimeStatus />
        <View style={s.companionToggle}><MiniButton icon="sparkles-outline" label={companionOpen ? 'Hide companion' : 'Show companion'} onPress={() => setCompanionOpen(open => !open)} /></View>
        </View>
        {companionOpen && <ScrollView style={[s.companionDock, { top: headerHeight + 8, bottom: composerHeight + 12 }, compact && s.companionDockCompact]} keyboardShouldPersistTaps="handled">
          <DragonCompanionPanel draft={draft}
            lastUserText={messages.slice().reverse().find(message => message.author_type === 'user')?.content || undefined}
            academy={dragonAcademy.view} telemetry={dragonAcademy.telemetry} />
        </ScrollView>}
        <DragonDemoPlayer demo={dragonAcademy.demo} onClose={dragonAcademy.closeDemo} />
        {companionOpen && !!dragonAcademy.error && <Text accessibilityRole="alert" style={s.errorText}>{dragonAcademy.error}</Text>}
        {state.error && <View style={s.alert} accessibilityRole={state.error.kind === 'cancelled' ? undefined : 'alert'}><View style={s.row}>
          <Ionicons name={state.error.kind === 'cancelled' ? 'stop-circle-outline' : 'alert-circle-outline'} size={20} color={state.error.kind === 'cancelled' ? C.textMuted : C.warning} />
          <Text style={s.alertText}>{state.error.message}</Text>
          <IconButton icon="close-outline" label="Dismiss error" onPress={controller.dismissError} /></View>
          <View style={s.row}>{state.error.retryable && <MiniButton icon="refresh-outline" label="Try again" disabled={busy}
            onPress={() => run(async () => {
              if (state.pending) await controller.retry();
              else if (state.activeThread) await controller.refreshConversation();
              else { await controller.refreshThreads(); await controller.refreshModels(); }
            })} />}
            {state.error.kind === 'conflict' && <MiniButton icon="refresh-outline" label="Refresh conversation" disabled={busy}
              onPress={() => run(controller.refreshConversation)} />}
            {state.error.kind === 'unavailable' && <MiniButton icon="options-outline" label="Choose model" onPress={() => setModelsOpen(true)} />}</View>
        </View>}
        {state.notice && <View style={s.alert} accessibilityLiveRegion="polite"><View style={s.row}><Text style={s.alertText}>{state.notice}</Text>
          <IconButton icon="close-outline" label="Dismiss notice" onPress={controller.dismissNotice} /></View></View>}
        {loading ? <View style={s.loading}><ActivityIndicator color={C.primaryHover} /><Text style={s.muted}>{state.ready ? 'Opening conversation…' : 'Opening your conversations…'}</Text></View> :
          <ScrollView ref={scroll} style={s.scroll} contentContainerStyle={[s.messagesContent, !compact && companionOpen && s.messagesWithCompanion, compact && s.compactContent]}
            keyboardShouldPersistTaps="handled" keyboardDismissMode="interactive" scrollEventThrottle={100}
            onScroll={event => { const { layoutMeasurement, contentOffset, contentSize } = event.nativeEvent;
              nearBottom.current = layoutMeasurement.height + contentOffset.y >= contentSize.height - 100;
              if (nearBottom.current) setNewBelow(false);
            }} onContentSizeChange={() => { if (nearBottom.current) scroll.current?.scrollToEnd({ animated: false }); }}>
            {!messages.length && !pending ? <View style={s.empty}>
              <View style={s.heroIcon}><Ionicons name="sparkles-outline" size={30} color={C.primaryHover} /></View>
              <View style={{ gap: 12 }}><Text accessibilityRole="header" style={s.heroTitle}>What are we working on?</Text>
                <Text style={s.heroDetail}>Bring a question, an idea, or something you’re stuck on. We’ll take it from there.</Text></View>
              <View style={s.suggestions}>{STARTERS.map(starter => <TouchableOpacity key={starter.title} accessibilityRole="button"
                accessibilityLabel={starter.title} style={s.suggestion} onPress={() => { setDraft(starter.prompt); input.current?.focus(); }}>
                <Ionicons name={starter.icon} size={22} color={C.primaryHover} /><View style={{ gap: 6 }}>
                  <Text style={s.suggestionTitle}>{starter.title}</Text><Text style={s.suggestionDetail}>{starter.detail}</Text></View>
              </TouchableOpacity>)}</View>
            </View> : <View style={s.messagesColumn}>
              {messages.map(message => <MessageCard key={message.message_id} message={message} busy={busy || !!state.pending || state.activeThread?.state !== 'active'}
                notify={notify} edit={controller.edit} regenerate={controller.regenerate} />)}
              {pending?.kind === 'chat' && !messages.some(message => message.author_type === 'user' && message.idempotency_key === pending.idempotencyKey) &&
                <View style={[s.message, s.userMessage]}><Text style={s.messageAuthor}>You</Text><Text selectable style={s.userText}>{pending.message}</Text></View>}
              {pending && <View style={[s.message, s.assistantMessage]}>
                <View style={s.row}><View style={s.avatar}><Ionicons name="sparkles-outline" size={14} color={C.primaryHover} /></View><Text style={s.messageAuthor}>Jeeves</Text></View>
                {!!pending.streamText && <MessageContent text={pending.streamText} notify={notify} streaming={busy} />}
                {busy && <View style={s.thinking}><ActivityIndicator size="small" color={C.primaryHover} /><Text style={s.muted}>
                  {state.status === 'cancelling' ? 'Stopping…' : state.status === 'reconnecting' ? 'Reconnecting…' : pending.streamText ? 'Writing…' : 'Thinking…'}
                </Text></View>}
                {!busy && <View style={s.messageActions}><Text style={s.muted}>{pending.state === 'cancelled' ? 'Response stopped' : 'Response interrupted'}</Text>
                  <MiniButton icon="refresh-outline" label="Retry" onPress={() => run(controller.retry)} />
                  <MiniButton icon="stop-circle-outline" label="Stop reply" onPress={() => run(controller.cancel)} /></View>}
              </View>}
            </View>}
          </ScrollView>}
        {newBelow && <TouchableOpacity accessibilityRole="button" accessibilityLabel="Scroll to latest message" onPress={() => scrollToBottom()} style={s.jump}>
          <Ionicons name="arrow-down-outline" size={16} color={C.text} /><Text style={s.miniText}>Latest message</Text></TouchableOpacity>}
        <View style={[s.composerArea, compact && s.compactContent]} onLayout={event => setComposerHeight(Math.ceil(event.nativeEvent.layout.height))}><View style={s.composerColumn}>
          {state.activeThread?.state === 'archived' ? <View style={s.alert}><Text style={s.alertText}>Restore this conversation to continue chatting.</Text>
            <Button icon="arrow-undo-outline" label="Restore conversation" onPress={() => run(() => controller.archive(false))} /></View> : <>
            {!!uploadError && <View style={s.row}><Text style={[s.errorText, { flex: 1 }]} accessibilityRole="alert">{uploadError}</Text><IconButton icon="close-outline" label="Dismiss file error" onPress={() => setUploadError(null)} /></View>}
            <View style={[s.composer, focused && s.focusedComposer]}>
              {!!attached.length && <View style={s.files}>{attached.map(file => <View key={file.attachmentRef} style={s.file}>
                <Ionicons name="document-outline" size={17} color={C.primaryHover} /><Text numberOfLines={1} style={s.fileName}>{file.filename}</Text>
                <Text style={s.fileSize}>{Math.max(1, Math.ceil(file.sizeBytes / 1024))} KB</Text>
                <IconButton icon="close-outline" label={`Remove ${file.filename}`} disabled={busy} onPress={() => removeAttachment(file)} />
              </View>)}</View>}
              <TextInput ref={input} value={draft} onChangeText={setDraft} multiline maxLength={MAX_MESSAGE_LENGTH}
                placeholder={busy ? 'Your next message…' : 'Message Jeeves…'} placeholderTextColor={C.textDim}
                accessibilityLabel="Message Jeeves" style={s.composerInput} onFocus={() => setFocused(true)} onBlur={() => setFocused(false)}
                onKeyPress={event => { if (Platform.OS !== 'web') return;
                  const key = event.nativeEvent as unknown as KeyboardEvent;
                  if (key.key === 'Enter' && !key.shiftKey && !key.isComposing && !key.altKey && canSend) { event.preventDefault(); void send(); }
                }} />
              <View style={s.between}><View style={s.row}>
                <IconButton icon="attach-outline" label="Attach a file" disabled={busy || loading || creating || uploading || attached.length >= 4 || !state.ready}
                  onPress={() => { setConsentChecked(false); setAttachmentConsent(true); }} />
                {uploading ? <View style={s.row}><ActivityIndicator size="small" color={C.primaryHover} /><Text style={s.muted}>Attaching…</Text>
                  <MiniButton icon="close-outline" label="Cancel" onPress={() => uploadController.current?.abort()} /></View> :
                  <Text style={s.muted}>{draft.length > 30000 ? `${draft.length.toLocaleString()} / ${MAX_MESSAGE_LENGTH.toLocaleString()}` : attached.length ? `${attached.length} / 4 files` : 'Ask anything'}</Text>}
              </View>
                {busy ? <TouchableOpacity accessibilityRole="button" accessibilityLabel="Stop generating" accessibilityState={{ disabled: state.status === 'cancelling' }}
                  disabled={state.status === 'cancelling'} style={[s.sendButton, s.stopButton]} onPress={() => run(controller.cancel)}><Ionicons name="stop" size={17} color={C.text} /></TouchableOpacity> :
                  <TouchableOpacity accessibilityRole="button" accessibilityLabel="Send message" accessibilityState={{ disabled: !canSend }}
                    disabled={!canSend} onPress={() => { void send(); }} style={[s.sendButton, !canSend && s.disabled]}><Ionicons name="arrow-up-outline" size={23} color={C.text} /></TouchableOpacity>}
              </View>
            </View>
            <Text style={s.composerHint}>{pending && !busy ? 'Retry or stop the interrupted reply to continue.' : busy ? 'You can draft your next message while Jeeves replies.' : modelReady ? Platform.OS === 'web' ? 'Enter to send · Shift + Enter for a new line' : 'Check important information.' : 'Choose an available model to start chatting.'}</Text>
          </>}
        </View></View>
      </View>
    </KeyboardAvoidingView>
    {compact && sidebarOpen && <Modal visible animationType="slide" onRequestClose={() => setSidebarOpen(false)}>
      <SafeAreaView style={s.root}>{sidebar}</SafeAreaView></Modal>}
    {modelsOpen && <Dialog title="Choose a model" close={() => setModelsOpen(false)}>
      <Text style={s.dialogBody}>Choose how you’d like Jeeves to respond.</Text>
      <ScrollView style={s.dialogScroll} contentContainerStyle={s.modelList} keyboardShouldPersistTaps="handled">
        {!state.models.length && <Text style={s.dialogBody}>No models are available right now. Refresh to check again.</Text>}
        {state.models.map(model => <TouchableOpacity key={model.id} accessibilityRole="button"
          accessibilityLabel={`${model.label}. ${model.selectable && model.available ? 'Ready' : model.readiness?.message || 'Unavailable'}`}
          accessibilityState={{ selected: model.id === state.selectedModelId, disabled: !model.selectable || !model.available || busy }}
          disabled={!model.selectable || !model.available || busy} style={[s.modelItem, model.id === state.selectedModelId && s.selectedModel]}
          onPress={() => { controller.selectModel(model.id); setModelsOpen(false); input.current?.focus(); }}>
          <View style={s.between}><Text style={s.modelName}>{model.label}</Text>
            <Text style={[s.badge, (!model.selectable || !model.available) && s.unavailableBadge]}>{model.selectable && model.available ? 'Ready' : 'Unavailable'}</Text>
            {model.id === state.selectedModelId && <Ionicons name="checkmark-circle" size={19} color={C.primaryHover} />}</View>
          <Text style={s.modelDetails}>{model.selectable && model.available ? `${model.credential_free ? 'Runs locally' : 'Connected model'}${model.context_window ? ` · ${Math.round(model.context_window / 1000)}K context` : ''}` : model.readiness?.message || 'This model is not ready to use.'}</Text>
        </TouchableOpacity>)}
      </ScrollView>
      <Button icon="refresh-outline" label="Refresh models" disabled={busy} onPress={() => run(controller.refreshModels)} />
    </Dialog>}
    {manage && <Dialog title={manage.action === 'rename' ? 'Rename conversation' : manage.action === 'delete' ? 'Delete conversation?' : manage.action === 'export' ? 'Export conversation' : 'Conversation options'} close={() => { if (!mutationBusy) setManage(null); }}>
      {manage.action === 'menu' ? <>
        <Text numberOfLines={3} style={s.dialogBody}>{manage.thread.title}</Text>
        <Button icon="create-outline" label="Rename" onPress={() => { setRenameTitle(manage.thread.title); setManage({ ...manage, action: 'rename' }); }} />
        <Button icon={manage.thread.state === 'archived' ? 'arrow-undo-outline' : 'archive-outline'}
          label={manage.thread.state === 'archived' ? 'Restore conversation' : 'Archive conversation'} disabled={mutationBusy}
          onPress={() => { void manageAction('archive'); }} />
        <Button icon="download-outline" label="Export conversation" onPress={() => { setExportFormat('markdown'); setManage({ ...manage, action: 'export' }); }} />
        <Button icon="trash-outline" label="Delete conversation" danger onPress={() => setManage({ ...manage, action: 'delete' })} />
      </> : manage.action === 'rename' ? <>
        <TextInput value={renameTitle} onChangeText={setRenameTitle} maxLength={200} autoFocus accessibilityLabel="Conversation title"
          style={s.input} editable={!mutationBusy} onSubmitEditing={() => { if (renameTitle.trim()) void manageAction('rename'); }} />
        <View style={s.dialogActions}><Button label="Cancel" disabled={mutationBusy} onPress={() => setManage(null)} />
          <Button label={mutationBusy ? 'Saving…' : 'Save'} primary disabled={mutationBusy || !renameTitle.trim()} onPress={() => { void manageAction('rename'); }} /></View>
      </> : manage.action === 'export' ? <>
        <Text style={s.dialogBody}>Download this conversation as a readable document or a JSON file.</Text>
        <View style={s.tabs}>{(['markdown', 'json'] as const).map(format => <TouchableOpacity key={format} accessibilityRole="radio"
          accessibilityState={{ selected: exportFormat === format, disabled: mutationBusy }} disabled={mutationBusy}
          onPress={() => setExportFormat(format)} style={[s.tab, exportFormat === format && s.activeTab]}>
          <Text style={[s.tabText, exportFormat === format && s.selectedText]}>{format === 'markdown' ? 'Markdown (.md)' : 'JSON (.json)'}</Text>
        </TouchableOpacity>)}</View>
        <View style={s.dialogActions}><Button label="Cancel" disabled={mutationBusy} onPress={() => setManage(null)} />
          <Button icon="download-outline" label={mutationBusy ? 'Preparing…' : Platform.OS === 'web' ? 'Download' : 'Save or share'} primary
            disabled={mutationBusy} onPress={() => { void manageAction('export'); }} /></View>
      </> : <>
        <Text style={s.dialogBody}>“{manage.thread.title}” and its messages will be deleted. This cannot be undone.</Text>
        <View style={s.dialogActions}><Button label="Keep conversation" disabled={mutationBusy} onPress={() => setManage(null)} />
          <Button icon="trash-outline" label={mutationBusy ? 'Deleting…' : 'Delete'} danger disabled={mutationBusy} onPress={() => { void manageAction('delete'); }} /></View>
      </>}
      {dialogError && <Text accessibilityRole="alert" style={s.errorText}>{dialogError}</Text>}
    </Dialog>}
    {attachmentConsent && <Dialog title="Attach a file" close={() => setAttachmentConsent(false)}>
      {checkingAttachments ? <View style={s.thinking}><ActivityIndicator size="small" color={C.primaryHover} /><Text style={s.muted}>Checking available file types…</Text></View> : <>
        {capabilitiesError && <Text style={s.errorText} accessibilityRole="alert">{capabilitiesError}</Text>}
        {!!attachmentTypes.length && <>
          <Text style={s.dialogBody}>Attach a supported file. Up to four files per message, 5 MB each.</Text>
          <Text style={s.dialogBody}>Text{attachmentTypes.includes('application/pdf') ? ' and PDF' : ''} content can be read.{attachmentTypes.some(type => type.startsWith('image/')) || attachmentTypes.includes('audio/wav') ? ' Images and audio are validated as files; this chat does not describe images or transcribe audio.' : ''}</Text>
        </>}
      </>}
      <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: consentChecked }} onPress={() => setConsentChecked(value => !value)} style={s.checkbox}>
        <View style={[s.checkboxBox, consentChecked && s.checkedBox]}>{consentChecked && <Ionicons name="checkmark" size={17} color={C.text} />}</View>
        <Text style={s.checkboxText}>I have permission to use this file in this conversation.</Text>
      </TouchableOpacity>
      <View style={s.dialogActions}><Button label="Cancel" onPress={() => setAttachmentConsent(false)} />
        <Button icon="document-outline" label="Choose file" primary disabled={!consentChecked || checkingAttachments || !attachmentTypes.length}
          onPress={() => { setAttachmentConsent(false); void pickAttachment(); }} /></View>
    </Dialog>}
    {!!toast && <View pointerEvents="none" style={s.toast} accessibilityLiveRegion="polite"><Text style={s.toastText}>{toast}</Text></View>}
  </SafeAreaView>;
}
