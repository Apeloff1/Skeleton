/**
 * CodeDock API Service Layer v11.9
 * 
 * Centralized API service with proper error handling, retry logic,
 * and type-safe responses
 */

import Constants from 'expo-constants';

// ============================================================================
// CONFIGURATION
// ============================================================================

const API_BASE_URL = Constants.expoConfig?.extra?.EXPO_BACKEND_URL || '';
const DEFAULT_TIMEOUT = 30000;
const MAX_RETRIES = 3;
const RETRY_DELAY = 1000;

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

export interface APIResponse<T> {
  data: T | null;
  error: string | null;
  status: number;
  success: boolean;
}

export interface RequestConfig {
  timeout?: number;
  retries?: number;
  headers?: Record<string, string>;
}

export interface CodeReviewRequest {
  code: string;
  language: string;
  review_depth?: 'quick' | 'standard' | 'deep';
  focus_areas?: string[];
}

export interface CodeReviewResponse {
  review_id: string;
  structure_analysis: {
    total_lines: number;
    code_lines: number;
    comment_ratio: number;
    cyclomatic_complexity: number;
    max_nesting_depth: number;
  };
  security_analysis: {
    issues: Array<{
      type: string;
      severity: string;
      line: number;
      snippet: string;
      recommendation: string;
    }>;
    issues_count: number;
    high_severity: number;
  };
  quality_score: {
    overall: number;
    breakdown: Record<string, number>;
    grade: string;
  };
  ai_review: string;
}

export interface TestGenerationRequest {
  code: string;
  language: string;
  test_framework?: string;
  coverage_target?: number;
  test_types?: string[];
}

export interface TestGenerationResponse {
  test_code: string;
  framework: string;
  estimated_test_count: number;
  test_types: string[];
}

export interface LearningTrack {
  id: string;
  name: string;
  description: string;
  total_hours: number;
  sub_tracks: string[];
  difficulty_range: string;
}

export interface LearningModule {
  id: string;
  title: string;
  reading_time_minutes: number;
  content_type: string;
  difficulty: number;
  topics?: string[];
  learning_objectives?: string[];
  key_concepts?: Array<{ term: string; definition: string }>;
  code_examples?: Array<{ language: string; title: string; code: string }>;
}

export interface EmotionDetectionRequest {
  user_id: string;
  recent_actions: Array<{ action_type: string; [key: string]: any }>;
  text_input?: string;
}

export interface EmotionDetectionResponse {
  user_id: string;
  emotional_state: {
    primary: string;
    intensity: number;
    all_scores: Record<string, number>;
  };
  recommended_response_style: string;
  immediate_intervention_needed: boolean;
}

export interface PsychologyProfile {
  user_id: string;
  profile: {
    motivation_type: string;
    cognitive_style: string;
    stress_tolerance: string;
    learning_anxiety_level: number;
    growth_mindset_score: number;
    resilience_score: number;
  };
  recommendations: Array<{
    type: string;
    title: string;
    suggestions: string[];
  }>;
}

// ============================================================================
// BASE API CLASS
// ============================================================================

class BaseAPI {
  protected baseUrl: string;
  protected defaultHeaders: Record<string, string>;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
    this.defaultHeaders = {
      'Content-Type': 'application/json',
    };
  }

  protected async request<T>(
    endpoint: string,
    options: RequestInit = {},
    config: RequestConfig = {}
  ): Promise<APIResponse<T>> {
    const { timeout = DEFAULT_TIMEOUT, retries = MAX_RETRIES } = config;
    
    const url = `${this.baseUrl}${endpoint}`;
    const headers = { ...this.defaultHeaders, ...config.headers, ...options.headers as Record<string, string> };
    
    let lastError: Error | null = null;
    
    for (let attempt = 0; attempt <= retries; attempt++) {
      try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeout);
        
        const response = await fetch(url, {
          ...options,
          headers,
          signal: controller.signal,
        });
        
        clearTimeout(timeoutId);
        
        const data = await response.json().catch(() => null);
        
        return {
          data: response.ok ? data : null,
          error: response.ok ? null : data?.detail || data?.message || `HTTP ${response.status}`,
          status: response.status,
          success: response.ok,
        };
      } catch (error) {
        lastError = error as Error;
        
        if (attempt < retries) {
          await this.delay(RETRY_DELAY * (attempt + 1));
        }
      }
    }
    
    return {
      data: null,
      error: lastError?.message || 'Unknown error',
      status: 0,
      success: false,
    };
  }

  protected async get<T>(endpoint: string, config?: RequestConfig): Promise<APIResponse<T>> {
    return this.request<T>(endpoint, { method: 'GET' }, config);
  }

  protected async post<T>(endpoint: string, body: any, config?: RequestConfig): Promise<APIResponse<T>> {
    return this.request<T>(
      endpoint,
      { method: 'POST', body: JSON.stringify(body) },
      config
    );
  }

  protected async put<T>(endpoint: string, body: any, config?: RequestConfig): Promise<APIResponse<T>> {
    return this.request<T>(
      endpoint,
      { method: 'PUT', body: JSON.stringify(body) },
      config
    );
  }

  protected async delete<T>(endpoint: string, config?: RequestConfig): Promise<APIResponse<T>> {
    return this.request<T>(endpoint, { method: 'DELETE' }, config);
  }

  protected delay(ms: number): Promise<void> {
    return new Promise(resolve => setTimeout(resolve, ms));
  }
}

// ============================================================================
// AI TOOLKIT SERVICE
// ============================================================================

class AIToolkitService extends BaseAPI {
  async getInfo() {
    return this.get<{ name: string; capabilities: string[] }>('/api/ai-toolkit/info');
  }

  async codeReview(request: CodeReviewRequest) {
    return this.post<CodeReviewResponse>('/api/ai-toolkit/code-review', request);
  }

  async generateTests(request: TestGenerationRequest) {
    return this.post<TestGenerationResponse>('/api/ai-toolkit/generate-tests', request);
  }

  async refactor(code: string, language: string, goals: string[] = ['readability']) {
    return this.post<{ refactored_code: string }>('/api/ai-toolkit/refactor', {
      code, language, refactor_goals: goals, preserve_behavior: true
    });
  }

  async generateDocs(code: string, language: string, style: string = 'google') {
    return this.post<{ documented_code: string }>('/api/ai-toolkit/generate-docs', {
      code, language, doc_style: style, include_examples: true
    });
  }

  async predictBugs(code: string, language: string) {
    return this.post<{ bug_predictions: string; estimated_issues: number }>('/api/ai-toolkit/predict-bugs', {
      code, language
    });
  }

  async optimizePerformance(code: string, language: string, level: string = 'balanced') {
    return this.post<{ optimized_code: string }>(`/api/ai-toolkit/optimize-performance?code=${encodeURIComponent(code)}&language=${language}&optimization_level=${level}`, {});
  }

  async getQualityScore(code: string, language: string) {
    return this.get<{ quality_score: { overall: number; grade: string } }>(
      `/api/ai-toolkit/quality-score?code=${encodeURIComponent(code)}&language=${language}`
    );
  }

  async pairProgramming(userId: string, code: string, language: string, task: string, sessionId?: string) {
    return this.post<{ session_id: string; ai_response: string }>('/api/ai-toolkit/pair-programming', {
      user_id: userId, code, language, task_description: task, session_id: sessionId
    });
  }
}

// ============================================================================
// READING CURRICULUM SERVICE
// ============================================================================

class ReadingCurriculumService extends BaseAPI {
  async getInfo() {
    return this.get<{ total_curriculum_hours: number; knowledge_tracks: string[] }>('/api/reading/info');
  }

  async getTracks() {
    return this.get<{ tracks: LearningTrack[] }>('/api/reading/tracks');
  }

  async getTrack(trackId: string) {
    return this.get<{ track_id: string; sub_tracks: Record<string, any> }>(`/api/reading/track/${trackId}`);
  }

  async getModule(moduleId: string) {
    return this.get<LearningModule>(`/api/reading/module/${moduleId}`);
  }

  async getManuals() {
    return this.get<{ manuals: any[]; language_manuals: any[] }>('/api/reading/manuals');
  }

  async updateProgress(userId: string, moduleId: string, progress: number, completed: boolean = false) {
    return this.post<{ updated: boolean }>(`/api/reading/progress/update?user_id=${userId}&module_id=${moduleId}&progress_percent=${progress}&completed=${completed}`, {});
  }

  async getProgress(userId: string) {
    return this.get<{ modules_started: number; modules_completed: number; total_reading_time_hours: number }>(`/api/reading/progress/${userId}`);
  }

  async addBookmark(userId: string, moduleId: string, position: string, note?: string) {
    return this.post<{ created: boolean }>(`/api/reading/bookmark?user_id=${userId}&module_id=${moduleId}&position=${position}${note ? `&note=${encodeURIComponent(note)}` : ''}`, {});
  }

  async getBookmarks(userId: string) {
    return this.get<{ bookmarks: any[] }>(`/api/reading/bookmarks/${userId}`);
  }
}

// ============================================================================
// JEEVES EQ SERVICE
// ============================================================================

class JeevesEQService extends BaseAPI {
  async getInfo() {
    return this.get<{ capabilities: string[] }>('/api/jeeves-eq/info');
  }

  async detectEmotion(request: EmotionDetectionRequest) {
    return this.post<EmotionDetectionResponse>(`/api/jeeves-eq/detect-emotion?user_id=${request.user_id}`, request);
  }

  async getTherapeuticResponse(userId: string, emotion: string, intensity: number) {
    return this.post<{ response: string }>(`/api/jeeves-eq/therapeutic-response?user_id=${userId}&emotional_state=${emotion}&intensity=${intensity}`, {});
  }

  async getPsychologyProfile(userId: string) {
    return this.get<PsychologyProfile>(`/api/jeeves-eq/psychology-profile/${userId}`);
  }

  async checkCognitiveLoad(userId: string, duration: number, concepts: number, errors: number, lastBreak: number) {
    return this.post<{ cognitive_load_level: string; break_recommended: boolean }>(
      `/api/jeeves-eq/cognitive-load-check?user_id=${userId}&session_duration_minutes=${duration}&new_concepts_introduced=${concepts}&error_count=${errors}&last_break_minutes_ago=${lastBreak}`,
      {}
    );
  }

  async getWellnessReminder() {
    return this.get<{ type: string; message: string }>('/api/jeeves-eq/wellness-reminder');
  }

  async startPomodoro(userId: string, type: 'work' | 'short_break' | 'long_break') {
    return this.post<{ started: boolean; duration_minutes: number }>(`/api/jeeves-eq/pomodoro/start?user_id=${userId}&session_type=${type}`, {});
  }

  async getPomodoroStatus(userId: string) {
    return this.get<{ active_session: boolean; remaining_minutes: number }>(`/api/jeeves-eq/pomodoro/status/${userId}`);
  }

  async getGrowthMindsetMessage(context: string) {
    return this.post<{ message: string }>(`/api/jeeves-eq/growth-mindset-message?context=${context}`, {});
  }
}

// ============================================================================
// EXPORT SERVICE
// ============================================================================

class ExportServiceAPI extends BaseAPI {
  async exportToPDF(content: string, filename: string, language: string = 'python') {
    return this.post<{ export_id: string; pdf_data: any }>('/api/export/pdf', {
      content, filename, content_type: 'code', language, include_line_numbers: true
    });
  }

  async pushToGitHub(token: string, owner: string, repo: string, filePath: string, content: string, message: string) {
    return this.post<{ success: boolean; commit_sha: string }>('/api/export/github/push', {
      token, repo_owner: owner, repo_name: repo, file_path: filePath, content, commit_message: message
    });
  }

  async pullFromGitHub(token: string, owner: string, repo: string, filePath: string) {
    return this.post<{ success: boolean; content: string }>('/api/export/github/pull', {
      token, repo_owner: owner, repo_name: repo, file_path: filePath
    });
  }

  async createGitHubRepo(token: string, repoName: string, description?: string, isPrivate: boolean = false) {
    return this.post<{ success: boolean; repo_url: string }>('/api/export/github/create-repo', {
      token, repo_name: repoName, description, private: isPrivate
    });
  }

  async listGitHubRepos(token: string) {
    return this.get<{ repos: any[] }>(`/api/export/github/repos?token=${token}`);
  }

  async logAIInteraction(userId: string, type: string, prompt: string, response: string, model: string = 'gpt-4o') {
    return this.post<{ logged: boolean }>('/api/export/log-ai-interaction', {
      user_id: userId, interaction_type: type, prompt, response, model_used: model
    });
  }

  async getAIInteractions(userId: string) {
    return this.get<{ total_interactions: number; by_type: Record<string, number> }>(`/api/export/ai-interactions/${userId}`);
  }
}

// ============================================================================
// LOGSCRAPER SERVICE
// ============================================================================

class LogscraperService extends BaseAPI {
  async logAction(userId: string, actionType: string, actionData: Record<string, any> = {}) {
    return this.post<{ logged: boolean }>('/api/logscraper/log', {
      user_id: userId, action_type: actionType, action_data: actionData
    });
  }

  async getProfile(userId: string) {
    return this.get<any>(`/api/logscraper/profile/${userId}`);
  }

  async getInsights(userId: string) {
    return this.get<{ insights: any[] }>(`/api/logscraper/insights/${userId}`);
  }

  async scrapeSession(userId: string) {
    return this.post<{ stats: any }>(`/api/logscraper/scrape-session?user_id=${userId}`, {});
  }
}

// ============================================================================
// QUIZ BANK SERVICE
// ============================================================================

class QuizBankService extends BaseAPI {
  async getInfo() {
    return this.get<{ total_quizzes: number }>('/api/quiz-bank/info');
  }

  async getQuizzes(category: string, count: number = 10, difficulty?: number) {
    let url = `/api/quiz-bank/${category}?count=${count}`;
    if (difficulty) url += `&difficulty=${difficulty}`;
    return this.get<{ quizzes: any[] }>(url);
  }

  async submitAnswer(quizId: string, selectedAnswer: number) {
    return this.post<{ correct: boolean; explanation: string }>(`/api/quiz-bank/submit?quiz_id=${quizId}&selected_answer=${selectedAnswer}`, {});
  }
}

// ============================================================================
// CORE API SERVICE
// ============================================================================

class CoreAPIService extends BaseAPI {
  async getHealth() {
    return this.get<{ status: string }>('/api/health');
  }

  async getLanguages() {
    return this.get<{ languages: any[] }>('/api/languages');
  }

  async runCode(code: string, language: string) {
    return this.post<{ output: string; error: string | null; execution_time: number }>('/api/run', {
      code, language
    });
  }

  async getTemplates(language: string) {
    return this.get<any>(`/api/templates/${language}`);
  }

  async getAIModes() {
    return this.get<{ modes: any[] }>('/api/ai/modes');
  }

  async generateAI(prompt: string, mode: string, code?: string, language?: string) {
    return this.post<{ response: string }>('/api/ai/generate', {
      prompt, mode, code, language
    });
  }
}

// ============================================================================
// SERVICE INSTANCES
// ============================================================================

export const aiToolkit = new AIToolkitService();
export const readingCurriculum = new ReadingCurriculumService();
export const jeevesEQ = new JeevesEQService();
export const exportAPI = new ExportServiceAPI();
export const logscraper = new LogscraperService();
export const quizBank = new QuizBankService();
export const coreAPI = new CoreAPIService();

// ============================================================================
// UNIFIED API OBJECT
// ============================================================================

const API = {
  core: coreAPI,
  aiToolkit,
  reading: readingCurriculum,
  jeevesEQ,
  export: exportAPI,
  logscraper,
  quizBank,
};

export default API;

// ============================================================================
// BACKWARD COMPATIBILITY UTILITIES
// ============================================================================

/**
 * Parse and normalize API errors
 */
export function parseError(error: any): { message: string; code?: string; retry?: boolean } {
  if (error?.message) {
    return {
      message: error.message,
      code: error.code || 'UNKNOWN',
      retry: error.code === 'NETWORK_ERROR' || error.code === 'TIMEOUT',
    };
  }
  return {
    message: typeof error === 'string' ? error : 'An unknown error occurred',
    code: 'UNKNOWN',
    retry: true,
  };
}

/**
 * Retry a function with exponential backoff
 */
export async function retryWithBackoff<T>(
  fn: () => Promise<T>,
  maxRetries: number = 3,
  baseDelay: number = 1000
): Promise<T> {
  let lastError: any;
  
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      if (attempt < maxRetries) {
        const delay = baseDelay * Math.pow(2, attempt);
        await new Promise(resolve => setTimeout(resolve, delay));
      }
    }
  }
  
  throw lastError;
}

// ============================================================================
// LEGACY API SERVICE (Backward Compatibility)
// ============================================================================

class ApiService {
  static async get(endpoint: string) {
    const response = await coreAPI['get'](endpoint);
    if (!response.success) throw new Error(response.error || 'Request failed');
    return response.data;
  }

  static async post(endpoint: string, body: any) {
    const response = await coreAPI['post'](endpoint, body);
    if (!response.success) throw new Error(response.error || 'Request failed');
    return response.data;
  }

  static async getLanguages() {
    const response = await coreAPI.getLanguages();
    return response.data?.languages || [];
  }

  static async getTemplates(language: string) {
    const response = await coreAPI.getTemplates(language);
    return response.data || {};
  }

  static async executeCode(code: string, language: string) {
    const response = await coreAPI.runCode(code, language);
    return response.data;
  }

  static async getAIModes() {
    const response = await coreAPI.getAIModes();
    return response.data?.modes || [];
  }

  static async generateAI(code: string, language: string, mode: string) {
    const response = await coreAPI.generateAI('', mode, code, language);
    return response.data;
  }

  static async aiAssist(code: string, language: string, mode: string, context?: string) {
    const response = await coreAPI.generateAI(context || '', mode, code, language);
    return response.data;
  }

  static async getFiles() {
    const response = await coreAPI['get']('/api/files');
    return response.data || { files: [] };
  }

  static async saveFile(file: any) {
    const response = await coreAPI['post']('/api/files', file);
    return response.data;
  }

  static async deleteFile(fileId: string) {
    const response = await coreAPI['delete'](`/api/files/${fileId}`);
    return response.data;
  }

  static async analyzeCode(code: string, language: string) {
    const response = await coreAPI['post']('/api/analyze', { code, language });
    return response.data;
  }

  static async addLanguageAddon(addon: { name: string; extension: string; description?: string }) {
    const response = await coreAPI['post']('/api/languages/addon', addon);
    return response.data;
  }

  static async getTooltips() {
    const response = await coreAPI['get']('/api/tooltips');
    return response.data || { tooltips: {} };
  }

  static async getTutorialSteps() {
    const response = await coreAPI['get']('/api/tutorial/steps');
    return response.data || { steps: [] };
  }

  static async getAvailableDocks() {
    const response = await coreAPI['get']('/api/docks/available');
    return response.data || { docks: [] };
  }
}

export { ApiService };
