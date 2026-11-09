import React, { useMemo, useState } from 'react';
import { Text, View } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { buildContext, defaultContextSelection } from './context';
import type { ContextSelection } from './types';
import { Action, Badge, Field, LinksPicker, Section, Toggle, styles } from './ui';
import type { PanelProps } from './ui';

export function ContextPanel({ state, project, store, send }: PanelProps & {
  send: (draft: string, selection: ContextSelection) => void;
}) {
  const [selection, setSelection] = useState(() => defaultContextSelection(state, project.id));
  const [draft, setDraft] = useState('Help me decide the next useful step for this project.');
  const bundle = useMemo(() => buildContext(state, selection), [state, selection]);
  return (
    <View style={styles.stack}>
      <Section title="Choose what Jeeves sees" subtitle="Review the exact project material attached to a new chat. Nothing is sent until you press Send in chat.">
        <Toggle label="Include project goal and background" value={selection.includeProject} onChange={includeProject => setSelection({ ...selection, includeProject })} />
        <LinksPicker label="Tasks" selected={selection.taskIds} options={state.tasks.filter(item => item.projectId === project.id)} onChange={taskIds => setSelection({ ...selection, taskIds })} />
        <LinksPicker label="Notes" selected={selection.noteIds} options={state.notes.filter(item => item.projectId === project.id && !item.archived)} onChange={noteIds => setSelection({ ...selection, noteIds })} />
        <LinksPicker label="Sources" selected={selection.sourceIds} options={state.sources.filter(item => item.projectId === project.id)} onChange={sourceIds => setSelection({ ...selection, sourceIds })} />
        <View style={styles.wrap}>
          {[1000, 2000, 4000].map(maxCharacters => <Action key={maxCharacters} label={`${maxCharacters} characters`} selected={selection.maxCharacters === maxCharacters} onPress={() => setSelection({ ...selection, maxCharacters })} />)}
          <Action label="Reset selection" onPress={() => setSelection(defaultContextSelection(state, project.id))} />
        </View>
      </Section>
      <Section title="Context preview" subtitle={`${bundle.characters} / ${bundle.budget} characters`}>
        {bundle.sections.map(section => <View key={`${section.kind}-${section.id}`} style={styles.card}>
          <View style={styles.wrap}><Text style={styles.label}>{section.label}</Text>{section.truncated && <Badge text="Shortened to fit" tone="amber" />}</View>
          <Text selectable style={styles.text}>{section.text}</Text>
        </View>)}
        {!bundle.sections.length && <Text style={styles.muted}>No project context selected.</Text>}
        {bundle.omitted.map((reason, index) => <Text key={index} style={styles.error}>{reason}</Text>)}
        <Action label="Copy exact context" icon="copy-outline" onPress={() => {
          void Clipboard.setStringAsync(bundle.text).then(() => store.notify('Context copied.')).catch(() => store.notify('Clipboard unavailable. Select the preview text to copy it.'));
        }} />
      </Section>
      <Section title="Start a project conversation">
        <Field label="Your question" value={draft} onChange={setDraft} multiline maxLength={16000} />
        <Action label="Open draft in Jeeves" icon="chatbubble-outline" disabled={!draft.trim()} onPress={() => send(draft, selection)} />
      </Section>
    </View>
  );
}
