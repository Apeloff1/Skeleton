/**
 * Masterclass Modal v11.2.0
 * Complete Coding School - 2860+ Hours
 */

import React, { useState, useEffect } from 'react';
import { API_BASE } from '../../utils/apiBase';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  Modal, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const API_URL = API_BASE;

interface MasterclassModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
}

export const MasterclassModal: React.FC<MasterclassModalProps> = ({
  visible, onClose, colors
}) => {
  const [isLoading, setIsLoading] = useState(true);
  const [tracks, setTracks] = useState<any[]>([]);
  const [selectedTrack, setSelectedTrack] = useState<any>(null);
  const [totalHours, setTotalHours] = useState(0);
  const [certifications, setCertifications] = useState<any[]>([]);
  const [activeTab, setActiveTab] = useState<'tracks' | 'certs'>('tracks');

  useEffect(() => {
    if (visible) {
      loadData();
    }
  }, [visible]);

  const loadData = async () => {
    setIsLoading(true);
    try {
      const [tracksRes, certsRes] = await Promise.all([
        apiFetch(`${API_URL}/api/masterclass/tracks`),
        apiFetch(`${API_URL}/api/masterclass/certifications`)
      ]);
      const tracksData = await tracksRes.json();
      const certsData = await certsRes.json();
      setTracks(tracksData.tracks || []);
      setTotalHours(tracksData.total_hours || 0);
      setCertifications(certsData.certifications || []);
    } catch (error) {
      console.error('Failed to load masterclass:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const loadTrackDetails = async (trackKey: string) => {
    setIsLoading(true);
    try {
      const response = await apiFetch(`${API_URL}/api/masterclass/track/${trackKey}`);
      const data = await response.json();
      setSelectedTrack(data);
    } catch (error) {
      console.error('Failed to load track:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const getLevelColor = (level: string) => {
    if (level.includes('beginner')) return '#10B981';
    if (level.includes('intermediate')) return '#3B82F6';
    if (level.includes('advanced')) return '#F59E0B';
    if (level.includes('expert')) return '#EF4444';
    return colors.primary;
  };

  const renderHeader = () => (
    <View style={[styles.header, { borderBottomColor: colors.border }]}>
      <TouchableOpacity onPress={selectedTrack ? () => setSelectedTrack(null) : onClose} style={styles.backBtn}>
        <Ionicons name={selectedTrack ? "arrow-back" : "close"} size={24} color={colors.text} />
      </TouchableOpacity>
      <View style={styles.headerTitle}>
        <Ionicons name="school" size={24} color="#8B5CF6" />
        <Text style={[styles.title, { color: colors.text }]}>Masterclass</Text>
      </View>
      <View style={{ width: 40 }} />
    </View>
  );

  const renderStats = () => (
    <View style={[styles.statsBar, { backgroundColor: colors.surfaceAlt }]}>
      <View style={styles.statItem}>
        <Text style={[styles.statValue, { color: '#8B5CF6' }]}>{totalHours}+</Text>
        <Text style={[styles.statLabel, { color: colors.textMuted }]}>Hours</Text>
      </View>
      <View style={styles.statItem}>
        <Text style={[styles.statValue, { color: '#10B981' }]}>{tracks.length}</Text>
        <Text style={[styles.statLabel, { color: colors.textMuted }]}>Tracks</Text>
      </View>
      <View style={styles.statItem}>
        <Text style={[styles.statValue, { color: '#F59E0B' }]}>{certifications.length}</Text>
        <Text style={[styles.statLabel, { color: colors.textMuted }]}>Certs</Text>
      </View>
    </View>
  );

  const renderTabs = () => (
    <View style={[styles.tabBar, { backgroundColor: colors.surfaceAlt }]}>
      <TouchableOpacity
        style={[styles.tab, activeTab === 'tracks' && styles.activeTab]}
        onPress={() => setActiveTab('tracks')}
      >
        <Ionicons name="book-outline" size={18} color={activeTab === 'tracks' ? colors.primary : colors.textMuted} />
        <Text style={[styles.tabText, { color: activeTab === 'tracks' ? colors.primary : colors.textMuted }]}>Tracks</Text>
      </TouchableOpacity>
      <TouchableOpacity
        style={[styles.tab, activeTab === 'certs' && styles.activeTab]}
        onPress={() => setActiveTab('certs')}
      >
        <Ionicons name="ribbon-outline" size={18} color={activeTab === 'certs' ? colors.primary : colors.textMuted} />
        <Text style={[styles.tabText, { color: activeTab === 'certs' ? colors.primary : colors.textMuted }]}>Certifications</Text>
      </TouchableOpacity>
    </View>
  );

  const renderTracks = () => (
    <ScrollView style={styles.tracksList} contentContainerStyle={styles.tracksContent}>
      {tracks.map((track) => (
        <TouchableOpacity
          key={track.key}
          style={[styles.trackCard, { backgroundColor: colors.surfaceAlt }]}
          onPress={() => loadTrackDetails(track.key)}
        >
          <View style={styles.trackHeader}>
            <Text style={styles.trackIcon}>{track.icon}</Text>
            <View style={styles.trackInfo}>
              <Text style={[styles.trackName, { color: colors.text }]}>{track.name}</Text>
              <Text style={[styles.trackDesc, { color: colors.textMuted }]}>{track.description}</Text>
            </View>
          </View>
          <View style={styles.trackMeta}>
            <View style={[styles.levelBadge, { backgroundColor: getLevelColor(track.level) + '20' }]}>
              <Text style={[styles.levelText, { color: getLevelColor(track.level) }]}>
                {track.level.replace(/_/g, ' ')}
              </Text>
            </View>
            <View style={styles.trackStats}>
              <Ionicons name="time-outline" size={14} color={colors.textMuted} />
              <Text style={[styles.trackHours, { color: colors.textMuted }]}>{track.total_hours}h</Text>
              <Text style={[styles.trackModules, { color: colors.textMuted }]}>• {track.module_count} modules</Text>
            </View>
          </View>
        </TouchableOpacity>
      ))}
    </ScrollView>
  );

  const renderCertifications = () => (
    <ScrollView style={styles.certsList} contentContainerStyle={styles.certsContent}>
      {certifications.map((cert) => (
        <View key={cert.id} style={[styles.certCard, { backgroundColor: colors.surfaceAlt }]}>
          <Text style={styles.certBadge}>{cert.badge}</Text>
          <View style={styles.certInfo}>
            <Text style={[styles.certName, { color: colors.text }]}>{cert.name}</Text>
            <Text style={[styles.certReq, { color: colors.textMuted }]}>
              Requires {cert.hours_required}+ hours
            </Text>
          </View>
          <View style={[styles.certStatus, { backgroundColor: '#10B98120' }]}>
            <Text style={[styles.certStatusText, { color: '#10B981' }]}>Available</Text>
          </View>
        </View>
      ))}
    </ScrollView>
  );

  const renderTrackDetails = () => {
    if (!selectedTrack) return null;
    return (
      <ScrollView style={styles.trackDetails}>
        <View style={[styles.trackDetailHeader, { backgroundColor: colors.surfaceAlt }]}>
          <Text style={styles.detailIcon}>{selectedTrack.icon}</Text>
          <Text style={[styles.detailName, { color: colors.text }]}>{selectedTrack.name}</Text>
          <Text style={[styles.detailDesc, { color: colors.textMuted }]}>{selectedTrack.description}</Text>
          <View style={styles.detailStats}>
            <View style={styles.detailStat}>
              <Text style={[styles.detailStatValue, { color: colors.primary }]}>{selectedTrack.total_hours}</Text>
              <Text style={[styles.detailStatLabel, { color: colors.textMuted }]}>Hours</Text>
            </View>
            <View style={styles.detailStat}>
              <Text style={[styles.detailStatValue, { color: colors.secondary }]}>{selectedTrack.modules?.length || 0}</Text>
              <Text style={[styles.detailStatLabel, { color: colors.textMuted }]}>Modules</Text>
            </View>
          </View>
        </View>
        
        <Text style={[styles.sectionTitle, { color: colors.textMuted }]}>Modules</Text>
        {selectedTrack.modules?.map((module: any, idx: number) => (
          <View key={module.id || idx} style={[styles.moduleCard, { backgroundColor: colors.surfaceAlt }]}>
            <View style={styles.moduleNumber}>
              <Text style={[styles.moduleNum, { color: colors.primary }]}>{idx + 1}</Text>
            </View>
            <View style={styles.moduleInfo}>
              <Text style={[styles.moduleName, { color: colors.text }]}>{module.name}</Text>
              <Text style={[styles.moduleHours, { color: colors.textMuted }]}>{module.hours} hours • {module.lessons || '?'} lessons</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
          </View>
        ))}
      </ScrollView>
    );
  };

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        {renderHeader()}
        
        {isLoading ? (
          <ActivityIndicator size="large" color={colors.primary} style={styles.loader} />
        ) : selectedTrack ? (
          renderTrackDetails()
        ) : (
          <>
            {renderStats()}
            {renderTabs()}
            {activeTab === 'tracks' ? renderTracks() : renderCertifications()}
          </>
        )}
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
  loader: { flex: 1, justifyContent: 'center' },
  statsBar: { flexDirection: 'row', justifyContent: 'space-around', paddingVertical: 16, marginHorizontal: 16, marginTop: 16, borderRadius: 12 },
  statItem: { alignItems: 'center' },
  statValue: { fontSize: 28, fontWeight: '800' },
  statLabel: { fontSize: 12, marginTop: 4 },
  tabBar: { flexDirection: 'row', marginHorizontal: 16, marginTop: 16, borderRadius: 12, padding: 4 },
  tab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, gap: 6, borderRadius: 10 },
  activeTab: { backgroundColor: 'rgba(139, 92, 246, 0.1)' },
  tabText: { fontSize: 14, fontWeight: '600' },
  tracksList: { flex: 1 },
  tracksContent: { padding: 16, gap: 12 },
  trackCard: { padding: 16, borderRadius: 12 },
  trackHeader: { flexDirection: 'row', gap: 12 },
  trackIcon: { fontSize: 32 },
  trackInfo: { flex: 1 },
  trackName: { fontSize: 16, fontWeight: '700' },
  trackDesc: { fontSize: 13, marginTop: 4, lineHeight: 18 },
  trackMeta: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 12 },
  levelBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  levelText: { fontSize: 11, fontWeight: '600', textTransform: 'capitalize' },
  trackStats: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  trackHours: { fontSize: 12 },
  trackModules: { fontSize: 12 },
  certsList: { flex: 1 },
  certsContent: { padding: 16, gap: 12 },
  certCard: { flexDirection: 'row', alignItems: 'center', padding: 16, borderRadius: 12, gap: 12 },
  certBadge: { fontSize: 32 },
  certInfo: { flex: 1 },
  certName: { fontSize: 16, fontWeight: '700' },
  certReq: { fontSize: 13, marginTop: 2 },
  certStatus: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 12 },
  certStatusText: { fontSize: 12, fontWeight: '600' },
  trackDetails: { flex: 1 },
  trackDetailHeader: { padding: 20, margin: 16, borderRadius: 16, alignItems: 'center' },
  detailIcon: { fontSize: 48 },
  detailName: { fontSize: 22, fontWeight: '800', marginTop: 12 },
  detailDesc: { fontSize: 14, textAlign: 'center', marginTop: 8, lineHeight: 20 },
  detailStats: { flexDirection: 'row', gap: 40, marginTop: 16 },
  detailStat: { alignItems: 'center' },
  detailStatValue: { fontSize: 28, fontWeight: '800' },
  detailStatLabel: { fontSize: 12 },
  sectionTitle: { fontSize: 13, fontWeight: '600', marginHorizontal: 16, marginTop: 16, marginBottom: 8, textTransform: 'uppercase' },
  moduleCard: { flexDirection: 'row', alignItems: 'center', padding: 14, marginHorizontal: 16, marginBottom: 8, borderRadius: 12, gap: 12 },
  moduleNumber: { width: 32, height: 32, borderRadius: 16, backgroundColor: 'rgba(139, 92, 246, 0.1)', justifyContent: 'center', alignItems: 'center' },
  moduleNum: { fontSize: 14, fontWeight: '700' },
  moduleInfo: { flex: 1 },
  moduleName: { fontSize: 15, fontWeight: '600' },
  moduleHours: { fontSize: 12, marginTop: 2 },
});
