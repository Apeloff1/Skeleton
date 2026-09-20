import React from 'react';
import { Text, View } from 'react-native';
import type { WorkbenchTab } from './types';
import { activityDays, capacityForecast, dashboard, formatMinutes, relativeTime } from './selectors';
import { criticalPath, projectRisks } from './planning';
import { Action, Badge, Metric, Section, styles } from './ui';
import type { PanelProps } from './ui';

export default function OverviewPanel({ state, project, now, navigate }: PanelProps & { navigate: (tab: WorkbenchTab) => void }) {
  const summary = dashboard(state, project.id, now)!;
  const risks = projectRisks(state, project.id, now);
  const capacity = capacityForecast(state, project.id);
  const path = criticalPath(state.tasks.filter(task => task.projectId === project.id));
  const activity = activityDays(state, project.id, now, 7);
  return (
    <View style={styles.stack}>
      <Section title={project.title} subtitle={project.summary || 'A place to turn your goal into recorded, verifiable work.'}>
        <View style={styles.wrap}>
          <Badge text={project.status} tone="accent" />
          {!!project.engine && <Badge text={project.engine} />}
          <Badge text={project.experience} />
          {project.tags.map(tag => <Badge key={tag} text={`#${tag}`} />)}
        </View>
        <Text style={styles.label}>Goal</Text>
        <Text selectable style={styles.text}>{project.goal || 'Set a concrete goal in project details.'}</Text>
        <View style={styles.wrap}>
          <Metric label="Task completion" value={`${summary.completionPercent}%`} detail={`${summary.completedTasks} of ${summary.taskCount} tasks done`} />
          <Metric label="Ready to study" value={summary.dueCards} />
          <Metric label="Recorded focus" value={formatMinutes(summary.focusMinutes)} />
          <Metric label="Notes and sources" value={summary.notes + summary.sources} />
        </View>
      </Section>
      {!!risks.length && <Section title="Needs attention">
        {risks.map(risk => <View key={risk.code} style={styles.card}>
          <Badge text={risk.severity} tone={risk.severity === 'warning' ? 'amber' : 'muted'} />
          <Text style={styles.text}>{risk.message}</Text>
        </View>)}
      </Section>}
      <Section title="Available next tasks" subtitle="Tasks with no unfinished dependencies or manual block." action={<Action label="Open task board" icon="arrow-forward" onPress={() => navigate('tasks')} />}>
        {!summary.nextTasks.length && <Text style={styles.muted}>No available tasks. Add a task or resolve an existing dependency.</Text>}
        {summary.nextTasks.map(task => <View key={task.id} style={styles.card}>
          <Text style={styles.label}>{task.title}</Text>
          <Text style={styles.small}>{task.priority} priority · {task.estimateMinutes ? formatMinutes(task.estimateMinutes) : 'Unestimated'}</Text>
        </View>)}
      </Section>
      <Section title="Scope and capacity" subtitle="Estimates come from your task records, not from an AI prediction.">
        <Text style={styles.text}>{formatMinutes(capacity.minutes)} of estimated open work</Text>
        <Text style={styles.muted}>{capacity.weeks === null ? 'Set a weekly budget to calculate a rough number of weeks.' : `Approximately ${capacity.weeks} week(s) at ${formatMinutes(project.weeklyMinutes)} per week, before interruptions or rework.`}</Text>
        {!!capacity.unestimated && <Text style={styles.error}>{capacity.unestimated} task(s) are not estimated and are excluded from this total.</Text>}
        <Text style={styles.muted}>Longest dependency chain: {formatMinutes(path.estimatedMinutes)} of estimated work.</Text>
        {!!path.taskIds.length && <Text style={styles.small}>{path.taskIds.map(id => state.tasks.find(task => task.id === id)?.title || id).join(' → ')}</Text>}
      </Section>
      <Section title="Last seven days">
        {activity.map(day => <View key={day.date} style={styles.row}>
          <Text style={[styles.small, styles.flex]}>{day.date}</Text>
          <Text style={styles.small}>{day.completedTasks} tasks · {day.focusMinutes}m focus · {day.reviews} reviews</Text>
        </View>)}
        <Text style={styles.small}>Focus time is attributed to the session’s completion date. Activity reflects retained records only.</Text>
      </Section>
      <Section title="Recent notes" action={<Action label="Open notebook" icon="arrow-forward" onPress={() => navigate('notes')} />}>
        {!summary.recentNotes.length && <Text style={styles.muted}>Record what you learn so you can reuse it in future conversations.</Text>}
        {summary.recentNotes.map(note => <View key={note.id} style={styles.card}>
          <Text style={styles.label}>{note.title}</Text>
          <Text numberOfLines={2} style={styles.muted}>{note.body}</Text>
          <Badge text={note.confidence} />
        </View>)}
      </Section>
      <Section title="Recent activity">
        {!summary.recentEvents.length && <Text style={styles.muted}>Your next changes will appear here.</Text>}
        {summary.recentEvents.map(event => <View key={event.id} style={styles.row}>
          <Text style={[styles.text, styles.flex]}>{event.summary}</Text>
          <Text style={styles.small}>{relativeTime(event.at, now)}</Text>
        </View>)}
      </Section>
    </View>
  );
}
