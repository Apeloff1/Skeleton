/**
 * CodeDock Modal Management Store v12.0
 * 
 * Centralized modal state management using Zustand
 * Replaces 60+ useState hooks for modal visibility
 */

import { create } from 'zustand';

// All modals in the application
export type ModalType = 
  | 'language'
  | 'template'
  | 'files'
  | 'settings'
  | 'ai'
  | 'bible'
  | 'compiler'
  | 'pipeline'
  | 'learning'
  | 'collaboration'
  | 'hub'
  | 'aiSuggestions'
  | 'tutorial'
  | 'aiPipeline'
  | 'curriculum'
  | 'vault'
  | 'advanced'
  | 'codeToApp'
  | 'imagine'
  | 'debugger'
  | 'musicPipeline'
  | 'education'
  | 'jeeves'
  | 'masterclass'
  | 'assetPipeline'
  | 'gameGenres'
  | 'commandPalette'
  | 'multiAgent'
  | 'sota'
  | 'codeIntelligence'
  | 'liveCollab'
  | 'worldEngine'
  | 'narrative'
  | 'logicEngine'
  | 'physicsAcademy'
  | 'mathAcademy'
  | 'csAcademy'
  | 'hybridPipeline'
  | 'sotaExtended'
  | 'immersiveLearning'
  | 'readingCorner'
  | 'jeevesEQ'
  | 'exportGitHub'
  | 'aiInteractionsLog'
  | 'dashboard'
  | 'learningHub'
  | 'immersiveTutor'
  | 'aiGameGenerator'
  | 'languageTrack'
  | 'repeatClass'
  | 'achievements'
  | 'myProgress'
  | 'leaderboard'
  | 'languageRecommend'
  | 'academyContent'
  | 'sortingVault'
  | 'groupChat'
  | 'mathAcademyFull'
  | 'pipelineAgents'
  | 'qualityControl'
  | 'gameFactory'
  | 'jeevesLevel'
  | 'vaultBrowser'
  | 'thermalMonitor'
  | 'performanceArmor'
  | 'resilienceForge'
  | 'knowledgeNexus'
  | 'sentinelArray'
  | 'gameMechanicsNexus'
  | 'quantumFactory'
  | 'gameBuilder'
  | 'deployForge'
  | 'megaDomains'
  | 'hyperscaleDomains'
  | 'jeevesMasterBuild'
  | 'knowledgeDatabases'
  | 'interactiveQuizzes'
  | 'readingLibrary'
  | 'studyPaths'
  | 'dailyChallenges'
  | 'bugfixLibrary'
  | 'codePlayground'
  | 'referenceHub'
  | 'gamification'
  | 'languageAcademy'
  | 'offlineSync'
  | 'rosettaPlayground'
  | 'challengeArena'
  | 'megaAcademy'
  | null;

interface ModalState {
  activeModal: ModalType;
  modalHistory: ModalType[];
  modalData: Record<string, any>;
  
  // Actions
  openModal: (modal: ModalType, data?: any) => void;
  closeModal: () => void;
  closeAllModals: () => void;
  setModalData: (key: string, value: any) => void;
  getModalData: (key: string) => any;
  goBack: () => void;
}

export const useModalStore = create<ModalState>((set, get) => ({
  activeModal: null,
  modalHistory: [],
  modalData: {},
  
  openModal: (modal, data) => set((state) => {
    const newHistory = state.activeModal 
      ? [...state.modalHistory, state.activeModal]
      : state.modalHistory;
    return {
      activeModal: modal,
      modalHistory: newHistory.slice(-5), // Keep last 5 in history
      modalData: data ? { ...state.modalData, [modal || '']: data } : state.modalData,
    };
  }),
  
  closeModal: () => set((state) => ({
    activeModal: null,
    modalHistory: state.modalHistory,
  })),
  
  closeAllModals: () => set({
    activeModal: null,
    modalHistory: [],
    modalData: {},
  }),
  
  setModalData: (key, value) => set((state) => ({
    modalData: { ...state.modalData, [key]: value },
  })),
  
  getModalData: (key) => get().modalData[key],
  
  goBack: () => set((state) => {
    const newHistory = [...state.modalHistory];
    const previousModal = newHistory.pop() || null;
    return {
      activeModal: previousModal,
      modalHistory: newHistory,
    };
  }),
}));

// Selector hooks for common patterns
export const useActiveModal = () => useModalStore((state) => state.activeModal);
export const useModalActions = () => useModalStore((state) => ({
  openModal: state.openModal,
  closeModal: state.closeModal,
  closeAllModals: state.closeAllModals,
  goBack: state.goBack,
}));

// ─────────────────────────────────────────────────────────────────────
// 2026-02 — MODAL_TO_ROUTE: when a modal has a dedicated native route,
// callers can use openModalSmart() (utils/openModalFromRoute.ts) to
// router.push() the route instead of mounting the legacy modal tree.
// This is the path to dropping the 40+ modal imports from hub.tsx.
// Every entry here MUST have a backing /app/<route>.tsx (validated by
// scripts/route_coverage_check.py).
// ─────────────────────────────────────────────────────────────────────
export const MODAL_TO_ROUTE: Partial<Record<NonNullable<ModalType>, string>> = {
  // Heavy modals that are also native routes — prefer the route.
  bible:              '/bible',
  compiler:           '/compiler',
  vault:              '/vault',
  masterclass:        '/masterclass',
  jeeves:             '/jeeves',
  jeevesEQ:           '/jeeves-eq',
  jeevesLevel:        '/jeeves-level',
  education:          '/education',
  megaAcademy:        '/mega-academy',
  mathAcademy:        '/math-academy',
  mathAcademyFull:    '/math-academy-full',
  physicsAcademy:     '/physics-academy',
  csAcademy:          '/cs-academy',
  languageAcademy:    '/language-academy',
  languageTrack:      '/language-track',
  languageRecommend:  '/lang-recommend',
  aiPipeline:         '/ai-pipeline',
  aiSuggestions:      '/ai-suggestions',
  aiInteractionsLog:  '/ai-interactions',
  aiGameGenerator:    '/ai-game-generator',
  sota:               '/sota',
  sotaExtended:       '/sota-extended',
  challengeArena:     '/challenges',
  dailyChallenges:    '/daily-challenges',
  codeToApp:          '/code-to-app',
  knowledgeDatabases: '/knowledge-databases',
  thermalMonitor:     '/thermal',
  referenceHub:       '/reference',
  immersiveTutor:     '/immersive-tutor',
  immersiveLearning:  '/immersive-learning',
  multiAgent:         '/multi-agent',
  gameFactory:        '/game-factory',
  advanced:           '/advanced',
  bugfixLibrary:      '/bugfix-library',
  collaboration:      '/collaboration',
  gamification:       '/gamification',
  groupChat:          '/group-chat',
  hybridPipeline:     '/hybrid-pipeline',
  interactiveQuizzes: '/interactive-quizzes',
  offlineSync:        '/offline-sync',
  myProgress:         '/progress',
  readingCorner:      '/reading-corner',
  rosettaPlayground:  '/rosetta-playground',
  studyPaths:         '/study-paths',
  learningHub:        '/learning-hub',
  achievements:       '/achievements',
  leaderboard:        '/leaderboard',
  curriculum:         '/curriculum',
  dashboard:          '/dashboard',
  liveCollab:         '/collab',
  debugger:           '/debugger',
  codeIntelligence:   '/intelligence',
  codePlayground:     '/playground',
  imagine:            '/imagine',
  musicPipeline:      '/music',
  assetPipeline:      '/assets',
  hub:                '/hub',
  // P3 \u2014 Dynamic feature-flags admin/dev screen
  // (named "settings.feature_flags" in some call-sites, expose at /feature-flags).
};

// Convenience: a friendly route table for the in-app router.
export const FEATURE_FLAGS_ROUTE = '/feature-flags';

export function getRouteForModal(modal: ModalType): string | undefined {
  return modal ? MODAL_TO_ROUTE[modal as NonNullable<ModalType>] : undefined;
}

export default useModalStore;
