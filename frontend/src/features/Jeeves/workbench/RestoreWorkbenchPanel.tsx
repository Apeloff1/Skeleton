import React, { useState } from 'react';
import { Text, View } from 'react-native';
import { previewBackup } from './backup';
import { pickBackupFile } from './files';
import type { WorkbenchStore } from './WorkbenchStore';
import { Action, Badge, Section, styles } from './ui';

/** Import remains reachable before a device has its first project. */
export default function RestoreWorkbenchPanel({ store }: { store: WorkbenchStore }) {
  const [file, setFile] = useState<{ name: string; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const preview = file ? previewBackup(file.text) : null;
  const choose = async () => {
    setBusy(true);
    setError('');
    try {
      const selected = await pickBackupFile();
      if (selected) setFile(selected);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not open the backup file.');
    } finally {
      setBusy(false);
    }
  };
  const restore = () => {
    if (!file || !preview?.ok) return;
    if (store.importBackup(file.text, 'merge')) {
      const active = store.getSnapshot().state.activeProjectId;
      if (!active && preview.value.counts.project === 0) store.notify('Imported shared records. Create a project to begin using the workbench.');
      setFile(null);
      setError('');
    } else {
      setError(store.getSnapshot().notice || 'The backup could not be imported.');
    }
  };
  return <Section title="Bring your work from another device" subtitle="Choose a Jeeves JSON backup. Review its contents before importing it into this device’s workbench.">
    <Action label="Open a workbench backup" icon="folder-open-outline" disabled={busy} onPress={() => { void choose(); }} />
    {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    {file && <View style={styles.stack}>
      <Text style={styles.label}>{file.name}</Text>
      {preview && !preview.ok && preview.issues.slice(0, 20).map((issue, index) => <Text key={index} style={styles.error}>{issue.path}: {issue.message}</Text>)}
      {preview?.ok && <>
        <View style={styles.wrap}>{Object.entries(preview.value.counts).map(([kind, count]) => <Badge key={kind} text={`${kind}: ${count}`} />)}</View>
        {preview.value.warnings.slice(0, 20).map((warning, index) => <Text key={index} style={styles.muted}>{warning}</Text>)}
        <Action label="Import these records" icon="download-outline" onPress={restore} />
      </>}
      <Action label="Cancel backup import" onPress={() => { setFile(null); setError(''); }} />
    </View>}
  </Section>;
}
