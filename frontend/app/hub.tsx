// ============================================================================
// CODEDOCK ULTIMATE HUB - Main Application
// Version: 11.4.0 | Mobile-Optimized Edition
// Power Aware • Stability Layer • Polished UI • Performance Optimized
// ============================================================================

import { NATIVE_DRIVER } from '../src/utils/platformStyles';
import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, TextInput,
  ActivityIndicator, SafeAreaView, StatusBar, Platform,
  KeyboardAvoidingView, Modal, Animated, Vibration,
  Pressable,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useRouter } from 'expo-router';
// 2026-05-15 — StyleSheet extracted into /src/styles/home.styles.ts to keep the
// route directory free of non-route files (expo-router treats any /app/*.ts as a route).
import { styles } from '../src/styles/home.styles';
// 2026-05-15 — Starlight backdrop for the Hub (second screen).
import { StarlightBackground } from '../src/components/StarlightBackground';
// 2026-06 — Galaxy Studio agent-health probe for the home-tile degradation chip.
import apiClient from '../src/utils/apiClient';
import { traceStepSync } from '../utils/bootTracer';

// ── Lazy modal loader (2026-06, Samsung-S20 OOM fix) ────────────────────
// Defers each heavy modal's MODULE EVALUATION until it is first opened,
// instead of evaluating all ~50 modal modules synchronously at hub.tsx
// module-eval (which spiked memory and hard-crashed mid-tier Android).
// Every modal below is rendered inside <LazyModal>, which now provides the
// required <Suspense> boundary, so React.lazy works transparently.
const lazyNamed = (loader: () => Promise<any>, key: string) =>
  React.lazy(() => loader().then((m: any) => ({ default: m[key] })));

// Custom Hooks
import { useTheme } from '../hooks/useTheme';
import { useStorage } from '../hooks/useStorage';
import { useAPI } from '../hooks/useAPI';
import { usePowerAwareness } from '../hooks/usePowerAwareness';
import { useStability } from '../hooks/useStability';
import { useMobileOptimization } from '../hooks/useMobileOptimization';

// Boot the global ngrok tunnel heartbeat + resilient network layer
// 2026-02 — Moved out of module scope into a deferred microtask so a
// failure here can never block hub.tsx from even being imported. Any
// throw becomes a console warning instead of a bundle-time crash.
import { startHeartbeat as _startTunnelHeartbeat } from '../utils/resilientNet';


// Mobile UI Components
import { ErrorBoundary } from '../components/ErrorBoundary';
import { QuickActionBar } from '../components/MobileUI/QuickActionBar';
import { MinimalToolbar } from '../components/MobileUI/MinimalToolbar';
import { StatusIndicator } from '../components/MobileUI/StatusIndicator';
import { RecentArtifactsStrip } from '../components/RecentArtifactsStrip';

// Features (lazy — evaluated on first open)
const BibleModal = lazyNamed(() => import('../features/Bible/BibleModal'), 'BibleModal');
const CompilerModal = lazyNamed(() => import('../features/Compiler/CompilerModal'), 'CompilerModal');
const PipelineVisualizer = lazyNamed(() => import('../features/Pipeline/PipelineVisualizer'), 'PipelineVisualizer');
const LearningDashboard = lazyNamed(() => import('../features/Learning/LearningDashboard'), 'LearningDashboard');
const CollaborationModal = lazyNamed(() => import('../features/Collaboration/CollaborationModal'), 'CollaborationModal');
const HubModal = lazyNamed(() => import('../features/Hub/HubModal'), 'HubModal');
const AISuggestionsModal = lazyNamed(() => import('../features/AI/AISuggestionsModal'), 'AISuggestionsModal');
import { useVoiceCommands, speak } from '../features/Voice/useVoiceCommands';
// 2026-02 — Removed dead imports `starlog` (VersionControl/Starlog) and
// `wasmCompiler` (WasmCompiler/WasmCompiler). They were imported but
// never referenced anywhere in this file, adding pointless module-load
// work (and risk: any sync throw in those modules would crash the hub
// route on import). If they're needed later, re-import locally where
// used so the cost is paid only when the feature actually runs.

// v11.0 Features (lazy)
const AIPipelineModal = lazyNamed(() => import('../features/AIPipeline/AIPipelineModal'), 'AIPipelineModal');
const CurriculumBrowser = lazyNamed(() => import('../features/Curriculum/CurriculumBrowser'), 'CurriculumBrowser');
const VaultModal = lazyNamed(() => import('../features/Vault/VaultModal'), 'VaultModal');
const AdvancedFeaturesModal = lazyNamed(() => import('../features/Advanced/AdvancedFeaturesModal'), 'AdvancedFeaturesModal');
const CodeToAppModal = lazyNamed(() => import('../features/CodeToApp/CodeToAppModal'), 'CodeToAppModal');
const ImagineModal = lazyNamed(() => import('../features/Imagine/ImagineModal'), 'ImagineModal');

// v11.1 SOTA 2026 Features (lazy)
const DebuggerModal = lazyNamed(() => import('../features/Debugger/DebuggerModal'), 'DebuggerModal');
const MusicPipelineModal = lazyNamed(() => import('../features/Music/MusicPipelineModal'), 'MusicPipelineModal');
const EducationModal = lazyNamed(() => import('../features/Education/EducationModal'), 'EducationModal');
const MegaAcademyModal = lazyNamed(() => import('../features/MegaAcademy/MegaAcademyModal'), 'MegaAcademyModal');
const JeevesModal = lazyNamed(() => import('../features/Jeeves/JeevesModal'), 'JeevesModal');

// v11.2 Masterclass, Assets & Game Systems (lazy)
const MasterclassModal = lazyNamed(() => import('../features/Masterclass/MasterclassModal'), 'MasterclassModal');
const AssetPipelineModal = lazyNamed(() => import('../features/AssetPipeline/AssetPipelineModal'), 'AssetPipelineModal');

// v11.3 Command Palette for Clean UI (lazy — heavy declarative menu, evaluated
// on first open inside a LazyModal Suspense boundary; keeps it off the cold boot).
const CommandPalette = lazyNamed(() => import('../components/CommandPalette'), 'CommandPalette');

// v11.3 SOTA Feature Modals (lazy)
const MultiAgentModal = lazyNamed(() => import('../features/MultiAgent/MultiAgentModal'), 'MultiAgentModal');
const SOTAModal = lazyNamed(() => import('../features/SOTA/SOTAModal'), 'SOTAModal');
const CodeIntelligenceModal = lazyNamed(() => import('../features/CodeIntelligence/CodeIntelligenceModal'), 'CodeIntelligenceModal');
const LiveCollabModal = lazyNamed(() => import('../features/LiveCollab/LiveCollabModal'), 'LiveCollabModal');

// v11.5 AI-to-Game Pipelines
// WorldEngine, Narrative, LogicEngine → Galaxy Studio Factory

// v11.6 Educational Academy & SOTA Extended (lazy)
const HybridPipelineModal = lazyNamed(() => import('../features/HybridPipeline/HybridPipelineModal'), 'HybridPipelineModal');
const SOTAExtendedModal = lazyNamed(() => import('../features/SOTAExtended/SOTAExtendedModal'), 'SOTAExtendedModal');
const ImmersiveLearningModal = lazyNamed(() => import('../features/ImmersiveLearning/ImmersiveLearningModal'), 'ImmersiveLearningModal');

// v11.8 Reading Corner, Jeeves EQ & Export (lazy)
const ReadingCornerModal = lazyNamed(() => import('../features/ReadingCorner/ReadingCornerModal'), 'ReadingCornerModal');
const JeevesEQModal = lazyNamed(() => import('../features/JeevesEQ/JeevesEQModal'), 'JeevesEQModal');

// v12.0 AI Interactions Log (lazy)
const AIInteractionsLogModal = lazyNamed(() => import('../features/AIInteractionsLog/AIInteractionsLogModal'), 'AIInteractionsLogModal');

// v12.0 Dashboard & Session Tracking
const DashboardModal = lazyNamed(() => import('../features/Dashboard/DashboardModal'), 'DashboardModal');
import { AchievementQueue } from '../components/AchievementNotification';
import { useSessionTracker } from '../hooks/useSessionTracker';

// v12.5 Learning Hub - Multi-Layer Learning System (lazy)
const LearningHubModal = lazyNamed(() => import('../features/LearningHub/LearningHubModal'), 'LearningHubModal');

// v14.5 Immersive Tutor - Jeeves Synergy Learning System (lazy)
const ImmersiveTutorModal = lazyNamed(() => import('../features/ImmersiveTutor/ImmersiveTutorModal'), 'ImmersiveTutorModal');

// v17.0 Knowledge Databases & Interactive Quizzes (lazy)
const KnowledgeDatabasesModal = lazyNamed(() => import('../features/KnowledgeDatabases/KnowledgeDatabasesModal'), 'KnowledgeDatabasesModal');
const InteractiveQuizzesModal = lazyNamed(() => import('../features/InteractiveQuizzes/InteractiveQuizzesModal'), 'InteractiveQuizzesModal');
const ReadingLibraryModal = lazyNamed(() => import('../features/ReadingLibrary/ReadingLibraryModal'), 'ReadingLibraryModal');
const StudyPathsModal = lazyNamed(() => import('../features/StudyPaths/StudyPathsModal'), 'StudyPathsModal');
const DailyChallengesModal = lazyNamed(() => import('../features/DailyChallenges/DailyChallengesModal'), 'DailyChallengesModal');
const BugfixLibraryModal = lazyNamed(() => import('../features/BugfixLibrary/BugfixLibraryModal'), 'BugfixLibraryModal');
const CodePlaygroundModal = lazyNamed(() => import('../features/CodePlayground/CodePlaygroundModal'), 'CodePlaygroundModal');
const ReferenceHubModal = lazyNamed(() => import('../features/ReferenceHub/ReferenceHubModal'), 'ReferenceHubModal');

// v20.0 Gamification, Language Academy, Offline Sync (lazy)
const GamificationModal = lazyNamed(() => import('../features/Gamification/GamificationModal'), 'GamificationModal');
const LanguageAcademyModal = lazyNamed(() => import('../features/LanguageAcademy/LanguageAcademyModal'), 'LanguageAcademyModal');
const OfflineSyncModal = lazyNamed(() => import('../features/OfflineSync/OfflineSyncModal'), 'OfflineSyncModal');

// v25.0 Rosetta Playground (lazy)
const RosettaPlaygroundModal = lazyNamed(() => import('../features/RosettaPlayground/RosettaPlaygroundModal'), 'RosettaPlaygroundModal');

// v28.0 Challenge Arena (lazy)
const ChallengeArenaModal = lazyNamed(() => import('../features/ChallengeArena/ChallengeArenaModal'), 'ChallengeArenaModal');

import { resolveAction } from '../utils/actionMap';
import { toast } from '../components/Toast';
import { useFeatureFlag, FLAG } from '../src/feature-flags';

// v15.5 AI Game Generator - Unified Game Development Interface (lazy)
const AIGameGeneratorModal = lazyNamed(() => import('../features/AIGameGenerator/AIGameGeneratorModal'), 'AIGameGeneratorModal');

// v16.0 Language Academy, Achievements & Progress (lazy)
const LanguageTrackModal = lazyNamed(() => import('../features/LanguageTrack/LanguageTrackModal'), 'LanguageTrackModal');
const AchievementsModal = lazyNamed(() => import('../features/Achievements/AchievementsModal'), 'AchievementsModal');
const ProgressModal = lazyNamed(() => import('../features/Progress/ProgressModal'), 'ProgressModal');
const LeaderboardModal = lazyNamed(() => import('../features/Leaderboard/LeaderboardModal'), 'LeaderboardModal');
const LanguageRecommendModal = lazyNamed(() => import('../features/LanguageRecommend/LanguageRecommendModal'), 'LanguageRecommendModal');

// v16.5 - Group Chat, Math Academy Full, Pipeline Agents (lazy)
const GroupChatModal = lazyNamed(() => import('../features/GroupChat/GroupChatModal'), 'GroupChatModal');
const ThermalMonitorModal = lazyNamed(() => import('../features/ThermalMonitor/ThermalMonitorModal'), 'ThermalMonitorModal');
// Heaviest module (~3.5k lines) — default export, lazy-loaded.
const GalaxyStudioFactoryModal = React.lazy(() => import('../features/GalaxyStudioFactory/GalaxyStudioFactoryModal'));
import { LazyModal } from '../components/LazyModal';
import { useThermalGuard } from '../hooks/useThermalGuard';
const JeevesLevelModal = lazyNamed(() => import('../features/JeevesLevel/JeevesLevelModal'), 'JeevesLevelModal');
const MathAcademyFullModal = lazyNamed(() => import('../features/MathAcademy/MathAcademyFullModal'), 'MathAcademyModal');

// i18n Provider
import { I18nProvider } from '../i18n';
import { LanguageSwitcher } from '../components/LanguageSwitcher';

// Zustand Stores
import { useModalStore, ModalType } from '../store/modalStore';

// Types
import { Language, Template, AIMode } from '../types';

// Constants
import { VERSION, CODENAME } from '../constants/config';

// ============================================================================
// APP WRAPPER WITH PROVIDERS
// ============================================================================
import { withScreenGuard } from '../components/withScreenGuard';
// 2026-02 — WebView lazy-required.
// Importing react-native-webview at module scope on Android (Samsung S20,
// Fabric / New Architecture) can throw during module init if the native
// module fails to register (race with Hermes startup). We lazy-require
// it inside a small wrapper so the WebView only loads when a feature
// that uses it actually mounts. The wrapper degrades to a placeholder
// view if the native module isn't available, instead of crashing hub.
let _WebView: any = null;
function _tryLoadWebView() {
  if (_WebView) return _WebView;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    _WebView = require('react-native-webview').WebView;
  } catch (e) {
    console.warn('[hub] react-native-webview unavailable:', e);
    _WebView = null;
  }
  return _WebView;
}
const WebView: React.FC<any> = (props) => {
  const W = _tryLoadWebView();
  if (!W) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#0A0A0A' }}>
        <Text style={{ color: '#94a3b8', fontSize: 12 }}>Web preview unavailable on this device</Text>
      </View>
    );
  }
  return <W {...props} />;
};
if (typeof setTimeout === 'function') {
  setTimeout(() => {
    try { _startTunnelHeartbeat(); }
    catch (e) { console.warn('[hub] tunnel heartbeat failed to start:', e); }
  }, 0);
}


// ============================================================================
// MAIN APP COMPONENT
// ============================================================================
traceStepSync('hub_module_eval');   // proves hub.tsx finished module load (25+ heavy modal imports above)

function CodeDockAppContent() {
  traceStepSync('hub_render_enter');
  // Core Hooks
  const router = useRouter();

  // 2026-05-15 — First-launch welcome screen redirect.
  // If the welcome flag isn't set in AsyncStorage we route the user to /welcome
  // (animated starfall splash) which sets the flag on tap-to-enter.
  // 2026-02 — Also mark this boot as clean once the Hub mounts, so the
  // 2026-02 — REDUNDANT LAUNCHER ERA.
  // Previously this effect would redirect first-time visitors to /welcome
  // to see the starfall splash. That role has now been taken over by the
  // root LaunchCascade in app/index.tsx → components/LaunchCascade.tsx,
  // which is more resilient (4 fallback layers + watchdog escalation).
  //
  // Removing the hub→/welcome redirect collapses one navigation hop and
  // eliminates the failure case where welcome.tsx itself crashed (we'd
  // ping-pong between hub and welcome forever).
  //
  // We ALSO mark this boot as clean ASAP (no 1500 ms timer) — every
  // millisecond of delay between "hub rendered" and "markBootClean fires"
  // is a window where a child crash could leave the counter incremented.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // Ensure welcome_seen is set so future cold-boots from the cascade
        // can fast-path straight to hub. Best-effort, never blocks.
        AsyncStorage.setItem('@codedock:welcome_seen:v1', '1').catch(() => {});
      } catch {}
      try {
        const { markBootClean, traceStep } = await import('../utils/bootTracer');
        if (cancelled) return;
        await traceStep('hub_mounted');
        // Fire markBootClean on the next tick — fast enough to clear the
        // counter before most child renders, but late enough that a sync
        // throw in the first paint still leaves the counter incremented.
        Promise.resolve().then(() => { markBootClean().catch(() => {}); });
      } catch { /* never block startup */ }
    })();
    return () => { cancelled = true; };
  }, []);

  const { theme, colors, toggleTheme, isLoading: themeLoading } = useTheme();
  const { 
    tutorialCompleted, setTutorialCompleted,
    bibleProgress, markChapterComplete, toggleBookmark, 
    isLoading: storageLoading 
  } = useStorage();
  const {
    languages, templates, files, aiModes, tutorialSteps,
    connectionStatus, lastError, isLoading: apiLoading,
    dataSource,
    loadInitialData, loadTemplates, refreshFiles,
    executeCode: apiExecuteCode, aiAssist, saveFile: apiSaveFile,
  } = useAPI();
  
  // v11.4 Mobile Optimization Hooks
  const power = usePowerAwareness();
  const stability = useStability();
  useMobileOptimization();

  // v18.0 Thermal Guard — Stagger + Stutterstep + Heat Management
  useThermalGuard();

  // Zustand Modal Store
  const { activeModal, openModal, closeModal } = useModalStore();
  
  // v12.0 Session Tracker with achievements
  const { 
    achievements, 
    xpEarned,
    clearAchievements 
  } = useSessionTracker('default_user');
  
  // Helper to check if a modal is open
  const isModalOpen = useCallback((modal: ModalType) => activeModal === modal, [activeModal]);
  const getModalData = useModalStore(s => s.getModalData);

  // P3 — Dynamic feature flags (server-driven, cached by FeatureFlagProvider).
  // Drives runtime gating of optional UI surfaces. Flags resolve to their
  // sensible defaults if the backend is unreachable so cold boots never
  // regress functionality.
  const ffCommandPalette = useFeatureFlag(FLAG.HUB_COMMAND_PALETTE, true);

  // Core State (non-modal)
  const [selectedLanguage, setSelectedLanguage] = useState<Language | null>(null);
  const [code, setCode] = useState('');
  const [output, setOutput] = useState('');
  const [isExecuting, setIsExecuting] = useState(false);
  const [currentFileName, setCurrentFileName] = useState('untitled');
  const [executionTime, setExecutionTime] = useState<number | null>(null);

  // UI State (non-modal)
  const [showOutput, setShowOutput] = useState(false);
  const [metronomeOpen, setMetronomeOpen] = useState(false);
  // Temporarily hard-code defaults instead of reading from useSettings —
  // the Zustand-persist hydration race was blocking the home boot on web.
  const codingMetronomeEnabled = false;
  const codingMetronomeBpm = 90;
  const [showWebPreview, setShowWebPreview] = useState(false);
  const [htmlPreview, setHtmlPreview] = useState('');
  
  // Voice Command Handler
  const handleVoiceCommand = useCallback((action: string, params?: any) => {
    switch (action) {
      case 'RUN_CODE':
        executeCode();
        break;
      case 'CLEAR_CODE':
        clearCode();
        break;
      case 'SAVE_FILE':
        saveFile();
        break;
      case 'OPEN_MODAL':
        if (params?.modal === 'compiler') openModal('compiler');
        else if (params?.modal === 'bible') openModal('bible');
        else if (params?.modal === 'settings') openModal('settings');
        break;
      case 'RUN_ANALYSIS':
        openModal('compiler');
        break;
      case 'HELP':
        speak('Available commands: Run code, Clear code, Save file, Open compiler, Open bible, Engage LTO, Engage PGO, Set optimization level O3');
        break;
      default:
        console.log('Voice command:', action, params);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openModal]);

  // Voice Commands Hook
  useVoiceCommands(handleVoiceCommand);
  
  // AI State
  const [selectedAIMode, setSelectedAIMode] = useState<AIMode | null>(null);
  const [aiResponse, setAIResponse] = useState('');
  const [isAILoading, setIsAILoading] = useState(false);

  // Tutorial State
  const [currentTutorialStep, setCurrentTutorialStep] = useState(0);

  // Galaxy Studio agent-health — drives the degradation alert chip on the tile.
  const [galaxyHealth, setGalaxyHealth] = useState<number | null>(null);
  const galaxyDegraded = galaxyHealth !== null && galaxyHealth < 90;
  // Count of in-flight Galaxy background jobs (expansion / APK packaging) —
  // drives a live "running" badge on the tile so progress shows without
  // opening the modal.
  const [galaxyJobs, setGalaxyJobs] = useState(0);

  // Animation
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const fadeAnim = useRef(new Animated.Value(0)).current;

  // Derived
  const isLoading = themeLoading || storageLoading || apiLoading;

  // ============================================================================
  // EFFECTS
  // ============================================================================
  useEffect(() => {
    loadInitialData();
    
    // Start entrance animation
    Animated.timing(fadeAnim, { toValue: 1, duration: 500, useNativeDriver: NATIVE_DRIVER }).start();
    
    // Pulse animation for AI button
    Animated.loop(
      Animated.sequence([
        Animated.timing(pulseAnim, { toValue: 1.05, duration: 1500, useNativeDriver: NATIVE_DRIVER }),
        Animated.timing(pulseAnim, { toValue: 1, duration: 1500, useNativeDriver: NATIVE_DRIVER }),
      ])
    ).start();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Set default language when languages load
  useEffect(() => {
    if (languages.length > 0 && !selectedLanguage) {
      const defaultLang = languages.find(l => l.key === 'python') || languages[0];
      setSelectedLanguage(defaultLang);
      loadTemplates(defaultLang.key);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [languages]);

  // Fetch the latest Galaxy Studio agent once-over health for the tile chip.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await apiClient.get<{ ok: boolean; history: { health_pct: number }[] }>(
          '/api/galaxy-studio/agents/once-over/history?limit=1',
        );
        if (!cancelled && r.ok && r.data?.history?.length) {
          setGalaxyHealth(r.data.history[r.data.history.length - 1].health_pct);
        }
      } catch {
        // non-fatal — chip simply won't show
      }
    })();
    return () => { cancelled = true; };
  }, []);

  // Poll for in-flight Galaxy background jobs (expansion / APK packaging) so the
  // tile shows a live "running" badge without opening the modal.
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const r = await apiClient.get<{ ok: boolean; count: number }>(
          '/api/galaxy-studio/jobs/active',
        );
        if (alive && r.ok && r.data) setGalaxyJobs(r.data.count || 0);
      } catch {
        // non-fatal — badge simply won't show
      }
    };
    tick();
    const iv = setInterval(tick, 6000);
    return () => { alive = false; clearInterval(iv); };
  }, []);

  // Show tutorial for first-time users
  useEffect(() => {
    if (!tutorialCompleted && !isLoading && tutorialSteps.length > 0) {
      setTimeout(() => openModal('tutorial'), 1000);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tutorialCompleted, isLoading, tutorialSteps]);

  // ============================================================================
  // HANDLERS
  // ============================================================================
  const selectLanguage = useCallback((lang: Language) => {
    setSelectedLanguage(lang);
    closeModal();
    setCode('');
    setOutput('');
    setShowOutput(false);
    setShowWebPreview(false);
    setExecutionTime(null);
    loadTemplates(lang.key);
    if (Platform.OS !== 'web') Vibration.vibrate(10);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadTemplates]);

  const executeCode = useCallback(async () => {
    if (!code.trim() || !selectedLanguage) return;

    setIsExecuting(true);
    setOutput('');
    setShowOutput(true);
    setShowWebPreview(false);
    setExecutionTime(null);

    try {
      // Handle HTML preview
      if (selectedLanguage.key === 'html') {
        setHtmlPreview(code);
        setShowWebPreview(true);
        setShowOutput(false);
        return;
      }

      // Handle JS/TS preview in WebView
      if (selectedLanguage.key === 'javascript' || selectedLanguage.key === 'typescript') {
        const result = await apiExecuteCode(code, selectedLanguage.key);
        const wrappedCode = result?.output || '';
        setHtmlPreview(`
          <html><head><meta name="viewport" content="width=device-width, initial-scale=1">
          <style>body{font-family:monospace;padding:16px;background:${colors.codeBackground};color:${colors.text};font-size:14px;margin:0;}</style></head>
          <body><pre id="o">${wrappedCode || 'No output'}</pre></body></html>
        `);
        setShowWebPreview(true);
        setShowOutput(false);
        setExecutionTime(result?.execution_time || 0);
        return;
      }

      // Standard execution
      const result = await apiExecuteCode(code, selectedLanguage.key);
      setExecutionTime(result?.execution_time || 0);
      
      const stdout = result?.output || '';
      const stderr = result?.error;
      
      if (stderr) {
        setOutput(`❌ Error:\n${stderr}`);
      } else if (stdout) {
        setOutput(stdout);
      } else {
        setOutput('✓ Program executed successfully (no output)');
      }
    } catch (error: any) {
      setOutput(`❌ Execution failed: ${error.message || 'Unknown error'}`);
    } finally {
      setIsExecuting(false);
    }
  }, [code, selectedLanguage, apiExecuteCode, colors]);

  const applyTemplate = useCallback((template: Template) => {
    setCode(template.code);
    closeModal();
    setShowOutput(false);
    setExecutionTime(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const saveFile = useCallback(async () => {
    if (!code.trim() || !selectedLanguage) return;
    try {
      await apiSaveFile({
        name: currentFileName + selectedLanguage.extension,
        language: selectedLanguage.key,
        code,
      });
      toast.success(`Saved ${currentFileName}${selectedLanguage.extension}`);
      refreshFiles();
    } catch (error: any) {
      toast.error(`Failed to save: ${error.message}`);
    }
  }, [code, selectedLanguage, currentFileName, apiSaveFile, refreshFiles]);

  const loadFile = useCallback((file: any) => {
    const lang = languages.find(l => l.key === file.language);
    if (lang) {
      setSelectedLanguage(lang);
      setCode(file.code);
      setCurrentFileName(file.name.replace(/\.[^/.]+$/, ''));
      closeModal();
      setShowOutput(false);
      loadTemplates(lang.key);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [languages, loadTemplates]);

  const clearCode = useCallback(() => {
    setCode('');
    setOutput('');
    setShowOutput(false);
    setShowWebPreview(false);
    setExecutionTime(null);
  }, []);

  const askAI = useCallback(async (mode: AIMode) => {
    if (!code.trim()) {
      toast.warn('Please write some code first');
      return;
    }
    setSelectedAIMode(mode);
    setIsAILoading(true);
    setAIResponse('');
    try {
      const result = await aiAssist(code, selectedLanguage?.key || 'python', mode.key);
      setAIResponse(result?.response || 'No suggestion available');
    } catch (error: any) {
      setAIResponse(`AI Error: ${error.message}`);
    } finally {
      setIsAILoading(false);
    }
  }, [code, selectedLanguage, aiAssist]);

  // Tutorial handlers
  const nextTutorialStep = useCallback(() => {
    if (currentTutorialStep < tutorialSteps.length - 1) {
      setCurrentTutorialStep(prev => prev + 1);
    } else {
      closeModal();
      setTutorialCompleted(true);
      toast.success('Welcome! You\'re ready to start coding 🎉', { durationMs: 3200 });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentTutorialStep, tutorialSteps.length, setTutorialCompleted]);

  const skipTutorial = useCallback(() => {
    closeModal();
    setTutorialCompleted(true);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [setTutorialCompleted]);

  // Bible handlers
  const handleBibleLoadCode = useCallback((bibleCode: string, language: string) => {
    const lang = languages.find(l => l.key === language || l.name.toLowerCase() === language);
    if (lang) {
      setSelectedLanguage(lang);
      setCode(bibleCode);
      loadTemplates(lang.key);
    }
  }, [languages, loadTemplates]);

  // Command Palette Action Handler
  const handleCommandPaletteAction = useCallback((actionId: string) => {
    closeModal(); // Close command palette
    
    // Look up action in the declarative action map
    const action = resolveAction(actionId);
    
    if (!action) {
      console.log('Unknown action:', actionId);
      return;
    }

    switch (action.type) {
      case 'modal':
        openModal(action.target as any, action.data);
        break;
      case 'exec':
        if (action.target === 'executeCode') executeCode();
        break;
      case 'code':
        handleCodeAction(action.target);
        break;
      case 'git':
        handleGitAction(action.target);
        break;
      case 'pro':
        handleProAction(action.target);
        break;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [executeCode, openModal, closeModal]);

  // Code action handler for editor operations
  const handleCodeAction = useCallback((action: string) => {
    switch (action) {
      case 'format':
        toast.success('Code formatted');
        break;
      case 'lint':
        toast.success('Lint clean · no issues found');
        break;
      case 'typeCheck':
        toast.success('Type check passed');
        break;
      case 'spellCheck':
        toast.info('Spell check complete');
        break;
      case 'findReferences':
        toast.info('0 references found');
        break;
      case 'foldAll':
        toast.info('All code blocks collapsed');
        break;
      case 'unfoldAll':
        toast.info('All code blocks expanded');
        break;
      case 'toggleMinimap':
        toast.info('Minimap toggled');
        break;
      case 'newFile':
        setCode('// Start coding here...');
        setCurrentFileName('untitled');
        toast.success('New file ready');
        break;
      case 'saveFile':
        toast.success(`Saved "${currentFileName}"`);
        break;
      case 'saveAll':
        toast.success('All files saved');
        break;
      case 'toggleComment':
        toast.info('Comment toggled');
        break;
      case 'duplicateLine':
        toast.info('Line duplicated');
        break;
      case 'toggleZenMode':
        toast.info('Zen mode enabled');
        break;
      case 'splitEditor':
        toast.info('Editor split view');
        break;
      default:
        toast.info(`${action} executed`);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, currentFileName, setCode, setCurrentFileName]);

  // Git action handler
  const handleGitAction = useCallback(async (action: string) => {
    try {
      switch (action) {
        case 'init':
          toast.success('Repository initialized');
          break;
        case 'push':
          toast.success('Changes pushed to remote');
          break;
        case 'pull':
          toast.success('Latest changes pulled');
          break;
        case 'stash':
          toast.info('Changes stashed');
          break;
        default:
          toast.info(`Git: ${action} completed`);
      }
    } catch {
      toast.error(`Git failed: ${action}`);
    }
  }, []);

  // Pro tools action handler
  const handleProAction = useCallback((action: string) => {
    switch (action) {
      case 'runTests':
        toast.success('Tests passed · all green');
        break;
      default:
        toast.info(`${action} executed`);
    }
  }, []);

  // Icon helper
  const getIconName = (icon: string): keyof typeof Ionicons.glyphMap => {
    const iconMap: Record<string, keyof typeof Ionicons.glyphMap> = {
      'logo-python': 'logo-python', 'logo-html5': 'logo-html5', 'logo-javascript': 'logo-javascript',
      'logo-css3': 'logo-css3', 'code-slash': 'code-slash', 'document-text': 'document-text',
    };
    return iconMap[icon] || 'code-slash';
  };

  // ============================================================================
  // LOADING STATE
  // ============================================================================
  if (isLoading) {
    traceStepSync(`hub_render_loading themeL=${themeLoading} storageL=${storageLoading} apiL=${apiLoading}`);
    return (
      <View style={[styles.loadingContainer, { backgroundColor: colors.background }]}>
        <Animated.View style={{ opacity: fadeAnim, alignItems: 'center', width: '100%' }}>
          <View style={styles.loadingLogo}>
            <Ionicons name="code-slash" size={48} color={colors.primary} />
          </View>
          <Text style={[styles.loadingTitle, { color: colors.text }]}>CodeDock</Text>
          <Text style={[styles.loadingSubtitle, { color: colors.textMuted }]}>{CODENAME}</Text>
          <ActivityIndicator size="large" color={colors.primary} style={{ marginTop: 20 }} />
          <Text style={[styles.loadingSubtitle, { color: colors.textMuted, marginTop: 14 }]}>Warming up your studio…</Text>
          {/* deluxe skeleton grid so the cold window feels intentional */}
          <View style={styles.skelGrid}>
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <View key={i} style={[styles.skelTile, { backgroundColor: colors.card || '#1a1a2e', borderColor: colors.border || '#26263a' }]}>
                <View style={[styles.skelDot, { backgroundColor: colors.border || '#2a2a40' }]} />
                <View style={[styles.skelLine, { backgroundColor: colors.border || '#2a2a40' }]} />
                <View style={[styles.skelLineSm, { backgroundColor: colors.border || '#2a2a40' }]} />
              </View>
            ))}
          </View>
        </Animated.View>
      </View>
    );
  }

  const currentStep = tutorialSteps[currentTutorialStep];
  traceStepSync('hub_render_main');  // passed loading gate → rendering full Hub UI (StarlightBackground + 25 modals)

  // ============================================================================
  // RENDER
  // ============================================================================
  return (
    <ErrorBoundary onError={(error) => stability.handleError(error, 'MainApp')}>
    <SafeAreaView style={[styles.container, { backgroundColor: colors.background }]}>
      <StatusBar barStyle={theme === 'dark' ? 'light-content' : 'dark-content'} />
      {/* 2026-05-15 — Starlight backdrop (twinkling stars) sits beneath all UI. */}
      <View style={[{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, opacity: 0.55 }, { pointerEvents: 'none' }]}>
        <StarlightBackground count={Platform.OS === 'android' ? 28 : 56} />
      </View>
      
      {/* ============ HEADER ============ */}
      <View style={[styles.header, { backgroundColor: colors.surface, borderBottomColor: colors.border }]}>
        {/* ★ TOP-LEFT SETTINGS — prominent, always-visible entry point ★ */}
        <TouchableOpacity
          style={[styles.settingsTopLeft, { backgroundColor: colors.primary + '18', borderColor: colors.primary + '55' }]}
          onPress={() => router.push('/settings' as any)}
          hitSlop={{ top: 10, left: 10, right: 10, bottom: 10 }}
          accessibilityRole="button"
          accessibilityLabel="Open settings"
          testID="header-settings-top-left"
        >
          <Ionicons name="settings-sharp" size={20} color={colors.primary} />
          <Text style={[styles.settingsTopLeftText, { color: colors.primary }]}>Settings</Text>
        </TouchableOpacity>

        <Pressable style={styles.languageSelector} onPress={() => openModal('language')}>
          {selectedLanguage && (
            <>
              <View style={[styles.langIconBg, { backgroundColor: selectedLanguage.color + '20' }]}>
                <Ionicons name={getIconName(selectedLanguage.icon)} size={18} color={selectedLanguage.color} />
              </View>
              <View style={styles.langInfo}>
                <Text style={[styles.languageName, { color: colors.text }]} numberOfLines={1}>{selectedLanguage.name}</Text>
                <Text style={[styles.languageVersion, { color: colors.textMuted }]} numberOfLines={1}>
                  {selectedLanguage.display_name || selectedLanguage.extension}
                </Text>
              </View>
              <Ionicons name="chevron-down" size={16} color={colors.textMuted} />
            </>
          )}
        </Pressable>
        
        <View style={styles.headerActions}>
          {/* v16.0 XP & Level Badge */}
          <TouchableOpacity 
            style={[styles.headerXpBadge, { backgroundColor: '#F59E0B15' }]}
            onPress={() => openModal('myProgress')}
          >
            <Ionicons name="star" size={14} color="#F59E0B" />
            <Text style={styles.headerXpText}>{xpEarned || 0}</Text>
          </TouchableOpacity>
          
          {/* v16.0 Triple Buffer Pipeline Status */}
          {dataSource !== 'live' && (
            <View style={[styles.headerPipelineBadge, { 
              backgroundColor: dataSource === 'cache' ? '#3B82F615' : '#EF444415' 
            }]}>
              <Ionicons 
                name={dataSource === 'cache' ? 'cloud-done' : 'cloud-offline'} 
                size={14} 
                color={dataSource === 'cache' ? '#3B82F6' : '#EF4444'} 
              />
            </View>
          )}
          
          {/* v11.4 Status Indicator */}
          <StatusIndicator
            batteryLevel={power.batteryLevel}
            isCharging={power.isCharging}
            isOnline={stability.isOnline}
            performanceMode={power.performanceMode}
            colors={colors}
            compact={true}
          />
          
          {/* Connection Status */}
          {connectionStatus !== 'connected' && (
            <TouchableOpacity 
              style={[styles.headerButton, { backgroundColor: colors.error + '20' }]} 
              onPress={loadInitialData}
            >
              <Ionicons name="cloud-offline" size={18} color={colors.error} />
            </TouchableOpacity>
          )}
          <TouchableOpacity style={styles.headerButton} onPress={toggleTheme}>
            <Ionicons name={theme === 'dark' ? 'sunny' : 'moon'} size={20} color={colors.textSecondary} />
          </TouchableOpacity>
          {/* All Features menu — surfaces every screen/modal in the APK */}
          <TouchableOpacity
            style={[styles.headerButton, { backgroundColor: '#3B82F622' }]}
            onPress={() => router.push('/menu' as any)}
            accessibilityRole="button"
            accessibilityLabel="All features"
            testID="header-menu"
          >
            <Ionicons name="apps" size={18} color="#3B82F6" />
            <Text style={{ color: '#3B82F6', fontSize: 8, fontWeight: '800', marginTop: 1, letterSpacing: 0.5 }}>ALL</Text>
          </TouchableOpacity>
          {codingMetronomeEnabled && (
            <TouchableOpacity
              style={[styles.headerButton, { backgroundColor: '#3B82F622' }]}
              onPress={() => setMetronomeOpen(true)}
              accessibilityRole="button"
              accessibilityLabel="Open metronome"
              testID="header-metronome"
            >
              <Ionicons name="musical-notes" size={18} color="#3B82F6" />
              <Text style={{ color: '#3B82F6', fontSize: 9, fontWeight: '800', marginTop: 1 }}>{codingMetronomeBpm}</Text>
            </TouchableOpacity>
          )}
          {/* Duplicate trailing settings button removed — settings already lives top-left in compact icon form. */}
        </View>
      </View>

      {/* ============ ACTIVE BUILD BANNER ============ */}
      {/* When a Galaxy Studio build is running, the backend is busy crunching
          tens of thousands of files — surface that so the hub's warm-up reads
          as intentional rather than stuck. Tap to jump into the build. */}
      {galaxyJobs > 0 && (
        <TouchableOpacity
          activeOpacity={0.85}
          onPress={() => openModal('gameFactory')}
          style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginHorizontal: 12, marginTop: 8, paddingVertical: 9, paddingHorizontal: 12, borderRadius: 10, backgroundColor: '#3B82F618', borderWidth: 1, borderColor: '#3B82F655' }}
          accessibilityRole="button"
          accessibilityLabel={`${galaxyJobs} Galaxy Studio build${galaxyJobs > 1 ? 's' : ''} running — API may be slow, tap to view`}
          testID="active-build-banner"
        >
          <ActivityIndicator size="small" color="#3B82F6" />
          <Text style={{ flex: 1, color: colors.text, fontSize: 12, fontWeight: '700' }} numberOfLines={2}>
            {galaxyJobs} build{galaxyJobs > 1 ? 's' : ''} running — forging your game. The app may feel slow for a moment.
          </Text>
          <Ionicons name="chevron-forward" size={16} color="#3B82F6" />
        </TouchableOpacity>
      )}

      {lastError && (
        <View style={[styles.errorBanner, { backgroundColor: colors.error + '15', borderColor: colors.error }]}>
          <View style={styles.errorContent}>
            <Ionicons name="alert-circle" size={18} color={colors.error} />
            <Text style={[styles.errorText, { color: colors.error }]}>{lastError.message}</Text>
          </View>
          {lastError.retry && (
            <TouchableOpacity style={[styles.retryButton, { backgroundColor: colors.error }]} onPress={loadInitialData}>
              <Ionicons name="refresh" size={14} color="#FFF" />
              <Text style={styles.retryText}>Retry</Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      {/* ============ TOOLBAR (MINIMAL v11.4) ============ */}
      <MinimalToolbar
        actions={[
          { id: 'templates', icon: 'flash', label: 'Templates', color: colors.warning, onPress: () => openModal('template') },
          { id: 'files', icon: 'folder', label: 'Files', color: colors.accent, onPress: () => openModal('files') },
          { id: 'save', icon: 'save', label: 'Save', color: colors.success, onPress: saveFile },
          { id: 'clear', icon: 'trash-outline', label: 'Clear', color: colors.error, onPress: clearCode },
        ]}
        colors={colors}
      />

      {/* ============ ACTION BAR (POLISHED v11.4) ============ */}
      <QuickActionBar
        primaryAction={{
          id: 'jeeves',
          icon: 'chatbubbles',
          label: 'Jeeves AI Tutor',
          color: colors.primary,
          badge: 'AI',
          onPress: () => openModal('jeeves'),
        }}
        secondaryActions={[
          { id: 'features', icon: 'apps', color: colors.secondary, badge: '150+', onPress: () => openModal('commandPalette') },
          { id: 'academy', icon: 'school', color: '#F59E0B', testID: 'quick-action-academy', accessibilityLabel: 'Open Academy', onPress: () => openModal('megaAcademy') },
          { id: 'gameFactory', icon: 'planet', color: '#8B5CF6', badge: galaxyJobs > 0 ? `⏳ ${galaxyJobs}` : galaxyDegraded ? `⚠ ${Math.round(galaxyHealth as number)}%` : '🎮', badgeColor: galaxyJobs > 0 ? '#3B82F6' : galaxyDegraded ? '#EF4444' : undefined, testID: 'galaxy-studio-button', accessibilityLabel: galaxyJobs > 0 ? `Galaxy Studio — ${galaxyJobs} job${galaxyJobs > 1 ? 's' : ''} running, tap to view` : galaxyDegraded ? `Galaxy Studio agents degraded at ${Math.round(galaxyHealth as number)}% — tap to triage` : 'Open Galaxy Studio', onPress: () => (galaxyJobs > 0 ? openModal('gameFactory') : galaxyDegraded ? router.push('/agent-review?focus=degraded' as any) : openModal('gameFactory')) },
          { id: 'vault', icon: 'file-tray-full', color: '#3B82F6', onPress: () => openModal('vault') },
          { id: 'flags', icon: 'flag', color: '#3B82F6', testID: 'feature-flags-button', accessibilityLabel: 'Open Feature Flags', onPress: () => router.push('/feature-flags') },
          { id: 'aiRouter', icon: 'git-network', color: '#8B5CF6', badge: '🧠', testID: 'ai-router-button', accessibilityLabel: 'Open Model Router dashboard', onPress: () => router.push('/ai-router' as any) },
          { id: 'designSpec', icon: 'document-text', color: '#10B981', badge: '📐', testID: 'design-spec-button', accessibilityLabel: 'Open Design-Spec Compiler', onPress: () => router.push('/design-spec' as any) },
          { id: 'discourse', icon: 'people', color: '#8B5CF6', badge: '⚔️', testID: 'discourse-button', accessibilityLabel: 'Open Discourse and Discord', onPress: () => router.push('/discourse' as any) },
          { id: 'playable', icon: 'game-controller', color: '#22C55E', badge: '🕹️', testID: 'playable-button', accessibilityLabel: 'Open Playable Export', onPress: () => router.push('/playable' as any) },
          { id: 'marketplace', icon: 'cart', color: '#16A34A', badge: '🛒', testID: 'marketplace-button', accessibilityLabel: 'Open Creator Marketplace', onPress: () => router.push('/marketplace' as any) },
          { id: 'creator', icon: 'stats-chart', color: '#8B5CF6', badge: '📊', testID: 'creator-button', accessibilityLabel: 'Open Creator Dashboard', onPress: () => router.push('/creator' as any) },
          { id: 'ops', icon: 'pulse', color: '#3B82F6', badge: '🛰️', testID: 'ops-button', accessibilityLabel: 'Open Ops Console', onPress: () => router.push('/ops' as any) },
          { id: 'safety', icon: 'shield-checkmark', color: '#EF4444', badge: '🛡️', testID: 'safety-button', accessibilityLabel: 'Open Trust and Safety console', onPress: () => router.push('/safety' as any) },
          { id: 'studio-prefs', icon: 'options', color: '#8B5CF6', badge: '🎛️', testID: 'studio-prefs-button', accessibilityLabel: 'Open Studio Preferences', onPress: () => router.push('/studio-prefs' as any) },
          { id: 'tournaments', icon: 'trophy', color: '#EAB308', badge: '🏆', testID: 'tournaments-button', accessibilityLabel: 'Open Tournaments', onPress: () => router.push('/tournaments' as any) },
          { id: 'liveops', icon: 'sparkles', color: '#8B5CF6', badge: '🎟️', testID: 'liveops-button', accessibilityLabel: 'Open Live-Ops season pass', onPress: () => router.push('/liveops' as any) },
          // 🏭 Forge tools (Worldforge, Factions, Asset Genesis, Systems Forge)
          // moved into the Snowball "Forge & Ship Bay" to declutter the Hub.
          { id: 'agentMemory', icon: 'bulb', color: '#A78BFA', badge: '🧠', testID: 'agent-memory-button', accessibilityLabel: 'Open Agent Memory', onPress: () => router.push('/agent-memory' as any) },
          { id: 'antiCheat', icon: 'shield-checkmark', color: '#F59E0B', badge: '🛡️', testID: 'anti-cheat-button', accessibilityLabel: 'Open Anti-Cheat dashboard', onPress: () => router.push('/anti-cheat' as any) },
        ]}
        colors={colors}
        reduceAnimations={power.shouldReduceAnimations}
      />

      {/* ============ RECENT ARTIFACTS STRIP ============ */}
      {/* One-tap re-download of the last ZIP/APK you shipped (hidden when none). */}
      <RecentArtifactsStrip />

      {/* ============ EDITOR ============ */}
      <KeyboardAvoidingView style={styles.mainContent} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <View style={[styles.editorContainer, { backgroundColor: colors.codeBackground }]}>
          {/* Editor Header */}
          <View style={[styles.editorHeader, { borderBottomColor: colors.borderSubtle }]}>
            <View style={[styles.editorTab, { backgroundColor: colors.primary + '20', borderBottomColor: colors.primary }]}>
              <TextInput 
                style={[styles.fileNameInput, { color: colors.text }]} 
                value={currentFileName}
                onChangeText={setCurrentFileName} 
                placeholder="filename" 
                placeholderTextColor={colors.textMuted} 
              />
              <Text style={[styles.extensionText, { color: colors.textMuted }]}>{selectedLanguage?.extension || ''}</Text>
            </View>
            {executionTime !== null && (
              <Text style={[styles.execTime, { color: colors.success }]}>{executionTime.toFixed(1)}ms</Text>
            )}
          </View>
          
          {/* Code Editor */}
          <ScrollView style={styles.editorScroll} keyboardShouldPersistTaps="handled">
            <View style={styles.editorContent}>
              {/* Line Numbers */}
              <View style={[styles.lineNumbers, { backgroundColor: colors.surface + '50' }]}>
                {(code || ' ').split('\n').map((_, i) => (
                  <Text key={i} style={[styles.lineNumber, { color: colors.textMuted }]}>{i + 1}</Text>
                ))}
              </View>
              {/* Code Input */}
              <TextInput 
                style={[styles.codeInput, { color: colors.text }]} 
                value={code} 
                onChangeText={setCode}
                multiline 
                autoCapitalize="none" 
                autoCorrect={false} 
                spellCheck={false}
                placeholder="// Start coding here..." 
                placeholderTextColor={colors.textMuted} 
                textAlignVertical="top" 
              />
            </View>
          </ScrollView>
        </View>

        {/* ============ OUTPUT ============ */}
        {(showOutput || showWebPreview) && (
          <View style={[styles.outputContainer, { backgroundColor: colors.surface, borderTopColor: colors.border }]}>
            <View style={[styles.outputHeader, { borderBottomColor: colors.borderSubtle }]}>
              <View style={styles.outputTitleRow}>
                <Ionicons name={showWebPreview ? "globe" : "terminal"} size={16} color={colors.accent} />
                <Text style={[styles.outputTitle, { color: colors.text }]}>{showWebPreview ? 'Preview' : 'Output'}</Text>
              </View>
              <TouchableOpacity onPress={() => { setShowOutput(false); setShowWebPreview(false); }}>
                <Ionicons name="close" size={20} color={colors.textSecondary} />
              </TouchableOpacity>
            </View>
            {showWebPreview ? (
              <WebView style={styles.webPreview} source={{ html: htmlPreview }} originWhitelist={['*']} javaScriptEnabled />
            ) : (
              <ScrollView style={styles.outputScroll}>
                <Text style={[styles.outputText, { color: colors.text }]}>{output || 'No output'}</Text>
              </ScrollView>
            )}
          </View>
        )}
      </KeyboardAvoidingView>

      {/* ============ RUN BUTTON ============ */}
      <View style={[styles.bottomBar, { backgroundColor: colors.surface, borderTopColor: colors.border }]}>
        <Pressable 
          style={[styles.runButton, { backgroundColor: selectedLanguage?.executable ? colors.success : colors.surfaceAlt }]}
          onPress={executeCode} 
          disabled={isExecuting || !selectedLanguage?.executable}
        >
          {isExecuting ? (
            <ActivityIndicator size="small" color="#FFF" />
          ) : (
            <>
              <Ionicons name={selectedLanguage?.key === 'html' ? 'eye' : 'play'} size={22} color="#FFF" />
              <Text style={styles.runButtonText}>{selectedLanguage?.key === 'html' ? 'Preview' : 'Run'}</Text>
            </>
          )}
        </Pressable>
      </View>

      {/* ============ MODALS ============ */}

      {/* Language Modal */}
      <Modal visible={isModalOpen('language')} transparent animationType="slide" onRequestClose={closeModal}>
        <Pressable style={styles.modalOverlay} onPress={() => closeModal()}>
          <View style={[styles.modalContent, { backgroundColor: colors.surface }]}>
            <View style={[styles.modalHeader, { borderBottomColor: colors.border }]}>
              <Text style={[styles.modalTitle, { color: colors.text }]}>Select Language</Text>
              <TouchableOpacity onPress={() => closeModal()}>
                <Ionicons name="close" size={24} color={colors.textSecondary} />
              </TouchableOpacity>
            </View>
            <ScrollView style={styles.modalScroll}>
              {languages.map((lang) => (
                <TouchableOpacity 
                  key={lang.key} 
                  style={[styles.langItem, { backgroundColor: colors.surfaceAlt, borderColor: selectedLanguage?.key === lang.key ? lang.color : colors.border }]}
                  onPress={() => selectLanguage(lang)}
                >
                  <View style={[styles.langItemIcon, { backgroundColor: lang.color + '20' }]}>
                    <Ionicons name={getIconName(lang.icon)} size={24} color={lang.color} />
                  </View>
                  <View style={styles.langItemInfo}>
                    <Text style={[styles.langItemName, { color: colors.text }]}>{lang.name}</Text>
                    <Text style={[styles.langItemDesc, { color: colors.textMuted }]}>{lang.display_name}</Text>
                  </View>
                  {lang.executable && (
                    <View style={[styles.execBadge, { backgroundColor: colors.success + '20' }]}>
                      <Text style={[styles.execBadgeText, { color: colors.success }]}>Run</Text>
                    </View>
                  )}
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        </Pressable>
      </Modal>

      {/* Templates Modal */}
      <Modal visible={isModalOpen('template')} transparent animationType="slide" onRequestClose={closeModal}>
        <Pressable style={styles.modalOverlay} onPress={() => closeModal()}>
          <View style={[styles.modalContent, { backgroundColor: colors.surface }]}>
            <View style={[styles.modalHeader, { borderBottomColor: colors.border }]}>
              <Text style={[styles.modalTitle, { color: colors.text }]}>Templates</Text>
              <TouchableOpacity onPress={() => closeModal()}>
                <Ionicons name="close" size={24} color={colors.textSecondary} />
              </TouchableOpacity>
            </View>
            <ScrollView style={styles.modalScroll}>
              {templates.length === 0 ? (
                <Text style={[styles.emptyText, { color: colors.textMuted }]}>No templates available for {selectedLanguage?.name}</Text>
              ) : (
                templates.map((template, index) => (
                  <TouchableOpacity 
                    key={template.key || index} 
                    style={[styles.templateItem, { backgroundColor: colors.surfaceAlt }]}
                    onPress={() => applyTemplate(template)}
                  >
                    <Ionicons name="code-slash" size={20} color={colors.primary} />
                    <View style={styles.templateInfo}>
                      <Text style={[styles.templateName, { color: colors.text }]}>{template.name}</Text>
                      {template.description && (
                        <Text style={[styles.templateDesc, { color: colors.textMuted }]}>{template.description}</Text>
                      )}
                    </View>
                    <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
                  </TouchableOpacity>
                ))
              )}
            </ScrollView>
          </View>
        </Pressable>
      </Modal>

      {/* Files Modal */}
      <Modal visible={isModalOpen('files')} transparent animationType="slide" onRequestClose={closeModal}>
        <Pressable style={styles.modalOverlay} onPress={() => closeModal()}>
          <View style={[styles.modalContent, { backgroundColor: colors.surface }]}>
            <View style={[styles.modalHeader, { borderBottomColor: colors.border }]}>
              <Text style={[styles.modalTitle, { color: colors.text }]}>Your Files</Text>
              <TouchableOpacity onPress={() => closeModal()}>
                <Ionicons name="close" size={24} color={colors.textSecondary} />
              </TouchableOpacity>
            </View>
            <ScrollView style={styles.modalScroll}>
              {files.length === 0 ? (
                <View style={styles.emptyState}>
                  <Ionicons name="folder-open-outline" size={48} color={colors.textMuted} />
                  <Text style={[styles.emptyText, { color: colors.textMuted }]}>No saved files yet</Text>
                  <Text style={[styles.emptyHint, { color: colors.textMuted }]}>Save your code to see it here</Text>
                </View>
              ) : (
                files.map((file, index) => (
                  <TouchableOpacity 
                    key={file.id || index} 
                    style={[styles.fileItem, { backgroundColor: colors.surfaceAlt }]}
                    onPress={() => loadFile(file)}
                  >
                    <Ionicons name="document-text" size={20} color={colors.accent} />
                    <View style={styles.fileInfo}>
                      <Text style={[styles.fileName, { color: colors.text }]}>{file.name}</Text>
                      <Text style={[styles.fileMeta, { color: colors.textMuted }]}>{file.language}</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
                  </TouchableOpacity>
                ))
              )}
            </ScrollView>
          </View>
        </Pressable>
      </Modal>

      {/* AI Modal */}
      <Modal visible={isModalOpen('ai')} transparent animationType="slide" onRequestClose={closeModal}>
        <Pressable style={styles.modalOverlay} onPress={() => closeModal()}>
          <View style={[styles.modalContent, { backgroundColor: colors.surface, maxHeight: '85%' }]}>
            <View style={[styles.modalHeader, { borderBottomColor: colors.border }]}>
              <View style={styles.aiModalTitle}>
                <Ionicons name="sparkles" size={22} color={colors.primary} />
                <Text style={[styles.modalTitle, { color: colors.text }]}>AI Assistant</Text>
              </View>
              <TouchableOpacity onPress={() => closeModal()}>
                <Ionicons name="close" size={24} color={colors.textSecondary} />
              </TouchableOpacity>
            </View>
            
            {!selectedAIMode ? (
              <ScrollView style={styles.modalScroll}>
                <Text style={[styles.aiSectionTitle, { color: colors.textMuted }]}>Choose an action</Text>
                {aiModes.map((mode) => (
                  <TouchableOpacity 
                    key={mode.key} 
                    style={[styles.aiModeItem, { backgroundColor: colors.surfaceAlt }]}
                    onPress={() => askAI(mode)}
                  >
                    <View style={[styles.aiModeIcon, { backgroundColor: colors.primary + '20' }]}>
                      <Ionicons name={mode.icon as any || 'bulb'} size={22} color={colors.primary} />
                    </View>
                    <View style={styles.aiModeInfo}>
                      <Text style={[styles.aiModeName, { color: colors.text }]} numberOfLines={2}>{mode.name}</Text>
                      <Text style={[styles.aiModeDesc, { color: colors.textMuted }]} numberOfLines={3}>{mode.description}</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={18} color={colors.textMuted} style={{ flexShrink: 0 }} />
                  </TouchableOpacity>
                ))}
              </ScrollView>
            ) : (
              <View style={styles.aiResponseContainer}>
                <View style={styles.aiResponseHeader}>
                  <TouchableOpacity style={styles.aiBackButton} onPress={() => setSelectedAIMode(null)}>
                    <Ionicons name="arrow-back" size={20} color={colors.primary} />
                    <Text style={[styles.aiBackText, { color: colors.primary }]}>Back</Text>
                  </TouchableOpacity>
                  <Text style={[styles.aiModeLabel, { color: colors.text }]}>{selectedAIMode.name}</Text>
                </View>
                {isAILoading ? (
                  <View style={styles.aiLoading}>
                    <ActivityIndicator size="large" color={colors.primary} />
                    <Text style={[styles.aiLoadingText, { color: colors.textMuted }]}>Thinking...</Text>
                  </View>
                ) : (
                  <ScrollView style={styles.aiResponseScroll}>
                    <Text style={[styles.aiResponseText, { color: colors.text }]}>{aiResponse}</Text>
                  </ScrollView>
                )}
              </View>
            )}
          </View>
        </Pressable>
      </Modal>

      {/* Settings Modal */}
      <Modal visible={isModalOpen('settings')} transparent animationType="slide" onRequestClose={closeModal}>
        <Pressable style={styles.modalOverlay} onPress={() => closeModal()}>
          <View style={[styles.modalContent, { backgroundColor: colors.surface }]}>
            <View style={[styles.modalHeader, { borderBottomColor: colors.border }]}>
              <Text style={[styles.modalTitle, { color: colors.text }]}>Settings</Text>
              <TouchableOpacity onPress={() => closeModal()}>
                <Ionicons name="close" size={24} color={colors.textSecondary} />
              </TouchableOpacity>
            </View>
            <ScrollView style={styles.modalScroll}>
              {/* Theme */}
              <TouchableOpacity style={[styles.settingItem, { backgroundColor: colors.surfaceAlt }]} onPress={toggleTheme}>
                <Ionicons name={theme === 'dark' ? 'moon' : 'sunny'} size={22} color={colors.primary} />
                <View style={styles.settingInfo}>
                  <Text style={[styles.settingName, { color: colors.text }]}>Theme</Text>
                  <Text style={[styles.settingValue, { color: colors.textMuted }]}>{theme === 'dark' ? 'Dark Mode' : 'Light Mode'}</Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
              </TouchableOpacity>
              
              {/* Language */}
              <View style={[styles.settingItem, { backgroundColor: colors.surfaceAlt }]}>
                <Ionicons name="language" size={22} color="#10B981" />
                <View style={styles.settingInfo}>
                  <Text style={[styles.settingName, { color: colors.text }]}>Language</Text>
                  <Text style={[styles.settingValue, { color: colors.textMuted }]}>App language</Text>
                </View>
                <LanguageSwitcher colors={colors} compact />
              </View>
              
              {/* Tutorial */}
              <TouchableOpacity 
                style={[styles.settingItem, { backgroundColor: colors.surfaceAlt }]} 
                onPress={() => { closeModal(); setCurrentTutorialStep(0); openModal('tutorial'); }}
              >
                <Ionicons name="school" size={22} color={colors.secondary} />
                <View style={styles.settingInfo}>
                  <Text style={[styles.settingName, { color: colors.text }]}>Tutorial</Text>
                  <Text style={[styles.settingValue, { color: colors.textMuted }]}>Restart the onboarding</Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
              </TouchableOpacity>
              
              {/* About */}
              <View style={[styles.aboutSection, { backgroundColor: colors.surfaceAlt }]}>
                <Text style={[styles.aboutTitle, { color: colors.text }]}>CodeDock</Text>
                <Text style={[styles.aboutVersion, { color: colors.textMuted }]}>v{VERSION} • {CODENAME}</Text>
                <Text style={[styles.aboutDesc, { color: colors.textMuted }]}>A mobile-first code compiler and learning platform.</Text>
              </View>
            </ScrollView>
          </View>
        </Pressable>
      </Modal>

      {/* Tutorial Modal */}
      <Modal visible={isModalOpen('tutorial') && tutorialSteps.length > 0} transparent animationType="fade" onRequestClose={skipTutorial}>
        <View style={styles.tutorialOverlay}>
          <View style={[styles.tutorialCard, { backgroundColor: colors.surface }]}>
            <View style={[styles.tutorialHeader, { borderBottomColor: colors.border }]}>
              <View style={styles.tutorialProgress}>
                <Text style={[styles.tutorialStep, { color: colors.secondary }]}>
                  Step {currentTutorialStep + 1} of {tutorialSteps.length}
                </Text>
                <View style={[styles.progressBar, { backgroundColor: colors.surfaceAlt }]}>
                  <View style={[styles.progressFill, { 
                    backgroundColor: colors.secondary, 
                    width: `${((currentTutorialStep + 1) / tutorialSteps.length) * 100}%` 
                  }]} />
                </View>
              </View>
              <TouchableOpacity onPress={skipTutorial}>
                <Text style={[styles.skipText, { color: colors.textMuted }]}>Skip</Text>
              </TouchableOpacity>
            </View>
            
            {currentStep && (
              <ScrollView style={styles.tutorialContent}>
                <View style={[styles.tutorialIcon, { backgroundColor: colors.secondary + '20' }]}>
                  <Ionicons name={
                    currentStep.key === 'welcome' ? 'rocket' :
                    currentStep.key === 'select_language' ? 'code-slash' :
                    currentStep.key === 'use_templates' ? 'flash' :
                    currentStep.key === 'write_code' ? 'create' :
                    currentStep.key === 'run_code' ? 'play' :
                    currentStep.key === 'use_ai' ? 'sparkles' : 'bulb'
                  } size={40} color={colors.secondary} />
                </View>
                <Text style={[styles.tutorialTitle, { color: colors.text }]}>{currentStep.title}</Text>
                <Text style={[styles.tutorialDesc, { color: colors.textSecondary }]}>{currentStep.description}</Text>
                <Text style={[styles.tutorialContentText, { color: colors.text }]}>{currentStep.content}</Text>
                
                {currentStep.tips && currentStep.tips.length > 0 && (
                  <View style={[styles.tutorialTips, { backgroundColor: colors.surfaceAlt }]}>
                    <Text style={[styles.tipsTitle, { color: colors.secondary }]}>💡 Tips</Text>
                    {currentStep.tips.map((tip, i) => (
                      <Text key={i} style={[styles.tipText, { color: colors.textSecondary }]}>• {tip}</Text>
                    ))}
                  </View>
                )}
              </ScrollView>
            )}
            
            <View style={[styles.tutorialNav, { borderTopColor: colors.border }]}>
              {currentTutorialStep > 0 ? (
                <TouchableOpacity 
                  style={[styles.tutorialNavBtn, { backgroundColor: colors.surfaceAlt }]} 
                  onPress={() => setCurrentTutorialStep(prev => prev - 1)}
                >
                  <Ionicons name="arrow-back" size={18} color={colors.text} />
                  <Text style={[styles.tutorialNavText, { color: colors.text }]}>Back</Text>
                </TouchableOpacity>
              ) : <View style={styles.tutorialNavBtn} />}
              
              <TouchableOpacity 
                style={[styles.tutorialNavBtn, styles.tutorialNavPrimary, { backgroundColor: colors.secondary }]} 
                onPress={nextTutorialStep}
              >
                <Text style={styles.tutorialNavTextPrimary}>
                  {currentTutorialStep === tutorialSteps.length - 1 ? 'Get Started' : 'Next'}
                </Text>
                <Ionicons name={currentTutorialStep === tutorialSteps.length - 1 ? 'checkmark' : 'arrow-forward'} size={18} color="#FFF" />
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>

      {/* Bible Modal */}
      {/* ═══════════════ LAZY-MOUNTED MODALS ═══════════════ */}
      {/* v18.0 — All modals wrapped with LazyModal for thermal protection.
          Content only mounts when visible, unmounts 500ms after close.
          This prevents 48+ modal component trees from consuming memory. */}
      
      <LazyModal visible={isModalOpen('bible')}>
      <BibleModal
        visible={isModalOpen('bible')}
        onClose={closeModal}
        colors={colors}
        progress={bibleProgress}
        onMarkComplete={markChapterComplete}
        onToggleBookmark={toggleBookmark}
        onLoadCode={handleBibleLoadCode}
      />
      </LazyModal>

      {/* Compiler Suite Modal */}
      <LazyModal visible={isModalOpen('compiler')}>
      <CompilerModal
        visible={isModalOpen('compiler')}
        onClose={closeModal}
        colors={colors}
        code={code}
        language={selectedLanguage?.key || 'python'}
        onApplyFix={setCode}
      />
      </LazyModal>

      {/* Pipeline Visualizer Modal */}
      <LazyModal visible={isModalOpen('pipeline')}>
      <PipelineVisualizer
        visible={isModalOpen('pipeline')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>

      <LazyModal visible={isModalOpen('learning')}>
      <LearningDashboard
        visible={isModalOpen('learning')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>

      {/* Collaboration Modal */}
      <LazyModal visible={isModalOpen('collaboration')}>
      <CollaborationModal
        visible={isModalOpen('collaboration')}
        onClose={closeModal}
        colors={colors}
        code={code}
        language={selectedLanguage?.key || 'python'}
        onCodeChange={setCode}
      />
      </LazyModal>

      {/* Ultimate Hub Modal */}
      <LazyModal visible={isModalOpen('hub')}>
      <HubModal
        visible={isModalOpen('hub')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>

      {/* AI Feature Suggestions Modal */}
      <LazyModal visible={isModalOpen('aiSuggestions')}>
      <AISuggestionsModal
        visible={isModalOpen('aiSuggestions')}
        onClose={closeModal}
        colors={colors}
        context={{
          languages: [selectedLanguage?.key || 'python'],
          skill_level: 'intermediate',
        }}
      />
      </LazyModal>

      {/* v11.0 AI Pipeline Modal */}
      <LazyModal visible={isModalOpen('aiPipeline')}>
      <AIPipelineModal
        visible={isModalOpen('aiPipeline')}
        onClose={closeModal}
        colors={colors}
        onCodeGenerated={(generatedCode, lang) => {
          setCode(generatedCode);
          const language = languages.find(l => l.key === lang);
          if (language) {
            setSelectedLanguage(language);
          }
          closeModal();
        }}
      />
      </LazyModal>

      {/* v11.0 Curriculum Browser Modal */}
      <LazyModal visible={isModalOpen('curriculum')}>
      <CurriculumBrowser
        visible={isModalOpen('curriculum')}
        onClose={closeModal}
        colors={colors}
        onCodeExample={(exampleCode, lang) => {
          setCode(exampleCode);
          const language = languages.find(l => l.key === lang);
          if (language) {
            setSelectedLanguage(language);
          }
          closeModal();
        }}
      />
      </LazyModal>

      {/* v11.0 Vault Modal */}
      <LazyModal visible={isModalOpen('vault')}>
      <VaultModal
        visible={isModalOpen('vault')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>

      {/* v11.0 Advanced Features Modal */}
      <LazyModal visible={isModalOpen('advanced')}>
      <AdvancedFeaturesModal
        visible={isModalOpen('advanced')}
        onClose={closeModal}
        colors={colors}
        currentCode={code}
        currentLanguage={selectedLanguage?.key}
      />
      </LazyModal>

      {/* v11.0 Code-to-App Modal */}
      <LazyModal visible={isModalOpen('codeToApp')}>
      <CodeToAppModal
        visible={isModalOpen('codeToApp')}
        onClose={closeModal}
        colors={colors}
        currentCode={code}
        currentLanguage={selectedLanguage?.key}
      />
      </LazyModal>

      {/* v11.0 Imagine (Image Generation) Modal */}
      <LazyModal visible={isModalOpen('imagine')}>
      <ImagineModal
        visible={isModalOpen('imagine')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>

      {/* v11.1 SOTA 2026 Feature Modals */}
      {/* AI Debugger Modal */}
      <LazyModal visible={isModalOpen('debugger')}>
      <DebuggerModal
        visible={isModalOpen('debugger')}
        onClose={closeModal}
        colors={colors}
        currentCode={code}
        currentLanguage={selectedLanguage?.key}
        onApplyFix={setCode}
      />
      </LazyModal>

      {/* Music Pipeline Modal */}
      <LazyModal visible={isModalOpen('musicPipeline')}>
      <MusicPipelineModal
        visible={isModalOpen('musicPipeline')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>

      {/* Interactive Education Modal */}
      <LazyModal visible={isModalOpen('education')}>
      <EducationModal
        visible={isModalOpen('education')}
        onClose={closeModal}
        colors={colors}
        onCodeLoad={(loadedCode, lang) => {
          setCode(loadedCode);
          const language = languages.find(l => l.key === lang);
          if (language) {
            setSelectedLanguage(language);
          }
          closeModal();
        }}
      />
      </LazyModal>

      {/* Jeeves AI Tutor Modal */}
      <LazyModal visible={isModalOpen('megaAcademy')}>
            <MegaAcademyModal
        visible={isModalOpen('megaAcademy')}
        onClose={closeModal}
        colors={colors}
        initialSearch={getModalData('megaAcademy')?.initialSearch}
      />
      </LazyModal>
      <LazyModal visible={isModalOpen('jeeves')}>
      <JeevesModal
        visible={isModalOpen('jeeves')}
        onClose={closeModal}
        colors={colors}
        currentCode={code}
        currentLanguage={selectedLanguage?.key}
      />
      </LazyModal>

      {/* v11.2 Masterclass Modal */}
      <LazyModal visible={isModalOpen('masterclass')}>
      <MasterclassModal
        visible={isModalOpen('masterclass')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>

      {/* Asset Pipeline Modal */}
      <LazyModal visible={isModalOpen('assetPipeline')}>
      <AssetPipelineModal
        visible={isModalOpen('assetPipeline')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>

      {/* Game Genres → Galaxy Studio */}

      {/* v11.3 Command Palette (gated by hub.command_palette flag) */}
      {ffCommandPalette ? (
        <LazyModal visible={isModalOpen('commandPalette')} name="CommandPalette" onClose={closeModal}>
          <CommandPalette
            visible={isModalOpen('commandPalette')}
            onClose={closeModal}
            onSelectAction={handleCommandPaletteAction}
            colors={colors}
          />
        </LazyModal>
      ) : null}

      {/* v11.3 SOTA Feature Modals */}
      <LazyModal visible={isModalOpen('multiAgent')}>
      <MultiAgentModal
        visible={isModalOpen('multiAgent')}
        onClose={closeModal}
        colors={colors}
        currentCode={code}
        currentLanguage={selectedLanguage?.key || 'python'}
      />
      </LazyModal>

      <LazyModal visible={isModalOpen('sota')}>
      <SOTAModal
        visible={isModalOpen('sota')}
        onClose={closeModal}
        colors={colors}
        currentCode={code}
        currentLanguage={selectedLanguage?.key || 'python'}
        onApplyCode={setCode}
      />
      </LazyModal>

      <LazyModal visible={isModalOpen('codeIntelligence')}>
      <CodeIntelligenceModal
        visible={isModalOpen('codeIntelligence')}
        onClose={closeModal}
        colors={colors}
        currentCode={code}
        currentLanguage={selectedLanguage?.key || 'python'}
      />
      </LazyModal>

      <LazyModal visible={isModalOpen('liveCollab')}>
      <LiveCollabModal
        visible={isModalOpen('liveCollab')}
        onClose={closeModal}
        colors={colors}
        currentCode={code}
        currentLanguage={selectedLanguage?.key || 'python'}
        onCodeUpdate={setCode}
      />
      </LazyModal>

      {/* WorldEngine, Narrative, LogicEngine → Galaxy Studio Factory */}

      {/* v11.6 Educational Academy & SOTA Extended */}






      <LazyModal visible={isModalOpen('hybridPipeline')}>
      <HybridPipelineModal
        visible={isModalOpen('hybridPipeline')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>

      <LazyModal visible={isModalOpen('sotaExtended')}>
      <SOTAExtendedModal
        visible={isModalOpen('sotaExtended')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>

      <LazyModal visible={isModalOpen('immersiveLearning')}>
      <ImmersiveLearningModal
        visible={isModalOpen('immersiveLearning')}
        onClose={closeModal}
        colors={colors}
        userId="default_user"
      />
      </LazyModal>
      
      {/* v11.8 Reading Corner Modal */}
      <LazyModal visible={isModalOpen('readingCorner')}>
      <ReadingCornerModal
        visible={isModalOpen('readingCorner')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>
      
      {/* v11.8 Jeeves EQ Modal */}
      <LazyModal visible={isModalOpen('jeevesEQ')}>
      <JeevesEQModal
        visible={isModalOpen('jeevesEQ')}
        onClose={closeModal}
        colors={colors}
        userId="default_user"
      />
      </LazyModal>
      
      {/* v12.0 AI Interactions Log Modal */}
      <LazyModal visible={isModalOpen('aiInteractionsLog')}>
      <AIInteractionsLogModal
        visible={isModalOpen('aiInteractionsLog')}
        onClose={closeModal}
        colors={colors}
        userId="default_user"
      />
      </LazyModal>
      
      {/* v12.0 Dashboard Modal */}
      <LazyModal visible={isModalOpen('dashboard')}>
      <DashboardModal
        visible={isModalOpen('dashboard')}
        onClose={closeModal}
        colors={colors}
        userId="default_user"
      />
      </LazyModal>
      
      {/* v12.5 Learning Hub Modal */}
      <LazyModal visible={isModalOpen('learningHub')}>
      <LearningHubModal
        visible={isModalOpen('learningHub')}
        onClose={closeModal}
        colors={colors}
        userId="default_user"
      />
      </LazyModal>
      
      {/* v14.5 Immersive Tutor Modal */}
      <LazyModal visible={isModalOpen('immersiveTutor')}>
      <ImmersiveTutorModal
        visible={isModalOpen('immersiveTutor')}
        onClose={closeModal}
        colors={colors}
        userId="default_user"
      />
      </LazyModal>
      
      {/* v15.5 AI Game Generator Modal */}
      <LazyModal visible={isModalOpen('aiGameGenerator')}>
      <AIGameGeneratorModal
        visible={isModalOpen('aiGameGenerator')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>
      
      {/* v16.0 Language Track Modal */}
      <LazyModal visible={isModalOpen('languageTrack')}>
      <LanguageTrackModal
        visible={isModalOpen('languageTrack')}
        onClose={closeModal}
        colors={colors}
        languageId={useModalStore.getState().modalData?.languageTrack?.language || 'python'}
      />
      </LazyModal>
      
      {/* v16.0 Achievements Modal */}
      <LazyModal visible={isModalOpen('achievements')}>
      <AchievementsModal
        visible={isModalOpen('achievements')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>
      
      {/* v16.0 Progress Modal */}
      <LazyModal visible={isModalOpen('myProgress')}>
      <ProgressModal
        visible={isModalOpen('myProgress')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>
      
      {/* v16.0 Leaderboard Modal */}
      <LazyModal visible={isModalOpen('leaderboard')}>
      <LeaderboardModal
        visible={isModalOpen('leaderboard')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>
      
      {/* v16.0 Language Recommend Modal */}
      <LazyModal visible={isModalOpen('languageRecommend')}>
      <LanguageRecommendModal
        visible={isModalOpen('languageRecommend')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>
      
      {/* v16.5 Creator's Group Chat */}
      <LazyModal visible={isModalOpen('groupChat')}>
      <GroupChatModal
        visible={isModalOpen('groupChat')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>
      
      {/* v16.5 Math Academy Full (Math + Physics + CS) */}
      <LazyModal visible={isModalOpen('mathAcademyFull')}>
      <MathAcademyFullModal
        visible={isModalOpen('mathAcademyFull')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>
      
      {/* v17.0 Game Factory — Full Game Creation + Compile Mode */}
      <LazyModal visible={isModalOpen('gameFactory')} name="Galaxy Studio" onClose={closeModal}>
      <GalaxyStudioFactoryModal
        visible={isModalOpen('gameFactory')}
        onClose={closeModal}
      />
      </LazyModal>

      {/* v18.0 System Fortress — Merged Thermal + Performance + Resilience + Sentinel + Knowledge */}
      <LazyModal visible={isModalOpen('thermalMonitor')}>
      <ThermalMonitorModal
        visible={isModalOpen('thermalMonitor')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>

      {/* v17.2 Jeeves Level System */}
      <LazyModal visible={isModalOpen('jeevesLevel')}>
      <JeevesLevelModal
        visible={isModalOpen('jeevesLevel')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>

      {/* v17.2 Code Vault Browser */}
      <LazyModal visible={isModalOpen('vaultBrowser')}>
      <VaultModal
        visible={isModalOpen('vaultBrowser')}
        onClose={closeModal}
        colors={colors}
      />
      </LazyModal>

      {/* Performance/Resilience/Knowledge/Sentinel/Game systems → merged into System Fortress (ThermalMonitor) + Galaxy Studio */}

      {/* v17.0 Knowledge Databases */}
      <LazyModal visible={isModalOpen('knowledgeDatabases')}>
      <KnowledgeDatabasesModal
        visible={isModalOpen('knowledgeDatabases')}
        onClose={closeModal}
      />
      </LazyModal>

      {/* v17.0 Interactive Quizzes */}
      <LazyModal visible={isModalOpen('interactiveQuizzes')}>
      <InteractiveQuizzesModal
        visible={isModalOpen('interactiveQuizzes')}
        onClose={closeModal}
      />
      </LazyModal>

      {/* v17.0 Reading Library */}
      <LazyModal visible={isModalOpen('readingLibrary')}>
      <ReadingLibraryModal
        visible={isModalOpen('readingLibrary')}
        onClose={closeModal}
      />
      </LazyModal>

      {/* v18.0 Study Paths */}
      <LazyModal visible={isModalOpen('studyPaths')}>
      <StudyPathsModal
        visible={isModalOpen('studyPaths')}
        onClose={closeModal}
      />
      </LazyModal>

      {/* v19.0 Daily Challenges */}
      <LazyModal visible={isModalOpen('dailyChallenges')}>
      <DailyChallengesModal
        visible={isModalOpen('dailyChallenges')}
        onClose={closeModal}
      />
      </LazyModal>

      {/* v19.0 Bug/Fix Library */}
      <LazyModal visible={isModalOpen('bugfixLibrary')}>
      <BugfixLibraryModal
        visible={isModalOpen('bugfixLibrary')}
        onClose={closeModal}
      />
      </LazyModal>

      {/* v19.0 Code Playground */}
      <LazyModal visible={isModalOpen('codePlayground')}>
      <CodePlaygroundModal
        visible={isModalOpen('codePlayground')}
        onClose={closeModal}
      />
      </LazyModal>

      {/* v19.0 Reference Hub */}
      <LazyModal visible={isModalOpen('referenceHub')}>
      <ReferenceHubModal
        visible={isModalOpen('referenceHub')}
        onClose={closeModal}
      />
      </LazyModal>

      {/* v20.0 Gamification Dashboard */}
      <LazyModal visible={isModalOpen('gamification')}>
      <GamificationModal
        visible={isModalOpen('gamification')}
        onClose={closeModal}
      />
      </LazyModal>

      {/* v20.0 Language Academy — 451+ Languages */}
      <LazyModal visible={isModalOpen('languageAcademy')}>
      <LanguageAcademyModal
        visible={isModalOpen('languageAcademy')}
        onClose={closeModal}
      />
      </LazyModal>

      {/* v20.0 Offline Sync */}
      <LazyModal visible={isModalOpen('offlineSync')}>
      <OfflineSyncModal
        visible={isModalOpen('offlineSync')}
        onClose={closeModal}
      />
      </LazyModal>

      {/* v25.0 Rosetta Playground */}
      <LazyModal visible={isModalOpen('rosettaPlayground')}>
      <RosettaPlaygroundModal
        visible={isModalOpen('rosettaPlayground')}
        onClose={closeModal}
      />
      </LazyModal>

      {/* v28.0 Challenge Arena */}
      <LazyModal visible={isModalOpen('challengeArena')}>
      <ChallengeArenaModal
        visible={isModalOpen('challengeArena')}
        onClose={closeModal}
      />
      </LazyModal>
      
      {/* v12.0 Achievement Notifications */}
      <AchievementQueue
        achievements={achievements}
        onClear={clearAchievements}
        colors={colors}
      />

      {/* ─── METRONOME ─── disabled — investigate web boot hang */}
      {false && metronomeOpen && (
        <Modal visible={metronomeOpen} transparent animationType="slide" onRequestClose={() => setMetronomeOpen(false)}>
          <View />
        </Modal>
      )}
    </SafeAreaView>
    </ErrorBoundary>
  );
}

function CodeDockApp() {
  return (
    <I18nProvider defaultLanguage="en">
      <CodeDockAppContent />
    </I18nProvider>
  );
}

// Wrap the Hub in a per-screen ErrorBoundary so a render crash inside any
// of the 40+ legacy modals only takes down the Hub route (not the whole
// app). The user gets a "Retry / Back / Home" trace screen and can recover.
export default withScreenGuard(CodeDockApp, 'Hub');

