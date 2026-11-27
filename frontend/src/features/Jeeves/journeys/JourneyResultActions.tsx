/** Review typed AI data, then use the existing notebook, task and studio owners. */
import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { CryptoDigestAlgorithm, digestStringAsync } from 'expo-crypto';
import { getAuthEpoch, subscribeAuthChanges } from '../../../auth/gameforgeAuth';
import { validateJourneyArtifact } from '../../../product/aiJourneyClient';
import { getLearningProject, listLearningProjects, type LearningProject, type LearningProjectSummary } from '../../../product/gameLearningClient';
import { createStudioGoal, listStudioGoals, type StudioGoal } from '../../../product/gameStudioAgentClient';
import ChatStoryActions from '../ChatStoryActions';
import ChatSceneActions from '../ChatSceneActions';
import GameStudioAssistantPanel from '../GameStudioAssistantPanel';
import { workbenchStore as store } from '../workbench/store';
import { undoChatTasks } from '../workbench/chatTaskAdapter';
import { prepareJourneyCommit, commitJourneyArtifact } from './journeyWorkbench';
import { artifactText, canonicalJourneyJSON, existingStudioHandoff, readJourneyArtifact, readJourneyEnvelope, studioDestinationUnavailable, studioHandoffSpec, type JourneyArtifact, type JourneyPreview } from './journeyDraft';
import { JourneyButton, JourneyDialog, JourneyField, colors, human, ui } from './journeyUI';

function ArtifactEditor({ value, change, disabled }: { value: JourneyArtifact; change: (value: JourneyArtifact) => void; disabled: boolean }) {
  const collection = ['claims', 'tasks', 'cards', 'items', 'steps'].find(key => Array.isArray(value[key]));
  const rows = collection ? value[collection] as Record<string, unknown>[] : [];
  const updateRow = (index: number, key: string, next: unknown) => {
    if (collection) change({ ...value, [collection]: rows.map((row, at) => index === at ? { ...row, [key]: next } : row) });
  };
  return <View style={ui.stack}>
    <JourneyField label="Result title" value={value.title} maxLength={160} onChange={title => change({ ...value, title })} disabled={disabled} testID="journey-result-title" />
    {['summary', 'goal'].filter(key => typeof value[key] === 'string').map(key => <JourneyField key={key} label={human(key)} value={String(value[key])} multiline disabled={disabled} onChange={text => change({ ...value, [key]: text })} />)}
    {rows.map((row, index) => <View key={index} style={ui.card}><View style={ui.row}><Text style={ui.title}>{human(collection || 'item')} {index + 1}</Text><JourneyButton label={'Remove item ' + (index + 1)} disabled={disabled || rows.length <= 1} onPress={() => collection && change({ ...value, [collection]: rows.filter((_, at) => at !== index) })} /></View>
      {Object.entries(row).map(([key, content]) => {
        if (key === 'id') return <Text key={key} style={ui.muted}>Reference: {String(content)}</Text>;
        if (key === 'confidence') return <View key={key} style={ui.stack}><Text style={ui.label}>Proposed confidence</Text><View style={ui.row}>{['supported', 'uncertain', 'contradicted'].map(option => <JourneyButton key={option} label={human(option)} selected={content === option} disabled={disabled} onPress={() => updateRow(index, key, option)} />)}</View><Text style={ui.muted}>Source references and structure can be checked; this label does not establish factual accuracy.</Text></View>;
        if (key === 'correct_choice') return <View key={key} style={ui.stack}><Text style={ui.label}>Correct answer</Text><View style={ui.row}><JourneyButton label="Short answer" disabled={disabled} selected={content === null} onPress={() => updateRow(index, key, null)} />{(Array.isArray(row.choices) ? row.choices : []).map((choice, at) => <JourneyButton key={at} label={String(choice)} selected={content === at} disabled={disabled} onPress={() => { if (collection) change({ ...value, [collection]: rows.map((current, position) => position === index ? { ...current, correct_choice: at, answer: String(choice) } : current) }); }} />)}</View></View>;
        if (Array.isArray(content)) return <JourneyField key={key} label={human(key) + (key === 'depends_on' || key === 'source_ids' ? ' (comma-separated IDs)' : ' (one per line)')} value={content.join(key === 'depends_on' || key === 'source_ids' ? ', ' : '\n')} multiline disabled={disabled} maxLength={8000} onChange={text => updateRow(index, key, text.split(key === 'depends_on' || key === 'source_ids' ? ',' : '\n').map(item => item.trim()).filter(Boolean))} />;
        if (typeof content === 'string' || typeof content === 'number') return <JourneyField key={key} label={human(key)} value={String(content)} multiline={typeof content === 'string' && !['title', 'name', 'role', 'operation'].includes(key)} maxLength={key === 'title' || key === 'name' ? 160 : 4000} disabled={disabled} numeric={typeof content === 'number'} onChange={text => updateRow(index, key, typeof content === 'number' && /^\d+$/.test(text) ? Number(text) : text)} />;
        return null;
      })}
    </View>)}
    {['open_questions', 'completion_requirements'].filter(key => Array.isArray(value[key])).map(key => key === 'completion_requirements'
      ? <Text key={key} style={ui.muted}>Required evidence: {(value[key] as string[]).join(' · ')}</Text>
      : <JourneyField key={key} label={human(key) + ' (one per line)'} value={(value[key] as string[]).join('\n')} multiline disabled={disabled} onChange={text => change({ ...value, [key]: text.split('\n').map(item => item.trim()).filter(Boolean) })} />)}
  </View>;
}

export default function JourneyResultActions({ text, requestText, conversationId, messageId, disabled, notify }: {
  text: string; requestText: string; conversationId: string; messageId: string; disabled?: boolean; notify: (message: string) => void;
}) {
  const envelope = readJourneyEnvelope(requestText);
  return envelope ? <ScopedJourneyResult key={envelope.request_digest + ':' + conversationId + ':' + messageId} {...{ text, conversationId, messageId, disabled, notify }} envelope={envelope} /> : null;
}

function ScopedJourneyResult({ text, envelope, conversationId, messageId, disabled = false, notify }: Omit<Parameters<typeof JourneyResultActions>[0], 'requestText'> & { envelope: NonNullable<ReturnType<typeof readJourneyEnvelope>> }) {
  const router = useRouter();
  const [open, setOpen] = useState(false); const [artifact, setArtifact] = useState<JourneyArtifact | null>(null);
  const [raw, setRaw] = useState(text); const [preview, setPreview] = useState<JourneyPreview | null>(null);
  const [projectId, setProjectId] = useState(''); const [projects, setProjects] = useState<{ id: string; title: string }[]>([]);
  const [error, setError] = useState(''); const [notice, setNotice] = useState(''); const [busy, setBusy] = useState(false);
  const [applied, setApplied] = useState(false); const [appliedRevision, setAppliedRevision] = useState<number | null>(null);
  const [studioProjects, setStudioProjects] = useState<LearningProjectSummary[]>([]); const [studioProject, setStudioProject] = useState<LearningProject | null>(null);
  const [creatorDraftCount, setCreatorDraftCount] = useState(0);
  const [studioGoal, setStudioGoal] = useState<StudioGoal | null>(null); const [showStudio, setShowStudio] = useState(false);
  const commitPlan = useRef<ReturnType<typeof prepareJourneyCommit> | null>(null);
  const generation = useRef(0); const controller = useRef<AbortController | null>(null); const alive = useRef(true); const opened = useRef(false);
  const creating = useRef(false);
  const ownerEpoch = useRef(getAuthEpoch());
  const safe = () => alive.current && ownerEpoch.current === getAuthEpoch();
  useEffect(() => { alive.current = true; const unsubscribe = subscribeAuthChanges(() => { generation.current += 1; controller.current?.abort(); setOpen(false); setArtifact(null); setPreview(null); setRaw(''); setProjects([]); setStudioProjects([]); setCreatorDraftCount(0); setStudioProject(null); setStudioGoal(null); commitPlan.current = null; }); return () => { alive.current = false; generation.current += 1; controller.current?.abort(); unsubscribe(); }; }, []);
  const invalidate = () => { generation.current += 1; controller.current?.abort(); setPreview(null); commitPlan.current = null; setError(''); setNotice(''); };
  const edit = (value: JourneyArtifact) => { invalidate(); setArtifact(value); };
  const show = async () => {
    if (!safe() || disabled) return; opened.current = true; setOpen(true);
    if (creating.current || applied) return;
    setError(''); setNotice('');
    try { if (!artifact) setArtifact(readJourneyArtifact(raw, envelope.request, envelope.request_digest)); }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'The reply could not be parsed.'); }
    await store.initialize(); if (!safe() || !opened.current) return;
    const snapshot = store.getSnapshot(); const choices = snapshot.state.projects.filter(item => item.status !== 'archived');
    setProjects(choices); setProjectId(current => choices.some(item => item.id === current) ? current : snapshot.state.activeProjectId || choices[0]?.id || '');
    if (envelope.request.journey_id === 'studio') {
      try {
        const rows = await listLearningProjects();
        if (safe() && opened.current) {
          const eligible = rows.filter(project => studioDestinationUnavailable(project) === null);
          setStudioProjects(eligible); setCreatorDraftCount(rows.length - eligible.length);
        }
      }
      catch (cause) { if (safe() && opened.current) setError(cause instanceof Error ? cause.message : 'Studio projects are unavailable.'); }
    }
  };
  const close = () => { opened.current = false; generation.current += 1; if (!creating.current) { controller.current?.abort(); setBusy(false); } setOpen(false); };
  const check = async () => {
    if (!artifact || busy || disabled || applied || !safe()) return;
    const attempt = ++generation.current; const abort = new AbortController(); controller.current = abort; const serialized = canonicalJourneyJSON(artifact);
    setBusy(true); setError(''); setNotice(''); setPreview(null); commitPlan.current = null;
    try {
      const value = await validateJourneyArtifact(envelope.request, artifact, abort.signal);
      if (!safe() || !opened.current || attempt !== generation.current || serialized !== canonicalJourneyJSON(artifact)) return;
      if (value.request_digest !== envelope.request_digest) throw new Error('The artifact belongs to a different prepared request.');
      setArtifact(value.artifact); setPreview(value);
      if (value.journey_id !== 'studio' && projectId) commitPlan.current = prepareJourneyCommit(store.getSnapshot().state, projectId, value, { conversationId, messageId, request: envelope.request });
    } catch (cause) { if (safe() && opened.current && attempt === generation.current) setError(cause instanceof Error ? cause.message : 'The result could not be reviewed.'); }
    finally { if (safe() && opened.current && attempt === generation.current) setBusy(false); }
  };
  const save = async () => {
    if (creating.current || busy || disabled || applied || !preview || !commitPlan.current || !safe()) return;
    creating.current = true; setBusy(true); setError('');
    try {
      const value = await commitJourneyArtifact(store, commitPlan.current, safe);
      if (!safe()) return;
      setNotice(value.message); if (opened.current) notify(value.message);
      if (value.status !== 'refused') { setApplied(true); setAppliedRevision(value.status === 'saved' ? value.revision : null); }
      else setError(value.message);
    } finally { creating.current = false; if (safe()) setBusy(false); }
  };
  const selectStudioProject = async (id: string) => {
    invalidate(); setStudioProject(null); setStudioGoal(null); setShowStudio(false);
    const attempt = ++generation.current; setBusy(true);
    try {
      const value = await getLearningProject(id);
      if (!safe() || !opened.current || attempt !== generation.current) return;
      const unavailable = studioDestinationUnavailable(value);
      if (unavailable) throw new Error(unavailable);
      setStudioProject(value);
    }
    catch (cause) { if (safe() && opened.current && attempt === generation.current) setError(cause instanceof Error ? cause.message : 'The studio project could not be read.'); }
    finally { if (safe() && opened.current && attempt === generation.current) setBusy(false); }
  };
  const saveStudioGoal = async () => {
    if (!studioProject || !preview || applied || creating.current || busy || !safe()) return;
    const mode = envelope.request.options.completion_mode === 'original' ? 'original' : 'native';
    creating.current = true; setBusy(true); setError('');
    const abort = new AbortController(); controller.current = abort;
    try {
      const spec = studioHandoffSpec(studioProject.project_id, preview, conversationId, messageId, mode);
      const key = 'journey-goal-' + await digestStringAsync(CryptoDigestAlgorithm.SHA256, spec.keyMaterial);
      if (!safe() || abort.signal.aborted) return;
      const history = await listStudioGoals(studioProject.project_id, { signal: abort.signal });
      if (!safe() || abort.signal.aborted) return;
      const retained = existingStudioHandoff(history, spec);
      const value = retained !== null ? history[retained] : await createStudioGoal(studioProject, { goal: spec.goal, maxSteps: 12, executionMode: 'plan', allowEdits: false, authorizationSeconds: 600, maxModelCalls: 8, maxJobs: 0, max_output_tokens: 1024, completionMode: mode, completionRequirements: [] }, { signal: abort.signal }, key);
      if (!safe() || abort.signal.aborted) return;
      setStudioGoal(value); setApplied(true); setNotice('Plan-only studio goal saved. Its project owner controls execution and any later edit authorization.');
    } catch (cause) { if (safe() && !abort.signal.aborted) setError((cause instanceof Error ? cause.message : 'Goal creation was not confirmed.') + ' Reuse this form to retry the same request, or inspect existing goal history before starting another.'); }
    finally { creating.current = false; if (safe()) setBusy(false); }
  };
  return <><JourneyButton label={applied ? 'View journey result' : 'Review guided result'} onPress={() => { void show(); }} disabled={disabled} testID="journey-result-open" />{open && <JourneyDialog title={human(envelope.request.journey_id) + ' · review your result'} close={close}>
    <Text style={ui.muted}>The response is a proposal. Edit its content, check its structure and source references, then choose its destination. Factual accuracy and actual execution require their own evidence.</Text>
    {!!envelope.request.source_refs.length && <View style={ui.card}><Text style={ui.label}>Available source references</Text>{envelope.request.source_refs.map(source => <Text selectable key={source.id} style={ui.muted}>{source.id} · {source.label}{'\n'}{source.locator}</Text>)}</View>}
    {artifact ? <><ArtifactEditor value={artifact} change={edit} disabled={busy || applied} /><JourneyButton label="Edit response JSON" disabled={busy || applied} onPress={() => { invalidate(); setRaw(JSON.stringify(artifact, null, 2)); setArtifact(null); }} /></> : <><JourneyField label="Structured response JSON" value={raw} onChange={setRaw} multiline maxLength={64000} disabled={busy || applied} testID="journey-result-json" /><JourneyButton label="Read structured reply" onPress={() => { try { invalidate(); setArtifact(readJourneyArtifact(raw, envelope.request, envelope.request_digest)); } catch (cause) { setError(cause instanceof Error ? cause.message : 'The reply is invalid.'); } }} disabled={busy || applied} /></>}
    {envelope.request.journey_id !== 'studio' ? <View style={ui.card}><Text style={ui.title}>Device-local destination</Text><Text style={ui.muted}>Save to the existing workbench on this device. It is separate from your account’s canonical chat history.</Text><View style={ui.row}>{projects.map(project => <JourneyButton key={project.id} label={project.title} selected={projectId === project.id} disabled={busy || applied} onPress={() => { invalidate(); setProjectId(project.id); }} />)}</View>{!projects.length && <Text style={ui.muted}>Create a workbench project before saving this result.</Text>}</View> : <View style={ui.card}><Text style={ui.title}>Choose an owned studio project</Text>{creatorDraftCount > 0 && <Text style={ui.muted}>{creatorDraftCount} saved creator draft(s) can be opened in Dragon. Choose a Game Learning or Forge project for Studio planning.</Text>}{!studioProjects.length && <Text style={ui.muted}>No eligible Studio projects are loaded. Create a project in Game Learning, or use a saved Forge project for source-only planning.</Text>}<View style={ui.row}>{studioProjects.map(project => <JourneyButton key={project.project_id} label={project.name + (project.console_id === 'forge:godot' ? ' · Forge source plan' : '')} selected={studioProject?.project_id === project.project_id} disabled={busy || applied} onPress={() => { void selectStudioProject(project.project_id); }} />)}</View><Text style={ui.muted}>This saves a plan-only goal to the existing studio owner. Running tools, editing assets and starting jobs require the studio’s separate controls.</Text></View>}
    <JourneyButton label="Check edited result" onPress={() => { void check(); }} disabled={!artifact || busy || applied || disabled} testID="journey-result-check" />
    {preview && <View style={ui.card} testID="journey-result-proof"><Text style={ui.title}>Structure checked · awaiting your decision</Text><Text style={ui.muted}>Source identifiers match the references you supplied. No factual or runtime certification is implied.</Text>{preview.journey_id === 'plan' && <><Text style={ui.text}>Total effort: {String(preview.checks.total_minutes)} minutes · Critical path: {String(preview.checks.critical_path_minutes)} minutes · Cost: {String(preview.checks.total_cost)} units</Text><Text style={ui.muted}>Dependency order: {Array.isArray(preview.checks.topological_order) ? preview.checks.topological_order.join(' → ') : 'Unavailable'}</Text><Text style={ui.muted}>Time budget: {preview.checks.within_time_budget ? 'within' : 'exceeded'} · Cost budget: {preview.checks.within_cost_budget ? 'within' : 'exceeded'}. These checks cover the declared task graph.</Text></>}{preview.warnings.map(warning => <Text key={warning} style={ui.muted}>{warning}</Text>)}<JourneyButton label={preview.journey_id === 'studio' ? 'Save reviewed plan-only studio goal' : 'Save reviewed result to Workbench'} onPress={() => { void (preview.journey_id === 'studio' ? saveStudioGoal() : save()); }} disabled={busy || applied || disabled || (preview.journey_id === 'studio' ? !studioProject : !commitPlan.current)} testID="journey-result-save" /></View>}
    {preview?.journey_id === 'creative' && <View style={ui.card}><Text style={ui.title}>Continue with the existing creative tools</Text><ChatStoryActions text={artifactText(preview.artifact)} conversationId={conversationId} messageId={messageId} notify={notify} /><ChatSceneActions text={'Scene design\n' + artifactText(preview.artifact)} conversationId={conversationId} messageId={messageId} notify={notify} /><JourneyButton label="Open game-learning quest and cast editors" onPress={() => router.push('/game-learning')} /></View>}
    {studioGoal && studioProject && <View style={ui.card}><Text style={ui.success}>Saved goal: {studioGoal.goal_id} · {studioGoal.status}</Text><JourneyButton label={showStudio ? 'Hide scoped studio controls' : 'Open existing scoped studio controls'} onPress={() => setShowStudio(value => !value)} />{showStudio && <GameStudioAssistantPanel key={studioProject.project_id} project={studioProject} initialGoalId={studioGoal.goal_id} onSaved={setStudioProject} onJob={job => notify('Studio job recorded: ' + job.job_id)} />}</View>}
    {appliedRevision !== null && <JourneyButton label="Undo this exact workbench save" disabled={busy} onPress={() => { setBusy(true); void undoChatTasks(store, appliedRevision).then(undone => { if (!safe() || !opened.current) return; if (undone) { setAppliedRevision(null); setNotice('The reviewed result was removed and the undo was saved.'); } else setError('Workbench changed after this save. Open it to review the latest records before undoing.'); }).finally(() => { if (safe() && opened.current) setBusy(false); }); }} />}
    {applied && envelope.request.journey_id !== 'studio' && <JourneyButton label={envelope.request.journey_id === 'study' ? 'Open Workbench study and practice' : 'Open saved work in Workbench'} onPress={() => router.push('/jeeves-workbench')} testID="journey-result-workbench" />}
    {busy && <View style={ui.row}><ActivityIndicator color={colors.accent} /><Text style={ui.muted}>Checking the current owner and saved state…</Text></View>}{error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}{notice && <Text accessibilityLiveRegion="polite" style={ui.success}>{notice}</Text>}
  </JourneyDialog>}</>;
}
