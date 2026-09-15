/**
 * Language Track Modal v16.0
 * Shows classes for a specific programming language from the Language Academy
 * Supports repeat class system with achievement tracking
 */

import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  Modal, ActivityIndicator, Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';

import { apiFetch } from '../../utils/apiController';
import { toast } from '../../components/Toast';
const API_BASE = (() => {
  if (typeof window !== 'undefined' && (window as any).location?.origin && !(window as any).location.origin.startsWith('file:')) {
    return (window as any).location.origin.replace(/\/+$/, '');
  }
  return (Constants.expoConfig?.extra?.EXPO_PUBLIC_BACKEND_URL as string)
    || process.env.EXPO_PUBLIC_BACKEND_URL || '';
})();

interface LanguageTrackModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  languageId?: string;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
interface ClassItem {
  class_id: string;
  name: string;
  description: string;
  duration_hours: number;
  level: string;
  topics: string[];
}

interface LanguageData {
  language_id: string;
  name: string;
  greeting: string;
  teaching_style: string;
  core_concepts: string[];
  code_snippets: Record<string, string>;
  best_practices: string[];
  common_mistakes: {mistake: string; fix: string}[];
  difficulty_tips: Record<string, string>;
  ecosystem: string[];
  history_note: string;
}

export const LanguageTrackModal: React.FC<LanguageTrackModalProps> = ({
  visible, onClose, colors, languageId = 'python'
}) => {
  const [languageData, setLanguageData] = useState<LanguageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedLevel, setSelectedLevel] = useState('beginner');
  const [completedClasses, setCompletedClasses] = useState<Record<string, number>>({});

  const levels = ['beginner', 'intermediate', 'advanced', 'expert'];
  const levelColors: Record<string, string> = {
    beginner: '#22C55E',
    intermediate: '#3B82F6', 
    advanced: '#F59E0B',
    expert: '#EF4444'
  };

  useEffect(() => {
    if (visible && languageId) {
      loadLanguageData();
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, languageId]);

  const loadLanguageData = async () => {
    setLoading(true);
    try {
      const res = await apiFetch(`${API_BASE}/api/jeeves-languages/language/${languageId}/teach?level=${selectedLevel}`);
      if (res.ok) {
        const data = await res.json();
        setLanguageData({
          language_id: languageId,
          name: data.language || languageId,
          greeting: data.greeting || '',
          teaching_style: '',
          core_concepts: data.concepts_to_learn || [],
          code_snippets: data.code_examples || {},
          best_practices: data.best_practices || [],
          common_mistakes: data.common_pitfalls || [],
          difficulty_tips: {},
          ecosystem: data.ecosystem || [],
          history_note: '',
        });
      }
    } catch {
      // Fallback data
      setLanguageData({
        language_id: languageId,
        name: languageId.charAt(0).toUpperCase() + languageId.slice(1),
        greeting: `Welcome to the ${languageId} track!`,
        teaching_style: 'Interactive',
        core_concepts: ['Variables & Types', 'Control Flow', 'Functions', 'Data Structures', 'Error Handling', 'Advanced Patterns'],
        code_snippets: {},
        best_practices: ['Write clean code', 'Test your code', 'Read the documentation'],
        common_mistakes: [{mistake: 'Not reading docs', fix: 'Always read the official documentation'}],
        difficulty_tips: {},
        ecosystem: [],
        history_note: '',
      });
    }
    setLoading(false);
  };

  const handleCompleteClass = async (conceptIndex: number) => {
    const classId = `${languageId}_concept_${conceptIndex}`;
    const className = languageData?.core_concepts[conceptIndex] || `Class ${conceptIndex}`;
    const currentCount = completedClasses[classId] || 0;

    try {
      const res = await apiFetch(`${API_BASE}/api/class-progress/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: 'default_user',
          class_id: classId,
          class_name: className,
          language_id: languageId,
          category: 'language',
          score: Math.floor(Math.random() * 30) + 70,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        setCompletedClasses(prev => ({ ...prev, [classId]: data.completion_count }));
        
        if (data.new_achievements && data.new_achievements.length > 0) {
          const achNames = data.new_achievements.map((a: any) => a.name).join(', ');
          Alert.alert(
            'Achievement Unlocked!', 
            `${data.message}\n\nNew: ${achNames}`,
            [{ text: 'Awesome!', style: 'default' }]
          );
        } else {
          Alert.alert('Class Complete!', data.message);
        }
      }
    } catch {
      setCompletedClasses(prev => ({ ...prev, [classId]: currentCount + 1 }));
      toast.info(`Completed ${currentCount + 1} time(s)`);
    }
  };

  const getRepeatBadge = (count: number) => {
    if (count >= 10) return { text: 'LEGENDARY', color: '#EF4444' };
    if (count >= 5) return { text: 'EPIC', color: '#EC4899' };
    if (count >= 3) return { text: 'MASTERED', color: '#F59E0B' };
    if (count >= 2) return { text: 'REPEATED', color: '#8B5CF6' };
    if (count >= 1) return { text: 'DONE', color: '#22C55E' };
    return null;
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={[styles.overlay, { backgroundColor: colors.background }]}>
        {/* Header */}
        <View style={[styles.header, { borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={onClose} style={styles.backBtn}>
            <Ionicons name="arrow-back" size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerCenter}>
            <Text style={[styles.headerTitle, { color: colors.text }]}>
              {languageData?.name || languageId} Track
            </Text>
            <Text style={[styles.headerSub, { color: colors.textMuted }]}>
              Language Academy
            </Text>
          </View>
          <View style={[styles.badge, { backgroundColor: levelColors[selectedLevel] + '20' }]}>
            <Ionicons name="school" size={16} color={levelColors[selectedLevel]} />
          </View>
        </View>

        {loading ? (
          <View style={styles.loadingView}>
            <ActivityIndicator size="large" color={colors.primary} />
            <Text style={[styles.loadingText, { color: colors.textMuted }]}>Loading curriculum...</Text>
          </View>
        ) : (
          <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
            {/* Greeting */}
            <View style={[styles.greetingCard, { backgroundColor: colors.primary + '15', borderColor: colors.primary + '30' }]}>
              <Ionicons name="chatbubbles" size={20} color={colors.primary} />
              <Text style={[styles.greetingText, { color: colors.text }]}>
                {languageData?.greeting}
              </Text>
            </View>

            {/* Level Selector */}
            <View style={styles.levelRow}>
              {levels.map(level => (
                <TouchableOpacity
                  key={level}
                  style={[
                    styles.levelBtn,
                    { backgroundColor: selectedLevel === level ? levelColors[level] + '20' : colors.surface,
                      borderColor: selectedLevel === level ? levelColors[level] : colors.border }
                  ]}
                  onPress={() => { setSelectedLevel(level); loadLanguageData(); }}
                >
                  <Text style={[
                    styles.levelText,
                    { color: selectedLevel === level ? levelColors[level] : colors.textMuted }
                  ]}>
                    {level.charAt(0).toUpperCase() + level.slice(1)}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            {/* Core Concepts / Classes */}
            <Text style={[styles.sectionTitle, { color: colors.text }]}>Classes</Text>
            {languageData?.core_concepts.map((concept, idx) => {
              const classId = `${languageId}_concept_${idx}`;
              const count = completedClasses[classId] || 0;
              const badge = getRepeatBadge(count);
              
              return (
                <View key={idx} style={[styles.classCard, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                  <View style={styles.classHeader}>
                    <View style={[styles.classIcon, { backgroundColor: levelColors[selectedLevel] + '15' }]}>
                      <Ionicons name="book" size={18} color={levelColors[selectedLevel]} />
                    </View>
                    <View style={styles.classInfo}>
                      <Text style={[styles.className, { color: colors.text }]}>{concept}</Text>
                      <View style={styles.classMetaRow}>
                        <Text style={[styles.classMeta, { color: colors.textMuted }]}>
                          Class {idx + 1} of {languageData.core_concepts.length}
                        </Text>
                        {count > 0 && (
                          <Text style={[styles.classMeta, { color: colors.textMuted }]}>
                            Completed {count}x
                          </Text>
                        )}
                      </View>
                    </View>
                    {badge && (
                      <View style={[styles.repeatBadge, { backgroundColor: badge.color + '20' }]}>
                        <Text style={[styles.repeatBadgeText, { color: badge.color }]}>{badge.text}</Text>
                      </View>
                    )}
                  </View>
                  <TouchableOpacity
                    style={[styles.startBtn, { backgroundColor: count > 0 ? '#8B5CF6' : levelColors[selectedLevel] }]}
                    onPress={() => handleCompleteClass(idx)}
                  >
                    <Ionicons name={count > 0 ? 'refresh' : 'play'} size={16} color="#FFF" />
                    <Text style={styles.startBtnText}>
                      {count > 0 ? `Repeat (${count}x)` : 'Start Class'}
                    </Text>
                  </TouchableOpacity>
                </View>
              );
            })}

            {/* Best Practices */}
            <Text style={[styles.sectionTitle, { color: colors.text }]}>Best Practices</Text>
            {languageData?.best_practices.map((practice, idx) => (
              <View key={idx} style={[styles.practiceItem, { backgroundColor: colors.surface, borderColor: colors.border }]}>
                <Ionicons name="checkmark-circle" size={18} color="#22C55E" />
                <Text style={[styles.practiceText, { color: colors.text }]}>{practice}</Text>
              </View>
            ))}

            {/* Common Mistakes */}
            {languageData?.common_mistakes && languageData.common_mistakes.length > 0 && (
              <>
                <Text style={[styles.sectionTitle, { color: colors.text }]}>Common Mistakes</Text>
                {languageData.common_mistakes.map((item, idx) => (
                  <View key={idx} style={[styles.mistakeCard, { backgroundColor: '#EF444415', borderColor: '#EF444430' }]}>
                    <View style={styles.mistakeRow}>
                      <Ionicons name="close-circle" size={16} color="#EF4444" />
                      <Text style={[styles.mistakeText, { color: colors.text }]}>{item.mistake}</Text>
                    </View>
                    <View style={styles.mistakeRow}>
                      <Ionicons name="checkmark-circle" size={16} color="#22C55E" />
                      <Text style={[styles.fixText, { color: colors.textMuted }]}>{item.fix}</Text>
                    </View>
                  </View>
                ))}
              </>
            )}

            {/* Ecosystem */}
            {languageData?.ecosystem && languageData.ecosystem.length > 0 && (
              <>
                <Text style={[styles.sectionTitle, { color: colors.text }]}>Ecosystem</Text>
                <View style={styles.tagRow}>
                  {languageData.ecosystem.map((tool, idx) => (
                    <View key={idx} style={[styles.tag, { backgroundColor: colors.primary + '15' }]}>
                      <Text style={[styles.tagText, { color: colors.primary }]}>{tool}</Text>
                    </View>
                  ))}
                </View>
              </>
            )}

            <View style={{ height: 40 }} />
          </ScrollView>
        )}
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: { flex: 1 },
  header: {
    flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16,
    paddingVertical: 14, borderBottomWidth: 1,
  },
  backBtn: { padding: 4 },
  headerCenter: { flex: 1, marginLeft: 12 },
  headerTitle: { fontSize: 18, fontWeight: '700' },
  headerSub: { fontSize: 12, marginTop: 2 },
  badge: { width: 36, height: 36, borderRadius: 18, justifyContent: 'center', alignItems: 'center' },
  loadingView: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { marginTop: 12, fontSize: 14 },
  content: { flex: 1, paddingHorizontal: 16 },
  greetingCard: {
    flexDirection: 'row', alignItems: 'center', padding: 14, borderRadius: 12,
    marginTop: 16, gap: 10, borderWidth: 1,
  },
  greetingText: { flex: 1, fontSize: 14, lineHeight: 20 },
  levelRow: { flexDirection: 'row', gap: 8, marginTop: 16 },
  levelBtn: {
    flex: 1, paddingVertical: 10, borderRadius: 10, alignItems: 'center',
    borderWidth: 1,
  },
  levelText: { fontSize: 12, fontWeight: '600' },
  sectionTitle: { fontSize: 16, fontWeight: '700', marginTop: 20, marginBottom: 10 },
  classCard: {
    borderRadius: 12, padding: 14, marginBottom: 10, borderWidth: 1,
  },
  classHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 },
  classIcon: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  classInfo: { flex: 1 },
  className: { fontSize: 15, fontWeight: '600' },
  classMetaRow: { flexDirection: 'row', gap: 12, marginTop: 2 },
  classMeta: { fontSize: 12 },
  repeatBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 8 },
  repeatBadgeText: { fontSize: 10, fontWeight: '800' },
  startBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: 10, borderRadius: 10, gap: 6,
  },
  startBtnText: { color: '#FFF', fontSize: 14, fontWeight: '600' },
  practiceItem: {
    flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12,
    borderRadius: 10, marginBottom: 6, borderWidth: 1,
  },
  practiceText: { flex: 1, fontSize: 14 },
  mistakeCard: { padding: 12, borderRadius: 10, marginBottom: 8, borderWidth: 1 },
  mistakeRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 },
  mistakeText: { flex: 1, fontSize: 14, fontWeight: '500' },
  fixText: { flex: 1, fontSize: 13 },
  tagRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  tag: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8 },
  tagText: { fontSize: 13, fontWeight: '600' },
});
