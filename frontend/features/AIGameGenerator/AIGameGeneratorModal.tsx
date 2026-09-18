/**
 * AI Game Generator Modal v15.5
 * Unified Interface for All AI-Powered Game Development Pipelines
 *
 * Features:
 * - NPC & Character Generation
 * - World & Level Design
 * - Combat & Game Systems
 * - Narrative & Quests
 * - VFX & Animation
 * - Economy & Monetization
 */

import React, { useState } from 'react';
import { API_BASE } from '../../utils/apiBase';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput,
  Modal, ActivityIndicator, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';

import { apiFetch } from '../../utils/apiController';
import { safeErrorMessage } from '../../utils/safeError';
import { toast } from '../../components/Toast';
const API_URL = API_BASE;

interface AIGameGeneratorModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  onGenerated?: (data: any, type: string) => void;
}

type CategoryType = 'npc' | 'world' | 'combat' | 'narrative' | 'animation' | 'vfx' | 'bot' | 'economy' | 'systems' | 'testing';

interface GenerationResult {
  success: boolean;
  data: any;
  ai_generated: boolean;
  model?: string;
}

const CATEGORIES: Array<{ key: CategoryType; label: string; icon: string; desc: string }> = [
  { key: 'npc', label: '👤 NPCs', icon: 'person', desc: 'Characters & AI Behavior' },
  { key: 'world', label: '🌍 Worlds', icon: 'globe', desc: 'Regions & Levels' },
  { key: 'combat', label: '⚔️ Combat', icon: 'flash', desc: 'Systems & Mechanics' },
  { key: 'narrative', label: '📖 Story', icon: 'book', desc: 'Quests & Dialogue' },
  { key: 'animation', label: '🎬 Animation', icon: 'film', desc: 'Motion & Keyframes' },
  { key: 'vfx', label: '✨ VFX', icon: 'sparkles', desc: 'Effects & Particles' },
  { key: 'bot', label: '🤖 Bots', icon: 'hardware-chip', desc: 'AI Personas' },
  { key: 'economy', label: '💰 Economy', icon: 'cash', desc: 'Monetization' },
  { key: 'systems', label: '⚙️ Systems', icon: 'cog', desc: 'Server Architecture' },
  { key: 'testing', label: '🧪 Testing', icon: 'flask', desc: 'QA & Test Cases' },
];

const readApiJson = async (response: Response) => {
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    const detail = data?.detail ?? data?.error ?? data?.message;
    const message = typeof detail === 'string' && detail.trim()
      ? detail
      : `Request failed (${response.status || 'unknown status'})`;
    throw new Error(message);
  }

  if (data == null) {
    throw new Error('API returned an empty or invalid JSON response');
  }

  return data;
};

const parseCommaSeparated = (value: string) =>
  value.split(',').map(item => item.trim()).filter(Boolean);

const parsePositiveWholeNumber = (value: string): number | null => {
  const normalized = value.trim();
  if (!/^\d+$/.test(normalized)) return null;
  const parsed = Number(normalized);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
};

export const AIGameGeneratorModal: React.FC<AIGameGeneratorModalProps> = ({
  visible, onClose, colors, onGenerated
}) => {
  const [activeCategory, setActiveCategory] = useState<CategoryType>('npc');
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<GenerationResult | null>(null);
  const [resultCategory, setResultCategory] = useState<CategoryType | null>(null);

  // NPC State
  const [npcDescription, setNpcDescription] = useState('');
  const [npcArchetype, setNpcArchetype] = useState('warrior');
  const [includeDialogue, setIncludeDialogue] = useState(true);
  const [includeQuests, setIncludeQuests] = useState(false);

  // World State
  const [worldBiome, setWorldBiome] = useState('forest');
  const [worldSize, setWorldSize] = useState('medium');
  const [worldFeatures, setWorldFeatures] = useState('village, dungeon, landmark');

  // Combat State
  const [combatStyle, setCombatStyle] = useState('turn_based');
  const [combatMechanics, setCombatMechanics] = useState('attack, defend, magic');
  const [combatComplexity, setCombatComplexity] = useState('moderate');

  // Narrative State
  const [questType, setQuestType] = useState('adventure');
  const [questDifficulty, setQuestDifficulty] = useState('medium');
  const [questSetting, setQuestSetting] = useState('fantasy village');

  // VFX State
  const [effectType, setEffectType] = useState('fire');
  const [visualStyle, setVisualStyle] = useState('realistic');

  // Economy State
  const [gameType, setGameType] = useState('RPG');
  const [monetizationModel, setMonetizationModel] = useState('free_to_play');

  // Systems State
  const [playerCapacity, setPlayerCapacity] = useState('1000');

  // Animation State
  const [characterType, setCharacterType] = useState('humanoid');
  const [animationName, setAnimationName] = useState('walk');
  const [animationStyle, setAnimationStyle] = useState('realistic');

  // Bot Persona State
  const [personaType, setPersonaType] = useState('companion');
  const [personalityTraits, setPersonalityTraits] = useState('friendly, helpful');
  const [knowledgeDomains, setKnowledgeDomains] = useState('general, combat');

  // Testing State
  const [testFeature, setTestFeature] = useState('');
  const [testType, setTestType] = useState('functional');

  const archetypes = ['warrior', 'mage', 'rogue', 'merchant', 'healer', 'noble', 'peasant', 'scholar'];
  const biomes = ['forest', 'desert', 'mountain', 'swamp', 'tundra', 'volcanic', 'underwater', 'haunted'];
  const sizes = ['small', 'medium', 'large', 'massive'];
  const combatStyles = ['turn_based', 'real_time', 'tactical', 'hybrid', 'action'];
  const complexities = ['simple', 'moderate', 'complex'];
  const questTypes = ['fetch', 'combat', 'investigation', 'escort', 'stealth', 'adventure', 'dungeon_crawl'];
  const difficulties = ['easy', 'medium', 'hard', 'legendary'];
  const effectTypes = ['fire', 'water', 'lightning', 'magic', 'explosion', 'healing', 'darkness', 'nature'];
  const visualStyles = ['realistic', 'stylized', 'cartoon', 'pixel', 'anime'];
  const gameTypes = ['RPG', 'Action', 'Strategy', 'Puzzle', 'Simulation', 'Mobile', 'MMO'];
  const monetizationModels = ['free_to_play', 'premium', 'subscription', 'cosmetic_only'];
  const characterTypes = ['humanoid', 'quadruped', 'bird', 'fish', 'insect', 'robot', 'slime', 'dragon'];
  const animationNames = ['walk', 'run', 'idle', 'jump', 'attack', 'death', 'cast', 'interact'];
  const personaTypes = ['companion', 'mentor', 'antagonist', 'shopkeeper', 'guide', 'narrator'];
  const testTypes = ['functional', 'unit', 'integration', 'performance', 'regression'];

  const recordFailure = (prefix: string, error: unknown) => {
    void safeErrorMessage(error);
    setResult({
      success: false,
      data: { error: prefix },
      ai_generated: false,
    });
    toast.error(prefix);
  };

  // =========================================================================
  // API CALLS
  // =========================================================================

  const generateNPC = async () => {
    const description = npcDescription.trim();
    if (!description) {
      toast.error('Please describe the NPC you want to create');
      return;
    }

    setIsLoading(true);
    setResult(null);
    setResultCategory('npc');

    try {
      const response = await apiFetch(`${API_URL}/api/npc-pipeline/ai/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description,
          archetype: npcArchetype,
          include_dialogue: includeDialogue,
          include_quests: includeQuests,
        }),
      });

      const data = await readApiJson(response);
      setResult({
        success: data.success !== false,
        data: data.npc ?? data,
        ai_generated: Boolean(data.ai_generated),
        model: typeof data.model === 'string' ? data.model : undefined,
      });
    } catch (error: unknown) {
      recordFailure('Failed to generate NPC', error);
    } finally {
      setIsLoading(false);
    }
  };

  const generateWorld = async () => {
    const features = parseCommaSeparated(worldFeatures);
    if (!features.length) {
      toast.error('Add at least one world feature');
      return;
    }

    setIsLoading(true);
    setResult(null);
    setResultCategory('world');

    try {
      const response = await apiFetch(`${API_URL}/api/world-management/ai/region/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          biome: worldBiome,
          size: worldSize,
          features,
        }),
      });

      const data = await readApiJson(response);
      setResult({
        success: data.success !== false,
        data: data.world_region ?? data,
        ai_generated: Boolean(data.ai_generated),
        model: typeof data.model === 'string' ? data.model : undefined,
      });
    } catch (error: unknown) {
      recordFailure('Failed to generate world', error);
    } finally {
      setIsLoading(false);
    }
  };

  const generateCombat = async () => {
    const mechanics = parseCommaSeparated(combatMechanics);
    if (!mechanics.length) {
      toast.error('Add at least one combat mechanic');
      return;
    }

    setIsLoading(true);
    setResult(null);
    setResultCategory('combat');

    try {
      const response = await apiFetch(`${API_URL}/api/game-logic-pipeline/ai/combat/design`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          combat_style: combatStyle,
          mechanics,
          complexity: combatComplexity,
        }),
      });

      const data = await readApiJson(response);
      setResult({
        success: data.success !== false,
        data: data.combat_system ?? data,
        ai_generated: Boolean(data.ai_generated),
        model: typeof data.model === 'string' ? data.model : undefined,
      });
    } catch (error: unknown) {
      recordFailure('Failed to generate combat system', error);
    } finally {
      setIsLoading(false);
    }
  };

  const generateQuest = async () => {
    const setting = questSetting.trim();
    if (!setting) {
      toast.error('Please describe the quest setting');
      return;
    }

    setIsLoading(true);
    setResult(null);
    setResultCategory('narrative');

    try {
      const response = await apiFetch(`${API_URL}/api/interactive-narrative/ai/quest/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          quest_type: questType,
          difficulty: questDifficulty,
          setting,
        }),
      });

      const data = await readApiJson(response);
      setResult({
        success: data.success !== false,
        data: data.quest ?? data,
        ai_generated: Boolean(data.ai_generated),
        model: typeof data.model === 'string' ? data.model : undefined,
      });
    } catch (error: unknown) {
      recordFailure('Failed to generate quest', error);
    } finally {
      setIsLoading(false);
    }
  };

  const generateVFX = async () => {
    setIsLoading(true);
    setResult(null);
    setResultCategory('vfx');

    try {
      const response = await apiFetch(`${API_URL}/api/animation-pipeline/ai/vfx/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          effect_type: effectType,
          visual_style: visualStyle,
        }),
      });

      const data = await readApiJson(response);
      setResult({
        success: data.success !== false,
        data: data.vfx_system ?? data,
        ai_generated: Boolean(data.ai_generated),
        model: typeof data.model === 'string' ? data.model : undefined,
      });
    } catch (error: unknown) {
      recordFailure('Failed to generate VFX', error);
    } finally {
      setIsLoading(false);
    }
  };

  const generateEconomy = async () => {
    setIsLoading(true);
    setResult(null);
    setResultCategory('economy');

    try {
      const response = await apiFetch(`${API_URL}/api/economy/ai/economy/design`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          game_type: gameType,
          monetization_model: monetizationModel,
        }),
      });

      const data = await readApiJson(response);
      setResult({
        success: data.success !== false,
        data: data.economy_design ?? data,
        ai_generated: Boolean(data.ai_generated),
        model: typeof data.model === 'string' ? data.model : undefined,
      });
    } catch (error: unknown) {
      recordFailure('Failed to generate economy', error);
    } finally {
      setIsLoading(false);
    }
  };

  const generateSystems = async () => {
    const capacity = parsePositiveWholeNumber(playerCapacity);
    if (capacity == null) {
      toast.error('Player capacity must contain digits only and be greater than zero');
      return;
    }

    setIsLoading(true);
    setResult(null);
    setResultCategory('systems');

    try {
      const response = await apiFetch(`${API_URL}/api/server-backend/ai/architecture/design`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          game_type: gameType,
          player_capacity: capacity,
        }),
      });

      const data = await readApiJson(response);
      setResult({
        success: data.success !== false,
        data: data.server_architecture ?? data,
        ai_generated: Boolean(data.ai_generated),
        model: typeof data.model === 'string' ? data.model : undefined,
      });
    } catch (error: unknown) {
      recordFailure('Failed to generate system architecture', error);
    } finally {
      setIsLoading(false);
    }
  };

  const generateAnimation = async () => {
    setIsLoading(true);
    setResult(null);
    setResultCategory('animation');

    try {
      const response = await apiFetch(`${API_URL}/api/animation-pipeline/ai/animation/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          character_type: characterType,
          animation_name: animationName,
          style: animationStyle,
        }),
      });

      const data = await readApiJson(response);
      setResult({
        success: data.success !== false,
        data: data.animation ?? data,
        ai_generated: Boolean(data.ai_generated),
        model: typeof data.model === 'string' ? data.model : undefined,
      });
    } catch (error: unknown) {
      recordFailure('Failed to generate animation', error);
    } finally {
      setIsLoading(false);
    }
  };

  const generateBotPersona = async () => {
    const traits = parseCommaSeparated(personalityTraits);
    const domains = parseCommaSeparated(knowledgeDomains);
    if (!traits.length) {
      toast.error('Add at least one personality trait');
      return;
    }
    if (!domains.length) {
      toast.error('Add at least one knowledge domain');
      return;
    }

    setIsLoading(true);
    setResult(null);
    setResultCategory('bot');

    try {
      const response = await apiFetch(`${API_URL}/api/bot-persona/ai/persona/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          persona_type: personaType,
          personality_traits: traits,
          knowledge_domains: domains,
        }),
      });

      const data = await readApiJson(response);
      setResult({
        success: data.success !== false,
        data: data.bot_persona ?? data,
        ai_generated: Boolean(data.ai_generated),
        model: typeof data.model === 'string' ? data.model : undefined,
      });
    } catch (error: unknown) {
      recordFailure('Failed to generate bot persona', error);
    } finally {
      setIsLoading(false);
    }
  };

  const generateTestCases = async () => {
    const feature = testFeature.trim();
    if (!feature) {
      toast.error('Please describe the feature to test');
      return;
    }

    setIsLoading(true);
    setResult(null);
    setResultCategory('testing');

    try {
      const response = await apiFetch(`${API_URL}/api/testing-qa/ai/test-cases/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          feature,
          test_type: testType,
        }),
      });

      const data = await readApiJson(response);
      setResult({
        success: data.success !== false,
        data: data.test_cases ?? data,
        ai_generated: Boolean(data.ai_generated),
        model: typeof data.model === 'string' ? data.model : undefined,
      });
    } catch (error: unknown) {
      recordFailure('Failed to generate test cases', error);
    } finally {
      setIsLoading(false);
    }
  };

  // =========================================================================
  // UI COMPONENTS
  // =========================================================================

  const renderChipSelector = (
    options: string[],
    selected: string,
    onSelect: (value: string) => void,
    label: string
  ) => (
    <View style={styles.selectorContainer}>
      <Text style={[styles.selectorLabel, { color: colors.text }]}>{label}</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipScroll}>
        {options.map((option) => (
          <TouchableOpacity
            key={option}
            disabled={isLoading}
            style={[
              styles.chip,
              isLoading && styles.controlDisabled,
              {
                backgroundColor: selected === option ? colors.primary : colors.cardBackground,
                borderColor: colors.border
              }
            ]}
            onPress={() => onSelect(option)}
            accessibilityRole="button"
            accessibilityState={{ selected: selected === option, disabled: isLoading }}
          >
            <Text style={[
              styles.chipText,
              { color: selected === option ? '#FFF' : colors.text }
            ]}>
              {option.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
    </View>
  );

  const renderToggle = (label: string, value: boolean, onToggle: () => void) => (
    <TouchableOpacity
      style={[styles.toggle, { borderColor: colors.border }, isLoading && styles.controlDisabled]}
      onPress={onToggle}
      disabled={isLoading}
      accessibilityRole="switch"
      accessibilityState={{ checked: value, disabled: isLoading }}
    >
      <Text style={[styles.toggleText, { color: colors.text }]}>{label}</Text>
      <View style={[
        styles.toggleSwitch,
        { backgroundColor: value ? colors.primary : colors.border }
      ]}>
        <View style={[
          styles.toggleKnob,
          { transform: [{ translateX: value ? 14 : 0 }] }
        ]} />
      </View>
    </TouchableOpacity>
  );

  const renderCategoryTabs = () => (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      style={[styles.categoryTabs, { borderBottomColor: colors.border }]}
    >
      {CATEGORIES.map((cat) => (
        <TouchableOpacity
          key={cat.key}
          disabled={isLoading}
          style={[
            styles.categoryTab,
            isLoading && styles.controlDisabled,
            activeCategory === cat.key && {
              backgroundColor: colors.primary + '20',
              borderBottomColor: colors.primary,
              borderBottomWidth: 2
            }
          ]}
          onPress={() => {
            setActiveCategory(cat.key);
            setResult(null);
            setResultCategory(null);
          }}
          accessibilityRole="tab"
          accessibilityLabel={`${cat.label}: ${cat.desc}`}
          accessibilityState={{ selected: activeCategory === cat.key, disabled: isLoading }}
        >
          <Ionicons
            name={cat.icon as any}
            size={20}
            color={activeCategory === cat.key ? colors.primary : colors.textSecondary}
          />
          <Text style={[
            styles.categoryLabel,
            { color: activeCategory === cat.key ? colors.primary : colors.textSecondary }
          ]}>
            {cat.label}
          </Text>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );

  const renderNPCForm = () => (
    <View style={styles.formContainer}>
      <Text style={[styles.formTitle, { color: colors.text }]}>🎭 AI NPC Generator</Text>
      <Text style={[styles.formSubtitle, { color: colors.textSecondary }]}>
        Create rich, detailed NPCs with AI-powered personalities and dialogue
      </Text>

      <Text style={[styles.inputLabel, { color: colors.text }]}>Describe your NPC:</Text>
      <TextInput
        style={[styles.textArea, { backgroundColor: colors.codeBackground, color: colors.text, borderColor: colors.border }]}
        placeholder="E.g., A grizzled old blacksmith who lost his family in the war but still has hope..."
        placeholderTextColor={colors.textSecondary}
        value={npcDescription}
        onChangeText={setNpcDescription}
        multiline
        numberOfLines={3}
        editable={!isLoading}
        accessibilityLabel="NPC description"
      />

      {renderChipSelector(archetypes, npcArchetype, setNpcArchetype, '🎯 Archetype:')}

      <View style={styles.toggleRow}>
        {renderToggle('Include Dialogue', includeDialogue, () => setIncludeDialogue(!includeDialogue))}
        {renderToggle('Include Quests', includeQuests, () => setIncludeQuests(!includeQuests))}
      </View>

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: colors.primary }]}
        onPress={generateNPC}
        disabled={isLoading}
        accessibilityRole="button"
        accessibilityState={{ disabled: isLoading, busy: isLoading }}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="sparkles" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Generate NPC with AI</Text>
          </>
        )}
      </TouchableOpacity>
    </View>
  );

  const renderWorldForm = () => (
    <View style={styles.formContainer}>
      <Text style={[styles.formTitle, { color: colors.text }]}>🗺️ AI World Generator</Text>
      <Text style={[styles.formSubtitle, { color: colors.textSecondary }]}>
        Create immersive world regions with locations, encounters, and secrets
      </Text>

      {renderChipSelector(biomes, worldBiome, setWorldBiome, '🌿 Biome:')}
      {renderChipSelector(sizes, worldSize, setWorldSize, '📏 Size:')}

      <Text style={[styles.inputLabel, { color: colors.text }]}>Features (comma-separated):</Text>
      <TextInput
        style={[styles.textInput, { backgroundColor: colors.codeBackground, color: colors.text, borderColor: colors.border }]}
        placeholder="village, dungeon, ancient ruins, hidden cave"
        placeholderTextColor={colors.textSecondary}
        value={worldFeatures}
        onChangeText={setWorldFeatures}
        editable={!isLoading}
        accessibilityLabel="World features"
      />

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: colors.primary }]}
        onPress={generateWorld}
        disabled={isLoading}
        accessibilityRole="button"
        accessibilityState={{ disabled: isLoading, busy: isLoading }}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="globe" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Generate World Region</Text>
          </>
        )}
      </TouchableOpacity>
    </View>
  );

  const renderCombatForm = () => (
    <View style={styles.formContainer}>
      <Text style={[styles.formTitle, { color: colors.text }]}>⚔️ AI Combat Designer</Text>
      <Text style={[styles.formSubtitle, { color: colors.textSecondary }]}>
        Design balanced combat systems with mechanics and formulas
      </Text>

      {renderChipSelector(combatStyles, combatStyle, setCombatStyle, '🎮 Combat Style:')}
      {renderChipSelector(complexities, combatComplexity, setCombatComplexity, '📊 Complexity:')}

      <Text style={[styles.inputLabel, { color: colors.text }]}>Mechanics (comma-separated):</Text>
      <TextInput
        style={[styles.textInput, { backgroundColor: colors.codeBackground, color: colors.text, borderColor: colors.border }]}
        placeholder="attack, defend, magic, cover_system, flanking"
        placeholderTextColor={colors.textSecondary}
        value={combatMechanics}
        onChangeText={setCombatMechanics}
        editable={!isLoading}
        accessibilityLabel="Combat mechanics"
      />

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: colors.primary }]}
        onPress={generateCombat}
        disabled={isLoading}
        accessibilityRole="button"
        accessibilityState={{ disabled: isLoading, busy: isLoading }}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="flash" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Design Combat System</Text>
          </>
        )}
      </TouchableOpacity>
    </View>
  );

  const renderNarrativeForm = () => (
    <View style={styles.formContainer}>
      <Text style={[styles.formTitle, { color: colors.text }]}>📜 AI Quest Generator</Text>
      <Text style={[styles.formSubtitle, { color: colors.textSecondary }]}>
        Create engaging quests with objectives, dialogue, and rewards
      </Text>

      {renderChipSelector(questTypes, questType, setQuestType, '📋 Quest Type:')}
      {renderChipSelector(difficulties, questDifficulty, setQuestDifficulty, '💀 Difficulty:')}

      <Text style={[styles.inputLabel, { color: colors.text }]}>Setting:</Text>
      <TextInput
        style={[styles.textInput, { backgroundColor: colors.codeBackground, color: colors.text, borderColor: colors.border }]}
        placeholder="ancient dwarven mines, cursed forest, floating city"
        placeholderTextColor={colors.textSecondary}
        value={questSetting}
        onChangeText={setQuestSetting}
        editable={!isLoading}
        accessibilityLabel="Quest setting"
      />

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: colors.primary }]}
        onPress={generateQuest}
        disabled={isLoading}
        accessibilityRole="button"
        accessibilityState={{ disabled: isLoading, busy: isLoading }}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="book" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Generate Quest</Text>
          </>
        )}
      </TouchableOpacity>
    </View>
  );

  const renderVFXForm = () => (
    <View style={styles.formContainer}>
      <Text style={[styles.formTitle, { color: colors.text }]}>✨ AI VFX Generator</Text>
      <Text style={[styles.formSubtitle, { color: colors.textSecondary }]}>
        Create stunning particle systems and visual effects
      </Text>

      {renderChipSelector(effectTypes, effectType, setEffectType, '🔥 Effect Type:')}
      {renderChipSelector(visualStyles, visualStyle, setVisualStyle, '🎨 Visual Style:')}

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: colors.primary }]}
        onPress={generateVFX}
        disabled={isLoading}
        accessibilityRole="button"
        accessibilityState={{ disabled: isLoading, busy: isLoading }}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="sparkles" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Generate VFX System</Text>
          </>
        )}
      </TouchableOpacity>
    </View>
  );

  const renderEconomyForm = () => (
    <View style={styles.formContainer}>
      <Text style={[styles.formTitle, { color: colors.text }]}>💰 AI Economy Designer</Text>
      <Text style={[styles.formSubtitle, { color: colors.textSecondary }]}>
        Design balanced game economies with ethical monetization
      </Text>

      {renderChipSelector(gameTypes, gameType, setGameType, '🎮 Game Type:')}
      {renderChipSelector(monetizationModels, monetizationModel, setMonetizationModel, '💵 Monetization:')}

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: colors.primary }]}
        onPress={generateEconomy}
        disabled={isLoading}
        accessibilityRole="button"
        accessibilityState={{ disabled: isLoading, busy: isLoading }}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="cash" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Design Economy</Text>
          </>
        )}
      </TouchableOpacity>
    </View>
  );

  const renderSystemsForm = () => (
    <View style={styles.formContainer}>
      <Text style={[styles.formTitle, { color: colors.text }]}>⚙️ AI Systems Architect</Text>
      <Text style={[styles.formSubtitle, { color: colors.textSecondary }]}>
        Design server architecture and game systems for your intended scale
      </Text>

      {renderChipSelector(gameTypes, gameType, setGameType, '🎮 Game Type:')}

      <Text style={[styles.inputLabel, { color: colors.text }]}>Player Capacity:</Text>
      <TextInput
        style={[styles.textInput, { backgroundColor: colors.codeBackground, color: colors.text, borderColor: colors.border }]}
        placeholder="1000"
        placeholderTextColor={colors.textSecondary}
        value={playerCapacity}
        onChangeText={setPlayerCapacity}
        keyboardType="numeric"
        editable={!isLoading}
        accessibilityLabel="Expected concurrent player capacity"
      />
      <Text style={[styles.inputHint, { color: colors.textSecondary }]}>Positive whole numbers only.</Text>

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: colors.primary }]}
        onPress={generateSystems}
        disabled={isLoading}
        accessibilityRole="button"
        accessibilityState={{ disabled: isLoading, busy: isLoading }}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="cog" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Design Architecture</Text>
          </>
        )}
      </TouchableOpacity>
    </View>
  );

  const renderAnimationForm = () => (
    <View style={styles.formContainer}>
      <Text style={[styles.formTitle, { color: colors.text }]}>🎬 AI Animation Generator</Text>
      <Text style={[styles.formSubtitle, { color: colors.textSecondary }]}>
        Create smooth animations with keyframes and timing
      </Text>

      {renderChipSelector(characterTypes, characterType, setCharacterType, '🦸 Character Type:')}
      {renderChipSelector(animationNames, animationName, setAnimationName, '🎭 Animation:')}
      {renderChipSelector(visualStyles, animationStyle, setAnimationStyle, '🎨 Style:')}

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: colors.primary }]}
        onPress={generateAnimation}
        disabled={isLoading}
        accessibilityRole="button"
        accessibilityState={{ disabled: isLoading, busy: isLoading }}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="film" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Generate Animation</Text>
          </>
        )}
      </TouchableOpacity>
    </View>
  );

  const renderBotForm = () => (
    <View style={styles.formContainer}>
      <Text style={[styles.formTitle, { color: colors.text }]}>🤖 AI Bot Persona Generator</Text>
      <Text style={[styles.formSubtitle, { color: colors.textSecondary }]}>
        Create AI companions with unique personalities
      </Text>

      {renderChipSelector(personaTypes, personaType, setPersonaType, '👤 Persona Type:')}

      <Text style={[styles.inputLabel, { color: colors.text }]}>Personality Traits (comma-separated):</Text>
      <TextInput
        style={[styles.textInput, { backgroundColor: colors.codeBackground, color: colors.text, borderColor: colors.border }]}
        placeholder="friendly, curious, brave, mysterious"
        placeholderTextColor={colors.textSecondary}
        value={personalityTraits}
        onChangeText={setPersonalityTraits}
        editable={!isLoading}
        accessibilityLabel="Bot personality traits"
      />

      <Text style={[styles.inputLabel, { color: colors.text }]}>Knowledge Domains (comma-separated):</Text>
      <TextInput
        style={[styles.textInput, { backgroundColor: colors.codeBackground, color: colors.text, borderColor: colors.border }]}
        placeholder="combat, history, magic, crafting"
        placeholderTextColor={colors.textSecondary}
        value={knowledgeDomains}
        onChangeText={setKnowledgeDomains}
        editable={!isLoading}
        accessibilityLabel="Bot knowledge domains"
      />

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: colors.primary }]}
        onPress={generateBotPersona}
        disabled={isLoading}
        accessibilityRole="button"
        accessibilityState={{ disabled: isLoading, busy: isLoading }}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="hardware-chip" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Generate Bot Persona</Text>
          </>
        )}
      </TouchableOpacity>
    </View>
  );

  const renderTestingForm = () => (
    <View style={styles.formContainer}>
      <Text style={[styles.formTitle, { color: colors.text }]}>🧪 AI Test Generator</Text>
      <Text style={[styles.formSubtitle, { color: colors.textSecondary }]}>
        Create comprehensive test cases for game features
      </Text>

      <Text style={[styles.inputLabel, { color: colors.text }]}>Feature to Test:</Text>
      <TextInput
        style={[styles.textArea, { backgroundColor: colors.codeBackground, color: colors.text, borderColor: colors.border }]}
        placeholder="Describe the game feature you want to test, e.g., 'Player inventory system with item stacking and sorting'"
        placeholderTextColor={colors.textSecondary}
        value={testFeature}
        onChangeText={setTestFeature}
        multiline
        numberOfLines={3}
        editable={!isLoading}
        accessibilityLabel="Feature to test"
      />

      {renderChipSelector(testTypes, testType, setTestType, '📋 Test Type:')}

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: colors.primary }]}
        onPress={generateTestCases}
        disabled={isLoading}
        accessibilityRole="button"
        accessibilityState={{ disabled: isLoading, busy: isLoading }}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="flask" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Generate Test Cases</Text>
          </>
        )}
      </TouchableOpacity>
    </View>
  );

  const renderResult = () => {
    if (!result) return null;

    const resultText = typeof result.data === 'string'
      ? result.data
      : JSON.stringify(result.data, null, 2);

    let displayText = resultText;
    if (displayText.includes('```json')) {
      displayText = displayText.replace(/```json\n?/g, '').replace(/```\n?/g, '');
    }

    const modelLabel = result.model?.trim() || 'AI';
    const generatedCategory = resultCategory ?? activeCategory;
    const generatedCategoryLabel = CATEGORIES.find(category => category.key === generatedCategory)?.label ?? generatedCategory;

    return (
      <View style={[styles.resultContainer, { backgroundColor: colors.codeBackground, borderColor: colors.border }]}>
        <View style={styles.resultHeader}>
          <Text style={[styles.resultTitle, { color: colors.text }]}>
            {result.success ? '✅ Generated Result' : '⚠️ Generation Failed'}
          </Text>
          {result.ai_generated && (
            <View style={[styles.aiBadge, { backgroundColor: colors.primary }]}> 
              <Text style={styles.aiBadgeText}>🤖 {modelLabel}</Text>
            </View>
          )}
        </View>
        <Text style={[styles.resultCategory, { color: colors.textSecondary }]}>
          {generatedCategoryLabel}
        </Text>
        <ScrollView style={styles.resultScroll} nestedScrollEnabled>
          <Text style={[styles.resultText, { color: colors.text }]}>
            {displayText}
          </Text>
        </ScrollView>
        <View style={styles.resultActions}>
          <TouchableOpacity
            style={[styles.resultActionBtn, { backgroundColor: colors.success }]}
            onPress={async () => {
              try {
                await Clipboard.setStringAsync(displayText);
                toast.success('Result copied to clipboard');
              } catch {
                toast.error('Unable to copy result to clipboard');
              }
            }}
            accessibilityRole="button"
            accessibilityLabel="Copy generated result"
          >
            <Ionicons name="copy" size={16} color="#FFF" />
            <Text style={styles.resultActionText}>Copy Result</Text>
          </TouchableOpacity>
          {result.success && onGenerated && (
            <TouchableOpacity
              style={[styles.resultActionBtn, { backgroundColor: colors.primary }]}
              onPress={() => {
                try {
                  onGenerated(result.data, generatedCategory);
                  toast.success('Added result to game builder');
                } catch {
                  toast.error('Unable to add result to game builder');
                }
              }}
              accessibilityRole="button"
              accessibilityLabel="Add generated result to game builder"
            >
              <Ionicons name="add-circle" size={16} color="#FFF" />
              <Text style={styles.resultActionText}>Add to Game Builder</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    );
  };

  const renderActiveForm = () => {
    switch (activeCategory) {
      case 'npc': return renderNPCForm();
      case 'world': return renderWorldForm();
      case 'combat': return renderCombatForm();
      case 'narrative': return renderNarrativeForm();
      case 'animation': return renderAnimationForm();
      case 'vfx': return renderVFXForm();
      case 'bot': return renderBotForm();
      case 'economy': return renderEconomyForm();
      case 'systems': return renderSystemsForm();
      case 'testing': return renderTestingForm();
      default: return renderNPCForm();
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent={false}>
      <View style={[styles.container, { backgroundColor: colors.background }]}> 
        <View style={[styles.header, { borderBottomColor: colors.border }]}> 
          <TouchableOpacity
            onPress={onClose}
            style={styles.closeBtn}
            accessibilityRole="button"
            accessibilityLabel="Close AI Game Generator"
          >
            <Ionicons name="close" size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerTitle}>
            <Text style={[styles.title, { color: colors.text }]}>🎮 AI Game Generator</Text>
            <Text style={[styles.subtitle, { color: colors.textSecondary }]}>Connected model shown per result</Text>
          </View>
          <View style={styles.placeholder} />
        </View>

        {renderCategoryTabs()}

        <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
          {renderActiveForm()}
          {renderResult()}
          <View style={styles.bottomPadding} />
        </ScrollView>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    paddingTop: Platform.OS === 'ios' ? 50 : 30
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingBottom: 12,
    borderBottomWidth: 1
  },
  closeBtn: {
    padding: 8
  },
  headerTitle: {
    alignItems: 'center',
  },
  title: {
    fontSize: 20,
    fontWeight: 'bold'
  },
  subtitle: {
    fontSize: 12,
    marginTop: 2,
  },
  placeholder: {
    width: 40
  },
  categoryTabs: {
    borderBottomWidth: 1,
    maxHeight: 60,
  },
  categoryTab: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 12,
    paddingHorizontal: 16,
    gap: 6,
  },
  controlDisabled: {
    opacity: 0.55,
  },
  categoryLabel: {
    fontSize: 13,
    fontWeight: '600'
  },
  content: {
    flex: 1
  },
  formContainer: {
    padding: 16
  },
  formTitle: {
    fontSize: 22,
    fontWeight: 'bold',
    marginBottom: 4
  },
  formSubtitle: {
    fontSize: 14,
    marginBottom: 20
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
    marginTop: 12,
  },
  inputHint: {
    fontSize: 12,
    marginTop: 6,
  },
  textArea: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
    minHeight: 80,
    textAlignVertical: 'top'
  },
  textInput: {
    borderWidth: 1,
    borderRadius: 8,
    padding: 12,
    fontSize: 14,
  },
  selectorContainer: {
    marginTop: 16,
  },
  selectorLabel: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
  },
  chipScroll: {
    marginBottom: 8
  },
  chip: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
    marginRight: 8,
    borderWidth: 1
  },
  chipText: {
    fontSize: 13,
    fontWeight: '500'
  },
  toggleRow: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 16,
  },
  toggle: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 12,
    borderRadius: 8,
    borderWidth: 1,
  },
  toggleText: {
    fontSize: 13,
    fontWeight: '500',
  },
  toggleSwitch: {
    width: 36,
    height: 22,
    borderRadius: 11,
    padding: 2,
  },
  toggleKnob: {
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: '#FFF',
  },
  generateBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 16,
    borderRadius: 12,
    gap: 8,
    marginTop: 20
  },
  generateBtnText: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '700'
  },
  resultContainer: {
    margin: 16,
    borderRadius: 12,
    borderWidth: 1,
    padding: 16
  },
  resultHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  resultTitle: {
    fontSize: 16,
    fontWeight: '700'
  },
  resultCategory: {
    fontSize: 12,
    marginBottom: 12,
  },
  aiBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  aiBadgeText: {
    color: '#FFF',
    fontSize: 11,
    fontWeight: '600',
  },
  resultScroll: {
    maxHeight: 300
  },
  resultText: {
    fontSize: 12,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    lineHeight: 18
  },
  resultActions: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginTop: 12,
  },
  resultActionBtn: {
    flex: 1,
    minWidth: 140,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 12,
    borderRadius: 8,
    gap: 6,
  },
  resultActionText: {
    color: '#FFF',
    fontSize: 14,
    fontWeight: '600',
  },
  bottomPadding: {
    height: 40
  },
});

export default AIGameGeneratorModal;
