import React, { useMemo, useState } from 'react';
import { Text, View } from 'react-native';
import { weeklyReview, weeklyReviewMarkdown } from './insights';
import { exportName, saveTextFile } from './files';
import { formatMinutes } from './selectors';
import type { WorkbenchTab } from './types';
import { Action, Badge, Field, Metric, Section, styles } from './ui';
import type { PanelProps } from './ui';

export default function WeeklyReviewPanel({ state, project, store, now, navigate }: PanelProps & { navigate: (tab: WorkbenchTab) => void }) {
  const [offset, setOffset] = useState(0);
  const [reflection, setReflection] = useState('');
  const review = useMemo(() => weeklyReview(state, project.id, now, offset), [state, project.id, now, offset]);
  const signed = (value: number) => `${value > 0 ? '+' : ''}${value}`;
  const saveReflection = () => {
    if (store.dispatch({ type: 'note.create', input: {
      projectId: project.id,
      title: `Weekly review ${review.current.window.label}`,
      kind: 'retrospective',
      confidence: 'unverified',
      body: `${reflection}\n\n${weeklyReviewMarkdown(review)}`.slice(0, 30000),
      tags: ['weekly-review'],
    } })) {
      setReflection('');
      store.notify('Weekly reflection saved in your notebook.');
    }
  };
  return (
    <View style={styles.stack}>
      <Section title="Weekly review" subtitle={review.current.window.label}>
        <View style={styles.wrap}>
          <Action label="Previous week" disabled={offset <= -52} onPress={() => setOffset(offset - 1)} />
          <Action label="This week" selected={offset === 0} onPress={() => setOffset(0)} />
          <Action label="Next week" disabled={offset === 0} onPress={() => setOffset(offset + 1)} />
          <Action label="Export review" icon="download-outline" onPress={() => {
            void saveTextFile(weeklyReviewMarkdown(review), exportName(`${project.title}-week-${review.current.window.label}`, 'md'), 'text/markdown').catch(() => store.notify('Weekly review export failed.'));
          }} />
        </View>
        <View style={styles.wrap}>
          <Metric label="Completed tasks" value={review.current.completedTasks.length} detail={`${signed(review.completionChange)} compared with previous week`} />
          <Metric label="Completed focus" value={formatMinutes(review.current.focusMinutes)} detail={`${signed(review.focusChange)} minutes compared with previous week`} />
          <Metric label="Study answers" value={review.current.reviewCount} detail={`${review.current.reviewedCards} distinct cards`} />
          <Metric label="New notes" value={review.current.createdNotes.length} />
        </View>
        <Text style={styles.small}>This week is partial. Comparisons use retained local records. Focus is attributed to the day the session ended; deleting records changes these totals.</Text>
      </Section>
      <Section title="What moved forward">
        {!review.current.completedTasks.length && <Text style={styles.muted}>No completed tasks recorded for this week.</Text>}
        {review.current.completedTasks.slice(0, 30).map(task => <View key={task.id} style={styles.card}><Text style={styles.label}>{task.title}</Text><Text style={styles.small}>{task.completedAt ? new Date(task.completedAt).toLocaleDateString() : ''}</Text></View>)}
        {review.current.completedTasks.length > 30 && <Text style={styles.small}>Showing 30 tasks. Export includes the complete list.</Text>}
        {!!review.current.reflections.length && <Text style={styles.label}>Focus reflections</Text>}
        {review.current.reflections.slice(0, 10).map(item => <Text key={item.id} style={styles.text}>{item.text}</Text>)}
      </Section>
      <Section title="Study self-assessment" subtitle="These are your recorded answer grades. They do not measure retention or mastery.">
        <View style={styles.wrap}>{Object.entries(review.current.grades).map(([grade, count]) => <Badge key={grade} text={`${grade}: ${count}`} />)}</View>
        <Action label="Open study cards" onPress={() => navigate('study')} />
      </Section>
      <Section title="Current blockers" subtitle="This section shows today’s task state, including when you review a past week.">
        {!review.blockers.length && <Text style={styles.muted}>No dependency or manual blockers recorded.</Text>}
        {review.blockers.slice(0, 15).map(blocker => <View key={blocker.taskId} style={styles.card}>
          <Text style={styles.label}>{blocker.title}</Text>
          {blocker.manual && <Badge text="Manually blocked" tone="amber" />}
          <Text style={styles.muted}>Waiting for: {blocker.blockedBy.map(id => state.tasks.find(task => task.id === id)?.title || id).join(' → ') || 'a manually recorded blocker'}</Text>
          <Text style={styles.small}>{blocker.downstream} unfinished downstream task(s)</Text>
        </View>)}
        <Text style={styles.muted}>{review.overdueTasks.length} overdue · {review.staleTasks.length} unchanged for 14 days · {review.readyTasks.length} available to start</Text>
        <Action label="Review task board" onPress={() => navigate('tasks')} />
      </Section>
      <Section title="Knowledge to revisit">
        {!review.evidenceGaps.length && <Text style={styles.muted}>No evidence gaps detected by these structural checks.</Text>}
        {review.evidenceGaps.slice(0, 15).map(gap => <View key={gap.noteId} style={styles.card}>
          <Text style={styles.label}>{gap.title}</Text>
          <Badge text={gap.reason} tone="amber" />
          <Text style={styles.muted}>{gap.detail}</Text>
        </View>)}
        <Text style={styles.small}>{review.uncitedSources.length} sources are not cited by any note or card. A citation alone does not establish that a claim is correct.</Text>
        <Action label="Review notebook" onPress={() => navigate('notes')} />
      </Section>
      <Section title="Write your reflection" subtitle="Save your conclusions and next steps as a retrospective note.">
        {review.prompts.map(prompt => <Text key={prompt} style={styles.muted}>• {prompt}</Text>)}
        <Field label="What did you learn, and what will you change?" value={reflection} onChange={setReflection} multiline maxLength={12000} />
        <Action label="Save weekly reflection" icon="save-outline" disabled={!reflection.trim() || project.status === 'archived'} onPress={saveReflection} />
      </Section>
    </View>
  );
}
