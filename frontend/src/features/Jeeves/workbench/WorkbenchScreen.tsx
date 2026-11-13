import React, { useEffect, useState, useSyncExternalStore } from 'react';
import { ActivityIndicator, SafeAreaView, ScrollView, Text, View, useWindowDimensions } from 'react-native';
import { useRouter } from 'expo-router';
import { workbenchStore as store } from './store';
import ProjectEditor from './ProjectEditor';
import OverviewPanel from './OverviewPanel';
import TasksPanel from './TasksPanel';
import NotesPanel from './NotesPanel';
import SourcesPanel from './SourcesPanel';
import StudyPanel, { CardEditor } from './StudyPanel';
import FocusPanel from './FocusPanel';
import PromptsPanel from './PromptsPanel';
import { SearchPanel } from './SearchPanel';
import { ContextPanel } from './ContextPanel';
import { SettingsPanel } from './SettingsPanel';
import WeeklyReviewPanel from './WeeklyReviewPanel';
import RestoreWorkbenchPanel from './RestoreWorkbenchPanel';
import { defaultContextSelection, makeHandoff, noteDiscussionPrompt, taskDiscussionPrompt } from './context';
import { projectsByRecency, selectedProject } from './selectors';
import type { SearchHit } from './search';
import type { ContextSelection, Note, Project, WorkbenchTab } from './types';
import { Action, Badge, Empty, Section, palette, styles } from './ui';
import type { IconName } from './ui';

const tabs: { id: WorkbenchTab; title: string; icon: IconName }[] = [
  { id: 'overview', title: 'Overview', icon: 'grid-outline' },
  { id: 'weekly', title: 'Weekly review', icon: 'calendar-outline' },
  { id: 'tasks', title: 'Tasks', icon: 'checkbox-outline' },
  { id: 'notes', title: 'Notebook', icon: 'document-text-outline' },
  { id: 'sources', title: 'Sources', icon: 'library-outline' },
  { id: 'study', title: 'Study', icon: 'school-outline' },
  { id: 'prompts', title: 'Prompts', icon: 'sparkles-outline' },
  { id: 'focus', title: 'Focus', icon: 'timer-outline' },
  { id: 'search', title: 'Search', icon: 'search-outline' },
  { id: 'context', title: 'Chat context', icon: 'chatbubble-outline' },
  { id: 'settings', title: 'Data & settings', icon: 'settings-outline' },
];

export default function WorkbenchScreen() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const { state } = snapshot;
  const project = selectedProject(state);
  const [tab, setTab] = useState<WorkbenchTab>('overview');
  const [projectEditor, setProjectEditor] = useState<Project | 'new' | null>(null);
  const [cardNote, setCardNote] = useState<Note | null>(null);
  const [showProjects, setShowProjects] = useState(false);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { void store.initialize(); }, []);
  useEffect(() => { setNow(Date.now()); }, [state.revision]);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), state.sessions.some(item => item.outcome === 'running') ? 1000 : 30000);
    return () => clearInterval(timer);
  }, [state.sessions]);
  const send = async (draft: string, selection?: ContextSelection) => {
    if (!project) return;
    try {
      const value = makeHandoff(state, selection || defaultContextSelection(state, project.id), draft, {
        now: Date.now(), id: () => globalThis.crypto?.randomUUID?.() || `handoff-${Date.now()}`,
      });
      if (await store.handoff(value)) router.push('/jeeves-chat');
    } catch (error) { store.notify(error instanceof Error ? error.message : 'Could not prepare a chat draft.'); }
  };
  const openResult = (hit: SearchHit) => {
    if (hit.projectId) store.dispatch({ type: 'project.select', id: hit.projectId });
    const destination: Record<SearchHit['kind'], WorkbenchTab> = {
      project: 'overview', task: 'tasks', note: 'notes', source: 'sources', card: 'study', prompt: 'prompts', session: 'focus',
    };
    setTab(destination[hit.kind]);
    store.notify(`Opened ${hit.kind} collection for “${hit.title}”.`);
  };
  const props = project ? { state, project, store, now } : null;
  return (
    <SafeAreaView style={styles.safe}>
      <View style={{ padding: 16, gap: 12, borderBottomWidth: 1, borderColor: palette.border }}>
        <View style={[styles.row, { justifyContent: 'space-between', flexWrap: 'wrap' }]}>
          <View><Text style={[styles.sectionTitle, { fontSize: 25 }]}>Jeeves workbench</Text><Text style={styles.muted}>Build, learn, and keep your project knowledge together.</Text></View>
          <View style={styles.wrap}><Action label="Chat" icon="chatbubbles-outline" onPress={() => router.push('/jeeves-chat')} /><Action label="Projects" icon="folder-outline" selected={showProjects} onPress={() => setShowProjects(!showProjects)} /></View>
        </View>
        <View style={styles.wrap}>
          <Badge text={snapshot.loading ? 'Opening…' : snapshot.saveStatus === 'saved' ? 'Saved on this device' : snapshot.saveStatus} tone={snapshot.saveStatus === 'failed' || snapshot.saveStatus === 'conflict' ? 'red' : 'muted'} />
          <Action label="Undo" icon="arrow-undo-outline" disabled={!snapshot.undoAvailable} onPress={store.undo} compact />
          <Action label="Redo" icon="arrow-redo-outline" disabled={!snapshot.redoAvailable} onPress={store.redo} compact />
          {project && <Text style={styles.label}>{project.title}</Text>}
        </View>
        {snapshot.notice && <View style={styles.row}><Text accessibilityRole="alert" style={[styles.muted, styles.flex]}>{snapshot.notice}</Text><Action label="Dismiss" onPress={store.dismissNotice} compact /></View>}
      </View>
      {snapshot.loading && <ActivityIndicator color={palette.accent} style={{ margin: 30 }} />}
      {!snapshot.ready && snapshot.error && <View style={{ padding: 24, gap: 16 }}>
        <Text accessibilityRole="alert" style={styles.error}>{snapshot.error}</Text>
        <Action label="Retry opening workbench" onPress={() => { void store.initialize(); }} />
        {snapshot.recoveryAvailable && <Action label="Restore previous saved snapshot" onPress={() => { void store.restoreRecovery(); }} />}
      </View>}
      {snapshot.ready && <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: width < 600 ? 12 : 24, gap: 18, maxWidth: 1250, width: '100%', alignSelf: 'center', paddingBottom: 60 }}>
        {(showProjects || !project) && <Section title="Your projects" action={<Action label="New project" icon="add" onPress={() => setProjectEditor('new')} />}>
          {!state.projects.length && <Text style={styles.muted}>Start with a goal and an engine. Add tasks, notes and questions as your project develops.</Text>}
          {projectsByRecency(state).map(item => <View key={item.id} style={[styles.card, { borderLeftWidth: 4, borderLeftColor: item.color }]}>
            <View style={styles.wrap}><Text style={styles.label}>{item.title}</Text><Badge text={item.status} />{item.pinned && <Badge text="Pinned" tone="accent" />}</View>
            {!!item.summary && <Text style={styles.muted}>{item.summary}</Text>}
            <View style={styles.wrap}><Action label={`Open ${item.title}`} selected={project?.id === item.id} onPress={() => { store.dispatch({ type: 'project.select', id: item.id }); setShowProjects(false); }} /><Action label="Edit project" onPress={() => setProjectEditor(item)} /></View>
          </View>)}
        </Section>}
        {!project && <Empty icon="folder-open-outline" title="Make room for your next idea" message="Create a project to begin. Everything in this workbench works locally without an AI connection." action={<Action label="Create first project" onPress={() => setProjectEditor('new')} />} />}
        {!project && <RestoreWorkbenchPanel store={store} />}
        {project && props && <View key={project.id} style={styles.stack}>
          <View style={styles.wrap}>{tabs.map(item => <Action key={item.id} label={item.title} icon={item.icon} selected={tab === item.id} onPress={() => setTab(item.id)} />)}<Action label="Edit project" icon="create-outline" onPress={() => setProjectEditor(project)} /></View>
          {project.status === 'archived' && <Text style={styles.muted}>This project is archived. Edit its status to resume adding work.</Text>}
          {tab === 'overview' && <OverviewPanel {...props} navigate={setTab} />}
          {tab === 'weekly' && <WeeklyReviewPanel {...props} navigate={setTab} />}
          {tab === 'tasks' && <TasksPanel {...props} discuss={task => { void send(taskDiscussionPrompt(task.title, task.description), { ...defaultContextSelection(state, project.id), taskIds: [task.id] }); }} />}
          {tab === 'notes' && <NotesPanel {...props} discuss={note => { void send(noteDiscussionPrompt(note.title, note.body), { ...defaultContextSelection(state, project.id), noteIds: [note.id], sourceIds: note.sourceIds }); }} createCard={setCardNote} />}
          {tab === 'sources' && <SourcesPanel {...props} />}
          {tab === 'study' && <StudyPanel {...props} />}
          {tab === 'prompts' && <PromptsPanel {...props} usePrompt={draft => { void send(draft); }} />}
          {tab === 'focus' && <FocusPanel {...props} />}
          {tab === 'search' && <SearchPanel {...props} open={openResult} />}
          {tab === 'context' && <ContextPanel {...props} send={(draft, selection) => { void send(draft, selection); }} />}
          {tab === 'settings' && <SettingsPanel {...props} />}
        </View>}
      </ScrollView>}
      {projectEditor && <ProjectEditor store={store} project={projectEditor === 'new' ? undefined : projectEditor} close={() => setProjectEditor(null)} />}
      {cardNote && props && <CardEditor {...props} note={cardNote} close={() => setCardNote(null)} />}
    </SafeAreaView>
  );
}
