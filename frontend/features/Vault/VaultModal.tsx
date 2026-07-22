/**
 * Vault Browser — View all agent interactions, codeblocks, and learning data
 */

import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  Modal, ActivityIndicator, Platform, Image,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';

import { apiFetch } from '../../utils/apiController';
import { API_BASE } from '../../utils/apiBase';

interface VaultModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
}

interface VaultEntry {
  agent_id: string;
  agent_name: string;
  content: string;
  content_type: string;
  code_blocks: string[];
  metadata: any;
  stored_at: string;
  parsed_by_jeeves: boolean;
  learned_by_jeeves: boolean;
}

export const VaultModal: React.FC<VaultModalProps> = ({ visible, onClose, colors }) => {
  const [entries, setEntries] = useState<VaultEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [unlearned, setUnlearned] = useState(0);
  const [unparsed, setUnparsed] = useState(0);
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [filter, setFilter] = useState<string>('all');
  const [wgWorlds, setWgWorlds] = useState<any[]>([]);
  const [genesisAssets, setGenesisAssets] = useState<any[]>([]);
  const router = useRouter();

  useEffect(() => {
    if (visible) loadVault();
  }, [visible]);

  const loadVault = async () => {
    setLoading(true);
    try {
      const res = await apiFetch(`${API_BASE}/api/agents/vault/code?limit=100`);
      if (res.ok) {
        const data = await res.json();
        setEntries(data.vault_entries || []);
        setTotal(data.total || 0);
        setUnlearned(data.unlearned || 0);
        setUnparsed(data.unparsed || 0);
      }
      const wres = await apiFetch(`${API_BASE}/api/worldforge/worlds?limit=20`);
      if (wres.ok) { const wd = await wres.json(); setWgWorlds(wd.worlds || []); }
      const gres = await apiFetch(`${API_BASE}/api/vault/asset?tag=genesis&limit=100`);
      if (gres.ok) { const gd = await gres.json(); setGenesisAssets(gd.assets || []); }
    } catch {}
    setLoading(false);
  };

  const getTypeColor = (type: string) => {
    const map: Record<string, string> = {
      gdd: '#8B5CF6', world: '#10B981', systems: '#3B82F6', combat: '#EF4444',
      npc: '#3B82F6', narrative: '#F59E0B', graphics: '#EC4899', physics: '#3B82F6',
      audio: '#6366F1', ui: '#F97316', economy: '#84CC16', chat_response: '#8B5CF6',
      compiled_game: '#22C55E', competitor_analysis: '#EF4444', code: '#3B82F6', text: '#6B7280',
    };
    return map[type] || '#6B7280';
  };

  const getTypeIcon = (type: string): any => {
    const map: Record<string, string> = {
      gdd: 'document-text', world: 'globe', systems: 'construct', combat: 'flash',
      npc: 'people', narrative: 'book', graphics: 'color-palette', physics: 'planet',
      audio: 'musical-notes', ui: 'phone-portrait', economy: 'cash', chat_response: 'chatbubble',
      compiled_game: 'build', competitor_analysis: 'eye', code: 'code-slash', text: 'text',
    };
    return map[type] || 'document';
  };

  const filteredEntries = filter === 'all' ? entries : entries.filter(e => {
    if (filter === 'unlearned') return !e.learned_by_jeeves;
    if (filter === 'code') return e.code_blocks && e.code_blocks.length > 0;
    return e.content_type === filter;
  });

  const filters = [
    { id: 'all', label: 'All', count: entries.length },
    { id: 'genesis', label: '🎨 Genesis', count: genesisAssets.length },
    { id: 'unlearned', label: 'Unlearned', count: unlearned },
    { id: 'code', label: 'Has Code', count: entries.filter(e => e.code_blocks?.length > 0).length },
    { id: 'gdd', label: 'GDD', count: entries.filter(e => e.content_type === 'gdd').length },
    { id: 'chat_response', label: 'Chat', count: entries.filter(e => e.content_type === 'chat_response').length },
    { id: 'compiled_game', label: 'Compiled', count: entries.filter(e => e.content_type === 'compiled_game').length },
  ];

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={[styles.overlay, { backgroundColor: colors.background }]}>
        {/* Header */}
        <View style={[styles.header, { borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={onClose} style={styles.backBtn}>
            <Ionicons name="arrow-back" size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerCenter}>
            <Text style={[styles.headerTitle, { color: colors.text }]}>Code Vault</Text>
            <Text style={[styles.headerSub, { color: colors.textMuted }]}>
              {total} entries • {unlearned} unlearned • {unparsed} unparsed
            </Text>
          </View>
          <TouchableOpacity onPress={loadVault} style={styles.refreshBtn}>
            <Ionicons name="refresh" size={20} color={colors.text} />
          </TouchableOpacity>
        </View>

        {loading ? (
          <View style={styles.loadingView}>
            <ActivityIndicator size="large" color="#8B5CF6" />
          </View>
        ) : (
          <>
            {/* Filters */}
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.filterBar} contentContainerStyle={styles.filterContent}>
              {filters.map(f => (
                <TouchableOpacity
                  key={f.id}
                  style={[styles.filterChip, { backgroundColor: filter === f.id ? '#8B5CF630' : colors.surface, borderColor: filter === f.id ? '#8B5CF6' : colors.border }]}
                  onPress={() => setFilter(f.id)}
                >
                  <Text style={[styles.filterText, { color: filter === f.id ? '#8B5CF6' : colors.text }]}>{f.label}</Text>
                  <Text style={[styles.filterCount, { color: filter === f.id ? '#8B5CF6' : colors.textMuted }]}>{f.count}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>

            {wgWorlds.length > 0 ? (
              <TouchableOpacity testID="vault-wg-worlds" onPress={() => { onClose(); router.push('/worldforge' as any); }}
                style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginHorizontal: 12, marginBottom: 4, padding: 14, borderRadius: 12, borderWidth: 1, borderColor: '#16a34a', backgroundColor: '#0d1f1733' }}>
                <Text style={{ fontSize: 22 }}>🌍</Text>
                <View style={{ flex: 1 }}>
                  <Text style={{ color: colors.text, fontWeight: '800', fontSize: 14 }}>Generated Worlds (WG) · {wgWorlds.length}</Text>
                  <Text style={{ color: colors.textMuted, fontSize: 12, marginTop: 2 }} numberOfLines={1}>
                    {wgWorlds.slice(0, 3).map((w: any) => w.name).join(' · ')} — tap to open Worldforge
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color="#16a34a" />
              </TouchableOpacity>
            ) : null}

            {/* Entries */}
            <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
              {filter === 'genesis' ? (
                genesisAssets.length === 0 ? (
                  <View style={styles.emptyView}>
                    <Ionicons name="color-palette" size={48} color={colors.textMuted} />
                    <Text style={[styles.emptyText, { color: colors.textMuted }]}>No generated art yet</Text>
                    <Text style={[styles.emptySub, { color: colors.textMuted }]}>Create assets in Asset Genesis</Text>
                  </View>
                ) : (
                  <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8, padding: 8 }}>
                    {genesisAssets.map((a: any) => (
                      <View key={a.id} testID={`vault-genesis-${a.id}`}
                        style={{ width: '31%', alignItems: 'center', backgroundColor: colors.surface, borderRadius: 10, padding: 6, borderWidth: 1, borderColor: colors.border }}>
                        <Image source={{ uri: `${API_BASE}/api/assets/genesis/${a.id}.png` }}
                          style={{ width: '100%', aspectRatio: 1, borderRadius: 8, backgroundColor: '#0E1626' }} resizeMode="cover" />
                        <Text numberOfLines={1} style={{ color: colors.textMuted, fontSize: 10, marginTop: 4, fontWeight: '600' }}>
                          {a.asset_type || 'asset'}
                        </Text>
                      </View>
                    ))}
                  </View>
                )
              ) : filteredEntries.length === 0 ? (
                <View style={styles.emptyView}>
                  <Ionicons name="lock-closed" size={48} color={colors.textMuted} />
                  <Text style={[styles.emptyText, { color: colors.textMuted }]}>Vault is empty</Text>
                  <Text style={[styles.emptySub, { color: colors.textMuted }]}>Agent interactions will appear here</Text>
                </View>
              ) : (
                filteredEntries.map((entry, idx) => {
                  const isExpanded = expandedIdx === idx;
                  const typeColor = getTypeColor(entry.content_type);
                  return (
                    <TouchableOpacity
                      key={idx}
                      style={[styles.entryCard, { backgroundColor: colors.surface, borderColor: isExpanded ? typeColor + '60' : colors.border }]}
                      onPress={() => setExpandedIdx(isExpanded ? null : idx)}
                      activeOpacity={0.7}
                    >
                      <View style={styles.entryHeader}>
                        <View style={[styles.entryIcon, { backgroundColor: typeColor + '20' }]}>
                          <Ionicons name={getTypeIcon(entry.content_type)} size={16} color={typeColor} />
                        </View>
                        <View style={styles.entryInfo}>
                          <Text style={[styles.entryAgent, { color: colors.text }]}>{entry.agent_name || entry.agent_id}</Text>
                          <Text style={[styles.entryType, { color: typeColor }]}>{entry.content_type}</Text>
                        </View>
                        <View style={styles.entryBadges}>
                          {entry.learned_by_jeeves && (
                            <View style={[styles.badge, { backgroundColor: '#22C55E20' }]}>
                              <Ionicons name="checkmark" size={10} color="#22C55E" />
                            </View>
                          )}
                          {entry.code_blocks?.length > 0 && (
                            <View style={[styles.badge, { backgroundColor: '#3B82F620' }]}>
                              <Text style={styles.badgeText}>{entry.code_blocks.length}</Text>
                            </View>
                          )}
                        </View>
                        <Ionicons name={isExpanded ? 'chevron-up' : 'chevron-down'} size={16} color={colors.textMuted} />
                      </View>

                      {isExpanded && (
                        <View style={styles.entryBody}>
                          <Text style={[styles.entryContent, { color: colors.text }]} numberOfLines={20}>
                            {entry.content?.substring(0, 1500) || 'No content'}
                          </Text>
                          {entry.code_blocks?.length > 0 && (
                            <View style={[styles.codeSection, { backgroundColor: '#0D1117', borderColor: '#21262D' }]}>
                              <Text style={styles.codeSectionTitle}>Code Blocks ({entry.code_blocks.length})</Text>
                              {entry.code_blocks.map((code, ci) => (
                                <Text key={ci} style={styles.codeText} numberOfLines={15}>{code}</Text>
                              ))}
                            </View>
                          )}
                          <View style={styles.entryMeta}>
                            <Text style={[styles.metaText, { color: colors.textMuted }]}>
                              {new Date(entry.stored_at).toLocaleString()}
                            </Text>
                            <Text style={[styles.metaText, { color: entry.learned_by_jeeves ? '#22C55E' : '#EF4444' }]}>
                              {entry.learned_by_jeeves ? 'Learned' : 'Not learned'}
                            </Text>
                          </View>
                        </View>
                      )}
                    </TouchableOpacity>
                  );
                })
              )}
              <View style={{ height: 40 }} />
            </ScrollView>
          </>
        )}
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1 },
  backBtn: { padding: 4 },
  headerCenter: { flex: 1, marginLeft: 12 },
  headerTitle: { fontSize: 18, fontWeight: '700' },
  headerSub: { fontSize: 11, marginTop: 2 },
  refreshBtn: { padding: 8 },
  loadingView: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  filterBar: { maxHeight: 50 },
  filterContent: { paddingHorizontal: 16, paddingVertical: 8, gap: 8 },
  filterChip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 8, borderWidth: 1, marginRight: 6 },
  filterText: { fontSize: 12, fontWeight: '600' },
  filterCount: { fontSize: 10, fontWeight: '700' },
  content: { flex: 1, paddingHorizontal: 16 },
  emptyView: { alignItems: 'center', paddingTop: 80, gap: 8 },
  emptyText: { fontSize: 18, fontWeight: '700' },
  emptySub: { fontSize: 13 },
  entryCard: { borderRadius: 14, borderWidth: 1, marginTop: 8, overflow: 'hidden' },
  entryHeader: { flexDirection: 'row', alignItems: 'center', padding: 12, gap: 10 },
  entryIcon: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  entryInfo: { flex: 1 },
  entryAgent: { fontSize: 13, fontWeight: '700' },
  entryType: { fontSize: 11, fontWeight: '600', marginTop: 1 },
  entryBadges: { flexDirection: 'row', gap: 4 },
  badge: { width: 22, height: 22, borderRadius: 6, justifyContent: 'center', alignItems: 'center' },
  badgeText: { color: '#3B82F6', fontSize: 9, fontWeight: '800' },
  entryBody: { paddingHorizontal: 12, paddingBottom: 12 },
  entryContent: { fontSize: 12, lineHeight: 18 },
  codeSection: { marginTop: 10, padding: 10, borderRadius: 8, borderWidth: 1 },
  codeSectionTitle: { color: '#8B949E', fontSize: 11, fontWeight: '700', marginBottom: 6 },
  codeText: { fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', color: '#E6EDF3', fontSize: 10, lineHeight: 14, marginBottom: 8 },
  entryMeta: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 8 },
  metaText: { fontSize: 10 },
});
