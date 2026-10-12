import React, { useState } from 'react';
import { Text, View } from 'react-native';
import { useRouter } from 'expo-router';
import { workbenchStore } from './store';
import {
  ChatTaskPlan, commitChatTasks, extractChatTaskTitles,
  prepareChatTasks, undoChatTasks,
} from './chatTaskActions';
import { Action, Editor, palette, styles } from './ui';

/** Workbench tasks are only applied on explicit user confirmation. */
export default function ChatTaskActions({
  text, conversationId, messageId, notify,
}: {
  text: string;
  conversationId: string;
  messageId: string;
  notify: (notice: string) => void;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [plan, setPlan] = useState<ChatTaskPlan | null>(null);
  const [error, setError] = useState('');
  const [working, setWorking] = useState(false);
  const [appliedRevision, setAppliedRevision] = useState<number | null>(null);

  if (!extractChatTaskTitles(text).length) return null;

  const select = (projectId: string) => {
    try {
      const next = prepareChatTasks(
        workbenchStore.getSnapshot().state,
        projectId,
        text,
        conversationId,
        messageId,
      );
      setPlan(next);
      setError('');
    } catch (failure) {
      setPlan(null);
      setError(failure instanceof Error ? failure.message : 'Cannot preview these tasks.');
    }
  };

  const preview = async () => {
    setWorking(true);
    try {
      await workbenchStore.initialize();
      const current = workbenchStore.getSnapshot();
      if (!current.ready) throw new Error(current.error || 'Workbench cannot be opened.');
      const project = current.state.projects.find(item =>
        item.id === current.state.activeProjectId && item.status !== 'archived'
      ) || current.state.projects.find(item => item.status !== 'archived');
      setOpen(true);
      if (project) select(project.id);
      else {
        setPlan(null);
        setError('Create a project in Workbench before importing chat tasks.');
      }
    } catch (failure) {
      notify(failure instanceof Error ? failure.message : 'Workbench is unavailable.');
    } finally {
      setWorking(false);
    }
  };

  const apply = async () => {
    if (!plan || working) return;
    setWorking(true);
    try {
      const outcome = await commitChatTasks(workbenchStore, plan);
      if (outcome.status === 'saved') {
        setAppliedRevision(outcome.revision);
        setPlan(null);
        setOpen(false);
      } else if (outcome.status === 'unsaved') {
        setPlan(null);
        setOpen(false);
      } else {
        setError(outcome.message);
      }
      notify(outcome.message);
    } catch {
      setError('The task import did not finish. Inspect Workbench before trying again.');
    } finally {
      setWorking(false);
    }
  };

  const undo = async () => {
    if (appliedRevision === null || working) return;
    setWorking(true);
    try {
      const undone = await undoChatTasks(workbenchStore, appliedRevision);
      if (undone) setAppliedRevision(null);
      notify(undone ? 'The imported task batch was undone and saved.' :
        'Cannot safely undo: Workbench has changed or storage is not confirmed. Review the task board.');
    } finally {
      setWorking(false);
    }
  };

  const state = workbenchStore.getSnapshot().state;
  return (
    <View style={{ gap: 7, marginTop: 8 }}>
      <Action icon="list-outline" label="Review as project tasks"
        onPress={() => { void preview(); }} disabled={working} compact />
      {appliedRevision !== null && (
        <Action icon="arrow-undo-outline" label="Undo task import"
          onPress={() => { void undo(); }} disabled={working} compact />
      )}
      <Editor visible={open} title="Review Jeeves task proposal"
        close={() => { if (!working) setOpen(false); }}
        footer={
          <View style={{ gap: 8 }}>
            <Action icon="checkmark-circle-outline" label="Add reviewed tasks to Workbench"
              onPress={() => { void apply(); }} disabled={!plan || working} />
            <Action icon="close-outline" label="Cancel without changes"
              onPress={() => setOpen(false)} disabled={working} />
          </View>
        }>
        <Text style={styles.muted}>
          Assistant text is untrusted. These are proposed workbench tasks only:
          they will not execute game code or modify any game assets.
        </Text>
        <Text style={styles.label}>Choose the destination project</Text>
        <View style={styles.wrap}>
          {state.projects.filter(item => item.status !== 'archived').map(item => (
            <Action key={item.id} label={item.title}
              icon={plan?.projectId === item.id ? 'checkmark-circle' : 'folder-outline'}
              selected={plan?.projectId === item.id}
              onPress={() => select(item.id)} disabled={working} compact />
          ))}
        </View>
        {plan && <Text style={[styles.label, { marginTop: 12 }]}>
          {plan.steps.length} task(s) to create in {plan.projectTitle}
        </Text>}
        {plan?.steps.map(step => (
          <View key={step.ordinal} style={{
            backgroundColor: palette.panel,
            borderColor: palette.border,
            borderWidth: 1,
            borderRadius: 9,
            padding: 12,
          }}>
            <Text style={styles.text}>{step.ordinal}. {step.title}</Text>
            <Text style={styles.small}>Inbox · normal priority · 0 estimated minutes</Text>
          </View>
        ))}
        {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
        <Action icon="open-outline" label="Open Workbench"
          onPress={() => { setOpen(false); router.push('/jeeves-workbench'); }} />
      </Editor>
    </View>
  );
}
