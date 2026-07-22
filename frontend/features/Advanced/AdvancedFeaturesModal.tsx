/**
 * Advanced Features Modal v11.0.0
 * Starlog Version Control, Benchmarks, and Formal Verification
 */

import React, { useState, useCallback } from 'react';
import { API_BASE } from '../../utils/apiBase';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput,
  Modal, ActivityIndicator, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
import { toast } from '../../components/Toast';
const API_URL = API_BASE;

interface AdvancedFeaturesModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  currentCode?: string;
  currentLanguage?: string;
}

type FeatureTab = 'starlog' | 'benchmark' | 'verify';

export const AdvancedFeaturesModal: React.FC<AdvancedFeaturesModalProps> = ({
  visible, onClose, colors, currentCode, currentLanguage
}) => {
  const [activeTab, setActiveTab] = useState<FeatureTab>('starlog');
  const [isLoading, setIsLoading] = useState(false);
  
  // Starlog state
  const [commitMessage, setCommitMessage] = useState('');
  const [commitHistory, setCommitHistory] = useState<any[]>([]);
  const [, setCurrentCommit] = useState<string | null>(null);
  
  // Benchmark state
  const [benchmarkResult, setBenchmarkResult] = useState<any>(null);
  const [hardwareProfile, setHardwareProfile] = useState('modern_desktop');
  
  // Verification state
  const [verifyResult, setVerifyResult] = useState<any>(null);
  const [verifyProperty, setVerifyProperty] = useState('');

  const hardwareProfiles = [
    { key: 'modern_desktop', label: '🖥️ Modern Desktop', desc: 'i9-13900K, 64GB DDR5' },
    { key: 'laptop', label: '💻 Laptop', desc: 'M3 MacBook Pro' },
    { key: 'server', label: '🖧 Server', desc: 'Xeon, 256GB RAM' },
    { key: 'embedded', label: '📟 Embedded', desc: 'ARM Cortex-M4' },
    { key: 'mobile', label: '📱 Mobile', desc: 'Snapdragon 8 Gen 3' },
  ];

  const commitCode = useCallback(async () => {
    if (!currentCode?.trim() || !commitMessage.trim()) {
      toast.warn('Need code and a commit message');
      return;
    }

    setIsLoading(true);
    try {
      const response = await apiFetch(`${API_URL}/api/starlog/commit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: currentCode,
          language: currentLanguage || 'python',
          message: commitMessage,
          author: 'CodeDock User',
        }),
      });

      const data = await response.json();
      if (data.commit_id) {
        toast.success(`Commit ${data.commit_id.substring(0,8)} created`);
        setCommitMessage('');
        setCurrentCommit(data.commit_id);
        loadHistory();
      }
    } catch (error: any) {
      toast.error(`Commit failed: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentCode, currentLanguage, commitMessage]);

  const loadHistory = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await apiFetch(`${API_URL}/api/starlog/history?limit=10`);
      const data = await response.json();
      setCommitHistory(data.commits || []);
    } catch (error) {
      console.error('Failed to load history:', error);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const runBenchmark = useCallback(async () => {
    if (!currentCode?.trim()) {
      toast.warn('Need code to benchmark');
      return;
    }

    setIsLoading(true);
    setBenchmarkResult(null);
    try {
      const response = await apiFetch(`${API_URL}/api/benchmark/simulate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: currentCode,
          language: currentLanguage || 'python',
          hardware_profile: hardwareProfile,
          iterations: 1000,
        }),
      });

      const data = await response.json();
      setBenchmarkResult(data);
    } catch (error: any) {
      toast.error(`Benchmark failed: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  }, [currentCode, currentLanguage, hardwareProfile]);

  const runVerification = useCallback(async () => {
    if (!currentCode?.trim()) {
      toast.warn('Need code to verify');
      return;
    }

    setIsLoading(true);
    setVerifyResult(null);
    try {
      const response = await apiFetch(`${API_URL}/api/verify/formal`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: currentCode,
          language: currentLanguage || 'python',
          property: verifyProperty || 'memory_safety',
        }),
      });

      const data = await response.json();
      setVerifyResult(data);
    } catch (error: any) {
      toast.error(`Verification failed: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  }, [currentCode, currentLanguage, verifyProperty]);

  const renderTabs = () => (
    <View style={[styles.tabs, { borderBottomColor: colors.border }]}>
      {[
        { key: 'starlog', label: '⭐ Starlog', icon: 'git-branch-outline' },
        { key: 'benchmark', label: '⚡ Benchmark', icon: 'speedometer-outline' },
        { key: 'verify', label: '✓ Verify', icon: 'shield-checkmark-outline' },
      ].map((tab) => (
        <TouchableOpacity
          key={tab.key}
          style={[
            styles.tab,
            activeTab === tab.key && { borderBottomColor: colors.primary, borderBottomWidth: 2 }
          ]}
          onPress={() => {
            setActiveTab(tab.key as FeatureTab);
            if (tab.key === 'starlog' && commitHistory.length === 0) loadHistory();
          }}
        >
          <Text style={[styles.tabText, { color: activeTab === tab.key ? colors.primary : colors.textSecondary }]}>
            {tab.label}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );

  const renderStarlogTab = () => (
    <ScrollView style={styles.tabContent} showsVerticalScrollIndicator={false}>
      <View style={[styles.section, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>📝 Create Commit</Text>
        <TextInput
          style={[styles.input, { backgroundColor: colors.codeBackground, color: colors.text, borderColor: colors.border }]}
          placeholder="Commit message..."
          placeholderTextColor={colors.textSecondary}
          value={commitMessage}
          onChangeText={setCommitMessage}
          multiline
        />
        <TouchableOpacity
          style={[styles.actionBtn, { backgroundColor: colors.primary }]}
          onPress={commitCode}
          disabled={isLoading || !currentCode}
        >
          {isLoading ? (
            <ActivityIndicator color="#FFF" />
          ) : (
            <>
              <Ionicons name="git-commit" size={18} color="#FFF" />
              <Text style={styles.actionBtnText}>Commit Changes</Text>
            </>
          )}
        </TouchableOpacity>
      </View>

      <Text style={[styles.sectionHeader, { color: colors.text }]}>📜 Commit History</Text>
      {commitHistory.length === 0 ? (
        <View style={[styles.emptyState, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}>
          <Text style={[styles.emptyText, { color: colors.textSecondary }]}>No commits yet</Text>
        </View>
      ) : (
        commitHistory.map((commit, i) => (
          <View key={i} style={[styles.commitCard, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}>
            <View style={styles.commitHeader}>
              <Text style={[styles.commitHash, { color: colors.primary }]}>{commit.commit_id?.substring(0, 8)}</Text>
              <Text style={[styles.commitTime, { color: colors.textSecondary }]}>{commit.timestamp}</Text>
            </View>
            <Text style={[styles.commitMsg, { color: colors.text }]}>{commit.message}</Text>
          </View>
        ))
      )}
    </ScrollView>
  );

  const renderBenchmarkTab = () => (
    <ScrollView style={styles.tabContent} showsVerticalScrollIndicator={false}>
      <View style={[styles.section, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>🎯 Hardware Profile</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.profileScroll}>
          {hardwareProfiles.map((profile) => (
            <TouchableOpacity
              key={profile.key}
              style={[
                styles.profileChip,
                { backgroundColor: hardwareProfile === profile.key ? colors.primary : colors.codeBackground, borderColor: colors.border }
              ]}
              onPress={() => setHardwareProfile(profile.key)}
            >
              <Text style={[styles.profileLabel, { color: hardwareProfile === profile.key ? '#FFF' : colors.text }]}>
                {profile.label}
              </Text>
              <Text style={[styles.profileDesc, { color: hardwareProfile === profile.key ? 'rgba(255,255,255,0.8)' : colors.textSecondary }]}>
                {profile.desc}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        <TouchableOpacity
          style={[styles.actionBtn, { backgroundColor: colors.primary, marginTop: 16 }]}
          onPress={runBenchmark}
          disabled={isLoading || !currentCode}
        >
          {isLoading ? (
            <ActivityIndicator color="#FFF" />
          ) : (
            <>
              <Ionicons name="speedometer" size={18} color="#FFF" />
              <Text style={styles.actionBtnText}>Run Benchmark</Text>
            </>
          )}
        </TouchableOpacity>
      </View>

      {benchmarkResult && (
        <View style={[styles.resultCard, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}>
          <Text style={[styles.resultTitle, { color: colors.text }]}>📊 Benchmark Results</Text>
          
          <View style={styles.metricRow}>
            <View style={styles.metric}>
              <Text style={[styles.metricValue, { color: colors.primary }]}>
                {benchmarkResult.results?.cpu_cycles?.toLocaleString() || 'N/A'}
              </Text>
              <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>CPU Cycles</Text>
            </View>
            <View style={styles.metric}>
              <Text style={[styles.metricValue, { color: colors.primary }]}>
                {benchmarkResult.results?.estimated_time_ms?.toFixed(2) || 'N/A'}ms
              </Text>
              <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>Est. Time</Text>
            </View>
          </View>

          <View style={styles.metricRow}>
            <View style={styles.metric}>
              <Text style={[styles.metricValue, { color: colors.primary }]}>
                {benchmarkResult.results?.cache_misses || 'N/A'}
              </Text>
              <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>Cache Misses</Text>
            </View>
            <View style={styles.metric}>
              <Text style={[styles.metricValue, { color: colors.primary }]}>
                {benchmarkResult.results?.branch_mispredictions || 'N/A'}
              </Text>
              <Text style={[styles.metricLabel, { color: colors.textSecondary }]}>Branch Mispredict</Text>
            </View>
          </View>

          {benchmarkResult.optimizations?.length > 0 && (
            <>
              <Text style={[styles.subTitle, { color: colors.text, marginTop: 12 }]}>💡 Optimization Suggestions</Text>
              {benchmarkResult.optimizations.slice(0, 3).map((opt: string, i: number) => (
                <Text key={i} style={[styles.optText, { color: colors.textSecondary }]}>• {opt}</Text>
              ))}
            </>
          )}
        </View>
      )}
    </ScrollView>
  );

  const renderVerifyTab = () => (
    <ScrollView style={styles.tabContent} showsVerticalScrollIndicator={false}>
      <View style={[styles.section, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>🔍 Verification Property</Text>
        <TextInput
          style={[styles.input, { backgroundColor: colors.codeBackground, color: colors.text, borderColor: colors.border }]}
          placeholder="Property to verify (e.g., memory_safety, type_safety, termination)"
          placeholderTextColor={colors.textSecondary}
          value={verifyProperty}
          onChangeText={setVerifyProperty}
        />

        <TouchableOpacity
          style={[styles.actionBtn, { backgroundColor: colors.primary }]}
          onPress={runVerification}
          disabled={isLoading || !currentCode}
        >
          {isLoading ? (
            <ActivityIndicator color="#FFF" />
          ) : (
            <>
              <Ionicons name="shield-checkmark" size={18} color="#FFF" />
              <Text style={styles.actionBtnText}>Run Formal Verification</Text>
            </>
          )}
        </TouchableOpacity>
      </View>

      {verifyResult && (
        <View style={[styles.resultCard, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}>
          <View style={styles.verifyHeader}>
            <Text style={[styles.resultTitle, { color: colors.text }]}>✅ Verification Result</Text>
            <View style={[
              styles.verifyBadge,
              { backgroundColor: verifyResult.verified ? '#10B981' : '#EF4444' }
            ]}>
              <Text style={styles.verifyBadgeText}>
                {verifyResult.verified ? 'VERIFIED' : 'FAILED'}
              </Text>
            </View>
          </View>

          {verifyResult.proofs?.length > 0 && (
            <>
              <Text style={[styles.subTitle, { color: colors.text }]}>📜 Proofs</Text>
              {verifyResult.proofs.map((proof: any, i: number) => (
                <View key={i} style={[styles.proofCard, { backgroundColor: colors.codeBackground }]}>
                  <Text style={[styles.proofProperty, { color: colors.primary }]}>{proof.property}</Text>
                  <Text style={[styles.proofStatus, { color: proof.status === 'proven' ? '#10B981' : '#EF4444' }]}>
                    {proof.status}
                  </Text>
                </View>
              ))}
            </>
          )}

          {verifyResult.warnings?.length > 0 && (
            <>
              <Text style={[styles.subTitle, { color: colors.text, marginTop: 12 }]}>⚠️ Warnings</Text>
              {verifyResult.warnings.map((warn: string, i: number) => (
                <Text key={i} style={[styles.warnText, { color: '#F59E0B' }]}>• {warn}</Text>
              ))}
            </>
          )}
        </View>
      )}
    </ScrollView>
  );

  return (
    <Modal visible={visible} animationType="slide" transparent={false}>
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <View style={[styles.header, { borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
            <Ionicons name="close" size={24} color={colors.text} />
          </TouchableOpacity>
          <Text style={[styles.title, { color: colors.text }]}>🔬 Advanced Tools</Text>
          <View style={styles.placeholder} />
        </View>

        {renderTabs()}
        
        {activeTab === 'starlog' && renderStarlogTab()}
        {activeTab === 'benchmark' && renderBenchmarkTab()}
        {activeTab === 'verify' && renderVerifyTab()}
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, paddingTop: Platform.OS === 'ios' ? 50 : 30 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1 },
  closeBtn: { padding: 8 },
  title: { fontSize: 20, fontWeight: 'bold' },
  placeholder: { width: 40 },
  tabs: { flexDirection: 'row', borderBottomWidth: 1 },
  tab: { flex: 1, paddingVertical: 12, alignItems: 'center' },
  tabText: { fontSize: 13, fontWeight: '600' },
  tabContent: { flex: 1, padding: 16 },
  section: { padding: 16, borderRadius: 12, borderWidth: 1, marginBottom: 16 },
  sectionTitle: { fontSize: 16, fontWeight: 'bold', marginBottom: 12 },
  sectionHeader: { fontSize: 16, fontWeight: 'bold', marginBottom: 12 },
  input: { borderWidth: 1, borderRadius: 8, padding: 12, fontSize: 14, marginBottom: 12, minHeight: 60, textAlignVertical: 'top' },
  actionBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: 14, borderRadius: 8, gap: 8 },
  actionBtnText: { color: '#FFF', fontSize: 14, fontWeight: '600' },
  emptyState: { padding: 24, borderRadius: 12, borderWidth: 1, alignItems: 'center' },
  emptyText: { fontSize: 14 },
  commitCard: { padding: 12, borderRadius: 10, borderWidth: 1, marginBottom: 8 },
  commitHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 },
  commitHash: { fontSize: 12, fontWeight: '600', fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  commitTime: { fontSize: 11 },
  commitMsg: { fontSize: 14 },
  profileScroll: { marginVertical: 8 },
  profileChip: { padding: 12, borderRadius: 10, marginRight: 8, borderWidth: 1, minWidth: 120 },
  profileLabel: { fontSize: 13, fontWeight: '600' },
  profileDesc: { fontSize: 10, marginTop: 2 },
  resultCard: { padding: 16, borderRadius: 12, borderWidth: 1 },
  resultTitle: { fontSize: 16, fontWeight: 'bold', marginBottom: 12 },
  metricRow: { flexDirection: 'row', marginBottom: 12 },
  metric: { flex: 1, alignItems: 'center' },
  metricValue: { fontSize: 20, fontWeight: 'bold' },
  metricLabel: { fontSize: 11, marginTop: 2 },
  subTitle: { fontSize: 14, fontWeight: '600', marginBottom: 8 },
  optText: { fontSize: 12, marginBottom: 4, lineHeight: 18 },
  verifyHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  verifyBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  verifyBadgeText: { color: '#FFF', fontSize: 11, fontWeight: 'bold' },
  proofCard: { flexDirection: 'row', justifyContent: 'space-between', padding: 10, borderRadius: 6, marginBottom: 6 },
  proofProperty: { fontSize: 12, fontWeight: '500' },
  proofStatus: { fontSize: 12, fontWeight: '600', textTransform: 'uppercase' },
  warnText: { fontSize: 12, marginBottom: 4 },
});

export default AdvancedFeaturesModal;
