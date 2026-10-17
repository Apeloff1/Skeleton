import React, { useMemo, useState } from 'react';
import { Text, View } from 'react-native';
import type { Command } from './domain';
import { previewCardTable, previewMarkdownNotes, previewMarkdownTasks, previewTaskTable, validIntakeValues } from './intake';
import { Action, Badge, Choice, Field, Section, styles } from './ui';
import type { PanelProps } from './ui';

type IntakeMode = 'task-csv' | 'task-list' | 'card-tsv' | 'note-markdown';
const examples: Record<IntakeMode, string> = {
  'task-csv': 'title,description,status,priority,estimate_minutes,due_date,tags\nBuild movement,Start with keyboard controls,inbox,high,30,,prototype',
  'task-list': '- [ ] Build movement\n- [ ] Test the camera\n- [x] Create the project',
  'card-tsv': 'question\tanswer\thint\ttags\nWhat does delta time represent?\tElapsed time since the previous frame.\tThink frame rate.\tgame-loop',
  'note-markdown': '# Movement experiment\nCompare acceleration curves in a small test scene.\n\n# Camera decision\nStart with a fixed camera until movement feels good.',
};

export function IntakePanel({ project, store }: PanelProps) {
  const [mode, setMode] = useState<IntakeMode>('task-list');
  const [input, setInput] = useState('');
  const [previewed, setPreviewed] = useState(false);
  const prepared = useMemo(() => {
    if (!previewed || !input.trim()) return null;
    try {
      const preview = mode === 'task-csv' ? previewTaskTable(input, project.id)
        : mode === 'task-list' ? previewMarkdownTasks(input, project.id)
        : mode === 'card-tsv' ? previewCardTable(input, project.id)
        : previewMarkdownNotes(input, project.id);
      return { preview, error: null };
    } catch (error) {
      return { preview: null, error: error instanceof Error ? error.message : 'Could not read the pasted data.' };
    }
  }, [input, mode, previewed, project.id]);
  const importRows = () => {
    let commands: Command[];
    try {
      if (mode === 'task-csv' || mode === 'task-list') {
        const preview = mode === 'task-csv' ? previewTaskTable(input, project.id) : previewMarkdownTasks(input, project.id);
        commands = validIntakeValues(preview).map(input => ({ type: 'task.create', input }));
      } else if (mode === 'card-tsv') {
        commands = validIntakeValues(previewCardTable(input, project.id)).map(input => ({ type: 'card.create', input }));
      } else {
        commands = validIntakeValues(previewMarkdownNotes(input, project.id)).map(input => ({ type: 'note.create', input }));
      }
      if (store.dispatchBatch(commands)) {
        setInput('');
        setPreviewed(false);
      }
    } catch (error) {
      store.notify(error instanceof Error ? error.message : 'Import could not be completed.');
    }
  };
  return (
    <Section title="Bring existing work into this project" subtitle="Preview pasted text before importing. Every row must be valid; the complete import can be undone as one change.">
      <Choice label="Format" value={mode} values={['task-list', 'task-csv', 'card-tsv', 'note-markdown']} onChange={value => { setMode(value); setPreviewed(false); }} labels={{ 'task-list': 'Task list', 'task-csv': 'Tasks CSV', 'card-tsv': 'Cards TSV', 'note-markdown': 'Markdown notes' }} />
      <Text selectable style={styles.small}>Example format:{'\n'}{examples[mode]}</Text>
      <Field label="Paste records" value={input} onChange={value => { setInput(value); setPreviewed(false); }} multiline maxLength={500000} hint="Pasted content stays on this device. CSV and TSV support quoted multiline fields." />
      <Action label="Preview import" disabled={!input.trim()} onPress={() => setPreviewed(true)} />
      {prepared?.error && <Text accessibilityRole="alert" style={styles.error}>{prepared.error}</Text>}
      {prepared?.preview && <View style={styles.stack}>
        <View style={styles.wrap}><Badge text={`${prepared.preview.valid} valid`} tone="green" /><Badge text={`${prepared.preview.invalid} invalid`} tone={prepared.preview.invalid ? 'red' : 'muted'} /></View>
        {prepared.preview.warnings.map(warning => <Text key={warning} style={styles.muted}>{warning}</Text>)}
        {prepared.preview.rows.slice(0, 50).map((row, index) => <View key={index} style={styles.card}>
          <Text style={styles.label}>Line {row.line}: {row.value && ('title' in row.value ? row.value.title : row.value.question)}</Text>
          {row.errors.map(error => <Text key={error} style={styles.error}>{error}</Text>)}
          {row.warnings.map(warning => <Text key={warning} style={styles.muted}>{warning}</Text>)}
        </View>)}
        {prepared.preview.rows.length > 50 && <Text style={styles.muted}>Showing the first 50 rows. Validation covers all {prepared.preview.rows.length} rows.</Text>}
        <Action label={`Import ${prepared.preview.valid} records`} disabled={!!prepared.preview.invalid || !prepared.preview.valid || project.status === 'archived'} onPress={importRows} />
      </View>}
    </Section>
  );
}
