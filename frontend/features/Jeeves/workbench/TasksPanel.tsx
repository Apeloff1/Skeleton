import React, { useMemo, useState } from 'react';
import { Pagination, usePage } from './PageNavigation';
import { Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import type { ChecklistItem, Priority, Task, TaskFilter, TaskStatus } from './types';
import { LIMITS, PRIORITIES, TASK_STATUSES } from './types';
import { normalizeTags } from './validation';
import { filterTasks, formatMinutes, taskProgress } from './selectors';
import { canStart, isTerminal, planSession, unmetDependencies } from './planning';
import { tasksCsv } from './exports';
import { exportName, saveTextFile } from './files';
import { Action, Badge, Choice, Editor, Empty, Field, LinksPicker, Section, confirmAction, palette, styles } from './ui';
import type { PanelProps } from './ui';

function checklistId(): string {
  return globalThis.crypto?.randomUUID?.() || `check-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export function TaskEditor({ store, state, project, task, close }: PanelProps & { task?: Task; close: () => void }) {
  const [title, setTitle] = useState(task?.title || '');
  const [description, setDescription] = useState(task?.description || '');
  const [status, setStatus] = useState<TaskStatus>(task?.status || 'inbox');
  const [priority, setPriority] = useState<Priority>(task?.priority || 'normal');
  const [estimate, setEstimate] = useState(String(task?.estimateMinutes ?? 25));
  const [due, setDue] = useState(task?.dueDate || '');
  const [tags, setTags] = useState(task?.tags.join(', ') || '');
  const [dependencies, setDependencies] = useState(task?.dependencies || []);
  const [notes, setNotes] = useState(task?.noteIds || []);
  const [checklist, setChecklist] = useState<ChecklistItem[]>(task?.checklist.map(item => ({ ...item })) || []);
  const [newItem, setNewItem] = useState('');
  const [error, setError] = useState('');
  const addItem = () => {
    if (!newItem.trim()) return;
    if (checklist.length >= LIMITS.checklist) {
      setError(`Use at most ${LIMITS.checklist} checklist items.`);
      return;
    }
    setChecklist([...checklist, { id: checklistId(), text: newItem.trim(), done: false }]);
    setNewItem('');
  };
  const save = () => {
    try {
      const input = {
        title,
        description,
        status,
        priority,
        estimateMinutes: Number(estimate),
        dueDate: due.trim() || null,
        tags: normalizeTags(tags),
        dependencies,
        noteIds: notes,
        checklist,
      };
      const result = task
        ? store.dispatch({ type: 'task.update', id: task.id, revision: task.revision, patch: input })
        : store.dispatch({ type: 'task.create', input: { ...input, projectId: project.id } });
      if (result) close();
      else setError(store.getSnapshot().notice || 'Could not save the task.');
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Check the task fields.');
    }
  };
  return (
    <Editor visible title={task ? 'Edit task' : 'New task'} close={close} footer={<Action label="Save task" icon="checkmark-outline" onPress={save} />}>
      <Field label="Task title" value={title} onChange={setTitle} maxLength={LIMITS.title} placeholder="Build a small, verifiable outcome" />
      <Field label="Description and acceptance criteria" value={description} onChange={setDescription} multiline maxLength={LIMITS.body} hint="Describe what will change and how you will know it works." />
      <Choice label="Status" value={status} values={TASK_STATUSES} onChange={setStatus} />
      <Choice label="Priority" value={priority} values={PRIORITIES} onChange={setPriority} />
      <Field label="Estimated minutes" value={estimate} onChange={setEstimate} numeric maxLength={5} hint="Use 0 for work that still needs estimating." />
      <Field label="Due date" value={due} onChange={setDue} maxLength={10} placeholder="YYYY-MM-DD, or leave empty" />
      <Field label="Tags" value={tags} onChange={setTags} maxLength={500} placeholder="movement, prototype, input" />
      <Section title="Completion checklist" subtitle="Every item must be checked before the task can be marked done.">
        {checklist.map(item => (
          <View key={item.id} style={styles.row}>
            <TouchableOpacity
              accessibilityRole="checkbox"
              accessibilityLabel={item.text}
              accessibilityState={{ checked: item.done }}
              onPress={() => setChecklist(checklist.map(current => current.id === item.id ? { ...current, done: !current.done } : current))}
            >
              <Ionicons name={item.done ? 'checkbox' : 'square-outline'} color={palette.accent} size={23} />
            </TouchableOpacity>
            <Text style={[styles.text, styles.flex]}>{item.text}</Text>
            <Action label="Remove item" icon="close" compact onPress={() => setChecklist(checklist.filter(current => current.id !== item.id))} />
          </View>
        ))}
        <Field label="New checklist item" value={newItem} onChange={setNewItem} maxLength={500} />
        <Action label="Add checklist item" icon="add" onPress={addItem} disabled={!newItem.trim()} />
      </Section>
      <LinksPicker
        label="Depends on"
        selected={dependencies}
        options={state.tasks.filter(item => item.projectId === project.id && item.id !== task?.id).map(item => ({ id: item.id, title: `${item.title} (${item.status})` }))}
        onChange={setDependencies}
      />
      <LinksPicker
        label="Related notes"
        selected={notes}
        options={state.notes.filter(item => item.projectId === project.id && !item.archived)}
        onChange={setNotes}
      />
      {error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    </Editor>
  );
}

export default function TasksPanel(props: PanelProps & { discuss: (task: Task) => void }) {
  const { state, project, store, now } = props;
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState<TaskStatus | 'all' | 'open'>('open');
  const [sort, setSort] = useState<NonNullable<TaskFilter['sort']>>('manual');
  const [due, setDue] = useState<NonNullable<TaskFilter['due']> | 'all'>('all');
  const [editor, setEditor] = useState<Task | 'new' | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [planMinutes, setPlanMinutes] = useState('60');
  const [showPlan, setShowPlan] = useState(false);
  const tasks = useMemo(() => filterTasks(state, project.id, {
    query,
    statuses: filter === 'all' ? undefined : filter === 'open' ? ['inbox', 'ready', 'doing', 'blocked'] : [filter],
    sort,
    due: due === 'all' ? undefined : due,
  }, now), [state, project.id, query, filter, sort, due, now]);
  const projectTasks = state.tasks.filter(task => task.projectId === project.id);
  const { page, setPage } = usePage(tasks, JSON.stringify([query, filter, sort, due]));
  const plan = useMemo(() => {
    try { return planSession(projectTasks, Number(planMinutes), now); }
    catch { return null; }
  }, [projectTasks, planMinutes, now]);
  const readOnly = project.status === 'archived';
  const remove = (task: Task) => confirmAction('Delete task?', `Delete “${task.title}”? Undo remains available during this visit.`, () => {
    store.dispatch({ type: 'task.delete', id: task.id, revision: task.revision });
  });
  const move = (task: Task, direction: -1 | 1) => {
    const ordered = [...projectTasks].sort((a, b) => a.order - b.order || a.id.localeCompare(b.id));
    const index = ordered.findIndex(item => item.id === task.id);
    const target = index + direction;
    if (target < 0 || target >= ordered.length) return;
    [ordered[index], ordered[target]] = [ordered[target], ordered[index]];
    store.dispatch({ type: 'task.reorder', projectId: project.id, ids: ordered.map(item => item.id) });
  };
  const batch = (status: TaskStatus) => {
    const ids = selected.filter(id => projectTasks.some(task => task.id === id));
    if (store.dispatch({ type: 'task.batch-status', ids, status })) setSelected([]);
  };
  return (
    <View style={styles.stack}>
      <Section
        title="Task board"
        subtitle={`${projectTasks.filter(task => !isTerminal(task)).length} open · ${projectTasks.filter(task => task.status === 'done').length} complete`}
        action={<Action label="New task" icon="add" onPress={() => setEditor('new')} disabled={readOnly} />}
      >
        <Field label="Search tasks" value={query} onChange={setQuery} maxLength={200} placeholder="Search titles, descriptions or checklists" />
        <Choice label="Show" value={filter} values={['open', 'all', ...TASK_STATUSES]} onChange={setFilter} />
        <Choice label="Order by" value={sort} values={['manual', 'priority', 'due', 'updated', 'estimate']} onChange={setSort} />
        <Choice label="Due" value={due} values={['all', 'overdue', 'today', 'week', 'none']} onChange={setDue} />
        <View style={styles.wrap}>
          <Action label="Plan a session" icon="time-outline" selected={showPlan} onPress={() => setShowPlan(!showPlan)} />
          <Action label="Export task CSV" icon="download-outline" onPress={() => {
            void saveTextFile(tasksCsv(projectTasks, [project]), exportName(project.title + '-tasks', 'csv'), 'text/csv').catch(() => store.notify('Task export failed.'));
          }} />
        </View>
      </Section>
      {showPlan && (
        <Section title="Suggested work session" subtitle="A deterministic plan based on priority, dependencies and your time budget.">
          <Field label="Available minutes" value={planMinutes} onChange={setPlanMinutes} numeric maxLength={3} />
          {!plan && <Text style={styles.error}>Choose a whole number from 5 to 480 minutes.</Text>}
          {plan && <>
            <Text style={styles.text}>{formatMinutes(plan.plannedMinutes)} planned · {formatMinutes(plan.remainingMinutes)} remaining</Text>
            {plan.items.map((item, index) => (
              <View key={item.task.id} style={styles.card}>
                <Text style={styles.label}>{index + 1}. {item.task.title}</Text>
                <Text style={styles.muted}>{item.startMinute}–{item.endMinute} min · {item.reason}</Text>
                {!item.estimated && <Badge text="Uses a provisional 25-minute estimate" tone="amber" />}
              </View>
            ))}
            {!plan.items.length && <Text style={styles.muted}>No available task fits this budget. Check dependencies, blockers or estimates.</Text>}
            {plan.assumptions.map(assumption => <Text key={assumption} style={styles.small}>{assumption}</Text>)}
          </>}
        </Section>
      )}
      {selected.length > 0 && (
        <Section title={`${selected.length} selected`}>
          <View style={styles.wrap}>
            <Action label="Move to ready" onPress={() => batch('ready')} disabled={readOnly} />
            <Action label="Mark blocked" onPress={() => batch('blocked')} disabled={readOnly} />
            <Action label="Mark done" onPress={() => batch('done')} disabled={readOnly} />
            <Action label="Clear selection" onPress={() => setSelected([])} />
          </View>
        </Section>
      )}
      {!tasks.length && <Empty icon="checkbox-outline" title="No matching tasks" message="Create a task or change your filters. Start with a small outcome you can verify." />}
      <Pagination page={page} setPage={setPage} label="tasks" />
      {page.items.map(task => {
        const blocked = unmetDependencies(task, projectTasks);
        const progress = taskProgress(task);
        return (
          <Section key={task.id} title={task.title} action={
            <TouchableOpacity
              accessibilityRole="checkbox"
              accessibilityLabel={`Select ${task.title}`}
              accessibilityState={{ checked: selected.includes(task.id) }}
              onPress={() => setSelected(selected.includes(task.id) ? selected.filter(id => id !== task.id) : [...selected, task.id])}
            ><Ionicons name={selected.includes(task.id) ? 'checkbox' : 'square-outline'} size={24} color={palette.accent} /></TouchableOpacity>
          }>
            <View style={styles.wrap}>
              <Badge text={task.status} tone={task.status === 'done' ? 'green' : task.status === 'blocked' ? 'amber' : 'accent'} />
              <Badge text={task.priority} tone={task.priority === 'urgent' ? 'red' : 'muted'} />
              <Badge text={task.estimateMinutes ? formatMinutes(task.estimateMinutes) : 'Unestimated'} />
              {task.dueDate && <Badge text={`Due ${task.dueDate}`} />}
              {task.tags.map(tag => <Badge key={tag} text={`#${tag}`} />)}
            </View>
            {!!task.description && <Text selectable numberOfLines={5} style={styles.text}>{task.description}</Text>}
            {!!blocked.length && <Text style={styles.error}>Waiting for: {blocked.map(item => item.title).join(', ')}</Text>}
            {!!task.checklist.length && <>
              <Text style={styles.small}>Checklist {progress}% complete</Text>
              {task.checklist.map(item => <TouchableOpacity
                key={item.id}
                style={styles.row}
                disabled={readOnly}
                accessibilityRole="checkbox"
                accessibilityLabel={item.text}
                accessibilityState={{ checked: item.done, disabled: readOnly }}
                onPress={() => store.dispatch({ type: 'task.check', id: task.id, revision: task.revision, itemId: item.id, done: !item.done })}
              >
                <Ionicons name={item.done ? 'checkbox' : 'square-outline'} size={21} color={palette.accent} />
                <Text style={[styles.text, styles.flex]}>{item.text}</Text>
              </TouchableOpacity>)}
            </>}
            <View style={styles.wrap}>
              <Action label="Edit task" icon="create-outline" onPress={() => setEditor(task)} disabled={readOnly} compact />
              {!isTerminal(task) && task.status !== 'doing' && <Action label="Start task" icon="play-outline" onPress={() => store.dispatch({ type: 'task.status', id: task.id, revision: task.revision, status: 'doing' })} disabled={readOnly || !canStart(task, projectTasks)} compact />}
              {!isTerminal(task) && <Action label="Complete task" icon="checkmark" onPress={() => store.dispatch({ type: 'task.status', id: task.id, revision: task.revision, status: 'done' })} disabled={readOnly} compact />}
              {isTerminal(task) && <Action label="Reopen task" icon="refresh-outline" onPress={() => store.dispatch({ type: 'task.status', id: task.id, revision: task.revision, status: 'ready' })} disabled={readOnly} compact />}
              <Action label="Ask Jeeves" icon="sparkles-outline" onPress={() => props.discuss(task)} compact />
              {sort === 'manual' && <>
                <Action label="Move earlier" icon="arrow-up" onPress={() => move(task, -1)} disabled={readOnly} compact />
                <Action label="Move later" icon="arrow-down" onPress={() => move(task, 1)} disabled={readOnly} compact />
              </>}
              <Action label="Delete task" icon="trash-outline" danger onPress={() => remove(task)} disabled={readOnly} compact />
            </View>
          </Section>
        );
      })}
      {editor && <TaskEditor {...props} task={editor === 'new' ? undefined : editor} close={() => setEditor(null)} />}
    </View>
  );
}
