import React, { useState, useEffect, useCallback } from 'react';
import { API_BASE } from '../../utils/apiBase';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, Modal,
  ActivityIndicator, SafeAreaView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const API_URL = API_BASE;

const CAT_COLORS: Record<string, string> = {
  gamedev: '#EC4899', web: '#3B82F6', rust: '#F97316', ml: '#8B5CF6',
  devops: '#2563EB', security: '#EF4444', mobile: '#10B981', data: '#F59E0B',
  cs: '#6366F1', algorithms: '#3B82F6', web3: '#D946EF', leadership: '#64748B',
  graphics: '#F97316', python: '#3B82F6', java: '#EF4444', cpp: '#8B5CF6', testing: '#10B981',
};

const STEP_ICONS: Record<string, string> = {
  track: 'school', book: 'book', knowledge_db: 'library',
  quiz: 'bulb', milestone: 'trophy',
};

interface Props { visible: boolean; onClose: () => void; }

export const StudyPathsModal: React.FC<Props> = ({ visible, onClose }) => {
  const [paths, setPaths] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedPath, setSelectedPath] = useState<any>(null);

  const fetchPaths = useCallback(async () => {
    try {
      setLoading(true);
      const res = await apiFetch(`${API_URL}/api/academy/study-paths`);
      const data = await res.json();
      setPaths(data.paths || []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  const fetchPath = useCallback(async (pid: string) => {
    try {
      setLoading(true);
      const res = await apiFetch(`${API_URL}/api/academy/study-path/${pid}`);
      const data = await res.json();
      setSelectedPath(data.path);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (visible) fetchPaths(); }, [visible, fetchPaths]);

  const handleBack = () => {
    if (selectedPath) setSelectedPath(null);
    else onClose();
  };

  const renderPaths = () => (
    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
      <View style={styles.heroCard}>
        <Ionicons name="map" size={40} color="#F59E0B" />
        <Text style={styles.heroTitle}>Study Path Generator</Text>
        <Text style={styles.heroSub}>{paths.length} curated learning journeys</Text>
        <Text style={styles.heroDetail}>Each path chains books, tracks, quizzes, and knowledge bases into a complete curriculum</Text>
      </View>
      {paths.map((p) => {
        const color = CAT_COLORS[p.category] || '#888';
        return (
          <TouchableOpacity key={p.id} testID={`path-${p.id}`} style={[styles.pathCard, { borderLeftColor: color }]} onPress={() => fetchPath(p.id)}>
            <View style={styles.pathTop}>
              <Text style={styles.pathName}>{p.name}</Text>
              <View style={[styles.levelBadge, { backgroundColor: color + '25' }]}>
                <Text style={[styles.levelText, { color }]}>{p.start_level} → {p.end_level}</Text>
              </View>
            </View>
            <Text style={styles.pathDesc} numberOfLines={2}>{p.description}</Text>
            <View style={styles.pathMeta}>
              <View style={styles.pathStat}>
                <Ionicons name="time" size={14} color="#94A3B8" />
                <Text style={styles.pathStatText}>{p.total_hours?.toLocaleString()}h</Text>
              </View>
              <View style={styles.pathStat}>
                <Ionicons name="footsteps" size={14} color="#94A3B8" />
                <Text style={styles.pathStatText}>{p.total_steps} steps</Text>
              </View>
              <View style={styles.pathStat}>
                <Ionicons name="trophy" size={14} color="#F59E0B" />
                <Text style={styles.pathStatText}>{p.milestones} milestones</Text>
              </View>
            </View>
          </TouchableOpacity>
        );
      })}
    </ScrollView>
  );

  const renderPathDetail = () => {
    if (!selectedPath) return null;
    const color = CAT_COLORS[selectedPath.category] || '#888';
    return (
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        <View style={[styles.pathHeader, { borderLeftColor: color, borderLeftWidth: 4 }]}>
          <Text style={styles.pathDetailTitle}>{selectedPath.name}</Text>
          <View style={[styles.levelBadge, { backgroundColor: color + '25', alignSelf: 'flex-start', marginTop: 8 }]}>
            <Text style={[styles.levelText, { color }]}>{selectedPath.start_level} → {selectedPath.end_level}</Text>
          </View>
          <Text style={styles.pathDetailDesc}>{selectedPath.description}</Text>
          <View style={styles.pathDetailStats}>
            <Text style={styles.pathDetailStat}>{selectedPath.total_hours?.toLocaleString()} hours</Text>
            <Text style={styles.pathDetailStat}>{selectedPath.total_steps} steps</Text>
          </View>
        </View>
        <Text style={styles.sectionTitle}>LEARNING PATH</Text>
        {(selectedPath.steps || []).map((step: any, idx: number) => {
          const isMilestone = step.type === 'milestone';
          const icon = STEP_ICONS[step.type] || 'ellipse';
          return (
            <View key={idx} style={[styles.stepCard, isMilestone && styles.milestoneCard]}>
              <View style={styles.stepLine}>
                <View style={[styles.stepDot, { backgroundColor: isMilestone ? '#F59E0B' : color }]}>
                  <Ionicons name={icon as any} size={14} color="#FFF" />
                </View>
                {idx < (selectedPath.steps?.length || 0) - 1 && <View style={styles.stepConnector} />}
              </View>
              <View style={styles.stepContent}>
                <View style={styles.stepTop}>
                  <Text style={[styles.stepTitle, isMilestone && { color: '#F59E0B' }]}>{step.title}</Text>
                  <View style={[styles.typeBadge, { backgroundColor: isMilestone ? '#F59E0B20' : '#33415520' }]}>
                    <Text style={[styles.typeText, { color: isMilestone ? '#F59E0B' : '#94A3B8' }]}>{step.type}</Text>
                  </View>
                </View>
                <Text style={styles.stepDesc}>{step.description}</Text>
                <Text style={styles.stepHours}>{step.hours}h estimated</Text>
              </View>
            </View>
          );
        })}
        <View style={{ height: 40 }} />
      </ScrollView>
    );
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={handleBack}>
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity testID="study-back-btn" onPress={handleBack} style={styles.headerBtn}>
            <Ionicons name={selectedPath ? 'arrow-back' : 'close'} size={24} color="#F8FAFC" />
          </TouchableOpacity>
          <Text style={styles.headerTitle} numberOfLines={1}>{selectedPath ? selectedPath.name : 'Study Paths'}</Text>
          <View style={{ width: 44 }} />
        </View>
        {loading ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color="#F59E0B" />
            <Text style={styles.loadingText}>Loading paths...</Text>
          </View>
        ) : selectedPath ? renderPathDetail() : renderPaths()}
      </SafeAreaView>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F172A' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, backgroundColor: '#1E293B', borderBottomWidth: 1, borderBottomColor: '#334155' },
  headerBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { flex: 1, fontSize: 18, fontWeight: '700', color: '#F8FAFC', textAlign: 'center' },
  content: { flex: 1, paddingHorizontal: 16 },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  loadingText: { color: '#94A3B8', marginTop: 12 },
  heroCard: { alignItems: 'center', padding: 28, backgroundColor: '#1E293B', borderRadius: 16, marginTop: 16, borderWidth: 1, borderColor: '#F59E0B30' },
  heroTitle: { fontSize: 24, fontWeight: '800', color: '#F8FAFC', marginTop: 12 },
  heroSub: { fontSize: 14, color: '#94A3B8', marginTop: 4 },
  heroDetail: { fontSize: 12, color: '#64748B', marginTop: 8, textAlign: 'center', lineHeight: 18 },
  pathCard: { padding: 16, backgroundColor: '#1E293B', borderRadius: 12, marginTop: 10, borderLeftWidth: 4 },
  pathTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  pathName: { fontSize: 16, fontWeight: '700', color: '#F8FAFC', flex: 1, marginRight: 8 },
  levelBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  levelText: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase' },
  pathDesc: { fontSize: 12, color: '#94A3B8', marginTop: 6 },
  pathMeta: { flexDirection: 'row', gap: 16, marginTop: 10 },
  pathStat: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  pathStatText: { fontSize: 11, color: '#94A3B8' },
  pathHeader: { paddingTop: 20, paddingLeft: 12 },
  pathDetailTitle: { fontSize: 22, fontWeight: '800', color: '#F8FAFC' },
  pathDetailDesc: { fontSize: 13, color: '#CBD5E1', marginTop: 8, lineHeight: 20 },
  pathDetailStats: { flexDirection: 'row', gap: 16, marginTop: 12 },
  pathDetailStat: { fontSize: 12, color: '#94A3B8', backgroundColor: '#334155', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  sectionTitle: { fontSize: 12, fontWeight: '700', color: '#64748B', letterSpacing: 1, marginTop: 24, marginBottom: 12 },
  stepCard: { flexDirection: 'row', marginBottom: 4 },
  milestoneCard: {},
  stepLine: { width: 36, alignItems: 'center' },
  stepDot: { width: 28, height: 28, borderRadius: 14, justifyContent: 'center', alignItems: 'center', zIndex: 1 },
  stepConnector: { width: 2, flex: 1, backgroundColor: '#334155', marginTop: -2 },
  stepContent: { flex: 1, paddingLeft: 12, paddingBottom: 16 },
  stepTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  stepTitle: { fontSize: 14, fontWeight: '700', color: '#F8FAFC', flex: 1, marginRight: 8 },
  typeBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4 },
  typeText: { fontSize: 9, fontWeight: '700', textTransform: 'uppercase' },
  stepDesc: { fontSize: 12, color: '#94A3B8', marginTop: 4, lineHeight: 18 },
  stepHours: { fontSize: 11, color: '#3B82F6', marginTop: 4 },
});
