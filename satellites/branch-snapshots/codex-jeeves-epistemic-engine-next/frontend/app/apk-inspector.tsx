/**
 * /apk-inspector — Deep introspection of the most recent APKs.
 *
 * Surfaces the new /api/binary/* endpoints as a single-glance dashboard
 * that proves to the user (and to anyone sideloading) that the APK is
 * genuinely runnable on Android 7+:
 *
 *   • toolchain status      → Android SDK / qemu / JDK probe
 *   • per-APK inspection    → classes.dex magic, manifest binary-XML,
 *                             MainActivity reference, LAUNCHER intent,
 *                             resources.arsc, v1/v2/v3 signature schemes
 *   • diagnostic bullets    → ✓/✗ list of pass/fail checks
 *   • one-tap rebuild       → wipes artifacts and re-packages
 *
 * The inspection report is what convinces a developer the APK is real.
 */
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, SafeAreaView, RefreshControl, Linking, TextInput, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import theme from '../theme/tokens';
import { useModalLogger } from '../utils/modalLogger';
import { toast } from '../components/Toast';
import { useFeatureFlag } from '../utils/featureFlags';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const { breathing, palette, radii } = theme;

type ToolchainStatus = {
  android_sdk_root: string;
  build_tools_version?: string;
  android_jar_exists: boolean;
  debug_keystore_exists: boolean;
  javac_available: boolean;
  qemu_required: boolean;
  qemu_path?: string;
  tools: Record<string, { available: boolean; path?: string; is_x86_64_elf?: boolean; size?: number }>;
  have_full_toolchain: boolean;
};

type Inspection = {
  build_id: string;
  path: string;
  structure: {
    exists: boolean;
    size_bytes: number;
    sha256: string;
    entry_count: number;
    has_classes_dex: boolean;
    has_manifest: boolean;
    has_resources_arsc: boolean;
    asset_count: number;
    asset_paths: string[];
    classes_dex_size?: number;
    dex_magic?: string;
    dex_version?: string;
    manifest_is_binary_xml?: boolean;
    has_main_activity?: boolean;
    has_launcher_intent?: boolean;
    has_internet_permission?: boolean;
    has_v1_signature?: boolean;
  };
  signature: { verifies?: boolean; stdout?: string; stderr?: string };
  is_installable_apk: boolean;
  diagnostic: string[];
};

type ApkRow = {
  build_id: string; size_bytes: number; modified_at: number;
  has_classes_dex: boolean; has_manifest: boolean;
  classes_dex_size: number; is_likely_runnable: boolean;
};

export default function ApkInspector() {
  const router = useRouter();
  const log = useModalLogger('ApkInspector');
  const [tc, setTc]         = useState<ToolchainStatus | null>(null);
  const [insp, setInsp]     = useState<Inspection | null>(null);
  const [buildId, setBuildId] = useState('real_runnable_v1');
  const [busy, setBusy]     = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [error, setError]   = useState('');
  const [apkList, setApkList] = useState<ApkRow[]>([]);

  const loadList = useCallback(async () => {
    try {
      const r = await fetch(`${BACKEND}/api/binary/list`);
      const j = await r.json();
      setApkList(j.apks || []);
    } catch { /* non-fatal */ }
  }, []);

  const loadToolchain = useCallback(async () => {
    try {
      const r = await fetch(`${BACKEND}/api/binary/toolchain`);
      setTc(await r.json());
    } catch (e: any) {
      setError(`Toolchain probe failed: ${e?.message}`);
    }
  }, []);

  const loadInspection = useCallback(async () => {
    setBusy(true); setError('');
    try {
      const r = await fetch(`${BACKEND}/api/binary/inspect/${encodeURIComponent(buildId.trim())}`);
      if (r.status === 404) {
        setError(`No APK for "${buildId}". Run a build first via Galaxy Studio or use Tools Arena → Package Build.`);
        setInsp(null);
      } else {
        setInsp(await r.json());
      }
    } catch (e: any) {
      setError(`Inspection failed: ${e?.message}`);
    } finally {
      setBusy(false);
    }
  }, [buildId]);

  const installToolchain = useCallback(async () => {
    setError('');
    try {
      const r = await fetch(`${BACKEND}/api/binary/install-toolchain`, { method: 'POST' });
      const j = await r.json();
      toast.info(j.message || 'Toolchain installer started');
      // Poll status every 5s up to 10 min
      let n = 0;
      const tick = setInterval(async () => {
        n++;
        const sr = await fetch(`${BACKEND}/api/binary/toolchain`);
        const sj = await sr.json();
        if (sj.have_full_toolchain || n > 120) {
          clearInterval(tick);
          setTc(sj);
        }
      }, 5000);
    } catch (e: any) {
      setError(`Install trigger failed: ${e?.message}`);
    }
  }, []);

  const generateDemoApk = useCallback(async () => {
    setError('');
    setRebuilding(true);
    try {
      const tag = `quickbuild_${Date.now().toString(36)}`;
      const r = await fetch(`${BACKEND}/api/binary/rebuild/${tag}`, { method: 'POST' });
      const j = await r.json();
      if (!r.ok) {
        setError(j.detail || `Generate failed (HTTP ${r.status})`);
      } else {
        setBuildId(tag);
        await loadList();
        await loadInspection();
      }
    } catch (e: any) {
      setError(`Generate failed: ${e?.message}`);
    } finally {
      setRebuilding(false);
    }
  }, [loadInspection, loadList]);

  const rebuild = useCallback(async () => {
    setRebuilding(true); setError('');
    log.action('rebuild_started', { build_id: buildId });
    const _t0 = Date.now();
    try {
      const r = await fetch(`${BACKEND}/api/binary/rebuild/${encodeURIComponent(buildId.trim())}`, { method: 'POST' });
      const j = await r.json();
      if (!r.ok) {
        setError(j.detail || `Rebuild failed (HTTP ${r.status})`);
        log.error(new Error(`rebuild HTTP ${r.status}`), { build_id: buildId, body: j });
      } else {
        await loadInspection();
        log.metric('rebuild_duration_ms', Date.now() - _t0, 'ms');
      }
    } catch (e: any) {
      setError(`Rebuild error: ${e?.message}`);
      log.error(e, { build_id: buildId });
    } finally {
      setRebuilding(false);
    }
  }, [buildId, loadInspection, log]);

  useEffect(() => { loadToolchain(); loadInspection(); loadList(); }, [loadToolchain, loadInspection, loadList]);

  /** Auto self-heal: when the apk_self_heal_toolchain flag is on AND the
   *  toolchain probe reports a partial install, kick off the installer
   *  exactly once per mount so the user doesn't have to remember the
   *  manual button. Honours flag changes via useFeatureFlag subscription. */
  const flagSelfHeal = useFeatureFlag('apk_self_heal_toolchain');
  const _autoHealedRef = React.useRef(false);
  useEffect(() => {
    if (!flagSelfHeal || _autoHealedRef.current) return;
    if (!tc || tc.have_full_toolchain) return;
    _autoHealedRef.current = true;
    toast.info('Self-heal: triggering toolchain install…');
    installToolchain();
  }, [flagSelfHeal, tc, installToolchain]);

  const fmtBytes = (n?: number) => {
    if (!n && n !== 0) return '?';
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n/1024).toFixed(1)} KB`;
    return `${(n/(1024*1024)).toFixed(2)} MB`;
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} hitSlop={theme.hitSlop.md} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={palette.ink[100]} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={styles.h1}>APK Inspector</Text>
          <Text style={styles.sub}>Proof your APK is runnable on Android 7+</Text>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={styles.body}
        refreshControl={<RefreshControl refreshing={busy} onRefresh={loadInspection} tintColor={palette.ink[200]} />}
      >
        {/* Toolchain card */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Ionicons name="construct" size={18} color="#a78bfa" />
            <Text style={styles.cardTitle}>Toolchain Status</Text>
            {tc?.have_full_toolchain ? (
              <View style={[styles.statusPill, { backgroundColor: '#10b98122' }]}>
                <Text style={[styles.statusPillText, { color: '#10b981' }]}>READY</Text>
              </View>
            ) : tc ? (
              <View style={[styles.statusPill, { backgroundColor: '#ef444422' }]}>
                <Text style={[styles.statusPillText, { color: '#ef4444' }]}>PARTIAL</Text>
              </View>
            ) : null}
          </View>
          {tc ? (
            <>
              <Row label="Build-Tools" value={tc.build_tools_version || '(missing)'} ok={!!tc.build_tools_version} />
              <Row label="android.jar" value={tc.android_jar_exists ? '✓ present' : '✗ missing'} ok={tc.android_jar_exists} />
              <Row label="Debug keystore" value={tc.debug_keystore_exists ? '✓ present' : '✗ missing'} ok={tc.debug_keystore_exists} />
              <Row label="JDK (javac)" value={tc.javac_available ? '✓ JDK 17 available' : '✗ missing'} ok={tc.javac_available} />
              <Row label="qemu-x86_64" value={tc.qemu_required ? (tc.qemu_path ? '✓ cross-arch bridge' : '✗ missing on aarch64') : 'not needed'} ok={!tc.qemu_required || !!tc.qemu_path} />
              <View style={styles.divider} />
              {Object.entries(tc.tools).map(([name, info]) => (
                <Row
                  key={name}
                  label={name}
                  value={info.available ? `✓ ${fmtBytes(info.size)}${info.is_x86_64_elf ? ' (x86_64 ELF)' : ' (script)'}` : '✗ missing'}
                  ok={info.available}
                  mono
                />
              ))}
              {!tc.have_full_toolchain && (
                <TouchableOpacity
                  style={[styles.btn, styles.btnAccent, { marginTop: 12 }]}
                  onPress={installToolchain}
                >
                  <Ionicons name="cloud-download" size={18} color="#fff" />
                  <Text style={styles.btnText}>Install toolchain (5-10 min)</Text>
                </TouchableOpacity>
              )}
            </>
          ) : <ActivityIndicator color={palette.ink[200]} />}
        </View>

        {/* Inspection input */}
        <View style={styles.card}>
          <View style={styles.cardHeader}>
            <Ionicons name="archive" size={18} color="#f59e0b" />
            <Text style={styles.cardTitle}>Inspect APK</Text>
          </View>
          <Text style={styles.fieldLabel}>build_id</Text>
          <TextInput
            style={styles.input}
            value={buildId}
            onChangeText={setBuildId}
            placeholder="e.g. real_runnable_v1"
            placeholderTextColor={palette.ink[400]}
            autoCapitalize="none"
            autoCorrect={false}
          />
          <View style={styles.row}>
            <TouchableOpacity style={[styles.btn, styles.btnPrimary]} onPress={loadInspection} disabled={busy}>
              {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.btnText}>Inspect</Text>}
            </TouchableOpacity>
            <TouchableOpacity style={[styles.btn, styles.btnAccent]} onPress={rebuild} disabled={rebuilding || !insp}>
              {rebuilding ? <ActivityIndicator color="#fff" /> : <Text style={styles.btnText}>Rebuild</Text>}
            </TouchableOpacity>
          </View>

          {/* Existing APKs picker */}
          {apkList.length > 0 ? (
            <>
              <Text style={[styles.fieldLabel, { marginTop: 16 }]}>
                Existing APKs ({apkList.length})
              </Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginHorizontal: -breathing.cardPadding, paddingHorizontal: breathing.cardPadding }}>
                {apkList.map(apk => {
                  const active = apk.build_id === buildId;
                  return (
                    <TouchableOpacity
                      key={apk.build_id}
                      onPress={() => { setBuildId(apk.build_id); setTimeout(loadInspection, 100); }}
                      style={[
                        styles.apkChip,
                        active && { borderColor: '#a78bfa', backgroundColor: '#a78bfa22' },
                        !apk.is_likely_runnable && { borderColor: '#A78BFA' },
                      ]}
                    >
                      <Ionicons
                        name={apk.is_likely_runnable ? 'checkmark-circle' : 'alert-circle'}
                        size={14}
                        color={apk.is_likely_runnable ? '#10b981' : '#A78BFA'}
                      />
                      <Text style={[styles.apkChipText, active && { color: '#a78bfa' }]} numberOfLines={1}>
                        {apk.build_id}
                      </Text>
                      <Text style={styles.apkChipMeta}>{fmtBytes(apk.size_bytes)}</Text>
                    </TouchableOpacity>
                  );
                })}
              </ScrollView>
            </>
          ) : (
            <View style={styles.emptyState}>
              <Ionicons name="archive-outline" size={36} color={palette.ink[600]} />
              <Text style={styles.emptyText}>No APKs yet</Text>
              <Text style={styles.emptyHelp}>
                Generate a quick demo APK to verify the pipeline end-to-end.
              </Text>
              <TouchableOpacity
                style={[styles.btn, styles.btnPrimary, { marginTop: 12, paddingHorizontal: 18 }]}
                onPress={generateDemoApk}
                disabled={rebuilding}
              >
                {rebuilding ? <ActivityIndicator color="#fff" /> : (
                  <>
                    <Ionicons name="add-circle" size={18} color="#fff" />
                    <Text style={styles.btnText}>Generate demo APK</Text>
                  </>
                )}
              </TouchableOpacity>
            </View>
          )}
        </View>

        {/* Error */}
        {error ? (
          <View style={[styles.card, styles.errorCard]}>
            <Ionicons name="alert-circle" size={18} color="#A78BFA" />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}

        {/* Inspection result */}
        {insp ? (
          <>
            {/* Runnability badge */}
            <View style={[styles.card, { borderColor: insp.is_installable_apk ? '#10b981' : '#ef4444', borderWidth: 2 }]}>
              <View style={styles.cardHeader}>
                <Ionicons
                  name={insp.is_installable_apk ? 'checkmark-circle' : 'close-circle'}
                  size={28}
                  color={insp.is_installable_apk ? '#10b981' : '#ef4444'}
                />
                <View style={{ flex: 1 }}>
                  <Text style={[styles.cardTitle, { fontSize: 18 }]}>
                    {insp.is_installable_apk ? 'Installable APK' : 'NOT Installable'}
                  </Text>
                  <Text style={styles.sub}>
                    {insp.is_installable_apk
                      ? 'Sideload this on any Android 7+ device — it will launch.'
                      : 'Missing structural elements — see diagnostic below.'}
                  </Text>
                </View>
              </View>
            </View>

            {/* Diagnostic bullets */}
            <View style={styles.card}>
              <View style={styles.cardHeader}>
                <Ionicons name="checkmark-done" size={18} color="#10b981" />
                <Text style={styles.cardTitle}>Diagnostic</Text>
              </View>
              {insp.diagnostic.map((line, i) => {
                const ok = line.startsWith('✓');
                const warn = line.startsWith('⚠');
                return (
                  <Text key={i} style={[
                    styles.diagLine,
                    { color: ok ? '#10B981' : warn ? '#fbbf24' : '#A78BFA' },
                  ]}>{line}</Text>
                );
              })}
            </View>

            {/* Structure detail */}
            <View style={styles.card}>
              <View style={styles.cardHeader}>
                <Ionicons name="layers" size={18} color="#3B82F6" />
                <Text style={styles.cardTitle}>Structure</Text>
              </View>
              <Row label="Size" value={fmtBytes(insp.structure.size_bytes)} mono />
              <Row label="Entries" value={String(insp.structure.entry_count)} mono />
              <Row label="classes.dex" value={`${fmtBytes(insp.structure.classes_dex_size)} · ${insp.structure.dex_magic}${insp.structure.dex_version}`} ok={insp.structure.has_classes_dex} mono />
              <Row label="Binary XML manifest" value={insp.structure.manifest_is_binary_xml ? '✓ yes' : '✗ no'} ok={insp.structure.manifest_is_binary_xml} />
              <Row label="MainActivity" value={insp.structure.has_main_activity ? '✓ in manifest' : '✗ not found'} ok={insp.structure.has_main_activity} />
              <Row label="LAUNCHER intent" value={insp.structure.has_launcher_intent ? '✓ present' : '✗ missing'} ok={insp.structure.has_launcher_intent} />
              <Row label="INTERNET permission" value={insp.structure.has_internet_permission ? '✓ granted' : '✗ missing'} ok={insp.structure.has_internet_permission} />
              <Row label="resources.arsc" value={insp.structure.has_resources_arsc ? '✓ compiled' : '✗ missing'} ok={insp.structure.has_resources_arsc} />
              <Row label="Assets" value={`${insp.structure.asset_count} files`} mono />
              <View style={styles.divider} />
              <Text style={styles.fieldLabel}>SHA-256</Text>
              <Text style={styles.codeBlock} numberOfLines={2}>{insp.structure.sha256}</Text>
              {insp.structure.asset_paths.length > 0 && (
                <>
                  <Text style={styles.fieldLabel}>Asset paths (first 20)</Text>
                  <Text style={styles.codeBlock}>{insp.structure.asset_paths.join('\n')}</Text>
                </>
              )}
            </View>

            {/* Signature */}
            <View style={styles.card}>
              <View style={styles.cardHeader}>
                <Ionicons name="shield-checkmark" size={18} color="#a78bfa" />
                <Text style={styles.cardTitle}>Signature (apksigner verify)</Text>
              </View>
              <Text style={[styles.codeBlock, { color: insp.signature.verifies ? '#10B981' : '#A78BFA' }]}>
                {(insp.signature.stdout || insp.signature.stderr || '(no output)').trim()}
              </Text>
            </View>

            {/* Download */}
            <TouchableOpacity
              style={[styles.btn, styles.btnDownload]}
              onPress={() => Linking.openURL(`${BACKEND}/api/binary/download/${buildId}/apk`)}
            >
              <Ionicons name="download" size={20} color="#fff" />
              <Text style={styles.btnText}>Download APK ({fmtBytes(insp.structure.size_bytes)})</Text>
            </TouchableOpacity>
          </>
        ) : null}

        <View style={{ height: 40 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

// ─────────────────────────────────────────────────────────────────────
function Row({ label, value, ok, mono }: { label: string; value: string; ok?: boolean; mono?: boolean }) {
  return (
    <View style={styles.kvRow}>
      <Text style={styles.kvLabel}>{label}</Text>
      <Text style={[
        styles.kvValue,
        mono && { fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }) },
        ok === true && { color: '#10B981' },
        ok === false && { color: '#A78BFA' },
      ]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe:    { flex: 1, backgroundColor: palette.ink[1000] },
  header:  {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: breathing.gutter, paddingVertical: 12, gap: 12,
    borderBottomWidth: 1, borderBottomColor: palette.ink[800],
  },
  backBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  h1:      { fontSize: 22, fontWeight: '700', color: palette.ink[50] },
  sub:     { fontSize: 12, color: palette.ink[400], marginTop: 2 },
  body:    { padding: breathing.gutter, gap: breathing.cardGap },

  card: {
    backgroundColor: palette.ink[900], borderRadius: radii.lg,
    padding: breathing.cardPadding, borderWidth: 1, borderColor: palette.ink[800],
    marginBottom: breathing.cardGap,
  },
  cardHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 },
  cardTitle:  { fontSize: 15, fontWeight: '700', color: palette.ink[50], flex: 1 },

  statusPill: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: radii.pill },
  statusPillText: { fontSize: 11, fontWeight: '700', letterSpacing: 0.5 },

  fieldLabel: { fontSize: 12, fontWeight: '600', color: palette.ink[300], marginBottom: 6, marginTop: 6 },
  input: {
    backgroundColor: palette.ink[800], color: palette.ink[50],
    borderRadius: radii.md, paddingHorizontal: 12, paddingVertical: 10,
    fontSize: 14, borderWidth: 1, borderColor: palette.ink[700], minHeight: 44,
  },
  row: { flexDirection: 'row', gap: 8, marginTop: 10 },
  btn: {
    flex: 1, paddingVertical: 12, borderRadius: radii.md, alignItems: 'center',
    flexDirection: 'row', justifyContent: 'center', gap: 8,
    minHeight: breathing.minTouch,
  },
  btnPrimary: { backgroundColor: '#a78bfa' },
  btnAccent:  { backgroundColor: '#f59e0b' },
  btnDownload: { backgroundColor: '#10b981', paddingVertical: 14 },
  btnText: { color: palette.ink[1000], fontWeight: '800', fontSize: 14 },

  kvRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 5 },
  kvLabel: { color: palette.ink[300], fontSize: 13 },
  kvValue: { color: palette.ink[100], fontSize: 13 },
  divider: { height: 1, backgroundColor: palette.ink[800], marginVertical: 8 },

  diagLine: { fontSize: 13, paddingVertical: 3 },

  codeBlock: {
    backgroundColor: palette.ink[1000], color: palette.ink[100],
    fontSize: 11, padding: 10, borderRadius: radii.sm,
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }),
    marginTop: 4,
  },

  errorCard: { flexDirection: 'row', alignItems: 'center', gap: 10, borderColor: '#7f1d1d', backgroundColor: '#1f0a0a' },
  errorText: { color: '#fda4af', fontSize: 13, flex: 1 },

  apkChip: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 10, height: 32,
    borderRadius: radii.pill, borderWidth: 1.5,
    borderColor: palette.ink[700], marginRight: 8,
    backgroundColor: palette.ink[800],
  },
  apkChipText: { fontSize: 12, fontWeight: '600', color: palette.ink[100], maxWidth: 140 },
  apkChipMeta: { fontSize: 11, color: palette.ink[400], fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace' }) },

  emptyState: {
    alignItems: 'center', paddingVertical: 24, gap: 8,
    borderWidth: 1, borderColor: palette.ink[800], borderStyle: 'dashed',
    borderRadius: radii.md, marginTop: 16,
  },
  emptyText: { fontSize: 15, fontWeight: '600', color: palette.ink[200] },
  emptyHelp: { fontSize: 12, color: palette.ink[400], textAlign: 'center', paddingHorizontal: 24, marginTop: -2 },
});
