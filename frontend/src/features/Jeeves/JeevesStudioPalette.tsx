/** Jeeves' interactive game-studio cockpit. No model-authored effect is executed
 * by this component: each action is a reviewed draft or a real editor route.
 * The game-studio goal runner owns actual execution, authorization and receipts.
 */
import React, { useEffect, useMemo, useState } from 'react';
import { Modal, ScrollView, Text, TextInput, TouchableOpacity, View } from 'react-native';
import {
  advanceStudioGoal, createStudioGoal, getStudioGoal, type StudioGoal,
} from '../../product/gameStudioAgentClient';
import {
  getLearningProject, listLearningProjects, type LearningProjectSummary,
} from '../../product/gameLearningClient';

type Route = '/galaxy' | '/gameforge-studio' | '/forge-hub' | '/worldforge'
  | '/studio' | '/media-studio' | '/physics-studio' | '/game-learning'
  | '/jeeves-workbench' | '/skeleton-studio' | '/construct-forge'
  | '/systems-forge' | '/world-workbench' | '/jeeves-hub';

type Domain = { id: string; title: string; question: string; route: Route; family: string };
export const JEEVES_STUDIO_DOMAINS: readonly Domain[] = [
  { id: 'vision', title: 'Game vision', question: 'What is the distinctive player fantasy?', route: '/galaxy', family: 'Design' },
  { id: 'platform', title: 'Platforms & eras', question: 'Which consoles, SDKs and hardware tiers?', route: '/gameforge-studio', family: 'Engineering' },
  { id: 'engine', title: 'Engines', question: 'Which rendering and runtime targets?', route: '/gameforge-studio', family: 'Engineering' },
  { id: 'scope', title: 'Production scope', question: 'What are the non-negotiable playable completion criteria?', route: '/jeeves-workbench', family: 'Production' },
  { id: 'canon', title: 'Canon & continuity', question: 'Which worldbuilding facts must not drift?', route: '/world-workbench', family: 'Narrative' },
  { id: 'world', title: 'Worldbuilding', question: 'Which world layers, regions and biomes?', route: '/worldforge', family: 'World' },
  { id: 'map', title: 'Map design', question: 'Which maps, regions and position systems?', route: '/worldforge', family: 'World' },
  { id: 'pathing', title: 'Paths & transport', question: 'What alternate routes and movement types?', route: '/worldforge', family: 'World' },
  { id: 'story', title: 'Story & endings', question: 'Which arcs, acts, scenes and endings?', route: '/studio', family: 'Narrative' },
  { id: 'dialogue', title: 'Dialogue', question: 'How can dialogue affect subsequent scenes?', route: '/studio', family: 'Narrative' },
  { id: 'cast', title: 'Characters & cast', question: 'What are the cast identities, designs and arcs?', route: '/studio', family: 'Narrative' },
  { id: 'npc', title: 'NPC simulation', question: 'Which autonomous schedules and motivations?', route: '/systems-forge', family: 'Simulation' },
  { id: 'quests', title: 'Quest systems', question: 'Which interdependent quest paths and outcomes?', route: '/gameforge-studio', family: 'Design' },
  { id: 'combat', title: 'Combat', question: 'Which combat loops, moves and effects?', route: '/gameforge-studio', family: 'Design' },
  { id: 'movement', title: 'Locomotion', question: 'Which traversal and camera mechanics?', route: '/physics-studio', family: 'Simulation' },
  { id: 'physics', title: 'Physics', question: 'Which collision, traction and weight distribution rules?', route: '/physics-studio', family: 'Simulation' },
  { id: 'weather', title: 'Weather & forces', question: 'Which wind, turbulence and weather responses?', route: '/physics-studio', family: 'Simulation' },
  { id: 'economy', title: 'Economy', question: 'Which resource, crafting and trade loops?', route: '/systems-forge', family: 'Design' },
  { id: 'inventory', title: 'Inventory', question: 'How will equipment weight and items interact?', route: '/systems-forge', family: 'Design' },
  { id: 'progression', title: 'Progression', question: 'Which skills, classes and factions?', route: '/systems-forge', family: 'Design' },
  { id: 'puzzles', title: 'Puzzles', question: 'Which diverse puzzle solution paths?', route: '/gameforge-studio', family: 'Design' },
  { id: 'multiplayer', title: 'Multiplayer', question: 'Which network ownership and gameplay modes?', route: '/gameforge-studio', family: 'Engineering' },
  { id: 'accessibility', title: 'Accessibility', question: 'Which accessibility requirements?', route: '/skeleton-studio', family: 'Quality' },
  { id: 'localization', title: 'Localization', question: 'Which languages and localization formats?', route: '/skeleton-studio', family: 'Quality' },
  { id: 'ui', title: 'UI & HUD', question: 'Which screens, input schemes and HUD elements?', route: '/skeleton-studio', family: 'Interface' },
  { id: 'ux', title: 'Interaction flows', question: 'Which onboarding and interaction flows?', route: '/galaxy', family: 'Interface' },
  { id: 'sprite_forge', title: 'Sprite forge', question: 'Which sprite sheets, poses and palettes?', route: '/forge-hub', family: 'Forge' },
  { id: 'asset_forge', title: 'Asset forge', question: 'Which props, materials and original meshes?', route: '/construct-forge', family: 'Forge' },
  { id: 'scene_forge', title: 'Scene forge', question: 'Which scene graphs and triggers?', route: '/gameforge-studio', family: 'Forge' },
  { id: 'animation_forge', title: 'Animation forge', question: 'Which motion states, rigs and clips?', route: '/media-studio', family: 'Forge' },
  { id: 'audio_forge', title: 'Audio forge', question: 'Which original soundtrack and effects?', route: '/media-studio', family: 'Forge' },
  { id: 'lighting_forge', title: 'Lighting forge', question: 'Which shadows, reflections and light sources?', route: '/gameforge-studio', family: 'Forge' },
  { id: 'cinematics', title: 'Cinematics', question: 'Which shots and scene direction?', route: '/media-studio', family: 'Forge' },
  { id: 'playtest', title: 'Playtesting', question: 'Which scenarios prove actual gameplay?', route: '/game-learning', family: 'Quality' },
  { id: 'qa', title: 'Adversarial QA', question: 'Which quality gates and verification evidence?', route: '/jeeves-workbench', family: 'Quality' },
  { id: 'training', title: 'Books & weights', question: 'Which rights-cleared material and model candidate?', route: '/jeeves-hub', family: 'AI' },
  { id: 'delegation', title: 'AI delegation', question: 'Which specialist tools may Jeeves request?', route: '/jeeves-workbench', family: 'AI' },
  { id: 'release', title: 'Release & packaging', question: 'Which export, provenance and distribution goals?', route: '/skeleton-studio', family: 'Production' },
] as const;

type Mode = 'questionnaire' | 'forge' | 'flow' | 'inspect' | 'automation';
const MODES: readonly Mode[] = ['questionnaire', 'forge', 'flow', 'inspect', 'automation'];
const C = { bg: '#0b1220', card: '#151c30', border: '#35405e', text: '#e2e8f0', subtle: '#b9c3d8', accent: '#a78bfa' };

export default function JeevesStudioPalette({
  onCompose, onNavigate, disabled = false,
}: { onCompose: (draft: string) => void; onNavigate: (route: Route) => void; disabled?: boolean }) {
  const [visible, setVisible] = useState(false);
  const [facet, setFacet] = useState('vision');
  const [mode, setMode] = useState<Mode>('questionnaire');
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const reply = answers[facet] || '';
  const setReply = (value: string) => setAnswers(current => ({ ...current, [facet]: value }));
  const [source, setSource] = useState('');
  const [group, setGroup] = useState('All');
  const [projects, setProjects] = useState<LearningProjectSummary[]>([]);
  const [projectId, setProjectId] = useState('');
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [savingGoal, setSavingGoal] = useState(false);
  const [goalReceipt, setGoalReceipt] = useState<StudioGoal | null>(null);
  const [goalError, setGoalError] = useState('');
  const [executionMode, setExecutionMode] = useState<'plan' | 'run'>('plan');
  const [editAuthorization, setEditAuthorization] = useState(false);
  const [effectAcknowledged, setEffectAcknowledged] = useState(false);
  const [advancingGoal, setAdvancingGoal] = useState(false);

  useEffect(() => {
    if (!visible) return;
    let active = true;
    setLoadingProjects(true);
    setGoalError('');
    void listLearningProjects().then(rows => {
      if (!active) return;
      setProjects(rows);
      setProjectId(current => rows.some(row => row.project_id === current)
        ? current : (rows[0]?.project_id || ''));
    }).catch(error => {
      if (active) setGoalError(error instanceof Error ? error.message : 'Cannot list studio projects.');
    }).finally(() => { if (active) setLoadingProjects(false); });
    return () => { active = false; };
  }, [visible]);
  const domains = useMemo(() => JEEVES_STUDIO_DOMAINS.filter(item => group === 'All' || item.family === group), [group]);
  const chosen = JEEVES_STUDIO_DOMAINS.find(item => item.id === facet) || JEEVES_STUDIO_DOMAINS[0];
  const groups = ['All', ...Array.from(new Set(JEEVES_STUDIO_DOMAINS.map(item => item.family)))];

  const buildRequest = () => {
    const request = [
      'Jeeves: operate as the locally running game-studio AI, not an external API proxy.',
      `Studio facet: ${chosen.id} (${chosen.title}). Interaction mode: ${mode}.`,
      `Guiding question: ${chosen.question}`,
      reply.trim() ? `Selected-facet requirements: ${reply.trim()}` : 'Ask for the next missing requirement; do not invent an answer.',
      `Reviewed questionnaire answers (proposals only): ${JSON.stringify(Object.entries(answers).filter(([, answer]) => answer.trim()).map(([id, answer]) => ({ facet: id, answer: answer.trim() })))}`,
      source.trim() ? `User-supplied context/source reference (verify before reuse): ${source.trim()}` : 'No source attachment has been verified in this turn.',
      'Read the project canon and current editor state when available. Produce concrete, editable options and dependencies.',
      'For effects: propose a typed creator command and exact scopes, show the intended changes, wait for operator authorization, then delegate to the existing creator runbook.',
      'For every actual automated action require a durable hash-linked intent, host-issued receipt, validation, and independent review. Do not claim success without observed execution.',
      'Respect source licenses. Keep multimodal media under the app media/crawler workflows until ingestion and provenance are verified.',
    ].join('\n');
    return request;
  };

  const prepare = () => {
    const request = buildRequest();
    if (request.length > 16000) {
      setGoalError('Questionnaire is too long for chat. Split the request into smaller production steps.');
      return;
    }
    onCompose(request);
    setVisible(false);
  };

  const saveGoal = async () => {
    if (disabled || savingGoal || advancingGoal || !projectId) return;
    if (executionMode === 'run' && (!editAuthorization || !effectAcknowledged)) {
      setGoalError('Real production requires explicit edit permission and acknowledgement of project changes.');
      return;
    }
    const proposedGoal = buildRequest();
    if (proposedGoal.length > 4096) {
      setGoalError('Project goal exceeds the 4096-character admission limit. Use a smaller scoped plan.');
      return;
    }
    setSavingGoal(true);
    setGoalError('');
    setGoalReceipt(null);
    try {
      const project = await getLearningProject(projectId);
      const saved = await createStudioGoal(project, {
        goal: proposedGoal,
        maxSteps: 8,
        executionMode,
        allowEdits: executionMode === 'run' && editAuthorization,
        authorizationSeconds: 600,
        maxModelCalls: executionMode === 'run' ? 8 : 4,
        maxJobs: executionMode === 'run' ? 2 : 0,
        max_output_tokens: 1024,
      });
      setGoalReceipt(saved);
    } catch (error) {
      setGoalError(error instanceof Error ? error.message : 'Studio goal was not saved.');
    } finally {
      setSavingGoal(false);
    }
  };
  const reloadGoal = async () => {
    if (!goalReceipt || advancingGoal) return;
    setAdvancingGoal(true);
    setGoalError('');
    try {
      const saved = await getStudioGoal(goalReceipt.goal_id);
      if (saved.project_id !== projectId) throw new Error('This goal belongs to another project.');
      setGoalReceipt(saved);
    } catch (error) {
      setGoalError(error instanceof Error ? error.message : 'Unable to verify persisted goal.');
    } finally {
      setAdvancingGoal(false);
    }
  };
  const advanceGoal = async () => {
    if (!goalReceipt || goalReceipt.execution_mode !== 'run' ||
        !effectAcknowledged || disabled || advancingGoal) return;
    setAdvancingGoal(true);
    setGoalError('');
    try {
      // Always reload the authoritative version before a possibly mutating call;
      // the service independently enforces project revision and idempotency.
      const observed = await getStudioGoal(goalReceipt.goal_id);
      if (observed.project_id !== projectId || observed.execution_mode !== 'run')
        throw new Error('The inspected goal scope or execution permission changed.');
      const changed = await advanceStudioGoal(observed, 2, {}, undefined,
        { maxPlannerDecisions: 2, waitForWorkSeconds: 0 });
      setGoalReceipt(changed);
    } catch (error) {
      // A timeout can be an in-doubt effect. Reload state; never resend automatically.
      try {
        const authoritative = await getStudioGoal(goalReceipt.goal_id);
        if (authoritative.project_id === projectId) setGoalReceipt(authoritative);
      } catch { /* keep the prior receipt and show the original error */ }
      setGoalError(error instanceof Error ? error.message : 'Run advanced uncertainly; inspect before any retry.');
    } finally {
      setAdvancingGoal(false);
    }
  };
  const chip = (label: string, selected: boolean, press: () => void) => (
    <TouchableOpacity key={label} onPress={press} accessibilityRole="button"
      accessibilityState={{ selected }}
      style={{ borderWidth: 1, borderColor: selected ? C.accent : C.border,
        backgroundColor: selected ? '#302547' : C.card,
        borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9 }}>
      <Text style={{ color: C.text, fontSize: 12 }}>{label}</Text>
    </TouchableOpacity>
  );

  return <>
    <TouchableOpacity accessibilityRole="button" accessibilityLabel="Open Jeeves studio controls"
      disabled={disabled} onPress={() => setVisible(true)}
      style={{ borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10, alignSelf: 'flex-start' }}>
      <Text style={{ color: C.text, fontSize: 12, fontWeight: '700' }}>Studio controls · 38 facets · Forges / questionnaires / flows</Text>
    </TouchableOpacity>
    <Modal visible={visible} animationType="slide" onRequestClose={() => setVisible(false)}>
      <View style={{ flex: 1, backgroundColor: C.bg, paddingTop: 35 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 14 }}>
          <Text accessibilityRole="header" style={{ color: C.text, fontSize: 20, fontWeight: '700' }}>Jeeves Studio Controller</Text>
          {chip('Close', false, () => setVisible(false))}
        </View>
        <ScrollView contentContainerStyle={{ padding: 16, gap: 15 }} keyboardShouldPersistTaps="handled">
          <Text style={{ color: C.subtle }}>Choose a studio capability, questionnaire, forge or production flow. Jeeves will work in chat; open the real editor to perform changes. No hidden execution occurs from this selector.</Text>
          <Text style={{ color: C.text, fontWeight: '700' }}>Production family</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7 }}>{groups.map(name => chip(name, name === group, () => setGroup(name)))}</View>
          <Text style={{ color: C.text, fontWeight: '700' }}>Capability · {Object.values(answers).filter(answer => answer.trim()).length} / {JEEVES_STUDIO_DOMAINS.length} questions answered</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7 }}>{domains.map(item => chip(`${answers[item.id]?.trim() ? '✓ ' : ''}${item.title}`, chosen.id === item.id, () => setFacet(item.id)))}</View>
          <Text style={{ color: C.text, fontWeight: '700' }}>Working mode</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7 }}>{MODES.map(name => chip(name, mode === name, () => setMode(name)))}</View>
          <Text style={{ color: C.subtle }}>{chosen.question}</Text>
          <TextInput accessibilityLabel={`Requirements for ${chosen.title}`} value={reply}
            onChangeText={setReply} multiline maxLength={4096}
            placeholder="Answer the question or describe the changes…" placeholderTextColor={C.subtle}
            style={{ color: C.text, borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 12, minHeight: 90 }} />
          <Text style={{ color: C.text, fontWeight: '700' }}>Source references / multimodal context</Text>
          <TextInput accessibilityLabel="Source evidence reference" value={source}
            onChangeText={setSource} maxLength={1024}
            placeholder="Verified asset digest or source identifier (optional)" placeholderTextColor={C.subtle}
            style={{ color: C.text, borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 12 }} />
          <Text style={{ color: C.subtle }}>Media and screenshots are handled in the editor or media studio; entering a reference does not ingest a file.</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 10 }}>
            {chip('Compose for Jeeves', true, prepare)}
            {chip(`Open ${chosen.title} editor ↗`, false, () => {
              setVisible(false); onNavigate(chosen.route);
            })}
          </View>
          <View style={{ gap: 9, borderTopWidth: 1, borderColor: C.border, paddingTop: 12 }}>
            <Text style={{ color: C.text, fontWeight: '700' }}>Actual project workflow · durable receipts</Text>
            <Text style={{ color: C.subtle, fontSize: 12 }}>
              Save a reviewed plan or explicitly authorize real studio execution. The
              existing authenticated goal runner owns edits, jobs, decisions, revisions,
              and receipts. Jeeves proposals alone never execute.
            </Text>
            {loadingProjects && <Text style={{ color: C.subtle }}>Loading available projects…</Text>}
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7 }}>
              {projects.map(project => chip(project.name, projectId === project.project_id,
                () => { setProjectId(project.project_id); setGoalReceipt(null); setEffectAcknowledged(false); }))}
            </View>
            {projects.length === 0 && !loadingProjects &&
              <Text style={{ color: C.subtle }}>No studio projects were returned. Open Game Learning to create one.</Text>}
            <Text style={{ color: C.text, fontWeight: '700' }}>Authority for the selected project</Text>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7 }}>
              {chip('Draft a plan (no effects)', executionMode === 'plan',
                () => { setExecutionMode('plan'); setEditAuthorization(false); setEffectAcknowledged(false); })}
              {chip('Run real studio workflow', executionMode === 'run',
                () => { setExecutionMode('run'); setGoalReceipt(null); setEffectAcknowledged(false); })}
            </View>
            {executionMode === 'run' && <>
              <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: editAuthorization }}
                disabled={disabled} onPress={() => setEditAuthorization(value => !value)}
                style={{ padding: 9, borderWidth: 1, borderColor: C.border, borderRadius: 8 }}>
                <Text style={{ color: C.text }}>{editAuthorization ? '☑' : '☐'} Allow this goal to edit the selected project</Text>
              </TouchableOpacity>
              <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: effectAcknowledged }}
                disabled={disabled} onPress={() => setEffectAcknowledged(value => !value)}
                style={{ padding: 9, borderWidth: 1, borderColor: C.border, borderRadius: 8 }}>
                <Text style={{ color: C.text }}>{effectAcknowledged ? '☑' : '☐'} I authorize scoped editor and job effects within this goal’s 10-minute window and budgets</Text>
              </TouchableOpacity>
              <Text style={{ color: C.subtle, fontSize: 12 }}>
                Up to 8 goal steps, 8 model decisions and 2 jobs. The server validates
                source revision, permissions and tool authority. Check actual project
                history before authorizing additional work.
              </Text>
            </>}
            <TouchableOpacity accessibilityRole="button"
              accessibilityLabel={executionMode === 'run' ? 'Create scoped executable studio goal' : 'Save plan-only studio goal'}
              accessibilityState={{ disabled: disabled || savingGoal || advancingGoal || !projectId ||
                (executionMode === 'run' && (!editAuthorization || !effectAcknowledged)) }}
              disabled={disabled || savingGoal || advancingGoal || !projectId ||
                (executionMode === 'run' && (!editAuthorization || !effectAcknowledged))}
              onPress={() => { void saveGoal(); }}
              style={{ borderWidth: 1, borderColor: C.accent, backgroundColor: C.card,
                opacity: disabled || savingGoal || !projectId ? 0.5 : 1,
                borderRadius: 10, padding: 12, alignSelf: 'flex-start' }}>
              <Text style={{ color: C.text, fontWeight: '700' }}>
                {savingGoal ? 'Saving to project…' :
                  executionMode === 'run' ? 'Create authorized project workflow' : 'Save plan-only goal'}
              </Text>
            </TouchableOpacity>
            {!!goalError && <Text accessibilityRole="alert" style={{ color: '#fca5a5' }}>{goalError}</Text>}
            {goalReceipt && <>
              <Text accessibilityRole="status" style={{ color: '#86efac' }}>
                Persisted studio goal · {goalReceipt.goal_id} · {goalReceipt.status} ·
                {' '}{goalReceipt.execution_mode} · revision {goalReceipt.version}
              </Text>
              <Text selectable style={{ color: C.subtle, fontSize: 12 }}>
                Recorded steps: {goalReceipt.steps.length} / {goalReceipt.max_steps}
                {' · '}model calls {goalReceipt.model_calls} / {goalReceipt.max_model_calls}
                {' · '}jobs {goalReceipt.jobs_started} / {goalReceipt.max_jobs}
                {' · '}integrity {goalReceipt.integrity?.status || 'not reported'}
              </Text>
              {goalReceipt.integrity?.history_digest &&
                <Text selectable style={{ color: C.subtle, fontSize: 11 }}>
                  History SHA-256: {goalReceipt.integrity.history_digest}
                </Text>}
              {goalReceipt.integrity?.state_digest &&
                <Text selectable style={{ color: C.subtle, fontSize: 11 }}>
                  State SHA-256: {goalReceipt.integrity.state_digest}
                </Text>}
              {goalReceipt.last_step &&
                <Text selectable style={{ color: C.subtle, fontSize: 11 }}>
                  Last server-observed step: {JSON.stringify(goalReceipt.last_step).slice(0, 2500)}
                </Text>}
              <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 7 }}>
                {chip(advancingGoal ? 'Inspecting…' : 'Reload authoritative receipts', false,
                  () => { void reloadGoal(); })}
                {goalReceipt.execution_mode === 'run' && effectAcknowledged &&
                  !['completed', 'failed', 'cancelled', 'succeeded'].includes(goalReceipt.status) &&
                  chip(advancingGoal ? 'Working…' : 'Advance 2 authorized steps', true,
                    () => { void advanceGoal(); })}
                {chip('Open goal history in Game Learning ↗', false, () => {
                  setVisible(false); onNavigate('/game-learning');
                })}
              </View>
            </>}
          </View>
          <Text style={{ color: C.subtle, fontSize: 12 }}>AI-generated proposals are not execution receipts. Runtime authorization and artifact evidence remain required for each effect.</Text>
        </ScrollView>
      </View>
    </Modal>
  </>;
}
