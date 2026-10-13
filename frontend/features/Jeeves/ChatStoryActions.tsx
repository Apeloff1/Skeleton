import React, { useState } from 'react';
import { Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import api from '../../src/utils/apiClient';
import { authHeaders, checkMe } from '../../src/auth/gameforgeAuth';
import { makeStoryEventRequest, STORY_KINDS } from './storyContext';
import type { StoryKind } from './storyContext';
import { Action, Choice, Editor, Field, styles } from './workbench/ui';

/** Records a reply only after the human reviews its scene, actors and causality.
 * No model output can directly mutate canonical game or story state.
 */
export default function ChatStoryActions({
  text, conversationId, messageId, notify,
}: {
  text: string;
  conversationId: string;
  messageId: string;
  notify: (notice: string) => void;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [gameId, setGameId] = useState('');
  const [branch, setBranch] = useState('main');
  const [act, setAct] = useState('1');
  const [scene, setScene] = useState('1');
  const [beat, setBeat] = useState('1');
  const [kind, setKind] = useState<StoryKind>('establish');
  const [characters, setCharacters] = useState('');
  const [speaker, setSpeaker] = useState('');
  const [witnesses, setWitnesses] = useState('');
  const [required, setRequired] = useState('');
  const [granted, setGranted] = useState('');
  const [threadKey, setThreadKey] = useState('');
  const [reviewedText, setReviewedText] = useState(text.slice(0, 4000));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);

  const record = async () => {
    if (busy || saved) return;
    let data: ReturnType<typeof makeStoryEventRequest>;
    try {
      data = makeStoryEventRequest({
        gameId: gameId.trim(), branch, act, scene, beat, kind,
        characters, witnesses, speaker, text: reviewedText,
        knowledgeRequired: required, knowledgeGranted: granted,
        threadKey, conversationId, messageId,
      });
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Invalid story bookmark.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const identity = await checkMe();
      if (identity.enforced &&
          (!identity.authenticated || !['editor', 'admin'].includes(identity.role))) {
        throw new Error('Story edits require an authenticated editor or admin.');
      }
      const result = await api.post<any>(
        '/api/pipeline/' + encodeURIComponent(data.game) + '/story-index/events',
        data.event,
        {
          headers: authHeaders(), idempotencyKey: data.event.event_id,
          timeoutMs: 15000, retries: 0,
        },
      );
      if (!result.ok || !result.data?.ok ||
          result.data?.event?.event_id !== data.event.event_id ||
          result.data?.event?.branch_id !== data.event.branch_id) {
        throw new Error(result.status === 409
          ? 'This bookmark ID already has different content. Open the story index to reconcile.'
          : 'Story save was not confirmed. Inspect the index before resubmitting.');
      }
      setSaved(true);
      setOpen(false);
      notify(result.data.replayed
        ? 'This story reference was already recorded; no duplicate created.'
        : 'Story reference recorded. Use the continuity audit to check cross-scene consistency.');
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'The story reference could not be saved.');
    } finally {
      setBusy(false);
    }
  };

  const navigate = () => {
    if (!gameId.trim()) {
      setOpen(true);
      setError('Enter an existing game ID to open its story index.');
      return;
    }
    router.push({
      pathname: '/story-index',
      params: { game: gameId.trim() },
    });
  };

  return (
    <View style={{ gap: 6, marginTop: 8 }}>
      <Action label={saved ? 'View saved story reference' : 'Bookmark in story index'}
        icon="bookmark-outline" compact onPress={saved ? navigate : () => setOpen(true)} />
      <Editor visible={open} title="Review story continuity reference"
        close={() => { if (!busy) setOpen(false); }}
        footer={<View style={{ gap: 8 }}>
          <Action icon="checkmark-circle-outline" label="Record reviewed story reference"
            disabled={busy || saved} onPress={() => { void record(); }} />
          <Action icon="close" label="Cancel without saving"
            disabled={busy} onPress={() => setOpen(false)} />
        </View>}>
        <Text style={styles.muted}>
          This creates a cited, append-only scene reference, not verified game canon.
          Select the game, character identities, sequence and knowledge facts before saving.
          Chat text is untrusted until you review it.
        </Text>
        <Field label="Game build ID" value={gameId} onChange={setGameId}
          maxLength={128} placeholder="Existing game KB ID" />
        <Field label="Timeline branch ID" value={branch} onChange={setBranch}
          maxLength={96} />
        <View style={styles.row}>
          <View style={styles.flex}><Field label="Act" value={act} onChange={setAct} numeric maxLength={5} /></View>
          <View style={styles.flex}><Field label="Scene" value={scene} onChange={setScene} numeric maxLength={6} /></View>
          <View style={styles.flex}><Field label="Beat" value={beat} onChange={setBeat} numeric maxLength={6} /></View>
        </View>
        <Choice label="Event type" value={kind} values={STORY_KINDS}
          onChange={setKind} />
        <Field label="Participants — IDs separated by commas"
          value={characters} onChange={setCharacters} maxLength={1150}
          placeholder="hero,mentor" />
        <Field label="Speaker ID (dialogue)" value={speaker}
          onChange={setSpeaker} maxLength={96} />
        <Field label="Witness IDs — subset of participants"
          value={witnesses} onChange={setWitnesses} maxLength={1150} />
        <Field label="Facts characters must already know"
          value={required} onChange={setRequired} maxLength={1950}
          placeholder="secret_door_location" />
        <Field label="Facts learned in this event"
          value={granted} onChange={setGranted} maxLength={1950}
          placeholder="secret_door_location,player_identity" />
        <Field label="Causal quest/promise thread ID"
          value={threadKey} onChange={setThreadKey} maxLength={96}
          placeholder="missing_sibling" />
        <Field label="Reviewed story evidence" value={reviewedText}
          onChange={setReviewedText} multiline maxLength={4000}
          hint={text.length > 4000
            ? 'The original reply was longer than 4000 characters; review the excerpt.' :
              'Record factual story details; do not include instructions to the model.'} />
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      </Editor>
    </View>
  );
}
