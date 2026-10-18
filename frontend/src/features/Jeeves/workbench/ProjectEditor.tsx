import React, { useState } from 'react';
import { Text, View } from 'react-native';
import type { Project } from './types';
import { LIMITS, PROJECT_COLORS } from './types';
import type { WorkbenchStore } from './WorkbenchStore';
import { normalizeTags } from './validation';
import { Action, Choice, Editor, Field, Toggle, styles } from './ui';

export default function ProjectEditor({ store, project, close }: {
  store: WorkbenchStore;
  project?: Project;
  close: () => void;
}) {
  const [title, setTitle] = useState(project?.title || '');
  const [summary, setSummary] = useState(project?.summary || '');
  const [goal, setGoal] = useState(project?.goal || '');
  const [context, setContext] = useState(project?.context || '');
  const [engine, setEngine] = useState(project?.engine || '');
  const [experience, setExperience] = useState<Project['experience']>(project?.experience || 'beginner');
  const [status, setStatus] = useState<Project['status']>(project?.status || 'active');
  const [color, setColor] = useState<string>(project?.color || PROJECT_COLORS[0]);
  const [tags, setTags] = useState(project?.tags.join(', ') || '');
  const [weekly, setWeekly] = useState(String(project?.weeklyMinutes ?? 120));
  const [target, setTarget] = useState(project?.targetDate || '');
  const [pinned, setPinned] = useState(project?.pinned || false);
  const [error, setError] = useState('');

  const save = () => {
    try {
      const input = {
        title,
        summary,
        goal,
        context,
        engine,
        experience,
        status,
        color,
        tags: normalizeTags(tags),
        weeklyMinutes: Number(weekly),
        targetDate: target.trim() || null,
        pinned,
      };
      const result = project
        ? store.dispatch({ type: 'project.update', id: project.id, revision: project.revision, patch: input })
        : store.dispatch({ type: 'project.create', input });
      if (result) close();
      else setError(store.getSnapshot().notice || 'Could not save the project.');
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Check the project fields.');
    }
  };

  return (
    <Editor
      visible
      title={project ? 'Edit project' : 'New project'}
      close={close}
      footer={<Action label="Save project" icon="checkmark-outline" onPress={save} />}
    >
      <Field label="Project name" value={title} onChange={setTitle} maxLength={LIMITS.title} placeholder="My first playable prototype" />
      <Field label="Summary" value={summary} onChange={setSummary} multiline maxLength={LIMITS.summary} placeholder="What are you making, and who is it for?" />
      <Field label="Concrete goal" value={goal} onChange={setGoal} multiline maxLength={LIMITS.summary} hint="Describe an outcome you can demonstrate or test." placeholder="A player can complete a two-minute level with movement, hazards and a restart." />
      <Field label="Engine or tools" value={engine} onChange={setEngine} maxLength={120} placeholder="Godot 4, Unity, Unreal, Python…" />
      <Choice label="Experience" value={experience} values={['beginner', 'intermediate', 'advanced']} onChange={setExperience} />
      <Choice label="Project status" value={status} values={['active', 'paused', 'completed', 'archived']} onChange={setStatus} />
      <Field label="Project context" value={context} onChange={setContext} multiline maxLength={LIMITS.context} hint="Record constraints, decisions, environment details and what Jeeves should know. Selectively include this in chat context." />
      <Field label="Weekly time budget in minutes" value={weekly} onChange={setWeekly} numeric maxLength={5} hint="Use 0 when you have not set a budget." />
      <Field label="Target date" value={target} onChange={setTarget} maxLength={10} placeholder="YYYY-MM-DD, or leave empty" />
      <Field label="Tags" value={tags} onChange={setTags} maxLength={500} hint="Separate up to 12 short tags with commas." />
      <View style={styles.fieldGroup}>
        <Text style={styles.label}>Project accent</Text>
        <View style={styles.wrap}>
          {PROJECT_COLORS.map((candidate, index) => (
            <Action key={candidate} label={`Color ${index + 1}`} selected={color === candidate} onPress={() => setColor(candidate)} icon="color-palette-outline" />
          ))}
        </View>
        <View style={{ height: 6, borderRadius: 3, backgroundColor: color }} />
      </View>
      <Toggle label="Pin project" value={pinned} onChange={setPinned} hint="Pinned projects appear first in the project picker." />
      {error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    </Editor>
  );
}
