/**
 * Physics Academy Modal v11.6
 * Comprehensive Physics Education for Game Development
 */

import React, { useState, useEffect, memo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput,
  Modal, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';

import { apiFetch } from '../../utils/apiController';
const API_URL = Constants.expoConfig?.extra?.apiUrl || process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface PhysicsAcademyModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
}

type Category = 'classical_mechanics' | 'game_physics' | 'electromagnetism' | 'thermodynamics' | 'quantum_basics' | 'relativity_basics';
type SkillLevel = 'beginner' | 'intermediate' | 'advanced' | 'expert';

export const PhysicsAcademyModal = memo(function PhysicsAcademyModal({
  visible, onClose, colors
}: PhysicsAcademyModalProps) {
  const [selectedCategory, setSelectedCategory] = useState<Category | null>(null);
  const [topic, setTopic] = useState('');
  const [skillLevel, setSkillLevel] = useState<SkillLevel>('intermediate');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [info, setInfo] = useState<any>(null);

  useEffect(() => {
    if (visible) fetchInfo();
  }, [visible]);

  const fetchInfo = async () => {
    try {
      const res = await apiFetch(`${API_URL}/api/physics/info`);
      const data = await res.json();
      setInfo(data);
    } catch (e) {
      console.error('Failed to fetch physics info:', e);
    }
  };

  const categories: { id: Category; name: string; icon: string; color: string }[] = [
    { id: 'classical_mechanics', name: 'Classical Mechanics', icon: 'speedometer', color: '#3B82F6' },
    { id: 'game_physics', name: 'Game Physics', icon: 'game-controller', color: '#8B5CF6' },
    { id: 'electromagnetism', name: 'Electromagnetism', icon: 'flash', color: '#F59E0B' },
    { id: 'thermodynamics', name: 'Thermodynamics', icon: 'flame', color: '#EF4444' },
    { id: 'quantum_basics', name: 'Quantum', icon: 'nuclear', color: '#2563EB' },
    { id: 'relativity_basics', name: 'Relativity', icon: 'planet', color: '#EC4899' },
  ];

  const skillLevels: { id: SkillLevel; name: string }[] = [
    { id: 'beginner', name: 'Beginner' },
    { id: 'intermediate', name: 'Intermediate' },
    { id: 'advanced', name: 'Advanced' },
    { id: 'expert', name: 'Expert' },
  ];

  const learnTopic = async () => {
    if (!topic.trim()) return;
    setLoading(true);
    setResult(null);

    try {
      const res = await apiFetch(`${API_URL}/api/jeeves/teach-physics`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          topic,
          skill_level: skillLevel,
          include_simulation: true,
          game_context: selectedCategory ? `Focus on ${selectedCategory} applications` : null,
          personality: 'encouraging'
        })
      });
      const data = await res.json();
      setResult(data);
    } catch (e) {
      console.error('Physics learning error:', e);
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
              <Ionicons name="nuclear" size={24} color="#3B82F6" />
              <Text style={[localStyles.title, { color: colors.text }]}>Physics Academy</Text>
            </View>
            <TouchableOpacity onPress={onClose}>
              <Ionicons name="close" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          <ScrollView style={localStyles.content} showsVerticalScrollIndicator={false}>
            {/* Info Banner */}
            {info && (
              <View style={[localStyles.infoBanner, { backgroundColor: '#3B82F615' }]}>
                <Text style={[localStyles.infoText, { color: colors.text }]}>
                  {info.total_hours} Hours • {info.total_modules} Modules • {info.simulations?.length} Simulations
                </Text>
              </View>
            )}

            {/* Category Selection */}
            <Text style={[localStyles.sectionTitle, { color: colors.text }]}>Category</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={localStyles.categoryRow}>
              {categories.map((cat) => (
                <TouchableOpacity
                  key={cat.id}
                  style={[
                    localStyles.categoryChip,
                    { backgroundColor: selectedCategory === cat.id ? cat.color + '30' : colors.surfaceAlt }
                  ]}
                  onPress={() => setSelectedCategory(cat.id)}
                >
                  <Ionicons name={cat.icon as any} size={18} color={cat.color} />
                  <Text style={[localStyles.categoryText, { color: selectedCategory === cat.id ? cat.color : colors.text }]}>
                    {cat.name}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>

            {/* Skill Level */}
            <Text style={[localStyles.sectionTitle, { color: colors.text }]}>Your Level</Text>
            <View style={localStyles.levelRow}>
              {skillLevels.map((level) => (
                <TouchableOpacity
                  key={level.id}
                  style={[
                    localStyles.levelChip,
                    { backgroundColor: skillLevel === level.id ? '#3B82F6' : colors.surfaceAlt }
                  ]}
                  onPress={() => setSkillLevel(level.id)}
                >
                  <Text style={[localStyles.levelText, { color: skillLevel === level.id ? '#FFF' : colors.text }]}>
                    {level.name}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            {/* Topic Input */}
            <Text style={[localStyles.sectionTitle, { color: colors.text }]}>What do you want to learn?</Text>
            <TextInput
              style={[localStyles.topicInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
              placeholder="e.g., Collision detection, Rigid body dynamics, Projectile motion..."
              placeholderTextColor={colors.textMuted}
              value={topic}
              onChangeText={setTopic}
              multiline
              numberOfLines={2}
            />

            <TouchableOpacity
              style={[localStyles.learnBtn, { backgroundColor: loading ? colors.surfaceAlt : '#3B82F6' }]}
              onPress={learnTopic}
              disabled={loading || !topic.trim()}
            >
              {loading ? (
                <ActivityIndicator color="#FFF" />
              ) : (
                <>
                  <Ionicons name="school" size={20} color="#FFF" />
                  <Text style={localStyles.learnText}>Learn with Jeeves</Text>
                </>
              )}
            </TouchableOpacity>

            {/* Quick Topics */}
            <Text style={[localStyles.sectionTitle, { color: colors.text }]}>Quick Topics</Text>
            <View style={localStyles.quickTopics}>
              {['Newton\'s Laws', 'Collision Response', 'Verlet Integration', 'Fluid Dynamics', 'Soft Body Physics'].map((t) => (
                <TouchableOpacity
                  key={t}
                  style={[localStyles.quickChip, { backgroundColor: colors.surfaceAlt }]}
                  onPress={() => setTopic(t)}
                >
                  <Text style={[localStyles.quickText, { color: colors.text }]}>{t}</Text>
                </TouchableOpacity>
              ))}
            </View>

            {/* Result */}
            {result && (
              <View style={[localStyles.resultSection, { backgroundColor: colors.surfaceAlt }]}>
                <Text style={[localStyles.resultTitle, { color: colors.text }]}>Lesson: {result.topic}</Text>
                <ScrollView style={localStyles.resultScroll} nestedScrollEnabled>
                  <Text style={[localStyles.resultText, { color: colors.text }]}>
                    {result.lesson}
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
  categoryRow: { marginBottom: 16 },
  categoryChip: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 10, borderRadius: 10, marginRight: 10, gap: 8 },
  categoryText: { fontSize: 13, fontWeight: '600' },
  levelRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 },
  levelChip: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 10 },
  levelText: { fontSize: 14, fontWeight: '600' },
  topicInput: { padding: 14, borderRadius: 12, borderWidth: 1, fontSize: 14, minHeight: 60, textAlignVertical: 'top', marginBottom: 12 },
  learnBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 14, borderRadius: 12, gap: 10, marginBottom: 16 },
  learnText: { color: '#FFF', fontSize: 16, fontWeight: '700' },
  quickTopics: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 },
  quickChip: { paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8 },
  quickText: { fontSize: 13, fontWeight: '500' },
  resultSection: { padding: 14, borderRadius: 12, marginBottom: 20 },
  resultTitle: { fontSize: 14, fontWeight: '700', marginBottom: 10 },
  resultScroll: { maxHeight: 300 },
  resultText: { fontSize: 14, lineHeight: 22 },
});
