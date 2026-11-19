/**
 * UnifiedVault — the single mirrored vault view used by EVERY vault screen.
 *
 * Reads GET /api/gameforge/studio/vault/unified which aggregates the canonical
 * Boardroom (encrypted) vault + the agent code_vault + Worldforge artifacts, so
 * every vault surface in the app shows the exact same list.
 *
 * Tapping an entry opens a detail console: view content, DOWNLOAD to device,
 * (boardroom) browse version history + rollback, and FETCH the artifact INTO
 * another system (gamefiles / Jeeves knowledge) so work can continue there.
 */
import React from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator,
  RefreshControl, Modal, Image,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import api from '../utils/apiClient';
import {
  downloadToDevice, fetchBoardroomContent, fetchBoardroomVersions,
  rollbackVault, fetchToSystem, fetchMonograph,
} from '../utils/vaultActions';

const GREEN = '#22c55e';
const BLUE = '#3b82f6';
const PURPLE = '#a78bfa';
const AMBER = '#f59e0b';
const RED = '#ef4444';
const CARD = '#111827';
const BG = '#0b1220';
const MUTE = '#94a3b8';

const SOURCE_META: Record<string, { label: string; color: string; icon: any }> = {
  boardroom: { label: 'Boardroom', color: GREEN, icon: 'lock-closed' },
  agents: { label: 'Agents', color: BLUE, icon: 'people' },
  worldforge: { label: 'Worldforge', color: PURPLE, icon: 'planet' },
};

type Item = {
  id: string; name: string; source: string; kind: string;
  detail?: string; created_at?: number | string; encrypted?: boolean; image?: string;
};

export default function UnifiedVault({ embedded = false, onContinueInBuild }: { embedded?: boolean; onContinueInBuild?: () => void }) {
  const router = useRouter();
  const [items, setItems] = React.useState<Item[]>([]);
  const [counts, setCounts] = React.useState<Record<string, number>>({});
  const [loading, setLoading] = React.useState(true);
  const [refreshing, setRefreshing] = React.useState(false);
  const [filter, setFilter] = React.useState<'all' | 'boardroom' | 'agents' | 'worldforge'>('all');

  // detail modal
  const [sel, setSel] = React.useState<Item | null>(null);
  const [content, setContent] = React.useState('');
  const [versions, setVersions] = React.useState<any[]>([]);
  const [detailBusy, setDetailBusy] = React.useState(false);
  const [actionMsg, setActionMsg] = React.useState('');
  const [fetchedGamefiles, setFetchedGamefiles] = React.useState(false);

  const load = React.useCallback(async () => {
    const r = await api.get<any>('/api/gameforge/studio/vault/unified?limit=80', { timeoutMs: 20000 });
    if (r.ok && r.data?.ok) {
      setItems(r.data.items || []);
      setCounts(r.data.counts || {});
    }
    setLoading(false);
    setRefreshing(false);
  }, []);

  React.useEffect(() => { load(); }, [load]);

  const openItem = async (it: Item) => {
    setSel(it); setContent(''); setVersions([]); setActionMsg(''); setDetailBusy(true);
    try {
      if (it.source === 'boardroom') {
        const [c, v] = await Promise.all([fetchBoardroomContent(it.id), fetchBoardroomVersions(it.id)]);
        if (c.ok) setContent(c.data?.content || (c.data?.content_base64 ? '[binary file — download to view]' : ''));
        if (v.ok) setVersions(v.data?.versions || []);
      } else if (it.source === 'worldforge' && it.kind === 'monograph') {
        const m = await fetchMonograph(it.id);
        if (m.ok) setContent(m.data?.monograph || m.data?.body || '(no text)');
      }
    } finally { setDetailBusy(false); }
  };

  const closeItem = () => { setSel(null); setContent(''); setVersions([]); setActionMsg(''); setFetchedGamefiles(false); };

  const doDownload = async () => {
    if (!sel) return;
    setActionMsg('Downloading…');
    const r = await downloadToDevice(sel.id, sel.name);
    setActionMsg(r.ok ? 'Download started.' : `Download failed: ${r.error || ''}`);
  };

  const doRollback = async (toVersion: number) => {
    if (!sel) return;
    setDetailBusy(true); setActionMsg('Rolling back…');
    const r = await rollbackVault(sel.id, toVersion);
    if (r.ok && r.data?.ok) {
      setActionMsg(`Restored v${toVersion} as new latest (v${r.data.new_version}).`);
      await openItem(sel); await load();
    } else setActionMsg(r.status === 401 || r.status === 403 ? 'Admin required to rollback.' : 'Rollback failed.');
    setDetailBusy(false);
  };

  const doFetchTo = async (system: 'gamefiles' | 'knowledge') => {
    if (!sel) return;
    setDetailBusy(true); setActionMsg(`Sending to ${system}…`);
    const r = await fetchToSystem(sel.id, system);
    if (r.ok && r.data?.ok) {
      if (system === 'gamefiles') {
        setFetchedGamefiles(true);
        setActionMsg(`Loaded into build gamefiles (${r.data.filename}). Continue in Build/Forge.`);
      } else setActionMsg(`Fed into Jeeves knowledge (${r.data.topic}).`);
    } else setActionMsg(r.status === 401 || r.status === 403 ? 'Editor role required.' : 'Send failed.');
    setDetailBusy(false);
  };

  const continueInBuild = () => {
    closeItem();
    if (onContinueInBuild) onContinueInBuild();
    else router.push('/gameforge-studio');
  };

  const shown = filter === 'all' ? items : items.filter((i) => i.source === filter);
  const total = items.length;

  const Chip = ({ id, label }: { id: typeof filter; label: string }) => (
    <TouchableOpacity testID={`vault-filter-${id}`} style={[st.chip, filter === id && st.chipActive]} onPress={() => setFilter(id)}>
      <Text style={[st.chipTxt, filter === id && st.chipTxtActive]}>{label}</Text>
    </TouchableOpacity>
  );

  const body = (
    <>
      <View style={st.statRow}>
        <Stat label="Total" value={`${total}`} color={GREEN} />
        <Stat label="Boardroom" value={`${counts.boardroom ?? 0}`} color={GREEN} />
        <Stat label="Agents" value={`${counts.agents ?? 0}`} color={BLUE} />
        <Stat label="Worldforge" value={`${counts.worldforge ?? 0}`} color={PURPLE} />
      </View>

      <View style={st.chipRow}>
        <Chip id="all" label={`All (${total})`} />
        <Chip id="boardroom" label={`🔒 Boardroom (${counts.boardroom ?? 0})`} />
        <Chip id="agents" label={`Agents (${counts.agents ?? 0})`} />
        <Chip id="worldforge" label={`Worldforge (${counts.worldforge ?? 0})`} />
      </View>

      {loading ? (
        <View style={st.center}><ActivityIndicator color={GREEN} /></View>
      ) : shown.length === 0 ? (
        <Text style={st.empty}>No vault entries in this view yet.</Text>
      ) : (
        <View style={st.card}>
          {shown.map((it, i) => {
            const meta = SOURCE_META[it.source] || { label: it.source, color: MUTE, icon: 'cube' };
            return (
              <TouchableOpacity key={`${it.source}-${it.id}-${i}`} testID={`vault-item-${i}`} style={st.row} onPress={() => openItem(it)}>
                <Ionicons name={meta.icon} size={16} color={meta.color} />
                <View style={{ flex: 1 }}>
                  <Text style={st.name} numberOfLines={1}>{it.name}</Text>
                  <Text style={st.detail} numberOfLines={1}>{it.kind}{it.detail ? ` · ${it.detail}` : ''}</Text>
                </View>
                <View style={[st.badge, { borderColor: meta.color, backgroundColor: meta.color + '22' }]}>
                  <Text style={[st.badgeTxt, { color: meta.color }]}>{meta.label}</Text>
                </View>
                <Ionicons name="chevron-forward" size={14} color={MUTE} />
              </TouchableOpacity>
            );
          })}
        </View>
      )}
    </>
  );

  return (
    <>
      {embedded ? body : (
        <ScrollView
          contentContainerStyle={st.scroll}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={GREEN} />}
        >
          {body}
        </ScrollView>
      )}

      <Modal visible={!!sel} animationType="slide" transparent onRequestClose={closeItem}>
        <View style={st.backdrop}>
          <View style={st.sheet}>
            <View style={st.sheetHead}>
              <Text style={st.sheetTitle} numberOfLines={1}>{sel?.name || 'Vault entry'}</Text>
              <TouchableOpacity testID="vault-detail-close" onPress={closeItem} style={st.closeBtn}><Ionicons name="close" size={20} color="#f1f5f9" /></TouchableOpacity>
            </View>
            <Text style={st.sheetSub}>{(SOURCE_META[sel?.source || '']?.label || sel?.source)} · {sel?.kind}{sel?.detail ? ` · ${sel.detail}` : ''}</Text>

            {detailBusy ? <ActivityIndicator color={GREEN} style={{ marginTop: 20 }} /> : (
              <ScrollView style={{ maxHeight: 340 }} contentContainerStyle={{ paddingBottom: 8 }}>
                {sel?.source === 'worldforge' && sel?.image ? (
                  <Image source={{ uri: sel.image }} style={st.poster} resizeMode="cover" />
                ) : null}
                {!!content && <Text style={st.content} selectable>{content.slice(0, 6000)}</Text>}

                {sel?.source === 'boardroom' && versions.length > 0 && (
                  <>
                    <Text style={st.h3}>Version history</Text>
                    {versions.slice().reverse().map((v: any) => (
                      <View key={v.version} style={st.verRow}>
                        <Text style={st.verTxt}>v{v.version}{v === versions[versions.length - 1] ? '  (latest)' : ''}</Text>
                        {v.version !== versions[versions.length - 1]?.version && (
                          <TouchableOpacity testID={`vault-rollback-${v.version}`} style={st.miniBtn} onPress={() => doRollback(v.version)}>
                            <Text style={st.miniBtnTxt}>Restore</Text>
                          </TouchableOpacity>
                        )}
                      </View>
                    ))}
                  </>
                )}
              </ScrollView>
            )}

            <View style={st.actionRow}>
              <TouchableOpacity testID="vault-download" style={[st.actBtn, { backgroundColor: BLUE }]} onPress={doDownload}>
                <Ionicons name="download-outline" size={16} color="#fff" />
                <Text style={st.actTxt}>Download</Text>
              </TouchableOpacity>
              {sel?.source === 'boardroom' && (
                <>
                  <TouchableOpacity testID="vault-fetch-gamefiles" style={[st.actBtn, { backgroundColor: GREEN }]} onPress={() => doFetchTo('gamefiles')}>
                    <Ionicons name="hammer-outline" size={16} color="#04120a" />
                    <Text style={[st.actTxt, { color: '#04120a' }]}>→ Gamefiles</Text>
                  </TouchableOpacity>
                  <TouchableOpacity testID="vault-fetch-knowledge" style={[st.actBtn, { backgroundColor: PURPLE }]} onPress={() => doFetchTo('knowledge')}>
                    <Ionicons name="school-outline" size={16} color="#04120a" />
                    <Text style={[st.actTxt, { color: '#04120a' }]}>→ Jeeves</Text>
                  </TouchableOpacity>
                </>
              )}
            </View>
            {!!actionMsg && <Text style={st.actionMsg}>{actionMsg}</Text>}
            {fetchedGamefiles && (
              <TouchableOpacity testID="vault-continue-build" style={st.continueBtn} onPress={continueInBuild}>
                <Ionicons name="arrow-forward-circle" size={18} color="#04120a" />
                <Text style={st.continueTxt}>Continue in Build ▸</Text>
              </TouchableOpacity>
            )}
          </View>
        </View>
      </Modal>
    </>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <View style={st.stat}>
      <Text style={[st.statVal, { color }]}>{value}</Text>
      <Text style={st.statLbl}>{label}</Text>
    </View>
  );
}

const st = StyleSheet.create({
  scroll: { padding: 16, paddingBottom: 48 },
  statRow: { flexDirection: 'row', gap: 8, marginBottom: 12 },
  stat: { flex: 1, backgroundColor: CARD, borderRadius: 12, paddingVertical: 12, alignItems: 'center' },
  statVal: { fontSize: 16, fontWeight: '800' },
  statLbl: { color: MUTE, fontSize: 10, marginTop: 2 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 12 },
  chip: { backgroundColor: '#1e293b', borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6 },
  chipActive: { backgroundColor: GREEN },
  chipTxt: { color: '#cbd5e1', fontSize: 11, fontWeight: '600' },
  chipTxtActive: { color: '#04120a', fontWeight: '800' },
  card: { backgroundColor: CARD, borderRadius: 14, padding: 12 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1f2937' },
  name: { color: '#f1f5f9', fontSize: 13, fontWeight: '600' },
  detail: { color: MUTE, fontSize: 11, marginTop: 1 },
  badge: { borderRadius: 6, borderWidth: 1, paddingHorizontal: 7, paddingVertical: 2 },
  badgeTxt: { fontSize: 9, fontWeight: '800', textTransform: 'uppercase' },
  center: { paddingVertical: 40, alignItems: 'center' },
  empty: { color: MUTE, fontSize: 12, fontStyle: 'italic', textAlign: 'center', paddingVertical: 30 },
  // modal
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: BG, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 18, borderWidth: StyleSheet.hairlineWidth, borderColor: '#243043' },
  sheetHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  sheetTitle: { color: '#f1f5f9', fontSize: 16, fontWeight: '800', flex: 1 },
  closeBtn: { padding: 4 },
  sheetSub: { color: MUTE, fontSize: 12, marginTop: 2, marginBottom: 10 },
  content: { color: '#cbd5e1', fontSize: 12, lineHeight: 18, fontFamily: 'monospace' as any },
  poster: { width: '100%', height: 180, borderRadius: 10, marginBottom: 10 },
  h3: { color: '#e2e8f0', fontSize: 13, fontWeight: '700', marginTop: 14, marginBottom: 6 },
  verRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 5 },
  verTxt: { color: '#cbd5e1', fontSize: 12 },
  miniBtn: { backgroundColor: '#1e293b', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 5 },
  miniBtnTxt: { color: AMBER, fontSize: 11, fontWeight: '700' },
  actionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 14 },
  actBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10 },
  actTxt: { color: '#fff', fontSize: 12, fontWeight: '800' },
  actionMsg: { color: GREEN, fontSize: 12, marginTop: 10 },
  continueBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: GREEN, borderRadius: 12, paddingVertical: 13, marginTop: 12 },
  continueTxt: { color: '#04120a', fontSize: 14, fontWeight: '800' },
});
