import type { Priority, Task, Workbench } from './types';
import { assertInteger, WorkbenchError } from './validation';
import { localDayKey } from './review';

export const PRIORITY_WEIGHT: Record<Priority, number> = {
  low: 1,
  normal: 2,
  high: 3,
  urgent: 4,
};

export function isTerminal(task: Task): boolean {
  return task.status === 'done' || task.status === 'cancelled';
}

export function dependencyMap(tasks: Task[]): Map<string, Task> {
  return new Map(tasks.map(task => [task.id, task]));
}

export function unmetDependencies(task: Task, tasks: Task[]): Task[] {
  const byId = dependencyMap(tasks);
  return task.dependencies.map(id => byId.get(id)).filter((item): item is Task => !!item && item.status !== 'done');
}

export function missingDependencies(task: Task, tasks: Task[]): string[] {
  const ids = new Set(tasks.map(item => item.id));
  return task.dependencies.filter(id => !ids.has(id));
}

export function canStart(task: Task, tasks: Task[]): boolean {
  return !isTerminal(task) && task.status !== 'blocked'
    && unmetDependencies(task, tasks).length === 0
    && missingDependencies(task, tasks).length === 0;
}

/** Iterative DFS avoids recursion overflow on large imported graphs. */
export function dependencyCycle(tasks: Task[]): string[] | null {
  const byId = dependencyMap(tasks);
  const done = new Set<string>();
  for (const root of tasks) {
    if (done.has(root.id)) continue;
    const path: string[] = [];
    const active = new Map<string, number>();
    const stack: { id: string; index: number }[] = [{ id: root.id, index: 0 }];
    while (stack.length) {
      const frame = stack[stack.length - 1];
      if (!active.has(frame.id)) {
        active.set(frame.id, path.length);
        path.push(frame.id);
      }
      const edges = byId.get(frame.id)?.dependencies || [];
      if (frame.index >= edges.length) {
        done.add(frame.id);
        active.delete(frame.id);
        path.pop();
        stack.pop();
        continue;
      }
      const child = edges[frame.index++];
      if (active.has(child)) return [...path.slice(active.get(child)), child];
      if (!done.has(child) && byId.has(child)) stack.push({ id: child, index: 0 });
    }
  }
  return null;
}

export function validateDependencies(task: Task, tasks: Task[]): void {
  const byId = dependencyMap(tasks);
  for (const id of task.dependencies) {
    const dependency = byId.get(id);
    if (!dependency) throw new WorkbenchError('A dependency no longer exists.', 'missing');
    if (id === task.id) throw new WorkbenchError('A task cannot depend on itself.');
    if (dependency.projectId !== task.projectId) throw new WorkbenchError('Dependencies must belong to the same project.');
  }
  const candidate = tasks.some(item => item.id === task.id)
    ? tasks.map(item => item.id === task.id ? task : item)
    : [...tasks, task];
  if (dependencyCycle(candidate)) throw new WorkbenchError('This dependency would create a cycle.');
}

export function dependants(taskId: string, tasks: Task[], transitive = false): Task[] {
  const found = new Set<string>();
  const queue = [taskId];
  while (queue.length) {
    const id = queue.shift()!;
    for (const task of tasks) {
      if (task.id === taskId || found.has(task.id) || !task.dependencies.includes(id)) continue;
      found.add(task.id);
      if (transitive) queue.push(task.id);
    }
  }
  return tasks.filter(task => found.has(task.id));
}

export function topologicalTasks(tasks: Task[]): Task[] {
  const byId = dependencyMap(tasks);
  const degrees = new Map(tasks.map(task => [task.id, task.dependencies.filter(id => byId.has(id)).length]));
  const children = new Map<string, string[]>();
  for (const task of tasks) {
    for (const parent of task.dependencies) {
      children.set(parent, [...(children.get(parent) || []), task.id]);
    }
  }
  const compare = (a: Task, b: Task) => PRIORITY_WEIGHT[b.priority] - PRIORITY_WEIGHT[a.priority]
    || a.order - b.order || a.id.localeCompare(b.id);
  const ready = tasks.filter(task => degrees.get(task.id) === 0).sort(compare);
  const ordered: Task[] = [];
  while (ready.length) {
    const task = ready.shift()!;
    ordered.push(task);
    for (const child of children.get(task.id) || []) {
      const remaining = degrees.get(child)! - 1;
      degrees.set(child, remaining);
      if (remaining === 0) {
        ready.push(byId.get(child)!);
        ready.sort(compare);
      }
    }
  }
  if (ordered.length !== tasks.length) throw new WorkbenchError('The task graph contains a cycle.');
  return ordered;
}

export interface CriticalPath {
  taskIds: string[];
  estimatedMinutes: number;
  unestimatedTasks: number;
  earliestFinish: Record<string, number>;
}

export function criticalPath(tasks: Task[]): CriticalPath {
  const ordered = topologicalTasks(tasks);
  const finish: Record<string, number> = Object.create(null);
  const predecessor = new Map<string, string | null>();
  let longest = 0;
  let last: string | null = null;
  for (const task of ordered) {
    let parent: string | null = null;
    let start = 0;
    for (const id of task.dependencies) {
      if ((finish[id] || 0) > start) {
        start = finish[id];
        parent = id;
      }
    }
    finish[task.id] = start + (isTerminal(task) ? 0 : task.estimateMinutes);
    predecessor.set(task.id, parent);
    if (finish[task.id] > longest) {
      longest = finish[task.id];
      last = task.id;
    }
  }
  const path: string[] = [];
  while (last) {
    path.unshift(last);
    last = predecessor.get(last) || null;
  }
  return {
    taskIds: path,
    estimatedMinutes: longest,
    unestimatedTasks: tasks.filter(task => !isTerminal(task) && task.estimateMinutes === 0).length,
    earliestFinish: finish,
  };
}

export interface PlanItem {
  task: Task;
  reason: string;
  startMinute: number;
  endMinute: number;
  estimated: boolean;
}

export interface SessionPlan {
  items: PlanItem[];
  budgetMinutes: number;
  plannedMinutes: number;
  remainingMinutes: number;
  excluded: { taskId: string; reason: string }[];
  assumptions: string[];
}

export function planSession(tasks: Task[], budgetMinutes: number, now: number): SessionPlan {
  assertInteger(budgetMinutes, 'Session budget', 5, 480);
  const today = localDayKey(now);
  const active = tasks.filter(task => !isTerminal(task));
  const completed = new Set(tasks.filter(task => task.status === 'done').map(task => task.id));
  const scheduled = new Set<string>();
  const excluded = new Map<string, string>();
  const items: PlanItem[] = [];
  let used = 0;
  const rank = (task: Task) => {
    let value = PRIORITY_WEIGHT[task.priority] * 10;
    if (task.status === 'doing') value += 80;
    if (task.dueDate && task.dueDate < today) value += 60;
    else if (task.dueDate === today) value += 35;
    value += Math.min(20, dependants(task.id, tasks).filter(item => !isTerminal(item)).length * 5);
    return value;
  };
  const sorted = [...active].sort((a, b) => rank(b) - rank(a) || a.order - b.order || a.id.localeCompare(b.id));
  let changed = true;
  while (changed) {
    changed = false;
    for (const task of sorted) {
      if (scheduled.has(task.id)) continue;
      if (task.status === 'blocked') {
        excluded.set(task.id, 'Manually blocked');
        continue;
      }
      if (!task.dependencies.every(id => completed.has(id) || scheduled.has(id))) {
        excluded.set(task.id, 'Depends on unfinished work');
        continue;
      }
      const estimate = task.estimateMinutes || 25;
      if (used + estimate > budgetMinutes) {
        excluded.set(task.id, 'Does not fit the remaining time');
        continue;
      }
      const reason = task.status === 'doing' ? 'Continue work already in progress'
        : task.dueDate && task.dueDate < today ? 'Overdue'
          : task.dueDate === today ? 'Due today'
            : dependants(task.id, tasks).length ? 'Unlocks dependent tasks'
              : `${task.priority} priority`;
      items.push({ task, reason, startMinute: used, endMinute: used + estimate, estimated: task.estimateMinutes > 0 });
      used += estimate;
      scheduled.add(task.id);
      excluded.delete(task.id);
      changed = true;
    }
  }
  return {
    items,
    budgetMinutes,
    plannedMinutes: used,
    remainingMinutes: budgetMinutes - used,
    excluded: [...excluded].map(([taskId, reason]) => ({ taskId, reason })),
    assumptions: [
      'This is a deterministic suggestion, not a prediction of completion.',
      'Tasks without estimates are provisionally assigned 25 minutes.',
      'A dependency may appear earlier in the same plan; verify it is complete before starting its dependant.',
    ],
  };
}

export interface ProjectRisk {
  severity: 'info' | 'warning';
  code: string;
  message: string;
  taskIds: string[];
}

export function projectRisks(state: Workbench, projectId: string, now: number): ProjectRisk[] {
  const project = state.projects.find(item => item.id === projectId);
  if (!project) return [];
  const tasks = state.tasks.filter(item => item.projectId === projectId && !isTerminal(item));
  const today = localDayKey(now);
  const risks: ProjectRisk[] = [];
  const overdue = tasks.filter(task => task.dueDate && task.dueDate < today);
  const blocked = tasks.filter(task => task.status === 'blocked');
  const unestimated = tasks.filter(task => !task.estimateMinutes);
  const inProgress = tasks.filter(task => task.status === 'doing');
  if (overdue.length) risks.push({ severity: 'warning', code: 'overdue', message: `${overdue.length} task(s) are past their due date.`, taskIds: overdue.map(task => task.id) });
  if (blocked.length) risks.push({ severity: 'warning', code: 'blocked', message: `${blocked.length} task(s) need an unblock decision.`, taskIds: blocked.map(task => task.id) });
  if (unestimated.length) risks.push({ severity: 'info', code: 'unestimated', message: `${unestimated.length} task(s) have no estimate.`, taskIds: unestimated.map(task => task.id) });
  if (inProgress.length > 3) risks.push({ severity: 'warning', code: 'wip', message: 'More than three tasks are in progress. Consider finishing one before starting another.', taskIds: inProgress.map(task => task.id) });
  if (!project.goal.trim()) risks.push({ severity: 'info', code: 'goal', message: 'Define a concrete project goal to guide the next planning session.', taskIds: [] });
  if (project.targetDate && project.targetDate < today && project.status !== 'completed') risks.push({ severity: 'warning', code: 'target', message: 'The project target date has passed.', taskIds: [] });
  if (tasks.length && project.weeklyMinutes === 0) risks.push({ severity: 'info', code: 'capacity', message: 'Set a weekly time budget to compare scope with available time.', taskIds: [] });
  return risks;
}
