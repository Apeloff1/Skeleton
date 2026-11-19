// ============================================================================
// CODEDOCK QUANTUM NEXUS - API HOOK v16.0
// Triple-Buffered Pipeline: Live → Cache → Static
// ============================================================================

import { useState, useEffect, useCallback } from 'react';
import { ApiService, parseError, retryWithBackoff } from '../services/api';
import { traceStep } from '../utils/bootTracer';
import {
  tripleBufferGet,
  tripleBufferPost,
  getPipelineHealth,
  STATIC_FALLBACKS,
  type BufferSource,
  type PipelineHealth,
} from '../services/tripleBuffer';
import {
  Language, Template, CodeFile, AIMode,
  TutorialStep, Tooltip, ConnectionStatus, AppError
} from '../types';

export const useAPI = () => {
  // State - Initialize with static fallback data immediately
  const [languages, setLanguages] = useState<Language[]>(STATIC_FALLBACKS.languages as any);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [files, setFiles] = useState<CodeFile[]>([]);
  const [aiModes, setAIModes] = useState<AIMode[]>(STATIC_FALLBACKS.aiModes as any);
  const [tutorialSteps, setTutorialSteps] = useState<TutorialStep[]>([]);
  const [tooltips, setTooltips] = useState<Record<string, Tooltip>>({});
  const [availableDocks, setAvailableDocks] = useState<Language[]>([]);

  // Connection state - now driven by triple buffer pipeline health
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>('connected');
  const [lastError, setLastError] = useState<AppError | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [dataSource, setDataSource] = useState<BufferSource>('static');
  const [pipelineHealth, setPipelineHealth] = useState<PipelineHealth>(getPipelineHealth());

  // Triple-buffered initial data load — STAGGERED for thermal protection
  const loadInitialData = useCallback(async () => {
    traceStep('hub:loadInitialData_start').catch(() => {});
    setConnectionStatus('reconnecting');
    setIsLoading(true);

    // ── Loading-gate safety valve (2026-06) ──────────────────────────────
    // The Hub already renders with STATIC_FALLBACKS, so we must NEVER keep
    // users on the "Warming up your studio…" screen waiting on the network.
    // When the deployed backend is down/cold (520, hung TCP), each
    // tripleBufferGet can spend ~26s exhausting live retries before falling
    // back to static. Six sequential endpoints = ~150s frozen on the
    // loading screen → Android ANR / force-close ("won't launch"). This
    // timer releases the gate fast; live data hydrates in the background.
    let gateReleased = false;
    const releaseGate = () => {
      if (gateReleased) return;
      gateReleased = true;
      traceStep('hub:loading_gate_released').catch(() => {});
      setIsLoading(false);
    };
    const gateTimer = setTimeout(releaseGate, 3500);

    try {
      // PHASE 1: Critical data (languages + AI modes) — staggered, not parallel
      const langResult = await tripleBufferGet('/api/languages', { languages: STATIC_FALLBACKS.languages });
      // Stutterstep: 100ms buffer between requests to prevent device heat spike
      await new Promise(r => setTimeout(r, 100));
      const aiResult = await tripleBufferGet('/api/ai/modes', { modes: STATIC_FALLBACKS.aiModes });

      // Extract data from results
      const langData = langResult.data;
      const aiData = aiResult.data;

      setLanguages(
        (Array.isArray(langData)
          ? langData
          : (langData?.languages || STATIC_FALLBACKS.languages)) as any
      );
      setAIModes(
        (Array.isArray(aiData)
          ? aiData
          : (aiData?.modes || STATIC_FALLBACKS.aiModes)) as any
      );

      // Determine overall source (worst of the two)
      const source: BufferSource =
        langResult.source === 'static' || aiResult.source === 'static'
          ? 'static'
          : langResult.source === 'cache' || aiResult.source === 'cache'
            ? 'cache'
            : 'live';
      setDataSource(source);

      // Update connection status based on pipeline result
      if (source === 'live') {
        setConnectionStatus('connected');
      } else if (source === 'cache') {
        setConnectionStatus('connected'); // cached data is still usable
      } else {
        setConnectionStatus('disconnected');
      }

      // Critical data resolved (live, cache, OR static) — let the user in NOW.
      releaseGate();

      // Load non-critical data in the BACKGROUND — never gate the UI on it.
      // Each request spaced 100ms apart to prevent CPU/battery spikes.
      (async () => {
        try {
          const tooltipResult = await tripleBufferGet('/api/tooltips', { tooltips: {} });
          setTooltips(tooltipResult.data?.tooltips || {});
          await new Promise(r => setTimeout(r, 100));

          const tutorialResult = await tripleBufferGet('/api/tutorial/steps', { steps: [] });
          setTutorialSteps(tutorialResult.data?.steps || []);
          await new Promise(r => setTimeout(r, 100));

          const dockResult = await tripleBufferGet('/api/docks/available', { docks: [] });
          setAvailableDocks(dockResult.data?.docks || []);
          await new Promise(r => setTimeout(r, 100));

          const filesResult = await tripleBufferGet('/api/files', { files: [] });
          setFiles(filesResult.data?.files || []);
        } catch {
          // Non-critical, continue with defaults
        }
      })();

      setLastError(null);
    } catch (error: any) {
      console.error('Failed to load initial data:', error);
      setConnectionStatus('disconnected');
      setLastError(parseError(error) as any);
      setDataSource('static');

      // Already initialized with static fallbacks in state
    } finally {
      clearTimeout(gateTimer);
      releaseGate();
      setPipelineHealth(getPipelineHealth());
    }
  }, []);

  // Load templates for a language
  const loadTemplates = useCallback(async (language: string) => {
    try {
      const result = await tripleBufferGet(`/api/templates/${language}`, { templates: [] });
      setTemplates(result.data?.templates || []);
    } catch (error) {
      console.error('Failed to load templates:', error);
      setTemplates([]);
    }
  }, []);

  // Refresh files
  const refreshFiles = useCallback(async () => {
    try {
      const result = await tripleBufferGet('/api/files', { files: [] });
      setFiles(result.data?.files || []);
    } catch (error) {
      console.error('Failed to refresh files:', error);
    }
  }, []);

  // Execute code
  const executeCode = useCallback(async (code: string, language: string) => {
    try {
      const result = await ApiService.executeCode(code, language);
      return result;
    } catch (error: any) {
      throw parseError(error);
    }
  }, []);

  // AI Assist
  const aiAssist = useCallback(async (code: string, language: string, mode: string, context?: string) => {
    try {
      const result = await ApiService.aiAssist(code, language, mode, context);
      return result;
    } catch (error: any) {
      throw parseError(error);
    }
  }, []);

  // Save file
  const saveFile = useCallback(async (file: Partial<CodeFile>) => {
    try {
      const saved = await ApiService.saveFile(file);
      await refreshFiles();
      return saved;
    } catch (error: any) {
      throw parseError(error);
    }
  }, [refreshFiles]);

  // Delete file
  const deleteFile = useCallback(async (fileId: string) => {
    try {
      await ApiService.deleteFile(fileId);
      await refreshFiles();
    } catch (error: any) {
      throw parseError(error);
    }
  }, [refreshFiles]);

  // Analyze code
  const analyzeCode = useCallback(async (code: string, language: string) => {
    try {
      const result = await ApiService.analyzeCode(code, language);
      return result;
    } catch (error: any) {
      throw parseError(error);
    }
  }, []);

  // Add addon
  const addAddon = useCallback(async (addon: { name: string; extension: string; description?: string }) => {
    try {
      await ApiService.addLanguageAddon(addon);
      await loadInitialData();
    } catch (error: any) {
      throw parseError(error);
    }
  }, [loadInitialData]);

  return {
    // Data
    languages,
    templates,
    files,
    aiModes,
    tutorialSteps,
    tooltips,
    availableDocks,

    // Status
    connectionStatus,
    lastError,
    isLoading,

    // Triple Buffer Pipeline Status
    dataSource,
    pipelineHealth,

    // Actions
    loadInitialData,
    loadTemplates,
    refreshFiles,
    executeCode,
    aiAssist,
    saveFile,
    deleteFile,
    analyzeCode,
    addAddon,

    // Error handling
    clearError: () => setLastError(null),
  };
};

export default useAPI;
