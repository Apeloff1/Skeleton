/**
 * Music Pipeline Modal v11.0.0
 * AI-Powered Game Music Generation System
 */

import React, { useState, useEffect } from 'react';
import { API_BASE } from '../../utils/apiBase';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput,
  Modal, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const API_URL = API_BASE;

interface MusicPipelineModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  onMusicGenerated?: (composition: any) => void;
}

type MusicMode = 'generate' | 'sound-effect' | 'adaptive' | 'presets';

const GENRES = ['8bit', 'chiptune', 'orchestral', 'ambient', 'electronic', 'rock', 'jazz', 'synthwave', 'lofi', 'epic', 'horror', 'peaceful', 'action', 'puzzle', 'adventure', 'retro'];
const MOODS = ['happy', 'sad', 'tense', 'peaceful', 'epic', 'mysterious', 'energetic', 'calm', 'dark', 'uplifting', 'nostalgic', 'heroic'];
const SFX_CATEGORIES = ['ui', 'combat', 'environment', 'character', 'item', 'ambient', 'explosion', 'magic', 'mechanical', 'nature'];

export const MusicPipelineModal: React.FC<MusicPipelineModalProps> = ({
  visible, onClose, colors, onMusicGenerated
}) => {
  const [mode, setMode] = useState<MusicMode | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [presets, setPresets] = useState<any[]>([]);
  
  // Generation form state
  const [description, setDescription] = useState('');
  const [genre, setGenre] = useState('orchestral');
  const [mood, setMood] = useState('epic');
  const [duration, setDuration] = useState<'short' | 'medium' | 'long'>('medium');
  const [tempo, setTempo] = useState('');
  const [loopable, setLoopable] = useState(true);
  const [gameContext, setGameContext] = useState('');
  
  // SFX state
  const [sfxDescription, setSfxDescription] = useState('');
  const [sfxCategory, setSfxCategory] = useState('ui');
  const [sfxDuration, setSfxDuration] = useState<'instant' | 'short' | 'medium'>('short');
  
  // Adaptive state
  const [gameState, setGameState] = useState('');
  const [intensity, setIntensity] = useState(0.5);

  useEffect(() => {
    if (visible) {
      loadPresets();
    }
  }, [visible]);

  const loadPresets = async () => {
    try {
      const response = await apiFetch(`${API_URL}/api/music/presets`);
      const data = await response.json();
      setPresets(data.presets || []);
    } catch (error) {
      console.error('Failed to load presets:', error);
    }
  };

  const generateMusic = async () => {
    if (!description.trim()) return;
    setIsLoading(true);
    setResult(null);
    try {
      const response = await apiFetch(`${API_URL}/api/music/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description,
          genre,
          mood,
          duration,
          tempo: tempo ? parseInt(tempo) : undefined,
          loopable,
          game_context: gameContext || undefined
        })
      });
      const data = await response.json();
      setResult(data);
      if (onMusicGenerated) onMusicGenerated(data);
    } catch (error) {
      console.error('Music generation failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const generateSoundEffect = async () => {
    if (!sfxDescription.trim()) return;
    setIsLoading(true);
    setResult(null);
    try {
      const response = await apiFetch(`${API_URL}/api/music/sound-effect`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description: sfxDescription,
          category: sfxCategory,
          duration: sfxDuration
        })
      });
      const data = await response.json();
      setResult(data);
    } catch (error) {
      console.error('SFX generation failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const generateAdaptiveMusic = async () => {
    if (!gameState.trim()) return;
    setIsLoading(true);
    setResult(null);
    try {
      const response = await apiFetch(`${API_URL}/api/music/adaptive-music`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          game_state: gameState,
          intensity,
          transitions: true
        })
      });
      const data = await response.json();
      setResult(data);
    } catch (error) {
      console.error('Adaptive music failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const applyPreset = (preset: any) => {
    setDescription(preset.description);
    setGenre(preset.genre);
    setMood(preset.mood);
    setTempo(preset.tempo?.toString() || '');
    setLoopable(preset.loopable);
    setMode('generate');
  };

  const modes = [
    { key: 'generate', icon: 'musical-notes-outline', label: 'Generate Music', desc: 'Create game soundtracks', color: '#8B5CF6' },
    { key: 'sound-effect', icon: 'volume-high-outline', label: 'Sound Effects', desc: 'Design game SFX', color: '#F59E0B' },
    { key: 'adaptive', icon: 'pulse-outline', label: 'Adaptive Music', desc: 'Dynamic intensity system', color: '#10B981' },
    { key: 'presets', icon: 'albums-outline', label: 'Presets', desc: 'Quick start templates', color: '#3B82F6' },
  ];

  const renderModeSelector = () => (
    <View style={styles.modesContainer}>
      <Text style={[styles.sectionTitle, { color: colors.textMuted }]}>Music Creation Tools</Text>
      {modes.map((m) => (
        <TouchableOpacity
          key={m.key}
          style={[styles.modeCard, { backgroundColor: colors.surfaceAlt }]}
          onPress={() => setMode(m.key as MusicMode)}
        >
          <View style={[styles.modeIcon, { backgroundColor: m.color + '20' }]}>
            <Ionicons name={m.icon as any} size={24} color={m.color} />
          </View>
          <View style={styles.modeInfo}>
            <Text style={[styles.modeLabel, { color: colors.text }]}>{m.label}</Text>
            <Text style={[styles.modeDesc, { color: colors.textMuted }]}>{m.desc}</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
        </TouchableOpacity>
      ))}
    </View>
  );

  const renderGenerateForm = () => (
    <ScrollView style={styles.formContainer}>
      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Description *</Text>
      <TextInput
        style={[styles.textInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
        value={description}
        onChangeText={setDescription}
        placeholder="Epic orchestral battle theme with rising tension..."
        placeholderTextColor={colors.textMuted}
        multiline
      />

      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Genre</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipScroll}>
        {GENRES.map((g) => (
          <TouchableOpacity
            key={g}
            style={[styles.chip, { backgroundColor: genre === g ? colors.primary : colors.surfaceAlt }]}
            onPress={() => setGenre(g)}
          >
            <Text style={[styles.chipText, { color: genre === g ? '#FFF' : colors.text }]}>{g}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Mood</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipScroll}>
        {MOODS.map((m) => (
          <TouchableOpacity
            key={m}
            style={[styles.chip, { backgroundColor: mood === m ? colors.primary : colors.surfaceAlt }]}
            onPress={() => setMood(m)}
          >
            <Text style={[styles.chipText, { color: mood === m ? '#FFF' : colors.text }]}>{m}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <View style={styles.row}>
        <View style={styles.halfInput}>
          <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Duration</Text>
          <View style={styles.durationSelector}>
            {(['short', 'medium', 'long'] as const).map((d) => (
              <TouchableOpacity
                key={d}
                style={[styles.durationBtn, { backgroundColor: duration === d ? colors.primary : colors.surfaceAlt }]}
                onPress={() => setDuration(d)}
              >
                <Text style={[styles.durationText, { color: duration === d ? '#FFF' : colors.text }]}>{d}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
        <View style={styles.halfInput}>
          <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Tempo (BPM)</Text>
          <TextInput
            style={[styles.smallInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
            value={tempo}
            onChangeText={setTempo}
            placeholder="Auto"
            placeholderTextColor={colors.textMuted}
            keyboardType="numeric"
          />
        </View>
      </View>

      <TouchableOpacity
        style={[styles.toggleRow, { backgroundColor: colors.surfaceAlt }]}
        onPress={() => setLoopable(!loopable)}
      >
        <View style={styles.toggleInfo}>
          <Ionicons name="repeat" size={20} color={loopable ? colors.primary : colors.textMuted} />
          <Text style={[styles.toggleLabel, { color: colors.text }]}>Loopable Track</Text>
        </View>
        <Ionicons name={loopable ? 'checkbox' : 'square-outline'} size={24} color={loopable ? colors.primary : colors.textMuted} />
      </TouchableOpacity>

      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Game Context (Optional)</Text>
      <TextInput
        style={[styles.textInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
        value={gameContext}
        onChangeText={setGameContext}
        placeholder="Boss fight in a dark castle..."
        placeholderTextColor={colors.textMuted}
      />

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: colors.primary }]}
        onPress={generateMusic}
        disabled={isLoading || !description.trim()}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="musical-notes" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Generate Music</Text>
          </>
        )}
      </TouchableOpacity>
    </ScrollView>
  );

  const renderSFXForm = () => (
    <View style={styles.formContainer}>
      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Sound Description *</Text>
      <TextInput
        style={[styles.textInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
        value={sfxDescription}
        onChangeText={setSfxDescription}
        placeholder="Coin pickup with magical sparkle..."
        placeholderTextColor={colors.textMuted}
        multiline
      />

      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Category</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipScroll}>
        {SFX_CATEGORIES.map((c) => (
          <TouchableOpacity
            key={c}
            style={[styles.chip, { backgroundColor: sfxCategory === c ? '#F59E0B' : colors.surfaceAlt }]}
            onPress={() => setSfxCategory(c)}
          >
            <Text style={[styles.chipText, { color: sfxCategory === c ? '#FFF' : colors.text }]}>{c}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Duration</Text>
      <View style={styles.durationSelector}>
        {(['instant', 'short', 'medium'] as const).map((d) => (
          <TouchableOpacity
            key={d}
            style={[styles.durationBtn, { backgroundColor: sfxDuration === d ? '#F59E0B' : colors.surfaceAlt }]}
            onPress={() => setSfxDuration(d)}
          >
            <Text style={[styles.durationText, { color: sfxDuration === d ? '#FFF' : colors.text }]}>{d}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: '#F59E0B' }]}
        onPress={generateSoundEffect}
        disabled={isLoading || !sfxDescription.trim()}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="volume-high" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Generate SFX</Text>
          </>
        )}
      </TouchableOpacity>
    </View>
  );

  const renderAdaptiveForm = () => (
    <View style={styles.formContainer}>
      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Game State *</Text>
      <TextInput
        style={[styles.textInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
        value={gameState}
        onChangeText={setGameState}
        placeholder="Combat with multiple enemies..."
        placeholderTextColor={colors.textMuted}
        multiline
      />

      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Intensity: {Math.round(intensity * 100)}%</Text>
      <View style={styles.sliderContainer}>
        <TouchableOpacity onPress={() => setIntensity(Math.max(0, intensity - 0.1))}>
          <Ionicons name="remove-circle" size={28} color={colors.primary} />
        </TouchableOpacity>
        <View style={[styles.sliderTrack, { backgroundColor: colors.surfaceAlt }]}>
          <View style={[styles.sliderFill, { width: `${intensity * 100}%`, backgroundColor: getIntensityColor(intensity) }]} />
        </View>
        <TouchableOpacity onPress={() => setIntensity(Math.min(1, intensity + 0.1))}>
          <Ionicons name="add-circle" size={28} color={colors.primary} />
        </TouchableOpacity>
      </View>
      <View style={styles.intensityLabels}>
        <Text style={[styles.intensityLabel, { color: colors.textMuted }]}>Calm</Text>
        <Text style={[styles.intensityLabel, { color: colors.textMuted }]}>Intense</Text>
      </View>

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: '#10B981' }]}
        onPress={generateAdaptiveMusic}
        disabled={isLoading || !gameState.trim()}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="pulse" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Generate Adaptive System</Text>
          </>
        )}
      </TouchableOpacity>
    </View>
  );

  const renderPresets = () => (
    <View style={styles.presetsContainer}>
      <Text style={[styles.sectionTitle, { color: colors.textMuted }]}>Quick Start Presets</Text>
      {presets.map((preset) => (
        <TouchableOpacity
          key={preset.id}
          style={[styles.presetCard, { backgroundColor: colors.surfaceAlt }]}
          onPress={() => applyPreset(preset)}
        >
          <View style={[styles.presetIcon, { backgroundColor: '#3B82F620' }]}>
            <Ionicons name="musical-note" size={24} color="#3B82F6" />
          </View>
          <View style={styles.presetInfo}>
            <Text style={[styles.presetName, { color: colors.text }]}>{preset.name}</Text>
            <Text style={[styles.presetDesc, { color: colors.textMuted }]}>{preset.description}</Text>
            <View style={styles.presetTags}>
              <View style={[styles.presetTag, { backgroundColor: colors.primary + '20' }]}>
                <Text style={[styles.presetTagText, { color: colors.primary }]}>{preset.genre}</Text>
              </View>
              <View style={[styles.presetTag, { backgroundColor: colors.secondary + '20' }]}>
                <Text style={[styles.presetTagText, { color: colors.secondary }]}>{preset.mood}</Text>
              </View>
              <View style={[styles.presetTag, { backgroundColor: colors.accent + '20' }]}>
                <Text style={[styles.presetTagText, { color: colors.accent }]}>{preset.tempo} BPM</Text>
              </View>
            </View>
          </View>
        </TouchableOpacity>
      ))}
    </View>
  );

  const renderResult = () => {
    if (!result) return null;
    return (
      <ScrollView style={styles.resultContainer}>
        <View style={[styles.resultHeader, { backgroundColor: colors.surfaceAlt }]}>
          <Ionicons name="checkmark-circle" size={24} color="#10B981" />
          <Text style={[styles.resultTitle, { color: colors.text }]}>Generation Complete!</Text>
        </View>
        
        {result.export_ready && (
          <View style={[styles.exportSection, { backgroundColor: colors.surfaceAlt }]}>
            <Text style={[styles.exportTitle, { color: colors.text }]}>Export Prompts</Text>
            <View style={styles.exportItem}>
              <Text style={[styles.exportLabel, { color: colors.textMuted }]}>Suno:</Text>
              <Text style={[styles.exportValue, { color: colors.text }]}>{result.export_ready.suno_prompt}</Text>
            </View>
            <View style={styles.exportItem}>
              <Text style={[styles.exportLabel, { color: colors.textMuted }]}>Stable Audio:</Text>
              <Text style={[styles.exportValue, { color: colors.text }]}>{result.export_ready.stable_audio_prompt}</Text>
            </View>
          </View>
        )}

        <Text style={[styles.compositionText, { color: colors.text }]}>
          {result.composition || result.sound_design || result.adaptive_system || JSON.stringify(result, null, 2)}
        </Text>
      </ScrollView>
    );
  };

  const getIntensityColor = (val: number) => {
    if (val < 0.25) return '#10B981';
    if (val < 0.5) return '#3B82F6';
    if (val < 0.75) return '#F59E0B';
    return '#EF4444';
  };

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <View style={[styles.header, { borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={mode ? () => { setMode(null); setResult(null); } : onClose} style={styles.backBtn}>
            <Ionicons name={mode ? "arrow-back" : "close"} size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerTitle}>
            <Ionicons name="musical-notes" size={24} color="#8B5CF6" />
            <Text style={[styles.title, { color: colors.text }]}>Music Pipeline</Text>
          </View>
          <View style={{ width: 40 }} />
        </View>

        <ScrollView style={styles.content} contentContainerStyle={styles.contentContainer}>
          {!mode && renderModeSelector()}
          {mode === 'generate' && !result && renderGenerateForm()}
          {mode === 'sound-effect' && !result && renderSFXForm()}
          {mode === 'adaptive' && !result && renderAdaptiveForm()}
          {mode === 'presets' && renderPresets()}
          {result && renderResult()}
        </ScrollView>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1 },
  backBtn: { width: 40, height: 40, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { fontSize: 18, fontWeight: '700' },
  content: { flex: 1 },
  contentContainer: { padding: 16 },
  modesContainer: { gap: 12 },
  sectionTitle: { fontSize: 13, fontWeight: '600', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 0.5 },
  modeCard: { flexDirection: 'row', alignItems: 'center', padding: 16, borderRadius: 12, gap: 14 },
  modeIcon: { width: 48, height: 48, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
  modeInfo: { flex: 1 },
  modeLabel: { fontSize: 16, fontWeight: '700' },
  modeDesc: { fontSize: 13, marginTop: 2 },
  formContainer: { gap: 16 },
  inputLabel: { fontSize: 13, fontWeight: '600' },
  textInput: { padding: 14, borderRadius: 12, borderWidth: 1, minHeight: 80, textAlignVertical: 'top' },
  chipScroll: { marginVertical: 8 },
  chip: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20, marginRight: 8 },
  chipText: { fontSize: 13, fontWeight: '600' },
  row: { flexDirection: 'row', gap: 16 },
  halfInput: { flex: 1 },
  durationSelector: { flexDirection: 'row', gap: 8 },
  durationBtn: { flex: 1, paddingVertical: 10, borderRadius: 8, alignItems: 'center' },
  durationText: { fontSize: 13, fontWeight: '600' },
  smallInput: { padding: 12, borderRadius: 8, borderWidth: 1 },
  toggleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 14, borderRadius: 12 },
  toggleInfo: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  toggleLabel: { fontSize: 14, fontWeight: '600' },
  generateBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 16, borderRadius: 12, gap: 10, marginTop: 8 },
  generateBtnText: { color: '#FFF', fontSize: 16, fontWeight: '700' },
  sliderContainer: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  sliderTrack: { flex: 1, height: 8, borderRadius: 4, overflow: 'hidden' },
  sliderFill: { height: '100%', borderRadius: 4 },
  intensityLabels: { flexDirection: 'row', justifyContent: 'space-between' },
  intensityLabel: { fontSize: 12 },
  presetsContainer: { gap: 12 },
  presetCard: { flexDirection: 'row', padding: 16, borderRadius: 12, gap: 14 },
  presetIcon: { width: 48, height: 48, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
  presetInfo: { flex: 1 },
  presetName: { fontSize: 16, fontWeight: '700' },
  presetDesc: { fontSize: 13, marginTop: 2 },
  presetTags: { flexDirection: 'row', gap: 6, marginTop: 8, flexWrap: 'wrap' },
  presetTag: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  presetTagText: { fontSize: 11, fontWeight: '600' },
  resultContainer: { flex: 1 },
  resultHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 16, borderRadius: 12, marginBottom: 16 },
  resultTitle: { fontSize: 16, fontWeight: '700' },
  exportSection: { padding: 16, borderRadius: 12, marginBottom: 16 },
  exportTitle: { fontSize: 14, fontWeight: '700', marginBottom: 12 },
  exportItem: { marginBottom: 12 },
  exportLabel: { fontSize: 12, fontWeight: '600', marginBottom: 4 },
  exportValue: { fontSize: 13, lineHeight: 20 },
  compositionText: { fontSize: 14, lineHeight: 22 },
});
