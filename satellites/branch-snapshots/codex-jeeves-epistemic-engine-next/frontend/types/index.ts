// ============================================================================
// CODEDOCK QUANTUM NEXUS - TYPE DEFINITIONS
// Version: 4.2.0 | Refactored Architecture
// ============================================================================

export type Theme = 'dark' | 'light';

export type LanguageType = 'builtin' | 'addon' | 'custom' | 'expansion';

export interface Language {
  key: string;
  name: string;
  display_name: string;
  extension: string;
  icon: string;
  color: string;
  executable: boolean;
  type: LanguageType;
  tier: number;
  version?: string;
  coming_soon?: boolean;
}

export interface Template {
  key: string;
  name: string;
  code: string;
  description?: string;
  complexity?: 'trivial' | 'simple' | 'moderate' | 'complex' | 'advanced';
}

export interface CodeFile {
  id: string;
  name: string;
  language: string;
  code: string;
  created_at: string;
  updated_at: string;
}

export interface ExecutionResult {
  execution_id: string;
  result: {
    stdout: string;
    stderr: string;
    exit_code: number;
    execution_time: number;
  };
  metrics?: {
    lines_of_code: number;
    characters: number;
    complexity_estimate: string;
  };
}

export interface AIMode {
  key: string;
  name: string;
  description: string;
  icon: string;
  color: string;
  prompt_hint?: string;
}

export interface AIResponse {
  mode: string;
  suggestion: string;
  code_blocks: Array<{ language: string; code: string }>;
  confidence: number;
  model: string;
}

export interface TutorialStep {
  key: string;
  order: number;
  title: string;
  description: string;
  content: string;
  tips?: string[];
  highlight_element?: string;
  next_step?: string;
  celebration?: boolean;
}

export interface Tooltip {
  id: string;
  title: string;
  description: string;
  shortcut?: string;
}

export interface AnalysisResult {
  complexity: string;
  lines: number;
  issues: string[];
  suggestions: string[];
  score: number;
}

// Bible Types
export type BibleTier = 'beginner' | 'foundation' | 'intermediate' | 'advanced' | 'expert' | 'godtier';

export interface BibleSection {
  title: string;
  content: string;
  code?: string;
  language?: string;
  tips?: string[];
  warning?: string;
}

export interface BibleExercise {
  id: string;
  title: string;
  description: string;
  starterCode: string;
  language: string;
  hints: string[];
  solution?: string;
  testCases?: Array<{ input: string; expected: string }>;
}

export interface BibleChapter {
  id: string;
  day: number;
  tier: BibleTier;
  title: string;
  subtitle: string;
  icon: string;
  color: string;
  sections: BibleSection[];
  exercises?: BibleExercise[];
  unlocked: boolean;
  estimatedTime?: string;
}

export interface BibleProgress {
  completedChapters: Record<string, boolean>;
  bookmarks: string[];
  currentChapter?: string;
  currentSection?: number;
  exerciseResults: Record<string, boolean>;
  totalTimeSpent: number;
  streak: number;
  lastAccessed?: string;
}

// Error Types
export type ErrorType = 'network' | 'timeout' | 'server' | 'validation' | 'unknown';

export interface AppError {
  type: ErrorType;
  message: string;
  code?: number;
  retry?: boolean;
}

// Config Types
export interface AppConfig {
  API_TIMEOUT: number;
  MAX_RETRIES: number;
  RETRY_DELAY: number;
  CACHE_TTL: number;
  ANIMATION_DURATION: number;
  TOAST_DURATION: number;
}

export type ConnectionStatus = 'connected' | 'disconnected' | 'reconnecting';
