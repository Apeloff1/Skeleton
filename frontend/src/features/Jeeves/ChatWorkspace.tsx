import React, { useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react';
import {
  ActivityIndicator, Alert, Image, KeyboardAvoidingView, Modal, Platform, SafeAreaView,
  ScrollView, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View, useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useFocusEffect, useRouter } from 'expo-router';
import * as Clipboard from 'expo-clipboard';
import StudioLoginGate from '../../auth/StudioLoginGate';
import { getAuthToken } from '../../auth/gameforgeAuth';
import { accountChatStorage, archiveCanonicalChat, deleteCanonicalChat, renameCanonicalChat, cancelCanonicalChat, canonicalChatHistory, canonicalChatLibrary, exportCanonicalChat, sendCanonicalChat, verifiedChatScope } from '../../product/chatSessionClient';
import { WorkspaceController } from './WorkspaceController';
import MessageContent from './MessageContent';
import JeevesRuntimeStatus from './JeevesRuntimeStatus';
import ChatModelCapabilities from './ChatModelCapabilities';
import ChatCooperationDetails from './ChatCooperationDetails';
import ChatResponseReviewControl from './ChatResponseReviewControl';
import { cooperationConfigurationIssues, reviewedResponsePolicy } from '../../product/chatCooperation';
import { useChatReadiness } from '../../product/useChatReadiness';
import { chatProgressLabel } from '../../product/chatProgress';
import ChatTaskActions from './workbench/ChatTaskActions';
import ChatSceneActions from './ChatSceneActions';
import ChatStoryActions from './ChatStoryActions';
import JeevesStudioPalette from './JeevesStudioPalette';
import { MAX_CONTEXT, MAX_TEXT, searchConversations } from './workspace';
import { getJeevesRequestContext } from '../../state/settingsStore';
import type { Artifact, Conversation, Message } from './workspace';
import { exportTranscript, saveArtifact, saveChatExport } from './chatFiles';
import CaptureEditor from './workbench/CaptureEditor';
import { captureInput } from './workbench/capture';
import type { CaptureInput } from './workbench/capture';
import DragonCompanionPanel from './companion/DragonCompanionPanel';
import DragonDemoPlayer from './companion/DragonDemoPlayer';
import {useDragonAcademy} from './companion/useDragonAcademy';

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
    <Text style={s.buttonText} numberOfLines={1}>{label}</Text>
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
      {message.cooperation && <ChatCooperationDetails summary={message.cooperation} stopped={user && failed && message.terminal === true} />}
      {!user && message.status === 'complete' && <ChatTaskActions
        text={message.text} conversationId={controller.active.id}
        messageId={message.id} notify={controller.notify} />}
      {!user && message.status === 'complete' && <ChatSceneActions
        text={message.text} conversationId={controller.active.id}
        messageId={message.id} notify={controller.notify} />}
      {!user && message.status === 'complete' && !!message.text.trim() &&
        <ChatStoryActions text={message.text} conversationId={controller.active.sessionId || controller.active.id}
          messageId={message.id} notify={controller.notify} />}
      {message.attachmentName && <Text style={s.metadata}>Attachment · {message.attachmentName}</Text>}
      {(message.artifacts || []).map((artifact, i) => <ArtifactCard key={`${artifact.type}-${i}`} artifact={artifact} notify={controller.notify} />)}
      {!message.artifacts?.length && !!message.artifactCount && <Text style={s.metadata}>{message.artifactCount} artifact(s) from an earlier visit. File contents are not stored locally.</Text>}
      <View style={s.messageActions}>
        <Button icon="copy-outline" label="Copy" onPress={() => {
          void Clipboard.setStringAsync(message.text).then(() => controller.notify('Message copied.')).catch(() => controller.notify('Clipboard is unavailable. Select the message text to copy it.'));
        }} />
        {failed && <Button icon="cloud-download-outline" label="Check server" disabled={busy} onPress={() => {
          void controller.refreshCanonical().then(() => {
            const current = controller.active.messages.find(item => item.id === message.id);
            controller.notify(current?.status === 'complete'
              ? 'The completed reply was recovered from canonical history.'
              : 'No confirmed reply yet. Retry will reuse the original message ID.');
          });
        }} />}
        {failed && !message.terminal && <Button icon="refresh-outline" label="Resume" disabled={busy} onPress={() => { void controller.retry(message.id); }} />}
        {failed && !message.terminal && controller.active.canonicalThreadId && <Button icon="stop-outline" label="Cancel saved turn" disabled={busy} onPress={() => { void controller.cancelSavedTurn(message.id); }} />}
        {message.status === 'complete' && !!message.text.trim() && <Button icon="book-outline" label="Save note" onPress={() => setCapture(captureInput(controller.active, message, ''))} />}
      </View>
      {message.terminal && <Button icon="create-outline" label="Copy to draft" disabled={busy} onPress={() => controller.edit({ draft: message.text })} />}
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
    const action = () => { void controller.remove(conversation.id); };
    const question = conversation.canonicalThreadId ? `Permanently delete "${conversation.title}" and its canonical account history? Export a copy first if you want to keep it.` : `Delete the unsent draft "${conversation.title}" from this device?`;
    if (Platform.OS === 'web') { if (globalThis.confirm(question)) action(); }
    else Alert.alert('Delete conversation?', question, [{ text: 'Cancel', style: 'cancel' }, { text: 'Delete', style: 'destructive', onPress: action }]);
  };
  return <View style={s.library}>
    <View style={s.sectionHeader}><Text style={s.sectionTitle}>Conversations</Text><Button icon="close" label="Close" onPress={close} /></View>
    <View style={s.row}><Button icon="add-outline" label="New conversation" onPress={() => { controller.create(); close(); }} /><Button icon="cloud-download-outline" label="Refresh account list" onPress={() => { void controller.refreshLibrary(); }} /></View>
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
          <Text style={s.small}>{conversation.messages.length} cached messages · {new Date(conversation.updatedAt).toLocaleDateString()}</Text>
          <Text numberOfLines={2} style={s.chatPreview}>{conversation.draft ? `Draft: ${conversation.draft}` : conversation.messages.at(-1)?.text || 'Ready for your first question'}</Text>
        </TouchableOpacity>
        <View style={s.row}>
          <Button icon={archived ? 'arrow-undo-outline' : 'archive-outline'} label={archived ? 'Restore' : 'Archive'} onPress={() => { void controller.archive(conversation.id, !archived); }} />
          <Button icon="trash-outline" label="Delete" onPress={() => remove(conversation)} />
        </View>
      </View>)}
    </ScrollView>
    <Text style={s.small}>Canonical conversations are recovered from your account. Rename and archive update the server; Delete removes canonical history after confirmation. Pin and drafts remain on this device.</Text>
  </View>;
}

function ScopedChatWorkspace({ scope }: { scope: { key: string; token: string } }) {
  const router = useRouter();
  const dragonAcademy = useDragonAcademy();
  const { width: viewportWidth } = useWindowDimensions();
  const [hydrated, setHydrated] = useState(Platform.OS !== 'web');
  useEffect(() => { setHydrated(true); }, []);
  const width = hydrated ? viewportWidth : 0;
  const [controller] = useState(() => new WorkspaceController(
    accountChatStorage(scope), sendCanonicalChat, canonicalChatHistory,
    { cancel: cancelCanonicalChat, library: canonicalChatLibrary, archive: archiveCanonicalChat, remove: deleteCanonicalChat, rename: renameCanonicalChat },
  ));
  const { readiness, refresh: refreshModels, error: readinessError, observedAt: readinessObservedAt } = useChatReadiness();
  const [reviewResponse, setReviewResponse] = useState(false);
  const [reviewPolicy, setReviewPolicy] = useState(reviewedResponsePolicy);
  const [reviewFieldError, setReviewFieldError] = useState<string | null>(null);
  const [model, setModel] = useState<string>('automatic');
  const [modelPicker, setModelPicker] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [outputTokens, setOutputTokens] = useState<number | null>(null);
  const [knowledge, setKnowledge] = useState(false);
  const [knowledgeQuery, setKnowledgeQuery] = useState('');
  const selectedModel = readiness?.models.models.find(row => row.id === model);
  const modelReady = readiness?.available === true && (model === 'automatic' ? readiness.models.automatic_available : selectedModel?.selectable === true && selectedModel.available);
  const automaticRoutes = readiness?.models.models.filter(row => row.active || row.fallback === true) ?? [];
  const automaticOutputLimit = readiness?.models.automatic_available && automaticRoutes.length ? Math.min(...automaticRoutes.map(row => row.max_output_tokens)) : undefined;
  const automaticDefaultOutput = readiness?.models.automatic_available && automaticRoutes.length ? Math.min(...automaticRoutes.map(row => row.default_output_tokens)) : undefined;
  const observedOutputLimit = selectedModel?.max_output_tokens ?? (model === 'automatic' ? automaticOutputLimit : undefined);
  const observedDefaultOutput = selectedModel?.default_output_tokens ?? (model === 'automatic' ? automaticDefaultOutput : undefined);
  const answerTokenLimit = observedOutputLimit !== undefined && observedDefaultOutput !== undefined ? Math.min(outputTokens ?? observedDefaultOutput, observedOutputLimit, 16384) : undefined;
  const reviewAvailable = readiness?.capabilities.cooperative_review === true;
  const reviewIssues = cooperationConfigurationIssues(reviewPolicy, readiness?.models.models ?? [], answerTokenLimit);
  const reviewBudgetReady = !reviewResponse || reviewAvailable && !reviewFieldError && reviewIssues.length === 0;
  const snapshot = useSyncExternalStore(controller.subscribe, controller.getSnapshot, controller.getSnapshot);
  const conversation = controller.active;
  const busy = snapshot.busyId !== null;
  const [library, setLibrary] = useState(false);
  const [settings, setSettings] = useState(false);
  const [title, setTitle] = useState('');
  const [context, setContext] = useState('');
  const [showCompanion, setShowCompanion] = useState(false);
  const [composerHeight, setComposerHeight] = useState(168);
  const scroll = useRef<React.ElementRef<typeof ScrollView>>(null);

  useEffect(() => {
    void controller.initialize();
    return () => controller.detach();
  }, [controller]);

  useFocusEffect(React.useCallback(() => {
    if (snapshot.ready) {
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

  const storageLabel = useMemo(() => ({ loading: 'Opening chat cache…', saving: 'Caching…', saved: 'Account cache saved', error: 'Cache not saved' })[snapshot.saveState], [snapshot.saveState]);

  const send = () => {
    if (!snapshot.ready || busy || !conversation.draft.trim()) return;
    if (reviewResponse && !reviewAvailable) { controller.notify('Response review is unavailable. Refresh readiness or turn off review to continue.'); return; }
    if (!reviewBudgetReady) { controller.notify(reviewFieldError || reviewIssues[0] || 'Review the response settings before sending.'); return; }
    if (!modelReady) { controller.notify('Choose a ready model or open Setup to finish the AI connection.'); return; }
    if (knowledge && !knowledgeQuery.trim()) { controller.notify('Enter a query for the explicit captured-knowledge context.'); return; }
    let requestContext: string;
    try {
      requestContext = getJeevesRequestContext(conversation.context, MAX_CONTEXT);
    } catch (error) {
      controller.notify(error instanceof Error ? error.message : 'Jeeves preferences exceed the request context bound.');
      return; // Keep the draft untouched until the user fixes settings.
    }
    const pending = controller.send(undefined, {
      context: requestContext,
      ...(reviewResponse ? { cooperation: reviewPolicy } : {}),
      ...(selectedModel ? { provider_id: selectedModel.provider_id, model_id: selectedModel.model_id } : {}),
      ...(answerTokenLimit !== undefined ? { max_output_tokens: answerTokenLimit } : {}),
      ...(knowledge ? { crawler_context: { query: knowledgeQuery.trim(), max_documents: 4, max_characters: 16000 } } : {}),
    });
    void pending;
  };

  return <SafeAreaView style={s.safe}>
    <View style={s.header}>
      <TouchableOpacity onPress={() => router.back()} accessibilityLabel="Back" accessibilityRole="button" style={s.back} testID="back-btn"><Ionicons name="chevron-back" size={24} color={C.text} /></TouchableOpacity>
      <View style={s.brand}><Text style={s.brandTitle}>Jeeves</Text><Text style={s.small}>{storageLabel}</Text></View>
      <Button icon="chatbubbles-outline" label={width > 600 ? 'Conversations' : 'Chats'} onPress={() => setLibrary(true)} disabled={!snapshot.ready} />
      <Button icon="settings-outline" label="Setup" onPress={() => router.push('/setup' as never)} />
      {width > 800 && <Button icon="folder-outline" label="Workbench" onPress={() => router.push('/jeeves-workbench')} />}
      {width > 650 && <Button icon="add-outline" label="New chat" onPress={() => controller.create()} disabled={!snapshot.ready} />}
    </View>
    {!snapshot.ready ? <View style={s.loading}>
      {snapshot.loadError ? <><Text accessibilityRole="alert" style={s.error}>{snapshot.loadError}</Text><Button icon="refresh-outline" label="Retry opening chats" onPress={() => { void controller.initialize(); }} /></> : <ActivityIndicator color={C.purple} />}
    </View> : <KeyboardAvoidingView style={s.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={s.chatToolbar}>
        <View style={s.flex}><Text numberOfLines={1} style={s.chatTitle}>{conversation.title}</Text><Text style={s.small}>{conversation.messages.length} cached messages · account history{conversation.context ? ' · Project context attached' : ''}</Text></View>
        <Button icon={conversation.pinned ? 'star' : 'star-outline'} label="Pin" selected={conversation.pinned} onPress={() => controller.edit({ pinned: !conversation.pinned })} />
        <Button icon="refresh-outline" label="Refresh" disabled={busy} onPress={() => { void controller.refreshCanonical(); }} />
        <Button icon="options-outline" label="Details" onPress={() => { setTitle(conversation.title); setContext(conversation.context); setSettings(true); }} />
      </View>
      <JeevesRuntimeStatus readiness={readiness} refresh={refreshModels} readinessError={readinessError?.message} observedAt={readinessObservedAt} />
      <View style={s.chatToolbar}>
        <Button icon="hardware-chip-outline" label={selectedModel?.label || 'Automatic model'} disabled={busy} onPress={() => setModelPicker(true)} />
        <Text style={[s.small, s.flex]}>{modelReady ? 'Ready for a new turn' : 'A ready model and conversation storage are required'}</Text>
        <Button icon="globe-outline" label="Web capture" onPress={() => router.push('/crawler' as never)} />
      </View>
      {(snapshot.notice || snapshot.saveState === 'error') && <View style={s.notice} accessibilityRole="alert">
        <Text style={[s.small, s.flex]}>{snapshot.notice || 'Changes could not be saved to this device.'}</Text>
        {snapshot.saveState === 'error' ? <Button icon="refresh-outline" label="Save again" onPress={controller.retrySave} /> : <TouchableOpacity accessibilityLabel="Dismiss notice" onPress={controller.dismissNotice}><Ionicons name="close" size={20} color={C.text} /></TouchableOpacity>}
      </View>}
      {width < 1000 && <View style={{ paddingHorizontal: 14, paddingVertical: 5 }}><Button icon="paw-outline" label={showCompanion ? 'Hide companion' : 'Show companion'} selected={showCompanion} onPress={() => setShowCompanion(value => !value)} /></View>}
      {(width >= 1000 || showCompanion) && <ScrollView style={[s.companionDock, { bottom: composerHeight + 12 }, width < 1000 && s.companionDockCompact]} keyboardShouldPersistTaps="handled">
        <DragonCompanionPanel draft={conversation.draft} lastUserText={[...conversation.messages].reverse().find(message => message.role === 'user')?.text} academy={dragonAcademy.view} telemetry={dragonAcademy.telemetry} />
      </ScrollView>}
      <DragonDemoPlayer demo={dragonAcademy.demo} onClose={dragonAcademy.closeDemo} />
      {(width >= 1000 || showCompanion) && !!dragonAcademy.error && <Text accessibilityRole="alert" style={s.small}>{dragonAcademy.error}</Text>}
      <ScrollView ref={scroll} style={s.flex} contentContainerStyle={[s.transcript, width < 1000 && s.transcriptCompact]} keyboardShouldPersistTaps="handled" testID="jeeves-transcript">
        {!conversation.messages.length && <View style={s.welcome}>
          <View style={s.crest}><Ionicons name="sparkles-outline" size={34} color={C.purple} /></View>
          <Text style={s.welcomeTitle}>What shall we work on?</Text>
          <Text style={s.welcomeSubtitle}>Your companion for building, debugging and learning. Give Jeeves a goal and a little context to get started.</Text>
          <View style={s.starters}>{STARTERS.map(starter => <TouchableOpacity key={starter.title} style={[s.starter, { width: width > 600 ? '48%' : '100%' }]} accessibilityRole="button" onPress={() => controller.edit({ draft: starter.prompt })}>
            <Ionicons name={starter.icon} color={C.purple} size={23} /><Text style={s.chatTitle}>{starter.title}</Text><Text style={s.small}>{starter.detail}</Text>
          </TouchableOpacity>)}</View>
          <Text style={s.emptyText}>Replies come from the configured AI engine. Its real state is shown while a turn runs; the final answer appears when it is committed to your conversation.</Text>
        </View>}
        {conversation.messages.map(message => <MessageCard key={message.id} message={message} controller={controller} busy={busy} />)}
        {busy && snapshot.progress?.cooperation && <ChatCooperationDetails summary={snapshot.progress.cooperation} />}
        {busy && <View style={s.composing}><ActivityIndicator color={C.purple} /><Text style={s.small}>{chatProgressLabel(snapshot.progress?.state)}</Text><Button icon="stop-outline" label={snapshot.progress?.state === 'cancelling' ? 'Stopping…' : 'Stop'} disabled={snapshot.progress?.state === 'cancelling'} onPress={() => { void controller.cancel(); }} /></View>}
      </ScrollView>
      <View style={s.composer} onLayout={event => setComposerHeight(Math.ceil(event.nativeEvent.layout.height))}>
        <JeevesStudioPalette disabled={busy}
          onCompose={draft => controller.edit({ draft })}
          onNavigate={path => router.push(path as never)} />
        {knowledge && <View style={{ gap: 6 }}><Text style={s.small}>Explicitly retrieve from your captured sources for this message. External text remains source material.</Text><TextInput accessibilityLabel="Captured knowledge query" value={knowledgeQuery} onChangeText={setKnowledgeQuery} maxLength={1024} style={s.field} placeholder="Search your captured sources…" placeholderTextColor={C.muted} /></View>}
        <TextInput value={conversation.draft} onChangeText={draft => controller.edit({ draft })} style={s.composerInput} multiline maxLength={MAX_TEXT}
          placeholder="Ask Jeeves about your next step…" placeholderTextColor={C.muted} accessibilityLabel="Message Jeeves" testID="chat-input" onKeyPress={event => {
            const key = event.nativeEvent as { key: string; ctrlKey?: boolean; metaKey?: boolean };
            if (Platform.OS === 'web' && key.key === 'Enter' && (key.ctrlKey || key.metaKey)) { event.preventDefault(); send(); }
          }} />
        <View style={s.composerActions}>
          <Button icon="library-outline" label="Captured context" selected={knowledge} disabled={busy || readiness?.capabilities.crawler_context !== true || readiness?.checks.crawler?.available !== true} onPress={() => setKnowledge(value => !value)} />
          <View style={s.flex} />
          <TouchableOpacity onPress={send} disabled={busy || !modelReady || !reviewBudgetReady || !conversation.draft.trim()} style={[s.send, (busy || !modelReady || !reviewBudgetReady || !conversation.draft.trim()) && s.disabled]} accessibilityRole="button" accessibilityLabel="Send message" testID="chat-send"><Ionicons name="arrow-up" size={22} color={C.bg} /></TouchableOpacity>
        </View>
        <ChatResponseReviewControl enabled={reviewResponse} change={setReviewResponse} disabled={busy} available={reviewAvailable} answerTokenLimit={answerTokenLimit}
          policy={reviewPolicy} changePolicy={setReviewPolicy} models={readiness?.models.models ?? []} mainModel={selectedModel}
          fieldError={reviewFieldError} changeFieldError={setReviewFieldError} issues={reviewIssues} refreshModels={refreshModels} />
        <Text style={s.composerHint}>{`${conversation.draft.length.toLocaleString()} / 16,000 · Text chat · Saved account history${Platform.OS === 'web' ? ' · Ctrl/Cmd+Enter to send' : ''}`}</Text>
      </View>
    </KeyboardAvoidingView>}
    <Modal visible={library} animationType="slide" onRequestClose={() => setLibrary(false)}><SafeAreaView style={s.safe}><Library controller={controller} close={() => setLibrary(false)} /></SafeAreaView></Modal>
    <Modal visible={modelPicker} animationType="slide" onRequestClose={() => setModelPicker(false)}><SafeAreaView style={s.safe}><ScrollView contentContainerStyle={s.details}>
      <View style={s.sectionHeader}><Text style={s.sectionTitle}>Choose a model</Text><Button icon="close" label="Close" onPress={() => setModelPicker(false)} /></View>
      <Text style={s.small}>The engine owns model availability and credentials. A selection applies to the next new turn; Resume keeps the original saved selection.</Text>
      <Button icon="refresh-outline" label="Refresh models" onPress={() => void refreshModels()} />
      <Button icon="git-branch-outline" label="Automatic engine route" selected={model === 'automatic'} disabled={!readiness?.models.automatic_available} onPress={() => { setModel('automatic'); setOutputTokens(null); setModelPicker(false); }} />
      {!readiness && <Text style={s.error}>The configured model catalog could not be observed. Open Setup and refresh.</Text>}
      {readiness?.models.models.map(row => <View key={row.id} style={s.artifact}><Text style={s.label}>{row.label}</Text><Text style={s.small}>{row.readiness.message}{row.credential_free ? ' · Local, no hosted credential required' : ''}</Text>{row.readiness.action && <Text style={s.small}>{row.readiness.action}</Text>}<ChatModelCapabilities modelFamily={row.model_family} capabilities={row.capabilities} contextWindow={row.context_window} outputLimit={row.max_output_tokens} activation={row.activation} tokenizer={row.tokenizer} limitsSource={row.limits_source} runtimeFacts={row} /><Button icon="checkmark-outline" label={row.selectable ? model === row.id ? 'Selected' : 'Use model' : 'Unavailable'} disabled={!row.selectable} selected={model === row.id} onPress={() => { setModel(row.id); setOutputTokens(Math.min(row.default_output_tokens, row.max_output_tokens, 16384)); setModelPicker(false); }} /></View>)}
      {observedOutputLimit !== undefined && <><Text style={s.label}>Shared answer budget · {answerTokenLimit?.toLocaleString()} tokens</Text>{model === 'automatic' && <Text style={s.small}>The observed limit is the smallest capacity across the declared primary and fallback routes. Automatic routing remains engine-owned.</Text>}<View style={s.row}>{[128, 256, 512, 1024, 2048, 4096].filter(value => value <= observedOutputLimit).map(value => <Button key={value} icon="text-outline" label={String(value)} selected={answerTokenLimit === value} onPress={() => setOutputTokens(value)} />)}</View></>}
      <Text style={s.small}>Attachments and all-forms generation are unavailable in canonical chat. No file is uploaded from this screen.</Text>
      <Button icon="settings-outline" label="Setup & readiness" onPress={() => { setModelPicker(false); router.push('/setup' as never); }} />
    </ScrollView></SafeAreaView></Modal>
    <Modal visible={settings} animationType="slide" onRequestClose={() => setSettings(false)}><SafeAreaView style={s.safe}><ScrollView contentContainerStyle={s.details} keyboardShouldPersistTaps="handled">
      <View style={s.sectionHeader}><Text style={s.sectionTitle}>Conversation details</Text><Button icon="close" label="Cancel" onPress={() => setSettings(false)} /></View>
      <Text style={s.label}>Title</Text><TextInput value={title} onChangeText={setTitle} maxLength={100} style={s.field} accessibilityLabel="Conversation title" />
      <Text style={s.label}>Project context</Text><Text style={s.small}>Describe your engine, goals, experience and constraints. This text is sent with each message in this conversation.</Text>
      <TextInput value={context} onChangeText={setContext} maxLength={MAX_CONTEXT} multiline style={[s.field, s.contextField]} placeholder="Godot 4 · first 2D platformer · beginner · one weekend" placeholderTextColor={C.muted} accessibilityLabel="Project context" />
      <Text style={s.small}>{context.length} / {MAX_CONTEXT}</Text>
      <Button icon="checkmark-outline" label="Save details" disabled={busy} onPress={() => { void controller.saveDetails(title, context).then(saved => { if (saved) setSettings(false); }); }} />
      <View style={s.divider} /><Text style={s.label}>Keep a copy</Text><Text style={s.small}>Export the full current active conversation branch directly from your authorized account history. Attachments and generated file contents are excluded. An unsent draft can be exported from this device.</Text>
      {conversation.canonicalThreadId ? <View style={s.row}>{(['json', 'markdown'] as const).map(format => <Button key={format} icon="download-outline" label={exporting ? 'Exporting…' : `Export account ${format === 'json' ? 'JSON' : 'Markdown'}`} disabled={exporting} onPress={() => {
        const threadId = conversation.canonicalThreadId!; setExporting(true);
        void exportCanonicalChat(threadId, format).then(async file => { if (scope.token !== getAuthToken()) return; await saveChatExport(file); controller.notify(`Exported ${file.messageCount} canonical messages from the active conversation branch. Attachments are excluded.`); }).catch(error => controller.notify(error instanceof Error ? error.message : 'The conversation could not be exported.')).finally(() => setExporting(false));
      }} />)}</View> : <Button icon="download-outline" label="Export unsent device draft" onPress={() => { void exportTranscript(conversation).catch(() => controller.notify('Could not export the draft. Try copying its text.')); }} />}
      <Text style={s.small}>Canonical messages belong to your account and can be recovered from the server. Drafts, pins and a rebuildable cache remain scoped to this account on this device. Earlier unscoped cache bytes are preserved without importing them here.</Text>
    </ScrollView></SafeAreaView></Modal>
  </SafeAreaView>;
}

function AccountChat() {
  const router = useRouter();
  const [scope, setScope] = useState<{ key: string; token: string } | null>(null);
  const [error, setError] = useState('');
  const generation = useRef(0); const token = useRef(getAuthToken());
  const verify = React.useCallback(async () => {
    const epoch = ++generation.current; setScope(null); setError('');
    try { const value = await verifiedChatScope(); if (epoch === generation.current) { token.current = value.token; setScope(value); } }
    catch (err) { if (epoch === generation.current) setError(err instanceof Error ? err.message : 'Your account could not be verified.'); }
  }, []);
  useFocusEffect(React.useCallback(() => { void verify(); return () => { generation.current++; }; }, [verify]));
  useEffect(() => { const timer = setInterval(() => { if (token.current !== getAuthToken()) { token.current = getAuthToken(); void verify(); } }, 500); return () => clearInterval(timer); }, [verify]);
  if (scope) return <ScopedChatWorkspace key={scope.key + ':' + generation.current} scope={scope} />;
  return <SafeAreaView style={s.safe}><View style={s.loading}>{error ? <><Text accessibilityRole="alert" style={s.error}>{error}</Text><Text style={s.small}>No unverified account cache has been opened. Your earlier saved data remains untouched.</Text><Button icon="refresh-outline" label="Verify account again" onPress={() => void verify()} /><Button icon="settings-outline" label="Setup & readiness" onPress={() => router.push('/setup' as never)} /></> : <><ActivityIndicator color={C.purple} /><Text style={s.small}>Verifying your account before opening its chats…</Text></>}</View></SafeAreaView>;
}
export default function ChatWorkspace() { return <StudioLoginGate title="AI chat" requireAuthenticated><AccountChat /></StudioLoginGate>; }

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg }, flex: { flex: 1 }, disabled: { opacity: 0.4 },
  header: { flexDirection: 'row', alignItems: 'center', padding: 14, gap: 12, borderBottomWidth: 1, borderColor: C.edge },
  back: { padding: 7 }, brand: { flex: 1 }, brandTitle: { fontSize: 22, fontWeight: '800', color: C.text },
  small: { color: C.muted, fontSize: 12, lineHeight: 18 }, row: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  button: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, flexShrink: 1, paddingHorizontal: 10, paddingVertical: 10, borderWidth: 1, borderColor: C.edge, borderRadius: 9, minHeight: 44 },
  buttonText: { flexShrink: 1, color: C.text, fontSize: 12, fontWeight: '600' }, selected: { backgroundColor: '#292042', borderColor: '#6d52a4' },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 20, padding: 32 },
  chatToolbar: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', paddingHorizontal: 18, paddingVertical: 12, gap: 8, borderBottomWidth: 1, borderColor: C.edge },
  chatTitle: { color: C.text, fontSize: 15, fontWeight: '700', lineHeight: 21 },
  notice: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: '#26223c', padding: 12 },
  companionDock: { position: 'absolute', right: 16, top: 112, width: 310, zIndex: 8 }, companionDockCompact: { position: 'relative', right: undefined, top: undefined, bottom: undefined, maxHeight: 240, flexShrink: 1, width: '100%', maxWidth: 420, alignSelf: 'center', paddingHorizontal: 14, paddingTop: 10 },
  transcript: { padding: 18, paddingBottom: 30, paddingRight: 340, width: '100%', maxWidth: 1280, alignSelf: 'center', flexGrow: 1 }, transcriptCompact: { paddingRight: 18, maxWidth: 960 },
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
  messageActions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 4 }, error: { color: C.red, fontSize: 13, lineHeight: 20 },
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
