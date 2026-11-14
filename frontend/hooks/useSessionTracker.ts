/**
 * Session Tracker Hook v12.0
 * 
 * Real-time session tracking that integrates with the Synergy API.
 * Automatically tracks:
 * - Learning session start/end
 * - Progress updates
 * - AI interactions
 * - Emotional state changes
 */

import { useCallback, useRef, useState, useEffect } from 'react';
import { synergyService, SessionStartResponse } from '../services/synergy';
import { Achievement } from '../components/AchievementNotification';

interface SessionState {
  active: boolean;
  moduleId: string | null;
  sessionType: 'reading' | 'quiz' | 'practice' | null;
  startTime: number | null;
  progress: number;
  emotionalContext: {
    emotion: string;
    stressLevel: number;
  } | null;
  contentAdaptations: string[];
  tips: string[];
}

interface UseSessionTrackerReturn {
  session: SessionState;
  achievements: Achievement[];
  xpEarned: number;
  startSession: (moduleId: string, sessionType?: 'reading' | 'quiz' | 'practice') => Promise<SessionStartResponse | null>;
  updateProgress: (progress: number, emotionalState?: string) => Promise<void>;
  endSession: () => Promise<void>;
  logAIInteraction: (type: string, prompt: string, response: string) => Promise<void>;
  clearAchievements: () => void;
}

export const useSessionTracker = (userId: string = 'default_user'): UseSessionTrackerReturn => {
  const [session, setSession] = useState<SessionState>({
    active: false,
    moduleId: null,
    sessionType: null,
    startTime: null,
    progress: 0,
    emotionalContext: null,
    contentAdaptations: [],
    tips: [],
  });

  const [achievements, setAchievements] = useState<Achievement[]>([]);
  const [xpEarned, setXpEarned] = useState(0);
  const progressUpdateTimeout = useRef<NodeJS.Timeout | null>(null);
  const lastProgressUpdate = useRef<number>(0);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (progressUpdateTimeout.current) {
        clearTimeout(progressUpdateTimeout.current);
      }
    };
  }, []);

  /**
   * Start a new learning session
   */
  const startSession = useCallback(async (
    moduleId: string,
    sessionType: 'reading' | 'quiz' | 'practice' = 'reading'
  ): Promise<SessionStartResponse | null> => {
    try {
      const response = await synergyService.startSession(userId, moduleId, sessionType);
      
      setSession({
        active: true,
        moduleId,
        sessionType,
        startTime: Date.now(),
        progress: 0,
        emotionalContext: response.emotional_context as any,
        contentAdaptations: response.content_adaptations,
        tips: response.tips,
      });

      return response;
    } catch (error) {
      console.error('Failed to start session:', error);
      // Start session locally even if API fails
      setSession({
        active: true,
        moduleId,
        sessionType,
        startTime: Date.now(),
        progress: 0,
        emotionalContext: null,
        contentAdaptations: [],
        tips: ['Ready to learn? Let\'s dive in!'],
      });
      return null;
    }
  }, [userId]);

  /**
   * Update progress with debouncing to avoid too many API calls
   */
  const updateProgress = useCallback(async (
    progress: number,
    emotionalState?: string
  ): Promise<void> => {
    if (!session.active || !session.moduleId || !session.startTime) {
      return;
    }

    // Update local state immediately
    setSession(prev => ({ ...prev, progress }));

    // Debounce API calls (max once per 5 seconds)
    const now = Date.now();
    if (now - lastProgressUpdate.current < 5000) {
      // Clear existing timeout and set new one
      if (progressUpdateTimeout.current) {
        clearTimeout(progressUpdateTimeout.current);
      }
      progressUpdateTimeout.current = setTimeout(() => {
        updateProgressAPI(progress, emotionalState);
      }, 5000) as any;
      return;
    }

    await updateProgressAPI(progress, emotionalState);
  }, [session, userId]);

  const updateProgressAPI = async (progress: number, emotionalState?: string) => {
    if (!session.moduleId || !session.startTime) return;

    lastProgressUpdate.current = Date.now();
    const timeSpentSeconds = Math.floor((Date.now() - session.startTime) / 1000);

    try {
      const result = await synergyService.updateProgress(
        userId,
        session.moduleId,
        progress,
        timeSpentSeconds,
        emotionalState
      );

      // Add XP
      setXpEarned(prev => prev + result.xp_earned);

      // Check for new achievements
      if (result.new_achievements && result.new_achievements.length > 0) {
        const newAchievements: Achievement[] = result.new_achievements.map((a: any) => ({
          id: a.id,
          name: a.name,
          xp: a.xp,
          tier: getTierFromXp(a.xp),
        }));
        setAchievements(prev => [...prev, ...newAchievements]);
      }
    } catch (error) {
      console.error('Failed to update progress:', error);
    }
  };

  /**
   * End the current session
   */
  const endSession = useCallback(async (): Promise<void> => {
    if (!session.active || !session.moduleId || !session.startTime) {
      return;
    }

    // Final progress update
    const timeSpentSeconds = Math.floor((Date.now() - session.startTime) / 1000);
    
    try {
      await synergyService.updateProgress(
        userId,
        session.moduleId,
        session.progress,
        timeSpentSeconds
      );
    } catch (error) {
      console.error('Failed to save final session progress:', error);
    }

    // Reset session state
    setSession({
      active: false,
      moduleId: null,
      sessionType: null,
      startTime: null,
      progress: 0,
      emotionalContext: null,
      contentAdaptations: [],
      tips: [],
    });
  }, [session, userId]);

  /**
   * Log an AI interaction
   */
  const logAIInteraction = useCallback(async (
    type: string,
    prompt: string,
    response: string
  ): Promise<void> => {
    try {
      await synergyService.logAIInteraction(
        userId,
        type,
        prompt,
        response,
        session.moduleId || undefined
      );
    } catch (error) {
      console.error('Failed to log AI interaction:', error);
    }
  }, [userId, session.moduleId]);

  /**
   * Clear achievements queue
   */
  const clearAchievements = useCallback(() => {
    setAchievements([]);
  }, []);

  return {
    session,
    achievements,
    xpEarned,
    startSession,
    updateProgress,
    endSession,
    logAIInteraction,
    clearAchievements,
  };
};

// Helper function to determine achievement tier based on XP
function getTierFromXp(xp: number): 'bronze' | 'silver' | 'gold' | 'platinum' {
  if (xp >= 2000) return 'platinum';
  if (xp >= 500) return 'gold';
  if (xp >= 100) return 'silver';
  return 'bronze';
}

export default useSessionTracker;
