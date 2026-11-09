/**
 * SOTA Extended Modal v11.6
 * 15+ Bleeding Edge Features - April 2026
 */

import React, { useState, useEffect, memo } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  Modal, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';

import { apiFetch } from '../../utils/apiController';
const API_URL = Constants.expoConfig?.extra?.apiUrl || process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface SOTAExtendedModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
}

type Priority = 'high' | 'medium' | 'low';

export const SOTAExtendedModal = memo(function SOTAExtendedModal({
  visible, onClose, colors
}: SOTAExtendedModalProps) {
  const [selectedPriority, setSelectedPriority] = useState<Priority>('high');
  const [loading, setLoading] = useState(false);
  const [info, setInfo] = useState<any>(null);
  const [upgrades, setUpgrades] = useState<any>(null);
  const [activeUpgrade, setActiveUpgrade] = useState<any>(null);
  const [applying, setApplying] = useState(false);

  useEffect(() => {
    if (visible) {
      fetchInfo();
      fetchUpgrades();
    }
  }, [visible]);

  const fetchInfo = async () => {
    try {
      const res = await apiFetch(`${API_URL}/api/sota-extended/info`);
      const data = await res.json();
      setInfo(data);
    } catch (e) {
      console.error('Failed to fetch SOTA extended info:', e);
    }
  };

  const fetchUpgrades = async () => {
    setLoading(true);
    try {
      const res = await apiFetch(`${API_URL}/api/sota-extended/upgrades`);
      const data = await res.json();
      setUpgrades(data);
    } catch (e) {
      console.error('Failed to fetch upgrades:', e);
    } finally {
      setLoading(false);
    }
  };

  const applyUpgrade = async (upgradeId: string) => {
    setApplying(true);
    try {
      const res = await apiFetch(`${API_URL}/api/sota-extended/apply/${upgradeId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      const data = await res.json();
      setActiveUpgrade(data);
    } catch (e) {
      console.error('Failed to apply upgrade:', e);
    } finally {
      setApplying(false);
    }
  };

  const priorities: { id: Priority; name: string; color: string; icon: string }[] = [
    { id: 'high', name: 'High Priority', color: '#EF4444', icon: 'flash' },
    { id: 'medium', name: 'Medium', color: '#F59E0B', icon: 'time' },
    { id: 'low', name: 'Low', color: '#10B981', icon: 'leaf' },
  ];

  const getCurrentUpgrades = () => {
    if (!upgrades) return [];
    switch (selectedPriority) {
      case 'high': return Object.values(upgrades.high_priority || {});
      case 'medium': return upgrades.medium_priority || [];
      case 'low': return upgrades.low_priority || [];
      default: return [];
    }
  };

  const getCategoryColor = (category: string) => {
    const categoryColors: Record<string, string> = {
      'ai_assistance': '#8B5CF6',
      'code_quality': '#10B981',
      'ai_infrastructure': '#3B82F6',
      'search': '#2563EB',
      'testing': '#F59E0B',
      'performance': '#EC4899',
      'security': '#EF4444',
      'documentation': '#6366F1',
      'design': '#3B82F6',
      'database': '#F97316',
      'infrastructure': '#64748B',
      'collaboration': '#A855F7',
    };
    return categoryColors[category] || '#6B7280';
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={localStyles.overlay}>
        <View style={[localStyles.modal, { backgroundColor: colors.surface }]}>
          {/* Header */}
          <View style={[localStyles.header, { borderBottomColor: colors.border }]}>
            <View style={localStyles.headerTitle}>
              <Ionicons name="flash" size={24} color="#F59E0B" />
              <Text style={[localStyles.title, { color: colors.text }]}>SOTA Extended v11.6</Text>
            </View>
            <TouchableOpacity onPress={onClose}>
              <Ionicons name="close" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          <ScrollView style={localStyles.content} showsVerticalScrollIndicator={false}>
            {/* Info Banner */}
            {info && (
              <View style={[localStyles.infoBanner, { backgroundColor: '#F59E0B15' }]}>
                <Text style={[localStyles.infoText, { color: colors.text }]}>
                  {info.total_upgrades} Upgrades • {info.high_priority} High Priority • {info.categories?.length} Categories
                </Text>
              </View>
            )}

            {/* Priority Tabs */}
            <View style={localStyles.priorityTabs}>
              {priorities.map((p) => (
                <TouchableOpacity
                  key={p.id}
                  style={[
                    localStyles.priorityTab,
                    { backgroundColor: selectedPriority === p.id ? p.color + '20' : colors.surfaceAlt }
                  ]}
                  onPress={() => setSelectedPriority(p.id)}
                >
                  <Ionicons name={p.icon as any} size={16} color={p.color} />
                  <Text style={[localStyles.priorityText, { color: selectedPriority === p.id ? p.color : colors.text }]}>
                    {p.name}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            {/* Upgrades List */}
            {loading ? (
              <ActivityIndicator size="large" color="#F59E0B" style={{ marginTop: 40 }} />
            ) : (
              <View style={localStyles.upgradesList}>
                {getCurrentUpgrades().map((upgrade: any, index: number) => (
                  <TouchableOpacity
                    key={upgrade.id || index}
                    style={[localStyles.upgradeCard, { backgroundColor: colors.surfaceAlt }]}
                    onPress={() => applyUpgrade(upgrade.id)}
                    disabled={applying}
                  >
                    <View style={localStyles.upgradeHeader}>
                      <View style={[
                        localStyles.categoryBadge,
                        { backgroundColor: getCategoryColor(upgrade.category) + '20' }
                      ]}>
                        <Text style={[localStyles.categoryText, { color: getCategoryColor(upgrade.category) }]}>
                          {upgrade.category?.replace('_', ' ')}
                        </Text>
                      </View>
                      {upgrade.version && (
                        <Text style={[localStyles.versionText, { color: colors.textMuted }]}>
                          v{upgrade.version}
                        </Text>
                      )}
                    </View>
                    <Text style={[localStyles.upgradeName, { color: colors.text }]}>
                      {upgrade.name}
                    </Text>
                    <Text style={[localStyles.upgradeDesc, { color: colors.textMuted }]} numberOfLines={2}>
                      {upgrade.description}
                    </Text>
                    {upgrade.features && (
                      <View style={localStyles.featuresList}>
                        {upgrade.features.slice(0, 3).map((feature: string, i: number) => (
                          <View key={i} style={localStyles.featureItem}>
                            <Ionicons name="checkmark-circle" size={12} color="#10B981" />
                            <Text style={[localStyles.featureText, { color: colors.textSecondary }]}>
                              {feature}
                            </Text>
                          </View>
                        ))}
                      </View>
                    )}
                    <View style={[localStyles.applyBtn, { backgroundColor: '#F59E0B20' }]}>
                      <Text style={[localStyles.applyText, { color: '#F59E0B' }]}>Activate</Text>
                      <Ionicons name="arrow-forward" size={16} color="#F59E0B" />
                    </View>
                  </TouchableOpacity>
                ))}
              </View>
            )}

            {/* Active Upgrade Result */}
            {activeUpgrade && (
              <View style={[localStyles.resultSection, { backgroundColor: '#10B98120' }]}>
                <View style={localStyles.resultHeader}>
                  <Ionicons name="checkmark-circle" size={24} color="#10B981" />
                  <Text style={[localStyles.resultTitle, { color: colors.text }]}>
                    {activeUpgrade.upgrade?.name} Activated!
                  </Text>
                </View>
                <Text style={[localStyles.resultMessage, { color: colors.textSecondary }]}>
                  {activeUpgrade.message}
                </Text>
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
  priorityTabs: { flexDirection: 'row', gap: 8, marginBottom: 16 },
  priorityTab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 12, borderRadius: 10, gap: 6 },
  priorityText: { fontSize: 12, fontWeight: '600' },
  upgradesList: { gap: 12 },
  upgradeCard: { padding: 16, borderRadius: 12 },
  upgradeHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  categoryBadge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 6 },
  categoryText: { fontSize: 11, fontWeight: '600', textTransform: 'capitalize' },
  versionText: { fontSize: 11 },
  upgradeName: { fontSize: 16, fontWeight: '700', marginBottom: 4 },
  upgradeDesc: { fontSize: 13, lineHeight: 18, marginBottom: 10 },
  featuresList: { gap: 4, marginBottom: 12 },
  featureItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  featureText: { fontSize: 12 },
  applyBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, borderRadius: 8, gap: 6 },
  applyText: { fontSize: 14, fontWeight: '600' },
  resultSection: { padding: 16, borderRadius: 12, marginTop: 16, marginBottom: 20 },
  resultHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 },
  resultTitle: { fontSize: 16, fontWeight: '700' },
  resultMessage: { fontSize: 14 },
});
