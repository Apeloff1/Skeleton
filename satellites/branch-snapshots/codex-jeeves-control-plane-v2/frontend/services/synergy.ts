/**
 * CodeDock Synergy Service v12.0
 * 
 * Frontend integration layer for cross-feature data flow.
 * Connects learning progress, emotional state, and AI interactions.
 */

const API_BASE = process.env.EXPO_PUBLIC_BACKEND_URL || '';

export interface UserContext {
  user_id: string;
  context: {
    profile: Record<string, any>;
    learning: {
      modules_completed: number;
      current_track: string | null;
      study_streak: number;
      total_study_time: number;
    };
    emotional: {
      current_state: string;
      stress_level: number;
      engagement: number;
      preferred_pace: string;
    };
    recent_interactions: Array<{ type: string; topic: string }>;
  };
  recommendations?: Array<Record<string, any>>;
  insights?: {
    total_ai_interactions: number;
    interactions_this_week: number;
    learning_velocity: number;
    engagement_trend: string;
  };
}

export interface SessionStartResponse {
  session_started: boolean;
  module_id: string;
  emotional_context: {
    detected_emotion: string;
    stress_level: number;
  };
  content_adaptations: string[];
  recommended_session_length: number;
  tips: string[];
}

export interface DashboardData {
  user_id: string;
  period: string;
  learning: {
    total_study_minutes: number;
    modules_completed: number;
    current_streak: number;
    xp_earned: number;
  };
  ai_usage: {
    total_interactions: number;
    by_type: Record<string, number>;
    avg_per_day: number;
  };
  emotional_wellness: {
    current_state: string;
    avg_stress_level: number;
    pomodoro_sessions: number;
  };
  recommendations: Array<Record<string, any>>;
}

class SynergyService {
  private baseUrl: string;

  constructor() {
    this.baseUrl = `${API_BASE}/api/synergy`;
  }

  /**
   * Get unified user context for personalization
   */
  async getUserContext(
    userId: string,
    includeRecommendations = true,
    includeInsights = true
  ): Promise<UserContext> {
    try {
      const response = await fetch(`${this.baseUrl}/context`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          include_recommendations: includeRecommendations,
          include_insights: includeInsights,
        }),
      });
      
      if (!response.ok) {
        throw new Error(`Failed to get user context: ${response.status}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error('SynergyService.getUserContext error:', error);
      // Return default context on error
      return {
        user_id: userId,
        context: {
          profile: {},
          learning: { modules_completed: 0, current_track: null, study_streak: 0, total_study_time: 0 },
          emotional: { current_state: 'neutral', stress_level: 0.3, engagement: 0.7, preferred_pace: 'moderate' },
          recent_interactions: [],
        },
      };
    }
  }

  /**
   * Start a learning session with emotional context
   */
  async startSession(
    userId: string,
    moduleId: string,
    sessionType: 'reading' | 'quiz' | 'practice' = 'reading'
  ): Promise<SessionStartResponse> {
    try {
      const response = await fetch(`${this.baseUrl}/session/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          module_id: moduleId,
          session_type: sessionType,
        }),
      });
      
      if (!response.ok) {
        throw new Error(`Failed to start session: ${response.status}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error('SynergyService.startSession error:', error);
      return {
        session_started: false,
        module_id: moduleId,
        emotional_context: { detected_emotion: 'neutral', stress_level: 0.3 },
        content_adaptations: [],
        recommended_session_length: 25,
        tips: ['Ready to learn? Let\'s dive in!'],
      };
    }
  }

  /**
   * Update learning progress
   */
  async updateProgress(
    userId: string,
    moduleId: string,
    progress: number,
    timeSpentSeconds: number,
    emotionalState?: string
  ): Promise<{ progress_updated: boolean; xp_earned: number; new_achievements: any[] }> {
    try {
      const response = await fetch(`${this.baseUrl}/session/update`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          module_id: moduleId,
          progress,
          time_spent_seconds: timeSpentSeconds,
          emotional_state: emotionalState,
        }),
      });
      
      if (!response.ok) {
        throw new Error(`Failed to update progress: ${response.status}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error('SynergyService.updateProgress error:', error);
      return { progress_updated: false, xp_earned: 0, new_achievements: [] };
    }
  }

  /**
   * Log AI interaction for analytics
   */
  async logAIInteraction(
    userId: string,
    interactionType: string,
    prompt: string,
    response: string,
    contextModule?: string,
    satisfactionRating?: number
  ): Promise<{ logged: boolean; interaction_id?: string }> {
    try {
      const res = await fetch(`${this.baseUrl}/ai/log`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          interaction_type: interactionType,
          prompt,
          response,
          context_module: contextModule,
          satisfaction_rating: satisfactionRating,
        }),
      });
      
      if (!res.ok) {
        throw new Error(`Failed to log AI interaction: ${res.status}`);
      }
      
      return await res.json();
    } catch (error) {
      console.error('SynergyService.logAIInteraction error:', error);
      return { logged: false };
    }
  }

  /**
   * Get unified dashboard data
   */
  async getDashboard(userId: string, timeRangeDays = 7): Promise<DashboardData> {
    try {
      const response = await fetch(`${this.baseUrl}/dashboard`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          time_range_days: timeRangeDays,
        }),
      });
      
      if (!response.ok) {
        throw new Error(`Failed to get dashboard: ${response.status}`);
      }
      
      return await response.json();
    } catch (error) {
      console.error('SynergyService.getDashboard error:', error);
      return {
        user_id: userId,
        period: `Last ${timeRangeDays} days`,
        learning: { total_study_minutes: 0, modules_completed: 0, current_streak: 0, xp_earned: 0 },
        ai_usage: { total_interactions: 0, by_type: {}, avg_per_day: 0 },
        emotional_wellness: { current_state: 'neutral', avg_stress_level: 0.3, pomodoro_sessions: 0 },
        recommendations: [],
      };
    }
  }
}

export const synergyService = new SynergyService();
export default synergyService;
