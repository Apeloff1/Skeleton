/**
 * classStore.ts — client-side enrolment, week progress, quiz scores, and notes.
 * AsyncStorage-backed, single key per concern. Computes overall percent and
 * certificate eligibility.
 */
import { useEffect, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { bumpStat } from './userStore';

const ENROL_KEY = '@codedock:classes:enrolled';
const PROG_KEY  = '@codedock:classes:weekprog';   // { [classId]: { [week]: 'started' | 'completed' } }
const QUIZ_KEY  = '@codedock:classes:quiz';       // { [classId]: { [week]: { score, total, taken_at } } }
const NOTE_KEY  = '@codedock:reading:notes';      // { [`${itemType}:${itemId}:${chapter}`]: Array<Note> }

export interface ClassEnrol { class_id: string; title: string; enrolled_at: string; }
export interface QuizResult { score: number; total: number; taken_at: string; }
export interface ChapterNote { id: string; text: string; created_at: string; color?: string; }

// ── Enrolment ──
export async function enrolClass(class_id: string, title: string): Promise<void> {
  const cur = await listEnrolments();
  if (cur.find(c => c.class_id === class_id)) return;
  const next = [...cur, { class_id, title, enrolled_at: new Date().toISOString() }];
  await AsyncStorage.setItem(ENROL_KEY, JSON.stringify(next));
  bumpStat('classes_started', 1, 30);
}
export async function unenrolClass(class_id: string): Promise<void> {
  const cur = await listEnrolments();
  await AsyncStorage.setItem(ENROL_KEY, JSON.stringify(cur.filter(c => c.class_id !== class_id)));
}
export async function listEnrolments(): Promise<ClassEnrol[]> {
  try { const raw = await AsyncStorage.getItem(ENROL_KEY); return raw ? JSON.parse(raw) : []; } catch { return []; }
}

// ── Week progress ──
type WeekStatus = 'started' | 'completed';
export async function setWeekStatus(class_id: string, week: number, status: WeekStatus): Promise<void> {
  const all = await getAllProgress();
  const cls = all[class_id] || {};
  const prev = cls[week];
  cls[week] = status;
  all[class_id] = cls;
  await AsyncStorage.setItem(PROG_KEY, JSON.stringify(all));
  if (status === 'completed' && prev !== 'completed') {
    bumpStat('classes_weeks_completed', 1, 50);
  }
}
export async function getAllProgress(): Promise<Record<string, Record<number, WeekStatus>>> {
  try { const raw = await AsyncStorage.getItem(PROG_KEY); return raw ? JSON.parse(raw) : {}; } catch { return {}; }
}
export async function getClassProgress(class_id: string): Promise<Record<number, WeekStatus>> {
  return (await getAllProgress())[class_id] || {};
}

// ── Quiz ──
export async function saveQuiz(class_id: string, week: number, score: number, total: number): Promise<void> {
  const all = await getAllQuizScores();
  all[class_id] = all[class_id] || {};
  all[class_id][week] = { score, total, taken_at: new Date().toISOString() };
  await AsyncStorage.setItem(QUIZ_KEY, JSON.stringify(all));
}
export async function getAllQuizScores(): Promise<Record<string, Record<number, QuizResult>>> {
  try { const raw = await AsyncStorage.getItem(QUIZ_KEY); return raw ? JSON.parse(raw) : {}; } catch { return {}; }
}

// ── Notes ──
function noteKey(itemType: string, itemId: string, chapter: number) { return `${itemType}:${itemId}:${chapter}`; }
export async function addNote(itemType: string, itemId: string, chapter: number, text: string, color = '#3B82F6'): Promise<ChapterNote> {
  const all = await getAllNotes();
  const k = noteKey(itemType, itemId, chapter);
  const note: ChapterNote = { id: `n_${Date.now()}_${Math.floor(Math.random()*1e4)}`, text, color, created_at: new Date().toISOString() };
  all[k] = [...(all[k] || []), note];
  await AsyncStorage.setItem(NOTE_KEY, JSON.stringify(all));
  return note;
}
export async function getNotes(itemType: string, itemId: string, chapter: number): Promise<ChapterNote[]> {
  return (await getAllNotes())[noteKey(itemType, itemId, chapter)] || [];
}
export async function deleteNote(itemType: string, itemId: string, chapter: number, id: string): Promise<void> {
  const all = await getAllNotes();
  const k = noteKey(itemType, itemId, chapter);
  all[k] = (all[k] || []).filter(n => n.id !== id);
  await AsyncStorage.setItem(NOTE_KEY, JSON.stringify(all));
}
export async function getAllNotes(): Promise<Record<string, ChapterNote[]>> {
  try { const raw = await AsyncStorage.getItem(NOTE_KEY); return raw ? JSON.parse(raw) : {}; } catch { return {}; }
}

// ── Certificate eligibility ──
export function classCompletionPercent(weeks: number, progress: Record<number, WeekStatus>): number {
  if (!weeks) return 0;
  const done = Object.values(progress).filter(s => s === 'completed').length;
  return Math.min(100, (done / weeks) * 100);
}
export function isClassCompleted(weeks: number, progress: Record<number, WeekStatus>): boolean {
  return classCompletionPercent(weeks, progress) >= 100;
}

// ── React hook for live enrolments + progress ──
export function useEnrolmentsLive() {
  const [data, setData] = useState<{ enrolments: ClassEnrol[]; progress: Record<string, Record<number, WeekStatus>>; quizzes: Record<string, Record<number, QuizResult>>; }>({ enrolments: [], progress: {}, quizzes: {} });
  useEffect(() => {
    const reload = async () => {
      const [enrolments, progress, quizzes] = await Promise.all([listEnrolments(), getAllProgress(), getAllQuizScores()]);
      setData({ enrolments, progress, quizzes });
    };
    reload();
    const t = setInterval(reload, 3000);
    return () => clearInterval(t);
  }, []);
  return data;
}
