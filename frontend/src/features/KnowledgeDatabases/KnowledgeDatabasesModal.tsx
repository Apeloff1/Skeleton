import React, { useState, useEffect, useCallback } from 'react';
import { API_BASE } from '../../utils/apiBase';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, Modal,
  ActivityIndicator, SafeAreaView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const API_URL = API_BASE;

const DOMAIN_META: Record<string, { icon: string; color: string; label: string }> = {
  cs: { icon: 'code-slash', color: '#3B82F6', label: 'Computer Science' },
  physics: { icon: 'planet', color: '#8B5CF6', label: 'Physics' },
  rendering: { icon: 'color-palette', color: '#EC4899', label: 'Rendering & Skinning' },
  architecture: { icon: 'layers', color: '#F59E0B', label: 'Architecture & Frameworks' },
  computing_history: { icon: 'time', color: '#10B981', label: 'Computing History' },
};

interface Props {
  visible: boolean;
  onClose: () => void;
}

export const KnowledgeDatabasesModal: React.FC<Props> = ({ visible, onClose }) => {
  const [domains, setDomains] = useState<Record<string, any[]>>({});
  const [loading, setLoading] = useState(true);
  const [selectedDomain, setSelectedDomain] = useState<string | null>(null);
  const [domainDetail, setDomainDetail] = useState<any>(null);
  const [selectedEntry, setSelectedEntry] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);

  const fetchDomains = useCallback(async () => {
    try {
      setLoading(true);
      const [domainsRes, statsRes] = await Promise.all([
        apiFetch(`${API_URL}/api/academy/knowledge-dbs`),
        apiFetch(`${API_URL}/api/academy/stats`),
      ]);
      const domainsData = await domainsRes.json();
      const statsData = await statsRes.json();
      setDomains(domainsData.domains || {});
      setStats(statsData);
    } catch (e) {
      console.error('Failed to fetch knowledge databases:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchDomainDetail = useCallback(async (domain: string) => {
    try {
      setLoading(true);
      const res = await apiFetch(`${API_URL}/api/academy/knowledge-db/${domain}`);
      const data = await res.json();
      setDomainDetail(data);
      setSelectedDomain(domain);
    } catch (e) {
      console.error('Failed to fetch domain detail:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (visible) fetchDomains();
  }, [visible, fetchDomains]);

  const handleBack = () => {
    if (selectedEntry) {
      setSelectedEntry(null);
    } else if (selectedDomain) {
      setSelectedDomain(null);
      setDomainDetail(null);
    } else {
      onClose();
    }
  };

  const renderOverview = () => (
    <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
      {stats && (
        <View style={styles.statsBar}>
          <View style={styles.statItem}>
            <Text style={styles.statNum}>{stats.knowledge_databases || 0}</Text>
            <Text style={styles.statLabel}>Fields</Text>
          </View>
          <View style={styles.statItem}>
            <Text style={styles.statNum}>{stats.total_hours?.toLocaleString() || 0}</Text>
            <Text style={styles.statLabel}>Total Hours</Text>
          </View>
          <View style={styles.statItem}>
            <Text style={styles.statNum}>{stats.total_content_items?.toLocaleString() || 0}</Text>
            <Text style={styles.statLabel}>Content Items</Text>
          </View>
        </View>
      )}
      <Text style={styles.sectionTitle}>Knowledge Domains</Text>
      {Object.keys(DOMAIN_META).map((key) => {
        const meta = DOMAIN_META[key];
        const entries = domains[key] || [];
        const hours = entries.reduce((sum: number, e: any) => sum + (e.hours || 0), 0);
        return (
          <TouchableOpacity
            key={key}
            testID={`domain-card-${key}`}
            style={[styles.domainCard, { borderLeftColor: meta.color }]}
            onPress={() => fetchDomainDetail(key)}
          >
            <View style={[styles.domainIcon, { backgroundColor: meta.color + '20' }]}>
              <Ionicons name={meta.icon as any} size={28} color={meta.color} />
            </View>
            <View style={styles.domainInfo}>
              <Text style={styles.domainName}>{meta.label}</Text>
              <Text style={styles.domainStat}>
                {entries.length} fields  |  {hours.toLocaleString()} hours
              </Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color="#6B7280" />
          </TouchableOpacity>
        );
      })}
    </ScrollView>
  );

  const renderDomainDetail = () => {
    if (!domainDetail || !selectedDomain) return null;
    const meta = DOMAIN_META[selectedDomain] || { icon: 'help', color: '#888', label: selectedDomain };
    return (
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        <View style={[styles.domainHeader, { backgroundColor: meta.color + '15' }]}>
          <Ionicons name={meta.icon as any} size={36} color={meta.color} />
          <Text style={[styles.domainHeaderTitle, { color: meta.color }]}>{meta.label}</Text>
          <Text style={styles.domainHeaderStat}>
            {domainDetail.total_entries} entries  |  {domainDetail.total_hours?.toLocaleString()} hours
          </Text>
        </View>
        {Object.entries(domainDetail.data || {}).map(([type, items]: [string, any]) => (
          <View key={type} style={styles.typeSection}>
            <Text style={styles.typeSectionTitle}>{type.replace(/_/g, ' ').toUpperCase()}</Text>
            {(items as any[]).map((item: any) => (
              <TouchableOpacity
                key={item.id}
                testID={`field-${item.id}`}
                style={styles.fieldCard}
                onPress={() => setSelectedEntry(item)}
              >
                <View style={styles.fieldHeader}>
                  <Text style={styles.fieldName}>{item.name || item.title || item.id}</Text>
                  {item.level && (
                    <View style={[styles.levelBadge, { backgroundColor: item.level === 'graduate' ? '#8B5CF6' : item.level === 'advanced' ? '#EF4444' : '#3B82F6' }]}>
                      <Text style={styles.levelText}>{item.level}</Text>
                    </View>
                  )}
                </View>
                {item.hours && <Text style={styles.fieldHours}>{item.hours} hours</Text>}
                {item.description && <Text style={styles.fieldDesc} numberOfLines={2}>{item.description}</Text>}
              </TouchableOpacity>
            ))}
          </View>
        ))}
      </ScrollView>
    );
  };

  const renderEntryDetail = () => {
    if (!selectedEntry) return null;
    return (
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        <View style={styles.entryHeader}>
          <Text style={styles.entryTitle}>{selectedEntry.name || selectedEntry.title}</Text>
          {selectedEntry.level && (
            <View style={[styles.levelBadge, { backgroundColor: '#8B5CF6', alignSelf: 'flex-start', marginTop: 8 }]}>
              <Text style={styles.levelText}>{selectedEntry.level}</Text>
            </View>
          )}
          {selectedEntry.hours && <Text style={styles.entryHours}>{selectedEntry.hours} hours of study</Text>}
          {selectedEntry.description && <Text style={styles.entryDesc}>{selectedEntry.description}</Text>}
        </View>
        {selectedEntry.topics && (
          <View style={styles.topicsSection}>
            <Text style={styles.topicsSectionTitle}>Topics Covered</Text>
            {selectedEntry.topics.map((topic: string, i: number) => (
              <View key={i} style={styles.topicRow}>
                <View style={styles.topicBullet} />
                <Text style={styles.topicText}>{topic}</Text>
              </View>
            ))}
          </View>
        )}
        {selectedEntry.game_applications && (
          <View style={styles.topicsSection}>
            <Text style={[styles.topicsSectionTitle, { color: '#EC4899' }]}>Game Applications</Text>
            {selectedEntry.game_applications.map((app: string, i: number) => (
              <View key={i} style={styles.topicRow}>
                <Ionicons name="game-controller" size={14} color="#EC4899" style={{ marginRight: 8 }} />
                <Text style={styles.topicText}>{app}</Text>
              </View>
            ))}
          </View>
        )}
        {selectedEntry.key_features && (
          <View style={styles.topicsSection}>
            <Text style={styles.topicsSectionTitle}>Key Features</Text>
            {selectedEntry.key_features.map((f: string, i: number) => (
              <View key={i} style={styles.topicRow}>
                <Ionicons name="checkmark-circle" size={14} color="#10B981" style={{ marginRight: 8 }} />
                <Text style={styles.topicText}>{f}</Text>
              </View>
            ))}
          </View>
        )}
        {selectedEntry.entries && (
          <View style={styles.topicsSection}>
            <Text style={styles.topicsSectionTitle}>Timeline</Text>
            {selectedEntry.entries.map((entry: any, i: number) => (
              <View key={i} style={styles.timelineRow}>
                <Text style={styles.timelineYear}>{entry.year}</Text>
                <View style={styles.timelineContent}>
                  <Text style={styles.timelineTitle}>{entry.title}</Text>
                  <Text style={styles.timelineDesc}>{entry.desc}</Text>
                </View>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    );
  };

  const getTitle = () => {
    if (selectedEntry) return selectedEntry.name || selectedEntry.title || 'Detail';
    if (selectedDomain) return DOMAIN_META[selectedDomain]?.label || selectedDomain;
    return 'Knowledge Databases';
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={handleBack}>
      <SafeAreaView style={styles.container}>
        <View style={styles.header}>
          <TouchableOpacity testID="kb-back-btn" onPress={handleBack} style={styles.headerBtn}>
            <Ionicons name={selectedDomain || selectedEntry ? 'arrow-back' : 'close'} size={24} color="#F8FAFC" />
          </TouchableOpacity>
          <Text style={styles.headerTitle} numberOfLines={1}>{getTitle()}</Text>
          <View style={{ width: 44 }} />
        </View>
        {loading ? (
          <View style={styles.loadingContainer}>
            <ActivityIndicator size="large" color="#3B82F6" />
            <Text style={styles.loadingText}>Loading Knowledge...</Text>
          </View>
        ) : selectedEntry ? renderEntryDetail() : selectedDomain ? renderDomainDetail() : renderOverview()}
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
  loadingText: { color: '#94A3B8', marginTop: 12, fontSize: 14 },
  statsBar: { flexDirection: 'row', justifyContent: 'space-around', paddingVertical: 16, marginTop: 16, backgroundColor: '#1E293B', borderRadius: 12 },
  statItem: { alignItems: 'center' },
  statNum: { fontSize: 22, fontWeight: '800', color: '#F8FAFC' },
  statLabel: { fontSize: 11, color: '#94A3B8', marginTop: 2 },
  sectionTitle: { fontSize: 16, fontWeight: '700', color: '#94A3B8', marginTop: 20, marginBottom: 12, letterSpacing: 1 },
  domainCard: { flexDirection: 'row', alignItems: 'center', padding: 16, backgroundColor: '#1E293B', borderRadius: 12, marginBottom: 10, borderLeftWidth: 4 },
  domainIcon: { width: 52, height: 52, borderRadius: 12, justifyContent: 'center', alignItems: 'center', marginRight: 14 },
  domainInfo: { flex: 1 },
  domainName: { fontSize: 16, fontWeight: '700', color: '#F8FAFC' },
  domainStat: { fontSize: 12, color: '#94A3B8', marginTop: 3 },
  domainHeader: { padding: 20, borderRadius: 16, marginTop: 16, alignItems: 'center' },
  domainHeaderTitle: { fontSize: 22, fontWeight: '800', marginTop: 8 },
  domainHeaderStat: { fontSize: 13, color: '#94A3B8', marginTop: 4 },
  typeSection: { marginTop: 20 },
  typeSectionTitle: { fontSize: 13, fontWeight: '700', color: '#64748B', letterSpacing: 1, marginBottom: 10 },
  fieldCard: { padding: 14, backgroundColor: '#1E293B', borderRadius: 10, marginBottom: 8 },
  fieldHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  fieldName: { fontSize: 15, fontWeight: '600', color: '#F8FAFC', flex: 1 },
  levelBadge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  levelText: { fontSize: 10, fontWeight: '700', color: '#FFF', textTransform: 'uppercase' },
  fieldHours: { fontSize: 12, color: '#3B82F6', marginTop: 4 },
  fieldDesc: { fontSize: 12, color: '#94A3B8', marginTop: 4 },
  entryHeader: { paddingTop: 20 },
  entryTitle: { fontSize: 24, fontWeight: '800', color: '#F8FAFC' },
  entryHours: { fontSize: 14, color: '#3B82F6', marginTop: 6 },
  entryDesc: { fontSize: 14, color: '#CBD5E1', marginTop: 8, lineHeight: 22 },
  topicsSection: { marginTop: 24, backgroundColor: '#1E293B', borderRadius: 12, padding: 16 },
  topicsSectionTitle: { fontSize: 14, fontWeight: '700', color: '#3B82F6', marginBottom: 12 },
  topicRow: { flexDirection: 'row', alignItems: 'flex-start', marginBottom: 8 },
  topicBullet: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#3B82F6', marginRight: 10, marginTop: 6 },
  topicText: { fontSize: 14, color: '#E2E8F0', flex: 1, lineHeight: 20 },
  timelineRow: { flexDirection: 'row', marginBottom: 12 },
  timelineYear: { width: 60, fontSize: 12, fontWeight: '700', color: '#F59E0B' },
  timelineContent: { flex: 1 },
  timelineTitle: { fontSize: 14, fontWeight: '600', color: '#F8FAFC' },
  timelineDesc: { fontSize: 12, color: '#94A3B8', marginTop: 2 },
});
