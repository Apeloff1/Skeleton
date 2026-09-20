import React, { useState } from 'react';
import { Text, View } from 'react-native';
import { elapsedFocus, formatDuration, formatMinutes, remainingFocus } from './selectors';
import { MINUTE } from './review';
import { isTerminal } from './planning';
import { focusCsv } from './exports';
import { exportName, saveTextFile } from './files';
import { Action, Badge, Empty, Field, LinksPicker, Metric, Section, confirmAction, styles } from './ui';
import type { PanelProps } from './ui';

export default function FocusPanel({ state, project, store, now }: PanelProps) {
  const [minutes, setMinutes] = useState(String(state.preferences.focusMinutes));
  const [taskIds, setTaskIds] = useState<string[]>([]);
  const [reflection, setReflection] = useState('');
  const running = state.sessions.find(session => session.outcome === 'running');
  const current = running?.projectId === project.id ? running : null;
  const sessions = state.sessions.filter(session => session.projectId === project.id && session.outcome !== 'running')
    .sort((a, b) => b.startedAt - a.startedAt);
  const tasks = state.tasks.filter(task => task.projectId === project.id && !isTerminal(task));
  const readOnly = project.status === 'archived';
  const total = sessions.filter(session => session.outcome === 'completed').reduce((sum, session) => sum + elapsedFocus(session, now), 0);
  const start = () => {
    const result = store.dispatch({
      type: 'focus.start',
      projectId: project.id,
      taskId: taskIds.at(-1) || null,
      minutes: Number(minutes),
    });
    if (result) setReflection('');
  };
  const finish = (outcome: 'completed' | 'abandoned') => {
    if (!current) return;
    const result = store.dispatch({ type: 'focus.finish', id: current.id, outcome, reflection });
    if (result) setReflection('');
  };
  return (
    <View style={styles.stack}>
      <Section title="Focus sessions" subtitle="Record time spent on a specific task and capture a short reflection.">
        <View style={styles.wrap}>
          <Metric label="Completed sessions" value={sessions.filter(session => session.outcome === 'completed').length} />
          <Metric label="Recorded focus" value={formatMinutes(total / MINUTE)} />
        </View>
        <Text style={styles.small}>The timer uses saved timestamps and survives remounts. It does not send notifications or run background automation.</Text>
      </Section>
      {running && !current && <Section title="Another project has a running session">
        <Text style={styles.muted}>Finish that session before starting one here.</Text>
        <Action label="Open active session project" icon="arrow-forward" onPress={() => store.dispatch({ type: 'project.select', id: running.projectId })} />
      </Section>}
      {!running && <Section title="Start a session">
        <Field label="Focus duration in minutes" value={minutes} onChange={setMinutes} numeric maxLength={3} hint="Choose 1–480 minutes. The timer will show overtime without automatically completing your work." />
        <LinksPicker label="Optional task (choose one)" selected={taskIds} options={tasks} onChange={ids => setTaskIds(ids.slice(-1))} />
        <Action label="Start focus session" icon="play-outline" onPress={start} disabled={readOnly} />
      </Section>}
      {current && <Section title={current.pausedAt === null ? 'Focus in progress' : 'Focus paused'}>
        <Text style={[styles.metricValue, styles.centered]}>{formatDuration(remainingFocus(current, now))}</Text>
        <Text style={[styles.muted, styles.centered]}>Remaining · {formatDuration(elapsedFocus(current, now))} active time</Text>
        {remainingFocus(current, now) === 0 && <Badge text="Planned time reached — wrap up when ready" tone="amber" />}
        {!!current.taskId && <Text style={styles.label}>{state.tasks.find(task => task.id === current.taskId)?.title || 'Task no longer available'}</Text>}
        <View style={styles.wrap}>
          {current.pausedAt === null
            ? <Action label="Pause session" icon="pause-outline" onPress={() => store.dispatch({ type: 'focus.pause', id: current.id })} />
            : <Action label="Resume session" icon="play-outline" onPress={() => store.dispatch({ type: 'focus.resume', id: current.id })} />}
        </View>
        <Field label="Session reflection" value={reflection} onChange={setReflection} multiline maxLength={2000} placeholder="What changed? What did you verify? What should you do next?" />
        <Text style={styles.small}>The reflection is saved when you finish the session. Completing a session does not mark its task done.</Text>
        <View style={styles.wrap}>
          <Action label="Finish session" icon="checkmark-outline" onPress={() => finish('completed')} />
          <Action label="Abandon session" icon="stop-outline" danger onPress={() => confirmAction('End without completion?', 'The session will remain in history as abandoned.', () => finish('abandoned'))} />
        </View>
      </Section>}
      <Section title="Session history" action={<Action label="Export focus CSV" icon="download-outline" onPress={() => {
        void saveTextFile(focusCsv(state, project.id, now), exportName(project.title + '-focus', 'csv'), 'text/csv').catch(() => store.notify('Focus export failed.'));
      }} />}>
        {!sessions.length && <Empty icon="timer-outline" title="No finished sessions" message="Start a short session and record what you accomplished." />}
        {sessions.map(session => <View key={session.id} style={styles.card}>
          <View style={styles.wrap}>
            <Badge text={session.outcome} tone={session.outcome === 'completed' ? 'green' : 'amber'} />
            <Text style={styles.small}>{new Date(session.startedAt).toLocaleString()}</Text>
          </View>
          <Text style={styles.label}>{formatMinutes(elapsedFocus(session, now) / MINUTE)} active · {session.plannedMinutes}m planned</Text>
          {session.taskId && <Text style={styles.muted}>{state.tasks.find(task => task.id === session.taskId)?.title}</Text>}
          {!!session.reflection && <Text selectable style={styles.text}>{session.reflection}</Text>}
          <Action label="Delete session record" icon="trash-outline" danger compact onPress={() => confirmAction('Delete session record?', 'This removes its recorded focus time from project totals.', () => store.dispatch({ type: 'focus.delete', id: session.id, revision: session.revision }))} />
        </View>)}
      </Section>
    </View>
  );
}
