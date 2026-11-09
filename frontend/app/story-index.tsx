/** Project Story Index — actual indexed scene evidence and recall for Jeeves.
 * Every scene is server-owned, branch-scoped and cited. This is not a static
 * demo, and neither missing history nor audit truncation is marked "pass".
 */
import React from 'react';
import { ActivityIndicator, SafeAreaView, ScrollView, Text, TextInput, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import api from '../src/utils/apiClient';
import { authHeaders, checkMe } from '../src/auth/gameforgeAuth';
import { validProjectId } from '../src/product/worldWorkspace';
import { STORY_KINDS, prepareStoryEvent, storyIndexPath, type StoryDraft } from '../src/product/storyContinuity';
import { HANDOFF_KEY } from '../src/features/Jeeves/workbench/types';
import { makeStoryRecallHandoff } from '../src/features/Jeeves/storyContext';
import { Action, Section, palette, styles } from '../src/features/Jeeves/workbench/ui';

type StoryEvent = {
  event_id: string; branch_id: string; act: number; scene: number; beat: number;
  kind: string; text: string; character_ids: string[]; witness_ids: string[];
  thread_key: string | null; source_message_id: string | null;
};
type StoryAudit = {
  valid: boolean; complete: boolean; event_count: number; issue_count: number;
  issues: { code: string; event_id: string; detail: string; act: number; scene: number }[];
  open_threads: { thread_key: string; introduced_at: string }[];
  interaction_groups: string[];
};
type StoryRecall = {
  character_id: string; branch_id: string; context: string;
  citations: { event_id: string; source_message_id: string }[];
  included: number; truncated: boolean; complete_source: boolean;
  instruction_policy: string;
};

export default function StoryIndexScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ game?: string | string[] }>();
  const routeId = Array.isArray(params.game) ? params.game[0] : params.game;
  const [gameId, setGameId] = React.useState(validProjectId(routeId));
  const [branch, setBranch] = React.useState('main');
  const [characterId, setCharacterId] = React.useState('');
  const [events, setEvents] = React.useState<StoryEvent[]>([]);
  const [nextOffset, setNextOffset] = React.useState<number | null>(null);
  const [audit, setAudit] = React.useState<StoryAudit | null>(null);
  const [recall, setRecall] = React.useState<StoryRecall | null>(null);
  const [notice, setNotice] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [sending, setSending] = React.useState(false);
  const [recording, setRecording] = React.useState(false);
  const [storyReceipt, setStoryReceipt] = React.useState('');
  const [draft, setDraft] = React.useState<StoryDraft>({
    eventId: '', branchId: 'main', act: '1', scene: '1', beat: '0',
    kind: 'establish', text: '', characterIds: '', witnessIds: '',
    speakerId: '', threadKey: '', knowledgeRequired: '', knowledgeGranted: '',
  });
  const requestId = React.useRef(0);

  const load = React.useCallback(async (offset = 0) => {
    const game = validProjectId(gameId.trim());
    if (!game || !/^[A-Za-z0-9:_-]{1,96}$/.test(branch)) {
      setNotice('Enter a valid existing game ID and branch identifier.');
      return;
    }
    const nonce = ++requestId.current;
    setBusy(true);
    setNotice('');
    try {
      await checkMe();
      const root = storyIndexPath(game);
      const query = '?branch_id=' + encodeURIComponent(branch);
      const list = await api.get<any>(
        root + '/events' + query + '&limit=100&offset=' + offset,
        { headers: authHeaders(), timeoutMs: 15000, retries: 0 },
      );
      if (nonce !== requestId.current) return;
      if (!list.ok || !list.data?.ok ||
          list.data.game_id !== game || list.data.branch_id !== branch ||
          !Array.isArray(list.data.events)) {
        throw new Error('Story index could not confirm this project history.');
      }
      const page = list.data.events as StoryEvent[];
      setEvents(previous => offset === 0 ? page : [...previous, ...page]);
      setNextOffset(typeof list.data.next_offset === 'number'
        ? list.data.next_offset : null);
      if (offset === 0) {
        setRecall(null);
        const scan = await api.get<any>(
          root + '/audit' + query,
          { headers: authHeaders(), timeoutMs: 15000, retries: 0 },
        );
        if (nonce !== requestId.current) return;
        if (!scan.ok || !scan.data?.ok || scan.data.game_id !== game ||
            scan.data.branch_id !== branch || !scan.data.audit) {
          setAudit(null);
          setNotice('Events loaded, but a complete continuity audit could not be verified.');
        } else {
          setAudit(scan.data.audit);
        }
      }
    } catch (problem) {
      if (nonce === requestId.current) {
        if (offset === 0) { setEvents([]); setAudit(null); setNextOffset(null); }
        setNotice(problem instanceof Error ? problem.message : 'Story index is unavailable.');
      }
    } finally {
      if (nonce === requestId.current) setBusy(false);
    }
  }, [gameId, branch]);

  React.useEffect(() => {
    setGameId(validProjectId(routeId));
    setEvents([]);
    setAudit(null);
    setRecall(null);
    setNextOffset(null);
    requestId.current += 1;
  }, [routeId]);

  const searchCharacter = async () => {
    const game = validProjectId(gameId.trim());
    if (!game || !/^[A-Za-z0-9:_-]{1,96}$/.test(characterId) ||
        !/^[A-Za-z0-9:_-]{1,96}$/.test(branch)) {
      setNotice('Enter a game, story branch and an exact character ID.');
      return;
    }
    setBusy(true);
    setRecall(null);
    try {
      await checkMe();
      const result = await api.get<any>(
        storyIndexPath(game) + '/recall/' + encodeURIComponent(characterId) +
        '?branch_id=' + encodeURIComponent(branch) + '&max_chars=3500',
        { headers: authHeaders(), timeoutMs: 15000, retries: 0 },
      );
      if (!result.ok || !result.data?.ok || result.data.game_id !== game ||
          result.data.recall?.character_id !== characterId ||
          result.data.recall?.branch_id !== branch) {
        throw new Error('Character history was not confirmed.');
      }
      setRecall(result.data.recall);
      setNotice(result.data.recall.included
        ? 'Story evidence retrieved with source IDs. Review before passing it to Jeeves.'
        : 'No references for this character in the scanned branch.');
    } catch (problem) {
      setNotice(problem instanceof Error ? problem.message : 'Character lookup failed.');
    } finally { setBusy(false); }
  };

  const discuss = async () => {
    if (!recall || !recall.included || sending) return;
    setSending(true);
    setNotice('');
    try {
      const handoff = makeStoryRecallHandoff(
        gameId.trim(), characterId, recall, Date.now(),
        'recall-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10),
      );
      const pending = await AsyncStorage.getItem(HANDOFF_KEY);
      if (pending !== null) {
        throw new Error('An existing chat handoff needs to be opened first. No pending draft was overwritten.');
      }
      await AsyncStorage.setItem(HANDOFF_KEY, JSON.stringify(handoff));
      router.push('/jeeves-chat');
    } catch (problem) {
      setNotice(problem instanceof Error ? problem.message : 'Story handoff failed.');
    } finally { setSending(false); }
  };


  const recordStory = async () => {
    if (recording || busy) return;
    const game = validProjectId(gameId.trim());
    if (!game) { setNotice('Choose an existing game before recording.'); return; }
    let event;
    try {
      event = prepareStoryEvent({ ...draft, branchId: branch });
    } catch (problem) {
      setNotice(problem instanceof Error ? problem.message : 'Story event is invalid.');
      return;
    }
    setRecording(true);
    setStoryReceipt('');
    setNotice('');
    try {
      await checkMe();
      const response = await api.post<{
        ok: boolean; event: { event_id: string; branch_id: string; record_status: string };
        replayed: boolean; receipt: string;
      }>(storyIndexPath(game) + '/events', event, {
        headers: authHeaders(), timeoutMs: 15000, retries: 0,
      });
      const saved = response.data;
      if (!response.ok || !saved?.ok || !saved.receipt ||
          saved.event?.event_id !== event.event_id ||
          saved.event?.branch_id !== branch ||
          saved.event?.record_status !== 'creator_reviewed_evidence') {
        throw new Error('The server did not confirm a creator-reviewed receipt.');
      }
      setStoryReceipt((saved.replayed ? 'Existing event replayed: ' : 'Event recorded: ') + saved.receipt);
      setDraft(v => ({ ...v, eventId: '', text: '' }));
      await load(0);
    } catch (problem) {
      setNotice(problem instanceof Error ? problem.message : 'Story event could not be saved.');
    } finally {
      setRecording(false);
    }
  };

  const status = audit === null ? 'Not verified' :
    !audit.complete ? 'Incomplete scan — cannot certify continuity' :
      audit.valid ? 'No contradictions detected in indexed events' :
        audit.issue_count + ' continuity issue(s) detected';

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ gap: 16, padding: 18, paddingBottom: 80, maxWidth: 1100, width: '100%', alignSelf: 'center' }}>
        <View style={styles.row}>
          <View style={styles.flex}>
            <Text style={styles.sectionTitle}>Story Continuity Index</Text>
            <Text style={styles.muted}>Jeeves scene bookmarks, witnesses, character facts and causal threads</Text>
          </View>
          <Action label="Back" icon="arrow-back-outline" onPress={() => router.back()} />
        </View>
        <Section title="Select the canonical game" subtitle="Only game-specific indexed evidence is shown.">
          <TextInput style={styles.input} placeholder="Existing game build ID"
            accessibilityLabel="Game build ID" value={gameId}
            onChangeText={setGameId} autoCapitalize="none" />
          <TextInput style={styles.input} placeholder="Story branch"
            accessibilityLabel="Story branch ID" value={branch}
            onChangeText={setBranch} autoCapitalize="none" />
          <View style={styles.wrap}>
            <Action label="Load indexed scenes" icon="refresh-outline"
              disabled={busy} onPress={() => { void load(); }} />
            <Action label="Open canonical game KB" icon="book-outline"
              disabled={!validProjectId(gameId.trim())}
              onPress={() => router.push({ pathname: '/game-kb', params: { game: gameId.trim() } })} />
          </View>
        </Section>
        {busy && <ActivityIndicator color={palette.accent} />}
        {!!notice && <Text accessibilityRole="alert" style={styles.muted}>{notice}</Text>}

        <Section title="Record a creator-reviewed story event"
          subtitle="Append-only, branch-scoped evidence — never automatic model promotion">
          <Text style={styles.muted}>
            Record a stable unique event identity. Conflicting repeats fail closed.
            Saving requires the editor role and an existing canonical game.
          </Text>
          <TextInput style={styles.input} accessibilityLabel="Story event ID"
            value={draft.eventId} placeholder="Unique event ID" autoCapitalize="none"
            onChangeText={eventId => setDraft(v => ({ ...v, eventId }))} />
          <View style={styles.wrap}>
            {STORY_KINDS.map(kind => (
              <Action key={kind} label={draft.kind === kind ? '✓ ' + kind : kind}
                onPress={() => setDraft(v => ({ ...v, kind }))} />
            ))}
          </View>
          <TextInput style={styles.input} accessibilityLabel="Act number"
            value={draft.act} keyboardType="number-pad" placeholder="Act 1–10000"
            onChangeText={act => setDraft(v => ({ ...v, act }))} />
          <TextInput style={styles.input} accessibilityLabel="Scene number"
            value={draft.scene} keyboardType="number-pad" placeholder="Scene 1–100000"
            onChangeText={scene => setDraft(v => ({ ...v, scene }))} />
          <TextInput style={styles.input} accessibilityLabel="Beat number"
            value={draft.beat} keyboardType="number-pad" placeholder="Beat 0–100000"
            onChangeText={beat => setDraft(v => ({ ...v, beat }))} />
          <TextInput style={[styles.input, { minHeight: 96 }]} multiline
            accessibilityLabel="Story event evidence" value={draft.text}
            placeholder="Precisely what happened in the scene?"
            onChangeText={text => setDraft(v => ({ ...v, text }))} />
          <TextInput style={styles.input} accessibilityLabel="Character participants"
            value={draft.characterIds} autoCapitalize="none"
            placeholder="Participants (comma-separated character IDs)"
            onChangeText={characterIds => setDraft(v => ({ ...v, characterIds }))} />
          <TextInput style={styles.input} accessibilityLabel="Witness character IDs"
            value={draft.witnessIds} autoCapitalize="none"
            placeholder="Witnesses (must be participants)"
            onChangeText={witnessIds => setDraft(v => ({ ...v, witnessIds }))} />
          <TextInput style={styles.input} accessibilityLabel="Speaker character ID"
            value={draft.speakerId} autoCapitalize="none" placeholder="Speaker (dialogue)"
            onChangeText={speakerId => setDraft(v => ({ ...v, speakerId }))} />
          <TextInput style={styles.input} accessibilityLabel="Plot thread ID"
            value={draft.threadKey} autoCapitalize="none"
            placeholder="Thread key (promise/resolution)"
            onChangeText={threadKey => setDraft(v => ({ ...v, threadKey }))} />
          <TextInput style={styles.input} accessibilityLabel="Knowledge required IDs"
            value={draft.knowledgeRequired} autoCapitalize="none"
            placeholder="Required facts (comma-separated IDs)"
            onChangeText={knowledgeRequired => setDraft(v => ({ ...v, knowledgeRequired }))} />
          <TextInput style={styles.input} accessibilityLabel="Knowledge learned IDs"
            value={draft.knowledgeGranted} autoCapitalize="none"
            placeholder="Knowledge granted (comma-separated IDs)"
            onChangeText={knowledgeGranted => setDraft(v => ({ ...v, knowledgeGranted }))} />
          <Action label="Record creator-reviewed evidence" icon="save-outline"
            disabled={busy || recording || !draft.eventId.trim() || !draft.text.trim()}
            onPress={() => { void recordStory(); }} />
          {recording && <ActivityIndicator color={palette.accent} />}
          {!!storyReceipt && <Text style={styles.label}>{storyReceipt}</Text>}
        </Section>
        <Section title="Deterministic continuity audit" subtitle={status}>
          <Text style={styles.muted}>
            Indexed events are creator-reviewed fiction, not automatically verified canon.
            Branches never share implied knowledge. Audits stream up to 100,000 events in story order; larger histories report incomplete coverage.
          </Text>
          {audit && <>
            <Text style={styles.label}>{audit.event_count} events scanned · {audit.issue_count || 0} issues · {audit.open_threads?.length || 0} open promises</Text>
            {(audit.issues || []).slice(0, 50).map((issue, i) => (
              <View key={issue.event_id + ':' + i} style={styles.card}>
                <Text style={styles.error}>{issue.code} · Act {issue.act}, scene {issue.scene}</Text>
                <Text style={styles.text}>{issue.detail}</Text>
                <Text style={styles.small}>Event: {issue.event_id}</Text>
              </View>
            ))}
            {(audit.open_threads || []).slice(0, 30).map(promise => (
              <Text key={promise.thread_key} style={styles.text}>
                Unresolved: {promise.thread_key} (from {promise.introduced_at})
              </Text>
            ))}
            {audit.issue_count > 50 && <Text style={styles.muted}>
              Additional issues omitted from this screen; review the API audit record.
            </Text>}
          </>}
        </Section>
        <Section title="Scene-by-scene reference history"
          subtitle="Immutable bookmarks in act / scene / beat order">
          {!events.length && <Text style={styles.muted}>No scene events loaded for this branch.</Text>}
          {events.map(item => (
            <View key={item.event_id} style={styles.card}>
              <Text style={styles.label}>Act {item.act} · Scene {item.scene} · Beat {item.beat} · {item.kind}</Text>
              <Text style={styles.text}>{item.text}</Text>
              <Text style={styles.small}>
                Characters: {(item.character_ids || []).join(', ') || 'none'} · Witnesses: {(item.witness_ids || []).join(', ') || 'none'}
              </Text>
              <Text style={styles.small}>Source: {item.source_message_id || 'unattributed'} · Bookmark: {item.event_id}</Text>
              {!!item.thread_key && <Text style={styles.small}>Causal thread: {item.thread_key}</Text>}
            </View>
          ))}
          {nextOffset !== null && <Action label="Load next 100 events" icon="chevron-down-outline"
            disabled={busy} onPress={() => { void load(nextOffset); }} />}
        </Section>
        <Section title="Character-to-character history and Jeeves recall"
          subtitle="Select one character; retrieve cited source events before a new conversation">
          <TextInput style={styles.input} accessibilityLabel="Character ID" value={characterId}
            onChangeText={setCharacterId} autoCapitalize="none" placeholder="Exact character ID, e.g. hero" />
          <Action label="Retrieve character history" icon="search-outline"
            disabled={busy} onPress={() => { void searchCharacter(); }} />
          {recall && <>
            <Text style={styles.label}>
              {recall.included} references · {recall.truncated ? 'truncated/incomplete' : 'within budget'}
            </Text>
            <Text style={styles.muted}>{recall.context || 'No character evidence found.'}</Text>
            <Action label="Continue story in Jeeves with cited context"
              icon="chatbubbles-outline" disabled={!recall.included || sending}
              onPress={() => { void discuss(); }} />
          </>}
        </Section>
      </ScrollView>
    </SafeAreaView>
  );
}
