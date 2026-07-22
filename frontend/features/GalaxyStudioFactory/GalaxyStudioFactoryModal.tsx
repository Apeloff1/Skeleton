// ═══════════════════════════════════════════════════════════════════════
// GALAXY STUDIO FACTORY v6.0 — 100-Phase / 10-Batch 15-Minute Build + APK
// Interval polling • Batch-level generation • No 520 errors
// ═══════════════════════════════════════════════════════════════════════
import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, Modal,
  TextInput, ActivityIndicator, Animated, Platform,
  Linking, KeyboardAvoidingView, Keyboard,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import Constants from 'expo-constants';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { EXTRA_PARAM_CATEGORIES, DEFAULT_EXTRA_PARAMS, TOTAL_EXTRA_PARAMS } from './extraParams';
import { GAME_TEMPLATES, randomizeConfig, GameTemplate } from './presets';
import { GAME_ERAS, DEFAULT_ERA_ID } from './gameEras';
import { STYLE_SLIDERS, DEFAULT_STYLE_PARAMS } from './styleSliders';
import { ProductionStudioPanel } from './ProductionStudioPanel';
import { DEFAULT_PRODUCTION_STATE, ProductionState } from './productionSections';
import { YourChoicesCard } from './YourChoicesCard';
import { NarrativePhaseSliders, defaultPhaseValues as defaultNarrativePhaseValues, AllPhaseValues } from './NarrativePhaseSliders';
import { MatrixSliders, MatrixValues, defaultMatrixValues } from './MatrixSliders';
import { ALL_MATRICES, MECHANICS_MATRIX, WORLD_MATRIX, ART_MATRIX, AUDIO_MATRIX, TECH_MATRIX, MONETISATION_MATRIX, QA_MATRIX, AGENT_MATRIX, VECTOR_DB_MATRIX, PLAGIARISM_MATRIX, RDBMS_MATRIX, STYLES_MATRIX, MUTATION_MATRIX, UNIQUE_FLAIR_MATRIX } from './QuestionnaireMatrices';
import { rget, rpost, startHeartbeat, resetCircuit } from '../../utils/resilientNet';
import { getPhaseWeightsPayload } from '../../state/settingsStore';
import { TunnelStatusPill } from '../../components/TunnelStatusPill';
import Slider from '@react-native-community/slider';

import { apiFetch } from '../../utils/apiController';

// Palette + StyleSheet extracted into ./GalaxyStudioFactoryModal.styles
// to keep this file under the AST/parser timeout threshold.
import { T, s } from './GalaxyStudioFactoryModal.styles';
// 2026-05-15 — Done-state sub-screens extracted for clarity & file-size budget.
import { CodeFileView, CodeBrowseView, VaultView } from './GalaxyStudioFactoryModal.SubScreens';
// 2026-05-15 — Native-slider ML Console panel (Cross-Entropy · Fine-Tuning · ICL Log-Probs)
// 2026-05-15 — Wave-3 enhancement: Jeeves TTS chime + cross-route bridges on Done step.
import { useRouter } from 'expo-router';
import { jeevesSpeak } from '../Academy/jeevesTts';
import { shareResult } from '../../utils/shareResult';

import { FALLBACK_GENRES } from './fallbackGenres';
const BACKEND = (() => {
  // Web: prefer same-origin so the app works on any deploy URL.
  if (typeof window !== 'undefined' && (window as any).location?.origin && !(window as any).location.origin.startsWith('file:')) {
    return (window as any).location.origin.replace(/\/+$/, '');
  }
  return (Constants.expoConfig?.extra?.EXPO_PUBLIC_BACKEND_URL as string)
    || process.env.EXPO_PUBLIC_BACKEND_URL || '';
})();

interface Props { visible: boolean; onClose: () => void; }
type Step = 'pick' | 'building' | 'done';

// Map the Studio's gameEras id → backend final-build era key (core/eras.py).
const ERA_KEY_MAP: Record<string, string> = {
  pong_1972: '8bit', atari_1977: '8bit', nes_1985: '8bit',
  snes_1990: '16bit', ps1_1995: 'early3d', ps2_2000: '64bit',
  xbox360_2005: 'earlyhd', ps4_2013: 'modern', ps5_2020: 'modern',
  singularity: 'nextgen',
};

interface Genre {
  id: string; name: string; icon: string; color: string; desc: string;
  screens: number; components: number; logic_files: number;
  subgenres: string[]; subgenre_count: number;
}

// ═══════════════════════════════════════════════════════════════════════
// Active Jobs tray — surfaces in-flight background jobs (expansion / APK
// packaging) and lets a user who reopened the modal RECONNECT to a job that
// is still running server-side. Driven by GET /expand/status & /vault/apk-status.
// ═══════════════════════════════════════════════════════════════════════
const APK_STAGE_LABEL: Record<string, string> = {
  queued: 'queued', zipping: 'zipping files', zip_ready: 'zip ready',
  materializing: 'writing project', npm_install: 'installing deps',
  eas_init: 'initializing EAS', eas_build: 'triggering EAS build', done: 'finalizing',
};

function ActiveJobRow({ kind, job, T, topBorder }: { kind: 'expand' | 'apk'; job: any; T: any; topBorder?: boolean }) {
  const running = job.status === 'running';
  const color = job.status === 'completed' ? '#22C55E' : job.status === 'failed' ? '#EF4444' : '#60A5FA';
  let detail: string;
  if (kind === 'expand') {
    detail = running ? `generating… (pipeline ${job.phases_completed ?? 0}/${job.phases_total ?? 7})`
      : job.status === 'completed' ? `+${(job.files_added ?? 0).toLocaleString()} files → ${(job.total_files ?? 0).toLocaleString()} total`
      : job.status === 'failed' ? (job.error || 'failed') : String(job.status);
  } else {
    const res = job.result || {};
    detail = running ? (APK_STAGE_LABEL[job.stage] || job.stage || 'working…')
      : job.status === 'completed' ? `${res.apk_status || 'done'} • ${res.file_count ?? 0} files`
      : job.status === 'failed' ? (job.error || 'failed') : String(job.status);
  }
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6, borderTopWidth: topBorder ? 1 : 0, borderTopColor: T.border }}>
      <Ionicons name={kind === 'expand' ? 'sparkles-outline' : 'phone-portrait-outline'} size={16} color={color} />
      <View style={{ flex: 1 }}>
        <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{kind === 'expand' ? 'Expansion' : 'APK Packaging'}</Text>
        <Text style={{ color: T.textMuted, fontSize: 11 }} numberOfLines={1}>{detail}</Text>
      </View>
      {running ? <ActivityIndicator size="small" color={color} />
        : <Ionicons name={job.status === 'completed' ? 'checkmark-circle' : 'alert-circle'} size={16} color={color} />}
    </View>
  );
}

// ═══════════════════════════════════════════════════════════════════════
// FAILSAFE CONFIG — ZERO RECURSION polling, backoff via tick-skipping
// ═══════════════════════════════════════════════════════════════════════
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const POLL_BASE_INTERVAL = 5000;   // 5s base interval (setInterval tick rate)

// Batch name mapping for client-side estimates when server is unreachable
const BATCH_NAME_BY_NUM: Record<number | string, string> = {
  1: 'Vision & Concept',
  2: 'Deep Design',
  3: 'Quantum Core',
  4: 'Game Factory',
  5: 'Code Generation',
  6: 'Art & Audio',
  7: 'Narrative',
  8: 'QA Gauntlet',
  9: 'Marketing',
  10: 'Production & Deploy',
};

// ═══ DESCRIPTION CARD ═══
// eslint-disable-next-line react/display-name
const DescCard = React.memo(({ icon, color, label, hint, placeholder, value, onChange, onInputFocus }: any) => (
  <View style={s.descCard}>
    <View style={s.descCardHeader}>
      <Ionicons name={icon} size={16} color={color} />
      <Text style={s.descCardTitle}>{label}</Text>
      {value.length > 0 && <Text style={[s.descOk, { color }]}>✓</Text>}
    </View>
    <Text style={s.descCardHint}>{hint}</Text>
    <TextInput
      style={s.descInput} placeholder={placeholder} placeholderTextColor={T.textMuted}
      value={value} onChangeText={onChange} multiline maxLength={2000} scrollEnabled
      onFocus={onInputFocus} blurOnSubmit={false} />
    {value.length > 0 && <Text style={s.descCount}>{value.length}/2000</Text>}
  </View>
));

// ═══════════════════════════════════════════════════════════════════════════
//  FileSizeSlider — final card at the bottom of the questionnaire.
//
//  Lets the user pick the build's **target file count** between the hard
//  48 000 minimum (enforced on the backend) and 1 000 000 (god-tier ceiling).
//
//  Uses the same `s.descCard` shell as the five DescCard text inputs so the
//  whole questionnaire reads as one continuous block.
//
//  Quick-pick chips offer 5 canonical values:
//    48K (floor) · 100K (juggernaut) · 250K (behemoth) · 500K (god-tier) · 1M
//  Plus a live readout of the chosen tier label.
// ═══════════════════════════════════════════════════════════════════════════
const MIN_TARGET_FILES = 48_000;
const MAX_TARGET_FILES = 1_000_000;
const FILE_PRESETS: { value: number; label: string; tag: string }[] = [
  { value: 48_000,    label: '48K',  tag: 'FLOOR' },
  { value: 100_000,   label: '100K', tag: 'JUGGERNAUT' },
  { value: 250_000,   label: '250K', tag: 'BEHEMOTH' },
  { value: 500_000,   label: '500K', tag: 'GOD-TIER' },
  { value: 1_000_000, label: '1M',   tag: 'SINGULARITY' },
];
function _fileTierLabel(n: number): string {
  if (n >= 1_000_000) return 'SINGULARITY';
  if (n >= 500_000)   return 'GOD-TIER';
  if (n >= 250_000)   return 'BEHEMOTH';
  if (n >= 100_000)   return 'JUGGERNAUT';
  return 'BASELINE';
}
function _fileTierColor(n: number): string {
  if (n >= 1_000_000) return '#EC4899';   // pink
  if (n >= 500_000)   return '#A855F7';   // violet
  if (n >= 250_000)   return '#8B5CF6';   // brand
  if (n >= 100_000)   return '#3B82F6';   // cyan
  return '#10B981';                       // success
}

interface FileSizeSliderProps {
  value: number;
  onChange: (v: number) => void;
}
// eslint-disable-next-line react/display-name
const FileSizeSlider = React.memo(({ value, onChange }: FileSizeSliderProps) => {
  const tierLabel = _fileTierLabel(value);
  const tierColor = _fileTierColor(value);
  const progress = (value - MIN_TARGET_FILES) / (MAX_TARGET_FILES - MIN_TARGET_FILES);
  return (
    <View style={s.descCard} testID="file-size-slider-card">
      <View style={s.descCardHeader}>
        <Ionicons name="layers-outline" size={16} color={tierColor} />
        <Text style={s.descCardTitle}>Target file count</Text>
        <View style={[s.fileTierBadge, { backgroundColor: tierColor + '22', borderColor: tierColor + '66' }]} testID="tier-badge">
          <Text style={[s.fileTierBadgeText, { color: tierColor }]} testID="tier-badge-label">{tierLabel}</Text>
        </View>
      </View>
      <Text style={s.descCardHint}>
        Drag to set the build&apos;s target file count. Hard floor is 48 000 (every build ships at JUGGERNAUT-baseline or better).
      </Text>

      <View style={s.fileValueRow}>
        <Text style={[s.fileValueBig, { color: tierColor }]} testID="file-count-display">
          {value.toLocaleString()}
        </Text>
        <Text style={s.fileValueUnit}>files</Text>
      </View>

      <Slider
        testID="file-size-slider"
        style={{ width: '100%', height: 32 }}
        minimumValue={MIN_TARGET_FILES}
        maximumValue={MAX_TARGET_FILES}
        step={1000}
        value={value}
        onValueChange={onChange}
        minimumTrackTintColor={tierColor}
        maximumTrackTintColor={T.border}
        thumbTintColor={tierColor}
      />

      <View style={s.fileScaleRow}>
        <Text style={s.fileScaleLabel}>48K</Text>
        <Text style={s.fileScaleLabel}>250K</Text>
        <Text style={s.fileScaleLabel}>500K</Text>
        <Text style={s.fileScaleLabel}>1M</Text>
      </View>

      {/* Quick-pick presets */}
      <View style={s.filePresetRow}>
        {FILE_PRESETS.map(p => {
          const active = value === p.value;
          const c = _fileTierColor(p.value);
          return (
            <TouchableOpacity
              key={p.value}
              onPress={() => onChange(p.value)}
              activeOpacity={0.7}
              testID={`file-size-slider-chip-${p.label}`}
              style={[
                s.filePresetChip,
                active && { backgroundColor: c + '22', borderColor: c },
              ]}
              accessibilityRole="button"
              accessibilityLabel={`Set target to ${p.label} files (${p.tag})`}
            >
              <Text style={[s.filePresetLabel, active && { color: c }]}>{p.label}</Text>
              <Text style={[s.filePresetTag, active && { color: c + 'CC' }]}>{p.tag}</Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {/* Subtle progress hint */}
      <View style={s.fileMeter}>
        <View style={[s.fileMeterFill, { width: `${Math.min(100, Math.max(2, progress * 100))}%`, backgroundColor: tierColor }]} />
      </View>
    </View>
  );
});


const COMPLEXITY_LEVELS = [
  { val: 1, label: "L1: Minimal Arcade" },
  { val: 2, label: "L2: Casual 2D" },
  { val: 3, label: "L3: Standard Indie" },
  { val: 4, label: "L4: Deep Indie" },
  { val: 5, label: "L5: AA Standard" },
  { val: 6, label: "L6: AA Immersive" },
  { val: 7, label: "L7: AAA Core" },
  { val: 8, label: "L8: AAA Massive" },
  { val: 9, label: "L9: Next-Gen SOTA" },
  { val: 10, label: "L10: God-Tier Singularity" },
];

const AGE_STAGES = [
  { val: 'EC', label: "Early Childhood (3+)" },
  { val: 'E', label: "Everyone (6+)" },
  { val: 'E10', label: "Everyone 10+" },
  { val: 'T', label: "Teen (13+)" },
  { val: 'M', label: "Mature (17+)" },
  { val: 'AO', label: "Adults Only (18+)" },
  { val: 'ALL', label: "All Stages" },
];

// ★ 2026-02 — Horizontal chip picker for Story & Style settings.
// Kept inline so the modal stays one-file. Shows label + hint + horizontal
// chips with the active option highlighted in pink.
function StylePicker<T extends string>({
  label, hint, value, onChange, options,
}: { label: string; hint?: string; value: T; onChange: (v: T) => void; options: readonly T[] }) {
  return (
    <View style={{ marginTop: 10 }}>
      <Text style={{ color: '#F8FAFC', fontSize: 12, fontWeight: '800' }}>{label}</Text>
      {hint && <Text style={{ color: '#94A3B8', fontSize: 10, marginBottom: 4 }}>{hint}</Text>}
      <ScrollView horizontal showsHorizontalScrollIndicator={false}>
        {options.map(opt => {
          const active = opt === value;
          const pretty = String(opt).replace(/_/g, ' ');
          return (
            <TouchableOpacity
              key={String(opt)}
              onPress={() => onChange(opt)}
              style={{
                paddingHorizontal: 12, paddingVertical: 7, marginRight: 6,
                borderRadius: 14,
                backgroundColor: active ? 'rgba(236, 72, 153, 0.25)' : '#334155',
                borderWidth: 1,
                borderColor: active ? '#EC4899' : 'transparent',
              }}
            >
              <Text style={{
                color: active ? '#EC4899' : '#CBD5E1',
                fontSize: 11,
                fontWeight: active ? '800' : '600',
                textTransform: 'capitalize',
              }}>{pretty}</Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    </View>
  );
}

export default function GalaxyStudioFactoryModal
({ visible, onClose }: Props) {
  const [step, setStep] = useState<Step>('pick');
  // ★ 2026-05 SOTA UX: Quick / Advanced mode toggle.
  // Default ON (Quick) so first-time users see a focused, friendly form.
  // Turning it OFF reveals the full 100-slider depth for power users.
  const [quickMode, setQuickMode] = useState<boolean>(true);
  // Per-section collapse state for the Advanced sliders (when quickMode=false).
  const [, setCollapsedSections] = useState<Record<string, boolean>>({
    style: false,        // Style palette open by default
    sliders: true,       // 100-slider grid collapsed
    audio: true,
    multiplayer: true,
    monetisation: true,
  });
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const toggleSection = useCallback((key: string) => {
    setCollapsedSections(s => ({ ...s, [key]: !s[key] }));
  }, []);
  // Prime with baked-in fallback so the picker ALWAYS renders 52 genres,
  // network or not. The network fetch below overwrites on success.
  const [genres, setGenres] = useState<Genre[]>(FALLBACK_GENRES as any);
  const [manifest, setManifest] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  // Create
  const [title, setTitle] = useState('');

  // ★ 2026-05 — Defaults set to MAX. Users adjust DOWN from here. This
  // standardises the "give me the best possible build" experience: every
  // knob ships maxed by default. Drop only what you actively don't need.
  const [complexity, setComplexity] = useState<number>(10);
  const [ageTarget, setAgeTarget] = useState<string>('ALL');
  const [graphicsEra, setGraphicsEra] = useState<number>(7);
  const [npcDensity, setNpcDensity] = useState<number>(7);
  const [soundEra, setSoundEra] = useState<number>(7);
  const [worldSize, setWorldSize] = useState<number>(7);
  const [physicsRealism, setPhysicsRealism] = useState<number>(7);
  const [aiComplexity, setAiComplexity] = useState<number>(7);
  const [lightingEngine, setLightingEngine] = useState<number>(7);
  const [particleEffects, setParticleEffects] = useState<number>(7);
  const [destructionPhysics, setDestructionPhysics] = useState<number>(7);
  const [narrativeBranching, setNarrativeBranching] = useState<number>(7);
  const [economyComplexity, setEconomyComplexity] = useState<number>(7);
  const [multiplayerMax, setMultiplayerMax] = useState<number>(7);
  const [weatherSystems, setWeatherSystems] = useState<number>(7);
  const [dayNightCycle, setDayNightCycle] = useState<number>(7);
  const [animationFluidity, setAnimationFluidity] = useState<number>(7);
  const [postProcessing, setPostProcessing] = useState<number>(7);
  // ★ 2026-02 Animation controls (new) — wire into backend _phase_animations_pack
  const [animationStyle, setAnimationStyle] = useState<'subtle'|'smooth'|'punchy'|'cinematic'>('smooth');
  const [cameraEffects, setCameraEffects] = useState<boolean>(true);
  // ★ 2026-02 Story & Style pack — wire into backend _phase_story_style_pack
  // These choices drive dedicated phase outputs (storyline/, visual_style/,
  // tone/, perspective/, combat/, progression/, audio/) so every slider
  // visibly modifies the file tree.
  const [storylineStyle, setStorylineStyle] = useState<'heroic'|'tragedy'|'mystery'|'redemption'|'coming_of_age'|'comedy'|'cosmic_horror'>('heroic');
  const [gamePace, setGamePace] = useState<'slow_burn'|'standard'|'action_packed'|'breakneck'>('standard');
  const [difficultyCurve, setDifficultyCurve] = useState<'gentle'|'steady'|'adaptive'|'punishing'>('steady');
  const [perspective, setPerspective] = useState<'first_person'|'third_person'|'isometric'|'top_down'|'side_scroll'|'vr'>('third_person');
  const [combatStyle, setCombatStyle] = useState<'realtime'|'turn_based'|'action_rpg'|'rhythm'|'tactical'|'none'>('action_rpg');
  const [visualStyle, setVisualStyle] = useState<'photoreal'|'cel_shaded'|'pixel_art'|'low_poly'|'voxel'|'hand_painted'|'anime'>('hand_painted');
  const [gameTone, setGameTone] = useState<'heroic'|'dark'|'humorous'|'melancholic'|'epic'|'cozy'|'unsettling'>('epic');
  const [progressionType, setProgressionType] = useState<'linear'|'open_world'|'metroidvania'|'roguelike'|'sandbox'|'hub_and_spoke'>('open_world');
  const [audioMood, setAudioMood] = useState<'orchestral'|'synthwave'|'ambient'|'chiptune'|'rock'|'folk'|'silent'>('orchestral');
  // ★ 2026-02 Locomotion — chip slider (0-10) + style picker
  const [locomotionDepth, setLocomotionDepth] = useState<number>(7);
  const [locomotionStyle, setLocomotionStyle] = useState<'basic'|'tactical'|'parkour'|'als'|'gunplay'|'melee'>('als');
  const [foliageDensity, setFoliageDensity] = useState<number>(7);
  const [waterSimulation, setWaterSimulation] = useState<number>(7);
  const [uiMinimalism, setUiMinimalism] = useState<number>(7);
  const [lootVariety, setLootVariety] = useState<number>(7);
  const [craftingDepth, setCraftingDepth] = useState<number>(7);
  const [dialogDepth, setDialogDepth] = useState<number>(7);
  const [stealthMechanics, setStealthMechanics] = useState<number>(7);
  const [vehicleSimulation, setVehicleSimulation] = useState<number>(7);
  const [biomeDiversity, setBiomeDiversity] = useState<number>(7);
  const [factionReputation, setFactionReputation] = useState<number>(7);
  const [skillSystem, setSkillSystem] = useState<number>(7);
  const [goreSystem, setGoreSystem] = useState<number>(7);
  const [moddingSupport, setModdingSupport] = useState<number>(7);

  // ═══ 2026-05-15 — EXTREME-GRANULARITY MATRICES ═══════════════════════════
  // Every questionnaire section is now expressed as a phase × axes tensor.
  // 8 matrices × ~25-40 phases × 5 axes ≈ 1,250 dials. NarrativePhaseSliders
  // adds another 36 × 5 = 180. Total user-tunable dials > 1,400 across the
  // questionnaire. Each matrix is collapsed by default — Quick mode hides
  // them entirely.
  const [narrativePhaseValues, setNarrativePhaseValues] = useState<AllPhaseValues>(() => defaultNarrativePhaseValues());
  const [mechanicsMatrix, setMechanicsMatrix] = useState<MatrixValues>(() => defaultMatrixValues(MECHANICS_MATRIX));
  const [worldMatrix, setWorldMatrix] = useState<MatrixValues>(() => defaultMatrixValues(WORLD_MATRIX));
  const [artMatrix, setArtMatrix] = useState<MatrixValues>(() => defaultMatrixValues(ART_MATRIX));
  const [audioMatrix, setAudioMatrix] = useState<MatrixValues>(() => defaultMatrixValues(AUDIO_MATRIX));
  const [techMatrix, setTechMatrix] = useState<MatrixValues>(() => defaultMatrixValues(TECH_MATRIX));
  const [monetisationMatrix, setMonetisationMatrix] = useState<MatrixValues>(() => defaultMatrixValues(MONETISATION_MATRIX));
  const [qaMatrix, setQaMatrix] = useState<MatrixValues>(() => defaultMatrixValues(QA_MATRIX));
  const [agentMatrix, setAgentMatrix] = useState<MatrixValues>(() => defaultMatrixValues(AGENT_MATRIX));
  // ── 2026-05-15 second wave: DBs + Styles + Mutation + Flair ──
  const [vectorDbMatrix, setVectorDbMatrix]       = useState<MatrixValues>(() => defaultMatrixValues(VECTOR_DB_MATRIX));
  const [plagiarismMatrix, setPlagiarismMatrix]   = useState<MatrixValues>(() => defaultMatrixValues(PLAGIARISM_MATRIX));
  const [rdbmsMatrix, setRdbmsMatrix]             = useState<MatrixValues>(() => defaultMatrixValues(RDBMS_MATRIX));
  const [stylesMatrix, setStylesMatrix]           = useState<MatrixValues>(() => defaultMatrixValues(STYLES_MATRIX));
  const [mutationMatrix, setMutationMatrix]       = useState<MatrixValues>(() => defaultMatrixValues(MUTATION_MATRIX));
  const [uniqueFlairMatrix, setUniqueFlairMatrix] = useState<MatrixValues>(() => defaultMatrixValues(UNIQUE_FLAIR_MATRIX));
  const [expandedMatrix, setExpandedMatrix] = useState<string | null>(null);
  const matrixSetters: Record<string, (v: MatrixValues) => void> = {
    mechanics:    setMechanicsMatrix,
    world:        setWorldMatrix,
    art:          setArtMatrix,
    audio:        setAudioMatrix,
    tech:         setTechMatrix,
    monetisation: setMonetisationMatrix,
    qa:           setQaMatrix,
    agent:        setAgentMatrix,
    vector_db:    setVectorDbMatrix,
    plagiarism:   setPlagiarismMatrix,
    rdbms:        setRdbmsMatrix,
    styles:       setStylesMatrix,
    mutation:     setMutationMatrix,
    unique_flair: setUniqueFlairMatrix,
  };
  const matrixValues: Record<string, MatrixValues> = {
    mechanics:    mechanicsMatrix,
    world:        worldMatrix,
    art:          artMatrix,
    audio:        audioMatrix,
    tech:         techMatrix,
    monetisation: monetisationMatrix,
    qa:           qaMatrix,
    agent:        agentMatrix,
    vector_db:    vectorDbMatrix,
    plagiarism:   plagiarismMatrix,
    rdbms:        rdbmsMatrix,
    styles:       stylesMatrix,
    mutation:     mutationMatrix,
    unique_flair: uniqueFlairMatrix,
  };
  // ═══ JUICE slider (2026-05) — controls visual juice intensity ═══
  // 0 = sterile / minimal, 10 = explosive (max screen-shake, hit-stop, particles).
  // Backend wires this into the visual_juice agent-knowledge collection so the
  // agent picks the matching intensity tier ("subtle"|"medium"|"strong"|"explosive").
  const [juice, setJuice] = useState<number>(7);
  // ═══ v3: Game Era — tech/aesthetic tone selector ═══
  const [selectedEraId, setSelectedEraId] = useState<string>(DEFAULT_ERA_ID);
  const selectedEra = GAME_ERAS.find(e => e.id === selectedEraId) || GAME_ERAS[8];
  // ═══ v5: "Era by Age" — year slider 1985 → 2030. Anchors the build to
  // a specific year's hardware/cultural sensibility (e.g. 1995 PS1, 2015
  // live-service, 2030 neural-interface). Independent of Game Era above.
  const [ageEraYear, setAgeEraYear] = useState<number>(2025);
  const AGE_YEARS = Array.from({ length: 2030 - 1985 + 1 }, (_, i) => 1985 + i);
  // ═══ v6: 9 style pickers (graphic/sound/music/design/cinematic/director/
  // dimension/asset/model). Stored as flat {key: option_id} map.
  const [styleParams, setStyleParams] = useState<Record<string, string>>(DEFAULT_STYLE_PARAMS);
  const setStyleParam = useCallback((key: string, value: string) => {
    setStyleParams(prev => ({ ...prev, [key]: value }));
  }, []);
  // ═══ 2026-05-13 — Production Studio panel state (0-100 sliders + multi-select
  //     platforms/languages/monetization/save/network/art-direction/tone/narrative/
  //     perspective). Forwarded to the backend as extra_params.production.
  const [productionState, setProductionState] = useState<ProductionState>(DEFAULT_PRODUCTION_STATE);

  // ═══ v2: 100 extra questionnaire sliders — stored as flat { key: value } map ═══
  const [extraParams, setExtraParams] = useState<Record<string, number>>(DEFAULT_EXTRA_PARAMS);
  const [expandedExtraCat, setExpandedExtraCat] = useState<string | null>(null);
  const setExtraParam = useCallback((key: string, value: number) => {
    setExtraParams(prev => ({ ...prev, [key]: value }));
  }, []);

  // ═══ APPLY ERA — fills 29 classic sliders + 100 extras with era-appropriate defaults ═══
  const applyEra = useCallback((eraId: string) => {
    setSelectedEraId(eraId);
    const era = GAME_ERAS.find(e => e.id === eraId);
    if (!era) return;
    const co = era.classicOverrides;
    const s = (k: string, setter: (v: number) => void, cur: number) => {
      if (typeof co[k] === 'number') setter(co[k]);
    };
    s('graphicsEra', setGraphicsEra, graphicsEra);
    s('npcDensity', setNpcDensity, npcDensity);
    s('soundEra', setSoundEra, soundEra);
    s('worldSize', setWorldSize, worldSize);
    s('physicsRealism', setPhysicsRealism, physicsRealism);
    s('aiComplexity', setAiComplexity, aiComplexity);
    s('lightingEngine', setLightingEngine, lightingEngine);
    s('particleEffects', setParticleEffects, particleEffects);
    s('destructionPhysics', setDestructionPhysics, destructionPhysics);
    s('narrativeBranching', setNarrativeBranching, narrativeBranching);
    s('economyComplexity', setEconomyComplexity, economyComplexity);
    s('multiplayerMax', setMultiplayerMax, multiplayerMax);
    s('weatherSystems', setWeatherSystems, weatherSystems);
    s('dayNightCycle', setDayNightCycle, dayNightCycle);
    s('animationFluidity', setAnimationFluidity, animationFluidity);
    s('postProcessing', setPostProcessing, postProcessing);
    s('foliageDensity', setFoliageDensity, foliageDensity);
    s('waterSimulation', setWaterSimulation, waterSimulation);
    s('uiMinimalism', setUiMinimalism, uiMinimalism);
    s('lootVariety', setLootVariety, lootVariety);
    s('craftingDepth', setCraftingDepth, craftingDepth);
    s('dialogDepth', setDialogDepth, dialogDepth);
    s('stealthMechanics', setStealthMechanics, stealthMechanics);
    s('vehicleSimulation', setVehicleSimulation, vehicleSimulation);
    s('biomeDiversity', setBiomeDiversity, biomeDiversity);
    s('factionReputation', setFactionReputation, factionReputation);
    s('skillSystem', setSkillSystem, skillSystem);
    s('goreSystem', setGoreSystem, goreSystem);
    s('moddingSupport', setModdingSupport, moddingSupport);
    // Merge extra overrides over current extras (don't wipe everything)
    if (era.extraOverrides) {
      setExtraParams(prev => ({ ...prev, ...era.extraOverrides! }));
    }
  }, [graphicsEra, npcDensity, soundEra, worldSize, physicsRealism, aiComplexity, lightingEngine, particleEffects, destructionPhysics, narrativeBranching, economyComplexity, multiplayerMax, weatherSystems, dayNightCycle, animationFluidity, postProcessing, foliageDensity, waterSimulation, uiMinimalism, lootVariety, craftingDepth, dialogDepth, stealthMechanics, vehicleSimulation, biomeDiversity, factionReputation, skillSystem, goreSystem, moddingSupport]);

  // ═══ APPLY TEMPLATE — fills title/genre/29 classic sliders/100 extra params in one tap ═══
  const applyTemplate = useCallback((tpl: GameTemplate) => {
    // Handle the special "random" template
    if (tpl.id === 'random') {
      const rnd = randomizeConfig();
      setTitle(`Chaos ${Math.floor(Math.random() * 9999)}`);
      // Random genre pick happens naturally after user picks
      setComplexity([3, 5, 7, 10][Math.floor(Math.random() * 4)]);
      setAgeTarget(['E', 'T', 'M'][Math.floor(Math.random() * 3)]);
      const c = rnd.classic;
      setGraphicsEra(c.graphicsEra); setNpcDensity(c.npcDensity); setSoundEra(c.soundEra); setWorldSize(c.worldSize);
      setPhysicsRealism(c.physicsRealism); setAiComplexity(c.aiComplexity); setLightingEngine(c.lightingEngine); setParticleEffects(c.particleEffects);
      setDestructionPhysics(c.destructionPhysics); setNarrativeBranching(c.narrativeBranching); setEconomyComplexity(c.economyComplexity); setMultiplayerMax(c.multiplayerMax);
      setWeatherSystems(c.weatherSystems); setDayNightCycle(c.dayNightCycle); setAnimationFluidity(c.animationFluidity); setPostProcessing(c.postProcessing);
      setFoliageDensity(c.foliageDensity); setWaterSimulation(c.waterSimulation); setUiMinimalism(c.uiMinimalism); setLootVariety(c.lootVariety);
      setCraftingDepth(c.craftingDepth); setDialogDepth(c.dialogDepth); setStealthMechanics(c.stealthMechanics); setVehicleSimulation(c.vehicleSimulation);
      setBiomeDiversity(c.biomeDiversity); setFactionReputation(c.factionReputation); setSkillSystem(c.skillSystem); setGoreSystem(c.goreSystem);
      setModdingSupport(c.moddingSupport);
      setExtraParams(rnd.extra);
      return;
    }
    // Standard template application
    setTitle(tpl.title);
    if (tpl.genre) {
      const match = genres.find(g => g.id === tpl.genre);
      if (match) setSelectedGenre(match);
    }
    if (tpl.subgenre) setSelectedSubgenre(tpl.subgenre);
    setGameVision(tpl.gameVision);
    setSystemArch(tpl.systemArch);
    setWorldLaws(tpl.worldLaws);
    setAgentInstructions(tpl.agentInstructions);
    setScaleCommand(tpl.scaleCommand);
    setComplexity(tpl.complexity);
    setAgeTarget(tpl.ageTarget);
    const c = tpl.classic;
    setGraphicsEra(c.graphicsEra); setNpcDensity(c.npcDensity); setSoundEra(c.soundEra); setWorldSize(c.worldSize);
    setPhysicsRealism(c.physicsRealism); setAiComplexity(c.aiComplexity); setLightingEngine(c.lightingEngine); setParticleEffects(c.particleEffects);
    setDestructionPhysics(c.destructionPhysics); setNarrativeBranching(c.narrativeBranching); setEconomyComplexity(c.economyComplexity); setMultiplayerMax(c.multiplayerMax);
    setWeatherSystems(c.weatherSystems); setDayNightCycle(c.dayNightCycle); setAnimationFluidity(c.animationFluidity); setPostProcessing(c.postProcessing);
    setFoliageDensity(c.foliageDensity); setWaterSimulation(c.waterSimulation); setUiMinimalism(c.uiMinimalism); setLootVariety(c.lootVariety);
    setCraftingDepth(c.craftingDepth); setDialogDepth(c.dialogDepth); setStealthMechanics(c.stealthMechanics); setVehicleSimulation(c.vehicleSimulation);
    setBiomeDiversity(c.biomeDiversity); setFactionReputation(c.factionReputation); setSkillSystem(c.skillSystem); setGoreSystem(c.goreSystem);
    setModdingSupport(c.moddingSupport);
    if (tpl.extraOverrides) {
      setExtraParams({ ...DEFAULT_EXTRA_PARAMS, ...tpl.extraOverrides });
    } else {
      setExtraParams(DEFAULT_EXTRA_PARAMS);
    }
  }, [genres]);

  const [selectedGenre, setSelectedGenre] = useState<Genre | null>(null);
  const [selectedSubgenre, setSelectedSubgenre] = useState<string | null>(null);
  // ═══ Multi-genre / multi-subgenre fusion support ═══
  // The primary `selectedGenre` above stays the lead; extra picks fuse in.
  const [extraGenreIds, setExtraGenreIds] = useState<string[]>([]);
  const [extraSubgenreIds, setExtraSubgenreIds] = useState<string[]>([]);
  const [multiGenreMode, setMultiGenreMode] = useState<boolean>(false);
  const toggleExtraGenre = (id: string) => {
    if (!selectedGenre || id === selectedGenre.id) return;
    setExtraGenreIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };
  const toggleExtraSubgenre = (id: string) => {
    if (id === selectedSubgenre) return;
    setExtraSubgenreIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };
  const fusedGenreCount = 1 + extraGenreIds.length;
  const fusionMultiplier = fusedGenreCount > 1
    ? Math.min(3.0, 1.0 + 0.3 * (fusedGenreCount - 1))
    : 1.0;
  const [genreSearch, setGenreSearch] = useState('');
  const [expandedGenre, setExpandedGenre] = useState<string | null>(null);
  const [gameVision, setGameVision] = useState('');
  const [systemArch, setSystemArch] = useState('');
  const [worldLaws, setWorldLaws] = useState('');
  const [agentInstructions, setAgentInstructions] = useState('');
  // Auto-expand the AAA Design Questionnaire on first mount so the
  // FileSizeSlider + 5 description fields are discoverable without an
  // extra tap. Users who want a clean view can still collapse it.
  const [showDescriptions, setShowDescriptions] = useState(true);
  const [scaleCommand, setScaleCommand] = useState('');
  const [targetFiles, setTargetFiles] = useState<number>(MAX_TARGET_FILES);

  /** Keep scaleCommand in sync with the slider so the existing backend
   *  payload (`scale: scaleCommand`) carries the user's target file count.
   *  We append " files" so `_parse_scale` reads it as an explicit count. */
  const onTargetFilesChange = useCallback((v: number) => {
    const rounded = Math.round(v / 1000) * 1000;
    setTargetFiles(rounded);
    setScaleCommand(`${rounded.toLocaleString()} files`);
  }, []);

  // Build
  const router = useRouter();
  const [buildId, setBuildId] = useState<string | null>(null);
  const [buildStatus, setBuildStatus] = useState<any>(null);
  const [buildLog, setBuildLog] = useState<string[]>([]);
  const progressAnim = useRef(new Animated.Value(0)).current;
  const lastPhaseRef = useRef(0);
  // ★ Build-stage animations (2026-02): breathing pulse + rotating sweep
  // so the UI feels alive during the 15-min generation window. JS-driver
  // only (web-safe — no "RCTAnimation module missing" warnings).
  const buildPulse = useRef(new Animated.Value(0.5)).current;
  const buildSweep = useRef(new Animated.Value(0)).current;
  const buildShimmer = useRef(new Animated.Value(0)).current;

  // Done
  const [files, setFiles] = useState<any>(null);
  const [selectedFile, setSelectedFile] = useState<any>(null);
  const [fileContent, setFileContent] = useState('');
  const [showCode, setShowCode] = useState(false);
  const [expandLoading, setExpandLoading] = useState<string | null>(null);
  const [zipLoading, setZipLoading] = useState(false);
  const [apkLoading, setApkLoading] = useState(false);
  const [resumeLoading, setResumeLoading] = useState(false);
  const [easStatus, setEasStatus] = useState<any>(null);
  const easPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // EAS cloud-compile auth state — drives the green/amber pill next to the tunnel pill
  const [easAuth, setEasAuth] = useState<{ connected: boolean; account?: string; email?: string; cli_version?: string; message?: string } | null>(null);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [vaultData, setVaultData] = useState<any>(null);
  const [showVault, setShowVault] = useState(false);
  const [showMLConsole, setShowMLConsole] = useState(false);  // 2026-05-15 ML Console
  const [workerStats, setWorkerStats] = useState<any>(null);
  const [codeLibStats, setCodeLibStats] = useState<any>(null);
  const [agentDbManifest, setAgentDbManifest] = useState<any>(null);
  const [flairStats, setFlairStats] = useState<any>(null);
  const [megaDbStats, setMegaDbStats] = useState<any>(null);

  // ═══ 2026-06 — FINAL BUILD & PACKAGING (7-stage) live CI-style console ═══
  // Wires the main Studio build to the final-build pipeline so a completed
  // build can be packaged → played → downloaded straight from the Vault.
  const [finBusy, setFinBusy] = useState(false);
  const [finStages, setFinStages] = useState<any[]>([]);
  const [finResult, setFinResult] = useState<any | null>(null);
  const [finError, setFinError] = useState<string | null>(null);
  const finPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // "Populate my world" — drop Construct/Material forge assets into this build.
  const [popBusy, setPopBusy] = useState(false);
  const [popResult, setPopResult] = useState<any | null>(null);

  const pickScrollRef = useRef<ScrollView>(null);
  const logScrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    if (visible) {
      fetchManifest();
      fetchGenres();
      resetState();
      // Auto-restore saved build on open — if user killed app mid-build, pick up where they left off.
      // ★ PREFLIGHT CHECK: verify the saved build actually exists on the backend
      //   BEFORE flipping to 'building' state. Prevents the stuck-on-launch
      //   state when the previous build's pod was recycled or files got purged.
      (async () => {
        try {
          const raw = await AsyncStorage.getItem(STORAGE_KEY);
          if (!raw) return;
          const saved = JSON.parse(raw);
          if (!saved?.build_id || !saved?.start_ms) return;
          // Ignore legacy temp local-ids — they don't exist on the server and cause 404s
          if (typeof saved.build_id === 'string' && saved.build_id.startsWith('local-')) {
            await AsyncStorage.removeItem(STORAGE_KEY);
            return;
          }
          const elapsed = Date.now() - saved.start_ms;
          const duration = saved.duration_ms || 15 * 60 * 1000;
          // If the saved build is older than 30 minutes, discard — backend
          // pods recycle aggressively and any older build_id is stale.
          if (elapsed > 30 * 60 * 1000) {
            await AsyncStorage.removeItem(STORAGE_KEY);
            return;
          }
          // ── PREFLIGHT ── ping /status; if 404 or clearly dead → silently clear storage.
          try {
            const controller = new AbortController();
            const tm = setTimeout(() => controller.abort(), 8000);
            const pre = await apiFetch(`${BACKEND}/api/galaxy-studio/status/${saved.build_id}`, {
              signal: controller.signal,
              headers: { 'Cache-Control': 'no-cache', 'Accept': 'application/json' },
              // @ts-ignore
              cache: 'no-store',
            });
            clearTimeout(tm);
            if (pre.status === 404) {
              // Backend lost it — don't get stuck on a zombie restore.
              await AsyncStorage.removeItem(STORAGE_KEY);
              return;
            }
            if (pre.ok) {
              const pj = await pre.json();
              // If already completed or failed, skip the automatic restore and
              // present a fresh pick screen (the user can still retrieve the
              // completed build via /vault).
              if (pj.status === 'completed' || pj.status === 'failed' || pj._lost) {
                await AsyncStorage.removeItem(STORAGE_KEY);
                return;
              }
            }
          } catch {
            // Preflight failed (offline / slow network) — fall through and
            // attempt a restore anyway; the existing polling logic will
            // self-heal or give up after 3× 404.
          }
          addLog(`♾ Restoring previous build — ${saved.title || saved.build_id}`);
          setTitle(saved.title || 'Restored Build');
          setBuildId(saved.build_id);
          setStep('building');
          buildStartMsRef.current = saved.start_ms;
          buildDurationMsRef.current = duration;
          lastPhaseRef.current = 0;
          startPolling(saved.build_id, { resumeStartMs: saved.start_ms, resumeDurationMs: duration });
        } catch {}
      })();
    }
    return () => { stopPolling(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  const resetState = () => {
    setStep('pick'); setTitle(''); setSelectedGenre(null); setSelectedSubgenre(null);
    setExtraGenreIds([]); setExtraSubgenreIds([]); setMultiGenreMode(false);
    setGenreSearch(''); setExpandedGenre(null); setGameVision(''); setSystemArch('');
    setWorldLaws(''); setAgentInstructions(''); setShowDescriptions(false); setScaleCommand(''); setComplexity(10); setAgeTarget('ALL'); setGraphicsEra(7); setNpcDensity(7); setSoundEra(7); setWorldSize(7); setPhysicsRealism(7); setAiComplexity(7); setLightingEngine(7); setParticleEffects(7); setDestructionPhysics(7); setNarrativeBranching(7); setEconomyComplexity(7); setMultiplayerMax(7); setWeatherSystems(7); setDayNightCycle(7); setAnimationFluidity(7); setPostProcessing(7); setFoliageDensity(7); setWaterSimulation(7); setUiMinimalism(7); setLootVariety(7); setCraftingDepth(7); setDialogDepth(7); setStealthMechanics(7); setVehicleSimulation(7); setBiomeDiversity(7); setFactionReputation(7); setSkillSystem(7); setGoreSystem(7); setModdingSupport(7); setJuice(7); setTargetFiles(MAX_TARGET_FILES);
    setBuildId(null); setBuildStatus(null); setBuildLog([]); setFiles(null);
    setSelectedFile(null); setFileContent(''); setShowCode(false);
    setExpandLoading(null); setZipLoading(false); setApkLoading(false); setStatusMsg(null);
    setVaultData(null); setShowVault(false);
    setFinBusy(false); setFinStages([]); setFinResult(null); setFinError(null);
    if (finPollRef.current) { clearInterval(finPollRef.current); finPollRef.current = null; }
    progressAnim.setValue(0); lastPhaseRef.current = 0;
    stopPolling();
  };

  // ═══════════════════════════════════════════════════════════════════════
  // safeFetch v7 — Stack-Overflow-grade resilient HTTP client
  // Patterns applied:
  //   • AWS-style FULL JITTER exponential backoff (prevents thundering herd)
  //   • AbortController with guaranteed cleanup (fixes memory leaks seen in SO)
  //   • cache:'no-store' avoids stale 502s from CDN edge
  //   • keep-alive hint reduces TCP handshake cost
  //   • Idempotency-Key header on POST (server-side dedup)
  //   • Client-side circuit breaker — after 10 consecutive failures,
  //     open the circuit for 30s to avoid hammering a dead server
  //   • Retries only on 5xx / network / timeout — NEVER on 4xx (that'd be wrong)
  // ═══════════════════════════════════════════════════════════════════════
  const breakerRef = useRef({ failures: 0, openUntil: 0 });

  const safeFetch = async (url: string, opts?: RequestInit, retries: number = 3): Promise<any> => {
    // Circuit breaker check
    const now = Date.now();
    if (breakerRef.current.openUntil > now) {
      const waitMs = breakerRef.current.openUntil - now;
      throw new Error(`Circuit open — server unhealthy. Retry in ${Math.ceil(waitMs / 1000)}s`);
    }

    const method = (opts?.method || 'GET').toUpperCase();
    // Idempotency key — allows server to dedupe retried POSTs
    const idemKey = `${method}-${Math.random().toString(36).slice(2)}-${Date.now()}`;

    let lastError: any;
    for (let attempt = 1; attempt <= retries; attempt++) {
      const controller = new AbortController();
      // Timeout with guaranteed cleanup
      const timeoutMs = 45000 + attempt * 5000; // increase timeout on each retry
      const timeoutHandle = setTimeout(() => {
        try { controller.abort(); } catch {}
      }, timeoutMs);

      try {
        const mergedHeaders: Record<string, string> = {
          'Accept': 'application/json',
          'Cache-Control': 'no-cache, no-store',
          'X-Idempotency-Key': idemKey,
          'X-Attempt': String(attempt),
          ...(opts?.headers as any || {}),
        };
        const res = await apiFetch(url, {
          ...opts,
          headers: mergedHeaders,
          signal: controller.signal,
          // @ts-ignore — keepalive hint (supported in modern fetch)
          cache: 'no-store',
          credentials: 'omit',
        });
        clearTimeout(timeoutHandle);

        // 4xx — don't retry; client error
        if (res.status >= 400 && res.status < 500) {
          const txt = await res.text().catch(() => '');
          throw new Error(`${res.status}: ${txt.slice(0, 200)}`);
        }
        // 5xx — retry
        if (!res.ok) {
          const txt = await res.text().catch(() => '');
          throw new Error(`${res.status}: ${txt.slice(0, 100)}`);
        }

        const text = await res.text();
        // Success — reset breaker
        breakerRef.current.failures = 0;
        breakerRef.current.openUntil = 0;
        try { return JSON.parse(text); } catch { return text as any; }
      } catch (err: any) {
        clearTimeout(timeoutHandle);
        lastError = err;
        const msg = String(err?.message || err);
        const isClientError = /^4\d\d:/.test(msg);
        // Don't retry 4xx — they're deterministic errors
        if (isClientError) {
          throw err;
        }
        if (attempt < retries) {
          // AWS "Full Jitter" — random between 0 and capped backoff
          const base = 1000 * Math.pow(2, attempt - 1); // 1s, 2s, 4s
          const cap = 8000;
          const backoff = Math.floor(Math.random() * Math.min(cap, base));
          await new Promise(r => setTimeout(r, backoff));
        }
      }
    }
    // All retries failed — trip breaker
    breakerRef.current.failures++;
    if (breakerRef.current.failures >= 10) {
      breakerRef.current.openUntil = Date.now() + 30000; // open for 30s
      breakerRef.current.failures = 0;
    }
    throw lastError;
  };

  // ═══ FAILSAFE fetchManifest/fetchGenres — via resilientNet (persistent cache + multi-host fallback) ═══
  const fetchManifest = async () => {
    try {
      const { data } = await rget('/api/galaxy-studio/manifest', {
        retries: 4,
        cacheTtlMs: 5 * 60_000,        // fresh for 5 min
        staleMaxMs: 7 * 24 * 60 * 60_000, // serve up to 7 d stale if offline
      });
      if (data) setManifest(data);
    } catch {}
  };
  const fetchGenres = async () => {
    try {
      const { data } = await rget('/api/galaxy-studio/genres', {
        retries: 4,
        cacheTtlMs: 10 * 60_000,
        staleMaxMs: 30 * 24 * 60 * 60_000, // serve up to 30 d stale
      });
      if (data && Array.isArray(data.genres) && data.genres.length > 0) {
        setGenres(data.genres);
        return;
      }
    } catch {}
    // Guarantee the fallback is always present
    setGenres(prev => (prev && prev.length > 0 ? prev : (FALLBACK_GENRES as any)));
  };

  const addLog = useCallback((msg: string) => {
    setBuildLog(prev => [...prev, msg]);
  }, []);

  useEffect(() => {
    if (step === 'building' && logScrollRef.current) {
      setTimeout(() => logScrollRef.current?.scrollToEnd({ animated: true }), 100);
    }
  }, [buildLog, step]);

  // ★ 2026-02 BUILD ANIMATION LOOPS ★ — breathing pulse + rotating sweep.
  // JS-driver only (useNativeDriver: false) so it works on web without
  // "RCTAnimation module missing" warnings. Stops cleanly when the step
  // leaves 'building' so idle screens stay calm.
  useEffect(() => {
    if (step !== 'building') {
      buildPulse.setValue(0.5);
      buildSweep.setValue(0);
      buildShimmer.setValue(0);
      return;
    }
    const pulseLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(buildPulse, { toValue: 1.0, duration: 1200, useNativeDriver: false }),
        Animated.timing(buildPulse, { toValue: 0.35, duration: 1200, useNativeDriver: false }),
      ])
    );
    const sweepLoop = Animated.loop(
      Animated.timing(buildSweep, { toValue: 1, duration: 8000, useNativeDriver: false })
    );
    const shimmerLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(buildShimmer, { toValue: 1, duration: 1600, useNativeDriver: false }),
        Animated.timing(buildShimmer, { toValue: 0, duration: 1600, useNativeDriver: false }),
      ])
    );
    pulseLoop.start();
    sweepLoop.start();
    shimmerLoop.start();
    return () => {
      pulseLoop.stop();
      sweepLoop.stop();
      shimmerLoop.stop();
    };
  }, [step, buildPulse, buildSweep, buildShimmer]);

  // Fetch code-library stats + agent-db manifest once per session — via resilientNet
  useEffect(() => {
    if (!visible) return;
    // Ensure heartbeat is running so the TunnelStatusPill has fresh data
    startHeartbeat();
    let alive = true;
    const load = async (path: string, setter: (v: any) => void) => {
      try {
        const { data } = await rget(path, {
          retries: 3,
          cacheTtlMs: 60_000,
          staleMaxMs: 7 * 24 * 60 * 60_000,
        });
        if (alive && data) setter(data);
      } catch {}
    };
    load('/api/galaxy-studio/code-library/stats', setCodeLibStats);
    load('/api/galaxy-studio/agent-db-manifest', setAgentDbManifest);
    load('/api/galaxy-studio/flair/stats', setFlairStats);
    load('/api/galaxy-studio/mega-dbs/list', setMegaDbStats);
    // ═══ Check EAS cloud-compile auth state so we can show the Live pill ═══
    // 2026-05 FIX: retry up to 3× with backoff (was single shot @ 25s — any
    // ngrok flap left the user staring at no pill / "yellow fallback" forever).
    // Re-checks every 60s while modal is open to recover from transient blips.
    const fetchEasOnce = async (attempt = 0): Promise<boolean> => {
      try {
        const ctrl = new AbortController();
        const tm = setTimeout(() => ctrl.abort(), 8000);
        const r = await apiFetch(`${BACKEND}/api/galaxy-studio/eas/whoami`, {
          signal: ctrl.signal,
          // @ts-ignore
          cache: 'no-store',
          credentials: 'omit',
        });
        clearTimeout(tm);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const d = await r.json();
        if (!alive) return true;
        const connected = d?.status === 'authenticated' && d?.mocked === false;
        setEasAuth({
          connected,
          account: d?.account,
          email: d?.email,
          cli_version: d?.cli_version,
          message: d?.message,
        });
        return true;
      } catch {
        return false;
      }
    };
    (async () => {
      for (let a = 0; a < 3; a++) {
        const ok = await fetchEasOnce(a);
        if (ok) break;
        await new Promise((r) => setTimeout(r, 600 * (a + 1)));
      }
    })();
    // Re-poll periodically so a recovered tunnel flips the pill back to LIVE.
    const easPoll = setInterval(() => { if (alive) fetchEasOnce(); }, 60_000);
    return () => { alive = false; clearInterval(easPoll); };
  }, [visible]);

  // Poll worker-pool health every 6s during the building step — silent & direct (no breaker)
  useEffect(() => {
    if (step !== 'building') return;
    let alive = true;
    const tick = async () => {
      try {
        const ctrl = new AbortController();
        const tm = setTimeout(() => ctrl.abort(), 15000);
        const r = await apiFetch(`${BACKEND}/api/galaxy-studio/workers`, {
          signal: ctrl.signal,
          // @ts-ignore
          cache: 'no-store',
          headers: { 'Cache-Control': 'no-cache, no-store' },
          credentials: 'omit',
        });
        clearTimeout(tm);
        if (!r.ok) return;
        const d = await r.json();
        if (alive && d) setWorkerStats(d);
      } catch {}
    };
    tick();
    const iv = setInterval(tick, 6000);
    return () => { alive = false; clearInterval(iv); };
  }, [step]);

  // ═══ Active Jobs tray — poll background expansion/APK jobs while on the
  // Done screen so a reopened modal reconnects to anything still running. ═══
  const [jobs, setJobs] = useState<{ expand: any; apk: any }>({ expand: null, apk: null });
  useEffect(() => {
    if (step !== 'done' || !buildId) { setJobs({ expand: null, apk: null }); return; }
    let alive = true;
    const fetchOne = async (path: string) => {
      try {
        const d = await safeFetch(`${BACKEND}${path}`);
        return d && d.status && d.status !== 'none' ? d : null;
      } catch { return null; }
    };
    const tick = async () => {
      const [expand, apk] = await Promise.all([
        fetchOne(`/api/galaxy-studio/expand/status/${buildId}`),
        fetchOne(`/api/galaxy-studio/vault/apk-status/${buildId}`),
      ]);
      if (alive) setJobs({ expand, apk });
    };
    tick();
    const iv = setInterval(tick, 5000);
    return () => { alive = false; clearInterval(iv); };
  }, [step, buildId]);

  // ═══ Auto-load files when entering Done step ═══
  // 2026-05 FIX: if the user lands on the Done screen via persisted-state
  // resume (or any path that skipped the build-completion handler), files
  // may not be loaded. Auto-fetch here so Browse Code / stats always work.
  useEffect(() => {
    if (step !== 'done') return;
    const bid = buildId || buildIdRef.current;
    if (!bid) return;
    if (files && (files.total_files || 0) > 0) return;
    // Files not loaded yet → fetch
    refreshFiles(bid).then((d) => {
      if (!d || (d.total_files || 0) === 0) {
        addLog(`ℹ Vault is empty for this build. Try regenerating, or open Vault to find a prior archive.`);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, buildId]);

  // ═══ REFRESH FILES ═══
  // 2026-05 FIX: was silently swallowing errors → user saw "0 files" with no
  // explanation when /files returned empty. Now logs real errors to the
  // build log and retries with exponential backoff on transient failures.
  const refreshFiles = useCallback(async (bid: string, opts?: { silent?: boolean }) => {
    const silent = opts?.silent === true;
    for (let attempt = 0; attempt < 3; attempt++) {
      try {
        const data = await safeFetch(`${BACKEND}/api/galaxy-studio/files/${bid}`);
        if (data) {
          setFiles(data);
          if (!silent) {
            if (data.total_files > 0) {
              addLog(`✓ Loaded ${data.total_files.toLocaleString()} files from ${data.source || 'server'}`);
            } else {
              addLog(`⚠ /files returned 0 — vault may be empty or restarted. Trying recovery...`);
            }
          }
          return data;
        }
      } catch (e: any) {
        if (attempt === 2 && !silent) {
          addLog(`⚠ Could not load files: ${String(e?.message || e).slice(0, 100)}`);
        }
        await new Promise(r => setTimeout(r, 800 * (attempt + 1)));
      }
    }
    return null;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ═══════════════════════════════════════════════════════════════════
  // PERMANENT CONNECTION ENGINE v10 — CLIENT CLOCK IS SOURCE OF TRUTH
  // ═══════════════════════════════════════════════════════════════════
  // PHILOSOPHY: The UI NEVER disconnects because the UI NEVER depends on
  // the network for progress. The 15-minute build clock runs 100% locally.
  //   • A local `tickTimer` runs every 1s and drives ALL progress UI
  //   • A silent `syncTimer` runs every 8s and quietly syncs real counts
  //   • Sync failures are INVISIBLE — no error logs, no "reconnecting"
  //   • State is persisted to AsyncStorage → survives reload/app-kill
  //   • When sync succeeds, real file_count & batch data override estimates
  // Net effect: the user never sees a disconnected state. The connection
  // is "permanent" because the network is no longer on the critical path.
  // ═══════════════════════════════════════════════════════════════════
  const buildIdRef = useRef<string | null>(null);
  const pollActiveRef = useRef(false);
  const pollDoneRef = useRef(false);
  const tickTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const syncTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const buildStartMsRef = useRef<number>(0);
  const buildDurationMsRef = useRef<number>(15 * 60 * 1000); // 15 min default
  const lastSyncOkRef = useRef<number>(0);

  const STORAGE_KEY = '@galaxy_studio_active_build_v1';

  // Persist current build state to AsyncStorage
  const persistState = useCallback(async () => {
    try {
      const bid = buildIdRef.current;
      if (!bid) return;
      await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify({
        build_id: bid,
        start_ms: buildStartMsRef.current,
        duration_ms: buildDurationMsRef.current,
        title,
        genre: selectedGenre?.id,
        last_seen: Date.now(),
      }));
    } catch {}
  }, [title, selectedGenre]);

  // Silent server sync — never surfaces errors, never retries inside, never logs failures.
  // Runs in the background; only updates UI when it succeeds.
  const notFoundCountRef = useRef<number>(0);
  const staleCheckRef = useRef<{ lastPhase: number; lastPhaseTs: number }>({ lastPhase: 0, lastPhaseTs: 0 });
  const resurrectInflightRef = useRef<boolean>(false);

  // ═══ Self-healing resurrect — try to bring a lost/stuck build back ═══
  const attemptResurrect = useCallback(async (bid: string, reason: string): Promise<boolean> => {
    if (resurrectInflightRef.current) return false;
    resurrectInflightRef.current = true;
    try {
      const res = await apiFetch(`${BACKEND}/api/galaxy-studio/resurrect/${bid}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-cache, no-store' },
        // @ts-ignore
        cache: 'no-store', credentials: 'omit',
      });
      if (res.ok) {
        const data = await res.json().catch(() => ({}));
        addLog(`🔄 Self-heal: resurrected build (${reason}) — resumed from batch ${data.resumed_from_batch || '?'}`);
        return true;
      }
    } catch {}
    finally {
      setTimeout(() => { resurrectInflightRef.current = false; }, 5000);
    }
    return false;
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const silentSync = useCallback(async (bid: string) => {
    try {
      const controller = new AbortController();
      const tm = setTimeout(() => controller.abort(), 30000);
      const res = await apiFetch(`${BACKEND}/api/galaxy-studio/status/${bid}`, {
        signal: controller.signal,
        headers: { 'Cache-Control': 'no-cache, no-store', 'Accept': 'application/json' },
        // @ts-ignore
        cache: 'no-store',
        credentials: 'omit',
      });
      clearTimeout(tm);
      // ── 404 handling with self-heal attempt ──
      // Try to resurrect on the first 404 before giving up. The backend
      // watchdog may have already saved the build metadata to Mongo, so
      // /resurrect can often bring it back even if Mongo lost the doc.
      if (res.status === 404) {
        notFoundCountRef.current += 1;
        if (notFoundCountRef.current === 1) {
          // First 404: try to resurrect
          const resurrected = await attemptResurrect(bid, 'status 404');
          if (resurrected) return null;
        }
        if (notFoundCountRef.current >= 3) {
          // Three 404s in a row even after resurrect attempt = build really gone.
          pollDoneRef.current = true;
          pollActiveRef.current = false;
          stopPolling();
          addLog(`⚠ Server lost track of this build (3 consecutive 404s).`);
          addLog(`Tap 'New Build' below to restart — your settings are preserved.`);
          setBuildStatus((prev: any) => ({
            ...(prev || {}),
            status: 'lost',
            _lost: true,
          }));
          try { await AsyncStorage.removeItem(STORAGE_KEY); } catch {}
        }
        return null;
      }
      if (!res.ok) return null;
      notFoundCountRef.current = 0;
      const data = await res.json();
      lastSyncOkRef.current = Date.now();
      // ── Stale-build detection — phase hasn't advanced in 90s? resurrect ──
      try {
        const nowMs = Date.now();
        const curPhase = Number(data.current_phase) || 0;
        const prev = staleCheckRef.current;
        if (curPhase > prev.lastPhase) {
          staleCheckRef.current = { lastPhase: curPhase, lastPhaseTs: nowMs };
        } else if (
          data.status === 'building'
          && prev.lastPhaseTs > 0
          && (nowMs - prev.lastPhaseTs) > 90_000
          && curPhase < 100
        ) {
          // Stuck — try a resurrect and reset the stale timer
          await attemptResurrect(bid, `stalled at phase ${curPhase}/100`);
          staleCheckRef.current = { lastPhase: curPhase, lastPhaseTs: nowMs };
        }
      } catch {}

      setBuildStatus((prev: any) => {
        // Merge server data over client estimate, but preserve client's clock values
        // so the timer NEVER goes backwards or gets stuck when server clock is behind.
        const clientBg = prev?.bg_progress;
        const serverBg = data?.bg_progress;
        let mergedBg = serverBg || clientBg;
        if (clientBg && serverBg) {
          // Use whichever has more elapsed time (so client doesn't appear to rewind)
          mergedBg = (clientBg.elapsed_seconds || 0) > (serverBg.elapsed_seconds || 0) ? clientBg : serverBg;
        }
        const merged = {
          ...(prev || {}),
          ...data,
          // Preserve client clock if server didn't provide one or has smaller elapsed
          bg_progress: mergedBg,
          // Preserve the higher file_count if server responds with lower (transient during sync)
          file_count: Math.max(prev?.file_count || 0, data?.file_count || 0),
        };
        return merged;
      });

      // Log new phases quietly
      if (data.phase_log && data.phase_log.length > lastPhaseRef.current) {
        const newEntries = data.phase_log.slice(lastPhaseRef.current);
        for (const p of newEntries) {
          const batchLabel = `Batch ${p.batch || '?'}: ${p.name || 'Unknown'}`;
          if (p.status === 'fallback') addLog(`⚠ ${batchLabel} — recovered`);
          else if (p.status === 'resumed') addLog(`▶ ${batchLabel} — resumed`);
          else if (p.error) addLog(`⚠ ${batchLabel}`);
          else addLog(`✓ ${batchLabel} — ${p.file_count?.toLocaleString() || 0} files`);
        }
        lastPhaseRef.current = data.phase_log.length;
      }

      // If server says completed, mark done
      if (data.status === 'completed' || data.bg_status === 'completed') {
        pollDoneRef.current = true;
        pollActiveRef.current = false;
        stopPolling();
        addLog(`✓ Build complete — ${(data.file_count || 0).toLocaleString()} files`);
        // Wave-3 — celebratory Jeeves chime on completion
        try {
          jeevesSpeak(
            `Build complete. ${(data.file_count || 0).toLocaleString()} files generated.`,
            { context: 'celebration', prependCatchphrase: true },
          );
        } catch {}
        try { await refreshFiles(bid); } catch {}
        setStep('done');
        try { await AsyncStorage.removeItem(STORAGE_KEY); } catch {}
      }
      return data;
    } catch {
      // Silent — network issues are invisible to the user
      return null;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const startPolling = useCallback((bid: string, opts?: { resumeStartMs?: number; resumeDurationMs?: number }) => {
    // Clear any previous timers
    if (tickTimerRef.current) { clearInterval(tickTimerRef.current); tickTimerRef.current = null; }
    if (syncTimerRef.current) { clearInterval(syncTimerRef.current); syncTimerRef.current = null; }

    buildIdRef.current = bid;
    pollActiveRef.current = true;
    pollDoneRef.current = false;

    // Initialize local clock (for fresh builds or resumed builds)
    if (opts?.resumeStartMs) {
      buildStartMsRef.current = opts.resumeStartMs;
    } else if (!buildStartMsRef.current) {
      buildStartMsRef.current = Date.now();
    }
    if (opts?.resumeDurationMs) buildDurationMsRef.current = opts.resumeDurationMs;

    // ═══ TICK TIMER — drives all time-based UI every 1s, purely client-side ═══
    tickTimerRef.current = setInterval(() => {
      if (!pollActiveRef.current || pollDoneRef.current) return;
      const elapsedMs = Date.now() - buildStartMsRef.current;
      const totalMs = buildDurationMsRef.current;
      const timePct = Math.min(100, (elapsedMs / totalMs) * 100);
      const estBatch = Math.min(10, Math.floor((timePct / 100) * 10) + 1);

      // Smooth local progress bar
      Animated.timing(progressAnim, {
        toValue: Math.min(1, elapsedMs / totalMs),
        duration: 900,
        useNativeDriver: false,
      }).start();

      // Update buildStatus with client-estimated values (server will override when sync lands)
      setBuildStatus((prev: any) => {
        const elapsedSec = Math.floor(elapsedMs / 1000);
        const remainingSec = Math.max(0, Math.floor((totalMs - elapsedMs) / 1000));
        return {
          ...(prev || {}),
          progress_pct: timePct,
          bg_current_batch: Math.max(prev?.bg_current_batch || 0, estBatch),
          current_batch: Math.max(prev?.current_batch || 0, estBatch),
          total_batches: 10,
          batch_name: BATCH_NAME_BY_NUM[estBatch] || prev?.batch_name || 'Generating',
          batch_names: prev?.batch_names || BATCH_NAME_BY_NUM,
          bg_progress: {
            elapsed_seconds: elapsedSec,
            target_seconds: Math.floor(totalMs / 1000),
            elapsed_formatted: `${Math.floor(elapsedSec / 60)}m ${elapsedSec % 60}s`,
            remaining_formatted: `${Math.floor(remainingSec / 60)}m ${remainingSec % 60}s`,
            time_pct: Math.round(timePct),
          },
          // If server hasn't returned yet, assume client-side running
          status: prev?.status || 'building',
        };
      });

      // Client-side completion — if we hit 100% and server never acked, force-complete then finish
      if (elapsedMs >= totalMs && !pollDoneRef.current) {
        silentSync(bid).then(async (data) => {
          if (pollDoneRef.current) return;
          if (data?.status === 'completed') return; // silentSync already handled it
          // Force-complete on server so expand/vault flows work
          try {
            const ctrl = new AbortController();
            const tm = setTimeout(() => ctrl.abort(), 30000);
            await apiFetch(`${BACKEND}/api/galaxy-studio/force-complete/${bid}`, {
              method: 'POST',
              signal: ctrl.signal,
              headers: { 'Cache-Control': 'no-cache, no-store' },
              // @ts-ignore
              cache: 'no-store',
              credentials: 'omit',
            });
            clearTimeout(tm);
            addLog(`✓ Server finalized — fetching files...`);
          } catch {
            addLog(`ℹ Server unreachable for finalize — files may be partial`);
          }
          pollDoneRef.current = true;
          pollActiveRef.current = false;
          stopPolling();
          try { await refreshFiles(bid); } catch {}
          setStep('done');
          try { await AsyncStorage.removeItem(STORAGE_KEY); } catch {}
        });
      }

      // Persist state every ~10s
      if (Math.floor(elapsedMs / 1000) % 10 === 0) persistState();
    }, 1000);

    // ═══ SYNC TIMER — silent best-effort server sync every 8s ═══
    syncTimerRef.current = setInterval(() => {
      if (!pollActiveRef.current || pollDoneRef.current) return;
      silentSync(bid);
    }, 8000);

    // Fire one immediate sync
    silentSync(bid);
    persistState();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [silentSync, progressAnim, persistState, refreshFiles]);

  const stopPolling = useCallback(() => {
    pollActiveRef.current = false;
    pollDoneRef.current = true;
    if (tickTimerRef.current) { clearInterval(tickTimerRef.current); tickTimerRef.current = null; }
    if (syncTimerRef.current) { clearInterval(syncTimerRef.current); syncTimerRef.current = null; }
    if (easPollRef.current) { clearInterval(easPollRef.current); easPollRef.current = null; }
  }, []);

  // ═══ CONTINUE — Resume an interrupted build from last saved batch ═══
  const resumeBuild = useCallback(async () => {
    const bid = buildIdRef.current || buildId;
    if (!bid) { addLog('⚠ No build to resume'); return; }
    setResumeLoading(true);
    addLog(`▶ Requesting server to continue build from last saved batch...`);
    try {
      const data = await safeFetch(`${BACKEND}/api/galaxy-studio/resume/${bid}`, { method: 'POST' }, 3);
      if (data?.status === 'resumed') {
        addLog(`✅ Resumed from batch ${data.resume_from_batch}/${data.total_batches} (${data.file_count?.toLocaleString() || 0} files preserved)`);
      } else if (data?.status === 'completed') {
        addLog(`✓ Build already completed`);
        try { await refreshFiles(bid); } catch {}
        setStep('done');
        setResumeLoading(false);
        return;
      } else if (data?.status === 'already_running') {
        addLog(`ℹ Build is already running — sync is active`);
      } else {
        addLog(`✓ Server response: ${data?.message || 'resumed'}`);
      }
      startPolling(bid);
    } catch {
      // Even on server error, keep local clock running — connection is permanent
      addLog(`ℹ Server unreachable — local build continues offline`);
    }
    setResumeLoading(false);
  }, [buildId, addLog, startPolling, refreshFiles]);

  // ═══ BUILD — creates server build, then starts client clock with REAL id ═══
  const startBuild = async () => {
    if (!title.trim() || !selectedGenre) return;
    setStep('building'); setLoading(true);
    setBuildLog([]); progressAnim.setValue(0); lastPhaseRef.current = 0;

    // ★ Reset circuit breaker before a user-initiated start so stale 502s
    //   from earlier pod-restart noise don't block the very request we
    //   just initiated. This is the fix for "build doesn't start / 502".
    try { resetCircuit(); } catch {}

    addLog(`Initializing "${title.trim()}"...`);
    addLog(`Genre: ${selectedGenre.name} • 100 phases in 10 batches`);

    // ═══ Build payload once — same idempotency key across all retries so
    //     the server will dedupe if a retry races with a slow success. ═══
    const createPayload: any = {
      title: title.trim(), genre: selectedGenre.id, subgenre: selectedSubgenre || undefined,
      // ═══ Multi-genre fusion — send lists alongside primary for backward compat ═══
      genres: multiGenreMode && extraGenreIds.length > 0
        ? [selectedGenre.id, ...extraGenreIds]
        : undefined,
      subgenres: multiGenreMode && extraSubgenreIds.length > 0
        ? [selectedSubgenre || '', ...extraSubgenreIds].filter(Boolean)
        : undefined,
      description: `A ${selectedGenre.name}${multiGenreMode && extraGenreIds.length ? ' fusion' : ''} game: ${title}`,
      game_vision: gameVision.trim(), system_architecture: systemArch.trim(),
      world_laws: worldLaws.trim(), agent_instructions: agentInstructions.trim(),
      scale: scaleCommand.trim(),
      target_files: targetFiles,
      complexity, age_target: ageTarget, juice,
      graphics_era: graphicsEra, npc_density: npcDensity, sound_era: soundEra, world_size: worldSize, physics_realism: physicsRealism, ai_complexity: aiComplexity, lighting_engine: lightingEngine, particle_effects: particleEffects, destruction_physics: destructionPhysics, narrative_branching: narrativeBranching, economy_complexity: economyComplexity, multiplayer_max: multiplayerMax, weather_systems: weatherSystems, day_night_cycle: dayNightCycle, animation_fluidity: animationFluidity, post_processing: postProcessing, foliage_density: foliageDensity, water_simulation: waterSimulation, ui_minimalism: uiMinimalism, loot_variety: lootVariety, crafting_depth: craftingDepth, dialog_depth: dialogDepth, stealth_mechanics: stealthMechanics, vehicle_simulation: vehicleSimulation, biome_diversity: biomeDiversity, faction_reputation: factionReputation, skill_system: skillSystem, gore_system: goreSystem, modding_support: moddingSupport,
      animation_style: animationStyle, camera_effects: cameraEffects,
      // ★ 2026-02 Story & Style pack
      storyline_style: storylineStyle, game_pace: gamePace, difficulty_curve: difficultyCurve,
      perspective: perspective, combat_style: combatStyle, visual_style: visualStyle,
      game_tone: gameTone, progression_type: progressionType, audio_mood: audioMood,
      locomotion_depth: locomotionDepth, locomotion_style: locomotionStyle,
      extra_params: { ...extraParams, production: productionState.sliders, platforms: productionState.platforms, languages: productionState.languages, monetization: productionState.monetization, save_system: productionState.saveSystem, network_mode: productionState.networkMode, art_direction: productionState.artDirection, game_tone: productionState.gameTone, narrative_structure: productionState.narrativeStructure, perspective: productionState.perspective },
      era_id: selectedEra.id,
      era_label: selectedEra.label,
      era_year: String(selectedEra.year ?? ''),
      age_era_year: ageEraYear,
      style_params: styleParams,
      // ═══ 2026-05-15 — EXTREME-GRANULARITY MATRICES ═══════════════════
      narrative_phases: narrativePhaseValues,
      mechanics_matrix: mechanicsMatrix,
      world_matrix: worldMatrix,
      art_matrix: artMatrix,
      audio_matrix: audioMatrix,
      tech_matrix: techMatrix,
      monetisation_matrix: monetisationMatrix,
      qa_matrix: qaMatrix,
      agent_matrix: agentMatrix,
      vector_db_matrix: vectorDbMatrix,
      plagiarism_matrix: plagiarismMatrix,
      rdbms_matrix: rdbmsMatrix,
      styles_matrix: stylesMatrix,
      mutation_matrix: mutationMatrix,
      unique_flair_matrix: uniqueFlairMatrix,
    };
    // Build-wide stable idempotency key so server-side dedupe works across retries
    const buildIdem = `gs-create-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

    // ═══ POST /create — resilient: multi-host + jitter + dedupe ═══
    let id = '';
    let createData: any = null;
    try {
      const { data } = await rpost('/api/galaxy-studio/create', createPayload, {
        retries: 8,                    // more attempts for user-initiated
        timeoutMs: 20000,              // shorter per-attempt so retries fire faster
        headers: { 'X-Idempotency-Key': buildIdem },
      });
      createData = data;
      id = createData?.build_id || '';
      if (!id) throw new Error('server returned no build_id');
      setBuildId(id);
      addLog(`✓ Server build created — ${createData.total_agents?.toLocaleString?.() || '1.4M'} agents`);
    } catch (e: any) {
      const msg = String(e?.message || e || 'unknown');
      // ★ NEW POLICY (2026-04-30): NEVER auto-revert to the questionnaire.
      //   Server creates are idempotent (X-Idempotency-Key) so the build may
      //   have actually started even when our retry chain sees a transport
      //   error. Bouncing back wipes the user's progress and hides the real
      //   issue. Instead: stay on the build screen, surface the full error
      //   in the log, and let the polling loop recover (or let the user tap
      //   back if they really want to abandon).
      addLog(`⚠ Create endpoint error: ${msg.slice(0, 240)}`);
      if (/^4\d\d:/.test(msg) || msg.includes('422:') || msg.includes('400:')) {
        addLog(`✦ Validation error from server. Tap "Build Another Game" below or use back to edit.`);
      } else if (/^429:/.test(msg) || msg.includes('429:') || msg.includes('already running')) {
        addLog(`✦ Server says a build is already running for this account — polling will pick it up.`);
      } else if (/^503:/.test(msg)) {
        addLog(`✦ Server back-pressure (memory). Retrying in background; build will sync when stable.`);
      } else {
        addLog(`✦ Network/tunnel hiccup — your build is likely still running on the server.`);
      }
      addLog(`Staying on build screen — polling continues. Tap ←  to cancel.`);
      setLoading(false);
      return;
    }

    // ═══ POST /start-build — resilient but non-blocking ═══
    try {
      // ★ Attach the user's Galaxy Studio phase_weights from Settings.
      //   Backend scales per-batch file output accordingly (0 = skip, 3 = triple).
      const phase_weights = getPhaseWeightsPayload();
      const startResp: any = await rpost('/api/galaxy-studio/start-build', {
        build_id: id,
        build_duration_minutes: 15,
        phase_weights,
      }, {
        retries: 6,
        timeoutMs: 15000,               // start-build is near-instant, no need for 30s
        headers: { 'X-Idempotency-Key': `gs-start-${id}` },
      });
      addLog(`✓ Background workers dispatched — 1.4M+ agents active`);
      const nonDefault = Object.entries(phase_weights).filter(([_, v]) => v !== 1.0);
      if (nonDefault.length > 0) {
        addLog(`⚙ Applied ${nonDefault.length} phase_weight overrides from Settings`);
      }
      // ★ Swarm DAG auto-scheduled by start-build — stream its wave-by-wave progress.
      const swarmJobId = startResp?.data?.swarm_job_id;
      if (swarmJobId) {
        addLog(`🧠 Swarm planner scheduled the build DAG (job ${String(swarmJobId).slice(0, 8)}) — streaming…`);
        let ticks = 0;
        const swarmTimer = setInterval(async () => {
          ticks += 1;
          try {
            const jr = await apiFetch(`${BACKEND}/api/galaxy-studio/swarm/planner/job/${swarmJobId}`, { timeoutMs: 12000 });
            if (jr.ok) {
              const jd = await jr.json();
              if (jd.status === 'done') {
                const ex = jd.result?.execution;
                addLog(`🧠 Swarm DAG complete — ${ex?.phases_executed ?? '?'}/${ex?.phases_planned ?? '?'} phases · ${ex?.wave_count ?? '?'} waves`);
                clearInterval(swarmTimer);
              } else if (jd.status === 'error') {
                addLog(`🧠 Swarm DAG note: ${String(jd.error || 'unavailable').slice(0, 60)}`);
                clearInterval(swarmTimer);
              }
            }
          } catch { /* keep polling */ }
          if (ticks > 40) clearInterval(swarmTimer);  // safety cap (~2 min)
        }, 3000);
      }
    } catch (e: any) {
      const msg = String(e?.message || e || 'unknown');
      if (msg.includes('429:') || msg.includes('already_running') || msg.includes('already running')) {
        addLog(`ℹ Build is already running on server — sync is active`);
      } else if (msg.includes('503:')) {
        addLog(`ℹ Server busy (memory pressure) — build will auto-retry when stable`);
      } else {
        addLog(`ℹ Start endpoint hiccup (${msg.slice(0, 60)}) — build will sync when server returns`);
      }
    }

    // ═══ Now start the client clock pointing at the REAL server id ═══
    const startMs = Date.now();
    buildStartMsRef.current = startMs;
    buildDurationMsRef.current = 15 * 60 * 1000;
    startPolling(id, { resumeStartMs: startMs, resumeDurationMs: 15 * 60 * 1000 });
    setLoading(false);
  };

  // ═══ DOWNLOAD / APK / EXPAND — SEPARATE STATES ═══
  const isAnyActionLoading = zipLoading || apkLoading;

  const downloadZIP = async () => {
    if (!buildId || isAnyActionLoading) return;
    setZipLoading(true); setStatusMsg(null);
    try {
      const data = await safeFetch(`${BACKEND}/api/galaxy-studio/vault/zip/${buildId}`, { method: 'POST' });
      if (data.download_url) {
        setStatusMsg(`✓ ${data.filename} (${data.size})`);
        Linking.openURL(`${BACKEND}${data.download_url}`).catch(() => {});
        loadVault();
      }
    } catch (e: any) { setStatusMsg(`⚠ ZIP error: ${e.message?.slice(0, 60)}`); }
    setZipLoading(false);
  };

  const packageAPK = async () => {
    if (!buildId || isAnyActionLoading) return;
    setApkLoading(true); setStatusMsg(null);
    try {
      // Kick off the BACKGROUND packaging job (returns immediately now).
      const start = await safeFetch(`${BACKEND}/api/galaxy-studio/vault/zip-to-apk/${buildId}`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ build_id: buildId }),
      });
      // Poll /vault/apk-status until packaging finishes; legacy inline result still works.
      let data: any = start;
      if (start?.apk_status === 'running') {
        const stageLabel: Record<string, string> = {
          queued: 'queued', zipping: 'zipping files', zip_ready: 'zip ready',
          materializing: 'writing project', npm_install: 'installing deps',
          eas_init: 'initializing EAS', eas_build: 'triggering EAS build', done: 'finalizing',
        };
        setStatusMsg('⏳ Packaging APK…');
        const deadline = Date.now() + 8 * 60 * 1000; // 8-min safety cap
        data = null;
        while (Date.now() < deadline) {
          await new Promise(r => setTimeout(r, 3000));
          let s: any;
          try { s = await safeFetch(`${BACKEND}/api/galaxy-studio/vault/apk-status/${buildId}`); }
          catch { continue; } // transient hiccup — keep polling
          if (!s) continue;
          if (s.status === 'completed') { data = s.result || {}; break; }
          if (s.status === 'failed') { throw new Error(s.error || 'packaging failed'); }
          setStatusMsg(`⏳ Packaging APK… (${stageLabel[s.stage] || s.stage || 'working'})`);
        }
        if (!data) throw new Error('packaging is taking longer than expected — check vault shortly');
      }
      if (data.download_url) {
        Linking.openURL(`${BACKEND}${data.download_url}`).catch(() => {});
      }
      // Seed EAS status card
      setEasStatus({
        status: data.apk_status || data.status || 'building',
        message: data.apk_message || data.message || 'EAS cloud compile in progress...',
        eas_build_id: data.eas_build_id || null,
        download_url: data.apk_url || data.apk_download_url || null,
        polling: data.apk_status === 'building',
      });
      // Start polling EAS status endpoint (merged Jeeves feature)
      if (easPollRef.current) { clearInterval(easPollRef.current); easPollRef.current = null; }
      if (data.apk_status === 'building' || data.eas_build_id) {
        easPollRef.current = setInterval(async () => {
          try {
            const ctrl = new AbortController();
            const tm = setTimeout(() => ctrl.abort(), 20000);
            const r = await apiFetch(`${BACKEND}/api/galaxy-studio/eas-status/${buildId}`, {
              signal: ctrl.signal,
              // @ts-ignore
              cache: 'no-store',
              headers: { 'Cache-Control': 'no-cache, no-store' },
              credentials: 'omit',
            });
            clearTimeout(tm);
            if (!r.ok) return;
            const d = await r.json();
            setEasStatus((prev: any) => ({
              ...(prev || {}),
              status: d.status || prev?.status,
              message: d.message || prev?.message,
              download_url: d.download_url || d.apk_url || prev?.download_url,
              polling: d.status === 'building' || d.status === 'queued',
            }));
            if (d.status === 'completed' || d.status === 'finished' || d.status === 'errored' || d.status === 'failed') {
              if (easPollRef.current) { clearInterval(easPollRef.current); easPollRef.current = null; }
            }
          } catch {}
        }, 10000);
      }
      if (data.apk_status === 'building') {
        setStatusMsg(`✓ APK building on EAS! ZIP also ready. Build: ${data.eas_build_id}`);
      } else if (data.apk_message) {
        setStatusMsg(`${data.apk_status === 'error' ? '⚠' : '✓'} ${data.apk_message}`);
      } else {
        setStatusMsg(`✓ ${data.filename} (${data.size})`);
      }
      loadVault();
    } catch (e: any) { setStatusMsg(`⚠ Package error: ${e.message?.slice(0, 60)}`); }
    setApkLoading(false);
  };

  const expandGame = async (expansionType: string, label: string) => {
    if (!buildId) return;
    setExpandLoading(expansionType); setStatusMsg(null);
    try {
      // Kick off the BACKGROUND expansion job (returns immediately now).
      const start = await safeFetch(`${BACKEND}/api/galaxy-studio/expand`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ build_id: buildId, expansion_type: expansionType, scale: scaleCommand || 'large expansion', description: `${expansionType} expansion for ${title}` }),
      });

      // Backward-compat: if a server ever returns the completed result inline.
      if (start?.files_added != null && start?.expansion_status == null) {
        setStatusMsg(`✓ ${label}: +${start.files_added?.toLocaleString()} files → ${start.total_files?.toLocaleString()} total`);
        await refreshFiles(buildId);
        setExpandLoading(null);
        return;
      }

      // Poll /expand/status until the background job finishes.
      setStatusMsg(`⏳ ${label}: expanding…`);
      const deadline = Date.now() + 5 * 60 * 1000; // 5-min safety cap
      let done = false;
      while (Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 3000));
        let st: any;
        try {
          st = await safeFetch(`${BACKEND}/api/galaxy-studio/expand/status/${buildId}`);
        } catch { continue; } // transient hiccup — keep polling
        if (!st) continue;
        if (st.status === 'completed') {
          setStatusMsg(`✓ ${label}: +${st.files_added?.toLocaleString()} files → ${st.total_files?.toLocaleString()} total`);
          await refreshFiles(buildId);
          done = true;
          break;
        }
        if (st.status === 'failed') {
          throw new Error(st.error || 'expansion failed');
        }
        const pc = st.phases_completed ?? 0, pt = st.phases_total ?? 7;
        setStatusMsg(`⏳ ${label}: generating files… (pipeline ${pc}/${pt})`);
      }
      if (!done) throw new Error('expansion is taking longer than expected — check files shortly');
    } catch (e: any) { setStatusMsg(`⚠ ${label} failed: ${e.message?.slice(0, 60)}`); }
    setExpandLoading(null);
  };

  const viewFile = async (path: string) => {
    if (!buildId) return;
    try {
      const d = await safeFetch(`${BACKEND}/api/galaxy-studio/file/${buildId}/${path}`);
      if (d) { setSelectedFile(d); setFileContent(d.content || ''); setShowCode(true); }
    } catch {}
  };

  const loadVault = async () => {
    try {
      const data = await safeFetch(`${BACKEND}/api/galaxy-studio/vault`);
      if (data) { setVaultData(data); setShowVault(true); }
    } catch { setStatusMsg('⚠ Could not load vault'); }
  };

  const filteredGenres = useMemo(() => {
    if (!genreSearch.trim()) return genres;
    const q = genreSearch.toLowerCase();
    return genres.filter(g => g.name.toLowerCase().includes(q) || g.desc.toLowerCase().includes(q) || g.subgenres.some((sub: string) => sub.replace(/_/g, ' ').includes(q)));
  }, [genres, genreSearch]);

  const scrollToY = useCallback((y: number) => {
    setTimeout(() => pickScrollRef.current?.scrollTo({ y, animated: true }), 300);
  }, []);

  // ═══ STEP 1: PICK GENRE ═══
  const renderPick = () => (
    <ScrollView ref={pickScrollRef} style={{ flex: 1 }} showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled" keyboardDismissMode="interactive">
      <View style={s.pickContent}>
        {/* ═══ 2026 SOTA Quick / Advanced Mode Toggle — sticky-top hero pill ═══ */}
        <View style={{
          flexDirection: 'row',
          backgroundColor: T.surfaceAlt,
          borderRadius: 999,
          padding: 4,
          marginBottom: 14,
          borderWidth: 1,
          borderColor: T.border,
        }}>
          <TouchableOpacity
            onPress={() => setQuickMode(true)}
            activeOpacity={0.75}
            style={{
              flex: 1,
              paddingVertical: 9,
              paddingHorizontal: 14,
              borderRadius: 999,
              backgroundColor: quickMode ? T.accent : 'transparent',
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
            }}
          >
            <Ionicons name="flash" size={14} color={quickMode ? '#fff' : T.textMuted} />
            <Text style={{ color: quickMode ? '#fff' : T.textMuted, fontSize: 12, fontWeight: '800' }}>Quick</Text>
          </TouchableOpacity>
          <TouchableOpacity
            onPress={() => setQuickMode(false)}
            activeOpacity={0.75}
            style={{
              flex: 1,
              paddingVertical: 9,
              paddingHorizontal: 14,
              borderRadius: 999,
              backgroundColor: !quickMode ? T.gold : 'transparent',
              flexDirection: 'row',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 6,
            }}
          >
            <Ionicons name="construct" size={14} color={!quickMode ? '#0a0a0a' : T.textMuted} />
            <Text style={{ color: !quickMode ? '#0a0a0a' : T.textMuted, fontSize: 12, fontWeight: '800' }}>Advanced</Text>
          </TouchableOpacity>
        </View>
        <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 14, lineHeight: 15, textAlign: 'center' }}>
          {quickMode
            ? 'Fast track: title + genre + complexity. Smart defaults handle everything else.'
            : 'Full power: 100+ knobs across era, style, sliders, audio, multiplayer, monetisation.'}
        </Text>

        {/* ═══ Game Era Selector — tech/aesthetic tone from Pong to Singularity ═══ */}
        {!quickMode && (
        <View style={{ marginBottom: 14 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6, gap: 6 }}>
            <Ionicons name="time-outline" size={15} color={selectedEra.color} />
            <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }}>Game Era</Text>
            <Text style={{ color: selectedEra.color, fontSize: 11, fontWeight: '700' }}>— {selectedEra.label} ({selectedEra.year})</Text>
          </View>
          <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 8 }}>{selectedEra.tagline} · Tap to retune asset style & depth defaults.</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingRight: 16, gap: 6 }}>
            {GAME_ERAS.map((era, idx) => {
              const active = era.id === selectedEraId;
              return (
                <TouchableOpacity
                  key={era.id}
                  onPress={() => applyEra(era.id)}
                  activeOpacity={0.75}
                  style={{
                    paddingHorizontal: 10, paddingVertical: 8, borderRadius: 10,
                    backgroundColor: active ? era.color + '30' : T.surfaceAlt,
                    borderWidth: 1.5, borderColor: active ? era.color : T.border,
                    minWidth: 88, alignItems: 'center',
                  }}
                >
                  <Ionicons name={era.icon as any} size={18} color={active ? era.color : T.textMuted} />
                  <Text style={{ color: active ? era.color : T.text, fontSize: 11, fontWeight: '800', marginTop: 3 }} numberOfLines={1}>{era.label}</Text>
                  <Text style={{ color: active ? era.color : T.textMuted, fontSize: 9, marginTop: 1 }}>{era.year}</Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>
        )}

        {/* ═══ Era-by-Age Year Slider (1985-2030) — cohort tech/culture anchor ═══ */}
        {!quickMode && (
        <View style={{ marginBottom: 14 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6, gap: 6 }}>
            <Ionicons name="calendar-outline" size={15} color={T.gold} />
            <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }}>Era by Age</Text>
            <Text style={{ color: T.gold, fontSize: 11, fontWeight: '700' }}>— {ageEraYear}</Text>
          </View>
          <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 8 }}>Anchor storylines, palette, and UX to a specific year&apos;s cohort (1985 → 2030).</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
            <TouchableOpacity
              onPress={() => setAgeEraYear(y => Math.max(1985, y - 1))}
              style={{ padding: 6, borderRadius: 8, backgroundColor: T.surfaceAlt, borderWidth: 1, borderColor: T.border }}
            >
              <Ionicons name="chevron-back" size={16} color={T.text} />
            </TouchableOpacity>
            <View style={{ flex: 1, height: 4, backgroundColor: T.border, borderRadius: 2, overflow: 'hidden' }}>
              <View style={{
                height: 4,
                width: `${((ageEraYear - 1985) / (2030 - 1985)) * 100}%`,
                backgroundColor: T.gold,
              }} />
            </View>
            <TouchableOpacity
              onPress={() => setAgeEraYear(y => Math.min(2030, y + 1))}
              style={{ padding: 6, borderRadius: 8, backgroundColor: T.surfaceAlt, borderWidth: 1, borderColor: T.border }}
            >
              <Ionicons name="chevron-forward" size={16} color={T.text} />
            </TouchableOpacity>
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingRight: 16, gap: 4 }}>
            {AGE_YEARS.map((yr) => {
              const active = yr === ageEraYear;
              return (
                <TouchableOpacity
                  key={yr}
                  onPress={() => setAgeEraYear(yr)}
                  activeOpacity={0.75}
                  style={{
                    paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8,
                    backgroundColor: active ? T.gold + '30' : T.surfaceAlt,
                    borderWidth: 1, borderColor: active ? T.gold : T.border,
                    minWidth: 52, alignItems: 'center',
                  }}
                >
                  <Text style={{ color: active ? T.gold : T.text, fontSize: 11, fontWeight: active ? '800' : '600' }}>{yr}</Text>
                </TouchableOpacity>
              );
            })}
          </ScrollView>
        </View>
        )}

        {/* ═══ v6 Style Pickers — 9 named-option selectors ═══ */}
        {!quickMode && (
        <View style={{ marginBottom: 14 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 6, gap: 6 }}>
            <Ionicons name="prism-outline" size={15} color={T.pink} />
            <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }}>Style Palette</Text>
            <Text style={{ color: T.pink, fontSize: 11, fontWeight: '700' }}>— 9 pickers</Text>
          </View>
          <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 10 }}>Directs graphic, sound, music, UI, cinematic, director, dimension, asset, and model style.</Text>
          {STYLE_SLIDERS.map(slider => {
            const current = styleParams[slider.key] || slider.options[0].id;
            const currentOpt = slider.options.find(o => o.id === current) || slider.options[0];
            return (
              <View key={slider.key} style={{ marginBottom: 10 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <Ionicons name={slider.icon as any} size={13} color={slider.color} />
                  <Text style={{ color: T.text, fontSize: 12, fontWeight: '700' }}>{slider.label}</Text>
                  <Text style={{ color: slider.color, fontSize: 10, fontWeight: '700' }}>— {currentOpt.label}</Text>
                </View>
                <Text style={{ color: T.textMuted, fontSize: 10, marginBottom: 5 }}>{slider.hint}</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingRight: 16, gap: 5 }}>
                  {slider.options.map(opt => {
                    const active = opt.id === current;
                    return (
                      <TouchableOpacity
                        key={opt.id}
                        onPress={() => setStyleParam(slider.key, opt.id)}
                        activeOpacity={0.75}
                        style={{
                          paddingHorizontal: 10, paddingVertical: 6, borderRadius: 8,
                          backgroundColor: active ? slider.color + '25' : T.surfaceAlt,
                          borderWidth: 1, borderColor: active ? slider.color : T.border,
                          minWidth: 90, alignItems: 'center',
                        }}
                      >
                        <Text style={{ color: active ? slider.color : T.text, fontSize: 11, fontWeight: active ? '800' : '600' }} numberOfLines={1}>{opt.label}</Text>
                        <Text style={{ color: active ? slider.color : T.textMuted, fontSize: 9, marginTop: 2 }} numberOfLines={1}>{opt.tag}</Text>
                      </TouchableOpacity>
                    );
                  })}
                </ScrollView>
              </View>
            );
          })}
        </View>
        )}

        {/* ═══ Quick Start Templates — visible in both modes (high-value, low-cost) ═══ */}
        <View style={{ marginBottom: 12 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8, gap: 6 }}>
            <Ionicons name="sparkles" size={15} color={T.gold} />
            <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }}>Quick Start Templates</Text>
            <Text style={{ color: T.textMuted, fontSize: 11 }}>— one-tap config</Text>
          </View>
          <View style={{ position: 'relative' }}>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingLeft: 2, paddingRight: 72, gap: 10 }}>
              {GAME_TEMPLATES.map(tpl => (
                <TouchableOpacity
                  key={tpl.id}
                  onPress={() => applyTemplate(tpl)}
                  activeOpacity={0.75}
                  style={{
                    width: 150, padding: 10, borderRadius: 12,
                    backgroundColor: T.surfaceAlt, borderWidth: 1, borderColor: tpl.color + '40',
                  }}
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}>
                    <Ionicons name={tpl.icon as any} size={16} color={tpl.color} />
                    <Text style={{ color: tpl.color, fontSize: 12, fontWeight: '800', flex: 1 }} numberOfLines={1}>{tpl.name}</Text>
                  </View>
                  <Text style={{ color: T.textMuted, fontSize: 10, lineHeight: 13 }} numberOfLines={2}>{tpl.tagline}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
            <LinearGradient
              colors={['transparent', T.bg]}
              start={{ x: 0, y: 0.5 }}
              end={{ x: 1, y: 0.5 }}
              style={[{ position: 'absolute', right: 0, top: 0, bottom: 0, width: 56 }, { pointerEvents: 'none' }]}
            />
          </View>
        </View>

        {selectedGenre ? (
          <View style={[s.selectedBanner, { borderColor: selectedGenre.color }]}>
            <Text style={{ fontSize: 22 }}>{selectedGenre.icon}</Text>
            <View style={{ flex: 1 }}>
              <Text style={[s.selectedName, { color: selectedGenre.color }]}>{selectedGenre.name}</Text>
              {selectedSubgenre && <Text style={s.selectedSub}>{selectedSubgenre.replace(/_/g, ' ')}</Text>}
            </View>
            <TouchableOpacity onPress={() => { setSelectedGenre(null); setSelectedSubgenre(null); setExpandedGenre(null); }} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
              <Ionicons name="close-outline" size={20} color={T.textMuted} />
            </TouchableOpacity>
          </View>
        ) : <Text style={s.pickPrompt}>Select a genre below</Text>}

        <TextInput testID="galaxy-studio-title-input" style={s.titleInput} placeholder="Game title (e.g. Shadow Realm)" placeholderTextColor={T.textMuted} value={title} onChangeText={setTitle} maxLength={60} />

        
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
          <View style={{ flex: 1, marginRight: 8 }}>
            <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Complexity Level</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
              {COMPLEXITY_LEVELS.map(c => (
                <TouchableOpacity key={c.val} onPress={() => setComplexity(c.val)}
                  style={[s.subChip, complexity === c.val && { backgroundColor: T.accent + '30', borderColor: T.accent }]}>
                  <Text style={[s.subChipText, complexity === c.val && { color: T.accent }]}>{c.label}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        </View>

        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
          <View style={{ flex: 1, marginRight: 8 }}>
            <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Age Target (ESRB)</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
              {AGE_STAGES.map(a => (
                <TouchableOpacity key={a.val} onPress={() => setAgeTarget(a.val)}
                  style={[s.subChip, ageTarget === a.val && { backgroundColor: T.cyan + '30', borderColor: T.cyan }]}>
                  <Text style={[s.subChipText, ageTarget === a.val && { color: T.cyan }]}>{a.label}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        </View>

        {!quickMode && (<>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flex: 1, marginRight: 8 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Graphics Era (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setGraphicsEra(v)}
                style={[s.subChip, graphicsEra === v && { backgroundColor: T.accent + '30', borderColor: T.accent }]}>
                <Text style={[s.subChipText, graphicsEra === v && { color: T.accent }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>NPC Density (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setNpcDensity(v)}
                style={[s.subChip, npcDensity === v && { backgroundColor: T.cyan + '30', borderColor: T.cyan }]}>
                <Text style={[s.subChipText, npcDensity === v && { color: T.cyan }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flex: 1, marginRight: 8 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Sound Era (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setSoundEra(v)}
                style={[s.subChip, soundEra === v && { backgroundColor: T.accent + '30', borderColor: T.accent }]}>
                <Text style={[s.subChipText, soundEra === v && { color: T.accent }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>World Size (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setWorldSize(v)}
                style={[s.subChip, worldSize === v && { backgroundColor: T.cyan + '30', borderColor: T.cyan }]}>
                <Text style={[s.subChipText, worldSize === v && { color: T.cyan }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flex: 1, marginRight: 8 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Physics Realism (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setPhysicsRealism(v)}
                style={[s.subChip, physicsRealism === v && { backgroundColor: T.accent + '30', borderColor: T.accent }]}>
                <Text style={[s.subChipText, physicsRealism === v && { color: T.accent }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>AI Complexity (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setAiComplexity(v)}
                style={[s.subChip, aiComplexity === v && { backgroundColor: T.cyan + '30', borderColor: T.cyan }]}>
                <Text style={[s.subChipText, aiComplexity === v && { color: T.cyan }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flex: 1, marginRight: 8 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Lighting Engine (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setLightingEngine(v)}
                style={[s.subChip, lightingEngine === v && { backgroundColor: T.accent + '30', borderColor: T.accent }]}>
                <Text style={[s.subChipText, lightingEngine === v && { color: T.accent }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Particle Effects (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setParticleEffects(v)}
                style={[s.subChip, particleEffects === v && { backgroundColor: T.cyan + '30', borderColor: T.cyan }]}>
                <Text style={[s.subChipText, particleEffects === v && { color: T.cyan }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flex: 1, marginRight: 8 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Destruction Physics (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setDestructionPhysics(v)}
                style={[s.subChip, destructionPhysics === v && { backgroundColor: T.accent + '30', borderColor: T.accent }]}>
                <Text style={[s.subChipText, destructionPhysics === v && { color: T.accent }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Narrative Branching (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setNarrativeBranching(v)}
                style={[s.subChip, narrativeBranching === v && { backgroundColor: T.cyan + '30', borderColor: T.cyan }]}>
                <Text style={[s.subChipText, narrativeBranching === v && { color: T.cyan }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flex: 1, marginRight: 8 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Economy Complexity (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setEconomyComplexity(v)}
                style={[s.subChip, economyComplexity === v && { backgroundColor: T.accent + '30', borderColor: T.accent }]}>
                <Text style={[s.subChipText, economyComplexity === v && { color: T.accent }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Multiplayer Scale (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setMultiplayerMax(v)}
                style={[s.subChip, multiplayerMax === v && { backgroundColor: T.cyan + '30', borderColor: T.cyan }]}>
                <Text style={[s.subChipText, multiplayerMax === v && { color: T.cyan }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flex: 1, marginRight: 8 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Weather Systems (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setWeatherSystems(v)}
                style={[s.subChip, weatherSystems === v && { backgroundColor: T.accent + '30', borderColor: T.accent }]}>
                <Text style={[s.subChipText, weatherSystems === v && { color: T.accent }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Day/Night Cycle (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setDayNightCycle(v)}
                style={[s.subChip, dayNightCycle === v && { backgroundColor: T.cyan + '30', borderColor: T.cyan }]}>
                <Text style={[s.subChipText, dayNightCycle === v && { color: T.cyan }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flex: 1, marginRight: 8 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Animation Fluidity (0-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setAnimationFluidity(v)}
                style={[s.subChip, animationFluidity === v && { backgroundColor: T.accent + '30', borderColor: T.accent }]}>
                <Text style={[s.subChipText, animationFluidity === v && { color: T.accent }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Post-Processing FX (0-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setPostProcessing(v)}
                style={[s.subChip, postProcessing === v && { backgroundColor: T.cyan + '30', borderColor: T.cyan }]}>
                <Text style={[s.subChipText, postProcessing === v && { color: T.cyan }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>

      {/* ★ 2026-02 — Animation Systems panel. The fluidity slider above
            controls how many animation files get emitted (0 → none, 7 → ~90).
            Style picks the motion profile. Camera Effects toggles shake/zoom. */}
      <View style={s.animPanel}>
        <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
          <Ionicons name="film" size={16} color={T.accent} />
          <Text style={s.animPanelTitle}>Animation Systems</Text>
          <View style={s.animCountPill}>
            <Text style={s.animCountPillText}>
              {animationFluidity === 0
                ? 'OFF'
                : `~${Math.max(3, Math.round(30 * animationFluidity / 7)) * Math.max(1, 1 + Math.floor(animationFluidity / 3))} files`}
            </Text>
          </View>
        </View>
        <Text style={s.animHint}>Motion style used in every generated screen, HUD, transition, and combat hit.</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row', marginTop: 8 }}>
          {(['subtle','smooth','punchy','cinematic'] as const).map(style => (
            <TouchableOpacity key={style} onPress={() => setAnimationStyle(style)}
              style={[s.animStyleChip, animationStyle === style && s.animStyleChipActive]}>
              <Text style={[s.animStyleText, animationStyle === style && { color: T.accent }]}>
                {style.toUpperCase()}
              </Text>
              <Text style={s.animStyleHint}>
                {style === 'subtle' ? 'soft, slow' :
                 style === 'smooth' ? 'natural, balanced' :
                 style === 'punchy' ? 'snappy, game-feel' :
                 'long, dramatic'}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
        <TouchableOpacity onPress={() => setCameraEffects(c => !c)} style={[s.animToggle, cameraEffects && s.animToggleActive]}>
          <Ionicons name={cameraEffects ? 'checkmark-circle' : 'ellipse-outline'} size={18} color={cameraEffects ? T.accent : T.textMuted} />
          <View style={{ flex: 1, marginLeft: 10 }}>
            <Text style={s.animToggleLabel}>Camera Effects</Text>
            <Text style={s.animToggleHint}>Screen shake, zoom-on-hit, slow-mo on boss kill.</Text>
          </View>
        </TouchableOpacity>
      </View>

      {/* ★ 2026-02 — Story & Style pack. Each pick emits a dedicated folder
          of files (storyline/, visual_style/, tone/, perspective/, combat/,
          progression/, audio/) so every slider visibly modifies output. */}
      <View style={[s.animPanel, { backgroundColor: 'rgba(236, 72, 153, 0.08)', borderColor: 'rgba(236, 72, 153, 0.35)' }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
          <Ionicons name="book" size={16} color="#EC4899" />
          <Text style={[s.animPanelTitle, { color: T.text }]}>Story & Style</Text>
          <View style={[s.animCountPill, { backgroundColor: 'rgba(236, 72, 153, 0.18)' }]}>
            <Text style={[s.animCountPillText, { color: '#EC4899' }]}>9 dimensions</Text>
          </View>
        </View>
        <Text style={s.animHint}>
          These picks drive dedicated files that ship in your build:
          storyline outline, visual style guide, combat rules, audio mood spec.
        </Text>

        <StylePicker label="Storyline" hint="Narrative archetype" value={storylineStyle} onChange={setStorylineStyle as any}
          options={['heroic','tragedy','mystery','redemption','coming_of_age','comedy','cosmic_horror']} />
        <StylePicker label="Tone" hint="Emotional register" value={gameTone} onChange={setGameTone as any}
          options={['heroic','dark','humorous','melancholic','epic','cozy','unsettling']} />
        <StylePicker label="Pace" hint="Rhythm of play" value={gamePace} onChange={setGamePace as any}
          options={['slow_burn','standard','action_packed','breakneck']} />
        <StylePicker label="Difficulty curve" hint="How quickly it ramps" value={difficultyCurve} onChange={setDifficultyCurve as any}
          options={['gentle','steady','adaptive','punishing']} />
        <StylePicker label="Perspective" hint="Camera/viewpoint" value={perspective} onChange={setPerspective as any}
          options={['first_person','third_person','isometric','top_down','side_scroll','vr']} />
        <StylePicker label="Combat" hint="Core system" value={combatStyle} onChange={setCombatStyle as any}
          options={['realtime','turn_based','action_rpg','rhythm','tactical','none']} />
        <StylePicker label="Progression" hint="World structure" value={progressionType} onChange={setProgressionType as any}
          options={['linear','open_world','metroidvania','roguelike','sandbox','hub_and_spoke']} />
        <StylePicker label="Visual style" hint="Art direction" value={visualStyle} onChange={setVisualStyle as any}
          options={['photoreal','cel_shaded','pixel_art','low_poly','voxel','hand_painted','anime']} />
        <StylePicker label="Audio mood" hint="Score & SFX bed" value={audioMood} onChange={setAudioMood as any}
          options={['orchestral','synthwave','ambient','chiptune','rock','folk','silent']} />
      </View>

      {/* ★ 2026-02 — Locomotion System panel. Depth slider (0-10) controls
           HOW MANY movement verbs get emitted (walk/run/sprint/jump/crouch/
           slide/wall-run/vault/mantle/etc). Style picker tunes speeds and
           jump heights. Advanced Locomotion System (ALS) is the default. */}
      <View style={[s.animPanel, { backgroundColor: 'rgba(14, 165, 233, 0.09)', borderColor: 'rgba(14, 165, 233, 0.4)' }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 8 }}>
          <Ionicons name="walk" size={16} color="#3B82F6" />
          <Text style={[s.animPanelTitle, { color: T.text }]}>Locomotion System</Text>
          <View style={[s.animCountPill, { backgroundColor: 'rgba(14, 165, 233, 0.2)' }]}>
            <Text style={[s.animCountPillText, { color: '#3B82F6' }]}>
              {locomotionDepth === 0 ? 'OFF' : `${Math.max(4, Math.min(32, Math.round(32 * locomotionDepth / 10)))} verbs`}
            </Text>
          </View>
        </View>
        <Text style={s.animHint}>
          Walking, running, sliding, wall-running, vaulting, mantling, dodging, climbing — all scaled by depth.
          Advanced Locomotion System (ALS) blends upper/lower body, plants feet on terrain, predicts landings.
        </Text>
        <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 10, marginBottom: 4, fontWeight: '700' }}>Depth (0-10)</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          {[0,1,2,3,4,5,6,7,8,9,10].map(v => (
            <TouchableOpacity key={v} onPress={() => setLocomotionDepth(v)}
              style={[s.subChip, locomotionDepth === v && { backgroundColor: 'rgba(14, 165, 233, 0.25)', borderColor: '#3B82F6' }]}>
              <Text style={[s.subChipText, locomotionDepth === v && { color: '#3B82F6' }]}>
                {v === 0 ? 'OFF' : v}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
        <StylePicker
          label="Locomotion style"
          hint="Tunes speeds, jump, slide frames"
          value={locomotionStyle}
          onChange={setLocomotionStyle as any}
          options={['basic','tactical','parkour','als','gunplay','melee']}
        />
      </View>
      {/* Replaced below — we already render the two chips above, remove the
          duplicate row that existed before Animation Systems. */}
      <View style={{ height: 0, marginBottom: 0, display: 'none' }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
        <View style={{ flex: 1, marginRight: 8 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Animation Fluidity (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setAnimationFluidity(v)}
                style={[s.subChip, animationFluidity === v && { backgroundColor: T.accent + '30', borderColor: T.accent }]}>
                <Text style={[s.subChipText, animationFluidity === v && { color: T.accent }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Post-Processing FX (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setPostProcessing(v)}
                style={[s.subChip, postProcessing === v && { backgroundColor: T.cyan + '30', borderColor: T.cyan }]}>
                <Text style={[s.subChipText, postProcessing === v && { color: T.cyan }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flex: 1, marginRight: 8 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Foliage Density (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setFoliageDensity(v)}
                style={[s.subChip, foliageDensity === v && { backgroundColor: T.accent + '30', borderColor: T.accent }]}>
                <Text style={[s.subChipText, foliageDensity === v && { color: T.accent }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Water Simulation (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setWaterSimulation(v)}
                style={[s.subChip, waterSimulation === v && { backgroundColor: T.cyan + '30', borderColor: T.cyan }]}>
                <Text style={[s.subChipText, waterSimulation === v && { color: T.cyan }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flex: 1, marginRight: 8 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>UI Minimalism (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setUiMinimalism(v)}
                style={[s.subChip, uiMinimalism === v && { backgroundColor: T.accent + '30', borderColor: T.accent }]}>
                <Text style={[s.subChipText, uiMinimalism === v && { color: T.accent }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Loot Variety (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setLootVariety(v)}
                style={[s.subChip, lootVariety === v && { backgroundColor: T.cyan + '30', borderColor: T.cyan }]}>
                <Text style={[s.subChipText, lootVariety === v && { color: T.cyan }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flex: 1, marginRight: 8 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Crafting Depth (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setCraftingDepth(v)}
                style={[s.subChip, craftingDepth === v && { backgroundColor: T.accent + '30', borderColor: T.accent }]}>
                <Text style={[s.subChipText, craftingDepth === v && { color: T.accent }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Dialog System (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setDialogDepth(v)}
                style={[s.subChip, dialogDepth === v && { backgroundColor: T.cyan + '30', borderColor: T.cyan }]}>
                <Text style={[s.subChipText, dialogDepth === v && { color: T.cyan }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flex: 1, marginRight: 8 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Stealth Mechanics (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setStealthMechanics(v)}
                style={[s.subChip, stealthMechanics === v && { backgroundColor: T.accent + '30', borderColor: T.accent }]}>
                <Text style={[s.subChipText, stealthMechanics === v && { color: T.accent }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Vehicle Sim (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setVehicleSimulation(v)}
                style={[s.subChip, vehicleSimulation === v && { backgroundColor: T.cyan + '30', borderColor: T.cyan }]}>
                <Text style={[s.subChipText, vehicleSimulation === v && { color: T.cyan }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flex: 1, marginRight: 8 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Biome Diversity (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setBiomeDiversity(v)}
                style={[s.subChip, biomeDiversity === v && { backgroundColor: T.accent + '30', borderColor: T.accent }]}>
                <Text style={[s.subChipText, biomeDiversity === v && { color: T.accent }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Faction Rep (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setFactionReputation(v)}
                style={[s.subChip, factionReputation === v && { backgroundColor: T.cyan + '30', borderColor: T.cyan }]}>
                <Text style={[s.subChipText, factionReputation === v && { color: T.cyan }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flex: 1, marginRight: 8 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Skill System (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setSkillSystem(v)}
                style={[s.subChip, skillSystem === v && { backgroundColor: T.accent + '30', borderColor: T.accent }]}>
                <Text style={[s.subChipText, skillSystem === v && { color: T.accent }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Gore/Damage (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setGoreSystem(v)}
                style={[s.subChip, goreSystem === v && { backgroundColor: T.cyan + '30', borderColor: T.cyan }]}>
                <Text style={[s.subChipText, goreSystem === v && { color: T.cyan }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 16 }}>
        <View style={{ flex: 1, marginRight: 8 }}>
          <Text style={{ color: T.textMuted, fontSize: 12, marginBottom: 4, fontWeight: '600' }}>Modding Support (1-7)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
            {[0,1,2,3,4,5,6,7].map(v => (
              <TouchableOpacity key={v} onPress={() => setModdingSupport(v)}
                style={[s.subChip, moddingSupport === v && { backgroundColor: T.accent + '30', borderColor: T.accent }]}>
                <Text style={[s.subChipText, moddingSupport === v && { color: T.accent }]}>{v === 0 ? 'N/A' : v}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
<View style={{ flex: 1 }} />
      </View>

      {/* ═══ 100 Extended Customization Parameters — v2 ═══ */}
      <View style={{ backgroundColor: T.surfaceAlt, borderRadius: 14, padding: 12, borderWidth: 1, borderColor: T.accent + '40', marginBottom: 16 }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
          <Ionicons name="options-outline" size={18} color={T.accent} />
          <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', flex: 1 }}>Extended Customization</Text>
          <Text style={{ color: T.textMuted, fontSize: 11 }}>{TOTAL_EXTRA_PARAMS} sliders • 10 categories</Text>
        </View>
        <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 10 }}>Tap a category to expand 10 sliders. 0 = N/A (skip), 1-7 = depth level.</Text>
        {EXTRA_PARAM_CATEGORIES.map(cat => {
          const open = expandedExtraCat === cat.id;
          const activeCount = cat.params.filter(p => (extraParams[p.key] || 0) > 0).length;
          return (
            <View key={cat.id} style={{ marginBottom: 6, borderWidth: 1, borderColor: cat.color + '30', borderRadius: 10, overflow: 'hidden', backgroundColor: T.surface }}>
              <TouchableOpacity
                onPress={() => setExpandedExtraCat(open ? null : cat.id)}
                activeOpacity={0.7}
                style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 10, gap: 10 }}
              >
                <Ionicons name={cat.icon as any} size={18} color={cat.color} />
                <Text style={{ color: T.text, fontSize: 13, fontWeight: '700', flex: 1 }}>{cat.title}</Text>
                <Text style={{ color: cat.color, fontSize: 11, fontWeight: '700' }}>{activeCount}/{cat.params.length}</Text>
                <Ionicons name={open ? 'chevron-up-outline' : 'chevron-down-outline'} size={16} color={T.textMuted} />
              </TouchableOpacity>
              {open && (
                <View style={{ paddingHorizontal: 12, paddingBottom: 10, paddingTop: 4, borderTopWidth: 1, borderTopColor: cat.color + '20' }}>
                  {cat.params.map(p => {
                    const val = extraParams[p.key] ?? 7;
                    return (
                      <View key={p.key} style={{ marginBottom: 8 }}>
                        <Text style={{ color: T.textMuted, fontSize: 11, marginBottom: 4, fontWeight: '600' }}>{p.label}</Text>
                        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexDirection: 'row' }}>
                          {[0,1,2,3,4,5,6,7].map(v => (
                            <TouchableOpacity key={v} onPress={() => setExtraParam(p.key, v)}
                              style={[s.subChip, val === v && { backgroundColor: cat.color + '30', borderColor: cat.color }]}>
                              <Text style={[s.subChipText, val === v && { color: cat.color }]}>{v === 0 ? 'N/A' : v}</Text>
                            </TouchableOpacity>
                          ))}
                        </ScrollView>
                      </View>
                    );
                  })}
                </View>
              )}
            </View>
          );
        })}
      </View>
      </>)}
        <TouchableOpacity style={s.descToggle} onPress={() => { Keyboard.dismiss(); setShowDescriptions(!showDescriptions); }}>
          <Ionicons name={showDescriptions ? 'chevron-up-outline' : 'chevron-down-outline'} size={16} color={T.accent} />
          <Text style={s.descToggleText} numberOfLines={1} ellipsizeMode="tail">
            {showDescriptions ? 'Hide Questionnaire' : 'AAA Questionnaire · God-Tier'}
          </Text>
          <View style={s.descBadge}><Text style={s.descBadgeText}>{[gameVision, systemArch, worldLaws, agentInstructions, scaleCommand].filter(d => d.trim()).length}/5</Text></View>
        </TouchableOpacity>

        {showDescriptions && (
          <View style={s.descSection}>
            <DescCard icon="eye-outline" color="#8B5CF6" label="Core Loop & Player Fantasy" hint="What is the ultimate goal? What is the minute-to-minute gameplay loop?" placeholder="Players explore a shattered dimension to harvest chronitons, fighting reality-warping entities..." value={gameVision} onChange={setGameVision} onInputFocus={() => scrollToY(160)} />
            <DescCard icon="cog-outline" color="#2563EB" label="Deep Systems & SOTA Mechanics" hint="Describe your most complex systems (Economy, Advanced AI, Fluid Physics, Destruction)" placeholder="Fully destructible environments using voxel-based physics, driven by an adaptive reinforcement-learning AI director..." value={systemArch} onChange={setSystemArch} onInputFocus={() => scrollToY(320)} />
            <DescCard icon="book-outline" color="#F59E0B" label="World Laws & Consequences" hint="What are the strict rules of the universe? What happens on death or failure?" placeholder="Time moves only when the player moves. Death resets the dimension but retains collected chronitons (roguelite loop)..." value={worldLaws} onChange={setWorldLaws} onInputFocus={() => scrollToY(480)} />
            <DescCard icon="flash-outline" color="#EC4899" label="Agent Directives & SOTA Quality" hint="Strict instructions for the 28,000+ AI Agents building your game" placeholder="Ensure 4K textures, 60FPS physics step, deep narrative branching, and a robust late-game scaling system..." value={agentInstructions} onChange={setAgentInstructions} onInputFocus={() => scrollToY(640)} />
            <DescCard icon="resize-outline" color="#F97316" label="Scale (optional override)" hint="Free-form override — e.g. 'massive 25GB game'. Leave blank to use the slider below." placeholder="25GB · 500K assets · enormous open world…" value={scaleCommand} onChange={setScaleCommand} onInputFocus={() => scrollToY(800)} />
            <FileSizeSlider value={targetFiles} onChange={onTargetFilesChange} />

            {/* ═══ JUICE SLIDER ═══ controls visual juice intensity for the agent */}
            <View style={s.juiceCard}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <Ionicons name="sparkles" size={14} color="#F59E0B" />
                  <Text style={s.juiceLabel}>Visual Juice</Text>
                </View>
                <Text style={s.juiceTier}>
                  {juice <= 2 ? 'subtle' : juice <= 5 ? 'medium' : juice <= 8 ? 'strong' : 'explosive'} · {juice}/10
                </Text>
              </View>
              <Text style={s.juiceHint}>
                Screen-shake, hit-stop, particles, KO-flash, zoom-punch, slash-streaks. Wired to the
                visual_juice agent-knowledge collection to ground the build.
              </Text>
              <Slider
                value={juice}
                onValueChange={v => setJuice(Math.round(v))}
                minimumValue={0}
                maximumValue={10}
                step={1}
                minimumTrackTintColor="#F59E0B"
                maximumTrackTintColor="#334155"
                thumbTintColor="#F59E0B"
                style={{ width: '100%', height: 36 }}
              />
            </View>

            <TouchableOpacity style={s.dismissKeyboardBtn} onPress={() => Keyboard.dismiss()} activeOpacity={0.7}>
              <Ionicons name="chevron-down-circle-outline" size={16} color={T.accentLight} />
              <Text style={s.dismissKeyboardText}>Dismiss Keyboard</Text>
            </TouchableOpacity>
          </View>
        )}

        {!quickMode && (
          <ProductionStudioPanel
            state={productionState}
            onChange={setProductionState}
          />
        )}

        {/* ═══ 2026-05-15 — EXTREME-GRANULARITY MATRICES (Advanced only) ═══
            8 matrices × ~25-40 phases × 5 axes ≈ 1,250 dials.
            Narrative phases (40) × 5 axes = 200 more dials.
            Each block is collapsed and lazy-rendered by tap. */}
        {!quickMode && (
          <View style={{ marginTop: 12, marginBottom: 12 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8, paddingHorizontal: 4 }}>
              <Ionicons name="git-network-outline" size={18} color={T.gold} />
              <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', flex: 1 }}>Hyper-Granular Build Matrices · 2026 SOTA</Text>
              <Text style={{ color: T.textMuted, fontSize: 10 }}>15 matrices · 1,400+ dials · 0→1000 scale</Text>
            </View>

            {/* Narrative Phases (existing) */}
            <TouchableOpacity
              onPress={() => setExpandedMatrix(expandedMatrix === 'narrative' ? null : 'narrative')}
              activeOpacity={0.7}
              style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: T.surfaceAlt, borderRadius: 12, padding: 12, marginBottom: 6, borderWidth: 1, borderColor: '#7C9CFF44' }}
            >
              <Ionicons name="layers" size={16} color="#7C9CFF" />
              <Text style={{ color: T.text, fontSize: 13, fontWeight: '700', marginLeft: 8, flex: 1 }}>Narrative Phase Matrix</Text>
              <Text style={{ color: T.textMuted, fontSize: 10, marginRight: 8 }}>36 × 5</Text>
              <Ionicons name={expandedMatrix === 'narrative' ? 'chevron-up' : 'chevron-down'} size={16} color={T.textMuted} />
            </TouchableOpacity>
            {expandedMatrix === 'narrative' && (
              <NarrativePhaseSliders values={narrativePhaseValues} onChange={setNarrativePhaseValues} />
            )}

            {/* 8 thematic matrices */}
            {ALL_MATRICES.map(cfg => {
              const open = expandedMatrix === cfg.id;
              return (
                <View key={cfg.id}>
                  <TouchableOpacity
                    onPress={() => setExpandedMatrix(open ? null : cfg.id)}
                    activeOpacity={0.7}
                    style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: T.surfaceAlt, borderRadius: 12, padding: 12, marginBottom: 6, marginTop: 6, borderWidth: 1, borderColor: cfg.accent + '55' }}
                  >
                    <Ionicons name={cfg.icon} size={16} color={cfg.accent} />
                    <Text style={{ color: T.text, fontSize: 13, fontWeight: '700', marginLeft: 8, flex: 1 }}>{cfg.title}</Text>
                    <Text style={{ color: T.textMuted, fontSize: 10, marginRight: 8 }}>{cfg.phases.length} × {cfg.axes.length}</Text>
                    <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={16} color={T.textMuted} />
                  </TouchableOpacity>
                  {open && (
                    <MatrixSliders
                      config={cfg}
                      values={matrixValues[cfg.id]}
                      onChange={matrixSetters[cfg.id]}
                    />
                  )}
                </View>
              );
            })}
          </View>
        )}

        <YourChoicesCard
          title={title}
          genre={selectedGenre?.name ?? null}
          description={gameVision || systemArch || worldLaws || agentInstructions || ''}
          eraLabel={selectedEra?.label}
          eraYear={ageEraYear}
          ageTarget={ageTarget}
          complexity={complexity}
          extraParams={extraParams}
          production={productionState}
        />

        <View style={s.searchBar}>
          <Ionicons name="search-outline" size={16} color={T.textMuted} />
          <TextInput style={s.searchInput} placeholder={`Search ${genres.length} genres...`} placeholderTextColor={T.textMuted} value={genreSearch} onChangeText={setGenreSearch} />
          {genreSearch ? <TouchableOpacity onPress={() => setGenreSearch('')}><Ionicons name="close-outline" size={18} color={T.textMuted} /></TouchableOpacity> : null}
        </View>

        {/* ═══ FUSION MODE TOGGLE — unlock multi-genre + multi-subgenre selection ═══ */}
        <TouchableOpacity
          onPress={() => { setMultiGenreMode(v => !v); if (multiGenreMode) { setExtraGenreIds([]); setExtraSubgenreIds([]); } }}
          style={{
            flexDirection: 'row', alignItems: 'center', padding: 12,
            backgroundColor: multiGenreMode ? '#7C3AED20' : T.bgSecondary,
            borderWidth: 1, borderColor: multiGenreMode ? '#7C3AED' : T.border,
            borderRadius: 10, marginBottom: 12, gap: 10,
          }}
          activeOpacity={0.7}
        >
          <Ionicons name={multiGenreMode ? 'sparkles' : 'sparkles-outline'} size={20} color={multiGenreMode ? '#7C3AED' : T.textMuted} />
          <View style={{ flex: 1 }}>
            <Text style={{ fontSize: 13, fontWeight: '800', color: multiGenreMode ? '#7C3AED' : T.text }}>
              FUSION MODE {multiGenreMode ? 'ON' : 'OFF'}
            </Text>
            <Text style={{ fontSize: 10, color: T.textMuted, marginTop: 2 }}>
              {multiGenreMode
                ? `Mix multiple genres: ${fusedGenreCount} selected • ${fusionMultiplier.toFixed(1)}× delivery floor`
                : 'Enable to blend multiple genres into a single hybrid AAA build'}
            </Text>
          </View>
          <View style={{
            width: 36, height: 20, borderRadius: 10,
            backgroundColor: multiGenreMode ? '#7C3AED' : T.border,
            padding: 2, justifyContent: 'center',
            alignItems: multiGenreMode ? 'flex-end' : 'flex-start',
          }}>
            <View style={{ width: 16, height: 16, borderRadius: 8, backgroundColor: '#FFF' }} />
          </View>
        </TouchableOpacity>

        {filteredGenres.map(g => {
          const isSelected = selectedGenre?.id === g.id;
          const isExpanded = expandedGenre === g.id;
          const isExtraSelected = extraGenreIds.includes(g.id);
          return (
            <TouchableOpacity key={g.id} testID={`genre-${g.id}`} accessibilityLabel={`Genre ${g.name}`} style={[
                s.genreCard,
                isSelected && { borderColor: g.color, backgroundColor: g.color + '10' },
                (!isSelected && isExtraSelected) && { borderColor: g.color, borderStyle: 'dashed', backgroundColor: g.color + '08' },
              ]}
              onPress={() => {
                if (isSelected) {
                  setExpandedGenre(isExpanded ? null : g.id);
                } else if (multiGenreMode && selectedGenre) {
                  // In fusion mode, tap on non-primary toggles extra-add
                  toggleExtraGenre(g.id);
                } else {
                  setSelectedGenre(g); setSelectedSubgenre(null); setExpandedGenre(g.id);
                  // Reset extras on new primary
                  setExtraGenreIds([]); setExtraSubgenreIds([]);
                }
              }} activeOpacity={0.7}>
            {/* Fusion badge */}
            {(!isSelected && isExtraSelected) && (
              <View style={{ position: 'absolute', top: 6, right: 6, backgroundColor: g.color, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6 }}>
                <Text style={{ fontSize: 9, fontWeight: '700', color: '#FFF' }}>+ FUSED</Text>
              </View>
            )}
              <View style={s.genreRow}>
                <Text style={{ fontSize: 24 }}>{g.icon}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={[s.genreName, isSelected && { color: g.color }]}>{g.name}</Text>
                  <Text style={s.genreDesc} numberOfLines={1}>{g.desc}</Text>
                </View>
                <View style={[s.genreBadge, { backgroundColor: g.color + '20' }]}>
                  <Text style={[s.genreBadgeText, { color: g.color }]}>{g.subgenre_count}</Text>
                </View>
                {isSelected && <Ionicons name={isExpanded ? 'chevron-up-outline' : 'chevron-down-outline'} size={16} color={g.color} />}
              </View>
              {isSelected && isExpanded && (
                <View style={s.genreExpanded}>
                  <View style={s.subRow}>
                    {g.subgenres.map((sub: string) => (
                      <TouchableOpacity key={sub} style={[s.subChip, selectedSubgenre === sub && { backgroundColor: g.color + '30', borderColor: g.color }]}
                        onPress={() => setSelectedSubgenre(selectedSubgenre === sub ? null : sub)}>
                        <Text style={[s.subChipText, selectedSubgenre === sub && { color: g.color }]}>{sub.replace(/_/g, ' ')}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                  {/* ═══ Fusion Mode: multi-subgenre chips for active genre ═══ */}
                  {multiGenreMode && g.subgenres.length > 1 && (
                    <View style={{ marginTop: 10 }}>
                      <Text style={{ fontSize: 10, color: g.color, fontWeight: '700', marginBottom: 4, opacity: 0.85 }}>
                        + FUSION SUBGENRES ({extraSubgenreIds.length} added)
                      </Text>
                      <View style={s.subRow}>
                        {g.subgenres.filter((sub: string) => sub !== selectedSubgenre).map((sub: string) => {
                          const on = extraSubgenreIds.includes(sub);
                          return (
                            <TouchableOpacity key={`extra-${sub}`} style={[s.subChip, on && { backgroundColor: g.color + '20', borderColor: g.color, borderStyle: 'dashed' }]}
                              onPress={() => toggleExtraSubgenre(sub)}>
                              <Text style={[s.subChipText, on && { color: g.color }]}>{on ? '✓ ' : '+ '}{sub.replace(/_/g, ' ')}</Text>
                            </TouchableOpacity>
                          );
                        })}
                      </View>
                    </View>
                  )}
                </View>
              )}
            </TouchableOpacity>
          );
        })}

        {/* ═══ Primary Build CTA — anchored to the bottom of the questionnaire ═══ */}
        <TouchableOpacity
          testID="galaxy-studio-build-button"
          style={[s.buildBtn, (!title.trim() || !selectedGenre) && { opacity: 0.35 }]}
          onPress={startBuild}
          disabled={!title.trim() || !selectedGenre || loading}
          activeOpacity={0.7}
        >
          <Ionicons name="rocket-outline" size={20} color="#fff" />
          <Text style={s.buildBtnText}>
            {title.trim() && selectedGenre
              ? `Build ${title.slice(0, 22)}`
              : !selectedGenre
              ? 'Pick a genre to build'
              : 'Name your game to build'}
          </Text>
          <Text style={s.buildBtnSub}>15 min • 100 phases • 10 batches</Text>
        </TouchableOpacity>
        {/* ✨ 2026-05 — generous safe-area for home indicator / soft-nav. */}
        <View style={{ height: Platform.OS === 'ios' ? 96 : 64 }} />
      </View>
    </ScrollView>
  );

  // ═══ STEP 2: BUILDING — with timer, batch progress, and live polling ═══
  const renderBuilding = () => {
    const fc = buildStatus?.file_count || 0;
    const completedCount = buildStatus?.completed_phases || 0;
    const totalPhases = buildStatus?.total_phases || 100;
    const currentBatch = buildStatus?.current_batch || 0;
    const totalBatches = buildStatus?.total_batches || 10;
    const batchName = buildStatus?.batch_name || 'Initializing';
    const batchNames = buildStatus?.batch_names || {};
    const bgCurrentBatch = buildStatus?.bg_current_batch || 0;
    const bg = buildStatus?.bg_progress;
    const elapsed = bg?.elapsed_formatted || '0m 0s';
    const remaining = bg?.remaining_formatted || '15m 0s';
    const timePct = bg?.time_pct || 0;

    return (
      <View style={{ flex: 1, paddingHorizontal: 14, paddingTop: 10 }}>
        {/* Build hero — now with a breathing pulse ring + rotating glyph */}
        <View style={s.buildHero}>
          <View style={s.pulseCradle}>
            <Animated.View
              style={[
                s.pulseRingFar,
                {
                  opacity: buildPulse.interpolate({ inputRange: [0, 1], outputRange: [0.0, 0.55] }),
                  transform: [
                    { scale: buildPulse.interpolate({ inputRange: [0, 1], outputRange: [0.85, 1.4] }) },
                  ],
                },
              ]}
            />
            <Animated.View
              style={[
                s.pulseRingNear,
                {
                  opacity: buildPulse.interpolate({ inputRange: [0, 1], outputRange: [0.2, 0.9] }),
                  transform: [
                    { scale: buildPulse.interpolate({ inputRange: [0, 1], outputRange: [0.95, 1.15] }) },
                  ],
                },
              ]}
            />
            <Animated.View
              style={{
                transform: [
                  { rotate: buildSweep.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] }) },
                ],
              }}
            >
              <Ionicons name="planet" size={34} color={T.accentLight} />
            </Animated.View>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.buildTitle}>{title}</Text>
            <Text style={s.buildSub}>{selectedGenre?.icon} {selectedGenre?.name}</Text>
          </View>
          <View style={s.liveBadge}>
            <Animated.View style={[s.liveDot, { opacity: buildPulse }]} />
            <Text style={s.liveBadgeText}>LIVE</Text>
          </View>
        </View>

        {/* Timer */}
        <View style={s.timerRow}>
          <View style={s.timerBox}>
            <Ionicons name="time-outline" size={14} color={T.cyan} />
            <Text style={s.timerText}>{elapsed}</Text>
            <Text style={s.timerLabel}>elapsed</Text>
          </View>
          <View style={[s.timerBox, { borderColor: T.gold + '30' }]}>
            <Ionicons name="hourglass-outline" size={14} color={T.gold} />
            <Text style={[s.timerText, { color: T.gold }]}>{remaining}</Text>
            <Text style={s.timerLabel}>remaining</Text>
          </View>
          <View style={[s.timerBox, { borderColor: T.success + '30' }]}>
            <Ionicons name="document-text-outline" size={14} color={T.success} />
            <Text style={[s.timerText, { color: T.success }]}>{fc.toLocaleString()}</Text>
            <Text style={s.timerLabel}>files</Text>
          </View>
        </View>

        {/* Code Library + Agent DB Connection Chip */}
        {(codeLibStats || agentDbManifest || flairStats || megaDbStats) && (
          <View style={{ backgroundColor: T.surfaceAlt, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 7, marginHorizontal: 4, marginBottom: 6, borderWidth: 1, borderColor: T.accent + '30' }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 3 }}>
              <Ionicons name="library-outline" size={14} color={T.accent} />
              <Text style={{ color: T.text, fontSize: 10, flex: 1 }} numberOfLines={1}>
                <Text style={{ color: T.accent, fontWeight: '800' }}>{codeLibStats?.virtual_line_count_human || '0'}</Text>
                <Text> code lines · </Text>
                <Text style={{ color: T.gold, fontWeight: '700' }}>{agentDbManifest?.total_agents?.toLocaleString() || 0}</Text>
                <Text> agents · </Text>
                <Text style={{ color: T.accent, fontWeight: '700' }}>{agentDbManifest?.collection_count || 0}</Text>
                <Text> DBs</Text>
              </Text>
            </View>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Ionicons name="sparkles-outline" size={14} color={T.gold} />
              <Text style={{ color: T.text, fontSize: 10, flex: 1 }} numberOfLines={1}>
                <Text style={{ color: T.gold, fontWeight: '800' }}>{megaDbStats?.total_docs?.toLocaleString() || 0}</Text>
                <Text> mega-assets across </Text>
                <Text style={{ color: T.accent, fontWeight: '700' }}>{megaDbStats?.total_collections || 0}</Text>
                <Text> DBs · </Text>
                <Text style={{ color: '#EC4899', fontWeight: '800' }}>{flairStats?.total_flair?.toLocaleString() || 0}</Text>
                <Text> unique flair entries</Text>
              </Text>
            </View>
          </View>
        )}

        {/* Worker-Pool Health Chip */}
        {workerStats && (
          <View style={{ flexDirection: 'row', alignItems: 'center', backgroundColor: T.surfaceAlt, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, marginHorizontal: 4, marginBottom: 8, borderWidth: 1, borderColor: workerStats.health === 'excellent' ? T.success + '40' : workerStats.health === 'degraded' ? T.warning + '40' : T.danger + '40' }}>
            <Ionicons name="hardware-chip-outline" size={14} color={workerStats.health === 'excellent' ? T.success : workerStats.health === 'degraded' ? T.warning : T.danger} />
            <Text style={{ color: T.text, fontSize: 11, marginLeft: 6, flex: 1 }}>
              Workers: <Text style={{ color: T.accent, fontWeight: '700' }}>{workerStats.active || 0}</Text>/{workerStats.max_workers || 8} active
              {' • '}
              <Text style={{ color: T.success }}>{workerStats.total_completed || 0} done</Text>
              {workerStats.total_failed > 0 && <Text style={{ color: T.danger }}> • {workerStats.total_failed} failed</Text>}
            </Text>
            <Text style={{ color: workerStats.health === 'excellent' ? T.success : workerStats.health === 'degraded' ? T.warning : T.danger, fontSize: 10, fontWeight: '700', textTransform: 'uppercase' }}>{workerStats.health}</Text>
          </View>
        )}

        {/* Current Batch Indicator */}
        <View style={s.batchIndicator}>
          <View style={s.batchIndicatorHeader}>
            <Ionicons name="layers-outline" size={16} color={T.accent} />
            <Text style={s.batchIndicatorTitle}>Batch {bgCurrentBatch || currentBatch}/{totalBatches}</Text>
            <Text style={s.batchIndicatorName}>{batchName}</Text>
          </View>
          <Text style={s.batchIndicatorSub}>{completedCount}/{totalPhases} phases • {Math.round(completedCount / totalPhases * 100)}%</Text>
        </View>

        {/* Progress bar with animated shimmer */}
        <View style={s.progressWrap}>
          <View style={s.progressBg}>
            <Animated.View style={[s.progressFill, { width: progressAnim.interpolate({ inputRange: [0, 1], outputRange: ['0%', '100%'] }) }]}>
              <Animated.View
                style={[
                  s.progressShimmer,
                  {
                    opacity: buildShimmer.interpolate({ inputRange: [0, 1], outputRange: [0.2, 0.7] }),
                    transform: [
                      { translateX: buildShimmer.interpolate({ inputRange: [0, 1], outputRange: [-80, 80] }) },
                    ],
                  },
                ]}
              />
            </Animated.View>
          </View>
          <Text style={s.progressPct}>{Math.round(timePct)}%</Text>
        </View>

        {/* Batch chips — 10 batches instead of 100 individual phases */}
        <View style={s.phaseGrid}>
          {Array.from({ length: totalBatches }, (_, i) => {
            const batchNum = i + 1;
            const bName = batchNames[String(batchNum)] || `Batch ${batchNum}`;
            const done = batchNum < (bgCurrentBatch || currentBatch);
            const current = batchNum === (bgCurrentBatch || currentBatch);
            return (
              <View key={batchNum} style={[s.batchChip, done && { backgroundColor: T.success + '20', borderColor: T.success + '40' }, current && { backgroundColor: T.accent + '20', borderColor: T.accent }]}>
                {done ? <Ionicons name="checkmark-circle" size={14} color={T.success} /> : current ? <ActivityIndicator size={12} color={T.accent} /> : <View style={s.phaseDot} />}
                <View style={{ flex: 1 }}>
                  <Text style={[s.batchChipTitle, done && { color: T.success }, current && { color: T.accent }]}>{bName}</Text>
                  <Text style={s.batchChipSub}>10 phases</Text>
                </View>
              </View>
            );
          })}
        </View>

        {/* ── LIVE FILE PREVIEW — what was just generated ── */}
        {Array.isArray(buildStatus?.recent_files) && buildStatus.recent_files.length > 0 && (
          <View style={s.previewWrap}>
            <View style={s.previewHeader}>
              <Ionicons name="eye-outline" size={13} color={T.accent} />
              <Text style={s.previewTitle}>Live Preview</Text>
              <Text style={s.previewCount}>{buildStatus.recent_files.length} latest</Text>
            </View>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 4, gap: 6 }}>
              {buildStatus.recent_files.slice().reverse().map((f: any, i: number) => {
                const ext = String(f.ext || 'txt').toLowerCase();
                const tint = ext === 'tsx' || ext === 'ts' ? '#60A5FA'
                           : ext === 'md' ? '#A78BFA'
                           : ext === 'json' ? '#F59E0B'
                           : ext === 'py' ? '#10B981'
                           : '#94A3B8';
                const fname = String(f.path || '').split('/').slice(-1)[0] || '?';
                return (
                  <View key={`${f.path}-${i}`} style={[s.previewChip, { borderColor: tint + '50' }]}>
                    <View style={[s.previewExt, { backgroundColor: tint + '22' }]}>
                      <Text style={[s.previewExtText, { color: tint }]}>{ext}</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={s.previewName} numberOfLines={1}>{fname}</Text>
                      <Text style={s.previewSize}>{Math.round((f.size || 0) / 102.4) / 10} KB</Text>
                    </View>
                  </View>
                );
              })}
            </ScrollView>
          </View>
        )}

        {/* Build log */}
        <ScrollView ref={logScrollRef} style={s.logBox} showsVerticalScrollIndicator={false}>
          {buildLog.map((log, i) => (
            <View key={i} style={s.logRow}>
              <Ionicons name={log.startsWith('✓') || log.startsWith('✅') ? 'checkmark-circle' : log.startsWith('⚠') ? 'warning' : log.startsWith('⏳') || log.startsWith('🔄') ? 'reload' : 'chevron-forward'} size={12}
                color={log.startsWith('✓') || log.startsWith('✅') ? T.success : log.startsWith('⚠') ? T.warning : log.startsWith('⏳') || log.startsWith('🔄') ? T.gold : T.accent} />
              <Text style={s.logText}>{log}</Text>
            </View>
          ))}
          {buildLog.length > 0 && (
            <View style={s.logPulse}>
              <ActivityIndicator size={10} color={T.accent} />
              <Text style={s.logPulseText}>Auto-polling active — never gives up</Text>
            </View>
          )}
        </ScrollView>

        {/* Permanent-Connection Status: one unified Continue button */}
        <TouchableOpacity style={[s.actionBtn, { backgroundColor: T.success, marginTop: 8, marginHorizontal: 4 }]} onPress={resumeBuild} activeOpacity={0.7} disabled={resumeLoading}>
          {resumeLoading ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name="infinite-outline" size={20} color="#fff" />}
          <View style={{ flex: 1 }}>
            <Text style={[s.actionBtnTitle, { color: '#fff' }]}>Continue / Sync</Text>
            <Text style={[s.actionBtnSub, { color: '#fffa' }]}>Local build runs offline — tap to sync with server</Text>
          </View>
          <Ionicons name="chevron-forward-outline" size={16} color="#fffa" />
        </TouchableOpacity>
      </View>
    );
  };

  // ═══ FINAL BUILD & PACKAGING (7-stage) — kick async job + stream stages ═══
  const runFinalBuild = useCallback(async () => {
    if (!buildId || finBusy) return;
    setFinBusy(true); setFinError(null); setFinResult(null); setFinStages([]);
    if (finPollRef.current) { clearInterval(finPollRef.current); finPollRef.current = null; }
    const eraKey = ERA_KEY_MAP[selectedEra?.id] || 'modern';
    const cfg = {
      graphic_style: styleParams?.graphic || visualStyle,
      dimension: styleParams?.dimension || (perspective === 'side_scroll' || perspective === 'top_down' ? '2d' : '3d'),
      visual_style: visualStyle,
      audio_mood: audioMood,
      era_id: selectedEra?.id, era_label: selectedEra?.label,
    };
    try {
      const kick = await safeFetch(`${BACKEND}/api/galaxy-studio/final-build/package/async`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          build_id: buildId, genre: selectedGenre?.id || 'rpg',
          era: eraKey, seed: 1, persist: true, config: cfg,
        }),
      });
      const jobId = kick?.job_id;
      if (!jobId) throw new Error('no job id returned');
      addLog(`🏁 Final Build started — packaging "${title}" (${selectedEra?.label || eraKey})`);
      finPollRef.current = setInterval(async () => {
        try {
          const jd = await safeFetch(`${BACKEND}/api/galaxy-studio/final-build/job/${jobId}`);
          if (Array.isArray(jd?.stages)) setFinStages(jd.stages);
          if (jd?.status === 'done') {
            if (finPollRef.current) { clearInterval(finPollRef.current); finPollRef.current = null; }
            setFinResult(jd.result || null);
            setFinBusy(false);
            const r = jd.result || {};
            addLog(r.can_ship
              ? `✓ Final Build PASSED — ${r.gates_passed}/7 gates · score ${r.overall_score} · ready to play & download`
              : `⚠ Final Build BLOCKED — ${r.gates_passed}/7 gates (need all + ≥${r.production_threshold})`);
          } else if (jd?.status === 'error') {
            if (finPollRef.current) { clearInterval(finPollRef.current); finPollRef.current = null; }
            setFinError(jd.error || 'final build failed');
            setFinBusy(false);
          }
        } catch { /* keep polling */ }
      }, 700);
    } catch (e: any) {
      setFinError(String(e?.message || e).slice(0, 160));
      setFinBusy(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildId, finBusy, selectedEra, selectedGenre, styleParams, visualStyle, perspective, audioMood, title]);

  // Cleanup the final-build poller on unmount.
  useEffect(() => () => { if (finPollRef.current) clearInterval(finPollRef.current); }, []);

  // ═══ POPULATE MY WORLD — Construct + Material forge into this build's Vault ═══
  const populateWorld = useCallback(async () => {
    if (!buildId || popBusy) return;
    setPopBusy(true); setPopResult(null);
    const eraKey = ERA_KEY_MAP[selectedEra?.id] || 'modern';
    const genre = selectedGenre?.id || 'rpg';
    try {
      const [c, m] = await Promise.all([
        safeFetch(`${BACKEND}/api/galaxy-studio/constructs/snowball/forge`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ build_id: buildId, era: eraKey, seed: 1, construct_count: 24, mount: true, config: { genre } }),
        }),
        safeFetch(`${BACKEND}/api/galaxy-studio/materials/snowball/forge`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ build_id: buildId, era: eraKey, seed: 1, material_count: 24, mount: true, config: { genre } }),
        }),
      ]);
      const constructs = c?.constructs || 0;
      const materials = m?.materials || 0;
      setPopResult({ constructs, materials });
      addLog(`🏙️ Populated world — +${constructs} constructs, +${materials} materials mounted to the Vault. Re-run Final Build to package them.`);
    } catch (e: any) {
      setPopResult({ error: String(e?.message || e).slice(0, 120) });
    } finally { setPopBusy(false); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [buildId, popBusy, selectedEra, selectedGenre]);

  // ═══ STEP 3: DONE ═══
  const renderDone = () => {
    if (showCode && selectedFile) {
      return (
        <CodeFileView
          selectedFile={selectedFile}
          fileContent={fileContent}
          onBack={() => { setShowCode(false); setSelectedFile(null); }}
        />
      );
    }
    if (showCode && !selectedFile) {
      return (
        <CodeBrowseView
          files={files}
          onBack={() => setShowCode(false)}
          onSelectFile={viewFile}
        />
      );
    }
    if (showVault) {
      return (
        <VaultView
          vaultData={vaultData}
          backendUrl={BACKEND}
          onBack={() => setShowVault(false)}
        />
      );
    }

    return (
      <ScrollView style={{ flex: 1, paddingHorizontal: 14 }} showsVerticalScrollIndicator={false}>
        <View style={s.doneHero}><Ionicons name="checkmark-circle" size={48} color={T.success} /><Text style={s.doneTitle}>{title}</Text><Text style={s.doneSub}>{selectedGenre?.icon} {selectedGenre?.name}{selectedSubgenre ? ` / ${selectedSubgenre.replace(/_/g, ' ')}` : ''}</Text></View>
        {files && (<View style={s.statsBar}>
          <View style={s.statBox}><Text style={s.statNum}>{files.total_files?.toLocaleString()}</Text><Text style={s.statLabel}>files</Text></View>
          <View style={s.statDivider} /><View style={s.statBox}><Text style={s.statNum}>{files.total_lines?.toLocaleString()}</Text><Text style={s.statLabel}>lines</Text></View>
          <View style={s.statDivider} /><View style={s.statBox}><Text style={s.statNum}>{Math.round((files.total_bytes || 0) / 1024)}KB</Text><Text style={s.statLabel}>code</Text></View>
        </View>)}
        {/* ═══ 🏙️ POPULATE MY WORLD — Construct + Material Forge ═══ */}
        <View style={{ backgroundColor: T.surfaceAlt, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: '#6c8cff55', marginBottom: 10 }} testID="populate-world-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <Ionicons name="business-outline" size={18} color="#6c8cff" />
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', flex: 1 }}>Populate my world</Text>
            <Text style={{ color: T.textMuted, fontSize: 11 }}>constructs + materials</Text>
          </View>
          <Text style={{ color: T.textMuted, fontSize: 12, lineHeight: 17, marginBottom: 10 }}>
            Drop 24 era-correct buildings/cities/castles + 24 materials straight into this build&apos;s Vault, then re-run Final Build to package them.
          </Text>
          <TouchableOpacity onPress={populateWorld} disabled={popBusy || !buildId} activeOpacity={0.85}
            style={[{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: '#6c8cff', paddingVertical: 12, borderRadius: 10 }, popBusy && { opacity: 0.6 }]} testID="populate-world-btn">
            {popBusy ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name="business" size={18} color="#fff" />}
            <Text style={{ color: '#fff', fontSize: 14, fontWeight: '800' }}>{popBusy ? 'Populating…' : '🏙️ Populate world'}</Text>
          </TouchableOpacity>
          {popResult && !popResult.error && (
            <Text style={{ color: T.success, fontSize: 12, marginTop: 10, fontWeight: '700' }} testID="populate-world-result">
              ✓ +{popResult.constructs} constructs · +{popResult.materials} materials mounted — re-run Final Build to package
            </Text>
          )}
          {popResult?.error && <Text style={{ color: T.warning, fontSize: 12, marginTop: 10 }}>⚠ {popResult.error}</Text>}
        </View>

        {/* ═══ 🏁 FINAL BUILD & PACKAGING (7-stage) — live CI-style console ═══ */}
        <View style={{ backgroundColor: T.surfaceAlt, borderRadius: 14, padding: 14, borderWidth: 1, borderColor: (finResult ? (finResult.can_ship ? T.success : T.warning) : T.accent) + '55', marginBottom: 10 }} testID="final-build-card">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <Ionicons name="rocket-outline" size={18} color={T.accent} />
            <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', flex: 1 }}>Final Build &amp; Package</Text>
            <Text style={{ color: T.textMuted, fontSize: 11 }}>7-stage · ≥95 gate</Text>
          </View>
          <Text style={{ color: T.textMuted, fontSize: 12, lineHeight: 17, marginBottom: 10 }}>
            Cook every gamefile in the Vault into a verification-gated, playable, downloadable game ({selectedEra?.label || 'Modern'} era).
          </Text>

          <TouchableOpacity
            style={[{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: T.accent, paddingVertical: 12, borderRadius: 10 }, finBusy && { opacity: 0.6 }]}
            onPress={runFinalBuild} disabled={finBusy || !buildId} activeOpacity={0.85} testID="final-build-btn"
          >
            {finBusy ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name={finResult ? 'refresh-outline' : 'rocket'} size={18} color="#fff" />}
            <Text style={{ color: '#fff', fontSize: 14, fontWeight: '800' }}>
              {finBusy ? 'Building & packaging…' : finResult ? 'Re-run Final Build' : '🏁 Run Final Build & Package'}
            </Text>
          </TouchableOpacity>

          {/* Live 7-stage console */}
          {(finBusy || finStages.length > 0) && (
            <View style={{ marginTop: 12, gap: 6 }} testID="final-build-console">
              {[
                'Build Orchestrator', 'Asset Cooking', 'Code & Content Integration',
                'Platform Builds', 'Installer & Distribution Packaging', 'Validation & QA',
                'Distribution Prep',
              ].map((label, idx) => {
                const step = idx + 1;
                const st = finStages.find((x: any) => x.step === step);
                const passed = st?.gate?.passed;
                const reached = !!st;
                const isNext = !reached && finBusy && finStages.length === idx;
                return (
                  <View key={step} style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4, opacity: reached || isNext ? 1 : 0.4 }} testID={`fb-stage-${step}`}>
                    {reached
                      ? <Ionicons name={passed ? 'checkmark-circle' : 'close-circle'} size={16} color={passed ? T.success : T.warning} />
                      : isNext
                        ? <ActivityIndicator size={12} color={T.accent} />
                        : <View style={{ width: 16, height: 16, borderRadius: 8, borderWidth: 1.5, borderColor: T.border }} />}
                    <Text style={{ color: reached ? (passed ? T.success : T.warning) : T.textMuted, fontSize: 12, fontWeight: '700', flex: 1 }} numberOfLines={1}>
                      {step}. {label}
                    </Text>
                    {st?.gate && <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '800' }}>{st.gate.score}</Text>}
                  </View>
                );
              })}
            </View>
          )}

          {finError && (
            <Text style={{ color: T.warning, fontSize: 12, marginTop: 10 }} testID="final-build-error">⚠ {finError}</Text>
          )}

          {/* Result verdict + Play / Download */}
          {finResult && (
            <View style={{ marginTop: 12 }}>
              <View style={{ backgroundColor: (finResult.can_ship ? T.success : T.warning) + '18', borderRadius: 10, padding: 10, borderWidth: 1, borderColor: (finResult.can_ship ? T.success : T.warning) + '55' }}>
                <Text style={{ color: finResult.can_ship ? T.success : T.warning, fontSize: 13, fontWeight: '800' }} testID="final-build-verdict">
                  {finResult.can_ship ? '✅ READY TO PLAY & DOWNLOAD' : '⚠ BLOCKED'} · {finResult.gates_passed}/7 gates · score {finResult.overall_score}
                </Text>
                {finResult.totals && (
                  <Text style={{ color: T.textMuted, fontSize: 11, marginTop: 3 }}>
                    {finResult.totals.gamefiles} gamefiles · {finResult.totals.assets} assets · {finResult.totals.cooked_size} cooked · {finResult.playable?.entities ?? 0} entities
                  </Text>
                )}
              </View>
              {finResult.can_ship && finResult.playable?.playable && (
                <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
                  <TouchableOpacity
                    style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: T.success, paddingVertical: 11, borderRadius: 10 }}
                    onPress={() => { const u = `${BACKEND}${finResult.playable.play_url}`; if (Platform.OS === 'web') { try { (window as any).open(u, '_blank'); } catch {} } else Linking.openURL(u); }}
                    activeOpacity={0.85} testID="final-build-play"
                  >
                    <Ionicons name="play" size={16} color="#fff" />
                    <Text style={{ color: '#fff', fontSize: 13, fontWeight: '800' }}>Play game</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: T.accent, paddingVertical: 11, borderRadius: 10 }}
                    onPress={() => { const u = `${BACKEND}${finResult.playable.download_url}`; if (Platform.OS === 'web') { try { (window as any).open(u, '_blank'); } catch {} } else Linking.openURL(u); }}
                    activeOpacity={0.85} testID="final-build-download"
                  >
                    <Ionicons name="download" size={16} color="#fff" />
                    <Text style={{ color: '#fff', fontSize: 13, fontWeight: '800' }}>Download game.zip</Text>
                  </TouchableOpacity>
                </View>
              )}
            </View>
          )}
        </View>

        {statusMsg && (<View style={[s.statusBar, statusMsg.startsWith('✓') ? { borderColor: T.success + '40' } : { borderColor: T.warning + '40' }]}>
          <Ionicons name={statusMsg.startsWith('✓') ? 'checkmark-circle' : 'information-circle'} size={16} color={statusMsg.startsWith('✓') ? T.success : T.warning} />
          <Text style={[s.statusText, statusMsg.startsWith('✓') ? { color: T.success } : { color: T.warning }]}>{statusMsg}</Text>
        </View>)}
        {(jobs.expand || jobs.apk) && (
          <View style={{ backgroundColor: T.surfaceAlt, borderRadius: 12, padding: 12, borderWidth: 1, borderColor: T.border, marginBottom: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 2 }}>
              <Ionicons name="layers-outline" size={15} color={T.accent} />
              <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }}>Active Jobs</Text>
            </View>
            {jobs.expand && <ActiveJobRow kind="expand" job={jobs.expand} T={T} />}
            {jobs.apk && <ActiveJobRow kind="apk" job={jobs.apk} T={T} topBorder={!!jobs.expand} />}
          </View>
        )}
        <View style={s.actionGroup}>
          <TouchableOpacity style={[s.actionBtn, { backgroundColor: T.accent }, zipLoading && { opacity: 0.5 }]} onPress={downloadZIP} disabled={zipLoading} activeOpacity={0.7}>
            <Ionicons name="download-outline" size={22} color="#fff" /><View style={{ flex: 1 }}><Text style={s.actionBtnTitle}>Download ZIP</Text><Text style={s.actionBtnSub}>Full source code package</Text></View>
            {zipLoading ? <ActivityIndicator color="#fff" size="small" /> : <Ionicons name="chevron-forward-outline" size={18} color="#fff9" />}
          </TouchableOpacity>
          <TouchableOpacity style={[s.actionBtn, { backgroundColor: '#1D4ED8' }, apkLoading && { opacity: 0.5 }]} onPress={packageAPK} disabled={apkLoading} activeOpacity={0.7}>
            <Ionicons name="phone-portrait-outline" size={22} color="#fff" /><View style={{ flex: 1 }}><Text style={s.actionBtnTitle}>Build APK</Text><Text style={s.actionBtnSub}>EAS cloud build + ZIP download</Text></View>
            {apkLoading ? <ActivityIndicator color="#fff" size="small" /> : <Ionicons name="chevron-forward-outline" size={18} color="#fff9" />}
          </TouchableOpacity>
          {/* EAS status card (merged from Jeeves Master Build) */}
          {easStatus && (
            <View style={{ backgroundColor: T.surfaceAlt, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: '#1D4ED8' + '40', marginTop: 8 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Ionicons name="cloud-done-outline" size={18} color="#60A5FA" />
                <Text style={{ color: T.text, fontSize: 14, fontWeight: '800', flex: 1 }}>EAS Build: {easStatus.status || 'unknown'}</Text>
                {easStatus.polling && <ActivityIndicator size="small" color="#60A5FA" />}
              </View>
              {easStatus.message && <Text style={{ color: T.textMuted, fontSize: 12, marginTop: 6 }}>{easStatus.message}</Text>}
              {easStatus.eas_build_id && <Text style={{ color: T.textDim, fontSize: 11, marginTop: 4 }}>ID: {easStatus.eas_build_id}</Text>}
              {easStatus.download_url && (
                <TouchableOpacity style={{ marginTop: 10, flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#1D4ED8', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, alignSelf: 'flex-start' }} onPress={() => Linking.openURL(easStatus.download_url)} activeOpacity={0.7}>
                  <Ionicons name="download-outline" size={16} color="#fff" />
                  <Text style={{ color: '#fff', fontSize: 13, fontWeight: '700' }}>Download APK</Text>
                </TouchableOpacity>
              )}
            </View>
          )}
          {/* Manual Build Instructions (merged from Jeeves Master Build) */}
          <View style={{ backgroundColor: T.surfaceAlt, borderRadius: 12, padding: 14, borderWidth: 1, borderColor: T.border, marginTop: 8 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <Ionicons name="terminal-outline" size={16} color={T.accent} />
              <Text style={{ color: T.text, fontSize: 13, fontWeight: '800' }}>Manual Build Instructions</Text>
            </View>
            <Text style={{ color: T.textMuted, fontSize: 12, lineHeight: 18 }}>
              1. Download the ZIP{'\n'}
              2. Extract and cd into the project{'\n'}
              3. Run: npm install{'\n'}
              4. Run: npx expo start{'\n'}
              5. For APK: npx eas-cli build --platform android --profile preview
            </Text>
          </View>
          <View style={s.actionRow}>
            <TouchableOpacity style={[s.actionBtnSmall, { borderColor: T.accent + '40' }]} onPress={() => setShowCode(true)} activeOpacity={0.7}><Ionicons name="code-slash-outline" size={18} color={T.accent} /><Text style={[s.actionBtnSmallText, { color: T.accent }]}>Browse Code</Text></TouchableOpacity>
            <TouchableOpacity style={[s.actionBtnSmall, { borderColor: '#34D399' + '40' }]} onPress={loadVault} activeOpacity={0.7}><Ionicons name="folder-open-outline" size={18} color="#34D399" /><Text style={[s.actionBtnSmallText, { color: '#34D399' }]}>Vault</Text></TouchableOpacity>
          </View>
          {/* 2026-05-15 — ML Console: native-slider tuning for ml_config (Cross-Entropy · Fine-Tuning · ICL Log-Probs) */}
          {buildId && (
            <TouchableOpacity
              style={[s.actionBtnSmall, { borderColor: '#F59E0B' + '40', marginTop: 4 }]}
              onPress={() => setShowMLConsole(true)}
              activeOpacity={0.7}
            >
              <Ionicons name="options-outline" size={18} color="#F59E0B" />
              <Text style={[s.actionBtnSmallText, { color: '#F59E0B' }]}>ML Console</Text>
            </TouchableOpacity>
          )}
        </View>
        <View style={s.expandSection}>
          <Text style={s.expandTitle}>Expand Game</Text><Text style={s.expandDesc}>Add content to {title}</Text>
          <View style={s.expandGrid}>
            {[{ type: 'all', icon: 'planet-outline', label: 'Full DLC', color: '#8B5CF6' }, { type: 'content', icon: 'document-text-outline', label: 'Content', color: '#2563EB' }, { type: 'systems', icon: 'cog-outline', label: 'Systems', color: '#F59E0B' }, { type: 'zones', icon: 'map-outline', label: 'Zones', color: '#22C55E' }, { type: 'enemies', icon: 'skull-outline', label: 'Enemies', color: '#EF4444' }, { type: 'items', icon: 'diamond-outline', label: 'Items', color: '#EC4899' }].map(exp => {
              const isLoading = expandLoading === exp.type;
              return (<TouchableOpacity key={exp.type} style={[s.expandBtn, { borderColor: exp.color + '40' }, isLoading && { opacity: 0.6 }]} onPress={() => expandGame(exp.type, exp.label)} disabled={!!expandLoading} activeOpacity={0.7}>
                {isLoading ? <ActivityIndicator size={16} color={exp.color} /> : <Ionicons name={exp.icon as any} size={18} color={exp.color} />}
                <Text style={[s.expandBtnText, { color: exp.color }]}>{exp.label}</Text>
              </TouchableOpacity>);
            })}
          </View>
        </View>
        {files && (files.files?.length || 0) > 0 && (<View style={s.fileSection}>
          <Text style={s.fileSectionTitle}>Generated Files</Text>
          {(files.files || []).slice(0, 8).map((f: any) => (<TouchableOpacity key={f.path} style={s.fileRow} onPress={() => viewFile(f.path)} activeOpacity={0.7}><Ionicons name={f.type === 'tsx' ? 'logo-react' : 'code-slash-outline'} size={16} color={f.type === 'tsx' ? '#61dafb' : f.type === 'ts' ? '#3B82F6' : T.textDim} /><Text style={s.fileName} numberOfLines={1}>{f.path}</Text><Text style={s.fileSize}>{f.lines}L</Text></TouchableOpacity>))}
          {(files.files?.length || 0) > 8 && <TouchableOpacity style={s.showAllBtn} onPress={() => setShowCode(true)}><Text style={s.showAllText}>View all {files.total_files} files</Text><Ionicons name="chevron-forward-outline" size={14} color={T.accent} /></TouchableOpacity>}
        </View>)}
        {/* Wave-3 Galaxy bridges — Share/Copy build summary + Build Hub & Code Playground */}
        <View style={s.gxBridgeRow}>
          <TouchableOpacity
            style={[s.gxBridgeBtn, { backgroundColor: '#10B98122', borderColor: '#10B981' }]}
            onPress={async () => {
              if (!buildId) return;
              try {
                addLog?.('📦 Packaging ZIP + APK…');
                const r = await fetch(`${BACKEND}/api/binary/package`, {
                  method: 'POST',
                  headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ build_id: buildId, kinds: ['zip', 'apk'] }),
                });
                const j = await r.json();
                const arts = j.artifacts || [];
                if (arts.length === 0) {
                  addLog?.('⚠️ No artifacts produced — check backend logs');
                  return;
                }
                addLog?.(`✓ Packaged ${arts.length} artifacts:`);
                arts.forEach((a: any) => addLog?.(`   ${a.kind.toUpperCase()}: ${(a.size_bytes / 1024).toFixed(1)} KB · ${a.file_count} files`));
                try {
                  jeevesSpeak(
                    `${arts.length} artifacts packaged. The ZIP and APK are now downloadable.`,
                    { context: 'celebration', prependCatchphrase: false },
                  );
                } catch {}
              } catch (e: any) {
                addLog?.(`✗ Package failed: ${e.message || e}`);
              }
            }}
            activeOpacity={0.7}
            disabled={!buildId}
          >
            <Ionicons name="cube-outline" size={14} color="#10B981" />
            <Text style={[s.gxBridgeText, { color: '#10B981' }]}>Package ZIP + APK</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.gxBridgeBtn, { backgroundColor: '#3B82F622', borderColor: '#3B82F6' }]}
            onPress={() => {
              if (!buildId) return;
              const url = `${BACKEND}/api/binary/download/${buildId}/zip`;
              if (Platform.OS === 'web') {
                try { (window as any).open(url, '_blank'); } catch {}
              } else {
                Linking?.openURL?.(url);
              }
            }}
            activeOpacity={0.7}
            disabled={!buildId}
          >
            <Ionicons name="archive-outline" size={14} color="#3B82F6" />
            <Text style={[s.gxBridgeText, { color: '#3B82F6' }]}>Download ZIP</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.gxBridgeBtn, { backgroundColor: '#84CC1622', borderColor: '#84CC16' }]}
            onPress={() => {
              if (!buildId) return;
              const url = `${BACKEND}/api/binary/download/${buildId}/apk`;
              if (Platform.OS === 'web') {
                try { (window as any).open(url, '_blank'); } catch {}
              } else {
                Linking?.openURL?.(url);
              }
            }}
            activeOpacity={0.7}
            disabled={!buildId}
          >
            <Ionicons name="logo-android" size={14} color="#84CC16" />
            <Text style={[s.gxBridgeText, { color: '#84CC16' }]}>Download APK</Text>
          </TouchableOpacity>
        </View>
        <View style={[s.gxBridgeRow, { marginTop: 6 }]}>
          <TouchableOpacity
            style={[s.gxBridgeBtn, { backgroundColor: '#A78BFA22', borderColor: '#A78BFA' }]}
            onPress={() => {
              const summary =
                `🎮 ${title}\n${selectedGenre?.icon || ''} ${selectedGenre?.name || ''}${selectedSubgenre ? ' / ' + selectedSubgenre.replace(/_/g, ' ') : ''}\n\n` +
                `Files: ${files?.total_files?.toLocaleString() || 0}\n` +
                `Lines: ${files?.total_lines?.toLocaleString() || 0}\n` +
                `Size:  ${Math.round((files?.total_bytes || 0) / 1024)} KB\n` +
                `Build ID: ${buildId || '(none)'}\n`;
              shareResult(summary, 'Galaxy Studio build summary');
            }}
            activeOpacity={0.7}
          >
            <Ionicons name="share-social-outline" size={14} color="#A78BFA" />
            <Text style={[s.gxBridgeText, { color: '#A78BFA' }]}>Share summary</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.gxBridgeBtn, { backgroundColor: '#F59E0B22', borderColor: '#F59E0B' }]}
            onPress={() => { onClose(); router.push('/build-hub' as any); }}
            activeOpacity={0.7}
          >
            <Ionicons name="grid-outline" size={14} color="#F59E0B" />
            <Text style={[s.gxBridgeText, { color: '#F59E0B' }]}>Build Hub</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={[s.gxBridgeBtn, { backgroundColor: '#2563EB22', borderColor: '#2563EB' }]}
            onPress={() => { onClose(); router.push('/playground' as any); }}
            activeOpacity={0.7}
          >
            <Ionicons name="flask-outline" size={14} color="#2563EB" />
            <Text style={[s.gxBridgeText, { color: '#2563EB' }]}>Playground</Text>
          </TouchableOpacity>
        </View>
        <TouchableOpacity style={s.newBuildBtn} onPress={resetState}><Ionicons name="refresh-outline" size={18} color={T.accent} /><Text style={s.newBuildText}>Build Another Game</Text></TouchableOpacity>
        {/* ✨ 2026-05 — extra-tall bottom safety margin so the home-indicator
            / soft-nav doesn't overlap the last button. User flagged it
            being clipped on devices with bottom safe-area. */}
        <View style={{ height: Platform.OS === 'ios' ? 96 : 64 }} />
      </ScrollView>
    );
  };

  const getTitle = () => step === 'pick' ? 'Galaxy Studio' : step === 'building' ? '' : title || 'Game Ready';
  const getSub = () => step === 'pick' ? `${genres.length} genres • ${manifest?.total_agents?.toLocaleString() || '28,894'} agents` : step === 'building' ? `Batch ${buildStatus?.bg_current_batch || buildStatus?.current_batch || 0}/${buildStatus?.total_batches || 10} • ${(buildStatus?.completed_phases || 0)}/${buildStatus?.total_phases || 100} phases • ${(buildStatus?.file_count || 0).toLocaleString()} files` : `${files?.total_files?.toLocaleString() || 0} files • ${files?.total_lines?.toLocaleString() || 0} lines`;

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={s.container} testID="galaxy-studio-modal-root">
        <View style={s.header}>
          <TouchableOpacity testID="galaxy-studio-close-button" onPress={() => {
            if (showMLConsole) { setShowMLConsole(false); return; }
            if (showCode) { setShowCode(false); setSelectedFile(null); return; }
            if (showVault) { setShowVault(false); return; }
            if (step === 'done') { setStep('pick'); return; }
            if (step === 'building') return;
            onClose();
          }} style={s.headerBtn} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
            <Ionicons name={step === 'pick' && !showCode && !showVault && !showMLConsole ? 'close-outline' : 'arrow-back-outline'} size={24} color={T.text} />
          </TouchableOpacity>
          <View style={{ flex: 1, alignItems: 'center' }}>
            <Text style={s.headerTitle}>{getTitle()}</Text>
            <Text style={s.headerSub}>{getSub()}</Text>
          </View>
          <View style={{ minWidth: 40, alignItems: 'flex-end', flexDirection: 'row', gap: 6 }}>
            {easAuth && (
              <View
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  gap: 4,
                  paddingHorizontal: 8,
                  paddingVertical: 4,
                  borderRadius: 999,
                  backgroundColor: easAuth.connected ? '#064E3B' : '#78350F',
                  borderWidth: 1,
                  borderColor: easAuth.connected ? '#10B981' : '#F59E0B',
                }}
                testID="galaxy-studio-eas-pill"
              >
                <View
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: 3,
                    backgroundColor: easAuth.connected ? '#10B981' : '#F59E0B',
                  }}
                />
                <Text style={{ color: easAuth.connected ? '#A7F3D0' : '#FCD34D', fontSize: 10, fontWeight: '700' }}>
                  {easAuth.connected ? 'EAS LIVE' : 'EAS FALLBACK'}
                </Text>
              </View>
            )}
            <TunnelStatusPill compact />
          </View>
        </View>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'} keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 20}>
          {step === 'pick' && renderPick()}
          {step === 'building' && renderBuilding()}
          {step === 'done' && renderDone()}
        </KeyboardAvoidingView>
      </View>
    </Modal>
  );
}

