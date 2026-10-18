import React, { useState } from 'react';
import { Text, View } from 'react-native';
import { encodeBackup, previewBackup, projectBackup, recordCount } from './backup';
import { exportName, pickBackupFile, saveTextFile } from './files';
import { inspectIntegrity, orphanWarnings, projectDeletionImpact } from './integrity';
import { projectMarkdown } from './exports';
import { LIMITS } from './types';
import { IntakePanel } from './IntakePanel';
import { Action, Badge, Choice, Field, Section, Toggle, confirmAction, styles } from './ui';
import type { PanelProps } from './ui';

export function SettingsPanel(props: PanelProps) {
  const { state, project, store, now } = props;
  const [newCards, setNewCards] = useState(String(state.preferences.dailyNewCards));
  const [reviews, setReviews] = useState(String(state.preferences.dailyReviewCards));
  const [focus, setFocus] = useState(String(state.preferences.focusMinutes));
  const [pending, setPending] = useState<{ name: string; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const preview = pending ? previewBackup(pending.text) : null;
  const issues = inspectIntegrity(state);
  const warnings = orphanWarnings(state);
  const storageSize = JSON.stringify(state).length;
  const run = async (operation: () => Promise<unknown>) => {
    setBusy(true);
    try { await operation(); }
    catch (error) { store.notify(error instanceof Error ? error.message : 'The operation failed.'); }
    finally { setBusy(false); }
  };
  const importBackup = (mode: 'merge' | 'replace') => {
    if (!pending) return;
    const execute = () => {
      if (store.importBackup(pending.text, mode)) setPending(null);
    };
    if (mode === 'replace') confirmAction('Replace all workbench projects?', 'Export your current work first. This replaces projects, tasks, notes, cards, prompts and focus history. Undo remains available during this visit.', execute);
    else execute();
  };
  return (
    <View style={styles.stack}>
      <Section title="Study and focus preferences" subtitle="These settings apply to all projects on this device.">
        <Field label="New cards per day" value={newCards} onChange={setNewCards} numeric maxLength={3} />
        <Field label="Review cards per day" value={reviews} onChange={setReviews} numeric maxLength={4} />
        <Field label="Default focus minutes" value={focus} onChange={setFocus} numeric maxLength={3} />
        <Action label="Save numeric preferences" onPress={() => store.dispatch({ type: 'preferences.update', patch: { dailyNewCards: Number(newCards), dailyReviewCards: Number(reviews), focusMinutes: Number(focus) } })} />
        <Choice label="Week starts on" value={state.preferences.weekStartsOn} values={['monday', 'sunday']} onChange={weekStartsOn => store.dispatch({ type: 'preferences.update', patch: { weekStartsOn } })} />
        <Toggle label="Include cited sources in default chat context" value={state.preferences.includeSourcesInContext} onChange={includeSourcesInContext => store.dispatch({ type: 'preferences.update', patch: { includeSourcesInContext } })} />
        <Toggle label="Include completed tasks in default chat context" value={state.preferences.includeCompletedTasks} onChange={includeCompletedTasks => store.dispatch({ type: 'preferences.update', patch: { includeCompletedTasks } })} />
      </Section>
      <Section title="Export and back up" subtitle="Work is stored locally on this device. Export a JSON backup before clearing browser or app data.">
        <View style={styles.wrap}>
          <Action label="Full JSON backup" icon="download-outline" disabled={busy} onPress={() => { void run(() => saveTextFile(encodeBackup(state, now), 'jeeves-workbench.json', 'application/json')); }} />
          <Action label="Project JSON backup" disabled={busy} onPress={() => { void run(() => saveTextFile(encodeBackup(projectBackup(state, project.id), now), exportName(project.title, 'json'), 'application/json')); }} />
          <Action label="Project Markdown report" disabled={busy} onPress={() => { void run(() => saveTextFile(projectMarkdown(state, project.id, now), exportName(project.title, 'md'), 'text/markdown')); }} />
        </View>
        <Text style={styles.muted}>Backups contain your project text and study history. Keep exported files somewhere you trust. Chat messages and attachments are exported separately from the chat screen.</Text>
      </Section>
      <Section title="Import a backup" subtitle="Merge creates separate projects with new IDs. Replace restores the file as your workbench. Both validate every record and link first.">
        <Action label="Choose JSON backup" icon="document-outline" disabled={busy} onPress={() => { void run(async () => { const file = await pickBackupFile(); if (file) setPending(file); }); }} />
        {pending && <View style={styles.stack}>
          <Text style={styles.label}>{pending.name}</Text>
          {preview && !preview.ok && preview.issues.map((issue, index) => <Text key={index} style={styles.error}>{issue.path}: {issue.message}</Text>)}
          {preview?.ok && <>
            <View style={styles.wrap}>{Object.entries(preview.value.counts).map(([kind, count]) => <Badge key={kind} text={`${kind}: ${count}`} />)}</View>
            {preview.value.warnings.map((warning, index) => <Text key={index} style={styles.muted}>{warning}</Text>)}
            <View style={styles.wrap}><Action label="Merge as separate projects" onPress={() => importBackup('merge')} /><Action label="Replace workbench" danger onPress={() => importBackup('replace')} /></View>
          </>}
          <Action label="Cancel import" onPress={() => setPending(null)} />
        </View>}
      </Section>
      <IntakePanel {...props} />
      <Section title="Storage and recovery">
        <Text style={styles.text}>{recordCount(state)} records · {Math.round(storageSize / 1024)} / {Math.round(LIMITS.stateCharacters / 1024)} Ki characters · revision {state.revision}</Text>
        <Text style={styles.muted}>Each successful save retains the previous saved snapshot. Undo history lasts only for this visit. Another-tab checks detect changes before saving, but this workbench is intended for one editing tab at a time.</Text>
        <View style={styles.wrap}>
          <Action label="Retry save" onPress={store.retrySave} />
          <Action label="Reload saved version" onPress={() => confirmAction('Reload saved work?', 'Unsaved in-memory changes and undo history will be discarded. Export a backup first if needed.', () => { void store.reloadSaved(); })} />
          <Action label="Restore previous snapshot" disabled={!store.getSnapshot().recoveryAvailable} onPress={() => confirmAction('Restore recovery snapshot?', 'The previous saved snapshot will replace the current workbench. Export current work first.', () => { void store.restoreRecovery(); })} />
        </View>
        <Text style={issues.length ? styles.error : styles.muted}>{issues.length ? `${issues.length} integrity issues` : 'Record links and structural integrity are valid.'}</Text>
        {issues.slice(0, 20).map((issue, index) => <Text key={index} style={styles.error}>{issue.message}</Text>)}
        {warnings.slice(0, 20).map((warning, index) => <Text key={index} style={styles.small}>{warning}</Text>)}
      </Section>
      <Section title="Delete this project">
        <Text style={styles.muted}>This removes the project and its tasks, notes, sources, study cards, reviews, prompts and focus sessions. Shared prompts remain.</Text>
        <Text style={styles.small}>{JSON.stringify(projectDeletionImpact(state, project.id))}</Text>
        <Action label={`Delete ${project.title}`} danger onPress={() => confirmAction('Delete project and its records?', `Delete ${project.title}? Export a project backup first if you need to keep a copy.`, () => store.dispatch({ type: 'project.delete', id: project.id, revision: project.revision }))} />
      </Section>
    </View>
  );
}
