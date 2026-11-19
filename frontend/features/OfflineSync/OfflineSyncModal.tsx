/**
 * Offline Sync Modal — Download all data for offline use
 */
import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Modal, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { syncAllOfflineData, getCacheStats, clearOfflineCache, fetchManifest } from '../../services/offlineCache';

interface Props { visible: boolean; onClose: () => void; }

export const OfflineSyncModal: React.FC<Props> = ({ visible, onClose }) => {
  const [syncing, setSyncing] = useState(false);
  const [progress, setProgress] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [manifest, setManifest] = useState<any>(null);
  const [result, setResult] = useState<any>(null);

  useEffect(() => {
    if (visible) {
      loadStats();
      loadManifest();
    }
  }, [visible]);

  const loadStats = async () => { setStats(await getCacheStats()); };
  const loadManifest = async () => { setManifest(await fetchManifest()); };

  const startSync = async () => {
    setSyncing(true); setResult(null);
    const res = await syncAllOfflineData((p) => setProgress(p));
    setResult(res);
    setSyncing(false);
    loadStats();
  };

  const handleClear = async () => {
    await clearOfflineCache();
    setStats(await getCacheStats());
    setResult(null);
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <View style={st.container}>
        <View style={st.header}>
          <TouchableOpacity testID="offline-close" onPress={onClose} style={st.hBtn}>
            <Ionicons name="close" size={24} color="#F8FAFC" />
          </TouchableOpacity>
          <Text style={st.hTitle}>Offline Mode</Text>
          <View style={st.hBtn} />
        </View>

        <View style={st.content}>
          {/* Status Card */}
          <View style={[st.statusCard, { borderColor: stats?.isCached ? '#22C55E' : '#F59E0B' }]}>
            <Ionicons name={stats?.isCached ? 'cloud-done' : 'cloud-download'} size={36} color={stats?.isCached ? '#22C55E' : '#F59E0B'} />
            <Text style={st.statusTitle}>{stats?.isCached ? 'Offline Ready' : 'Not Cached'}</Text>
            {stats?.isCached && (
              <Text style={st.statusSub}>{stats.totalDocs.toLocaleString()} documents • {stats.collections} collections</Text>
            )}
            {stats?.cachedAt && (
              <Text style={st.statusDate}>Last sync: {new Date(stats.cachedAt).toLocaleDateString()}</Text>
            )}
          </View>

          {/* Manifest Info */}
          {manifest && (
            <View style={st.manifestCard}>
              <Text style={st.sectionTitle}>AVAILABLE FOR OFFLINE</Text>
              <Text style={st.manifestTotal}>{manifest.total_documents?.toLocaleString()} documents</Text>
              {Object.entries(manifest.collections || {}).slice(0, 8).map(([name, count]) => (
                <View key={name} style={st.collRow}>
                  <Text style={st.collName}>{name.replace(/_/g,' ')}</Text>
                  <Text style={st.collCount}>{(count as number).toLocaleString()}</Text>
                </View>
              ))}
              {Object.keys(manifest.collections || {}).length > 8 && (
                <Text style={st.moreText}>+{Object.keys(manifest.collections).length - 8} more collections</Text>
              )}
            </View>
          )}

          {/* Progress */}
          {syncing && progress && (
            <View style={st.progressCard}>
              <ActivityIndicator color="#3B82F6" />
              <Text style={st.progressTitle}>Syncing: {progress.collection}</Text>
              <Text style={st.progressSub}>
                Collection {progress.collectionIndex + 1}/{progress.totalCollections}
                {' • '}{progress.docProgress.downloaded}/{progress.docProgress.total} docs
              </Text>
              <View style={st.progressBarBg}>
                <View style={[st.progressBarFill, { width: `${progress.docProgress.percentage}%` }]} />
              </View>
            </View>
          )}

          {/* Result */}
          {result && (
            <View style={[st.resultCard, { borderColor: result.success ? '#22C55E' : '#EF4444' }]}>
              <Ionicons name={result.success ? 'checkmark-circle' : 'alert-circle'} size={24} color={result.success ? '#22C55E' : '#EF4444'} />
              <Text style={st.resultText}>
                {result.success ? 'Sync Complete!' : 'Sync had issues'} — {result.documents.toLocaleString()} docs cached
              </Text>
            </View>
          )}

          {/* Actions */}
          <TouchableOpacity
            testID="offline-sync-btn"
            style={[st.syncBtn, syncing && { opacity: 0.5 }]}
            onPress={startSync}
            disabled={syncing}
          >
            <Ionicons name="download" size={20} color="#FFF" />
            <Text style={st.syncBtnText}>{syncing ? 'Syncing...' : 'Download All Data'}</Text>
          </TouchableOpacity>

          {stats?.isCached && (
            <TouchableOpacity style={st.clearBtn} onPress={handleClear}>
              <Ionicons name="trash" size={18} color="#EF4444" />
              <Text style={st.clearBtnText}>Clear Cache</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    </Modal>
  );
};

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F172A' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, backgroundColor: '#1E293B', borderBottomWidth: 1, borderBottomColor: '#334155' },
  hBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  hTitle: { flex: 1, fontSize: 18, fontWeight: '700', color: '#F8FAFC', textAlign: 'center' },
  content: { flex: 1, paddingHorizontal: 16, paddingTop: 16 },
  statusCard: { backgroundColor: '#1E293B', borderRadius: 16, padding: 24, alignItems: 'center', borderWidth: 2 },
  statusTitle: { fontSize: 20, fontWeight: '800', color: '#F8FAFC', marginTop: 12 },
  statusSub: { fontSize: 13, color: '#94A3B8', marginTop: 4 },
  statusDate: { fontSize: 11, color: '#64748B', marginTop: 4 },
  manifestCard: { backgroundColor: '#1E293B', borderRadius: 12, padding: 16, marginTop: 16 },
  sectionTitle: { fontSize: 11, fontWeight: '800', color: '#64748B', letterSpacing: 1.5, marginBottom: 8 },
  manifestTotal: { fontSize: 18, fontWeight: '800', color: '#F59E0B', marginBottom: 12 },
  collRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  collName: { fontSize: 12, color: '#94A3B8', textTransform: 'capitalize' },
  collCount: { fontSize: 12, fontWeight: '700', color: '#F8FAFC' },
  moreText: { fontSize: 11, color: '#64748B', marginTop: 4 },
  progressCard: { backgroundColor: '#1E293B', borderRadius: 12, padding: 16, marginTop: 16, gap: 8 },
  progressTitle: { fontSize: 14, fontWeight: '700', color: '#F8FAFC', textTransform: 'capitalize' },
  progressSub: { fontSize: 12, color: '#94A3B8' },
  progressBarBg: { height: 6, borderRadius: 3, backgroundColor: '#0F172A', overflow: 'hidden' },
  progressBarFill: { height: '100%', borderRadius: 3, backgroundColor: '#3B82F6' },
  resultCard: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: '#1E293B', borderRadius: 12, padding: 14, marginTop: 12, borderWidth: 1 },
  resultText: { flex: 1, fontSize: 13, color: '#F8FAFC' },
  syncBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, backgroundColor: '#3B82F6', borderRadius: 12, paddingVertical: 16, marginTop: 20 },
  syncBtnText: { fontSize: 16, fontWeight: '700', color: '#FFF' },
  clearBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 14, marginTop: 12 },
  clearBtnText: { fontSize: 14, fontWeight: '600', color: '#EF4444' },
});
