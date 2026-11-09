/**
 * ╔═══════════════════════════════════════════════════════════════╗
 * ║  GAME FACTORY v17.0 — Full Game Creation + Compile Mode       ║
 * ║  End-to-end game creation system powered by Jeeves + Agents   ║
 * ╚═══════════════════════════════════════════════════════════════╝
 *
 * User describes a game → Jeeves orchestrates 22 agents → Compile → Ship
 */

import { NATIVE_DRIVER } from '../../src/utils/platformStyles';
import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  Modal, TextInput, ActivityIndicator, KeyboardAvoidingView,
  Platform, Animated, Dimensions, Image,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';

import { apiFetch } from '../../utils/apiController';
const API_BASE = (() => {
  if (typeof window !== 'undefined' && (window as any).location?.origin && !(window as any).location.origin.startsWith('file:')) {
    return (window as any).location.origin.replace(/\/+$/, '');
  }
  return (Constants.expoConfig?.extra?.EXPO_PUBLIC_BACKEND_URL as string)
    || process.env.EXPO_PUBLIC_BACKEND_URL || '';
})();

const { width: SCREEN_WIDTH } = Dimensions.get('window');

// ============================================================================
// TYPES
// ============================================================================

interface Genre {
  id: string;
  name: string;
  icon: string;
  color: string;
  description: string;
  engines: string[];
  complexity: string;
}

interface PipelineStep {
  step: number;
  name: string;
  agent: string;
  phase: string;
  description: string;
  icon: string;
  color: string;
  prompt_key: string;
}

interface Project {
  project_id: string;
  description: string;
  genre: string;
  engine: string;
  status: string;
  current_step: number;
  total_steps: number;
  steps_completed: number[];
  gdd: any;
  compiled_output: any;
  created_at: string;
}

interface GameFactoryModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
}

type ScreenView = 'home' | 'create' | 'competitor' | 'analysis' | 'building' | 'compiled' | 'projects';

// ============================================================================
// PHASE COLORS
// ============================================================================

const PHASE_COLORS: Record<string, string> = {
  design: '#8B5CF6',
  engineering: '#3B82F6',
  content: '#F59E0B',
  visual: '#EC4899',
  qa: '#EF4444',
  compile: '#22C55E',
};

// ============================================================================
// PIPELINE PHASE PREVIEW (Collapsible by Phase — handles 200 steps efficiently)
// ============================================================================

const PipelinePhasePreview: React.FC<{ pipeline: PipelineStep[]; colors: any }> = ({ pipeline, colors }) => {
  const [expandedPhases, setExpandedPhases] = useState<Record<string, boolean>>({});

  // Group steps by phase
  const phaseGroups = React.useMemo(() => {
    const groups: Record<string, PipelineStep[]> = {};
    for (const step of pipeline) {
      const phase = step.phase || 'other';
      if (!groups[phase]) groups[phase] = [];
      groups[phase].push(step);
    }
    return groups;
  }, [pipeline]);

  const togglePhase = (phase: string) => {
    setExpandedPhases(prev => ({ ...prev, [phase]: !prev[phase] }));
  };

  const phaseOrder = ['design', 'engineering', 'content', 'visual', 'qa', 'compile'];
  const sortedPhases = Object.keys(phaseGroups).sort(
    (a, b) => (phaseOrder.indexOf(a) === -1 ? 99 : phaseOrder.indexOf(a)) - (phaseOrder.indexOf(b) === -1 ? 99 : phaseOrder.indexOf(b))
  );

  return (
    <View style={[phaseStyles.container, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      {sortedPhases.map(phase => {
        const steps = phaseGroups[phase];
        const isExpanded = expandedPhases[phase];
        const phaseColor = PHASE_COLORS[phase] || '#6B7280';
        return (
          <View key={phase}>
            <TouchableOpacity
              style={[phaseStyles.phaseHeader, { borderBottomColor: isExpanded ? colors.border : 'transparent' }]}
              onPress={() => togglePhase(phase)}
            >
              <View style={[phaseStyles.phaseIndicator, { backgroundColor: phaseColor }]} />
              <View style={phaseStyles.phaseInfo}>
                <Text style={[phaseStyles.phaseName, { color: phaseColor }]}>{phase.toUpperCase()}</Text>
                <Text style={[phaseStyles.phaseCount, { color: colors.textMuted }]}>
                  {steps.length} steps • {steps[0]?.step}–{steps[steps.length - 1]?.step}
                </Text>
              </View>
              <View style={[phaseStyles.phaseCountBadge, { backgroundColor: phaseColor + '20' }]}>
                <Text style={[phaseStyles.phaseCountBadgeText, { color: phaseColor }]}>{steps.length}</Text>
              </View>
              <Ionicons name={isExpanded ? 'chevron-up' : 'chevron-down'} size={18} color={colors.textMuted} />
            </TouchableOpacity>
            {isExpanded && steps.map(step => (
              <View key={step.step} style={phaseStyles.pipelineStep}>
                <View style={[phaseStyles.pipelineDot, { backgroundColor: step.color }]}>
                  <Text style={phaseStyles.pipelineDotText}>{step.step}</Text>
                </View>
                <View style={phaseStyles.pipelineStepInfo}>
                  <Text style={[phaseStyles.pipelineStepName, { color: colors.text }]}>{step.name}</Text>
                  <Text style={[phaseStyles.pipelineStepAgent, { color: step.color }]}>{step.agent}</Text>
                </View>
              </View>
            ))}
          </View>
        );
      })}
    </View>
  );
};

const phaseStyles = StyleSheet.create({
  container: { borderRadius: 14, borderWidth: 1, overflow: 'hidden' },
  phaseHeader: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 14, gap: 10, borderBottomWidth: 0.5 },
  phaseIndicator: { width: 4, height: 28, borderRadius: 2 },
  phaseInfo: { flex: 1 },
  phaseName: { fontSize: 13, fontWeight: '800', letterSpacing: 1 },
  phaseCount: { fontSize: 11, marginTop: 2 },
  phaseCountBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  phaseCountBadgeText: { fontSize: 12, fontWeight: '800' },
  pipelineStep: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 8, gap: 10, borderBottomWidth: 0.5, borderBottomColor: 'rgba(255,255,255,0.04)' },
  pipelineDot: { width: 26, height: 26, borderRadius: 13, justifyContent: 'center', alignItems: 'center' },
  pipelineDotText: { color: '#FFF', fontSize: 10, fontWeight: '700' },
  pipelineStepInfo: { flex: 1 },
  pipelineStepName: { fontSize: 12, fontWeight: '600' },
  pipelineStepAgent: { fontSize: 10, marginTop: 1, fontWeight: '500' },
});

// ============================================================================
// MAIN COMPONENT
// ============================================================================

export const GameFactoryModal: React.FC<GameFactoryModalProps> = ({ visible, onClose, colors }) => {
  const [screen, setScreen] = useState<ScreenView>('home');
  const [genres, setGenres] = useState<Genre[]>([]);
  const [pipeline, setPipeline] = useState<PipelineStep[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(false);

  // Create form
  const [gameDescription, setGameDescription] = useState('');
  const [selectedGenre, setSelectedGenre] = useState<Genre | null>(null);
  const [selectedEngine, setSelectedEngine] = useState('');

  // Build state
  const [currentProject, setCurrentProject] = useState<Project | null>(null);
  const [buildingStep, setBuildingStep] = useState<number | null>(null);
  const [stepResults, setStepResults] = useState<Record<number, any>>({});
  const [compileResult, setCompileResult] = useState<any>(null);
  const [buildLog, setBuildLog] = useState<string[]>([]);
  const [autoBuild, setAutoBuild] = useState(false);

  // Competitor Mode
  const [targetGame, setTargetGame] = useState('');
  const [competitorAnalysis, setCompetitorAnalysis] = useState<any>(null);
  const [oracleKnowledge, setOracleKnowledge] = useState<any>(null);

  // Agent Summary (dynamic from API)
  const [agentSummary, setAgentSummary] = useState<any>(null);

  const scrollRef = useRef<ScrollView>(null);
  const pulseAnim = useRef(new Animated.Value(0)).current;

  // ============================================================================
  // LOAD DATA
  // ============================================================================

  useEffect(() => {
    if (visible) {
      loadGenres();
      loadPipeline();
      loadProjects();
      loadOracleKnowledge();
      loadAgentSummary();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  useEffect(() => {
    if (buildingStep !== null) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 1, duration: 800, useNativeDriver: NATIVE_DRIVER }),
          Animated.timing(pulseAnim, { toValue: 0, duration: 800, useNativeDriver: NATIVE_DRIVER }),
        ])
      ).start();
    } else {
      pulseAnim.setValue(0);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildingStep]);

  // Mobile-safe fetch with timeout and abort controller
  const safeFetch = useCallback(async (url: string, options?: RequestInit & { timeout?: number }) => {
    const controller = new AbortController();
    const timeout = options?.timeout || 10000;
    const timer = setTimeout(() => controller.abort(), timeout);
    try {
      const res = await apiFetch(url, { ...options, signal: controller.signal });
      clearTimeout(timer);
      return res;
    } catch (e: any) {
      clearTimeout(timer);
      if (e.name === 'AbortError') console.log(`[GameFactory] Request timeout: ${url}`);
      return null;
    }
  }, []);

  const loadGenres = useCallback(async () => {
    try {
      const res = await safeFetch(`${API_BASE}/api/game-factory/genres`);
      if (res?.ok) {
        const data = await res.json();
        setGenres(data.genres || []);
      }
    } catch {}
  }, [safeFetch]);

  const loadPipeline = useCallback(async () => {
    try {
      const res = await safeFetch(`${API_BASE}/api/game-factory/pipeline`);
      if (res?.ok) {
        const data = await res.json();
        setPipeline(data.steps || []);
      }
    } catch {}
  }, [safeFetch]);

  const loadProjects = useCallback(async () => {
    try {
      const res = await safeFetch(`${API_BASE}/api/game-factory/projects`);
      if (res?.ok) {
        const data = await res.json();
        setProjects(data.projects || []);
      }
    } catch {}
  }, [safeFetch]);

  const loadOracleKnowledge = useCallback(async () => {
    try {
      const res = await safeFetch(`${API_BASE}/api/game-factory/competitor/knowledge`);
      if (res?.ok) {
        const data = await res.json();
        setOracleKnowledge(data);
      }
    } catch {}
  }, [safeFetch]);

  const loadAgentSummary = useCallback(async () => {
    try {
      const res = await safeFetch(`${API_BASE}/api/game-factory/all-agents-summary`);
      if (res?.ok) {
        const data = await res.json();
        setAgentSummary(data);
      }
    } catch {}
  }, [safeFetch]);

  // ============================================================================
  // COMPETITOR MODE — Oracle Analysis
  // ============================================================================

  const analyzeCompetitor = async () => {
    if (!targetGame.trim()) return;
    setLoading(true);
    setBuildLog([`🔍 Oracle analyzing "${targetGame}"...`, `🧠 Accessing 165,000+ game knowledge base...`]);

    try {
      const res = await apiFetch(`${API_BASE}/api/game-factory/competitor`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_game: targetGame }),
      });

      if (res.ok) {
        const data = await res.json();
        setCompetitorAnalysis(data);

        // Also set up the project for building
        const project: Project = {
          project_id: data.project_id,
          description: `Competitor to ${targetGame}`,
          genre: data.competitor_gdd?.genre || 'custom',
          engine: data.competitor_gdd?.engine || 'Unreal',
          status: data.status,
          current_step: 1,
          total_steps: data.total_steps,
          steps_completed: [1],
          gdd: data.competitor_gdd,
          compiled_output: null,
          created_at: new Date().toISOString(),
        };
        setCurrentProject(project);
        setStepResults({ 1: data.competitor_gdd });
        setBuildLog(prev => [...prev,
          `✅ Oracle analysis complete`,
          `🎮 Target: ${data.target_analysis?.game || targetGame}`,
          `💪 Strengths: ${data.target_analysis?.strengths?.length || 0} identified`,
          `🎯 Weaknesses: ${data.target_analysis?.weaknesses?.length || 0} to exploit`,
          `🏗️ Competitor: ${data.competitor_gdd?.title || 'Untitled'}`,
          `📊 Advantage Score: ${data.competitive_advantage_score || 'N/A'}`,
        ]);
        setScreen('analysis');
      } else {
        setBuildLog(prev => [...prev, `❌ Analysis failed`]);
      }
    } catch (err: any) {
      setBuildLog(prev => [...prev, `❌ Error: ${err.message}`]);
    }
    setLoading(false);
  };

  // ============================================================================
  // CREATE GAME
  // ============================================================================

  const createGame = async () => {
    if (!gameDescription.trim()) return;
    setLoading(true);
    setBuildLog([`🎮 Creating game project...`]);

    try {
      const res = await apiFetch(`${API_BASE}/api/game-factory/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description: gameDescription,
          genre: selectedGenre?.id,
          engine: selectedEngine || undefined,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        const project: Project = {
          project_id: data.project_id,
          description: gameDescription,
          genre: selectedGenre?.id || 'custom',
          engine: selectedEngine,
          status: data.status,
          current_step: data.current_step,
          total_steps: data.total_steps,
          steps_completed: [1],
          gdd: data.gdd,
          compiled_output: null,
          created_at: new Date().toISOString(),
        };
        setCurrentProject(project);
        setStepResults({ 1: data.gdd });
        setBuildLog(prev => [...prev,
          `✅ GDD created by Jeeves`,
          `📋 Game: ${data.gdd?.title || 'Untitled'}`,
          `🎯 Genre: ${data.gdd?.genre || selectedGenre?.name || 'Custom'}`,
        ]);
        setScreen('building');
      } else {
        setBuildLog(prev => [...prev, `❌ Failed to create project`]);
      }
    } catch (err: any) {
      setBuildLog(prev => [...prev, `❌ Error: ${err.message}`]);
    }
    setLoading(false);
  };

  // ============================================================================
  // BUILD STEP
  // ============================================================================

  const executeBuildStep = async (stepNum?: number) => {
    if (!currentProject) return;
    const targetStep = stepNum || ((currentProject.current_step || 1) + 1);

    if (targetStep > pipeline.length) {
      setBuildLog(prev => [...prev, `🏁 All steps complete! Ready to compile.`]);
      return;
    }

    const stepDef = pipeline[targetStep - 1];
    if (!stepDef) return;

    setBuildingStep(targetStep);
    setBuildLog(prev => [...prev, `🔨 Step ${targetStep}: ${stepDef.name} (${stepDef.agent})...`]);

    try {
      const res = await apiFetch(`${API_BASE}/api/game-factory/build-step`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: currentProject.project_id,
          step_number: targetStep,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setStepResults(prev => ({ ...prev, [targetStep]: data.result }));
        setCurrentProject(prev => prev ? ({
          ...prev,
          current_step: targetStep,
          steps_completed: [...(prev.steps_completed || []), targetStep],
          status: data.status,
        }) : null);
        setBuildLog(prev => [...prev,
          `✅ ${stepDef.name} complete`,
          data.result?.success ? `   📦 Agent ${stepDef.agent} delivered` : `   ⚠️ Fallback used`,
        ]);

        // Holodeck render result
        if (data.holodeck_render?.success && data.holodeck_render?.image_url) {
          setBuildLog(prev => [...prev,
            `   🎨 Holodeck rendered: ${stepDef.name}`,
          ]);
        }
      } else {
        setBuildLog(prev => [...prev, `❌ Step ${targetStep} failed`]);
      }
    } catch (err: any) {
      setBuildLog(prev => [...prev, `❌ Error: ${err.message}`]);
    }

    setBuildingStep(null);
  };

  // ============================================================================
  // AUTO BUILD (all steps sequentially)
  // ============================================================================

  const startAutoBuild = async () => {
    if (!currentProject) return;
    setAutoBuild(true);

    const completed = currentProject.steps_completed || [];
    for (let i = 1; i <= pipeline.length; i++) {
      if (completed.includes(i)) continue;
      await executeBuildStep(i);
      // Small delay between steps for visual effect
      await new Promise(r => setTimeout(r, 500));
    }

    setAutoBuild(false);
    setBuildLog(prev => [...prev, `\n🏁 All pipeline steps complete!`, `🔧 Ready for FULL COMPILE MODE`]);
  };

  // ============================================================================
  // COMPILE
  // ============================================================================

  const compileGame = async () => {
    if (!currentProject) return;
    setBuildingStep(-1); // Special compile indicator
    setBuildLog(prev => [...prev, `\n⚡ FULL COMPILE MODE ACTIVATED`, `🔧 Jeeves assembling all systems...`]);

    try {
      const res = await apiFetch(`${API_BASE}/api/game-factory/compile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project_id: currentProject.project_id }),
      });

      if (res.ok) {
        const data = await res.json();
        setCompileResult(data.compilation);
        setCurrentProject(prev => prev ? ({ ...prev, status: 'compiled' }) : null);
        setBuildLog(prev => [...prev,
          `✅ COMPILATION ${data.compilation?.compilation_status || 'COMPLETE'}`,
          `📦 ${data.steps_used} systems assembled`,
          data.compilation?.aaa_certified ? `🏆 AAA CERTIFIED` : `⚠️ Review needed`,
        ]);
        setScreen('compiled');
      } else {
        setBuildLog(prev => [...prev, `❌ Compilation failed`]);
      }
    } catch (err: any) {
      setBuildLog(prev => [...prev, `❌ Compile error: ${err.message}`]);
    }

    setBuildingStep(null);
  };

  // ============================================================================
  // LOAD EXISTING PROJECT
  // ============================================================================

  const loadProject = async (projectId: string) => {
    setLoading(true);
    try {
      const res = await apiFetch(`${API_BASE}/api/game-factory/project/${projectId}`);
      if (res.ok) {
        const data = await res.json();
        setCurrentProject(data);
        setStepResults({});

        if (data.compiled_output) {
          setCompileResult(data.compiled_output);
          setScreen('compiled');
        } else {
          setBuildLog([`📂 Loaded project: ${data.gdd?.title || projectId}`]);
          setScreen('building');
        }
      }
    } catch {}
    setLoading(false);
  };

  // ============================================================================
  // RENDER: HOME SCREEN
  // ============================================================================

  const renderHome = () => {
    const totalAgents = agentSummary?.grand_total_with_all_layers || 25994;
    const totalSteps = pipeline.length || 200;
    const totalGenres = genres.length || 52;
    const qualityLayers = agentSummary?.quality_layers || {};
    const layerColors: Record<string, string> = {
      originals: '#8B5CF6', shadows: '#6366F1', ghosts: '#A855F7',
      angels: '#F59E0B', seraphim: '#EC4899', cherubim: '#D4A574',
    };
    const layerIcons: Record<string, string> = {
      originals: 'people', shadows: 'eye', ghosts: 'skull',
      angels: 'shield-checkmark', seraphim: 'sparkles', cherubim: 'flame',
    };

    return (
    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
      {/* Hero Section */}
      <View style={[styles.heroCard, { backgroundColor: '#8B5CF610', borderColor: '#8B5CF630' }]}>
        <View style={[styles.heroIconWrap, { backgroundColor: '#8B5CF620' }]}>
          <Ionicons name="game-controller" size={36} color="#8B5CF6" />
        </View>
        <Text style={[styles.heroTitle, { color: colors.text }]}>Game Factory</Text>
        <Text style={[styles.heroSub, { color: colors.textMuted }]}>
          Describe your game. {totalAgents.toLocaleString()} AI agents (Hexa-Layer) build it to AAA.
        </Text>
        <View style={styles.heroStats}>
          <View style={styles.heroStat}>
            <Text style={[styles.heroStatNum, { color: '#8B5CF6' }]}>{totalAgents.toLocaleString()}</Text>
            <Text style={[styles.heroStatLabel, { color: colors.textMuted }]}>Agents</Text>
          </View>
          <View style={styles.heroStat}>
            <Text style={[styles.heroStatNum, { color: '#3B82F6' }]}>{totalSteps}</Text>
            <Text style={[styles.heroStatLabel, { color: colors.textMuted }]}>Pipeline Steps</Text>
          </View>
          <View style={styles.heroStat}>
            <Text style={[styles.heroStatNum, { color: '#22C55E' }]}>{totalGenres}</Text>
            <Text style={[styles.heroStatLabel, { color: colors.textMuted }]}>Genres</Text>
          </View>
        </View>
      </View>

      {/* Quality Layers Breakdown */}
      {Object.keys(qualityLayers).length > 0 && (
        <View style={[styles.layersCard, { borderColor: '#333' }]}>
          <Text style={[styles.layersTitle, { color: colors.text }]}>Hexa-Layer Architecture</Text>
          {Object.entries(qualityLayers).map(([key, layer]: [string, any]) => (
            <View key={key} style={styles.layerRow}>
              <View style={[styles.layerIcon, { backgroundColor: (layerColors[key] || '#666') + '20' }]}>
                <Ionicons name={(layerIcons[key] || 'ellipse') as any} size={16} color={layerColors[key] || '#666'} />
              </View>
              <View style={styles.layerInfo}>
                <Text style={[styles.layerName, { color: colors.text }]}>{key.charAt(0).toUpperCase() + key.slice(1)}</Text>
                <Text style={[styles.layerPurpose, { color: colors.textMuted }]} numberOfLines={1}>{layer.purpose}</Text>
              </View>
              <Text style={[styles.layerCount, { color: layerColors[key] || '#666' }]}>{(layer.count || 0).toLocaleString()}</Text>
            </View>
          ))}
          <View style={styles.layerTotalRow}>
            <Text style={[styles.layerTotalLabel, { color: colors.textMuted }]}>Grand Total</Text>
            <Text style={[styles.layerTotalCount, { color: '#8B5CF6' }]}>{totalAgents.toLocaleString()}</Text>
          </View>
        </View>
      )}

      {/* Action Buttons */}
      <TouchableOpacity
        style={[styles.primaryBtn, { backgroundColor: '#8B5CF6' }]}
        onPress={() => setScreen('create')}
      >
        <Ionicons name="add-circle" size={22} color="#FFF" />
        <Text style={styles.primaryBtnText}>Create New Game</Text>
        <Ionicons name="arrow-forward" size={18} color="#FFF" />
      </TouchableOpacity>

      {/* Competitor Mode Button */}
      <TouchableOpacity
        style={[styles.primaryBtn, { backgroundColor: '#EF4444', marginTop: 8 }]}
        onPress={() => setScreen('competitor')}
      >
        <Ionicons name="eye" size={22} color="#FFF" />
        <Text style={styles.primaryBtnText}>Competitor Mode</Text>
        <Ionicons name="flash" size={18} color="#FFF" />
      </TouchableOpacity>

      {/* Recent Projects */}
      {projects.length > 0 && (
        <>
          <Text style={[styles.sectionTitle, { color: colors.text }]}>Recent Projects</Text>
          {projects.slice(0, 5).map(p => (
            <TouchableOpacity
              key={p.project_id}
              style={[styles.projectCard, { backgroundColor: colors.surface, borderColor: colors.border }]}
              onPress={() => loadProject(p.project_id)}
            >
              <View style={[styles.projectIcon, { backgroundColor: getStatusColor(p.status) + '20' }]}>
                <Ionicons name={getStatusIcon(p.status)} size={20} color={getStatusColor(p.status)} />
              </View>
              <View style={styles.projectInfo}>
                <Text style={[styles.projectName, { color: colors.text }]} numberOfLines={1}>
                  {p.gdd?.title || p.description?.substring(0, 40) || 'Untitled'}
                </Text>
                <Text style={[styles.projectMeta, { color: colors.textMuted }]}>
                  {p.genre} • {p.status} • Step {p.current_step}/{p.total_steps}
                </Text>
              </View>
              <View style={[styles.statusDot, { backgroundColor: getStatusColor(p.status) }]} />
            </TouchableOpacity>
          ))}
        </>
      )}

      {/* Pipeline Preview (Collapsible by Phase) */}
      <Text style={[styles.sectionTitle, { color: colors.text }]}>Build Pipeline</Text>
      <PipelinePhasePreview pipeline={pipeline} colors={colors} />

      <View style={{ height: 40 }} />
    </ScrollView>
    );
  };

  // ============================================================================
  // RENDER: CREATE SCREEN
  // ============================================================================

  const renderCreate = () => (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Describe Your Game</Text>
        <TextInput
          value={gameDescription}
          onChangeText={setGameDescription}
          placeholder="e.g. A dark fantasy RPG with turn-based combat, branching dialogue, and an open world to explore..."
          placeholderTextColor={colors.textMuted}
          style={[styles.descInput, { color: colors.text, backgroundColor: colors.surface, borderColor: colors.border }]}
          multiline
          numberOfLines={4}
          maxLength={2000}
          textAlignVertical="top"
        />
        <Text style={[styles.charCount, { color: colors.textMuted }]}>{gameDescription.length}/2000</Text>

        {/* Genre Selection */}
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Select Genre</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.genreScroll}>
          {genres.map(g => (
            <TouchableOpacity
              key={g.id}
              style={[
                styles.genreChip,
                { backgroundColor: selectedGenre?.id === g.id ? g.color + '30' : colors.surface, borderColor: selectedGenre?.id === g.id ? g.color : colors.border }
              ]}
              onPress={() => {
                setSelectedGenre(selectedGenre?.id === g.id ? null : g);
                if (g.engines?.length > 0) setSelectedEngine(g.engines[0]);
              }}
            >
              <Ionicons name={g.icon as any} size={16} color={selectedGenre?.id === g.id ? g.color : colors.textMuted} />
              <Text style={[styles.genreChipText, { color: selectedGenre?.id === g.id ? g.color : colors.text }]}>
                {g.name}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* Engine Selection */}
        {selectedGenre && (
          <>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>Engine</Text>
            <View style={styles.engineRow}>
              {selectedGenre.engines.map(eng => (
                <TouchableOpacity
                  key={eng}
                  style={[
                    styles.engineChip,
                    { backgroundColor: selectedEngine === eng ? '#3B82F630' : colors.surface, borderColor: selectedEngine === eng ? '#3B82F6' : colors.border }
                  ]}
                  onPress={() => setSelectedEngine(eng)}
                >
                  <Text style={[styles.engineChipText, { color: selectedEngine === eng ? '#3B82F6' : colors.text }]}>
                    {eng}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </>
        )}

        {/* Build Button */}
        <TouchableOpacity
          style={[styles.buildBtn, { backgroundColor: gameDescription.trim() ? '#22C55E' : colors.border, opacity: gameDescription.trim() ? 1 : 0.5 }]}
          onPress={createGame}
          disabled={!gameDescription.trim() || loading}
        >
          {loading ? (
            <ActivityIndicator color="#FFF" />
          ) : (
            <>
              <Ionicons name="rocket" size={22} color="#FFF" />
              <Text style={styles.buildBtnText}>Build Game</Text>
            </>
          )}
        </TouchableOpacity>

        <View style={{ height: 40 }} />
      </ScrollView>
    </KeyboardAvoidingView>
  );

  // ============================================================================
  // RENDER: BUILDING SCREEN
  // ============================================================================

  const renderBuilding = () => {
    const completed = currentProject?.steps_completed || [];
    const progress = completed.length / pipeline.length;

    return (
      <ScrollView ref={scrollRef} style={styles.content} showsVerticalScrollIndicator={false}>
        {/* Project Header */}
        <View style={[styles.buildHeader, { backgroundColor: '#8B5CF610', borderColor: '#8B5CF630' }]}>
          <Text style={[styles.buildTitle, { color: colors.text }]} numberOfLines={1}>
            {currentProject?.gdd?.title || 'Building Game...'}
          </Text>
          <Text style={[styles.buildMeta, { color: colors.textMuted }]}>
            {currentProject?.genre} • {currentProject?.engine} • {completed.length}/{pipeline.length} steps
          </Text>

          {/* Progress Bar */}
          <View style={[styles.progressBar, { backgroundColor: colors.border }]}>
            <View style={[styles.progressFill, { width: `${Math.max(5, progress * 100)}%`, backgroundColor: progress >= 1 ? '#22C55E' : '#8B5CF6' }]} />
          </View>
        </View>

        {/* Pipeline Steps */}
        {pipeline.map((step) => {
          const isCompleted = completed.includes(step.step);
          const isBuilding = buildingStep === step.step;
          const isNext = !isCompleted && step.step === (Math.max(...completed, 0) + 1);

          return (
            <View key={step.step} style={[
              styles.stepCard,
              {
                backgroundColor: isBuilding ? step.color + '15' : isCompleted ? '#22C55E08' : colors.surface,
                borderColor: isBuilding ? step.color : isCompleted ? '#22C55E40' : colors.border,
              }
            ]}>
              <View style={styles.stepHeader}>
                <View style={[styles.stepNum, { backgroundColor: isCompleted ? '#22C55E' : isBuilding ? step.color : colors.border }]}>
                  {isCompleted ? (
                    <Ionicons name="checkmark" size={14} color="#FFF" />
                  ) : isBuilding ? (
                    <Animated.View style={{ opacity: pulseAnim }}>
                      <ActivityIndicator size="small" color="#FFF" />
                    </Animated.View>
                  ) : (
                    <Text style={styles.stepNumText}>{step.step}</Text>
                  )}
                </View>
                <View style={styles.stepInfo}>
                  <Text style={[styles.stepName, { color: isBuilding ? step.color : colors.text }]}>{step.name}</Text>
                  <Text style={[styles.stepAgent, { color: colors.textMuted }]}>{step.description}</Text>
                </View>
                <View style={[styles.phaseBadge, { backgroundColor: PHASE_COLORS[step.phase] + '15' }]}>
                  <Text style={[styles.phaseBadgeText, { color: PHASE_COLORS[step.phase], fontSize: 9 }]}>{step.phase}</Text>
                </View>
              </View>

              {/* Step Result Preview */}
              {isCompleted && stepResults[step.step] && (
                <View style={[styles.stepResult, { backgroundColor: '#1E1E2E', borderColor: '#333' }]}>
                  <Text style={styles.stepResultText} numberOfLines={4}>
                    {typeof stepResults[step.step] === 'string'
                      ? stepResults[step.step].substring(0, 200)
                      : JSON.stringify(stepResults[step.step], null, 2).substring(0, 200)}...
                  </Text>
                </View>
              )}

              {/* Holodeck Render Image */}
              {isCompleted && stepResults[step.step]?.holodeck_render?.success && stepResults[step.step]?.holodeck_render?.image_url && (
                <View style={[styles.holodeckRenderCard, { borderColor: '#00D4FF40' }]}>
                  <View style={styles.holodeckRenderHeader}>
                    <Ionicons name="image" size={14} color="#00D4FF" />
                    <Text style={styles.holodeckRenderLabel}>Holodeck Render</Text>
                  </View>
                  <Image
                    source={{ uri: stepResults[step.step].holodeck_render.image_url }}
                    style={styles.holodeckRenderImage}
                    resizeMode="cover"
                  />
                </View>
              )}

              {/* Build This Step */}
              {isNext && !autoBuild && (
                <TouchableOpacity
                  style={[styles.stepBuildBtn, { backgroundColor: step.color }]}
                  onPress={() => executeBuildStep(step.step)}
                  disabled={buildingStep !== null}
                >
                  <Ionicons name="play" size={14} color="#FFF" />
                  <Text style={styles.stepBuildBtnText}>Build This Step</Text>
                </TouchableOpacity>
              )}
            </View>
          );
        })}

        {/* Auto Build & Compile Buttons */}
        <View style={styles.actionRow}>
          {completed.length < pipeline.length && (
            <TouchableOpacity
              style={[styles.autoBuildBtn, { backgroundColor: '#3B82F6', opacity: buildingStep !== null ? 0.5 : 1 }]}
              onPress={startAutoBuild}
              disabled={buildingStep !== null || autoBuild}
            >
              {autoBuild ? (
                <ActivityIndicator color="#FFF" size="small" />
              ) : (
                <Ionicons name="play-circle" size={20} color="#FFF" />
              )}
              <Text style={styles.autoBuildBtnText}>
                {autoBuild ? 'Building...' : 'Auto-Build All'}
              </Text>
            </TouchableOpacity>
          )}

          {completed.length >= 2 && (
            <TouchableOpacity
              style={[styles.compileBtnLarge, { backgroundColor: '#22C55E', opacity: buildingStep !== null ? 0.5 : 1 }]}
              onPress={compileGame}
              disabled={buildingStep !== null}
            >
              <Ionicons name="build" size={20} color="#FFF" />
              <Text style={styles.compileBtnLargeText}>COMPILE GAME</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Build Log */}
        {buildLog.length > 0 && (
          <View style={[styles.buildLogCard, { backgroundColor: '#0D1117', borderColor: '#21262D' }]}>
            <View style={styles.buildLogHeader}>
              <Ionicons name="terminal" size={14} color="#8B949E" />
              <Text style={styles.buildLogTitle}>Build Log</Text>
            </View>
            {buildLog.map((log, i) => (
              <Text key={i} style={styles.buildLogLine}>{log}</Text>
            ))}
          </View>
        )}

        <View style={{ height: 40 }} />
      </ScrollView>
    );
  };

  // ============================================================================
  // RENDER: COMPILED OUTPUT
  // ============================================================================

  const renderCompiled = () => (
    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
      {/* Celebration Header */}
      <View style={[styles.compileHeader, { backgroundColor: '#22C55E10', borderColor: '#22C55E30' }]}>
        <View style={[styles.compileIconWrap, { backgroundColor: '#22C55E20' }]}>
          <Ionicons name="checkmark-done-circle" size={48} color="#22C55E" />
        </View>
        <Text style={[styles.compileTitle, { color: colors.text }]}>Game Compiled!</Text>
        <Text style={[styles.compileSub, { color: colors.textMuted }]}>
          {currentProject?.gdd?.title || 'Your Game'} is ready
        </Text>
        {compileResult?.aaa_certified && (
          <View style={[styles.aaaBadge, { backgroundColor: '#F59E0B20', borderColor: '#F59E0B' }]}>
            <Ionicons name="star" size={16} color="#F59E0B" />
            <Text style={styles.aaaBadgeText}>AAA Certified</Text>
          </View>
        )}
      </View>

      {/* Project Structure */}
      {compileResult?.project_structure?.files && (
        <View style={[styles.compileSection, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <Text style={[styles.compileSectionTitle, { color: colors.text }]}>Project Structure</Text>
          {compileResult.project_structure.files.map((f: any, i: number) => (
            <View key={i} style={styles.fileRow}>
              <Ionicons name="document-text" size={14} color="#3B82F6" />
              <Text style={[styles.fileName, { color: colors.text }]}>{f.path}</Text>
              <Text style={[styles.fileDesc, { color: colors.textMuted }]}>{f.description}</Text>
            </View>
          ))}
        </View>
      )}

      {/* Main Code */}
      {(compileResult?.main_entry_code || compileResult?.engine_code) && (
        <View style={[styles.compileSection, { backgroundColor: '#0D1117', borderColor: '#21262D' }]}>
          <Text style={[styles.compileSectionTitle, { color: '#E6EDF3' }]}>Game Code</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <Text style={styles.codeOutput}>
              {(compileResult.main_entry_code || compileResult.engine_code || '').substring(0, 3000)}
            </Text>
          </ScrollView>
        </View>
      )}

      {/* Build Instructions */}
      {compileResult?.build_instructions && (
        <View style={[styles.compileSection, { backgroundColor: colors.surface, borderColor: colors.border }]}>
          <Text style={[styles.compileSectionTitle, { color: colors.text }]}>Build Instructions</Text>
          <Text style={[styles.instructions, { color: colors.text }]}>{compileResult.build_instructions}</Text>
        </View>
      )}

      {/* Raw Output */}
      {compileResult?._raw && (
        <View style={[styles.compileSection, { backgroundColor: '#0D1117', borderColor: '#21262D' }]}>
          <Text style={[styles.compileSectionTitle, { color: '#E6EDF3' }]}>Full Compile Output</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <Text style={styles.codeOutput}>
              {compileResult._raw.substring(0, 5000)}
            </Text>
          </ScrollView>
        </View>
      )}

      {/* Back to Build */}
      <TouchableOpacity
        style={[styles.primaryBtn, { backgroundColor: '#3B82F6', marginTop: 16 }]}
        onPress={() => setScreen('building')}
      >
        <Ionicons name="arrow-back" size={18} color="#FFF" />
        <Text style={styles.primaryBtnText}>Back to Pipeline</Text>
      </TouchableOpacity>

      <TouchableOpacity
        style={[styles.primaryBtn, { backgroundColor: '#8B5CF6', marginTop: 8 }]}
        onPress={() => {
          setScreen('home');
          setCurrentProject(null);
          setCompileResult(null);
          setStepResults({});
          setBuildLog([]);
          setGameDescription('');
          setSelectedGenre(null);
          loadProjects();
        }}
      >
        <Ionicons name="add-circle" size={18} color="#FFF" />
        <Text style={styles.primaryBtnText}>Create Another Game</Text>
      </TouchableOpacity>

      <View style={{ height: 40 }} />
    </ScrollView>
  );

  // ============================================================================
  // RENDER: COMPETITOR MODE SCREEN
  // ============================================================================

  const renderCompetitor = () => (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {/* Oracle Hero */}
        <View style={[styles.heroCard, { backgroundColor: '#EF444410', borderColor: '#EF444430' }]}>
          <View style={[styles.heroIconWrap, { backgroundColor: '#EF444420' }]}>
            <Ionicons name="eye" size={36} color="#EF4444" />
          </View>
          <Text style={[styles.heroTitle, { color: colors.text }]}>Competitor Mode</Text>
          <Text style={[styles.heroSub, { color: colors.textMuted }]}>
            Oracle analyzes any game and designs a superior competitor. 165,000+ games in knowledge base.
          </Text>
        </View>

        {/* Target Game Input */}
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Target Game</Text>
        <TextInput
          value={targetGame}
          onChangeText={setTargetGame}
          placeholder='e.g. "Minecraft", "Elden Ring", "Stardew Valley"...'
          placeholderTextColor={colors.textMuted}
          style={[styles.descInput, { color: colors.text, backgroundColor: colors.surface, borderColor: colors.border, minHeight: 56 }]}
          maxLength={200}
        />

        {/* Oracle Knowledge Preview */}
        {oracleKnowledge?.famous_analyses && (
          <>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>Oracle&apos;s Famous Analyses</Text>
            {oracleKnowledge.famous_analyses.map((a: any, i: number) => (
              <TouchableOpacity
                key={i}
                style={[styles.projectCard, { backgroundColor: colors.surface, borderColor: colors.border }]}
                onPress={() => setTargetGame(a.game)}
              >
                <View style={[styles.projectIcon, { backgroundColor: '#EF444420' }]}>
                  <Ionicons name="game-controller" size={18} color="#EF4444" />
                </View>
                <View style={styles.projectInfo}>
                  <Text style={[styles.projectName, { color: colors.text }]}>{a.game}</Text>
                  <Text style={[styles.projectMeta, { color: colors.textMuted }]} numberOfLines={2}>{a.key_insight}</Text>
                </View>
              </TouchableOpacity>
            ))}
          </>
        )}

        {/* Analyze Button */}
        <TouchableOpacity
          style={[styles.buildBtn, { backgroundColor: targetGame.trim() ? '#EF4444' : colors.border, opacity: targetGame.trim() ? 1 : 0.5 }]}
          onPress={analyzeCompetitor}
          disabled={!targetGame.trim() || loading}
        >
          {loading ? (
            <ActivityIndicator color="#FFF" />
          ) : (
            <>
              <Ionicons name="eye" size={22} color="#FFF" />
              <Text style={styles.buildBtnText}>Analyze & Design Competitor</Text>
            </>
          )}
        </TouchableOpacity>

        <View style={{ height: 40 }} />
      </ScrollView>
    </KeyboardAvoidingView>
  );

  // ============================================================================
  // RENDER: ANALYSIS RESULTS SCREEN
  // ============================================================================

  const renderAnalysis = () => {
    const analysis = competitorAnalysis?.target_analysis || {};
    const gdd = competitorAnalysis?.competitor_gdd || {};
    const howWeBeat = gdd.how_we_beat_them || [];

    return (
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {/* Analysis Header */}
        <View style={[styles.heroCard, { backgroundColor: '#EF444410', borderColor: '#EF444430' }]}>
          <View style={[styles.heroIconWrap, { backgroundColor: '#EF444420' }]}>
            <Ionicons name="analytics" size={36} color="#EF4444" />
          </View>
          <Text style={[styles.heroTitle, { color: colors.text }]}>{analysis.game || targetGame}</Text>
          <Text style={[styles.heroSub, { color: colors.textMuted }]}>
            {analysis.genre || ''} {analysis.developer ? `by ${analysis.developer}` : ''} {analysis.release_year ? `(${analysis.release_year})` : ''}
          </Text>
          {analysis.metacritic && (
            <View style={[styles.aaaBadge, { backgroundColor: '#F59E0B20', borderColor: '#F59E0B' }]}>
              <Ionicons name="star" size={14} color="#F59E0B" />
              <Text style={styles.aaaBadgeText}>Metacritic: {analysis.metacritic}</Text>
            </View>
          )}
        </View>

        {/* Strengths */}
        {analysis.strengths?.length > 0 && (
          <View style={[styles.compileSection, { backgroundColor: '#22C55E08', borderColor: '#22C55E30' }]}>
            <Text style={[styles.compileSectionTitle, { color: '#22C55E' }]}>Strengths</Text>
            {analysis.strengths.map((s: string, i: number) => (
              <View key={i} style={styles.fileRow}>
                <Ionicons name="checkmark-circle" size={14} color="#22C55E" />
                <Text style={[styles.fileName, { color: colors.text }]}>{s}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Weaknesses */}
        {analysis.weaknesses?.length > 0 && (
          <View style={[styles.compileSection, { backgroundColor: '#EF444408', borderColor: '#EF444430' }]}>
            <Text style={[styles.compileSectionTitle, { color: '#EF4444' }]}>Weaknesses to Exploit</Text>
            {analysis.weaknesses.map((w: string, i: number) => (
              <View key={i} style={styles.fileRow}>
                <Ionicons name="alert-circle" size={14} color="#EF4444" />
                <Text style={[styles.fileName, { color: colors.text }]}>{w}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Competitor GDD */}
        <View style={[styles.heroCard, { backgroundColor: '#8B5CF610', borderColor: '#8B5CF630', marginTop: 16 }]}>
          <Text style={[styles.heroTitle, { color: '#8B5CF6', fontSize: 20 }]}>Our Competitor</Text>
          <Text style={[styles.heroTitle, { color: colors.text }]}>{gdd.title || 'Untitled'}</Text>
          <Text style={[styles.heroSub, { color: colors.textMuted }]}>{gdd.tagline || ''}</Text>
        </View>

        {gdd.overview && (
          <View style={[styles.compileSection, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <Text style={[styles.compileSectionTitle, { color: colors.text }]}>Overview</Text>
            <Text style={[styles.instructions, { color: colors.text }]}>{gdd.overview}</Text>
          </View>
        )}

        {/* How We Beat Them */}
        {howWeBeat.length > 0 && (
          <View style={[styles.compileSection, { backgroundColor: '#8B5CF608', borderColor: '#8B5CF630' }]}>
            <Text style={[styles.compileSectionTitle, { color: '#8B5CF6' }]}>How We Beat Them</Text>
            {howWeBeat.map((h: any, i: number) => (
              <View key={i} style={[styles.beatCard, { borderBottomColor: colors.border }]}>
                <Text style={[styles.beatArea, { color: '#8B5CF6' }]}>{h.area}</Text>
                <View style={styles.beatRow}>
                  <View style={styles.beatCol}>
                    <Text style={[styles.beatLabel, { color: '#EF4444' }]}>Them</Text>
                    <Text style={[styles.beatText, { color: colors.textMuted }]}>{h.their_approach}</Text>
                  </View>
                  <Ionicons name="arrow-forward" size={16} color={colors.textMuted} />
                  <View style={styles.beatCol}>
                    <Text style={[styles.beatLabel, { color: '#22C55E' }]}>Us</Text>
                    <Text style={[styles.beatText, { color: colors.text }]}>{h.our_approach}</Text>
                  </View>
                </View>
                <Text style={[styles.beatWhy, { color: '#22C55E' }]}>{h.why_ours_is_better}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Innovations */}
        {gdd.innovations?.length > 0 && (
          <View style={[styles.compileSection, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            <Text style={[styles.compileSectionTitle, { color: colors.text }]}>Innovations</Text>
            {gdd.innovations.map((inn: string, i: number) => (
              <View key={i} style={styles.fileRow}>
                <Ionicons name="bulb" size={14} color="#F59E0B" />
                <Text style={[styles.fileName, { color: colors.text }]}>{inn}</Text>
              </View>
            ))}
          </View>
        )}

        {/* Build This Competitor */}
        <TouchableOpacity
          style={[styles.buildBtn, { backgroundColor: '#22C55E', marginTop: 16 }]}
          onPress={() => {
            setBuildLog(prev => [...prev, `\n🏗️ Starting build pipeline for competitor...`]);
            setScreen('building');
          }}
        >
          <Ionicons name="build" size={22} color="#FFF" />
          <Text style={styles.buildBtnText}>Build This Competitor</Text>
        </TouchableOpacity>

        {/* Build Log */}
        {buildLog.length > 0 && (
          <View style={[styles.buildLogCard, { backgroundColor: '#0D1117', borderColor: '#21262D' }]}>
            <View style={styles.buildLogHeader}>
              <Ionicons name="terminal" size={14} color="#8B949E" />
              <Text style={styles.buildLogTitle}>Oracle Log</Text>
            </View>
            {buildLog.map((log, i) => (
              <Text key={i} style={styles.buildLogLine}>{log}</Text>
            ))}
          </View>
        )}

        <View style={{ height: 40 }} />
      </ScrollView>
    );
  };

  // ============================================================================
  // HELPERS
  // ============================================================================

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'compiled': return '#22C55E';
      case 'ready_to_compile': return '#F59E0B';
      case 'in_progress': return '#3B82F6';
      case 'designing': return '#8B5CF6';
      default: return '#6B7280';
    }
  };

  const getStatusIcon = (status: string): any => {
    switch (status) {
      case 'compiled': return 'checkmark-circle';
      case 'ready_to_compile': return 'build';
      case 'in_progress': return 'construct';
      case 'designing': return 'document-text';
      default: return 'ellipsis-horizontal';
    }
  };

  const getHeaderTitle = () => {
    switch (screen) {
      case 'home': return 'Game Factory';
      case 'create': return 'New Game';
      case 'competitor': return 'Competitor Mode';
      case 'analysis': return `vs ${targetGame}`;
      case 'building': return currentProject?.gdd?.title || 'Building...';
      case 'compiled': return 'Compiled!';
      case 'projects': return 'My Projects';
      default: return 'Game Factory';
    }
  };

  // ============================================================================
  // MAIN RENDER
  // ============================================================================

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={[styles.overlay, { backgroundColor: colors.background }]}>
        {/* Header */}
        <View style={[styles.header, { borderBottomColor: colors.border }]}>
          <TouchableOpacity
            onPress={() => {
              if (screen === 'home') {
                onClose();
              } else if (screen === 'compiled') {
                setScreen('building');
              } else if (screen === 'analysis') {
                setScreen('competitor');
              } else if (screen === 'building' || screen === 'create' || screen === 'competitor') {
                setScreen('home');
              }
            }}
            style={styles.backBtn}
          >
            <Ionicons name={screen === 'home' ? 'close' : 'arrow-back'} size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerCenter}>
            <Text style={[styles.headerTitle, { color: colors.text }]}>{getHeaderTitle()}</Text>
            <Text style={[styles.headerSub, { color: colors.textMuted }]}>
              {screen === 'building'
                ? `${currentProject?.steps_completed?.length || 0}/${pipeline.length} steps • ${currentProject?.status}`
                : `${(agentSummary?.grand_total_with_all_layers || 25994).toLocaleString()} Agents (Hexa-Layer: Originals + Shadows + Ghosts + Angels + Seraphim + Cherubim) • ${pipeline.length || 200} Steps • ${genres.length || 52} Genres`}
            </Text>
          </View>
          {screen === 'building' && currentProject?.status !== 'compiled' && (
            <TouchableOpacity
              style={[styles.compileBtn, { backgroundColor: '#22C55E' }]}
              onPress={compileGame}
              disabled={buildingStep !== null}
            >
              <Ionicons name="build" size={16} color="#FFF" />
            </TouchableOpacity>
          )}
        </View>

        {/* Content */}
        {loading ? (
          <View style={styles.loadingView}>
            <ActivityIndicator size="large" color={colors.primary} />
            <Text style={[styles.loadingText, { color: colors.textMuted }]}>Creating your game...</Text>
          </View>
        ) : (
          <>
            {screen === 'home' && renderHome()}
            {screen === 'create' && renderCreate()}
            {screen === 'competitor' && renderCompetitor()}
            {screen === 'analysis' && renderAnalysis()}
            {screen === 'building' && renderBuilding()}
            {screen === 'compiled' && renderCompiled()}
          </>
        )}
      </View>
    </Modal>
  );
};

// ============================================================================
// STYLES
// ============================================================================

const styles = StyleSheet.create({
  overlay: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1 },
  backBtn: { padding: 4 },
  headerCenter: { flex: 1, marginLeft: 12 },
  headerTitle: { fontSize: 18, fontWeight: '700' },
  headerSub: { fontSize: 11, marginTop: 2 },
  compileBtn: { width: 40, height: 40, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
  loadingView: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 12 },
  loadingText: { fontSize: 14 },
  content: { flex: 1, paddingHorizontal: 16 },

  // Hero
  heroCard: { alignItems: 'center', padding: 24, borderRadius: 20, marginTop: 16, borderWidth: 1, gap: 10 },
  heroIconWrap: { width: 72, height: 72, borderRadius: 20, justifyContent: 'center', alignItems: 'center' },
  heroTitle: { fontSize: 24, fontWeight: '800' },
  heroSub: { fontSize: 14, textAlign: 'center', paddingHorizontal: 20, lineHeight: 20 },
  heroStats: { flexDirection: 'row', gap: 24, marginTop: 8 },
  heroStat: { alignItems: 'center' },
  heroStatNum: { fontSize: 22, fontWeight: '800' },
  heroStatLabel: { fontSize: 11 },

  // Buttons
  primaryBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, padding: 16, borderRadius: 14, marginTop: 16 },
  primaryBtnText: { color: '#FFF', fontSize: 16, fontWeight: '700' },

  // Section
  sectionTitle: { fontSize: 16, fontWeight: '700', marginTop: 20, marginBottom: 10 },

  // Projects
  projectCard: { flexDirection: 'row', alignItems: 'center', padding: 14, borderRadius: 14, marginBottom: 8, borderWidth: 1, gap: 12 },
  projectIcon: { width: 44, height: 44, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
  projectInfo: { flex: 1 },
  projectName: { fontSize: 14, fontWeight: '700' },
  projectMeta: { fontSize: 11, marginTop: 3 },
  statusDot: { width: 10, height: 10, borderRadius: 5 },

  // Pipeline Preview
  pipelinePreview: { borderRadius: 14, borderWidth: 1, overflow: 'hidden' },
  pipelineStep: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 10, gap: 10, borderBottomWidth: 0.5, borderBottomColor: 'rgba(255,255,255,0.05)' },
  pipelineDot: { width: 28, height: 28, borderRadius: 14, justifyContent: 'center', alignItems: 'center' },
  pipelineDotText: { color: '#FFF', fontSize: 12, fontWeight: '700' },
  pipelineStepInfo: { flex: 1 },
  pipelineStepName: { fontSize: 13, fontWeight: '600' },
  pipelineStepAgent: { fontSize: 10, marginTop: 2, fontWeight: '500' },
  phaseBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  phaseBadgeText: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase' },

  // Create
  descInput: { borderWidth: 1, borderRadius: 14, padding: 16, fontSize: 15, lineHeight: 22, minHeight: 120 },
  charCount: { fontSize: 11, textAlign: 'right', marginTop: 4 },
  genreScroll: { marginBottom: 8 },
  genreChip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 10, borderRadius: 12, borderWidth: 1, marginRight: 8 },
  genreChipText: { fontSize: 13, fontWeight: '600' },
  engineRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  engineChip: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, borderWidth: 1 },
  engineChipText: { fontSize: 13, fontWeight: '600' },
  buildBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, padding: 18, borderRadius: 16, marginTop: 24 },
  buildBtnText: { color: '#FFF', fontSize: 18, fontWeight: '800' },

  // Building
  buildHeader: { padding: 16, borderRadius: 14, marginTop: 12, borderWidth: 1 },
  buildTitle: { fontSize: 18, fontWeight: '700' },
  buildMeta: { fontSize: 12, marginTop: 4 },
  progressBar: { height: 8, borderRadius: 4, marginTop: 12, overflow: 'hidden' },
  progressFill: { height: '100%', borderRadius: 4 },

  stepCard: { borderRadius: 14, borderWidth: 1, marginTop: 10, padding: 14 },
  stepHeader: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  stepNum: { width: 30, height: 30, borderRadius: 15, justifyContent: 'center', alignItems: 'center' },
  stepNumText: { color: '#FFF', fontSize: 13, fontWeight: '700' },
  stepInfo: { flex: 1 },
  stepName: { fontSize: 14, fontWeight: '700' },
  stepAgent: { fontSize: 11, marginTop: 2 },
  stepResult: { marginTop: 10, padding: 10, borderRadius: 8, borderWidth: 1 },
  stepResultText: { fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', color: '#8B949E', fontSize: 10, lineHeight: 14 },
  holodeckRenderCard: { marginTop: 8, borderWidth: 1, borderRadius: 8, overflow: 'hidden', backgroundColor: '#0A1628' },
  holodeckRenderHeader: { flexDirection: 'row' as const, alignItems: 'center' as const, gap: 6, paddingHorizontal: 10, paddingVertical: 6, backgroundColor: '#00D4FF10' },
  holodeckRenderLabel: { color: '#00D4FF', fontSize: 11, fontWeight: '700' as const, letterSpacing: 1, textTransform: 'uppercase' as const },
  holodeckRenderImage: { width: '100%' as any, height: 180, backgroundColor: '#0D1117' },
  stepBuildBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: 10, paddingVertical: 10, borderRadius: 10 },
  stepBuildBtnText: { color: '#FFF', fontSize: 13, fontWeight: '700' },

  actionRow: { flexDirection: 'row', gap: 10, marginTop: 16 },
  autoBuildBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, padding: 14, borderRadius: 12 },
  autoBuildBtnText: { color: '#FFF', fontSize: 14, fontWeight: '700' },
  compileBtnLarge: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, padding: 14, borderRadius: 12 },
  compileBtnLargeText: { color: '#FFF', fontSize: 14, fontWeight: '800' },

  // Build Log
  buildLogCard: { marginTop: 16, padding: 14, borderRadius: 12, borderWidth: 1 },
  buildLogHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  buildLogTitle: { color: '#8B949E', fontSize: 12, fontWeight: '700' },
  buildLogLine: { color: '#C9D1D9', fontSize: 12, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', lineHeight: 18 },

  // Compiled
  compileHeader: { alignItems: 'center', padding: 24, borderRadius: 20, marginTop: 16, borderWidth: 1, gap: 8 },
  compileIconWrap: { width: 80, height: 80, borderRadius: 24, justifyContent: 'center', alignItems: 'center' },
  compileTitle: { fontSize: 24, fontWeight: '800' },
  compileSub: { fontSize: 14 },
  aaaBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 6, borderRadius: 10, borderWidth: 1, marginTop: 4 },
  aaaBadgeText: { color: '#F59E0B', fontSize: 13, fontWeight: '800' },
  compileSection: { marginTop: 16, padding: 14, borderRadius: 14, borderWidth: 1 },
  compileSectionTitle: { fontSize: 15, fontWeight: '700', marginBottom: 10 },
  fileRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6 },
  fileName: { fontSize: 13, fontWeight: '600', flex: 1 },
  fileDesc: { fontSize: 11 },
  codeOutput: { fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', color: '#E6EDF3', fontSize: 11, lineHeight: 16, minWidth: SCREEN_WIDTH - 60 },
  instructions: { fontSize: 13, lineHeight: 20 },

  // Competitor Analysis
  beatCard: { paddingVertical: 10, borderBottomWidth: 0.5, gap: 6 },
  beatArea: { fontSize: 14, fontWeight: '800', textTransform: 'uppercase' },
  beatRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  beatCol: { flex: 1, gap: 2 },
  beatLabel: { fontSize: 10, fontWeight: '800', textTransform: 'uppercase' },
  beatText: { fontSize: 12, lineHeight: 16 },
  beatWhy: { fontSize: 11, fontWeight: '600', fontStyle: 'italic' },

  // Quality Layers
  layersCard: { marginTop: 12, padding: 16, borderRadius: 14, borderWidth: 1, backgroundColor: '#0D111720', gap: 10 },
  layersTitle: { fontSize: 16, fontWeight: '800', marginBottom: 4, letterSpacing: 0.5 },
  layerRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  layerIcon: { width: 32, height: 32, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  layerInfo: { flex: 1 },
  layerName: { fontSize: 13, fontWeight: '700' },
  layerPurpose: { fontSize: 10, marginTop: 1 },
  layerCount: { fontSize: 14, fontWeight: '800', minWidth: 50, textAlign: 'right' },
  layerTotalRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingTop: 10, marginTop: 4, borderTopWidth: 1, borderTopColor: 'rgba(255,255,255,0.08)' },
  layerTotalLabel: { fontSize: 13, fontWeight: '700', textTransform: 'uppercase', letterSpacing: 1 },
  layerTotalCount: { fontSize: 20, fontWeight: '900' },
});
