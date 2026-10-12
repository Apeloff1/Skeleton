import React, { useState } from 'react';
import { Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Action, Editor, Field, styles } from './workbench/ui';
import {
  CHAPTER_SCENE_HANDOFF_KEY, chapterForAct, integer, slug,
  parseChapterSceneHandoff,
} from './chapterStudio';
import type { ChapterSceneHandoff } from './chapterStudio';
import { validProjectId } from '../../src/product/worldWorkspace';

/** Explicit chat -> chapter production draft. No unreviewed model content is
 * written to the server or silently accepted as canonical story history. */
export default function ChatChapterActions({
  text, conversationId, messageId, notify,
}: {
  text: string; conversationId: string; messageId: string;
  notify: (message: string) => void;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [game, setGame] = useState('');
  const [branch, setBranch] = useState('main');
  const [act, setAct] = useState('1');
  const [scene, setScene] = useState('1');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const draft = async () => {
    if (busy) return;
    setBusy(true); setError('');
    try {
      const gameId = validProjectId(game.trim());
      if (!gameId) throw new Error('Choose a valid existing game ID.');
      const actNumber = integer(act, 'Act', 1, 1000);
      const sceneNumber = integer(scene, 'Scene', 1, 9999);
      const chapterNumber = chapterForAct(actNumber);
      const source = slug(messageId, 'Jeeves message');
      const conversation = slug(conversationId, 'Jeeves conversation');
      const id = 'scene-' + Date.now().toString(36) + '-' +
        Math.random().toString(36).slice(2, 10);
      const handoff: ChapterSceneHandoff = {
        version: 1, id, createdAt: Date.now(), gameId,
        branchId: slug(branch, 'Story branch'),
        conversationId: conversation, messageId: source,
        text: text.slice(0, 16000), chapter: chapterNumber,
        act: actNumber, scene: sceneNumber,
      };
      if (!parseChapterSceneHandoff(JSON.stringify(handoff), Date.now())) {
        throw new Error('Chat-to-chapter proposal validation failed.');
      }
      const pending = await AsyncStorage.getItem(CHAPTER_SCENE_HANDOFF_KEY);
      if (pending) {
        throw new Error('Another scene proposal is pending. Open it in Chapter Studio before replacing it.');
      }
      await AsyncStorage.setItem(CHAPTER_SCENE_HANDOFF_KEY, JSON.stringify(handoff));
      setOpen(false);
      notify('Jeeves proposal staged for Chapter ' + chapterNumber +
        '. It still requires editing, exact plot markup and chapter receipts.');
      router.push({
        pathname: '/chapter-studio',
        params: { game: gameId, chat_scene: id },
      });
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Could not stage this proposal.');
    } finally { setBusy(false); }
  };
  if (!text.trim()) return null;
  return <View style={{ marginTop: 6, gap: 4 }}>
    <Action icon="albums-outline" compact label="Draft in chapter story editor"
      onPress={() => setOpen(true)} />
    <Editor visible={open} title="Chapter-aware Jeeves scene draft"
      close={() => { if (!busy) setOpen(false); }}
      footer={<View style={{ gap: 8 }}>
        <Action label="Stage proposal for creator review" icon="arrow-forward-circle-outline"
          disabled={busy} onPress={() => { void draft(); }} />
        <Action label="Cancel" disabled={busy} onPress={() => setOpen(false)} />
      </View>}>
      <Text style={styles.muted}>
        Chapters 1–100 each hold 10 acts; scene IDs range from 1–9,999 globally.
        This copies a proposed script to the editor. It does not create canon,
        replace a saved voice, execute production, or claim continuity proof.
      </Text>
      <Field label="Existing game build ID" value={game} onChange={setGame} maxLength={128} />
      <Field label="Story branch" value={branch} onChange={setBranch} maxLength={96} />
      <Field label="Act 1–1000" value={act} onChange={setAct} numeric maxLength={4} />
      <Field label="Global scene 1–9999" value={scene} onChange={setScene} numeric maxLength={4} />
      <Text style={styles.label}>
        {(() => { try { return 'Target chapter ' + chapterForAct(Number(act)); }
          catch { return 'Choose an act to determine its chapter.'; } })()}
      </Text>
      {text.length > 16000 && <Text style={styles.muted}>
        The proposed draft will use the first 16,000 characters. Review omitted text before saving.
      </Text>}
      {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    </Editor>
  </View>;
}
