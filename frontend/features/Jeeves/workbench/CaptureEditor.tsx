import React, { useEffect, useState, useSyncExternalStore } from 'react';
import { Text, View } from 'react-native';
import { workbenchStore as store } from './store';
import type { CaptureInput } from './capture';
import { Action, Choice, Editor, Field, styles } from './ui';
import type { NoteKind } from './types';

export default function CaptureEditor({ input, close }: { input: CaptureInput; close: () => void }) {
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot, store.getSnapshot);
  const [projectId, setProjectId] = useState(input.projectId);
  const [title, setTitle] = useState(input.title);
  const [body, setBody] = useState(input.text);
  const [kind, setKind] = useState<NoteKind>('note');
  useEffect(() => { void store.initialize(); }, []);
  const projects = snapshot.state.projects.filter(project => project.status !== 'archived');
  const chosen = projects.some(project => project.id === projectId) ? projectId : projects[0]?.id;
  return <Editor visible title="Save message to notebook" close={close} footer={
    <Action label="Save linked note" disabled={!snapshot.ready || !chosen || !title.trim() || !body.trim()} onPress={() => {
      if (chosen && store.capture({ ...input, projectId: chosen, title, text: body, kind })) close();
    }} />
  }>
    <Text style={styles.muted}>The note will be marked unverified and linked to this conversation as its source. Review any claims before relying on them.</Text>
    {!projects.length && <Text style={styles.muted}>Create a project in the workbench first, then save this message.</Text>}
    <View style={styles.wrap}>{projects.map(project => <Action key={project.id} label={project.title} selected={chosen === project.id} onPress={() => setProjectId(project.id)} />)}</View>
    <Field label="Note title" value={title} onChange={setTitle} maxLength={160} />
    <Choice label="Note kind" value={kind} values={['note', 'decision', 'experiment', 'reference', 'retrospective']} onChange={setKind} />
    <Field label="Note text" value={body} onChange={setBody} multiline maxLength={30000} />
    {snapshot.notice && <Text style={styles.error}>{snapshot.notice}</Text>}
    {snapshot.error && <Text style={styles.error}>{snapshot.error}</Text>}
  </Editor>;
}
