/**
 * Text-to-Hybrid Pipeline Modal v11.6
 * Complete Game Generation from Text Description
 */

import React, { useState, useEffect, memo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput,
  Modal, ActivityIndicator, Switch,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';

import { apiFetch } from '../../utils/apiController';
const API_URL = Constants.expoConfig?.extra?.apiUrl || process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface HybridPipelineModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
}

type Genre = 'action_rpg' | 'platformer' | 'survival' | 'puzzle' | 'strategy' | 'horror' | 'racing' | 'simulation';
type Scope = 'demo' | 'small' | 'medium' | 'large' | 'massive';

export const HybridPipelineModal = memo(function HybridPipelineModal({
  visible, onClose, colors
}: HybridPipelineModalProps) {
  const [concept, setConcept] = useState('');
  const [genre, setGenre] = useState<Genre>('action_rpg');
  const [scope, setScope] = useState<Scope>('demo');
  const [includeWorld, setIncludeWorld] = useState(true);
  const [includeNarrative, setIncludeNarrative] = useState(true);
  const [includeMechanics, setIncludeMechanics] = useState(true);
  const [includeAssets, setIncludeAssets] = useState(true);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [info, setInfo] = useState<any>(null);

  useEffect(() => {
    if (visible) fetchInfo();
  }, [visible]);

  const fetchInfo = async () => {
    try {
      const res = await apiFetch(`${API_URL}/api/hybrid/info`);
      const data = await res.json();
      setInfo(data);
    } catch (e) {
      console.error('Failed to fetch hybrid info:', e);
    }
  };

  const genres: { id: Genre; name: string; icon: string; color: string }[] = [
    { id: 'action_rpg', name: 'Action RPG', icon: 'shield', color: '#EF4444' },
    { id: 'platformer', name: 'Platformer', icon: 'walk', color: '#F59E0B' },
    { id: 'survival', name: 'Survival', icon: 'leaf', color: '#10B981' },
    { id: 'puzzle', name: 'Puzzle', icon: 'extension-puzzle', color: '#8B5CF6' },
    { id: 'strategy', name: 'Strategy', icon: 'map', color: '#3B82F6' },
    { id: 'horror', name: 'Horror', icon: 'skull', color: '#1F2937' },
    { id: 'racing', name: 'Racing', icon: 'car-sport', color: '#EC4899' },
    { id: 'simulation', name: 'Simulation', icon: 'build', color: '#2563EB' },
  ];

  const scopes: { id: Scope; name: string; hours: string }[] = [
    { id: 'demo', name: 'Demo', hours: '30min' },
    { id: 'small', name: 'Small', hours: '2hrs' },
    { id: 'medium', name: 'Medium', hours: '10hrs' },
    { id: 'large', name: 'Large', hours: '40hrs' },
    { id: 'massive', name: 'Massive', hours: '100+hrs' },
  ];

  const generate = async () => {
    if (!concept.trim()) return;
    setLoading(true);
    setResult(null);

    try {
      const res = await apiFetch(`${API_URL}/api/hybrid/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          concept,
          genre,
          style: 'fantasy',
          scope,
          target_platform: 'all',
          include_world: includeWorld,
          include_narrative: includeNarrative,
          include_mechanics: includeMechanics,
          include_assets: includeAssets,
          include_audio: false,
          quality_preset: 'high'
        })
      });
      const data = await res.json();
      setResult(data);
    } catch (e) {
      console.error('Hybrid generation error:', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={localStyles.overlay}>
        <View style={[localStyles.modal, { backgroundColor: colors.surface }]}>
          {/* Header */}
          <View style={[localStyles.header, { borderBottomColor: colors.border }]}>
            <View style={localStyles.headerTitle}>
              <Ionicons name="rocket" size={24} color="#EC4899" />
              <Text style={[localStyles.title, { color: colors.text }]}>Hybrid Pipeline</Text>
            </View>
            <TouchableOpacity onPress={onClose}>
              <Ionicons name="close" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          <ScrollView style={localStyles.content} showsVerticalScrollIndicator={false}>
            {/* Info Banner */}
            {info && (
              <View style={[localStyles.infoBanner, { backgroundColor: '#EC489915' }]}>
                <Text style={[localStyles.infoText, { color: colors.text }]}>
                  {info.genres_supported?.length} Genres • {info.pipelines_integrated?.length} Pipelines • Complete Game Generation
                </Text>
              </View>
            )}

            {/* Genre Selection */}
            <Text style={[localStyles.sectionTitle, { color: colors.text }]}>Game Genre</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={localStyles.genreRow}>
              {genres.map((g) => (
                <TouchableOpacity
                  key={g.id}
                  style={[
                    localStyles.genreChip,
                    { backgroundColor: genre === g.id ? g.color + '30' : colors.surfaceAlt }
                  ]}
                  onPress={() => setGenre(g.id)}
                >
                  <Ionicons name={g.icon as any} size={18} color={g.color} />
                  <Text style={[localStyles.genreText, { color: genre === g.id ? g.color : colors.text }]}>
                    {g.name}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>

            {/* Scope Selection */}
            <Text style={[localStyles.sectionTitle, { color: colors.text }]}>Game Scope</Text>
            <View style={localStyles.scopeRow}>
              {scopes.map((s) => (
                <TouchableOpacity
                  key={s.id}
                  style={[
                    localStyles.scopeChip,
                    { backgroundColor: scope === s.id ? '#EC4899' : colors.surfaceAlt }
                  ]}
                  onPress={() => setScope(s.id)}
                >
                  <Text style={[localStyles.scopeName, { color: scope === s.id ? '#FFF' : colors.text }]}>
                    {s.name}
                  </Text>
                  <Text style={[localStyles.scopeHours, { color: scope === s.id ? '#FFFC' : colors.textMuted }]}>
                    {s.hours}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            {/* Pipeline Toggles */}
            <Text style={[localStyles.sectionTitle, { color: colors.text }]}>Include Pipelines</Text>
            <View style={localStyles.togglesSection}>
              {[
                { key: 'world', label: 'World Engine', icon: 'globe', state: includeWorld, setter: setIncludeWorld },
                { key: 'narrative', label: 'Narrative', icon: 'book', state: includeNarrative, setter: setIncludeNarrative },
                { key: 'mechanics', label: 'Game Logic', icon: 'game-controller', state: includeMechanics, setter: setIncludeMechanics },
                { key: 'assets', label: 'Assets', icon: 'images', state: includeAssets, setter: setIncludeAssets },
              ].map((toggle) => (
                <View key={toggle.key} style={[localStyles.toggleRow, { backgroundColor: colors.surfaceAlt }]}>
                  <View style={localStyles.toggleLabel}>
                    <Ionicons name={toggle.icon as any} size={20} color={colors.textSecondary} />
                    <Text style={[localStyles.toggleText, { color: colors.text }]}>{toggle.label}</Text>
                  </View>
                  <Switch
                    value={toggle.state}
                    onValueChange={toggle.setter}
                    trackColor={{ false: colors.border, true: '#EC489980' }}
                    thumbColor={toggle.state ? '#EC4899' : colors.textMuted}
                  />
                </View>
              ))}
            </View>

            {/* Concept Input */}
            <Text style={[localStyles.sectionTitle, { color: colors.text }]}>Your Game Concept</Text>
            <TextInput
              style={[localStyles.conceptInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
              placeholder="Describe your dream game in detail... A roguelike dungeon crawler with procedurally generated levels, unique monsters, and a skill-based combat system..."
              placeholderTextColor={colors.textMuted}
              value={concept}
              onChangeText={setConcept}
              multiline
              numberOfLines={5}
            />

            <TouchableOpacity
              style={[localStyles.generateBtn, { backgroundColor: loading ? colors.surfaceAlt : '#EC4899' }]}
              onPress={generate}
              disabled={loading || !concept.trim()}
            >
              {loading ? (
                <ActivityIndicator color="#FFF" />
              ) : (
                <>
                  <Ionicons name="rocket" size={20} color="#FFF" />
                  <Text style={localStyles.generateText}>Generate Complete Game</Text>
                </>
              )}
            </TouchableOpacity>

            {/* Result */}
            {result && (
              <View style={[localStyles.resultSection, { backgroundColor: colors.surfaceAlt }]}>
                <Text style={[localStyles.resultTitle, { color: colors.text }]}>
                  {result.name || 'Generated Game Package'}
                </Text>
                <View style={localStyles.resultMeta}>
                  <Text style={[localStyles.resultMetaText, { color: colors.textMuted }]}>
                    Playtime: {result.estimates?.playtime_hours}hrs • Team: {result.estimates?.team_size} • {result.estimates?.dev_months} months
                  </Text>
                </View>
                <ScrollView style={localStyles.resultScroll} nestedScrollEnabled>
                  <Text style={[localStyles.resultText, { color: colors.text }]}>
                    {JSON.stringify(result.generated_content, null, 2)}
                  </Text>
                </ScrollView>
              </View>
            )}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
});

const localStyles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  modal: { maxHeight: '90%', borderTopLeftRadius: 20, borderTopRightRadius: 20 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1 },
  headerTitle: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  title: { fontSize: 18, fontWeight: '700' },
  content: { padding: 16 },
  infoBanner: { padding: 12, borderRadius: 10, marginBottom: 16 },
  infoText: { fontSize: 13, fontWeight: '600', textAlign: 'center' },
  sectionTitle: { fontSize: 16, fontWeight: '700', marginBottom: 12, marginTop: 8 },
  genreRow: { marginBottom: 16 },
  genreChip: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10, marginRight: 10, gap: 8 },
  genreText: { fontSize: 13, fontWeight: '600' },
  scopeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 },
  scopeChip: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10, alignItems: 'center' },
  scopeName: { fontSize: 14, fontWeight: '600' },
  scopeHours: { fontSize: 11, marginTop: 2 },
  togglesSection: { gap: 8, marginBottom: 16 },
  toggleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 12, borderRadius: 10 },
  toggleLabel: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  toggleText: { fontSize: 14, fontWeight: '600' },
  conceptInput: { padding: 14, borderRadius: 12, borderWidth: 1, fontSize: 14, minHeight: 120, textAlignVertical: 'top', marginBottom: 12 },
  generateBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 14, borderRadius: 12, gap: 10, marginBottom: 16 },
  generateText: { color: '#FFF', fontSize: 16, fontWeight: '700' },
  resultSection: { padding: 14, borderRadius: 12, marginBottom: 20 },
  resultTitle: { fontSize: 16, fontWeight: '700', marginBottom: 8 },
  resultMeta: { marginBottom: 12 },
  resultMetaText: { fontSize: 12 },
  resultScroll: { maxHeight: 250 },
  resultText: { fontSize: 12, lineHeight: 18, fontFamily: 'monospace' },
});
