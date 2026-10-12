/** Branching outcomes producer for RPG, adventure and story-led other genres.
 * Saves only reviewed plans; simulates player choices against authoritative
 * server state. Never writes imagined choices to the live playable game.
 */
import React, { useCallback, useState } from 'react';
import { ActivityIndicator, SafeAreaView, ScrollView, Text, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import api from '../src/utils/apiClient';
import { authHeaders, checkMe } from '../src/auth/gameforgeAuth';
import { validProjectId } from '../src/product/worldWorkspace';
import { HANDOFF_KEY } from '../features/Jeeves/workbench/types';
import {
  acceptSimulation, acceptOutcomeAudit, chooseOption, compactPlayerContext,
  exampleThreeEndingPlan, parsePlanDraft,
} from '../features/Jeeves/outcomeStudio';
import type {
  StorySimulation, OutcomeAudit, PlanCatalog,
} from '../features/Jeeves/outcomeStudio';
import { Action, Field, Section, Choice, styles, palette } from '../features/Jeeves/workbench/ui';

const SLUG = /^[A-Za-z0-9:_-]{1,96}$/;
type Page = 'author' | 'playthrough' | 'outcomes' | 'characters' | 'places' | 'matrices';
const AREAS = [
  'quest_completion', 'quest_failure', 'missed_quests', 'karma',
  'regions', 'cities', 'people', 'factions', 'gangs',
  'government_law', 'dialogue', 'character_arcs', 'place_lore',
  'world_reactivity', 'ending_choice', 'ending_closure', 'postgame',
  'mystery_reveals', 'replayability', 'literary_quality',
] as const;
export default function StoryOutcomesStudio() {
  const router = useRouter();
  const params = useLocalSearchParams<{ game?: string | string[] }>();
  const incoming = Array.isArray(params.game) ? params.game[0] : params.game;
  const [gameId, setGameId] = useState(validProjectId(incoming));
  const [branch, setBranch] = useState('main');
  const [raw, setRaw] = useState('');
  const [doc, setDoc] = useState<PlanCatalog | null>(null);
  const [revision, setRevision] = useState(0);
  const [planDigest, setPlanDigest] = useState('');
  const [authorKey, setAuthorKey] = useState('');
  const [choices, setChoices] = useState<string[]>([]);
  const [simulation, setSimulation] = useState<StorySimulation | null>(null);
  const [audit, setAudit] = useState<OutcomeAudit | null>(null);
  const [page, setPage] = useState<Page>('author');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [matrixArea, setMatrixArea] = useState<typeof AREAS[number]>('ending_closure');
  const [matrixItems, setMatrixItems] = useState<any[]>([]);
  const [matrixId, setMatrixId] = useState('ending_closure.plot_setup_payoff.ending');
  const [matrixLevel, setMatrixLevel] = useState('100');
  const [endingId, setEndingId] = useState('');
  const [pathBudget, setPathBudget] = useState('2000');

  const resetScope = (nextGame: string, nextBranch: string) => {
    setGameId(nextGame); setBranch(nextBranch);
    setRevision(0); setPlanDigest(''); setAuthorKey('');
    setDoc(null); setSimulation(null); setChoices([]); setAudit(null);
    setMatrixItems([]); setNotice('');
  };
  const base = useCallback(() => {
    const id = validProjectId(gameId.trim());
    if (!id || !SLUG.test(branch)) throw new Error('Select one valid game and story branch.');
    return '/api/pipeline/' + encodeURIComponent(id) + '/outcomes';
  }, [gameId, branch]);
  const withOperation = async (fn: () => Promise<void>) => {
    if (busy) return;
    setBusy(true); setNotice('');
    try {
      const auth = await checkMe();
      if (auth.enforced && !auth.authenticated) throw new Error('Sign in for project-scoped story work.');
      await fn();
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Outcome evidence could not be confirmed.');
    } finally { setBusy(false); }
  };
  const confirmCurrent = () => {
    if (!planDigest || authorKey !== gameId.trim() + ':' + branch || !doc) {
      throw new Error('Save or reload this exact narrative branch before simulation.');
    }
  };
  const save = async () => {
    const content = parsePlanDraft(raw, gameId.trim(), branch);
    const response = await api.put<any>(base() + '/plan',
      { expected_revision: revision, branch_id: branch, plan: content },
      { headers: authHeaders(), retries: 0, timeoutMs: 30000 },
    );
    if (!response.ok || !response.data?.ok ||
        response.data.branch_id !== branch ||
        typeof response.data.plan_digest !== 'string' ||
        !/^[a-f0-9]{64}$/.test(response.data.plan_digest)) {
      throw new Error(response.status === 409
        ? 'Story graph changed concurrently. Reload before making a revision.'
        : 'No authoritative branching plan receipt was issued.');
    }
    setRevision(response.data.revision); setPlanDigest(response.data.plan_digest);
    setAuthorKey(gameId.trim() + ':' + branch);
    setDoc(content); setChoices([]); setSimulation(null); setAudit(null);
    setNotice('Branch revision ' + response.data.revision +
      ' saved with immutable graph receipt ' + response.data.plan_digest.slice(0, 20) + '.');
  };
  const load = async () => {
    const response = await api.get<any>(
      base() + '/plan?branch_id=' + encodeURIComponent(branch),
      { headers: authHeaders(), retries: 0 },
    );
    if (!response.ok || !response.data?.ok ||
        response.data.game_id !== gameId.trim() ||
        response.data.branch_id !== branch ||
        !/^[a-f0-9]{64}$/.test(response.data.plan_digest)) {
      throw new Error('No confirmed story graph is available on this branch.');
    }
    const value = response.data.plan;
    const encoded = JSON.stringify(value, null, 2);
    const parsed = parsePlanDraft(encoded, gameId.trim(), branch);
    setRaw(encoded); setDoc(parsed); setRevision(response.data.revision);
    setPlanDigest(response.data.plan_digest);
    setAuthorKey(gameId.trim() + ':' + branch);
    setSimulation(null); setChoices([]); setAudit(null);
    setNotice('Loaded authoritative graph at revision ' + response.data.revision + '.');
  };
  const simulate = async (path: string[]) => {
    confirmCurrent();
    const response = await api.post<any>(
      base() + '/simulate', { branch_id: branch, choices: path },
      { headers: authHeaders(), retries: 0, timeoutMs: 30000 },
    );
    if (!response.ok || !response.data?.ok ||
        response.data.game_id !== gameId.trim() ||
        response.data.branch_id !== branch ||
        response.data.revision !== revision ||
        response.data.simulated_not_applied_to_game !== true) {
      throw new Error('Choice replay was not confirmed by the original plan.');
    }
    const result = acceptSimulation(response.data.simulation, planDigest, path);
    setChoices(path); setSimulation(result);
    setPage('playthrough');
    setNotice(result.ending_id
      ? (result.ending_accepted
        ? 'An evidence-closed ending was reached. This is simulation, not playable-game deployment.'
        : 'Ending reached but unresolved plot, companion, quest or place obligations remain.')
      : 'Real state-dependent dialogue choices are unlocked below.');
  };
  const advance = async (choiceId: string) => {
    if (!simulation) throw new Error('Start a player-history replay.');
    chooseOption(simulation, choiceId);
    await simulate([...choices, choiceId]);
  };
  const auditPaths = async () => {
    confirmCurrent();
    const budget = Number(pathBudget);
    if (!Number.isInteger(budget) || budget < 1 || budget > 10000) {
      throw new Error('Path exploration budget is 1..10,000.');
    }
    const response = await api.get<any>(
      base() + '/audit?branch_id=' + encodeURIComponent(branch) +
      '&path_budget=' + budget, { headers: authHeaders(), retries: 0, timeoutMs: 45000 },
    );
    if (!response.ok || !response.data?.ok ||
        response.data.plan_digest !== planDigest) {
      throw new Error('Outcome reachability audit could not verify the current plan.');
    }
    const result = acceptOutcomeAudit(response.data.audit, planDigest);
    setAudit(result); setPage('outcomes');
    setNotice(result.all_paths_verified
      ? 'Every enumerated decision path reaches a closed authored ending.'
      : 'Some branch paths fail closure or coverage is incomplete. Inspect issues.');
  };
  const loadMatrices = async () => {
    confirmCurrent();
    const all: any[] = [];
    for (let offset = 0; offset < 1000; offset += 100) {
      const response = await api.get<any>(
        base() + '/matrices?start=' + offset + '&limit=100',
        { headers: authHeaders(), retries: 0, timeoutMs: 30000 },
      );
      if (!response.ok || !response.data?.ok ||
          response.data.catalog?.matrix_count !== 1000 ||
          response.data.catalog?.levels_per_matrix !== 100 ||
          !Array.isArray(response.data.catalog?.matrices) ||
          response.data.catalog.matrices.length !== 100) {
        throw new Error('Outcome matrix catalog is incomplete or inconsistent.');
      }
      all.push(...response.data.catalog.matrices);
    }
    if (new Set(all.map(x => x.id)).size !== 1000) {
      throw new Error('Duplicate or missing outcome review matrices.');
    }
    setMatrixItems(all);
    setNotice('1,000 distinct outcome rubrics with 100 scrutiny levels each verified.');
  };
  const askJeeves = async () => {
    confirmCurrent();
    const target = endingId.trim() || doc?.endings[0]?.id;
    if (!target) throw new Error('Choose an actual authored ending.');
    const level = Number(matrixLevel);
    if (!Number.isInteger(level) || level < 1 || level > 100) {
      throw new Error('Select scrutiny level 1–100.');
    }
    const response = await api.get<any>(
      base() + '/matrix-prompt?branch_id=' + encodeURIComponent(branch) +
      '&ending_id=' + encodeURIComponent(target) +
      '&matrix_id=' + encodeURIComponent(matrixId) +
      '&level=' + level,
      { headers: authHeaders(), retries: 0 },
    );
    if (!response.ok || !response.data?.ok ||
        response.data.plan_digest !== planDigest ||
        response.data.instruction?.review_status !== 'unexecuted') {
      throw new Error('Outcome review request could not be bound to the current story.');
    }
    const pending = await AsyncStorage.getItem(HANDOFF_KEY);
    if (pending) throw new Error('Open your existing pending Jeeves handoff before staging another.');
    const token = 'outcome-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
    const draft = {
      version: 1, id: token, createdAt: Date.now(),
      projectId: gameId.trim(), projectTitle: (doc?.title || 'Game story').slice(0, 120),
      draft: response.data.instruction.prompt,
      context: compactPlayerContext(doc!, simulation),
      sourceLabels: ['Story graph ' + planDigest.slice(0, 16),
        'Ending ' + target, 'Matrix ' + matrixId + ' / L' + level],
    };
    await AsyncStorage.setItem(HANDOFF_KEY, JSON.stringify(draft));
    router.push('/jeeves-chat');
  };
  const currentPlan = (() => {
    try { return parsePlanDraft(raw, gameId.trim(), branch); }
    catch { return null; }
  })();

  return <SafeAreaView style={styles.safe}>
    <ScrollView keyboardShouldPersistTaps="handled"
      contentContainerStyle={{ gap: 13, padding: 16, paddingBottom: 100,
        maxWidth: 1020, width: '100%', alignSelf: 'center' }}>
      <View style={styles.wrap}>
        <View style={styles.flex}>
          <Text style={styles.sectionTitle}>Jeeves: Branching Story & Endings</Text>
          <Text style={styles.muted}>
            Dialogue choices · quests completed, failed or missed · karma ·
            reputation · factions · gang/law standing · NPC and place lore
          </Text>
        </View>
        <Action label="Chapter Studio" icon="albums-outline"
          onPress={() => router.push({ pathname: '/chapter-studio',
            params: { game: gameId } })} />
      </View>
      <Section title="Select canonical game and narrative branch">
        <Field label="Game build ID" value={gameId}
          onChange={value => resetScope(value, branch)} maxLength={128} />
        <Field label="Narrative branch" value={branch}
          onChange={value => resetScope(gameId, value)} maxLength={96} />
        <View style={styles.wrap}>
          <Action label="Load saved story graph" icon="download-outline" disabled={busy}
            onPress={() => { void withOperation(load); }} />
          <Action label="Load editable three-ending example" icon="bulb-outline"
            disabled={busy} onPress={() => {
              const example = exampleThreeEndingPlan();
              example.branch_id = branch;
              setRaw(JSON.stringify(example, null, 2)); setDoc(null);
              setPlanDigest(''); setSimulation(null); setChoices([]);
              setNotice('Example staged only. Review and save to your game to test it.');
              setPage('author');
            }} />
        </View>
        <Text style={styles.small}>
          {planDigest
            ? 'Saved revision ' + revision + ' · graph receipt ' + planDigest.slice(0, 24)
            : 'Not yet saved. A typed example never changes your playable game.'}
        </Text>
        <View style={styles.wrap}>
          {(['author', 'playthrough', 'outcomes', 'characters', 'places', 'matrices'] as const)
            .map(mode => <Action key={mode} label={mode}
              selected={page === mode} onPress={() => setPage(mode)} compact />)}
        </View>
      </Section>
      {busy && <ActivityIndicator color={palette.accent} />}
      {!!notice && <Text style={styles.muted} accessibilityRole="alert">{notice}</Text>}
      {page === 'author' && <Section title="Author the conditional story graph"
        subtitle="Structured JSON represents choices, guards, outcomes, and immutable lore citations.">
        <Text style={styles.muted}>
          Nodes have chapter/act/scene, optional NPC speaker and place, script,
          exact plot-point anchors, and alternative dialogue choices.
          Conditions use nested all/any/not, quest state, karma, reputation,
          dialogue history, story flags and lore discovery.
          Effects adjust quest state, karma, scoped reputation or relationships,
          and open/close plot obligations. Every choice leads forward to an
          authored decision or ending; missing/dead branches are refused.
        </Text>
        <Field label="Editable full game story definition" value={raw} onChange={setRaw}
          multiline maxLength={1_200_000}
          hint="Review every NPC/region/faction and every ending consequence before saving. This is a planning artifact, not executing scripts." />
        <Text style={currentPlan ? styles.label : styles.error}>
          {currentPlan
            ? currentPlan.nodes.length + ' decision scenes · ' +
              currentPlan.endings.length + ' endings · ' +
              currentPlan.characters.length + ' NPC biographies · ' +
              currentPlan.places.length + ' place lore entries'
            : 'The draft is not a valid local branching plan. Open example or fix JSON.'}
        </Text>
        <Action label="Save reviewed narrative graph with revision control"
          icon="save-outline" disabled={busy || !currentPlan}
          onPress={() => { void withOperation(save); }} />
        <Action label="Start clean player-choice simulation" disabled={busy || !planDigest}
          icon="play-outline" onPress={() => { void withOperation(() => simulate([])); }} />
      </Section>}
      {page === 'playthrough' && <Section title="Player dialogue & unlocked alternatives"
        subtitle="Only guards satisfied by recorded quests, karma, reputation and knowledge unlock.">
        <Action label="Start over" icon="refresh-outline" disabled={busy || !planDigest}
          onPress={() => { void withOperation(() => simulate([])); }} />
        {!!choices.length && <Action label="Undo most recent player choice"
          icon="arrow-undo-outline" disabled={busy}
          onPress={() => { void withOperation(() => simulate(choices.slice(0, -1))); }} />}
        {simulation && <>
          <Text style={styles.label}>
            {simulation.ending_id ? 'Ending: ' + simulation.ending_id
              : 'Current decision: ' + simulation.position}
          </Text>
          <Text style={styles.muted}>
            Karma {simulation.state.meters.karma || 0}.
            Quests: {JSON.stringify(simulation.state.quests)}.
            Reputation and relationships: {JSON.stringify(simulation.state.meters)}.
          </Text>
          <Text style={styles.small}>
            Flags: {simulation.state.flags.join(', ') || 'none'}.
            Discovered lore: {simulation.state.known_lore.join(', ') || 'none'}.
          </Text>
          {simulation.steps.map((item, i) => <View key={item.receipt_digest} style={styles.card}>
            <Text style={styles.label}>
              {i + 1}. Scene {item.scene} · {item.character || 'world'} · {item.place || 'elsewhere'}
            </Text>
            <Text style={styles.text}>{item.choice} — {item.intent}</Text>
            <Text style={styles.muted}>{item.emotional_consequence}</Text>
            <Text style={styles.small}>
              Consequences: {JSON.stringify(item.consequences).slice(0, 900)}
            </Text>
            <Text style={styles.small}>Evidence: {item.receipt_digest.slice(0, 28)}</Text>
          </View>)}
          {simulation.available_options.map(option =>
            <Action key={option.id} label={option.dialogue + ' → ' +
              (option.ending || option.next_node || '')}
              disabled={busy || !!simulation.ending_id}
              onPress={() => { void withOperation(() => advance(option.id)); }} />)}
          {simulation.ending && <>
            <Text style={simulation.ending_accepted ? styles.label : styles.error}>
              {simulation.ending.title} ({simulation.ending.tone}) ·
              {simulation.ending_accepted ? 'All recorded causal obligations closed' :
                'Unresolved consequences block narrative acceptance'}
            </Text>
            <Text style={styles.text}>{simulation.ending.epilogue}</Text>
            <Text style={styles.muted}>{simulation.ending.consequences}</Text>
            {Object.entries(simulation.ending.character_conclusions).map(([id, fate]) =>
              <Text key={id} style={styles.text}>Character {id}: {fate}</Text>)}
            {Object.entries(simulation.ending.place_conclusions).map(([id, fate]) =>
              <Text key={id} style={styles.text}>Place {id}: {fate}</Text>)}
            {Object.entries(simulation.ending.quest_conclusions).map(([id, fate]) =>
              <Text key={id} style={styles.text}>Quest {id}: {fate}</Text>)}
            {Object.entries(simulation.ending.faction_conclusions).map(([id, fate]) =>
              <Text key={id} style={styles.text}>Faction {id}: {fate}</Text>)}
            <Text style={styles.error}>
              Missing: threads {simulation.unresolved_threads.join(', ') || 'none'},
              NPC arcs {simulation.unresolved_character_arcs.join(', ') || 'none'},
              place lore {simulation.unresolved_place_lore.join(', ') || 'none'},
              quest outcomes {simulation.unresolved_quest_conclusions.join(', ') || 'none'},
              factions {simulation.unresolved_faction_conclusions.join(', ') || 'none'}
            </Text>
          </>}
          <Text style={styles.small}>Playthrough receipt: {simulation.receipt_digest}</Text>
        </>}
      </Section>}
      {page === 'outcomes' && <Section title="Adversarial branching outcome review"
        subtitle="Trace consequences for all enumerated choices, not just the preferred ending.">
        <Field label="Maximum audit history prefixes (1–10,000)" value={pathBudget}
          onChange={setPathBudget} numeric maxLength={5} />
        <Action label="Enumerate actually available player paths"
          icon="git-branch-outline" disabled={busy || !planDigest}
          onPress={() => { void withOperation(auditPaths); }} />
        {audit && <>
          <Text style={audit.all_paths_verified ? styles.label : styles.error}>
            {audit.paths_inspected} histories examined ·
            {audit.complete ? 'Full bounded exploration' : 'TRUNCATED — no completeness claim'}
          </Text>
          <Text style={styles.label}>
            Reachable endings: {audit.reachable_endings.join(', ') || 'none'}
          </Text>
          <Text style={styles.error}>
            Unreachable endings: {audit.unreachable_endings.join(', ') || 'none'}.
            Failed/dead-end paths: {audit.issue_count}.
          </Text>
          {audit.issues.slice(0, 30).map((item, i) =>
            <Text key={i} style={styles.error}>
              {item.error} — choices: {item.path.join(' → ')}
            </Text>)}
          <Text style={styles.small}>
            The audit traces simulated state transitions; it does not certify
            whether every emotional ending will satisfy every player.
          </Text>
        </>}
      </Section>}
      {page === 'characters' && <Section title="Individual characters and interwoven destinies"
        subtitle="Each speaking character needs a backstory, goals, dialogue identity and personal conclusions in reachable endings.">
        {(currentPlan?.characters || []).map(c =>
          <View key={c.id} style={styles.card}>
            <Text style={styles.label}>{c.name} · {c.id}</Text>
            <Text style={styles.text}>Backstory: {c.backstory}</Text>
            <Text style={styles.muted}>Goals: {c.goals}</Text>
            <Text style={styles.muted}>Dialogue: {c.dialogue_style}</Text>
            <Text style={styles.small}>Personal ending obligation: {c.personal_ending}</Text>
          </View>)}
        {!currentPlan?.characters.length &&
          <Text style={styles.error}>Author the cast records in the story graph.</Text>}
      </Section>}
      {page === 'places' && <Section title="Geography, legends and inhabited-place lore"
        subtitle="Cities and regions need history, culture, conflicts and consequences.">
        {(currentPlan?.places || []).map(p =>
          <View key={p.id} style={styles.card}>
            <Text style={styles.label}>{p.name} · {p.kind} · {p.id}</Text>
            <Text style={styles.text}>History: {p.history}</Text>
            <Text style={styles.muted}>Culture: {p.culture}</Text>
            <Text style={styles.small}>Conflicts: {p.regional_conflicts}</Text>
          </View>)}
      </Section>}
      {page === 'matrices' && <Section title="1,000 new outcome-weaving matrices × 100 scrutiny levels"
        subtitle="200 authored craft skills, five branch-analysis perspectives, 100 stage/lens levels.">
        <Action label="Load full 1,000-rubric catalog" icon="library-outline"
          disabled={busy || !planDigest} onPress={() => { void withOperation(loadMatrices); }} />
        {!!matrixItems.length && <>
          <Choice label="Narrative skill area" value={matrixArea}
            values={AREAS} onChange={setMatrixArea} />
          <View style={styles.wrap}>
            {matrixItems.filter(x => x.domain === matrixArea).map((row: any) =>
              <Action key={row.id} compact
                label={row.craft_skill + ' · ' + row.perspective}
                selected={row.id === matrixId} onPress={() => setMatrixId(row.id)} />)}
          </View>
        </>}
        <Field label="Exact matrix ID" value={matrixId}
          onChange={setMatrixId} maxLength={140} />
        <Field label="Scrutiny level 1–100" value={matrixLevel}
          onChange={setMatrixLevel} maxLength={3} numeric />
        <Field label="Ending ID to audit" value={endingId}
          onChange={setEndingId} maxLength={96}
          hint={'Authored endings: ' + (doc?.endings.map(x => x.id).join(', ') || 'none')} />
        <Action label="Ask Jeeves to audit this outcome matrix"
          icon="chatbubbles-outline" disabled={busy || !planDigest}
          onPress={() => { void withOperation(askJeeves); }} />
        <Text style={styles.small}>
          100,000 outcome-review requirements exist per ending, but none count
          as passed until evidence and human scrutiny support them.
        </Text>
      </Section>}
    </ScrollView>
  </SafeAreaView>;
}
