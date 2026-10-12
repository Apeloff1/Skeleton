/** Live Jeeves Chapter Studio: 100 chapters, 1,000 acts, 9,999 scenes.
 * Chapter-note revisions, source-cited plot highlighting and deterministic
 * proofreading receipts; reviewed source text is never model authority.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator, SafeAreaView, ScrollView, Text, View,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import api from '../src/utils/apiClient';
import { authHeaders, checkMe } from '../src/auth/gameforgeAuth';
import { validProjectId } from '../src/product/worldWorkspace';
import { HANDOFF_KEY } from '../features/Jeeves/workbench/types';
import {
  CHAPTER_SCENE_HANDOFF_KEY, PLOT_KINDS, acceptProof,
  chapterChatHandoff, chapterForAct, highlightedParts,
  integer, localPlotAnchors, parseChapterSceneHandoff, parsePlotPoints,
  slug, validateSceneCoordinates, voiceCast,
} from '../features/Jeeves/chapterStudio';
import type {
  ChapterNote, ChapterContext, PlotKind, PlotPoint, ProofReceipt, SceneDraft, ChapterSceneHandoff,
} from '../features/Jeeves/chapterStudio';
import { Action, Choice, Field, Section, palette, styles } from '../features/Jeeves/workbench/ui';

const ID = /^[A-Za-z0-9:_-]{1,96}$/;
type ChapterForm = {
  title: string; synopsis: string; notes: string; historical_setting: string;
  palette_rules: string; costume_rules: string; voice_rules: string;
  era_id: string; style_id: string; palette_id: string;
  voice_cast: string; transition_reason: string;
};
function blankChapter(): ChapterForm {
  return {
    title: '', synopsis: '', notes: '', historical_setting: '', palette_rules: '',
    costume_rules: '', voice_rules: '', era_id: '', style_id: '',
    palette_id: '', voice_cast: '', transition_reason: '',
  };
}
function chapterForm(value: ChapterNote): ChapterForm {
  return {
    title: value.title, synopsis: value.synopsis, notes: value.notes,
    historical_setting: value.historical_setting, palette_rules: value.palette_rules,
    costume_rules: value.costume_rules, voice_rules: value.voice_rules,
    era_id: value.era_id, style_id: value.style_id, palette_id: value.palette_id,
    voice_cast: Object.entries(value.voice_cast || {}).map(([c, v]) => c + '=' + v).join('\n'),
    transition_reason: value.transition_reason || '',
  };
}
function draftPoints(points: PlotPoint[]) { return JSON.stringify(points, null, 2); }

const HIGHLIGHT_COLORS: Record<PlotKind, string> = {
  setup: '#354454', payoff: '#19644a', foreshadow: '#554477',
  reveal: '#804e24', decision: '#5b4166', consequence: '#67413d',
  promise: '#27576c', resolution: '#256258', dialogue: '#4b5374',
  motif: '#405e4d', historical_detail: '#6b563c',
  visual_identity: '#574e7d', voice_identity: '#643f64',
};
export default function ChapterStudioScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ game?: string | string[]; chat_scene?: string | string[] }>();
  const incoming = Array.isArray(params.game) ? params.game[0] : params.game;
  const routeScene = Array.isArray(params.chat_scene) ? params.chat_scene[0] : params.chat_scene;
  const [gameId, setGameId] = useState(validProjectId(incoming));
  const [branch, setBranch] = useState('main');
  const [chapterId, setChapterId] = useState('1');
  const [actId, setActId] = useState('1');
  const [sceneId, setSceneId] = useState('1');
  const [chapter, setChapter] = useState<ChapterNote | null>(null);
  const [chapters, setChapters] = useState<ChapterNote[]>([]);
  const [chapterFormState, setChapterFormState] = useState<ChapterForm>(blankChapter);
  const [context, setContext] = useState<ChapterContext | null>(null);
  const [scene, setScene] = useState<SceneDraft | null>(null);
  const [scenes, setScenes] = useState<SceneDraft[]>([]);
  const [sceneNext, setSceneNext] = useState<number | null>(null);
  const [summary, setSummary] = useState('');
  const [script, setScript] = useState('');
  const [characters, setCharacters] = useState('');
  const [threadKeys, setThreadKeys] = useState('');
  const [sourceId, setSourceId] = useState('creator-reviewed');
  const [plotJson, setPlotJson] = useState('[]');
  const [newPlotId, setNewPlotId] = useState('');
  const [newPlotKind, setNewPlotKind] = useState<PlotKind>('setup');
  const [newPlotAnchor, setNewPlotAnchor] = useState('');
  const [proof, setProof] = useState<ProofReceipt | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [page, setPage] = useState<'chapter' | 'scenes' | 'production'>('chapter');
  const staged = React.useRef<ChapterSceneHandoff | null>(null);

  const base = useCallback(() => {
    const game = validProjectId(gameId.trim());
    if (!game || !ID.test(branch)) throw new Error('Select a valid project and branch.');
    return '/api/pipeline/' + encodeURIComponent(game);
  }, [gameId, branch]);

  const withOperation = async (work: () => Promise<void>) => {
    if (busy) return;
    setBusy(true); setNotice('');
    try {
      const auth = await checkMe();
      if (auth.enforced && !auth.authenticated) {
        throw new Error('Sign in before editing narrative production records.');
      }
      await work();
    } catch (e) {
      setNotice(e instanceof Error ? e.message : 'The story operation could not be confirmed.');
    } finally { setBusy(false); }
  };
  const loadChapters = async () => {
    const res = await api.get<any>(base() + '/chapters?branch_id=' + encodeURIComponent(branch),
      { headers: authHeaders(), retries: 0 });
    if (!res.ok || !res.data?.ok || res.data.game_id !== gameId.trim() ||
        res.data.branch_id !== branch || !Array.isArray(res.data.chapters)) {
      throw new Error('Could not verify chapter history for this project.');
    }
    setChapters(res.data.chapters);
  };
  const selectChapter = async (number: number) => {
    if (!Number.isInteger(number) || number < 1 || number > 100) {
      throw new Error('Choose a chapter between 1 and 100.');
    }
    const res = await api.get<any>(
      base() + '/chapters/' + number + '/context?branch_id=' + encodeURIComponent(branch) +
      '&max_chars=6000',
      { headers: authHeaders(), retries: 0 },
    );
    if (!res.ok || !res.data?.ok || res.data.game_id !== gameId.trim() ||
        res.data.branch_id !== branch || res.data.chapter?.chapter !== number ||
        res.data.context?.chapter_digest !== res.data.chapter?.digest) {
      throw new Error('No confirmed chapter note yet. Write chapter notes before drafting scenes.');
    }
    const note = res.data.chapter as ChapterNote;
    setChapter(note); setContext(res.data.context);
    setChapterFormState(chapterForm(note));
    setChapterId(String(number));
    const pending = staged.current;
    setActId(String(pending?.chapter === number ? pending.act : (number - 1) * 10 + 1));
    setScene(null); setProof(null); setSceneNext(null); setScenes([]);
    if (pending?.chapter === number) {
      setSceneId(String(pending.scene)); setScript(pending.text);
      setSourceId(pending.messageId);
      setSummary('Reviewed from Jeeves: ' + pending.messageId);
    } else {
      setSummary(''); setScript(''); setCharacters(''); setThreadKeys('');
      setPlotJson('[]');
    }
    setNotice('Loaded chapter revision ' + note.revision + ' with receipt ' + note.digest.slice(0, 12) + '.');
  };
  const saveChapter = async () => {
    const n = integer(chapterId, 'Chapter', 1, 100);
    const f = chapterFormState;
    const payload = {
      expected_revision: chapter?.chapter === n ? chapter.revision : 0,
      branch_id: slug(branch, 'Branch'), title: f.title.trim(),
      synopsis: f.synopsis.trim(), notes: f.notes,
      historical_setting: f.historical_setting.trim(),
      palette_rules: f.palette_rules.trim(), costume_rules: f.costume_rules.trim(),
      voice_rules: f.voice_rules.trim(), era_id: slug(f.era_id, 'Era'),
      style_id: slug(f.style_id, 'Style'), palette_id: slug(f.palette_id, 'Palette'),
      voice_cast: voiceCast(f.voice_cast),
      transition_reason: f.transition_reason.trim() || null,
      source_message_id: ID.test(sourceId) ? sourceId : null,
    };
    const res = await api.put<any>(
      base() + '/chapters/' + n, payload, { headers: authHeaders(), retries: 0 },
    );
    if (!res.ok || !res.data?.ok || res.data.chapter?.chapter !== n) {
      throw new Error(res.status === 409
        ? 'Chapter revision, palette or locked voice conflicts. Reload before editing.'
        : 'Chapter save is unconfirmed. Your editor fields are preserved.');
    }
    setChapter(res.data.chapter); setChapterFormState(chapterForm(res.data.chapter));
    setContext(null); setScene(null); setProof(null);
    await loadChapters();
    setNotice('Chapter notes saved with revision receipt ' + res.data.receipt.slice(0, 16) +
      (res.data.replayed ? ' (idempotent replay).' : '.'));
  };
  const loadScenes = async (offset = 0) => {
    const n = integer(chapterId, 'Chapter', 1, 100);
    const res = await api.get<any>(
      base() + '/scenes?chapter=' + n + '&branch_id=' + encodeURIComponent(branch) +
      '&limit=100&offset=' + offset, { headers: authHeaders(), retries: 0 },
    );
    if (!res.ok || !res.data?.ok || res.data.chapter !== n ||
        res.data.branch_id !== branch || !Array.isArray(res.data.scenes)) {
      throw new Error('Scene index could not be confirmed for the selected chapter.');
    }
    setScenes(current => offset === 0 ? res.data.scenes : [...current, ...res.data.scenes]);
    setSceneNext(typeof res.data.next_offset === 'number' ? res.data.next_offset : null);
  };
  const loadScene = async (no: number) => {
    const res = await api.get<any>(
      base() + '/scenes/' + no + '?branch_id=' + encodeURIComponent(branch),
      { headers: authHeaders(), retries: 0 },
    );
    if (!res.ok || !res.data?.ok || res.data.scene?.scene !== no ||
        res.data.scene?.branch_id !== branch) {
      throw new Error('Scene is not available from this branch.');
    }
    const item = res.data.scene as SceneDraft;
    if (chapter && item.chapter !== chapter.chapter) {
      throw new Error('Scene belongs to a different chapter.');
    }
    setScene(item); setSceneId(String(item.scene)); setActId(String(item.act));
    setSummary(item.summary); setScript(item.text);
    setCharacters((item.characters || []).join(','));
    setThreadKeys((item.thread_keys || []).join(','));
    setSourceId(item.source_message_id); setPlotJson(draftPoints(item.plot_points || []));
    setProof(item.proof || null);
    setNotice('Loaded scene ' + no + ', revision ' + item.revision +
      '. Edit to draft a new revision or review its current proof.');
    setPage('scenes');
  };
  const addPlotAnchor = () => {
    const points = plotJson.trim() === '[]' ? [] : parsePlotPoints(plotJson, script);
    const newPoint: PlotPoint = {
      id: slug(newPlotId, 'Plot point'), kind: newPlotKind,
      anchor: newPlotAnchor, description: '', related_event_id: null,
    };
    localPlotAnchors(script, [...points, newPoint]);
    setPlotJson(draftPoints([...points, newPoint]));
    setNewPlotId(''); setNewPlotAnchor('');
    setNotice('Plot point marked at its exact script occurrence. Save scene to obtain its receipt.');
  };
  const saveScene = async () => {
    if (!chapter) throw new Error('Save or open chapter notes before drafting a scene.');
    const act = integer(actId, 'Act', 1, 1000);
    const no = integer(sceneId, 'Scene', 1, 9999);
    validateSceneCoordinates(chapter.chapter, act, no);
    if (!summary.trim() || !script.trim() || script.length > 16000) {
      throw new Error('A scene requires a summary and script of no more than 16,000 characters.');
    }
    const characterIds = characters.split(',').map(x => x.trim()).filter(Boolean);
    const threadIds = threadKeys.split(',').map(x => x.trim()).filter(Boolean);
    characterIds.forEach(x => slug(x, 'Character'));
    threadIds.forEach(x => slug(x, 'Story thread'));
    if (new Set(characterIds).size !== characterIds.length ||
        new Set(threadIds).size !== threadIds.length) throw new Error('Duplicate character or thread.');
    const points = parsePlotPoints(plotJson, script);
    const res = await api.put<any>(
      base() + '/scenes/' + no,
      {
        expected_revision: scene?.scene === no ? scene.revision : 0,
        branch_id: branch, chapter: chapter.chapter, act,
        summary: summary.trim(), text: script, characters: characterIds,
        thread_keys: threadIds, plot_points: points,
        chapter_revision: chapter.revision, chapter_digest: chapter.digest,
        source_message_id: slug(sourceId, 'Chat source'),
      },
      { headers: authHeaders(), retries: 0 },
    );
    if (!res.ok || !res.data?.ok || res.data.scene?.scene !== no) {
      throw new Error(res.status === 409
        ? 'Scene or chapter revision conflict. Reload before retrying.'
        : 'No scene save receipt was confirmed. Preserve your draft.');
    }
    setScene(res.data.scene); setProof(null);
    const pending = staged.current;
    if (pending && pending.scene === no && pending.chapter === chapter.chapter
        && pending.gameId === gameId.trim() && pending.branchId === branch) {
      try {
        const saved = await AsyncStorage.getItem(CHAPTER_SCENE_HANDOFF_KEY);
        if (saved && parseChapterSceneHandoff(saved)?.id === pending.id) {
          await AsyncStorage.removeItem(CHAPTER_SCENE_HANDOFF_KEY);
          staged.current = null;
        }
      } catch {
        // The scene was saved on the server; preserving the pending handoff is
        // safer than losing it if device storage removal fails.
      }
    }
    setNotice('Scene revision saved: ' + res.data.receipt.slice(0, 18) +
      '. Its chapter note and voice IDs are now locked to this draft.');
    await loadScenes();
  };
  const reviewScene = async () => {
    if (!scene) throw new Error('Save your reviewed scene before proofreading.');
    const res = await api.post<any>(
      base() + '/scenes/' + scene.scene + '/proofread?branch_id=' + encodeURIComponent(branch),
      {}, { headers: authHeaders(), timeoutMs: 45000, retries: 0 },
    );
    if (!res.ok || !res.data?.ok || res.data.scene_receipt !== scene.digest ||
        res.data.proof?.scene_digest !== scene.digest) {
      throw new Error('100k scene inspection was not confirmed. No production approval was issued.');
    }
    setProof(res.data.proof);
    setNotice(res.data.proof.status === 'machine_checks_passed'
      ? '100,000 deterministic inspections completed. Human editorial review is still required.'
      : 'Proofreading found blocking issues. Resolve them before production approval.');
  };
  const approve = async () => {
    if (!scene || !chapter || !proof) throw new Error('Load a scene and a current proof receipt.');
    const receipt = acceptProof(proof, scene, chapter);
    const res = await api.post<any>(
      base() + '/scenes/' + scene.scene + '/approve',
      { branch_id: branch, expected_revision: scene.revision, proof_digest: receipt },
      { headers: authHeaders(), retries: 0 },
    );
    if (!res.ok || !res.data?.ok ||
        res.data.status !== 'approved_for_production' ||
        res.data.proof_digest !== receipt) {
      throw new Error('Human approval did not receive a confirmed production receipt.');
    }
    await loadScene(scene.scene);
    setPage('production');
    setNotice('Narrative scene approved with proof receipt ' + receipt.slice(0, 20) +
      '. Assets, audio, voice and gameplay still require independent production checks.');
  };
  const discussChapter = async () => {
    if (!chapter) throw new Error('Select a saved chapter.');
    // Re-fetch the latest version and citations before opening a new chat.
    const res = await api.get<any>(
      base() + '/chapters/' + chapter.chapter + '/context?branch_id=' +
      encodeURIComponent(branch) + '&max_chars=3600',
      { headers: authHeaders(), retries: 0 },
    );
    if (!res.ok || !res.data?.ok) throw new Error('Chapter context is unavailable.');
    const h = chapterChatHandoff(gameId.trim(), res.data.chapter, res.data.context,
      Date.now(), 'chapter-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 8));
    const existing = await AsyncStorage.getItem(HANDOFF_KEY);
    if (existing !== null) throw new Error('Open the pending chat handoff before preparing another.');
    await AsyncStorage.setItem(HANDOFF_KEY, JSON.stringify(h));
    router.push('/jeeves-chat');
  };

  useEffect(() => {
    if (!routeScene) return;
    let alive = true;
    void AsyncStorage.getItem(CHAPTER_SCENE_HANDOFF_KEY).then(raw => {
      const handoff = raw && parseChapterSceneHandoff(raw);
      if (!alive || !handoff || handoff.id !== routeScene ||
          handoff.gameId !== validProjectId(incoming)) return;
      staged.current = handoff;
      setGameId(handoff.gameId); setBranch(handoff.branchId);
      setChapterId(String(handoff.chapter)); setActId(String(handoff.act));
      setSceneId(String(handoff.scene)); setSourceId(handoff.messageId);
      setScript(handoff.text); setSummary('Reviewed from Jeeves: ' + handoff.messageId);
      setPage('scenes');
      setNotice('Jeeves scene proposal loaded. Review chapter notes, plot points and cast before saving.');
    }).catch(() => { if (alive) setNotice('Chat scene handoff was not available.'); });
    return () => { alive = false; };
  }, [incoming, routeScene]);

  const field = (key: keyof ChapterForm, label: string, maxLength = 600, multiline = false) =>
    <Field key={key} label={label} value={chapterFormState[key]}
      onChange={value => setChapterFormState(current => ({ ...current, [key]: value }))}
      maxLength={maxLength} multiline={multiline} />;
  const parts = (() => {
    try { return highlightedParts(script, localPlotAnchors(script, parsePlotPoints(plotJson, script))); }
    catch { return null; }
  })();
  const selectedChapter = chapters.find(x => x.chapter === Number(chapterId));
  return <SafeAreaView style={styles.safe}>
    <ScrollView keyboardShouldPersistTaps="handled"
      contentContainerStyle={{ gap: 14, padding: 16, paddingBottom: 90, maxWidth: 1050,
        width: '100%', alignSelf: 'center' }}>
      <View style={styles.wrap}>
        <View style={styles.flex}>
          <Text style={styles.sectionTitle}>Jeeves Chapter Production Studio</Text>
          <Text style={styles.muted}>100 chapters · 1,000 acts · 9,999 scenes · human-reviewed proof receipts</Text>
        </View>
        <Action label="Story Index" onPress={() => router.push({
          pathname: '/story-index', params: { game: gameId },
        })} />
      </View>
      <Section title="Select the game and timeline">
        <Field label="Game build ID" value={gameId} onChange={setGameId} maxLength={128} />
        <Field label="Story branch" value={branch} onChange={setBranch} maxLength={96} />
        <View style={styles.wrap}>
          <Action label="Load all chapters" icon="book-outline" disabled={busy}
            onPress={() => { void withOperation(loadChapters); }} />
          <Action label="Chapter notes" selected={page === 'chapter'} onPress={() => setPage('chapter')} />
          <Action label="Scene editor" selected={page === 'scenes'} onPress={() => setPage('scenes')} />
          <Action label="Production receipts" selected={page === 'production'} onPress={() => setPage('production')} />
        </View>
        <View style={styles.wrap}>
          {chapters.map(c => <Action key={c.chapter}
            label={'Chapter ' + c.chapter} compact
            selected={chapter?.chapter === c.chapter}
            onPress={() => { void withOperation(() => selectChapter(c.chapter)); }} />)}
        </View>
        <Field label="Chapter (1–100)" value={chapterId} onChange={setChapterId} numeric maxLength={3} />
        <Action label="Open chapter" disabled={busy}
          onPress={() => { void withOperation(async () => {
            await selectChapter(integer(chapterId, 'Chapter', 1, 100));
          }); }} />
        <Text style={styles.small}>
          {selectedChapter ? 'Saved chapter: ' + selectedChapter.title : 'Create this chapter to begin production.'}
        </Text>
      </Section>
      {busy && <ActivityIndicator color={palette.accent} />}
      {!!notice && <Text accessibilityRole="alert" style={styles.muted}>{notice}</Text>}
      {page === 'chapter' && <Section title="Chapter-wide authoritative reference notes"
        subtitle="These notes bind every scene to one immutable chapter revision.">
        {field('title', 'Chapter title', 180)}
        {field('synopsis', 'Chapter summary and goals', 3000, true)}
        {field('notes', 'Continuity / timeline / foreshadowing / character notes', 8000, true)}
        {field('historical_setting', 'History, era, culture and source context')}
        {field('palette_rules', 'Thematic colors and materials')}
        {field('costume_rules', 'Consistent costume, props, items and facial identities')}
        {field('voice_rules', 'Immutable voice rules and pronunciation')}
        {field('era_id', 'Canonical era ID', 96)}
        {field('style_id', 'Canonical art style ID', 96)}
        {field('palette_id', 'Canonical palette ID', 96)}
        {field('voice_cast', 'Immutable voices — character_id=voice_id per line', 4000, true)}
        {field('transition_reason', 'Approved era/style/palette transition rationale (only if needed)', 1200, true)}
        <View style={styles.wrap}>
          <Action icon="save-outline" label="Save chapter notes" disabled={busy}
            onPress={() => { void withOperation(saveChapter); }} />
          <Action icon="refresh-outline" label="Reload latest version" disabled={busy}
            onPress={() => { void withOperation(() => selectChapter(integer(chapterId, 'Chapter', 1, 100))); }} />
          <Action icon="chatbubbles-outline" label="Discuss full chapter with Jeeves"
            disabled={!chapter || busy} onPress={() => { void withOperation(discussChapter); }} />
        </View>
        {chapter && <Text style={styles.muted}>
          Revision {chapter.revision} · evidence receipt {chapter.digest.slice(0, 28)} ·
          This is reviewed fiction, not a claim that every future scene is consistent.
        </Text>}
        {context && <>
          <Text style={styles.label}>
            Chapter context: {context.included_scenes} cited scenes
            {context.truncated ? ' · PARTIAL — request omitted scenes before certifying' : ''}
          </Text>
          <Text style={styles.muted}>{context.context.slice(0, 1800)}</Text>
        </>}
      </Section>}
      {page === 'scenes' && <Section title="One scene at a time"
        subtitle="Sequence controls, exact-text plot highlighters and context-locked drafting">
        {!chapter && <Text style={styles.error}>First open or save chapter notes.</Text>}
        <Field label="Act (1–1000; ten acts per chapter)" value={actId} onChange={value => {
          setActId(value);
          try { setChapterId(String(chapterForAct(Number(value)))); } catch {}
        }} maxLength={4} numeric />
        <Field label="Global scene (1–9999)" value={sceneId} onChange={setSceneId} maxLength={4} numeric />
        <Action label="Find saved scene" disabled={busy} onPress={() => {
          void withOperation(() => loadScene(integer(sceneId, 'Scene', 1, 9999)));
        }} />
        <View style={styles.wrap}>
          <Action label="List chapter scenes" disabled={busy}
            onPress={() => { void withOperation(() => loadScenes()); }} />
          {scenes.map(s => <Action key={s.scene} compact
            label={'Scene ' + s.scene + ' · ' + s.status} onPress={() => {
              void withOperation(() => loadScene(s.scene));
            }} />)}
          {sceneNext !== null && <Action label="Next 100 scenes"
            disabled={busy} onPress={() => { void withOperation(() => loadScenes(sceneNext)); }} />}
        </View>
        <Field label="Scene summary" value={summary} onChange={setSummary} maxLength={600} multiline />
        <Field label="Characters — comma-separated IDs from chapter voice cast"
          value={characters} onChange={setCharacters} maxLength={2500} />
        <Field label="Open and affected plot/quest thread IDs" value={threadKeys}
          onChange={setThreadKeys} maxLength={3500} />
        <Field label="Source Jeeves message / creator evidence ID" value={sourceId}
          onChange={setSourceId} maxLength={96} />
        <Field label="Scene script — dialogue, actions, camera and interaction"
          value={script} onChange={value => { setScript(value); setProof(null); }}
          maxLength={16000} multiline />
        <Text style={styles.label}>Plot point markup — highlighted in the verified script</Text>
        <View style={styles.card}>
          <Text style={styles.text}>
            {(parts || [{ text: script, kind: null, id: null }]).map((part, i) =>
              <Text key={part.id || i} style={part.kind
                ? { backgroundColor: HIGHLIGHT_COLORS[part.kind], color: '#fff', fontWeight: 'bold' }
                : undefined}>
                {part.text}
              </Text>)}
          </Text>
          {!parts && <Text style={styles.error}>
            One or more plot-point anchors no longer match the scene. Repair anchors before saving.
          </Text>}
        </View>
        <Field label="New plot-point ID" value={newPlotId} onChange={setNewPlotId}
          maxLength={96} placeholder="reveal_hidden_heir" />
        <Choice label="Highlight type" value={newPlotKind} onChange={setNewPlotKind} values={PLOT_KINDS} />
        <Field label="Exact unique phrase to highlight" value={newPlotAnchor} onChange={setNewPlotAnchor}
          maxLength={500} placeholder="The first time this fact is revealed" />
        <Action label="Mark exact plot point" icon="color-wand-outline" onPress={() => {
          try { addPlotAnchor(); } catch (e) {
            setNotice(e instanceof Error ? e.message : 'Plot point is invalid.');
          }
        }} />
        <Field label="Advanced plot-point details (JSON, IDs, anchors, links)"
          value={plotJson} onChange={value => { setPlotJson(value); setProof(null); }}
          maxLength={15000} multiline
          hint='[{ "id":"reveal_01","kind":"reveal","anchor":"exact scene phrase","description":"...","related_event_id":null }]' />
        <Action label="Save reviewed scene draft" icon="save-outline"
          disabled={!chapter || busy} onPress={() => { void withOperation(saveScene); }} />
        {scene && <Text style={styles.muted}>
          Scene revision {scene.revision} · {scene.status} · immutable content receipt {scene.digest.slice(0, 24)}
        </Text>}
      </Section>}
      {page === 'production' && <Section title="100,000-inspection scene proofreading"
        subtitle="Deterministic rules are repeated and counted. They do not certify 100% semantic or artistic perfection.">
        <Text style={styles.muted}>
          Review act/scene ordering, chapter revision, exact plot markers, chronology,
          witnesses, historical palette, costume, immutable voice identity and source provenance.
          A changed scene or chapter must be proofread again.
        </Text>
        <Action label="Run 100,000 deterministic inspections" disabled={!scene || busy}
          icon="shield-checkmark-outline" onPress={() => { void withOperation(reviewScene); }} />
        {proof && <>
          <Text style={proof.status === 'machine_checks_passed' ? styles.label : styles.error}>
            {proof.status} · {proof.inspections_executed.toLocaleString()} checks
            · {proof.axes.length} review axes · {proof.history_complete ? 'indexed history scanned' : 'INCOMPLETE HISTORY'}
          </Text>
          {proof.axes.map(axis => <Text key={axis.name} style={axis.failed ? styles.error : styles.small}>
            {axis.name}: {axis.executed.toLocaleString()} inspected, {axis.failed.toLocaleString()} failed
          </Text>)}
          {proof.blocking_issues.map(issue => <Text key={issue} style={styles.error}>
            Blocked: {issue}
          </Text>)}
          {proof.warnings.map(issue => <Text key={issue} style={styles.muted}>
            Additional editorial review: {issue}
          </Text>)}
          <Text style={styles.small}>Receipt: {proof.receipt_digest}</Text>
          <Action label="Approve for narrative production" icon="checkmark-circle-outline"
            disabled={busy || !scene || !chapter || proof.status !== 'machine_checks_passed'}
            onPress={() => { void withOperation(approve); }} />
        </>}
        {scene && <Text style={styles.label}>
          Scene {scene.scene} · {scene.status} · source {scene.source_message_id}
        </Text>}
      </Section>}
    </ScrollView>
  </SafeAreaView>;
}
