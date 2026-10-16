/**
 * Long-running learning sessions: ordered progress writes, bounded UI queues,
 * and epoch-fenced async completions. The server currently identifies progress
 * by user+module; do not claim a durable session transaction from this hook.
 */
import { useCallback, useRef, useState, useEffect } from 'react';
import { synergyService, type SessionStartResponse } from '../services/synergy';
import type { Achievement } from '../components/AchievementNotification';

type SessionType = 'reading' | 'quiz' | 'practice';
interface SessionState {
  active: boolean;
  moduleId: string | null;
  sessionType: SessionType | null;
  startTime: number | null;
  progress: number;
  emotionalContext: { emotion: string; stressLevel: number } | null;
  contentAdaptations: string[];
  tips: string[];
}
interface UseSessionTrackerReturn {
  session: SessionState;
  achievements: Achievement[];
  xpEarned: number;
  startSession: (moduleId: string, sessionType?: SessionType) => Promise<SessionStartResponse | null>;
  updateProgress: (progress: number, emotionalState?: string) => Promise<void>;
  endSession: () => Promise<void>;
  logAIInteraction: (type: string, prompt: string, response: string) => Promise<void>;
  clearAchievements: () => void;
}
const INITIAL_SESSION: SessionState = {
  active: false, moduleId: null, sessionType: null, startTime: null, progress: 0,
  emotionalContext: null, contentAdaptations: [], tips: [],
};
const PROGRESS_INTERVAL_MS = 5_000;
const MAX_ACHIEVEMENTS = 100;

function getTierFromXp(xp: number): 'bronze' | 'silver' | 'gold' | 'platinum' {
  if (xp >= 2000) return 'platinum';
  if (xp >= 500) return 'gold';
  if (xp >= 100) return 'silver';
  return 'bronze';
}

export const useSessionTracker = (userId: string = 'default_user'): UseSessionTrackerReturn => {
  const [session, setSession] = useState<SessionState>(INITIAL_SESSION);
  const [achievements, setAchievements] = useState<Achievement[]>([]);
  const [xpEarned, setXpEarned] = useState(0);
  const liveSessionRef = useRef<SessionState>(INITIAL_SESSION);
  const mountedRef = useRef(true);
  const sessionEpochRef = useRef(0);
  const progressTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastProgressUpdateRef = useRef(0);
  const progressQueueRef = useRef<Promise<void>>(Promise.resolve());
  const endingRef = useRef<Promise<void> | null>(null);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      sessionEpochRef.current++;
      if (progressTimerRef.current) clearTimeout(progressTimerRef.current);
      progressTimerRef.current = null;
    };
  }, []);

  const cancelDelayedProgress = useCallback(() => {
    if (progressTimerRef.current) clearTimeout(progressTimerRef.current);
    progressTimerRef.current = null;
  }, []);

  // Serialize POSTs: a slower old progress response must not overtake the
  // final state of the same session on the wire.
  const queueProgress = useCallback((snapshot: SessionState, epoch: number, emotionalState?: string) => {
    if (!snapshot.moduleId || !snapshot.startTime) return progressQueueRef.current;
    const payload = { ...snapshot };
    const task = progressQueueRef.current.then(async () => {
      if (!mountedRef.current || epoch !== sessionEpochRef.current) return;
      const seconds = Math.max(0, Math.floor((Date.now() - payload.startTime!) / 1000));
      const result = await synergyService.updateProgress(
        userId, payload.moduleId!, payload.progress, seconds, emotionalState,
      );
      if (!mountedRef.current || epoch !== sessionEpochRef.current || !result.progress_updated) return;
      const xp = Number.isFinite(result.xp_earned) && result.xp_earned > 0
        ? result.xp_earned : 0;
      if (xp) setXpEarned(previous => previous + xp);
      if (Array.isArray(result.new_achievements) && result.new_achievements.length) {
        const gained: Achievement[] = result.new_achievements
          .filter(item => item && typeof item.id === 'string' && Number.isFinite(item.xp))
          .map(item => ({
            id: item.id, name: item.name, xp: item.xp, tier: getTierFromXp(item.xp),
          }));
        if (gained.length) setAchievements(previous =>
          [...previous, ...gained].slice(-MAX_ACHIEVEMENTS));
      }
    });
    progressQueueRef.current = task.catch(error => {
      console.error('Failed to persist session progress:', error);
    });
    return progressQueueRef.current;
  }, [userId]);

  const startSession = useCallback(async (
    moduleId: string,
    sessionType: SessionType = 'reading',
  ): Promise<SessionStartResponse | null> => {
    cancelDelayedProgress();
    const epoch = ++sessionEpochRef.current;
    lastProgressUpdateRef.current = 0;
    liveSessionRef.current = INITIAL_SESSION;
    if (mountedRef.current) setSession(INITIAL_SESSION);
    let response: SessionStartResponse | null = null;
    try {
      response = await synergyService.startSession(userId, moduleId, sessionType);
    } catch (error) {
      console.error('Failed to start session:', error);
    }
    if (!mountedRef.current || epoch !== sessionEpochRef.current) return null;

    const started: SessionState = {
      active: true, moduleId, sessionType, startTime: Date.now(), progress: 0,
      emotionalContext: response ? {
        emotion: response.emotional_context?.detected_emotion ?? 'neutral',
        stressLevel: response.emotional_context?.stress_level ?? 0,
      } : null,
      contentAdaptations: response?.content_adaptations ?? [],
      tips: response?.tips ?? ['Ready to learn!'],
    };
    liveSessionRef.current = started;
    setSession(started);
    return response;
  }, [userId, cancelDelayedProgress]);

  const updateProgress = useCallback(async (progress: number, emotionalState?: string) => {
    const current = liveSessionRef.current;
    if (!mountedRef.current || !current.active || !Number.isFinite(progress)) return;
    const updated = { ...current, progress: Math.max(0, Math.min(100, progress)) };
    liveSessionRef.current = updated;
    setSession(updated);

    const elapsed = Date.now() - lastProgressUpdateRef.current;
    if (elapsed >= PROGRESS_INTERVAL_MS) {
      cancelDelayedProgress();
      lastProgressUpdateRef.current = Date.now();
      await queueProgress(updated, sessionEpochRef.current, emotionalState);
      return;
    }
    cancelDelayedProgress();
    const epoch = sessionEpochRef.current;
    progressTimerRef.current = setTimeout(() => {
      progressTimerRef.current = null;
      if (!mountedRef.current || epoch !== sessionEpochRef.current ||
          !liveSessionRef.current.active) return;
      lastProgressUpdateRef.current = Date.now();
      void queueProgress(liveSessionRef.current, epoch, emotionalState);
    }, PROGRESS_INTERVAL_MS - elapsed);
  }, [cancelDelayedProgress, queueProgress]);

  const endSession = useCallback(async () => {
    if (endingRef.current) return endingRef.current;
    const final = liveSessionRef.current;
    if (!mountedRef.current || !final.active || !final.moduleId || !final.startTime) return;
    cancelDelayedProgress();
    // Terminal locally before I/O: updates after this call cannot reschedule.
    liveSessionRef.current = INITIAL_SESSION;
    setSession(INITIAL_SESSION);
    const task = (async () => {
      try {
        await progressQueueRef.current;
        await synergyService.updateProgress(
          userId, final.moduleId!, final.progress,
          Math.max(0, Math.floor((Date.now() - final.startTime!) / 1000)),
        );
      } catch (error) {
        console.error('Failed to save final session progress:', error);
      }
    })();
    endingRef.current = task;
    try {
      await task;
    } finally {
      if (endingRef.current === task) endingRef.current = null;
    }
  }, [userId, cancelDelayedProgress]);

  const logAIInteraction = useCallback(async (type: string, prompt: string, response: string) => {
    if (!mountedRef.current) return;
    try {
      await synergyService.logAIInteraction(
        userId, type, prompt, response, liveSessionRef.current.moduleId || undefined,
      );
    } catch (error) {
      console.error('Failed to log AI interaction:', error);
    }
  }, [userId]);

  const clearAchievements = useCallback(() => setAchievements([]), []);

  return {
    session, achievements, xpEarned, startSession, updateProgress,
    endSession, logAIInteraction, clearAchievements,
  };
};

export default useSessionTracker;
