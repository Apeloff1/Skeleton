/**
 * Asset Pipeline Modal v11.2.0
 * 2D Sprites & 3D Models Generation
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

interface AssetPipelineModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
}

type AssetMode = 'sprite' | 'model' | 'tileset' | 'presets';

export const AssetPipelineModal: React.FC<AssetPipelineModalProps> = ({
  visible, onClose, colors
}) => {
  const [mode, setMode] = useState<AssetMode | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [categories2D, setCategories2D] = useState<any>({});
  const [categories3D, setCategories3D] = useState<any>({});
  
  // Sprite form
  const [spriteDesc, setSpriteDesc] = useState('');
  const [spriteCategory, setSpriteCategory] = useState('characters');
  const [spriteType] = useState('player');
  const [spriteStyle, setSpriteStyle] = useState('pixel_art');
  const [spriteRes, setSpriteRes] = useState('32x32');
  const [spriteFrames, setSpriteFrames] = useState(1);
  
  // 3D Model form
  const [modelDesc, setModelDesc] = useState('');
  const [modelCategory, setModelCategory] = useState('characters');
  const [modelType] = useState('humanoid');
  const [modelStyle, setModelStyle] = useState('stylized');
  const [modelPoly, setModelPoly] = useState('mid_poly');
  const [modelTextures, setModelTextures] = useState(true);
  
  // Tileset form
  const [tileTheme, setTileTheme] = useState('forest');
  const [tileSize, setTileSize] = useState(32);

  useEffect(() => {
    if (visible) {
      loadCategories();
    }
  }, [visible]);

  const loadCategories = async () => {
    try {
      const [res2D, res3D] = await Promise.all([
        apiFetch(`${API_URL}/api/assets/categories/2d`),
        apiFetch(`${API_URL}/api/assets/categories/3d`)
      ]);
      setCategories2D(await res2D.json());
      setCategories3D(await res3D.json());
    } catch (error) {
      console.error('Failed to load categories:', error);
    }
  };

  const generateSprite = async () => {
    if (!spriteDesc.trim()) return;
    setIsLoading(true);
    setResult(null);
    try {
      const response = await apiFetch(`${API_URL}/api/assets/generate/sprite`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description: spriteDesc,
          category: spriteCategory,
          asset_type: spriteType,
          style: spriteStyle,
          resolution: spriteRes,
          animation_frames: spriteFrames
        })
      });
      const data = await response.json();
      setResult(data);
    } catch (error) {
      console.error('Sprite generation failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const generateModel = async () => {
    if (!modelDesc.trim()) return;
    setIsLoading(true);
    setResult(null);
    try {
      const response = await apiFetch(`${API_URL}/api/assets/generate/model`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description: modelDesc,
          category: modelCategory,
          asset_type: modelType,
          style: modelStyle,
          poly_count: modelPoly,
          textures: modelTextures
        })
      });
      const data = await response.json();
      setResult(data);
    } catch (error) {
      console.error('Model generation failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const generateTileset = async () => {
    setIsLoading(true);
    setResult(null);
    try {
      const response = await apiFetch(`${API_URL}/api/assets/generate/tileset`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          theme: tileTheme,
          style: spriteStyle,
          tile_size: tileSize,
          include_autotile: true
        })
      });
      const data = await response.json();
      setResult(data);
    } catch (error) {
      console.error('Tileset generation failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const modes = [
    { key: 'sprite', icon: 'image-outline', label: '2D Sprites', desc: 'Characters, items, UI', color: '#10B981' },
    { key: 'model', icon: 'cube-outline', label: '3D Models', desc: 'Characters, props, vehicles', color: '#3B82F6' },
    { key: 'tileset', icon: 'grid-outline', label: 'Tilesets', desc: 'Game world tiles', color: '#F59E0B' },
    { key: 'presets', icon: 'albums-outline', label: 'Presets', desc: 'Quick start templates', color: '#8B5CF6' },
  ];

  const spriteStyles = ['pixel_art', 'hand_drawn', 'vector', 'anime', 'realistic'];
  const modelStyles = ['realistic', 'stylized', 'low_poly', 'cartoon'];
  const resolutions = ['16x16', '32x32', '64x64', '128x128', '256x256'];
  const polyOptions = ['low_poly', 'mid_poly', 'high_poly'];
  const tileThemes = ['forest', 'desert', 'ice', 'lava', 'dungeon', 'city', 'space'];

  const renderModeSelector = () => (
    <View style={styles.modesContainer}>
      <Text style={[styles.sectionTitle, { color: colors.textMuted }]}>Asset Type</Text>
      {modes.map((m) => (
        <TouchableOpacity
          key={m.key}
          style={[styles.modeCard, { backgroundColor: colors.surfaceAlt }]}
          onPress={() => setMode(m.key as AssetMode)}
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

  const renderSpriteForm = () => (
    <ScrollView style={styles.formContainer}>
      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Description *</Text>
      <TextInput
        style={[styles.textInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
        value={spriteDesc}
        onChangeText={setSpriteDesc}
        placeholder="A fierce dragon with red scales breathing fire..."
        placeholderTextColor={colors.textMuted}
        multiline
      />

      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Category</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipScroll}>
        {Object.keys(categories2D).map((cat) => (
          <TouchableOpacity
            key={cat}
            style={[styles.chip, { backgroundColor: spriteCategory === cat ? '#10B981' : colors.surfaceAlt }]}
            onPress={() => setSpriteCategory(cat)}
          >
            <Text style={[styles.chipText, { color: spriteCategory === cat ? '#FFF' : colors.text }]}>{cat}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Style</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipScroll}>
        {spriteStyles.map((s) => (
          <TouchableOpacity
            key={s}
            style={[styles.chip, { backgroundColor: spriteStyle === s ? colors.primary : colors.surfaceAlt }]}
            onPress={() => setSpriteStyle(s)}
          >
            <Text style={[styles.chipText, { color: spriteStyle === s ? '#FFF' : colors.text }]}>{s.replace('_', ' ')}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <View style={styles.row}>
        <View style={styles.halfInput}>
          <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Resolution</Text>
          <View style={styles.resSelector}>
            {resolutions.slice(0, 3).map((r) => (
              <TouchableOpacity
                key={r}
                style={[styles.resBtn, { backgroundColor: spriteRes === r ? colors.primary : colors.surfaceAlt }]}
                onPress={() => setSpriteRes(r)}
              >
                <Text style={[styles.resText, { color: spriteRes === r ? '#FFF' : colors.text }]}>{r}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
        <View style={styles.halfInput}>
          <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Frames</Text>
          <View style={styles.frameSelector}>
            {[1, 4, 8, 12].map((f) => (
              <TouchableOpacity
                key={f}
                style={[styles.frameBtn, { backgroundColor: spriteFrames === f ? colors.secondary : colors.surfaceAlt }]}
                onPress={() => setSpriteFrames(f)}
              >
                <Text style={[styles.frameText, { color: spriteFrames === f ? '#FFF' : colors.text }]}>{f}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      </View>

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: '#10B981' }]}
        onPress={generateSprite}
        disabled={isLoading || !spriteDesc.trim()}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="sparkles" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Generate Sprite</Text>
          </>
        )}
      </TouchableOpacity>
    </ScrollView>
  );

  const renderModelForm = () => (
    <ScrollView style={styles.formContainer}>
      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Description *</Text>
      <TextInput
        style={[styles.textInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
        value={modelDesc}
        onChangeText={setModelDesc}
        placeholder="A medieval knight in full plate armor..."
        placeholderTextColor={colors.textMuted}
        multiline
      />

      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Category</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipScroll}>
        {Object.keys(categories3D).map((cat) => (
          <TouchableOpacity
            key={cat}
            style={[styles.chip, { backgroundColor: modelCategory === cat ? '#3B82F6' : colors.surfaceAlt }]}
            onPress={() => setModelCategory(cat)}
          >
            <Text style={[styles.chipText, { color: modelCategory === cat ? '#FFF' : colors.text }]}>{cat}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Style</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipScroll}>
        {modelStyles.map((s) => (
          <TouchableOpacity
            key={s}
            style={[styles.chip, { backgroundColor: modelStyle === s ? colors.primary : colors.surfaceAlt }]}
            onPress={() => setModelStyle(s)}
          >
            <Text style={[styles.chipText, { color: modelStyle === s ? '#FFF' : colors.text }]}>{s.replace('_', ' ')}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Polygon Count</Text>
      <View style={styles.polySelector}>
        {polyOptions.map((p) => (
          <TouchableOpacity
            key={p}
            style={[styles.polyBtn, { backgroundColor: modelPoly === p ? colors.secondary : colors.surfaceAlt }]}
            onPress={() => setModelPoly(p)}
          >
            <Text style={[styles.polyText, { color: modelPoly === p ? '#FFF' : colors.text }]}>{p.replace('_', ' ')}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity
        style={[styles.toggleRow, { backgroundColor: colors.surfaceAlt }]}
        onPress={() => setModelTextures(!modelTextures)}
      >
        <Text style={[styles.toggleLabel, { color: colors.text }]}>Include Textures</Text>
        <Ionicons name={modelTextures ? 'checkbox' : 'square-outline'} size={24} color={modelTextures ? colors.primary : colors.textMuted} />
      </TouchableOpacity>

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: '#3B82F6' }]}
        onPress={generateModel}
        disabled={isLoading || !modelDesc.trim()}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="cube" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Generate 3D Model</Text>
          </>
        )}
      </TouchableOpacity>
    </ScrollView>
  );

  const renderTilesetForm = () => (
    <ScrollView style={styles.formContainer}>
      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Theme</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipScroll}>
        {tileThemes.map((t) => (
          <TouchableOpacity
            key={t}
            style={[styles.chip, { backgroundColor: tileTheme === t ? '#F59E0B' : colors.surfaceAlt }]}
            onPress={() => setTileTheme(t)}
          >
            <Text style={[styles.chipText, { color: tileTheme === t ? '#FFF' : colors.text }]}>{t}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Tile Size</Text>
      <View style={styles.tileSizeSelector}>
        {[16, 32, 48, 64].map((s) => (
          <TouchableOpacity
            key={s}
            style={[styles.tileSizeBtn, { backgroundColor: tileSize === s ? '#F59E0B' : colors.surfaceAlt }]}
            onPress={() => setTileSize(s)}
          >
            <Text style={[styles.tileSizeText, { color: tileSize === s ? '#FFF' : colors.text }]}>{s}px</Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: '#F59E0B' }]}
        onPress={generateTileset}
        disabled={isLoading}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="grid" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Generate Tileset</Text>
          </>
        )}
      </TouchableOpacity>
    </ScrollView>
  );

  const renderResult = () => {
    if (!result) return null;
    return (
      <ScrollView style={styles.resultContainer}>
        <View style={[styles.resultHeader, { backgroundColor: colors.surfaceAlt }]}>
          <Ionicons name="checkmark-circle" size={24} color="#10B981" />
          <Text style={[styles.resultTitle, { color: colors.text }]}>Asset Generated!</Text>
        </View>
        
        {result.generation && (
          <View style={[styles.promptsSection, { backgroundColor: colors.surfaceAlt }]}>
            <Text style={[styles.promptsTitle, { color: colors.text }]}>Generation Prompts</Text>
            {result.generation.dalle_prompt && (
              <View style={styles.promptItem}>
                <Text style={[styles.promptLabel, { color: colors.primary }]}>DALL-E:</Text>
                <Text style={[styles.promptText, { color: colors.text }]}>{result.generation.dalle_prompt}</Text>
              </View>
            )}
            {result.generation.meshy_prompt && (
              <View style={styles.promptItem}>
                <Text style={[styles.promptLabel, { color: '#3B82F6' }]}>Meshy.ai:</Text>
                <Text style={[styles.promptText, { color: colors.text }]}>{result.generation.meshy_prompt}</Text>
              </View>
            )}
          </View>
        )}

        {result.technical && (
          <View style={[styles.techSection, { backgroundColor: colors.surfaceAlt }]}>
            <Text style={[styles.techTitle, { color: colors.text }]}>Technical Specs</Text>
            <Text style={[styles.techText, { color: colors.textMuted }]}>
              {JSON.stringify(result.technical, null, 2)}
            </Text>
          </View>
        )}
      </ScrollView>
    );
  };

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <View style={[styles.header, { borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={mode ? () => { setMode(null); setResult(null); } : onClose} style={styles.backBtn}>
            <Ionicons name={mode ? "arrow-back" : "close"} size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerTitle}>
            <Ionicons name="color-palette" size={24} color="#10B981" />
            <Text style={[styles.title, { color: colors.text }]}>Asset Pipeline</Text>
          </View>
          <View style={{ width: 40 }} />
        </View>

        <ScrollView style={styles.content} contentContainerStyle={styles.contentContainer}>
          {!mode && renderModeSelector()}
          {mode === 'sprite' && !result && renderSpriteForm()}
          {mode === 'model' && !result && renderModelForm()}
          {mode === 'tileset' && !result && renderTilesetForm()}
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
  sectionTitle: { fontSize: 13, fontWeight: '600', marginBottom: 12, textTransform: 'uppercase' },
  modeCard: { flexDirection: 'row', alignItems: 'center', padding: 16, borderRadius: 12, gap: 14 },
  modeIcon: { width: 48, height: 48, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
  modeInfo: { flex: 1 },
  modeLabel: { fontSize: 16, fontWeight: '700' },
  modeDesc: { fontSize: 13, marginTop: 2 },
  formContainer: { gap: 16 },
  inputLabel: { fontSize: 13, fontWeight: '600', marginBottom: 8 },
  textInput: { padding: 14, borderRadius: 12, borderWidth: 1, minHeight: 80, textAlignVertical: 'top' },
  chipScroll: { marginBottom: 8 },
  chip: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20, marginRight: 8 },
  chipText: { fontSize: 13, fontWeight: '600' },
  row: { flexDirection: 'row', gap: 16 },
  halfInput: { flex: 1 },
  resSelector: { flexDirection: 'row', gap: 6 },
  resBtn: { flex: 1, paddingVertical: 10, borderRadius: 8, alignItems: 'center' },
  resText: { fontSize: 12, fontWeight: '600' },
  frameSelector: { flexDirection: 'row', gap: 6 },
  frameBtn: { flex: 1, paddingVertical: 10, borderRadius: 8, alignItems: 'center' },
  frameText: { fontSize: 13, fontWeight: '600' },
  polySelector: { flexDirection: 'row', gap: 8 },
  polyBtn: { flex: 1, paddingVertical: 12, borderRadius: 10, alignItems: 'center' },
  polyText: { fontSize: 13, fontWeight: '600', textTransform: 'capitalize' },
  toggleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 14, borderRadius: 12, marginTop: 8 },
  toggleLabel: { fontSize: 14, fontWeight: '600' },
  tileSizeSelector: { flexDirection: 'row', gap: 8 },
  tileSizeBtn: { flex: 1, paddingVertical: 12, borderRadius: 10, alignItems: 'center' },
  tileSizeText: { fontSize: 14, fontWeight: '600' },
  generateBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 16, borderRadius: 12, gap: 10, marginTop: 16 },
  generateBtnText: { color: '#FFF', fontSize: 16, fontWeight: '700' },
  resultContainer: { flex: 1 },
  resultHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 16, borderRadius: 12, marginBottom: 16 },
  resultTitle: { fontSize: 18, fontWeight: '700' },
  promptsSection: { padding: 16, borderRadius: 12, marginBottom: 16 },
  promptsTitle: { fontSize: 14, fontWeight: '700', marginBottom: 12 },
  promptItem: { marginBottom: 12 },
  promptLabel: { fontSize: 12, fontWeight: '600', marginBottom: 4 },
  promptText: { fontSize: 13, lineHeight: 20 },
  techSection: { padding: 16, borderRadius: 12 },
  techTitle: { fontSize: 14, fontWeight: '700', marginBottom: 8 },
  techText: { fontSize: 12, fontFamily: 'monospace', lineHeight: 18 },
});
