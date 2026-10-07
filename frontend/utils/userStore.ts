/**
 * userStore.ts — central client-side state for profile, streaks, goals, theme,
 * achievements, and pomodoro sessions. AsyncStorage-backed so it persists
 * across reloads and works on web + native APK.
 *
 * Exposes a tiny pub/sub via a Zustand-style hook so any component can subscribe
 * to slices of state without prop-drilling.
 */
import { useEffect, useState, useCallback } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const KEY = '@codedock:user';
const DEFAULT_AVATAR_COLORS = ['#3B82F6', '#10B981', '#F59E0B', '#A855F7', '#EC4899', '#06B6D4'];

export interface Achievement {
  id: string;
  title: string;
  description: string;
  icon: string;        // Ionicons name
  color: string;
  threshold: number;   // value at which it unlocks (against `metric`)
  metric: keyof UserStats;
}

export interface UserStats {
  reading_chapters_completed: number;
  classes_started: number;
  classes_completed: number;
  classes_weeks_completed: number;
  galaxy_builds: number;
  scheduler_events_created: number;
  pomodoro_sessions: number;
  pomodoro_focus_minutes: number;
  streak_current: number;
  streak_best: number;
  last_activity_date: string;  // YYYY-MM-DD
  total_xp: number;
}

export interface UserGoals {
  daily_reading_minutes: number;
  daily_focus_minutes: number;
  daily_classes_progress: number;  // weeks per day
}

export interface UserProfile {
  name: string;
  email: string;
  avatar_color: string;
  bio: string;
  joined_at: string;
}

export interface UserState {
  profile: UserProfile;
  stats: UserStats;
  goals: UserGoals;
  theme: 'dark' | 'light';
  unlocked_achievements: string[];  // ids
}

export const ACHIEVEMENT_CATALOG: Achievement[] = [
  { id: 'first_chapter', title: 'First Page', description: 'Read your first chapter', icon: 'book', color: '#3B82F6', threshold: 1, metric: 'reading_chapters_completed' },
  { id: 'reader_10', title: 'Bookworm', description: 'Read 10 chapters', icon: 'library', color: '#3B82F6', threshold: 10, metric: 'reading_chapters_completed' },
  { id: 'reader_50', title: 'Scholar', description: 'Read 50 chapters', icon: 'school', color: '#1D4ED8', threshold: 50, metric: 'reading_chapters_completed' },
  { id: 'reader_200', title: 'Polymath', description: 'Read 200 chapters', icon: 'ribbon', color: '#1E3A8A', threshold: 200, metric: 'reading_chapters_completed' },
  { id: 'first_class', title: 'Enrolled', description: 'Start your first class', icon: 'school', color: '#10B981', threshold: 1, metric: 'classes_started' },
  { id: 'class_grad', title: 'Graduate', description: 'Complete one class', icon: 'trophy', color: '#F59E0B', threshold: 1, metric: 'classes_completed' },
  { id: 'class_grad_5', title: 'Multi-Degree', description: 'Complete five classes', icon: 'medal', color: '#F59E0B', threshold: 5, metric: 'classes_completed' },
  { id: 'weeks_50', title: 'Halfway Mark', description: 'Complete 50 weeks of classes', icon: 'rocket', color: '#10B981', threshold: 50, metric: 'classes_weeks_completed' },
  { id: 'first_build', title: 'World-Maker', description: 'Build your first galaxy game', icon: 'planet', color: '#A855F7', threshold: 1, metric: 'galaxy_builds' },
  { id: 'builds_10', title: 'Studio Veteran', description: 'Ship 10 galaxy builds', icon: 'planet', color: '#7E22CE', threshold: 10, metric: 'galaxy_builds' },
  { id: 'first_event', title: 'Planner', description: 'Create your first scheduled event', icon: 'calendar', color: '#06B6D4', threshold: 1, metric: 'scheduler_events_created' },
  { id: 'streak_3', title: 'Habit', description: '3-day streak', icon: 'flame', color: '#F97316', threshold: 3, metric: 'streak_best' },
  { id: 'streak_7', title: 'Week Strong', description: '7-day streak', icon: 'flame', color: '#EA580C', threshold: 7, metric: 'streak_best' },
  { id: 'streak_30', title: 'Disciplined', description: '30-day streak', icon: 'flame', color: '#DC2626', threshold: 30, metric: 'streak_best' },
  { id: 'pomodoro_10', title: 'Deep Worker', description: '10 pomodoro sessions', icon: 'time', color: '#EC4899', threshold: 10, metric: 'pomodoro_sessions' },
  { id: 'pomodoro_60_hr', title: '60-Hour Sage', description: '60 hours of focused work', icon: 'hourglass', color: '#BE185D', threshold: 3600, metric: 'pomodoro_focus_minutes' },
  { id: 'xp_1000', title: 'Apprentice', description: '1,000 XP', icon: 'star', color: '#FBBF24', threshold: 1000, metric: 'total_xp' },
  { id: 'xp_10000', title: 'Master', description: '10,000 XP', icon: 'star', color: '#F59E0B', threshold: 10000, metric: 'total_xp' },
];

const DEFAULT_STATE: UserState = {
  profile: {
    name: 'Explorer',
    email: '',
    avatar_color: DEFAULT_AVATAR_COLORS[0],
    bio: '',
    joined_at: new Date().toISOString(),
  },
  stats: {
    reading_chapters_completed: 0,
    classes_started: 0,
    classes_completed: 0,
    classes_weeks_completed: 0,
    galaxy_builds: 0,
    scheduler_events_created: 0,
    pomodoro_sessions: 0,
    pomodoro_focus_minutes: 0,
    streak_current: 0,
    streak_best: 0,
    last_activity_date: '',
    total_xp: 0,
  },
  goals: {
    daily_reading_minutes: 30,
    daily_focus_minutes: 60,
    daily_classes_progress: 1,
  },
  theme: 'dark',
  unlocked_achievements: [],
};

// ── pub/sub ──
type Listener = (s: UserState) => void;
let _state: UserState = DEFAULT_STATE;
let _loaded = false;
const _listeners = new Set<Listener>();

async function _load() {
  if (_loaded) return;
  _loaded = true;
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      _state = {
        ...DEFAULT_STATE,
        ...parsed,
        profile: { ...DEFAULT_STATE.profile, ...(parsed.profile || {}) },
        stats: { ...DEFAULT_STATE.stats, ...(parsed.stats || {}) },
        goals: { ...DEFAULT_STATE.goals, ...(parsed.goals || {}) },
      };
    }
  } catch {
    // ignore
  }
  _listeners.forEach(l => l(_state));
}

async function _persist() {
  try { await AsyncStorage.setItem(KEY, JSON.stringify(_state)); } catch {}
}

function _notify() {
  _listeners.forEach(l => l(_state));
}

function _todayKey() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function _bumpStreak() {
  const today = _todayKey();
  const last = _state.stats.last_activity_date;
  if (last === today) return; // already counted today
  const lastDate = last ? new Date(last) : null;
  const todayDate = new Date(today);
  if (lastDate) {
    const diffDays = Math.round((todayDate.getTime() - lastDate.getTime()) / 86400000);
    if (diffDays === 1) {
      _state.stats.streak_current += 1;
    } else if (diffDays > 1) {
      _state.stats.streak_current = 1;
    }
  } else {
    _state.stats.streak_current = 1;
  }
  if (_state.stats.streak_current > _state.stats.streak_best) {
    _state.stats.streak_best = _state.stats.streak_current;
  }
  _state.stats.last_activity_date = today;
}

function _checkAchievements() {
  for (const a of ACHIEVEMENT_CATALOG) {
    if (_state.unlocked_achievements.includes(a.id)) continue;
    const val = Number((_state.stats as any)[a.metric] || 0);
    if (val >= a.threshold) {
      _state.unlocked_achievements = [..._state.unlocked_achievements, a.id];
      // bonus XP for unlocking
      _state.stats.total_xp += 50;
    }
  }
}

// ── public mutators ──
export async function setProfile(patch: Partial<UserProfile>) {
  await _load();
  _state.profile = { ..._state.profile, ...patch };
  await _persist();
  _notify();
}

export async function setGoals(patch: Partial<UserGoals>) {
  await _load();
  _state.goals = { ..._state.goals, ...patch };
  await _persist();
  _notify();
}

export async function setTheme(theme: 'dark' | 'light') {
  await _load();
  _state.theme = theme;
  await _persist();
  _notify();
}

export async function bumpStat(metric: keyof UserStats, delta = 1, xp = 10) {
  await _load();
  const cur = Number((_state.stats as any)[metric] || 0);
  (_state.stats as any)[metric] = cur + delta;
  _state.stats.total_xp += xp;
  _bumpStreak();
  _checkAchievements();
  await _persist();
  _notify();
}

export async function getState(): Promise<UserState> {
  await _load();
  return _state;
}

export async function resetUser() {
  _state = { ...DEFAULT_STATE, profile: { ...DEFAULT_STATE.profile, joined_at: new Date().toISOString() } };
  await _persist();
  _notify();
}

// ── React hook ──
export function useUser(): UserState {
  const [s, setS] = useState<UserState>(_state);
  useEffect(() => {
    _load();
    const l: Listener = (next) => setS(next);
    _listeners.add(l);
    return () => { _listeners.delete(l); };
  }, []);
  return s;
}

export const AVATAR_COLORS = DEFAULT_AVATAR_COLORS;
