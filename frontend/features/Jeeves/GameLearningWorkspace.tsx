import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator, AppState, Image, KeyboardAvoidingView, Modal, Platform, SafeAreaView,
  ScrollView, Text, TextInput, TouchableOpacity, View, useWindowDimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import * as Clipboard from 'expo-clipboard';
import * as DocumentPicker from 'expo-document-picker';
import { getAuthToken } from '../../src/auth/gameforgeAuth';
import {
  cancelLearningJob, createLearningProject, exportLearningProject, generateLearningProject,
  getLearningCatalogue, getLearningJob, getLearningProject, getReviewedDragonSources, ingestLearningSource, learningJobTerminal,
  learningRequestKey, listLearningProjects, resumeLearningJob, revokeLearningSource, saveLearningEditor, simulateLearningProject, startLearningTraining,
  type LearningCatalogue, type LearningConsole, type LearningFile, type LearningJob,
  type LearningObservation, type LearningProject, type LearningProjectSummary, type LearningSession, type LearningSourceKind, type ReviewedDragonSource,
} from '../../src/product/gameLearningClient';
import { ChatClientError } from '../../src/product/chatErrors';
import { readLearningFile, saveLearningExport } from './gameLearningFiles';
import GameLearningFrame from './GameLearningFrame';
import s, { gameLearningColors as C } from './GameLearningWorkspace.styles';

type Icon = keyof typeof Ionicons.glyphMap;
type Tab = 'editor' | 'sources' | 'observe' | 'learn' | 'build';
const TABS: { id: Tab; label: string; icon: Icon }[] = [
  { id: 'editor', label: 'Editor', icon: 'code-slash-outline' },
  { id: 'sources', label: 'Sources', icon: 'file-tray-full-outline' },
  { id: 'observe', label: 'Play & observe', icon: 'game-controller-outline' },
  { id: 'learn', label: 'Learning', icon: 'analytics-outline' },
  { id: 'build', label: 'Build & export', icon: 'cube-outline' },
];
const MAX_FILE_BYTES = 128000;
function Button({ label, icon, disabled = false, primary = false, onPress }: {
  label: string; icon?: Icon; disabled?: boolean; primary?: boolean; onPress: () => void;
}) {
  return <TouchableOpacity accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled }}
    disabled={disabled} onPress={onPress} style={[s.button, primary && s.primaryButton, disabled && s.disabled]}>
    {icon && <Ionicons name={icon} size={17} color={C.text} />}<Text style={s.buttonText}>{label}</Text>
  </TouchableOpacity>;
}
function IconButton({ label, icon, onPress, disabled = false }: { label: string; icon: Icon; onPress: () => void; disabled?: boolean }) {
  return <TouchableOpacity accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled }}
    disabled={disabled} onPress={onPress} style={[s.iconButton, disabled && s.disabled]}><Ionicons name={icon} size={21} color={C.textMuted} /></TouchableOpacity>;
}
function Field({ label, value, change, multiline = false, numeric = false, placeholder, maxLength = 2000 }: {
  label: string; value: string; change: (value: string) => void; multiline?: boolean; numeric?: boolean; placeholder?: string; maxLength?: number;
}) {
  return <View style={s.fieldGroup}><Text style={s.label}>{label}</Text><TextInput value={value} onChangeText={change}
    accessibilityLabel={label} keyboardType={numeric ? 'number-pad' : 'default'} multiline={multiline} maxLength={maxLength}
    placeholder={placeholder} placeholderTextColor={C.textDim} style={[s.field, multiline && s.multiline]} autoCapitalize="none" autoCorrect={false} /></View>;
}
function Dialog({ title, close, children }: { title: string; close: () => void; children: React.ReactNode }) {
  return <Modal transparent visible animationType="fade" onRequestClose={close}>
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <View style={s.overlay}><View style={s.dialog} accessibilityViewIsModal>
        <View style={s.between}><Text accessibilityRole="header" style={s.title}>{title}</Text><IconButton label={`Close ${title}`} icon="close-outline" onPress={close} /></View>{children}
      </View></View>
    </KeyboardAvoidingView>
  </Modal>;
}
function Section({ title, children, detail }: { title: string; detail?: string; children: React.ReactNode }) {
  return <View style={s.section}><Text accessibilityRole="header" style={s.sectionTitle}>{title}</Text>
    {!!detail && <Text style={s.description}>{detail}</Text>}{children}</View>;
}
function human(value: string) { return value.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase()); }
function measured(value: unknown) {
  if (typeof value === 'number' && Number.isFinite(value)) return value.toLocaleString(undefined, { maximumSignificantDigits: 5 });
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (typeof value === 'string') return value.slice(0, 100);
  return null;
}
function Metrics({ values }: { values?: Record<string, unknown> }) {
  const entries = Object.entries(values || {}).map(([key, value]) => [key, measured(value)] as const).filter(([, value]) => value !== null).slice(0, 20);
  return entries.length ? <View style={s.metrics}>{entries.map(([key, value]) => <View key={key} style={s.metric}>
    <Text style={s.metricValue}>{value}</Text><Text style={s.metricLabel}>{human(key)}</Text></View>)}</View> : <Text style={s.muted}>No measured metrics have been reported yet.</Text>;
}
function Lineage({ refs }: { refs?: string[] }) {
  if (!refs?.length) return <Text style={s.muted}>Lineage is available after the server records an observation or learning result.</Text>;
  return <View style={{ gap: 6 }}>{refs.slice(0, 32).map((ref, index) => <Text selectable key={`${ref}:${index}`} style={s.reference}>{ref}</Text>)}</View>;
}
function Observation({ session }: { session?: LearningSession }) {
  const observation = (session?.observation || session?.last_observation) as LearningObservation | undefined;
  const frame = observation?.frame_base64;
  const mime = observation?.frame_media_type;
  const image = typeof frame === 'string' && frame.length < 2 * 1024 * 1024 && /^[A-Za-z0-9+/]*={0,2}$/.test(frame)
    && (mime === 'image/png' || mime === 'image/jpeg' || mime === 'image/webp');
  return <View style={s.observation}>
    {session?.last_frame ? <GameLearningFrame frame={session.last_frame} /> : image ? <Image source={{ uri: `data:${mime};base64,${frame}` }} style={s.frame} resizeMode="contain" accessibilityLabel="Latest frame returned by the game engine" /> :
      observation ? <Text selectable style={s.observationText}>{JSON.stringify(observation.state || observation, null, 2).slice(0, 16000)}</Text> :
        <><Ionicons name="game-controller-outline" size={36} color={C.textDim} /><Text style={s.muted}>Reset the engine to receive its first real observation.</Text></>}
  </View>;
}
function JobCard({ job, busy, cancel, resume }: { job: LearningJob; busy: boolean; cancel: (id: string) => void; resume?: (id: string) => void }) {
  const percent = job.progress ? Math.round(job.progress.completed / job.progress.total * 100) : 0;
  const error = typeof job.error === 'string' ? job.error : job.error?.message;
  return <View style={s.job}>
    <View style={s.between}><View style={{ gap: 4 }}><Text style={s.projectName}>{human(job.kind)}</Text>
      <Text style={s.muted}>{human(job.status)}{job.updated_at ? ` · ${new Date(job.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : ''}</Text></View>
      {!learningJobTerminal(job) && <Button label="Stop" icon="stop-circle-outline" disabled={busy} onPress={() => cancel(job.job_id)} />}</View>
    {job.resume_available && resume && <Button label="Resume from checkpoint" icon="play-outline" disabled={busy} onPress={() => resume(job.job_id)} />}
    {job.progress ? <><View style={s.progressTrack}><View style={[s.progressFill, { width: `${percent}%` }]} /></View>
      <Text style={s.muted}>{job.progress.completed.toLocaleString()} / {job.progress.total.toLocaleString()} {job.progress.unit || 'updates'}</Text></> :
      !learningJobTerminal(job) && <View style={s.row}><ActivityIndicator size="small" color={C.primaryHover} /><Text style={s.muted}>Waiting for the next measured update…</Text></View>}
    {!!error && <Text style={s.error} accessibilityRole="alert">{error}</Text>}
    <Metrics values={job.metrics} />
    {!!job.checkpoints?.length && <View style={{ gap: 8 }}><Text style={s.label}>Recorded checkpoints</Text>{job.checkpoints.slice(-8).map((checkpoint, index) =>
      <View key={checkpoint.checkpoint_id || checkpoint.digest || String(index)} style={s.checkpoint}>
        <Text style={s.muted}>{checkpoint.committed_episodes !== undefined ? `${checkpoint.committed_episodes} committed episodes` : checkpoint.episode !== undefined ? `Episode ${checkpoint.episode}` : checkpoint.step !== undefined ? `Update ${checkpoint.step}` : 'Checkpoint'}{checkpoint.committed_updates !== undefined ? ` · ${checkpoint.committed_updates} updates` : ''}</Text>
        <Text selectable style={s.reference}>{checkpoint.policy_digest || checkpoint.digest || checkpoint.checkpoint_id}</Text>
      </View>)}</View>}
    {!!job.lineage_refs?.length && <Lineage refs={job.lineage_refs} />}
  </View>;
}
function projectFiles(project: LearningProject): LearningFile[] {
  return project.files !== undefined ? project.files : [{ path: 'project.json', content: project.program_text, language: 'json', revision: project.version }];
}
function generatedFiles(job: LearningJob): LearningFile[] {
  const files = job.result?.files;
  if (!Array.isArray(files) || files.length > 96) return [];
  if (files.some(file => !file || typeof file.path !== 'string' || typeof file.content !== 'string' || new TextEncoder().encode(file.content).byteLength > MAX_FILE_BYTES)) return [];
  return files;
}
function integer(value: string, name: string, min: number, max: number) {
  if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) < min || Number(value) > max) throw new Error(`${name} must be between ${min} and ${max}.`);
  return Number(value);
}

export default function GameLearningWorkspace() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const compact = width < 1000;
  const narrow = width < 700;
  const [catalogue, setCatalogue] = useState<LearningCatalogue | null>(null);
  const [projects, setProjects] = useState<LearningProjectSummary[]>([]);
  const [project, setProject] = useState<LearningProject | null>(null);
  const [jobs, setJobs] = useState<Record<string, LearningJob>>({});
  const [tab, setTab] = useState<Tab>('editor');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [sidebar, setSidebar] = useState(false);
  const [newProject, setNewProject] = useState(false);
  const [projectName, setProjectName] = useState('');
  const [consoleId, setConsoleId] = useState('');
  const [consoleQuery, setConsoleQuery] = useState('');
  const [editorFiles, setEditorFiles] = useState<LearningFile[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [selectedFile, setSelectedFile] = useState('');
  const [editorVersion, setEditorVersion] = useState(0);
  const [addFile, setAddFile] = useState(false);
  const [newPath, setNewPath] = useState('');
  const [sourceKind, setSourceKind] = useState<LearningSourceKind>('text');
  const [sourceText, setSourceText] = useState('');
  const [dragonRef, setDragonRef] = useState('');
  const [dragonSources, setDragonSources] = useState<ReviewedDragonSource[]>([]);
  const [rights, setRights] = useState('');
  const [consent, setConsent] = useState(false);
  const [selectedSource, setSelectedSource] = useState('');
  const [selectedSession, setSelectedSession] = useState('');
  const [action, setAction] = useState('');
  const [steps, setSteps] = useState('16');
  const [seed, setSeed] = useState('13');
  const [epochs, setEpochs] = useState('12');
  const [algorithm, setAlgorithm] = useState('');
  const [continueLearning, setContinueLearning] = useState(true);
  const [trainSessions, setTrainSessions] = useState<string[]>([]);
  const [generationTitle, setGenerationTitle] = useState('');
  const [generationGenre, setGenerationGenre] = useState('arcade_golden_age');
  const [generationComplexity, setGenerationComplexity] = useState('2');
  const [withdrawSource, setWithdrawSource] = useState<string | null>(null);
  const [connectionRevision, setConnectionRevision] = useState(0);
  const mounted = useRef(true);
  const epoch = useRef(0);
  const mutation = useRef(false);
  const abort = useRef<AbortController | null>(null);
  const currentProject = useRef(project);
  currentProject.current = project;
  const savedFiles = project ? projectFiles(project) : [];
  const dirty = editorFiles.some(file => drafts[file.path] !== savedFiles.find(saved => saved.path === file.path)?.content);
  const dirtyRef = useRef(dirty); dirtyRef.current = dirty;
  const accountToken = getAuthToken();
  const previousAccount = useRef(accountToken);
  const createAttempt = useRef<{ fingerprint: string; key: string } | null>(null);
  const trainAttempt = useRef<{ fingerprint: string; key: string } | null>(null);
  const generationAttempt = useRef<{ fingerprint: string; key: string } | null>(null);
  const profile = catalogue?.consoles.find(console => console.console_id === project?.console_id);
  const session = project?.sessions.find(value => value.session_id === selectedSession) || project?.sessions.at(-1);
  const runtimeActions = session?.actions || project?.environment_actions || profile?.actions || [];
  const currentFile = editorFiles.find(file => file.path === selectedFile);
  const code = drafts[selectedFile] || '';
  const allJobs = Object.values(jobs).filter(job => job.project_id === project?.project_id).sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
  const availableAlgorithms = catalogue?.algorithms.filter(value => value.available) || [];
  const runningJobs = allJobs.filter(job => !learningJobTerminal(job));
  const ready = !!profile?.available;
  const editorChanged = !!project && editorVersion !== project.version && dirty;
  const resetEditor = useCallback((value: LearningProject) => {
    const files = projectFiles(value); setEditorFiles(files); setDrafts(Object.fromEntries(files.map(file => [file.path, file.content])));
    setSelectedFile(previous => files.some(file => file.path === previous) ? previous : value.entrypoint && files.some(file => file.path === value.entrypoint) ? value.entrypoint : files[0]?.path || ''); setEditorVersion(value.version);
  }, []);
  const acceptProject = useCallback((value: LearningProject, replaceEditor = false) => {
    if (!mounted.current || previousAccount.current !== getAuthToken()) return;
    setProject(value); setProjects(current => [value, ...current.filter(item => item.project_id !== value.project_id)]);
    setJobs(current => ({ ...current, ...Object.fromEntries(value.jobs.map(job => [job.job_id, { ...current[job.job_id], ...job,
      result: job.result && current[job.job_id]?.result ? { ...current[job.job_id].result, ...job.result } : job.result ?? current[job.job_id]?.result,
    }])) }));
    if (replaceEditor || !dirtyRef.current) resetEditor(value);
    setSelectedSource(previous => value.sources.some(source => source.source_id === previous) ? previous : value.sources.at(-1)?.source_id || '');
    setSelectedSession(previous => value.sessions.some(item => item.session_id === previous) ? previous : value.sessions.at(-1)?.session_id || '');
  }, [resetEditor]);
  const openProject = useCallback(async (id: string) => {
    if (mutation.current) return;
    const requestEpoch = ++epoch.current; setConnectionRevision(value => value + 1); abort.current?.abort(); const controller = new AbortController(); abort.current = controller;
    const token = getAuthToken(); setLoading(true); setError(null); setConflict(false); setSidebar(false);
    try {
      const value = await getLearningProject(id, { signal: controller.signal });
      if (!mounted.current || requestEpoch !== epoch.current || token !== getAuthToken()) return;
      acceptProject(value, true); setTrainSessions([]); setNotice(null); setTab('editor');
    } catch (caught) { if (!controller.signal.aborted && mounted.current) setError(caught instanceof Error ? caught.message : 'This project could not be opened.'); }
    finally { if (mounted.current && requestEpoch === epoch.current) setLoading(false); }
  }, [acceptProject]);
  const refreshProject = useCallback(async () => {
    const id = currentProject.current?.project_id;
    if (!id) return;
    const requestEpoch = epoch.current; const token = getAuthToken();
    const value = await getLearningProject(id);
    if (mounted.current && requestEpoch === epoch.current && token === getAuthToken()) acceptProject(value);
  }, [acceptProject]);
  const initialize = useCallback(async () => {
    const token = getAuthToken(); const requestEpoch = ++epoch.current; setConnectionRevision(value => value + 1);
    setLoading(true); setError(null);
    const [catalog, list] = await Promise.allSettled([getLearningCatalogue(), listLearningProjects()]);
    if (!mounted.current || token !== getAuthToken() || requestEpoch !== epoch.current) return;
    if (catalog.status === 'fulfilled') { setCatalogue(catalog.value); setConsoleId(current => current || catalog.value.consoles.find(value => value.available)?.console_id || catalog.value.consoles[0]?.console_id || ''); setAlgorithm(current => current || catalog.value.algorithms.find(value => value.available)?.id || ''); }
    else setError(catalog.reason instanceof Error ? catalog.reason.message : 'The game engine catalogue could not be loaded.');
    if (list.status === 'fulfilled') {
      setProjects(list.value);
      const selected = currentProject.current?.project_id || list.value[0]?.project_id;
      if (selected) {
        try {
          const opened = await getLearningProject(selected);
          if (mounted.current && token === getAuthToken() && requestEpoch === epoch.current) acceptProject(opened, !currentProject.current);
        } catch (caught) { if (mounted.current && token === getAuthToken()) setError(caught instanceof Error ? caught.message : 'The selected project could not be opened.'); }
      }
    } else setError(list.reason instanceof Error ? list.reason.message : 'Projects could not be loaded.');
    setLoading(false);
  }, [acceptProject]);
  useEffect(() => { mounted.current = true; void initialize(); return () => { mounted.current = false; epoch.current++; abort.current?.abort(); }; }, [initialize]);
  useEffect(() => {
    if (previousAccount.current === accountToken) return;
    previousAccount.current = accountToken; epoch.current++; abort.current?.abort();
    setProject(null); setProjects([]); setJobs({}); setCatalogue(null); setDrafts({}); setEditorFiles([]); setSourceText(''); setDragonRef(''); setRights(''); setConsent(false);
    setDragonSources([]); setGenerationTitle(''); setProjectName(''); setSelectedSource(''); setSelectedSession(''); setTrainSessions([]); setNewProject(false); setAddFile(false); setWithdrawSource(null);
    createAttempt.current = null; trainAttempt.current = null; generationAttempt.current = null;
    setConnectionRevision(value => value + 1); setError('Your account changed. Refresh the studio to load this account’s projects.'); setLoading(false);
  }, [accountToken]);
  useEffect(() => {
    if (!profile) return;
    setAction(value => runtimeActions.includes(value) ? value : runtimeActions[0] || '');
    setSourceKind(value => profile.supported_source_kinds.includes(value) ? value : profile.supported_source_kinds[0] || 'text');
  }, [profile, runtimeActions]);
  const pollingIds = runningJobs.map(job => job.job_id).slice(0, 4).join('|');
  useEffect(() => {
    if (!pollingIds) return;
    const controller = new AbortController(); const token = getAuthToken(); const requestEpoch = epoch.current;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = async () => {
      const results = await Promise.allSettled(pollingIds.split('|').map(id => getLearningJob(id, { signal: controller.signal })));
      if (controller.signal.aborted || !mounted.current || token !== getAuthToken() || requestEpoch !== epoch.current) return;
      let settled = false;
      for (const result of results) {
        if (result.status === 'fulfilled') { const value = result.value; setJobs(current => ({ ...current, [value.job_id]: value })); settled ||= learningJobTerminal(value); }
        else setError(result.reason instanceof Error ? result.reason.message : 'Learning progress was interrupted. Refresh to reconnect.');
      }
      if (settled && !mutation.current) { try { await refreshProject(); } catch { /* The authoritative job remains visible; refresh is available. */ } }
      if (!controller.signal.aborted) timer = setTimeout(poll, 2000);
    };
    timer = setTimeout(poll, 500);
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [pollingIds, refreshProject, connectionRevision]);
  useEffect(() => {
    const subscription = AppState.addEventListener('change', state => { if (state === 'active' && currentProject.current && !mutation.current) void refreshProject().catch(() => setError('Refresh to reconnect to this project.')); });
    return () => subscription.remove();
  }, [refreshProject]);
  const perform = useCallback(async (label: string, operation: (current: LearningProject, signal: AbortSignal) => Promise<void>) => {
    const selected = currentProject.current;
    if (!selected || mutation.current) return;
    mutation.current = true; setBusy(label); setError(null); setConflict(false); setNotice(null);
    const requestEpoch = epoch.current; const token = getAuthToken(); const controller = new AbortController(); abort.current = controller;
    try { await operation(selected, controller.signal); }
    catch (caught) {
      if (mounted.current && requestEpoch === epoch.current && token === getAuthToken()) {
        setError(caught instanceof Error ? caught.message : 'The operation could not be completed.'); setConflict(caught instanceof ChatClientError && caught.kind === 'conflict');
      }
    } finally { mutation.current = false; if (mounted.current && requestEpoch === epoch.current) setBusy(null); }
  }, []);
  const save = useCallback(() => {
    void perform('Saving source', async (current, signal) => {
      const files = editorFiles.map(file => ({ ...file, content: drafts[file.path] ?? file.content }));
      if (files.some(file => new TextEncoder().encode(file.content).byteLength > MAX_FILE_BYTES)) throw new Error('Each source file must stay below 128 KB.');
      const text = files.find(file => file.path === current.entrypoint)?.content ?? current.program_text;
      const result = await saveLearningEditor({ ...current, version: editorVersion }, text, files, { signal });
      if (signal.aborted) return; acceptProject(result, true); setNotice('Project source saved.');
    });
  }, [perform, editorFiles, drafts, editorVersion, acceptProject]);
  useEffect(() => {
    if (Platform.OS !== 'web' || typeof document === 'undefined') return;
    const handler = (event: KeyboardEvent) => { if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); if (dirty && !mutation.current) save(); } };
    document.addEventListener('keydown', handler); return () => document.removeEventListener('keydown', handler);
  }, [save, dirty]);
  const create = async () => {
    if (mutation.current || !projectName.trim() || !consoleId) return;
    if (dirty) { setError('Save or reload your editor changes before creating another project.'); return; }
    mutation.current = true; setBusy('Creating project'); setError(null);
    const token = getAuthToken();
    try {
      const fingerprint = JSON.stringify({ name: projectName.trim(), consoleId });
      if (createAttempt.current?.fingerprint !== fingerprint) createAttempt.current = { fingerprint, key: learningRequestKey('create') };
      const value = await createLearningProject(projectName.trim(), consoleId, {}, createAttempt.current.key);
      if (token !== getAuthToken() || !mounted.current) return;
      createAttempt.current = null; epoch.current++; setConnectionRevision(previous => previous + 1); acceptProject(value, true); setNewProject(false); setProjectName(''); setTrainSessions([]); setTab('editor');
    } catch (caught) { if (mounted.current && token === getAuthToken()) setError(caught instanceof Error ? caught.message : 'The project could not be created.'); }
    finally { mutation.current = false; if (mounted.current) setBusy(null); }
  };
  const rightsRefs = () => {
    const values = rights.split(/[\n,]/).map(value => value.trim()).filter(Boolean);
    if (!consent || !values.length || values.length > 64 || new Set(values).size !== values.length) throw new Error('Confirm your rights and provide distinct permission references before ingesting a source.');
    return values;
  };
  const ingest = (file = false) => {
    void perform('Ingesting source', async (current, signal) => {
      const permissionRefs = rightsRefs(); const token = getAuthToken(); const original = current.project_id;
      let text = sourceKind === 'text' ? sourceText : undefined; let filename: string | undefined; let contentBase64: string | undefined;
      if (file || sourceKind === 'rom' || sourceKind === 'project') {
        const result = await DocumentPicker.getDocumentAsync({ type: '*/*', copyToCacheDirectory: true, multiple: false });
        if (result.canceled || signal.aborted) return;
        filename = result.assets[0].name;
        contentBase64 = await readLearningFile(result.assets[0], Math.min(16777216, catalogue?.limits?.upload_bytes || 16777216)); text = undefined;
      }
      if (signal.aborted || token !== getAuthToken() || currentProject.current?.project_id !== original) throw new Error('The account or project changed. Choose the source again.');
      const value = await ingestLearningSource(current, { kind: sourceKind, text, filename, contentBase64, dragonRef: sourceKind === 'dragon' ? dragonRef.trim() : undefined, rightsRefs: permissionRefs }, { signal });
      if (signal.aborted || token !== getAuthToken()) return; acceptProject(value); setSourceText(''); setDragonRef(''); setConsent(false); setNotice('Source ingested with its rights and provenance.');
    });
  };
  const simulate = (reset: boolean, single: boolean) => {
    void perform(reset ? 'Resetting engine' : 'Executing actions', async (current, signal) => {
      const value = await simulateLearningProject(current, { sourceId: selectedSource || undefined, sessionId: reset ? undefined : session?.session_id,
        sessionVersion: reset ? undefined : session?.version, reset, action: action || undefined, steps: reset ? 0 : single ? 1 : integer(steps, 'Steps', 1, 64), seed: integer(seed, 'Seed', 0, 2147483647) }, { signal });
      if (signal.aborted) return; acceptProject(value); const last = value.sessions.at(-1); if (last) setSelectedSession(last.session_id); setNotice(reset ? 'Engine reset; observation recorded.' : 'Measured transitions recorded.');
    });
  };
  const train = () => {
    void perform('Starting local training', async (current, signal) => {
      const selected = availableAlgorithms.find(value => value.id === algorithm);
      if (!selected) throw new Error('Choose an available local learner.');
      const ids = trainSessions.length ? trainSessions : session ? [session.session_id] : [];
      if (!ids.length) throw new Error('Record an engine session before training.');
      const config = { sessionIds: ids, algorithm, epochs: integer(epochs, 'Training episodes', 1, 256), seed: integer(seed, 'Seed', 0, 2147483647), episodeSteps: integer(steps, 'Episode steps', 1, 64), sourceId: selectedSource || undefined, freshPolicy: !continueLearning || !current.policy_id };
      const fingerprint = JSON.stringify({ projectId: current.project_id, version: current.version, config });
      if (trainAttempt.current?.fingerprint !== fingerprint) trainAttempt.current = { fingerprint, key: learningRequestKey('train') };
      const job = await startLearningTraining(current, config, { signal }, trainAttempt.current.key);
      trainAttempt.current = null;
      if (signal.aborted) return; setJobs(values => ({ ...values, [job.job_id]: job })); await refreshProject(); setNotice('Local training accepted. Progress below comes from the running learner.');
    });
  };
  const cancel = (id: string) => { void perform('Stopping job', async (_current, signal) => { const value = await cancelLearningJob(id, { signal }); if (!signal.aborted) setJobs(values => ({ ...values, [id]: value })); }); };
  const resume = (id: string) => { void perform('Resuming job', async (_current, signal) => { const value = await resumeLearningJob(id, { signal }); if (!signal.aborted) setJobs(values => ({ ...values, [id]: value })); }); };
  const generate = () => {
    void perform('Generating game project', async (current, signal) => {
      if (!generationTitle.trim()) throw new Error('Name the original game you want to build.');
      const config = { title: generationTitle.trim(), genre: generationGenre.trim(), complexity: integer(generationComplexity, 'Complexity', 1, 5),
        seed: integer(seed, 'Seed', 0, 2147483647), sourceId: selectedSource || undefined, policyId: current.policy_id || undefined };
      const fingerprint = JSON.stringify({ projectId: current.project_id, version: current.version, config });
      if (generationAttempt.current?.fingerprint !== fingerprint) generationAttempt.current = { fingerprint, key: learningRequestKey('generate') };
      const job = await generateLearningProject(current, config, { signal }, generationAttempt.current.key);
      generationAttempt.current = null;
      if (signal.aborted) return; setJobs(values => ({ ...values, [job.job_id]: job })); await refreshProject(); setNotice('Generation accepted. The server will record the resulting files and lineage.');
    });
  };
  const download = (jobId?: string) => { void perform('Preparing export', async (current, signal) => { const token = getAuthToken(); const file = await exportLearningProject(current, { signal }, jobId); if (!signal.aborted && token === getAuthToken()) { await saveLearningExport(file); setNotice('Project export prepared.'); } }); };
  const consoleList = useMemo(() => catalogue?.consoles.filter(value => `${value.label} ${value.family || ''}`.toLowerCase().includes(consoleQuery.toLowerCase())) || [], [catalogue, consoleQuery]);
  const visibleProjects = [...projects].sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
  const library = <View style={[s.sidebar, compact && s.mobileSidebar]}>
    <View style={s.between}><Text style={s.title}>Projects</Text>{compact && <IconButton label="Close projects" icon="close-outline" onPress={() => setSidebar(false)} />}</View>
    <Button label="New project" icon="add-outline" primary disabled={!!busy || !catalogue} onPress={() => { setSidebar(false); setNewProject(true); }} />
    <ScrollView style={s.sidebarList} contentContainerStyle={s.listContent} keyboardShouldPersistTaps="handled">
      {!projects.length && <Text style={s.muted}>Create a project to start editing, observing, and learning.</Text>}
      {visibleProjects.map(value => <TouchableOpacity key={value.project_id} accessibilityRole="button" accessibilityLabel={`Open ${value.name}`}
        accessibilityState={{ selected: value.project_id === project?.project_id, disabled: !!busy }} disabled={!!busy}
        onPress={() => { if (dirty) { setError('Save or reload your editor changes before switching projects.'); setSidebar(false); } else void openProject(value.project_id); }}
        style={[s.project, value.project_id === project?.project_id && s.selected]}>
        <Text numberOfLines={2} style={s.projectName}>{value.name}</Text><Text style={s.muted}>{catalogue?.consoles.find(console => console.console_id === value.console_id)?.label || value.console_id}</Text>
        <Text style={s.dim}>Revision {value.version}{value.updated_at ? ` · ${new Date(value.updated_at).toLocaleDateString()}` : ''}</Text>
      </TouchableOpacity>)}
    </ScrollView>
    <View style={s.between}><IconButton label="Return home" icon="home-outline" onPress={() => router.replace('/product')} />
      <Text style={s.muted}>Jeeves studio</Text><IconButton label="Refresh studio" icon="refresh-outline" disabled={!!busy} onPress={() => { void initialize(); }} /></View>
  </View>;
  return <SafeAreaView style={s.root}><KeyboardAvoidingView style={s.main} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
    <View style={[s.header, compact && s.compactHeader]}><View style={[s.row, { flex: 1 }]}>
      {compact && <IconButton label="Open projects" icon="menu-outline" onPress={() => setSidebar(true)} />}
      <View style={{ gap: 4, flex: 1 }}><Text numberOfLines={1} style={s.title}>{project?.name || 'Game learning studio'}</Text>
        <Text style={s.subtitle}>{project ? `${profile?.label || project.console_id} · Revision ${project.version}` : 'Edit, run, and learn from real local game sessions'}</Text></View></View>
      {!narrow && <Button label="New project" icon="add-outline" disabled={!!busy || !catalogue} onPress={() => setNewProject(true)} />}
    </View>
    <View style={s.body}>{!compact && library}<View style={s.main}>
      {!!project && <View style={s.tabs}>{TABS.map(value => <TouchableOpacity key={value.id} accessibilityRole="tab"
        accessibilityState={{ selected: tab === value.id }} onPress={() => setTab(value.id)} style={[s.tab, tab === value.id && s.activeTab]}>
        <Ionicons name={value.icon} size={17} color={tab === value.id ? C.primaryHover : C.textMuted} /><Text style={[s.tabText, tab === value.id && s.activeText]}>{value.label}</Text>
      </TouchableOpacity>)}</View>}
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={[s.content, compact && s.compactContent]}>
        {!!error && <View style={s.alert} accessibilityRole="alert"><View style={s.between}><Text style={[s.error, { flex: 1 }]}>{error}</Text>
          <IconButton label="Dismiss error" icon="close-outline" onPress={() => setError(null)} /></View>
          {conflict && <Button label="Refresh server revision" icon="refresh-outline" disabled={!!busy} onPress={() => { void refreshProject().then(() => setConflict(false)).catch(caught => setError(caught.message)); }} />}
          {!project && <Button label="Refresh studio" icon="refresh-outline" onPress={() => { void initialize(); }} />}
        </View>}
        {!!notice && <Text style={s.notice} accessibilityLiveRegion="polite">{notice}</Text>}
        {!!busy && <View style={s.row}><ActivityIndicator size="small" color={C.primaryHover} /><Text style={s.muted}>{busy}…</Text></View>}
        {loading ? <View style={s.loading}><ActivityIndicator color={C.primaryHover} /><Text style={s.muted}>Opening the studio…</Text></View> : !project ? <View style={s.empty}>
          <View style={s.heroIcon}><Ionicons name="game-controller-outline" size={32} color={C.primaryHover} /></View>
          <Text accessibilityRole="header" style={s.hero}>Build a game. Teach Jeeves how it works.</Text>
          <Text style={s.description}>Choose a platform, edit its project, ingest sources you’re permitted to use, and record actual engine transitions for local learning.</Text>
          <Text style={s.description}>The catalogue identifies reference simulations and supported ROM execution separately.</Text>
          <Button label="Create a project" icon="add-outline" primary disabled={!catalogue} onPress={() => setNewProject(true)} />
        </View> : <>
          <View style={s.alert}><View style={s.between}><Text style={s.badge}>{human(profile?.engine_kind || 'Runtime status unavailable')}</Text>
            <Text style={ready ? s.success : s.unavailable}>{ready ? 'Ready' : 'Unavailable'}</Text></View>
            <Text style={s.description}>{profile?.readiness?.message || profile?.description || 'Refresh the catalogue for current runtime capabilities.'}</Text>
          </View>
          {tab === 'editor' && <>
            <Section title="Project source" detail="Changes are saved to this project’s exact server revision. They run only through the selected engine.">
              <View style={s.between}><Text style={dirty ? s.unsaved : s.success}>{dirty ? 'Unsaved changes' : 'Saved source'} · revision {editorVersion}</Text>
                <View style={s.row}><Button label="Add file" icon="add-outline" disabled={!!busy || editorFiles.length >= 96} onPress={() => { setNewPath(''); setAddFile(true); }} />
                  <Button label="Save" icon="save-outline" primary disabled={!!busy || !dirty} onPress={save} /></View></View>
              {editorChanged && <View style={s.alert}><Text style={s.description}>The server revision changed. Your local edit is retained; saving it will require resolving that revision conflict.</Text>
                <Button label="Copy current edit" icon="copy-outline" onPress={() => { void Clipboard.setStringAsync(code); }} />
                <Button label="Reload current server files" icon="refresh-outline" disabled={!!busy} onPress={() => { resetEditor(project); setNotice('Editor reloaded from the current server revision.'); }} /></View>}
              <ScrollView horizontal contentContainerStyle={s.fileTabs} showsHorizontalScrollIndicator>{editorFiles.map(file => <TouchableOpacity key={file.path}
                accessibilityRole="tab" accessibilityLabel={`Edit ${file.path}`} accessibilityState={{ selected: file.path === selectedFile }} onPress={() => setSelectedFile(file.path)}
                style={[s.fileTab, selectedFile === file.path && s.selected]}><Ionicons name="document-text-outline" size={15} color={C.textMuted} />
                <Text style={s.fileName}>{file.path}{drafts[file.path] !== file.content ? ' •' : ''}</Text></TouchableOpacity>)}</ScrollView>
              {!currentFile && <Text style={s.muted}>This project has no source files yet. Add a file to begin editing.</Text>}
              {!!currentFile && <View style={s.editor}><View style={s.editorToolbar}><Text style={s.label}>{currentFile?.language || profile?.editor_language || 'Source'}</Text>
                {(currentFile?.language === 'json' || selectedFile.endsWith('.json')) && <Button label="Format JSON" disabled={!!busy} onPress={() => {
                  try { dirtyRef.current = true; setDrafts(values => ({ ...values, [selectedFile]: JSON.stringify(JSON.parse(code), null, 2) })); } catch { setError('This file is not valid JSON yet.'); }
                }} />}</View>
                <ScrollView horizontal><View style={s.editorBody}><View style={s.lineNumbers}>{code.split('\n').slice(0, 2000).map((_, index) => <Text key={index} style={s.lineNumber}>{index + 1}</Text>)}</View>
                  <TextInput multiline value={code} onChangeText={value => { dirtyRef.current = true; setDrafts(values => ({ ...values, [selectedFile]: value })); }}
                    editable={!busy} maxLength={MAX_FILE_BYTES} style={s.code} accessibilityLabel={`Source editor for ${selectedFile}`}
                    autoCapitalize="none" autoCorrect={false} spellCheck={false} textAlignVertical="top" />
                </View></ScrollView>
              </View>}
              <Text style={s.dim}>{Platform.OS === 'web' ? 'Ctrl / ⌘ + S to save · ' : ''}{new TextEncoder().encode(code).byteLength.toLocaleString()} / 128,000 bytes</Text>
            </Section>
          </>}
          {tab === 'sources' && <>
            <Section title="Ingest a source" detail="Only supported formats are admitted. Rights and original source identity are retained for learning and generation.">
              <View style={s.chips}>{(profile?.supported_source_kinds || []).map(kind => <TouchableOpacity key={kind} accessibilityRole="radio" accessibilityState={{ selected: sourceKind === kind }}
                style={[s.chip, sourceKind === kind && s.selected]} onPress={() => setSourceKind(kind)}><Text style={[s.chipText, sourceKind === kind && s.activeText]}>{kind === 'rom' ? 'ROM / cartridge' : kind === 'dragon' ? 'Dragon source' : kind === 'project' ? 'Project archive' : 'Text / document'}</Text></TouchableOpacity>)}</View>
              {sourceKind === 'text' && <Field label="Source text" value={sourceText} change={setSourceText} multiline maxLength={128000} placeholder="Paste notes, a trace, or original game design material…" />}
              {sourceKind === 'dragon' && <>
                <Field label="Existing Dragon source reference" value={dragonRef} change={setDragonRef} maxLength={512} placeholder="dragon:source-id:reviewed-revision" />
                <Button label="Browse reviewed Dragon sources" icon="library-outline" disabled={!!busy} onPress={() => { void perform('Loading reviewed sources', async (_current, signal) => { const sources = await getReviewedDragonSources({ signal }); if (!signal.aborted) setDragonSources(sources); }); }} />
                {dragonSources.map(source => <TouchableOpacity key={source.source_ref} style={[s.source, dragonRef === source.source_ref && s.selected]} accessibilityRole="radio"
                  accessibilityState={{ checked: dragonRef === source.source_ref }} onPress={() => setDragonRef(source.source_ref)}><Text style={s.projectName}>{source.title}</Text>{source.url && <Text numberOfLines={2} style={s.muted}>{source.url}</Text>}</TouchableOpacity>)}
              </>}
              {sourceKind === 'rom' && <Text style={s.description}>Choose a ROM file you’re permitted to use. Ingestion confirms its format; executable hardware support is reported separately.</Text>}
              {sourceKind === 'project' && <Text style={s.description}>Choose a supported original project archive. File paths, source bytes, and format are validated before admission.</Text>}
              <Field label="Rights / permission references" value={rights} change={setRights} maxLength={4096} placeholder="One reference per line, or comma separated" multiline />
              <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: consent }} onPress={() => setConsent(value => !value)} style={s.checkbox}>
                <View style={[s.checkboxBox, consent && s.checked]}>{consent && <Ionicons name="checkmark" size={17} color={C.text} />}</View>
                <Text style={s.checkboxText}>I own this material or have permission to use it for game learning and original project generation.</Text>
              </TouchableOpacity>
              <View style={s.chips}><Button label={sourceKind === 'rom' ? 'Choose ROM file' : sourceKind === 'project' ? 'Choose project archive' : sourceKind === 'dragon' ? 'Ingest Dragon source' : 'Ingest text'} icon="cloud-upload-outline" primary
                disabled={!!busy || !consent || !rights.trim() || sourceKind === 'text' && !sourceText.trim() || sourceKind === 'dragon' && !dragonRef.trim()}
                onPress={() => ingest(sourceKind === 'rom' || sourceKind === 'project')} />
                {sourceKind === 'text' && <Button label="Choose document file" icon="document-outline" disabled={!!busy || !consent || !rights.trim()} onPress={() => ingest(true)} />}</View>
            </Section>
            <Section title="Project sources">
              {!project.sources.length && <Text style={s.muted}>No sources have been ingested yet.</Text>}
              {project.sources.map(source => <View key={source.source_id} style={s.source}><View style={s.between}><Text style={s.projectName}>{source.filename || human(source.kind)}</Text><Text style={s.badge}>{source.status ? human(source.status) : human(source.kind)}</Text></View>
                {!!source.summary && <Text style={s.description}>{source.summary}</Text>}<Text style={s.rights}>Rights: {source.rights_refs.join(', ')}</Text>
                <Text style={source.state === 'revoked' ? s.unavailable : s.muted}>{source.state === 'revoked' ? 'Withdrawn from learning' : 'Format evidence recorded; execution support is reported by the runtime.'}</Text>
                {source.bundle?.warnings?.slice(0, 6).map((warning, index) => <Text key={index} style={s.muted}>{warning}</Text>)}
                {!!source.source_digest && <Text selectable style={s.reference}>{source.source_digest}</Text>}
                {!!source.lineage_refs?.length && <Lineage refs={source.lineage_refs} />}
                {source.state !== 'revoked' && <Button label="Withdraw source" icon="remove-circle-outline" disabled={!!busy} onPress={() => setWithdrawSource(source.source_id)} />}</View>)}
            </Section>
          </>}
          {tab === 'observe' && <View style={narrow ? undefined : s.split}>
            <View style={s.column}><Section title="Live engine observation"><Observation session={session} />
              <Metrics values={session ? { ...(session.steps !== undefined ? { steps: session.steps } : {}), ...(session.total_reward !== undefined ? { total_reward: session.total_reward } : {}), ...(session.terminated !== undefined ? { terminated: session.terminated } : {}), ...(session.truncated !== undefined ? { truncated: session.truncated } : {}), ...session.metrics } : undefined} />
            </Section><Section title="Observation lineage"><Lineage refs={session?.lineage_refs} />{!!session?.snapshot_digest && <Text selectable style={s.reference}>Snapshot: {session.snapshot_digest}</Text>}</Section></View>
            <View style={s.column}><Section title="Engine controls" detail="Actions execute in the registered runtime and record measured transitions.">
              {project.sources.find(source => source.source_id === selectedSource)?.kind === 'rom' && !profile?.engine_kind.toLowerCase().includes('rom') && <Text style={s.description}>This profile runs the project’s reference simulation. The selected ROM is retained as format and provenance evidence.</Text>}
              {!!project.sources.length && <><Text style={s.label}>Source</Text><View style={s.chips}>{project.sources.map(source => <TouchableOpacity key={source.source_id} accessibilityRole="radio"
                accessibilityState={{ selected: selectedSource === source.source_id }} onPress={() => setSelectedSource(source.source_id)} style={[s.chip, selectedSource === source.source_id && s.selected]}><Text style={s.chipText}>{source.filename || human(source.kind)}</Text></TouchableOpacity>)}</View></>}
              {!!project.sessions.length && <><Text style={s.label}>Recorded session</Text><View style={s.chips}>{project.sessions.slice(-8).map((value, index) => <TouchableOpacity key={value.session_id}
                accessibilityRole="radio" accessibilityState={{ selected: session?.session_id === value.session_id }} onPress={() => setSelectedSession(value.session_id)} style={[s.chip, session?.session_id === value.session_id && s.selected]}><Text style={s.chipText}>Session {Math.max(0, project.sessions.length - 8) + index + 1}</Text></TouchableOpacity>)}</View></>}
              <Text style={s.label}>Action</Text><View style={s.chips}>{runtimeActions.map(value => <TouchableOpacity key={value} accessibilityRole="radio" accessibilityState={{ selected: action === value }}
                onPress={() => setAction(value)} style={[s.chip, action === value && s.selected]}><Text style={s.chipText}>{human(value)}</Text></TouchableOpacity>)}</View>
              <Field label="Deterministic seed" numeric value={seed} change={setSeed} maxLength={10} />
              <Field label="Steps per batch / training episode (1–64)" numeric value={steps} change={setSteps} maxLength={2} />
              <View style={s.chips}><Button label="Reset" icon="refresh-outline" disabled={!!busy || !ready || dirty} onPress={() => simulate(true, true)} />
                <Button label="Step" icon="play-skip-forward-outline" primary disabled={!!busy || !ready || !session || !!session.terminated || !!session.truncated || dirty || !action || !session.version} onPress={() => simulate(false, true)} />
                <Button label="Run batch" icon="play-outline" disabled={!!busy || !ready || !session || !!session.terminated || !!session.truncated || dirty || !action || !session.version} onPress={() => simulate(false, false)} /></View>
              {dirty && <Text style={s.unsaved}>Save your source changes before running the engine.</Text>}
            </Section></View>
          </View>}
          {tab === 'learn' && <>
            <Section title="Local learning" detail="Train a candidate from real engine observations. Measured evaluation and checkpoints stay separate from production promotion.">
              <Text style={s.label}>Learner</Text><View style={s.chips}>{(catalogue?.algorithms || []).map(value => <TouchableOpacity key={value.id} accessibilityRole="radio"
                accessibilityState={{ selected: algorithm === value.id, disabled: !value.available }} disabled={!value.available} onPress={() => setAlgorithm(value.id)} style={[s.chip, algorithm === value.id && s.selected]}><Text style={s.chipText}>{value.label}{!value.available ? ' · unavailable' : ''}</Text></TouchableOpacity>)}</View>
              {!availableAlgorithms.length && <Text style={s.unavailable}>No local learner is ready. Refresh the catalogue to check again.</Text>}
              <Text style={s.label}>Measured sessions for lineage</Text><View style={s.chips}>{project.sessions.map((value, index) => <TouchableOpacity key={value.session_id} accessibilityRole="checkbox"
                accessibilityState={{ checked: trainSessions.includes(value.session_id) }} onPress={() => setTrainSessions(current => current.includes(value.session_id) ? current.filter(id => id !== value.session_id) : [...current, value.session_id])}
                style={[s.chip, trainSessions.includes(value.session_id) && s.selected]}><Text style={s.chipText}>Session {index + 1}</Text></TouchableOpacity>)}</View>
              {!project.sessions.length && <Text style={s.muted}>Use Play & observe to record an engine session first.</Text>}
              <View style={narrow ? { gap: 12 } : s.split}><View style={s.column}><Field label="Training episodes (1–256)" numeric value={epochs} change={setEpochs} maxLength={3} /></View>
                <View style={s.column}><Field label="Seed" numeric value={seed} change={setSeed} maxLength={10} /></View></View>
              {!!project.policy_id && <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: continueLearning }} onPress={() => setContinueLearning(value => !value)} style={s.checkbox}>
                <View style={[s.checkboxBox, continueLearning && s.checked]}>{continueLearning && <Ionicons name="checkmark" size={17} color={C.text} />}</View>
                <Text style={s.checkboxText}>Continue from the current learned candidate. Uncheck to start a fresh policy after changing its environment.</Text>
              </TouchableOpacity>}
              <Button label="Start local training" icon="analytics-outline" primary disabled={!!busy || !ready || !availableAlgorithms.length || !project.sessions.length || !!runningJobs.length || dirty} onPress={train} />
            </Section>
            <Section title="Measured learning jobs">{!allJobs.filter(job => job.kind !== 'generate' && job.kind !== 'generation').length && <Text style={s.muted}>Training metrics and checkpoints will appear after a real job starts.</Text>}
              {allJobs.filter(job => job.kind !== 'generate' && job.kind !== 'generation').slice(0, 12).map(job => <JobCard key={job.job_id} job={job} busy={!!busy} cancel={cancel} resume={resume} />)}</Section>
            <Section title="Project learning lineage"><Lineage refs={project.lineage_refs} /><Metrics values={project.metrics} /></Section>
          </>}
          {tab === 'build' && <>
            <Section title="Generate an original game project" detail="Create compatible original source from this project’s metadata and recorded learning lineage. Source ROM code and assets are not copied into generated output.">
              <Field label="Original game title" value={generationTitle} change={setGenerationTitle} maxLength={120} placeholder="Name your original game…" />
              {catalogue?.generation_genres?.length ? <View style={s.chips}>{catalogue.generation_genres.map(genre => <TouchableOpacity key={genre.id}
                accessibilityRole="radio" accessibilityState={{ checked: generationGenre === genre.id }} onPress={() => setGenerationGenre(genre.id)} style={[s.chip, generationGenre === genre.id && s.selected]}><Text style={s.chipText}>{genre.label}</Text></TouchableOpacity>)}</View> :
                <Field label="Registered genre / controller" value={generationGenre} change={setGenerationGenre} maxLength={64} />}
              <View style={narrow ? { gap: 12 } : s.split}><View style={s.column}><Field label="Complexity (1–5)" value={generationComplexity} change={setGenerationComplexity} numeric maxLength={1} /></View>
                <View style={s.column}><Field label="Generation seed" value={seed} change={setSeed} numeric maxLength={10} /></View></View>
              {project.policy_id && <Text style={s.description}>The current learned policy is included when its recorded environment is compatible.</Text>}
              <Button label="Generate project" icon="sparkles-outline" primary disabled={!!busy || !generationTitle.trim() || dirty || !!runningJobs.length} onPress={generate} />
            </Section>
            {allJobs.filter(job => job.kind === 'generate' || job.kind === 'generation').slice(0, 8).map(job => <View key={job.job_id} style={{ gap: 12 }}>
              <JobCard job={job} busy={!!busy} cancel={cancel} resume={resume} />
              {job.status === 'completed' && !generatedFiles(job).length && <Button label="Load generated files" icon="document-text-outline" disabled={!!busy} onPress={() => {
                void perform('Loading candidate source', async (current, signal) => { const value = await getLearningJob(job.job_id, { signal }); if (value.project_id !== current.project_id) throw new Error('This candidate belongs to a different project.'); if (!signal.aborted) setJobs(values => ({ ...values, [value.job_id]: value })); });
              }} />}
              {!!generatedFiles(job).length && <Section title="Generated candidate source">
                <View style={s.chips}><Button label="Add generated files to editor" icon="code-slash-outline" disabled={!!busy || dirty} onPress={() => {
                  const files = generatedFiles(job); const merged = [...new Map([...editorFiles, ...files].map(file => [file.path, file])).values()];
                  if (merged.length > 96 || merged.reduce((total, file) => total + new TextEncoder().encode(file.content).byteLength, 0) > 1000000) { setError('The generated source exceeds this project’s file bounds. Download it as a separate candidate.'); return; }
                  dirtyRef.current = true; setEditorFiles(merged); setDrafts(Object.fromEntries(merged.map(file => [file.path, file.content]))); setSelectedFile(files[0]?.path || selectedFile); setTab('editor'); setNotice('Generated files added as unsaved edits. Save to adopt this candidate.');
                }} /><Button label="Download candidate bundle" icon="download-outline" disabled={!!busy} onPress={() => download(job.job_id)} /></View>
                {generatedFiles(job).map(file => <View key={file.path} style={s.checkpoint}><Text style={s.fileName}>{file.path}</Text><Text style={s.dim}>{new TextEncoder().encode(file.content).byteLength.toLocaleString()} bytes</Text></View>)}
              </Section>}
            </View>)}
            {!!project.generated_projects?.length && <Section title="Generated projects">{project.generated_projects.map((generated, index) => <View key={generated.generated_id || String(index)} style={s.source}>
              <Text style={s.projectName}>{generated.name || `Generated project ${index + 1}`}</Text>{generated.target && <Text style={s.muted}>Target: {generated.target}</Text>}
              {generated.files?.map(file => <View key={file.path} style={{ gap: 6 }}><Text style={s.fileName}>{file.path}</Text><Text selectable style={s.observationText}>{file.content.slice(0, 12000)}</Text></View>)}<Lineage refs={generated.lineage_refs} />
            </View>)}</Section>}
            <Section title="Export the current project" detail="Download the exact saved project bundle, generated files, and declared target information from the server.">
              <Button label={Platform.OS === 'web' ? 'Download project bundle' : 'Save or share project bundle'} icon="download-outline" disabled={!!busy || dirty} onPress={() => download()} />
              {dirty && <Text style={s.unsaved}>Save source changes before exporting.</Text>}
            </Section>
          </>}
        </>}
      </ScrollView>
    </View></View>
    {compact && sidebar && <Modal visible animationType="slide" onRequestClose={() => setSidebar(false)}><SafeAreaView style={s.root}>{library}</SafeAreaView></Modal>}
    {newProject && <Dialog title="New game-learning project" close={() => { if (!busy) setNewProject(false); }}>
      <Field label="Project name" value={projectName} change={setProjectName} maxLength={160} placeholder="Name your original project" />
      <Field label="Find a console or PC profile" value={consoleQuery} change={setConsoleQuery} maxLength={100} placeholder="Search platforms…" />
      <ScrollView style={s.dialogScroll} contentContainerStyle={s.consoleList} keyboardShouldPersistTaps="handled">{consoleList.map(value => <TouchableOpacity key={value.console_id} accessibilityRole="radio"
        accessibilityState={{ selected: consoleId === value.console_id }} style={[s.console, consoleId === value.console_id && s.selected]} onPress={() => setConsoleId(value.console_id)}>
        <View style={s.between}><Text style={s.projectName}>{value.label}</Text><Text style={value.available ? s.success : s.unavailable}>{value.available ? 'Ready' : 'Unavailable'}</Text></View>
        <Text style={s.badge}>{human(value.engine_kind)}</Text><Text style={s.description}>{value.readiness?.message || value.description}</Text>
      </TouchableOpacity>)}</ScrollView>
      <Button label={busy ? 'Creating…' : 'Create project'} icon="add-outline" primary disabled={!!busy || !projectName.trim() || !consoleId} onPress={() => { void create(); }} />
      {!!error && <Text style={s.error}>{error}</Text>}
    </Dialog>}
    {addFile && <Dialog title="Add a source file" close={() => setAddFile(false)}>
      <Field label="Relative file path" value={newPath} change={setNewPath} maxLength={160} placeholder="src/game.py" />
      <Text style={s.description}>The file becomes part of the server project when you save the editor.</Text>
      <Button label="Add to editor" primary disabled={!newPath.trim() || !!busy} onPress={() => {
        const path = newPath.trim();
        if (path.startsWith('/') || path.includes('\\') || path.split('/').some(part => !part || part === '.' || part === '..') || editorFiles.some(file => file.path === path)) { setError('Choose a new relative path without parent traversal.'); return; }
        const language = path.endsWith('.json') ? 'json' : path.endsWith('.py') ? 'python' : path.endsWith('.js') ? 'javascript' : path.endsWith('.lua') ? 'lua' : 'text';
        dirtyRef.current = true; setEditorFiles(values => [...values, { path, content: '', language }]); setDrafts(values => ({ ...values, [path]: '' })); setSelectedFile(path); setAddFile(false);
      }} />
    </Dialog>}
    {withdrawSource && <Dialog title="Withdraw this source?" close={() => { if (!busy) setWithdrawSource(null); }}>
      <Text style={s.description}>The source will be blocked from future learning and generation. Work that depends on its authority will be fenced; provenance is retained.</Text>
      <View style={s.chips}><Button label="Keep source" disabled={!!busy} onPress={() => setWithdrawSource(null)} />
        <Button label="Withdraw source" icon="remove-circle-outline" disabled={!!busy} onPress={() => {
          void perform('Withdrawing source', async (current, signal) => { const value = await revokeLearningSource(current, withdrawSource, { signal }); if (!signal.aborted) { acceptProject(value); setWithdrawSource(null); setNotice('Source withdrawn from future learning and generation.'); } });
        }} /></View>
    </Dialog>}
  </KeyboardAvoidingView></SafeAreaView>;
}
