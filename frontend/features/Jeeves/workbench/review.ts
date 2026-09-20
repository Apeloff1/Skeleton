import type { CardSchedule, Review, ReviewGrade, StudyCard, Workbench } from './types';
import { assertEnum, assertInteger, assertNumber, WorkbenchError } from './validation';

export const MINUTE = 60_000;
export const DAY = 24 * 60 * MINUTE;
const LEARNING_STEPS = [1, 10];
const MAX_INTERVAL = 36500;

export function initialSchedule(now: number): CardSchedule {
  return {
    state: 'new',
    dueAt: now,
    intervalDays: 0,
    ease: 2.5,
    repetitions: 0,
    lapses: 0,
    learningStep: 0,
    lastReviewedAt: null,
    suspendedFrom: null,
  };
}

function boundedInterval(days: number): number {
  return Math.min(MAX_INTERVAL, Math.max(1, Math.round(days)));
}

function reviewSchedule(previous: CardSchedule, grade: ReviewGrade, now: number): CardSchedule {
  const next = { ...previous };
  const elapsedDays = previous.lastReviewedAt === null ? 0 : Math.max(0, (now - previous.lastReviewedAt) / DAY);
  const delay = Math.max(0, elapsedDays - previous.intervalDays);
  if (grade === 'again') {
    next.state = 'relearning';
    next.learningStep = 0;
    next.lapses += 1;
    next.intervalDays = Math.max(1, Math.round(previous.intervalDays * 0.5));
    next.ease = Math.max(1.3, previous.ease - 0.2);
    next.dueAt = now + LEARNING_STEPS[0] * MINUTE;
    return next;
  }
  if (grade === 'hard') {
    next.intervalDays = boundedInterval(previous.intervalDays * 1.2 + delay * 0.25);
    next.ease = Math.max(1.3, previous.ease - 0.15);
  } else if (grade === 'good') {
    next.intervalDays = boundedInterval((previous.intervalDays + delay * 0.5) * previous.ease);
  } else {
    next.intervalDays = boundedInterval((previous.intervalDays + delay) * previous.ease * 1.3);
    next.ease = Math.min(3.5, previous.ease + 0.15);
  }
  // A successful review must not reduce its prior interval unless it reached the cap.
  next.intervalDays = Math.max(next.intervalDays, Math.min(MAX_INTERVAL, previous.intervalDays + 1));
  next.dueAt = now + next.intervalDays * DAY;
  next.state = 'review';
  next.learningStep = 0;
  return next;
}

function learningSchedule(previous: CardSchedule, grade: ReviewGrade, now: number): CardSchedule {
  const next = { ...previous };
  const relearning = previous.state === 'relearning';
  if (grade === 'easy') {
    next.state = 'review';
    next.intervalDays = relearning ? boundedInterval(previous.intervalDays * 1.3) : 4;
    next.dueAt = now + next.intervalDays * DAY;
    next.learningStep = 0;
    return next;
  }
  if (grade === 'again') {
    next.state = relearning ? 'relearning' : 'learning';
    next.learningStep = 0;
    next.dueAt = now + LEARNING_STEPS[0] * MINUTE;
    return next;
  }
  if (grade === 'hard') {
    next.state = relearning ? 'relearning' : 'learning';
    next.dueAt = now + 6 * MINUTE;
    return next;
  }
  if (previous.state === 'new' || previous.learningStep === 0) {
    next.state = relearning ? 'relearning' : 'learning';
    next.learningStep = 1;
    next.dueAt = now + LEARNING_STEPS[1] * MINUTE;
    return next;
  }
  next.state = 'review';
  next.learningStep = 0;
  next.intervalDays = relearning ? Math.max(1, previous.intervalDays) : 1;
  next.dueAt = now + next.intervalDays * DAY;
  return next;
}

/** Deterministic spaced repetition, not a claim of measured learning or calibrated recall probability. */
export function scheduleReview(previous: CardSchedule, grade: ReviewGrade, now: number): CardSchedule {
  assertEnum(grade, ['again', 'hard', 'good', 'easy'], 'Review grade');
  assertNumber(now, 'Review time', 0, 8.64e15 - MAX_INTERVAL * DAY);
  if (previous.state === 'suspended') throw new WorkbenchError('Resume this card before reviewing it.', 'blocked');
  if (previous.lastReviewedAt !== null && now < previous.lastReviewedAt) {
    throw new WorkbenchError('The review time is before the previous review.', 'conflict');
  }
  const next = previous.state === 'review'
    ? reviewSchedule(previous, grade, now)
    : learningSchedule(previous, grade, now);
  return {
    ...next,
    ease: Number(next.ease.toFixed(3)),
    repetitions: previous.repetitions + 1,
    lastReviewedAt: now,
    suspendedFrom: null,
  };
}

export function suspendSchedule(schedule: CardSchedule): CardSchedule {
  if (schedule.state === 'suspended') return { ...schedule };
  return { ...schedule, state: 'suspended', suspendedFrom: schedule.state };
}

export function resumeSchedule(schedule: CardSchedule, now: number): CardSchedule {
  if (schedule.state !== 'suspended') return { ...schedule };
  return {
    ...schedule,
    state: schedule.suspendedFrom || 'new',
    suspendedFrom: null,
    dueAt: Math.max(now, schedule.dueAt),
  };
}

export function localDayKey(time: number): string {
  const date = new Date(time);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export function dayStart(time: number): number {
  const date = new Date(time);
  date.setHours(0, 0, 0, 0);
  return date.getTime();
}

export function addCalendarDays(time: number, days: number): number {
  const date = new Date(time);
  date.setDate(date.getDate() + days);
  return date.getTime();
}

export interface ReviewQueue {
  cards: StudyCard[];
  due: number;
  newAvailable: number;
  newRemaining: number;
  reviewRemaining: number;
  learning: number;
  nextDueAt: number | null;
}

export function buildReviewQueue(state: Workbench, projectId: string, now: number): ReviewQueue {
  const today = localDayKey(now);
  const reviews = state.reviews.filter(item => item.projectId === projectId && localDayKey(item.reviewedAt) === today);
  const introduced = new Set(reviews.filter(item => item.previous.state === 'new').map(item => item.cardId));
  const reviewed = new Set(reviews.filter(item => item.previous.state === 'review').map(item => item.cardId));
  const newRemaining = Math.max(0, state.preferences.dailyNewCards - introduced.size);
  const reviewRemaining = Math.max(0, state.preferences.dailyReviewCards - reviewed.size);
  const cards = state.cards.filter(card => card.projectId === projectId && card.schedule.state !== 'suspended');
  const learning = cards.filter(card => ['learning', 'relearning'].includes(card.schedule.state) && card.schedule.dueAt <= now);
  const due = cards.filter(card => card.schedule.state === 'review' && card.schedule.dueAt <= now);
  const fresh = cards.filter(card => card.schedule.state === 'new');
  learning.sort((a, b) => a.schedule.dueAt - b.schedule.dueAt || a.id.localeCompare(b.id));
  due.sort((a, b) => a.schedule.dueAt - b.schedule.dueAt || a.id.localeCompare(b.id));
  fresh.sort((a, b) => a.createdAt - b.createdAt || a.id.localeCompare(b.id));
  const future = cards.filter(card => card.schedule.state !== 'new' && card.schedule.dueAt > now);
  return {
    cards: [...learning, ...due.slice(0, reviewRemaining), ...fresh.slice(0, newRemaining)],
    due: due.length,
    newAvailable: fresh.length,
    newRemaining,
    reviewRemaining,
    learning: learning.length,
    nextDueAt: future.length ? Math.min(...future.map(card => card.schedule.dueAt)) : null,
  };
}

export function gradeIntervals(schedule: CardSchedule, now: number): Record<ReviewGrade, string> {
  const label = (grade: ReviewGrade) => {
    const next = scheduleReview(schedule, grade, now);
    return intervalLabel(next.dueAt - now);
  };
  return {
    again: label('again'),
    hard: label('hard'),
    good: label('good'),
    easy: label('easy'),
  };
}

export function intervalLabel(milliseconds: number): string {
  if (milliseconds < MINUTE) return 'now';
  if (milliseconds < 60 * MINUTE) return `${Math.round(milliseconds / MINUTE)}m`;
  if (milliseconds < DAY) return `${Math.round(milliseconds / (60 * MINUTE))}h`;
  const days = Math.round(milliseconds / DAY);
  if (days < 30) return `${days}d`;
  if (days < 365) return `${Math.round(days / 30)}mo`;
  return `${(days / 365).toFixed(1)}y`;
}

export interface ReviewDay {
  day: string;
  reviews: number;
  cards: number;
  minutes: number;
  again: number;
  hard: number;
  good: number;
  easy: number;
}

export function reviewHistory(reviews: Review[], now: number, days = 14): ReviewDay[] {
  assertInteger(days, 'History days', 1, 366);
  const byDay = new Map<string, Review[]>();
  for (const review of reviews) {
    if (review.reviewedAt > now) continue;
    const day = localDayKey(review.reviewedAt);
    byDay.set(day, [...(byDay.get(day) || []), review]);
  }
  return Array.from({ length: days }, (_, index) => {
    const day = localDayKey(addCalendarDays(now, index - days + 1));
    const entries = byDay.get(day) || [];
    return {
      day,
      reviews: entries.length,
      cards: new Set(entries.map(item => item.cardId)).size,
      minutes: Math.round(entries.reduce((total, item) => total + item.durationMs, 0) / MINUTE),
      again: entries.filter(item => item.grade === 'again').length,
      hard: entries.filter(item => item.grade === 'hard').length,
      good: entries.filter(item => item.grade === 'good').length,
      easy: entries.filter(item => item.grade === 'easy').length,
    };
  });
}

export function reviewStreak(reviews: Review[], now: number): number {
  const dates = new Set(reviews.filter(review => review.reviewedAt <= now).map(review => localDayKey(review.reviewedAt)));
  let cursor = now;
  if (!dates.has(localDayKey(cursor))) cursor = addCalendarDays(cursor, -1);
  let streak = 0;
  while (dates.has(localDayKey(cursor)) && streak < 36600) {
    streak += 1;
    cursor = addCalendarDays(cursor, -1);
  }
  return streak;
}

export function difficultCards(cards: StudyCard[], reviews: Review[], limit = 10): StudyCard[] {
  const lastGrades = new Map<string, Review[]>();
  for (const review of [...reviews].sort((a, b) => b.reviewedAt - a.reviewedAt)) {
    const current = lastGrades.get(review.cardId) || [];
    if (current.length < 10) current.push(review);
    lastGrades.set(review.cardId, current);
  }
  const score = (card: StudyCard) => {
    const recent = lastGrades.get(card.id) || [];
    const failures = recent.filter(review => review.grade === 'again').length;
    const hard = recent.filter(review => review.grade === 'hard').length;
    return failures * 3 + hard + card.schedule.lapses;
  };
  return cards.filter(card => score(card) > 0)
    .sort((a, b) => score(b) - score(a) || a.id.localeCompare(b.id))
    .slice(0, Math.max(0, limit));
}
