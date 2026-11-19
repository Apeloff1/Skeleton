/**
 * /feature-flags — Dynamic feature-flag admin/dev screen v2.
 *
 * Upgrades over v1:
 *   • Live filter (search by name/description).
 *   • Namespace grouping (hub.* / experimental.* / observability.* / ...).
 *   • "Changed" pill on flags whose state diverges from the bundled defaults.
 *   • Empty-state when search returns no rows.
 *   • Admin token editor (persisted via AsyncStorage; injected on mutations).
 *   • Local per-device override (long-press) — survives restarts.
 *   • Audit log inline drawer per flag.
 *   • Pull-to-refresh + Toast on every mutation.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  TextInput, StyleSheet, SafeAreaView, Platform, RefreshControl, Alert, Modal,
} from 'react-native';
import { useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { useFeatureFlags, ResolvedFlag } from '../src/feature-flags';
import { BUNDLED_FALLBACK_FLAGS } from '../src/feature-flags/fallback';
import {
  loadAdminToken, setAdminToken, adminHeaders, getAdminTokenCached,
} from '../src/feature-flags/adminToken';
import {
  loadLocalOverrides, setLocalOverride, clearLocalOverrides,
} from '../src/feature-flags/overrides';
import { toast } from '../components/Toast';

interface AuditRow { ts: number; name: string; action: string; diff: any; ip: string; user_agent: string; actor: string }

function namespaceOf(name: string): string {
  const i = name.indexOf('.');
  return i > 0 ? name.slice(0, i) : 'other';
}
function defaultsFor(name: string): { enabled: boolean; rollout: number } | null {
  const d = BUNDLED_FALLBACK_FLAGS.find(f => f.name === name);
  return d ? { enabled: d.enabled, rollout: d.rollout } : null;
}
function hasChanged(f: ResolvedFlag): boolean {
  const d = defaultsFor(f.name);
  if (!d) return false;
  return d.enabled !== f.enabled || d.rollout !== f.rollout;
}

export default function FeatureFlagsAdminScreen() {
  const router = useRouter();
  const { flags, environment, loading, error, refresh, userId, setUserId } = useFeatureFlags();
  const [busy,  setBusy]   = React.useState<string | null>(null);
  const [draft, setDraft]  = React.useState<string>('');
  const [query, setQuery]  = React.useState<string>('');
  const [token, setToken]  = React.useState<string>('');
  const [tokenDraft, setTokenDraft] = React.useState<string>('');
  const [auditOpen, setAuditOpen]   = React.useState<string | null>(null);
  const [auditRows, setAuditRows]   = React.useState<AuditRow[]>([]);
  const [overrides, setOverrides]   = React.useState<Record<string, boolean>>({});

  // Boot — hydrate token + local overrides.
  React.useEffect(() => {
    (async () => {
      const t = await loadAdminToken();
      setToken(t); setTokenDraft(t);
      const o = await loadLocalOverrides();
      setOverrides({ ...o });
    })();
  }, []);

  const post = React.useCallback(async (name: string, body: any) => {
    setBusy(name);
    try {
      const r = await api.post(`/api/feature-flags/${encodeURIComponent(name)}`, body, { headers: adminHeaders() });
      if (!r.ok) {
        toast.error(`Update failed: ${r.error || r.status}`);
      } else {
        toast.success(`Updated ${name}`);
      }
    } finally { setBusy(null); await refresh(); }
  }, [refresh]);

  const onToggle    = React.useCallback((f: ResolvedFlag) => post(f.name, { enabled: !f.enabled }), [post]);
  const onSetRollout = React.useCallback((f: ResolvedFlag, rollout: number) => post(f.name, { rollout }), [post]);

  const onDelete = React.useCallback((f: ResolvedFlag) => {
    Alert.alert('Delete flag?', f.name, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => {
        setBusy(f.name);
        try {
          const r = await api.del(`/api/feature-flags/${encodeURIComponent(f.name)}`, { headers: adminHeaders() });
          if (!r.ok) toast.error(`Delete failed: ${r.error || r.status}`);
          else toast.success(`Deleted ${f.name}`);
        } finally { setBusy(null); await refresh(); }
      }},
    ]);
  }, [refresh]);

  const onOpenAudit = React.useCallback(async (name: string) => {
    setAuditOpen(name); setAuditRows([]);
    const r = await api.get<{ ok: boolean; rows: AuditRow[] }>(`/api/feature-flags/audit?limit=50&name=${encodeURIComponent(name)}`);
    setAuditRows((r.data?.rows as AuditRow[]) || []);
  }, []);

  const onSaveToken = React.useCallback(async () => {
    await setAdminToken(tokenDraft.trim());
    setToken(tokenDraft.trim());
    toast.success(getAdminTokenCached() ? 'Admin token saved' : 'Admin token cleared');
  }, [tokenDraft]);

  const onToggleOverride = React.useCallback(async (f: ResolvedFlag) => {
    const cur = overrides[f.name];
    const next = cur === undefined ? !f.resolved : (cur ? null : null);  // cycle: unset → opposite → unset
    if (next === null) {
      await setLocalOverride(f.name, null);
      const { [f.name]: _drop, ...rest } = overrides;
      setOverrides(rest);
      toast.show(`Local override cleared for ${f.name}`);
    } else {
      await setLocalOverride(f.name, next);
      setOverrides({ ...overrides, [f.name]: next });
      toast.show(`Local override → ${next ? 'ON' : 'OFF'} for ${f.name}`);
    }
  }, [overrides]);

  const onClearLocalOverrides = React.useCallback(async () => {
    await clearLocalOverrides();
    setOverrides({});
    toast.success('All local overrides cleared');
  }, []);

  const filteredGrouped = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = !q ? flags : flags.filter(f =>
      f.name.toLowerCase().includes(q) || (f.description || '').toLowerCase().includes(q)
    );
    const groups: Record<string, ResolvedFlag[]> = {};
    for (const f of filtered) {
      const ns = namespaceOf(f.name);
      (groups[ns] = groups[ns] || []).push(f);
    }
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [flags, query]);

  const totalCount = flags.length;
  const visibleCount = filteredGrouped.reduce((acc, [, list]) => acc + list.length, 0);

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backTxt}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Feature Flags</Text>
        <Text style={styles.env}>{environment.toUpperCase()}</Text>
      </View>

      <View style={styles.userRow}>
        <Text style={styles.userLabel}>user_id</Text>
        <TextInput
          style={styles.userInput}
          value={draft || userId || ''}
          onChangeText={setDraft}
          onSubmitEditing={() => setUserId(draft || null)}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder="default_user"
          placeholderTextColor="#64748b"
        />
        <TouchableOpacity style={styles.applyBtn} onPress={() => setUserId(draft || null)}>
          <Text style={styles.applyTxt}>Apply</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.userRow}>
        <Text style={styles.userLabel}>token</Text>
        <TextInput
          style={styles.userInput}
          value={tokenDraft}
          onChangeText={setTokenDraft}
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
          placeholder={token ? '••• admin token saved' : 'X-Admin-Token (optional)'}
          placeholderTextColor="#64748b"
        />
        <TouchableOpacity style={styles.applyBtn} onPress={onSaveToken}>
          <Text style={styles.applyTxt}>Save</Text>
        </TouchableOpacity>
      </View>

      {Object.keys(overrides).length > 0 ? (
        <View style={styles.overrideBanner}>
          <Text style={styles.overrideTxt}>
            {Object.keys(overrides).length} local override{Object.keys(overrides).length === 1 ? '' : 's'} active
          </Text>
          <TouchableOpacity onPress={onClearLocalOverrides}>
            <Text style={styles.overrideClear}>Clear all</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {error ? <Text style={styles.err}>error: {error}</Text> : null}

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={{ paddingBottom: 80 }}
        refreshControl={<RefreshControl tintColor="#fff" refreshing={loading} onRefresh={refresh} />}
      >
        {loading && totalCount === 0 ? (
          <ActivityIndicator color="#fff" style={{ marginTop: 24 }} />
        ) : null}

        {filteredGrouped.length === 0 && totalCount > 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>No flags match “{query}”</Text>
            <Text style={styles.emptySub}>{visibleCount}/{totalCount} visible</Text>
          </View>
        ) : null}

        {filteredGrouped.map(([ns, list]) => (
          <View key={ns}>
            <View style={styles.groupHeader}>
              <Text style={styles.groupName}>{ns}</Text>
              <Text style={styles.groupCount}>{list.length}</Text>
            </View>
            {list.map((f) => {
              const changed = hasChanged(f);
              const ov = overrides[f.name];
              const isBusy = busy === f.name;
              return (
                <TouchableOpacity
                  key={f.name}
                  style={styles.row}
                  onLongPress={() => onToggleOverride(f)}
                  delayLongPress={400}
                  activeOpacity={0.8}
                >
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <Text style={styles.name}>{f.name}</Text>
                      {changed ? <Text style={styles.changedPill}>CHANGED</Text> : null}
                      {ov !== undefined ? (
                        <Text style={[styles.changedPill, { backgroundColor: '#9333ea' }]}>
                          OVERRIDE {ov ? 'ON' : 'OFF'}
                        </Text>
                      ) : null}
                    </View>
                    <Text style={styles.desc} numberOfLines={2}>{f.description || '—'}</Text>
                    <View style={styles.metaRow}>
                      <Text style={[styles.pill, f.resolved ? styles.pillOn : styles.pillOff]}>
                        {f.resolved ? 'RESOLVED ON' : 'RESOLVED OFF'}
                      </Text>
                      <Text style={styles.pillMeta}>rollout {f.rollout}%</Text>
                      {f.environments.length ? (
                        <Text style={styles.pillMeta}>env: {f.environments.join(', ')}</Text>
                      ) : null}
                      <TouchableOpacity onPress={() => onOpenAudit(f.name)}>
                        <Text style={styles.audit}>Audit</Text>
                      </TouchableOpacity>
                      <TouchableOpacity onPress={() => onDelete(f)}>
                        <Text style={styles.del}>Delete</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                  <View style={styles.actions}>
                    <TouchableOpacity
                      onPress={() => onToggle(f)}
                      disabled={isBusy}
                      style={[styles.toggle, f.enabled ? styles.toggleOn : styles.toggleOff]}
                    >
                      {isBusy
                        ? <ActivityIndicator color="#fff" size="small" />
                        : <Text style={styles.toggleTxt}>{f.enabled ? 'ON' : 'OFF'}</Text>}
                    </TouchableOpacity>
                    <View style={styles.rolloutBtns}>
                      {[0, 10, 50, 100].map((v) => (
                        <TouchableOpacity
                          key={v}
                          style={[styles.rolloutBtn, f.rollout === v && styles.rolloutBtnActive]}
                          disabled={isBusy}
                          onPress={() => onSetRollout(f, v)}
                        >
                          <Text style={styles.rolloutTxt}>{v}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>
                </TouchableOpacity>
              );
            })}
          </View>
        ))}
      </ScrollView>

      <View style={styles.controls}>
        <TextInput
          style={styles.search}
          value={query}
          onChangeText={setQuery}
          placeholder={`Search ${totalCount} flag${totalCount === 1 ? '' : 's'}…`}
          placeholderTextColor="#64748b"
          autoCorrect={false}
          autoCapitalize="none"
        />
      </View>

      {/* Audit log drawer */}
      <Modal visible={!!auditOpen} animationType="slide" transparent onRequestClose={() => setAuditOpen(null)}>
        <View style={styles.auditBackdrop}>
          <View style={styles.auditSheet}>
            <View style={styles.auditHeader}>
              <Text style={styles.auditTitle}>Audit · {auditOpen}</Text>
              <TouchableOpacity onPress={() => setAuditOpen(null)}>
                <Text style={styles.backTxt}>Close</Text>
              </TouchableOpacity>
            </View>
            <ScrollView style={{ maxHeight: 360 }}>
              {auditRows.length === 0 ? (
                <Text style={styles.emptySub}>No audit entries.</Text>
              ) : null}
              {auditRows.map((row, i) => (
                <View key={i} style={styles.auditRow}>
                  <Text style={styles.auditAction}>{row.action.toUpperCase()}</Text>
                  <Text style={styles.auditDetails}>
                    {new Date(row.ts * 1000).toLocaleString()} · {row.ip || 'local'}
                  </Text>
                  <Text style={styles.auditDiff}>{JSON.stringify(row.diff)}</Text>
                </View>
              ))}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:       { flex: 1, backgroundColor: '#0A0A0A' },
  header:     {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingTop: Platform.OS === 'ios' ? 8 : 16, paddingBottom: 12,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1F1F1F',
  },
  backBtn:    { paddingVertical: 6, paddingHorizontal: 10 },
  backTxt:    { color: '#93c5fd', fontSize: 15 },
  title:      { color: '#fff', fontSize: 18, fontWeight: '700' },
  env:        { color: '#f59e0b', fontSize: 11, fontWeight: '700', letterSpacing: 0.5 },
  controls:   { paddingHorizontal: 12, paddingTop: 8, paddingBottom: Platform.OS === 'ios' ? 20 : 10, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#1F1F1F' },
  search:     {
    backgroundColor: '#262626', color: '#fff', borderRadius: 8,
    paddingHorizontal: 12, paddingVertical: Platform.OS === 'ios' ? 10 : 6, fontSize: 13,
  },
  userRow:    { flexDirection: 'row', alignItems: 'center', padding: 12, gap: 8 },
  userLabel:  { color: '#94a3b8', fontSize: 12, width: 60 },
  userInput:  {
    flex: 1, backgroundColor: '#262626', color: '#fff', borderRadius: 6,
    paddingHorizontal: 10, paddingVertical: Platform.OS === 'ios' ? 8 : 4, fontSize: 13,
  },
  applyBtn:   { backgroundColor: '#3b82f6', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 6 },
  applyTxt:   { color: '#fff', fontSize: 12, fontWeight: '600' },
  overrideBanner: {
    flexDirection: 'row', justifyContent: 'space-between',
    paddingHorizontal: 14, paddingVertical: 8, backgroundColor: '#581c87',
  },
  overrideTxt: { color: '#fae8ff', fontSize: 12, fontWeight: '600' },
  overrideClear: { color: '#fff', fontSize: 12, textDecorationLine: 'underline' },
  err:        { color: '#f87171', padding: 12, fontSize: 12 },
  scroll:     { flex: 1 },
  groupHeader:{
    flexDirection: 'row', justifyContent: 'space-between',
    paddingHorizontal: 14, paddingTop: 14, paddingBottom: 6,
  },
  groupName:  { color: '#3B82F6', fontSize: 11, fontWeight: '800', letterSpacing: 1.2, textTransform: 'uppercase' },
  groupCount: { color: '#64748b', fontSize: 11, fontWeight: '600' },
  row:        {
    flexDirection: 'row', alignItems: 'flex-start',
    paddingHorizontal: 14, paddingVertical: 12, gap: 10,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1F1F1F',
  },
  name:       { color: '#fff', fontSize: 14, fontWeight: '600' },
  changedPill:{
    backgroundColor: '#b45309', color: '#fffbeb',
    fontSize: 9, fontWeight: '700', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 6, overflow: 'hidden',
  },
  desc:       { color: '#94a3b8', fontSize: 12, lineHeight: 16, marginBottom: 6, marginTop: 4 },
  metaRow:    { flexDirection: 'row', flexWrap: 'wrap', gap: 6, alignItems: 'center' },
  pill:       { fontSize: 10, fontWeight: '700', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10, overflow: 'hidden' },
  pillOn:     { backgroundColor: '#065f46', color: '#a7f3d0' },
  pillOff:    { backgroundColor: '#374151', color: '#9ca3af' },
  pillMeta:   { fontSize: 10, color: '#94a3b8', backgroundColor: '#262626', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 8, overflow: 'hidden' },
  audit:      { color: '#3B82F6', fontSize: 10, fontWeight: '600', paddingHorizontal: 6, paddingVertical: 2 },
  del:        { color: '#f87171', fontSize: 10, fontWeight: '600', paddingHorizontal: 6, paddingVertical: 2 },
  actions:    { alignItems: 'flex-end', gap: 8 },
  toggle:     { paddingHorizontal: 14, paddingVertical: 6, borderRadius: 14, minWidth: 56, alignItems: 'center' },
  toggleOn:   { backgroundColor: '#16a34a' },
  toggleOff:  { backgroundColor: '#374151' },
  toggleTxt:  { color: '#fff', fontWeight: '700', fontSize: 11 },
  rolloutBtns:{ flexDirection: 'row', gap: 4 },
  rolloutBtn: { backgroundColor: '#262626', paddingHorizontal: 6, paddingVertical: 3, borderRadius: 5, minWidth: 26, alignItems: 'center' },
  rolloutBtnActive: { backgroundColor: '#3b82f6' },
  rolloutTxt: { color: '#fff', fontSize: 10, fontWeight: '600' },
  empty:      { padding: 40, alignItems: 'center' },
  emptyTitle: { color: '#94a3b8', fontSize: 14, fontWeight: '600', marginBottom: 4 },
  emptySub:   { color: '#64748b', fontSize: 12, padding: 16 },
  auditBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.65)', justifyContent: 'flex-end' },
  auditSheet:    { backgroundColor: '#0A0A0A', padding: 16, borderTopLeftRadius: 14, borderTopRightRadius: 14, maxHeight: '70%' },
  auditHeader:   { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  auditTitle:    { color: '#fff', fontSize: 15, fontWeight: '700' },
  auditRow:      { paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1F1F1F' },
  auditAction:   { color: '#3B82F6', fontSize: 10, fontWeight: '800', letterSpacing: 1 },
  auditDetails:  { color: '#94a3b8', fontSize: 11, marginTop: 2 },
  auditDiff:     { color: '#e2e8f0', fontSize: 10, marginTop: 4, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
});
