/**
 * CodeDock Global State Management v11.9
 * 
 * Zustand-based centralized state management with persistence
 * Replaces scattered useState calls for better structural integrity
 */

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { SupportedLanguage } from '../i18n';

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

export interface Language {
  key: string;
  name: string;
  extension: string;
  display_name?: string;
  icon?: string;
}

export interface File {
  id: string;
  name: string;
  content: string;
  language: string;
  created_at: string;
  updated_at: string;
}

export interface UserProfile {
  id: string;
  username: string;
  email?: string;
  avatar?: string;
  level: number;
  xp: number;
  streak: number;
  achievements: string[];
  preferences: UserPreferences;
}

export interface UserPreferences {
  theme: 'light' | 'dark' | 'system';
  language: SupportedLanguage;
  editorFontSize: number;
  autoSave: boolean;
  soundEffects: boolean;
  hapticFeedback: boolean;
  notifications: boolean;
}

export interface EditorState {
  code: string;
  language: Language | null;
  output: string;
  isRunning: boolean;
  hasChanges: boolean;
  cursorPosition: { line: number; column: number };
}

export interface AIState {
  isGenerating: boolean;
  lastPrompt: string;
  lastResponse: string;
  conversationHistory: Array<{ role: 'user' | 'assistant'; content: string }>;
  activeMode: string;
}

export interface LearningState {
  currentTrack: string | null;
  currentModule: string | null;
  progress: Record<string, number>;
  completedModules: string[];
  bookmarks: string[];
  studyTime: number;
}

export interface EmotionalState {
  currentEmotion: string;
  intensity: number;
  lastDetected: string | null;
  pomodoroActive: boolean;
  pomodoroType: 'work' | 'short_break' | 'long_break';
  pomodoroTimeRemaining: number;
  sessionsCompleted: number;
}

// ============================================================================
// STORE SLICES
// ============================================================================

interface AppState {
  // User
  user: UserProfile | null;
  isAuthenticated: boolean;
  setUser: (user: UserProfile | null) => void;
  updatePreferences: (prefs: Partial<UserPreferences>) => void;
  
  // Editor
  editor: EditorState;
  setCode: (code: string) => void;
  setLanguage: (language: Language | null) => void;
  setOutput: (output: string) => void;
  setIsRunning: (isRunning: boolean) => void;
  resetEditor: () => void;
  
  // AI
  ai: AIState;
  setAIGenerating: (isGenerating: boolean) => void;
  addToConversation: (message: { role: 'user' | 'assistant'; content: string }) => void;
  clearConversation: () => void;
  setAIMode: (mode: string) => void;
  
  // Learning
  learning: LearningState;
  setCurrentTrack: (track: string | null) => void;
  setCurrentModule: (module: string | null) => void;
  updateProgress: (moduleId: string, progress: number) => void;
  completeModule: (moduleId: string) => void;
  toggleBookmark: (moduleId: string) => void;
  addStudyTime: (minutes: number) => void;
  
  // Emotional/Wellness
  emotional: EmotionalState;
  setEmotion: (emotion: string, intensity: number) => void;
  startPomodoro: (type: 'work' | 'short_break' | 'long_break') => void;
  stopPomodoro: () => void;
  tickPomodoro: () => void;
  completePomodoro: () => void;
  
  // UI State
  activeModal: string | null;
  setActiveModal: (modal: string | null) => void;
  
  // Theme
  theme: 'light' | 'dark';
  toggleTheme: () => void;
  
  // App Language
  appLanguage: SupportedLanguage;
  setAppLanguage: (lang: SupportedLanguage) => void;
}

// ============================================================================
// DEFAULT VALUES
// ============================================================================

const defaultEditorState: EditorState = {
  code: '# Welcome to CodeDock Quantum!\n# Start coding here...\n\nprint("Hello, World!")\n',
  language: null,
  output: '',
  isRunning: false,
  hasChanges: false,
  cursorPosition: { line: 1, column: 1 },
};

const defaultAIState: AIState = {
  isGenerating: false,
  lastPrompt: '',
  lastResponse: '',
  conversationHistory: [],
  activeMode: 'assistant',
};

const defaultLearningState: LearningState = {
  currentTrack: null,
  currentModule: null,
  progress: {},
  completedModules: [],
  bookmarks: [],
  studyTime: 0,
};

const defaultEmotionalState: EmotionalState = {
  currentEmotion: 'neutral',
  intensity: 0.5,
  lastDetected: null,
  pomodoroActive: false,
  pomodoroType: 'work',
  pomodoroTimeRemaining: 25 * 60,
  sessionsCompleted: 0,
};

const defaultPreferences: UserPreferences = {
  theme: 'dark',
  language: 'en',
  editorFontSize: 14,
  autoSave: true,
  soundEffects: true,
  hapticFeedback: true,
  notifications: true,
};

// ============================================================================
// STORE CREATION
// ============================================================================

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      // User State
      user: null,
      isAuthenticated: false,
      setUser: (user) => set({ user, isAuthenticated: !!user }),
      updatePreferences: (prefs) => set((state) => ({
        user: state.user ? {
          ...state.user,
          preferences: { ...state.user.preferences, ...prefs }
        } : null
      })),
      
      // Editor State
      editor: defaultEditorState,
      setCode: (code) => set((state) => ({
        editor: { ...state.editor, code, hasChanges: true }
      })),
      setLanguage: (language) => set((state) => ({
        editor: { ...state.editor, language }
      })),
      setOutput: (output) => set((state) => ({
        editor: { ...state.editor, output }
      })),
      setIsRunning: (isRunning) => set((state) => ({
        editor: { ...state.editor, isRunning }
      })),
      resetEditor: () => set({ editor: defaultEditorState }),
      
      // AI State
      ai: defaultAIState,
      setAIGenerating: (isGenerating) => set((state) => ({
        ai: { ...state.ai, isGenerating }
      })),
      addToConversation: (message) => set((state) => ({
        ai: {
          ...state.ai,
          conversationHistory: [...state.ai.conversationHistory, message].slice(-20) // Keep last 20
        }
      })),
      clearConversation: () => set((state) => ({
        ai: { ...state.ai, conversationHistory: [] }
      })),
      setAIMode: (mode) => set((state) => ({
        ai: { ...state.ai, activeMode: mode }
      })),
      
      // Learning State
      learning: defaultLearningState,
      setCurrentTrack: (track) => set((state) => ({
        learning: { ...state.learning, currentTrack: track }
      })),
      setCurrentModule: (module) => set((state) => ({
        learning: { ...state.learning, currentModule: module }
      })),
      updateProgress: (moduleId, progress) => set((state) => ({
        learning: {
          ...state.learning,
          progress: { ...state.learning.progress, [moduleId]: progress }
        }
      })),
      completeModule: (moduleId) => set((state) => ({
        learning: {
          ...state.learning,
          completedModules: state.learning.completedModules.includes(moduleId)
            ? state.learning.completedModules
            : [...state.learning.completedModules, moduleId],
          progress: { ...state.learning.progress, [moduleId]: 100 }
        }
      })),
      toggleBookmark: (moduleId) => set((state) => ({
        learning: {
          ...state.learning,
          bookmarks: state.learning.bookmarks.includes(moduleId)
            ? state.learning.bookmarks.filter(id => id !== moduleId)
            : [...state.learning.bookmarks, moduleId]
        }
      })),
      addStudyTime: (minutes) => set((state) => ({
        learning: { ...state.learning, studyTime: state.learning.studyTime + minutes }
      })),
      
      // Emotional State
      emotional: defaultEmotionalState,
      setEmotion: (emotion, intensity) => set((state) => ({
        emotional: {
          ...state.emotional,
          currentEmotion: emotion,
          intensity,
          lastDetected: new Date().toISOString()
        }
      })),
      startPomodoro: (type) => {
        const durations = { work: 25 * 60, short_break: 5 * 60, long_break: 15 * 60 };
        set((state) => ({
          emotional: {
            ...state.emotional,
            pomodoroActive: true,
            pomodoroType: type,
            pomodoroTimeRemaining: durations[type]
          }
        }));
      },
      stopPomodoro: () => set((state) => ({
        emotional: { ...state.emotional, pomodoroActive: false }
      })),
      tickPomodoro: () => set((state) => ({
        emotional: {
          ...state.emotional,
          pomodoroTimeRemaining: Math.max(0, state.emotional.pomodoroTimeRemaining - 1)
        }
      })),
      completePomodoro: () => set((state) => ({
        emotional: {
          ...state.emotional,
          pomodoroActive: false,
          sessionsCompleted: state.emotional.pomodoroType === 'work'
            ? state.emotional.sessionsCompleted + 1
            : state.emotional.sessionsCompleted
        }
      })),
      
      // UI State
      activeModal: null,
      setActiveModal: (modal) => set({ activeModal: modal }),
      
      // Theme
      theme: 'dark',
      toggleTheme: () => set((state) => ({
        theme: state.theme === 'dark' ? 'light' : 'dark'
      })),
      
      // App Language
      appLanguage: 'en',
      setAppLanguage: (lang) => set({ appLanguage: lang }),
    }),
    {
      name: 'codedock-storage',
      storage: createJSONStorage(() => AsyncStorage),
      partialize: (state) => ({
        // Only persist these fields
        user: state.user,
        theme: state.theme,
        appLanguage: state.appLanguage,
        learning: {
          progress: state.learning.progress,
          completedModules: state.learning.completedModules,
          bookmarks: state.learning.bookmarks,
          studyTime: state.learning.studyTime,
        },
        emotional: {
          sessionsCompleted: state.emotional.sessionsCompleted,
        },
      }),
    }
  )
);

// ============================================================================
// SELECTOR HOOKS
// ============================================================================

export const useEditor = () => useAppStore((state) => state.editor);
export const useAI = () => useAppStore((state) => state.ai);
export const useLearning = () => useAppStore((state) => state.learning);
export const useEmotional = () => useAppStore((state) => state.emotional);
export const useUser = () => useAppStore((state) => state.user);
export const useTheme = () => useAppStore((state) => state.theme);
export const useAppLanguage = () => useAppStore((state) => state.appLanguage);

// ============================================================================
// ACTION HOOKS
// ============================================================================

export const useEditorActions = () => useAppStore((state) => ({
  setCode: state.setCode,
  setLanguage: state.setLanguage,
  setOutput: state.setOutput,
  setIsRunning: state.setIsRunning,
  resetEditor: state.resetEditor,
}));

export const useAIActions = () => useAppStore((state) => ({
  setAIGenerating: state.setAIGenerating,
  addToConversation: state.addToConversation,
  clearConversation: state.clearConversation,
  setAIMode: state.setAIMode,
}));

export const useLearningActions = () => useAppStore((state) => ({
  setCurrentTrack: state.setCurrentTrack,
  setCurrentModule: state.setCurrentModule,
  updateProgress: state.updateProgress,
  completeModule: state.completeModule,
  toggleBookmark: state.toggleBookmark,
  addStudyTime: state.addStudyTime,
}));

export const useEmotionalActions = () => useAppStore((state) => ({
  setEmotion: state.setEmotion,
  startPomodoro: state.startPomodoro,
  stopPomodoro: state.stopPomodoro,
  tickPomodoro: state.tickPomodoro,
  completePomodoro: state.completePomodoro,
}));

export default useAppStore;
