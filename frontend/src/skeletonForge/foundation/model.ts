/**
 * Studio shell state: first-run, account gate, projects, and where Back goes.
 * Pure — screens and persistence sit on top of this reducer.
 */
import { questionnaireReducer, type QuestionnaireAction, type QuestionnaireState } from '../questionnaire';
import { summarizeRun } from '../run';
import type { RunPayload } from '../types';

export const SCREENS = ['boot', 'onboarding', 'sign-in', 'dashboard', 'brief', 'build', 'account', 'settings'] as const;
export type Screen = typeof SCREENS[number];

export type BuildPhase = 'idle' | 'running' | 'done' | 'error';
export type MotionPref = 'system' | 'on' | 'off';
export type TextSizePref = 'system' | 'small' | 'default' | 'large' | 'xlarge';

export interface StudioPrefs {
  reducedMotion: MotionPref;
  textSize: TextSizePref;
}

export const DEFAULT_PREFS: StudioPrefs = { reducedMotion: 'system', textSize: 'system' };

export const TEXT_SCALE: Record<Exclude<TextSizePref, 'system'>, number> = {
  small: 0.9,
  default: 1,
  large: 1.2,
  xlarge: 1.4,
};

export interface RunSnapshot {
  phase: 'done' | 'error';
  error: string | null;
  startedAt: number | null;
  finishedAt: number | null;
  succeeded: boolean;
  payload: RunPayload | null;
}

export interface StudioProject {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  questionnaire: QuestionnaireState;
  lastRun: RunSnapshot | null;
}

export interface AuthView {
  phase: 'loading' | 'ready' | 'unavailable';
  authenticated: boolean;
  enforced: boolean;
  role: string;
  email: string | null;
  error: string | null;
}

export interface AuthObservation {
  authenticated: boolean;
  enforced: boolean;
  role: string;
  user: { email?: string } | null;
  observed?: boolean;
  error?: string;
}

export interface FoundationState {
  screen: Screen;
  hydrated: boolean;
  reloading: boolean;
  onboarded: boolean;
  replaying: boolean;
  /** Set when first-run should open a new brief once the gate allows it. */
  intent: 'create' | null;
  auth: AuthView;
  projects: StudioProject[];
  projectsCorrupt: boolean;
  /** Do not write over a save we could not read. */
  holdSaves: boolean;
  hydrateError: string | null;
  persistError: string | null;
  activeId: string | null;
  prefs: StudioPrefs;
}

export interface LoadResult {
  onboarded: boolean;
  projects: StudioProject[];
  prefs: StudioPrefs;
  projectsCorrupt: boolean;
  holdSaves: boolean;
  error: string | null;
}

export type FoundationAction =
  | { type: 'replace'; state: FoundationState }
  | ({ type: 'hydrated' } & LoadResult)
  | { type: 'authLoading' }
  | { type: 'auth'; view: AuthView }
  | { type: 'retryLoad' }
  | { type: 'startFresh' }
  | { type: 'skipOnboarding' }
  | { type: 'finishOnboarding'; id: string; at: string }
  | { type: 'replayOnboarding' }
  | { type: 'fulfillIntent'; id: string; at: string }
  | { type: 'createProject'; id: string; at: string }
  | { type: 'openProject'; id: string; focus?: 'brief' | 'build' }
  | { type: 'questionnaire'; action: QuestionnaireAction; at: string }
  | { type: 'openBuild' }
  | { type: 'openBrief' }
  | { type: 'openDashboard' }
  | { type: 'openAccount' }
  | { type: 'openSettings' }
  | { type: 'openSignIn' }
  | { type: 'back' }
  | { type: 'signedOut' }
  | { type: 'setPrefs'; prefs: StudioPrefs }
  | { type: 'recordRun'; projectId: string; snapshot: RunSnapshot }
  | { type: 'persistError'; error: string | null };

const LOADING_AUTH: AuthView = {
  phase: 'loading', authenticated: false, enforced: true, role: 'anonymous', email: null, error: null,
};

export function initialFoundationState(): FoundationState {
  return {
    screen: 'boot',
    hydrated: false,
    reloading: false,
    onboarded: false,
    replaying: false,
    intent: null,
    auth: LOADING_AUTH,
    projects: [],
    projectsCorrupt: false,
    holdSaves: false,
    hydrateError: null,
    persistError: null,
    activeId: null,
    prefs: DEFAULT_PREFS,
  };
}

export function freshQuestionnaire(): QuestionnaireState {
  return {
    step: 'vision',
    vision: '',
    brief: {},
    beats: {},
    options: { archetype: 'auto', target: 'godot', era: null, generation: null },
  };
}

export function projectTitle(vision: string): string {
  const line = vision.trim().split('\n')[0]?.trim() ?? '';
  if (!line) return 'Untitled project';
  return line.length > 64 ? `${line.slice(0, 63)}…` : line;
}

export function createId(now: number, n: number): string {
  return `p_${Math.max(0, Math.floor(now)).toString(36)}_${Math.max(0, Math.floor(n)).toString(36)}`;
}

export function canEnter(state: FoundationState): boolean {
  if (!state.hydrated || !state.onboarded) return false;
  if (state.auth.phase === 'loading') return false;
  if (state.auth.phase === 'unavailable') return !state.auth.enforced;
  return state.auth.authenticated || !state.auth.enforced;
}

export function viewFromMe(me: AuthObservation): AuthView {
  if (me.observed === false) {
    return {
      phase: 'unavailable',
      authenticated: false,
      enforced: me.enforced,
      role: 'anonymous',
      email: null,
      error: me.error || 'The account service did not answer.',
    };
  }
  const email = me.user && typeof me.user.email === 'string' && me.user.email.trim() ? me.user.email.trim() : null;
  return {
    phase: 'ready',
    authenticated: Boolean(me.authenticated),
    enforced: Boolean(me.enforced),
    role: me.authenticated ? (me.role || 'anonymous') : 'anonymous',
    email: me.authenticated ? email : null,
    error: null,
  };
}

export function credentialError(email: string, password: string): string | null {
  const value = email.trim();
  if (!value || !value.includes('@') || value.startsWith('@') || value.endsWith('@') || value.includes(' ')) {
    return 'Enter the email address for the account.';
  }
  if (!password) return 'Enter the password.';
  return null;
}

function place(state: FoundationState): FoundationState {
  if (!state.hydrated || state.auth.phase === 'loading') return { ...state, screen: 'boot' };
  if (!state.onboarded) return { ...state, screen: 'onboarding' };
  if (!canEnter(state)) return { ...state, screen: 'sign-in' };
  if (state.screen === 'boot' || state.screen === 'onboarding' || state.screen === 'sign-in') {
    return { ...state, screen: 'dashboard' };
  }
  return state;
}

function go(state: FoundationState, screen: Screen): FoundationState {
  if (screen !== 'account' && screen !== 'sign-in' && screen !== 'onboarding' && !canEnter(state)) {
    return { ...state, screen: 'sign-in' };
  }
  return { ...state, screen };
}

function replaceProject(state: FoundationState, project: StudioProject): FoundationState {
  return { ...state, projects: state.projects.map((item) => (item.id === project.id ? project : item)) };
}

function openNewProject(state: FoundationState, id: string, at: string): FoundationState {
  const project: StudioProject = {
    id,
    title: 'Untitled project',
    createdAt: at,
    updatedAt: at,
    questionnaire: freshQuestionnaire(),
    lastRun: null,
  };
  return { ...state, intent: null, projects: [project, ...state.projects], activeId: id, screen: 'brief' };
}

export function foundationReducer(state: FoundationState, action: FoundationAction): FoundationState {
  switch (action.type) {
    case 'replace':
      return action.state;
    case 'hydrated':
      return place({
        ...state,
        hydrated: true,
        reloading: false,
        onboarded: action.onboarded,
        projects: action.projects,
        prefs: action.prefs,
        projectsCorrupt: action.projectsCorrupt,
        holdSaves: action.holdSaves,
        hydrateError: action.error,
      });
    case 'authLoading':
      return place({ ...state, auth: { ...state.auth, phase: 'loading', error: null } });
    case 'auth': {
      const next = place({ ...state, auth: action.view });
      return next;
    }
    case 'retryLoad':
      return { ...state, reloading: true };
    case 'startFresh':
      return {
        ...state,
        projects: [],
        projectsCorrupt: false,
        holdSaves: false,
        hydrateError: null,
        activeId: null,
      };
    case 'skipOnboarding': {
      const next = { ...state, onboarded: true, replaying: false, intent: null };
      return canEnter(next) ? { ...next, screen: 'dashboard' } : { ...next, screen: 'sign-in' };
    }
    case 'finishOnboarding': {
      const next = { ...state, onboarded: true, replaying: false };
      if (state.replaying) {
        return canEnter(next) ? { ...next, intent: null, screen: 'dashboard' } : { ...next, intent: null, screen: 'sign-in' };
      }
      const pending = { ...next, intent: 'create' as const };
      if (!canEnter(pending)) return { ...pending, screen: 'sign-in' };
      if (pending.holdSaves) return { ...pending, screen: 'dashboard' };
      return openNewProject(pending, action.id, action.at);
    }
    case 'replayOnboarding':
      return { ...state, replaying: true, screen: 'onboarding' };
    case 'fulfillIntent':
      if (state.intent !== 'create' || !canEnter(state) || state.holdSaves) return state;
      return openNewProject(state, action.id, action.at);
    case 'createProject':
      if (!canEnter(state) || state.holdSaves) return state;
      return openNewProject(state, action.id, action.at);
    case 'openProject': {
      if (!state.projects.some((project) => project.id === action.id)) return state;
      return go({ ...state, activeId: action.id }, action.focus === 'build' ? 'build' : 'brief');
    }
    case 'questionnaire': {
      const current = state.projects.find((project) => project.id === state.activeId);
      if (!current) return state;
      const questionnaire = questionnaireReducer(current.questionnaire, action.action);
      return replaceProject(state, {
        ...current,
        questionnaire,
        title: projectTitle(questionnaire.vision),
        updatedAt: action.at,
      });
    }
    case 'openBuild':
      return state.activeId ? go(state, 'build') : state;
    case 'openBrief':
      return state.activeId ? go(state, 'brief') : state;
    case 'openDashboard':
      return go(state, 'dashboard');
    case 'openAccount':
      return { ...state, screen: 'account' };
    case 'openSettings':
      return go(state, 'settings');
    case 'openSignIn':
      return { ...state, screen: 'sign-in' };
    case 'back':
      if (state.screen === 'build') return state.activeId ? { ...state, screen: 'brief' } : { ...state, screen: 'dashboard' };
      if (state.screen === 'brief' || state.screen === 'settings' || state.screen === 'account') return go(state, 'dashboard');
      if (state.screen === 'sign-in' && canEnter(state)) return { ...state, screen: 'dashboard' };
      return state;
    case 'signedOut': {
      const auth: AuthView = { ...state.auth, phase: 'ready', authenticated: false, role: 'anonymous', email: null, error: null };
      const next = { ...state, auth };
      return auth.enforced ? { ...next, screen: 'sign-in' } : { ...next, screen: 'account' };
    }
    case 'setPrefs':
      return { ...state, prefs: sanitizePrefs(action.prefs) };
    case 'recordRun':
      return applyRecordRun(state, action.projectId, action.snapshot);
    case 'persistError':
      return { ...state, persistError: action.error };
    default:
      return state;
  }
}

export function applyRecordRun(state: FoundationState, projectId: string, snapshot: RunSnapshot): FoundationState {
  const current = state.projects.find((project) => project.id === projectId);
  if (!current) return state;
  const updatedAt = snapshot.finishedAt != null ? new Date(snapshot.finishedAt).toISOString() : current.updatedAt;
  return replaceProject(state, { ...current, lastRun: snapshot, updatedAt });
}

export interface PersistSnapshot {
  onboarded: boolean;
  projects: StudioProject[];
  prefs: StudioPrefs;
  projectsCorrupt: boolean;
  holdSaves: boolean;
}

export function persistSnapshot(state: FoundationState): PersistSnapshot {
  return {
    onboarded: state.onboarded,
    projects: state.projects,
    prefs: state.prefs,
    projectsCorrupt: state.projectsCorrupt,
    holdSaves: state.holdSaves,
  };
}

export function orderedProjects(projects: readonly StudioProject[]): StudioProject[] {
  return [...projects].sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : a.updatedAt > b.updatedAt ? -1 : a.id < b.id ? -1 : 1));
}

export function projectStatus(project: StudioProject, liveOwner: string | null, livePhase: BuildPhase): string {
  if (liveOwner === project.id && livePhase === 'running') return 'Forging';
  if (!project.lastRun) return 'Brief in progress';
  if (project.lastRun.phase === 'error') return 'Needs attention';
  if (project.lastRun.succeeded) return 'Built';
  return 'Finished with failures';
}

export function openTarget(project: StudioProject, liveOwner: string | null, livePhase: BuildPhase): 'brief' | 'build' {
  if (liveOwner === project.id && livePhase === 'running') return 'build';
  if (project.lastRun) return 'build';
  return 'brief';
}

export interface StepAction {
  id: 'retry' | 'edit-brief' | 'wait' | 'projects' | 'cockpit';
  label: string;
  detail: string;
}

/** The next thing to do on the build screen, besides the controls ForgeRunPanel already draws. */
export function buildGuidance(phase: BuildPhase, error: string | null, payload: RunPayload | null): StepAction {
  if (phase === 'running') {
    return {
      id: 'projects',
      label: 'All projects',
      detail: 'The forge runs every stage in this one request. You can leave this screen; cancel here if you want it to stop.',
    };
  }
  if (phase === 'idle') {
    return {
      id: 'edit-brief',
      label: 'Finish the brief',
      detail: 'Nothing has been built yet. Complete the questionnaire and forge it.',
    };
  }
  if (phase === 'error') {
    return {
      id: 'edit-brief',
      label: 'Change the brief',
      detail: error?.trim() || 'The build did not finish. Adjust the brief, or run it again from the status above.',
    };
  }
  const summary = summarizeRun(payload);
  if (!summary.succeeded) {
    const stage = summary.failedStage;
    const detail = summary.advice
      || stage?.error
      || (stage ? `${stage.label} failed.` : 'The forge finished with failures.');
    return { id: 'edit-brief', label: 'Change the brief and forge again', detail };
  }
  const era = summary.era ? `Built in the ${summary.era} era.` : 'The build finished.';
  return { id: 'projects', label: 'Back to projects', detail: era };
}

export function exits(state: FoundationState): string[] {
  switch (state.screen) {
    case 'boot':
      return ['setup'];
    case 'onboarding':
      return ['skip', state.replaying ? 'done' : 'create'];
    case 'sign-in':
      return state.auth.phase === 'unavailable'
        ? ['retry', 'setup', ...(state.auth.enforced ? [] : ['guest'])]
        : ['submit', 'google', 'setup', ...(state.auth.enforced ? [] : ['guest'])];
    case 'dashboard':
      return state.holdSaves
        ? ['retry', 'start-fresh', 'settings', 'account']
        : ['create', 'settings', 'account', ...(state.projects.length ? ['open'] : [])];
    case 'brief':
      return ['projects', 'build', 'cockpit'];
    case 'build':
      return ['brief', 'projects', 'next'];
    case 'account':
      return ['back', state.auth.authenticated ? 'sign-out' : 'sign-in'];
    case 'settings':
      return ['back', 'motion', 'text', 'replay'];
    default:
      return [];
  }
}

const MOTION: readonly MotionPref[] = ['system', 'on', 'off'];
const TEXT: readonly TextSizePref[] = ['system', 'small', 'default', 'large', 'xlarge'];

export function sanitizePrefs(raw: unknown): StudioPrefs {
  const obj = raw && typeof raw === 'object' ? raw as Record<string, unknown> : {};
  const reducedMotion = MOTION.includes(obj.reducedMotion as MotionPref) ? obj.reducedMotion as MotionPref : DEFAULT_PREFS.reducedMotion;
  const textSize = TEXT.includes(obj.textSize as TextSizePref) ? obj.textSize as TextSizePref : DEFAULT_PREFS.textSize;
  return { reducedMotion, textSize };
}

function stringMap(raw: unknown): Record<string, string> | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const out: Record<string, string> = {};
  for (const [key, value] of Object.entries(raw)) {
    if (typeof value !== 'string') return null;
    out[key] = value;
  }
  return out;
}

function sanitizeProject(raw: unknown): StudioProject | null {
  if (!raw || typeof raw !== 'object') return null;
  const item = raw as Record<string, unknown>;
  if (typeof item.id !== 'string' || !item.id.trim()) return null;
  if (typeof item.createdAt !== 'string' || typeof item.updatedAt !== 'string') return null;
  const q = item.questionnaire;
  if (!q || typeof q !== 'object') return null;
  const questionnaire = q as QuestionnaireState;
  if (!['vision', 'brief', 'beats', 'options', 'review'].includes(questionnaire.step)) return null;
  if (typeof questionnaire.vision !== 'string') return null;
  const brief = stringMap(questionnaire.brief);
  const beats = stringMap(questionnaire.beats);
  if (!brief || !beats) return null;
  const options = questionnaire.options;
  if (!options || typeof options !== 'object') return null;
  if (typeof options.archetype !== 'string' || typeof options.target !== 'string') return null;
  if (!(options.era == null || typeof options.era === 'string')) return null;
  if (!(options.generation == null || typeof options.generation === 'string')) return null;
  let lastRun: RunSnapshot | null = null;
  if (item.lastRun != null) {
    if (typeof item.lastRun !== 'object') return null;
    const run = item.lastRun as RunSnapshot;
    if (run.phase !== 'done' && run.phase !== 'error') return null;
    if (!(run.error == null || typeof run.error === 'string')) return null;
    if (typeof run.succeeded !== 'boolean') return null;
    lastRun = {
      phase: run.phase,
      error: run.error ?? null,
      startedAt: typeof run.startedAt === 'number' ? run.startedAt : null,
      finishedAt: typeof run.finishedAt === 'number' ? run.finishedAt : null,
      succeeded: run.succeeded,
      payload: run.payload && typeof run.payload === 'object' ? run.payload : null,
    };
  }
  return {
    id: item.id,
    title: typeof item.title === 'string' && item.title.trim() ? item.title : 'Untitled project',
    createdAt: item.createdAt,
    updatedAt: item.updatedAt,
    questionnaire: { step: questionnaire.step, vision: questionnaire.vision, brief, beats, options: { ...options } },
    lastRun,
  };
}

/** One unreadable project fails the whole file so a later save cannot drop the rest. */
export function sanitizeProjects(raw: unknown): { projects: StudioProject[]; corrupt: boolean } {
  if (raw == null) return { projects: [], corrupt: false };
  if (!Array.isArray(raw)) return { projects: [], corrupt: true };
  const projects: StudioProject[] = [];
  for (const item of raw) {
    const project = sanitizeProject(item);
    if (!project) return { projects: [], corrupt: true };
    projects.push(project);
  }
  return { projects, corrupt: false };
}

export interface AuthClient {
  checkMe: () => Promise<AuthObservation>;
  completeWebRedirect: () => Promise<unknown>;
}

export async function bootstrap(load: () => Promise<LoadResult>, auth: AuthClient): Promise<FoundationState> {
  let state = initialFoundationState();
  try { await auth.completeWebRedirect(); } catch { /* checkMe still decides the session */ }
  let loaded: LoadResult;
  try {
    loaded = await load();
  } catch (error) {
    loaded = {
      onboarded: false,
      projects: [],
      prefs: DEFAULT_PREFS,
      projectsCorrupt: false,
      holdSaves: true,
      error: error instanceof Error ? error.message : 'Saved studio data could not be read.',
    };
  }
  state = foundationReducer(state, { type: 'hydrated', ...loaded });
  try {
    const me = await auth.checkMe();
    state = foundationReducer(state, { type: 'auth', view: viewFromMe(me) });
  } catch (error) {
    state = foundationReducer(state, {
      type: 'auth',
      view: {
        phase: 'unavailable',
        authenticated: false,
        enforced: true,
        role: 'anonymous',
        email: null,
        error: error instanceof Error ? error.message : 'The account service did not answer.',
      },
    });
  }
  return state;
}
