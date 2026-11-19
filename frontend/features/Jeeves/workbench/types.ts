/** Portable workbench records. All dates are UTC epoch milliseconds except due-date strings. */
export const WORKBENCH_VERSION = 1;
export const WORKBENCH_KEY = '@tutolage/jeeves-workbench:v1';
export const RECOVERY_KEY = '@tutolage/jeeves-workbench:recovery:v1';
export const HANDOFF_KEY = '@tutolage/jeeves-workbench:handoff:v1';

export const LIMITS = {
  projects: 40,
  tasks: 1500,
  notes: 800,
  cards: 2000,
  prompts: 200,
  sources: 500,
  sessions: 500,
  events: 1500,
  reviews: 5000,
  title: 160,
  summary: 2000,
  body: 30000,
  context: 12000,
  answer: 8000,
  tags: 12,
  tag: 40,
  checklist: 50,
  dependencies: 40,
  links: 40,
  backupBytes: 12 * 1024 * 1024,
  stateCharacters: 5 * 1024 * 1024,
} as const;

export type ProjectStatus = 'active' | 'paused' | 'completed' | 'archived';
export type TaskStatus = 'inbox' | 'ready' | 'doing' | 'blocked' | 'done' | 'cancelled';
export type Priority = 'low' | 'normal' | 'high' | 'urgent';
export type NoteKind = 'note' | 'decision' | 'experiment' | 'reference' | 'retrospective';
export type CardState = 'new' | 'learning' | 'review' | 'relearning' | 'suspended';
export type ReviewGrade = 'again' | 'hard' | 'good' | 'easy';
export type SourceKind = 'url' | 'book' | 'file' | 'conversation' | 'observation';
export type Confidence = 'unverified' | 'tentative' | 'supported' | 'contradicted';
export type RecordKind = 'project' | 'task' | 'note' | 'card' | 'prompt' | 'source' | 'session';
export type EventKind = 'created' | 'updated' | 'status' | 'deleted' | 'restored' | 'reviewed' | 'imported' | 'focused';

export interface Entity {
  id: string;
  createdAt: number;
  updatedAt: number;
  revision: number;
}

export interface Project extends Entity {
  title: string;
  summary: string;
  goal: string;
  context: string;
  engine: string;
  experience: 'beginner' | 'intermediate' | 'advanced';
  status: ProjectStatus;
  color: string;
  tags: string[];
  pinned: boolean;
  weeklyMinutes: number;
  targetDate: string | null;
}

export interface ChecklistItem {
  id: string;
  text: string;
  done: boolean;
}

export interface Task extends Entity {
  projectId: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: Priority;
  estimateMinutes: number;
  dueDate: string | null;
  completedAt: number | null;
  dependencies: string[];
  checklist: ChecklistItem[];
  tags: string[];
  noteIds: string[];
  order: number;
}

export interface Note extends Entity {
  projectId: string;
  title: string;
  body: string;
  kind: NoteKind;
  tags: string[];
  sourceIds: string[];
  relatedNoteIds: string[];
  confidence: Confidence;
  pinned: boolean;
  archived: boolean;
}

export interface Source extends Entity {
  projectId: string;
  title: string;
  kind: SourceKind;
  locator: string;
  excerpt: string;
  author: string;
  accessedAt: number;
  tags: string[];
}

export interface CardSchedule {
  state: CardState;
  dueAt: number;
  intervalDays: number;
  ease: number;
  repetitions: number;
  lapses: number;
  learningStep: number;
  lastReviewedAt: number | null;
  suspendedFrom: Exclude<CardState, 'suspended'> | null;
}

export interface StudyCard extends Entity {
  projectId: string;
  question: string;
  answer: string;
  hint: string;
  explanation: string;
  tags: string[];
  noteId: string | null;
  sourceIds: string[];
  schedule: CardSchedule;
}

export interface Review extends Entity {
  projectId: string;
  cardId: string;
  grade: ReviewGrade;
  durationMs: number;
  reviewedAt: number;
  previous: CardSchedule;
  next: CardSchedule;
  sessionId: string | null;
}

export interface PromptVariable {
  key: string;
  label: string;
  description: string;
  defaultValue: string;
  required: boolean;
}

export interface SavedPrompt extends Entity {
  projectId: string | null;
  title: string;
  description: string;
  template: string;
  variables: PromptVariable[];
  tags: string[];
  favorite: boolean;
  useCount: number;
  lastUsedAt: number | null;
}

export interface FocusSession extends Entity {
  projectId: string;
  taskId: string | null;
  startedAt: number;
  endedAt: number | null;
  plannedMinutes: number;
  pausedAt: number | null;
  pausedMilliseconds: number;
  outcome: 'running' | 'completed' | 'abandoned';
  reflection: string;
}

export interface ActivityEvent {
  id: string;
  at: number;
  projectId: string | null;
  entityKind: RecordKind;
  entityId: string;
  action: EventKind;
  summary: string;
}

export interface Preferences {
  dailyNewCards: number;
  dailyReviewCards: number;
  focusMinutes: number;
  weekStartsOn: 'monday' | 'sunday';
  includeSourcesInContext: boolean;
  includeCompletedTasks: boolean;
  confirmBeforeDelete: boolean;
}

export interface Workbench {
  version: 1;
  id: string;
  revision: number;
  createdAt: number;
  updatedAt: number;
  activeProjectId: string | null;
  projects: Project[];
  tasks: Task[];
  notes: Note[];
  sources: Source[];
  cards: StudyCard[];
  reviews: Review[];
  prompts: SavedPrompt[];
  sessions: FocusSession[];
  events: ActivityEvent[];
  preferences: Preferences;
}

export interface MutationContext {
  now: number;
  id: () => string;
}

export interface TaskFilter {
  query?: string;
  statuses?: TaskStatus[];
  priorities?: Priority[];
  tag?: string;
  due?: 'overdue' | 'today' | 'week' | 'none';
  sort?: 'manual' | 'priority' | 'due' | 'updated' | 'estimate';
}

export interface NoteFilter {
  query?: string;
  kind?: NoteKind;
  tag?: string;
  archived?: boolean;
  confidence?: Confidence;
}

export interface Dashboard {
  project: Project;
  taskCount: number;
  completedTasks: number;
  overdueTasks: number;
  blockedTasks: number;
  estimatedMinutes: number;
  focusMinutes: number;
  notes: number;
  sources: number;
  cards: number;
  dueCards: number;
  reviewedToday: number;
  completionPercent: number;
  nextTasks: Task[];
  recentNotes: Note[];
  recentEvents: ActivityEvent[];
}

export interface ValidationIssue {
  path: string;
  message: string;
}

export type Result<T> =
  | { ok: true; value: T }
  | { ok: false; issues: ValidationIssue[] };

export interface ContextSelection {
  projectId: string;
  noteIds: string[];
  taskIds: string[];
  sourceIds: string[];
  includeProject: boolean;
  maxCharacters: number;
}

export interface ContextSection {
  id: string;
  label: string;
  kind: 'project' | 'task' | 'note' | 'source';
  text: string;
  truncated: boolean;
}

export interface ContextBundle {
  text: string;
  sections: ContextSection[];
  omitted: string[];
  characters: number;
  budget: number;
}

export interface ChatHandoff {
  version: 1;
  id: string;
  createdAt: number;
  projectId: string;
  projectTitle: string;
  draft: string;
  context: string;
  sourceLabels: string[];
}

export interface BackupEnvelope {
  format: 'jeeves-workbench';
  version: 1;
  exportedAt: number;
  recordCount: number;
  workspace: Workbench;
}

export interface ImportPreview {
  imported: Workbench;
  counts: Record<RecordKind | 'review', number>;
  warnings: string[];
}

export type WorkbenchTab =
  | 'overview'
  | 'weekly'
  | 'tasks'
  | 'notes'
  | 'sources'
  | 'study'
  | 'prompts'
  | 'focus'
  | 'search'
  | 'context'
  | 'settings';

export const PROJECT_COLORS = [
  '#a78bfa',
  '#60a5fa',
  '#fbbf24',
  '#f472b6',
  '#86efac',
  '#fb923c',
] as const;

export const TASK_STATUSES: TaskStatus[] = [
  'inbox',
  'ready',
  'doing',
  'blocked',
  'done',
  'cancelled',
];

export const PRIORITIES: Priority[] = ['low', 'normal', 'high', 'urgent'];
export const NOTE_KINDS: NoteKind[] = ['note', 'decision', 'experiment', 'reference', 'retrospective'];
export const REVIEW_GRADES: ReviewGrade[] = ['again', 'hard', 'good', 'easy'];
export const CONFIDENCES: Confidence[] = ['unverified', 'tentative', 'supported', 'contradicted'];
