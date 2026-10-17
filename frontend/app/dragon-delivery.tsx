/** Authenticated Dragon delivery route and canonical source-archive listing. */
import React from 'react';
import {ActivityIndicator, Platform, ScrollView, StyleSheet, Text, TouchableOpacity, View} from 'react-native';

import StudioLoginGate from '../src/auth/StudioLoginGate';
import api from '../src/utils/apiClient';
import {authHeaders, getAuthToken} from '../src/auth/gameforgeAuth';
import {API_BASE} from '../src/utils/apiBase';
import DragonDeliveryWorkbench from '../src/features/Jeeves/companion/DragonDeliveryWorkbench';
import {
  type NativeAttempt, type NativeTarget,
  normalizeNativeAttempts, normalizeNativeTargets, titleCaseId,
} from '../src/features/Jeeves/companion/dragonNativeTargets';
import {saveNativeSourceZip} from '../src/features/Jeeves/companion/saveNativeSourceZip';

const API = (API_BASE || '').replace(/\/$/, '');
const MAX_SOURCE_ZIP_BYTES = 250_000;
const SHA256 = /^[a-f0-9]{64}$/;

function DeliveryScreen() {
  const [targets, setTargets] = React.useState<NativeTarget[]>([]);
  const [projects, setProjects] = React.useState<NativeAttempt[]>([]);
  const [error, setError] = React.useState('');
  const [notice, setNotice] = React.useState('');
  const [loadingProjects, setLoadingProjects] = React.useState(false);
  const [downloading, setDownloading] = React.useState<string | null>(null);
  const live = React.useRef(true);
  const downloadAbort = React.useRef<AbortController | null>(null);

  const refreshProjects = React.useCallback(async () => {
    const token = getAuthToken();
    if (!token) {
      if (live.current) setProjects([]);
      return;
    }
    if (live.current) setLoadingProjects(true);
    try {
      const result = await api.get<Record<string, unknown>>(
        '/api/dragon-academy/status',
        {headers: authHeaders(), timeoutMs: 12000, retries: 0},
      );
      if (!live.current || token !== getAuthToken()) return;
      if (!result.ok || result.data?.ok !== true || !Array.isArray(result.data.native_attempts)) {
        throw new Error('Generated native source records could not be verified.');
      }
      const rows = normalizeNativeAttempts(result.data.native_attempts);
      rows.sort((a, b) => b.created_at - a.created_at);
      setProjects(rows.slice(0, 24));
    } catch (e) {
      if (live.current && token === getAuthToken()) {
        setError(e instanceof Error ? e.message : 'Native project history unavailable.');
      }
    } finally {
      if (live.current) setLoadingProjects(false);
    }
  }, []);

  React.useEffect(() => {
    live.current = true;
    void api.get<Record<string, unknown>>('/api/dragon-academy/native/targets', {
      headers: authHeaders(), timeoutMs: 12000, retries: 0,
    }).then(result => {
      if (!live.current) return;
      if (!result.ok || result.data?.ok !== true) {
        setError('Native target catalog is not available.'); return;
      }
      setTargets(normalizeNativeTargets(result.data.targets));
    }).catch(() => {
      if (live.current) setError('Native target catalog is not available.');
    });
    void refreshProjects();
    return () => {
      live.current = false;
      downloadAbort.current?.abort();
    };
  }, [refreshProjects]);

  const downloadProject = React.useCallback(async (item: NativeAttempt) => {
    if (downloading || !SHA256.test(item.attempt_id)) return;
    const token = getAuthToken();
    if (!token) {
      setError('Sign in before downloading private native source files.');
      return;
    }
    const controller = new AbortController();
    downloadAbort.current = controller;
    setDownloading(item.attempt_id);
    setError('');
    setNotice('');
    try {
      const response = await fetch(
        API + '/api/dragon-academy/native/' + item.attempt_id + '/archive',
        {method: 'GET', headers: authHeaders(), signal: controller.signal, cache: 'no-store'},
      );
      if (!response.ok) {
        throw new Error(response.status === 401 || response.status === 403
          ? 'This native source project is not available to the signed-in owner.'
          : 'Native source archive is unavailable.');
      }
      const mime = response.headers.get('content-type') || '';
      const digest = response.headers.get('x-content-sha256') || '';
      const size = Number(response.headers.get('content-length') || 0);
      if (!mime.includes('application/zip') || !SHA256.test(digest) ||
          !Number.isSafeInteger(size) || size < 0 || size > MAX_SOURCE_ZIP_BYTES) {
        throw new Error('The response was not a bounded, verifiable source-only ZIP.');
      }
      const archive = await response.blob();
      if (archive.size === 0 || archive.size > MAX_SOURCE_ZIP_BYTES) {
        throw new Error('Native source archive exceeded the permitted size.');
      }
      if (Platform.OS === 'web' && typeof crypto !== 'undefined' &&
          crypto.subtle && typeof archive.arrayBuffer === 'function') {
        const bytes = new Uint8Array(await crypto.subtle.digest('SHA-256', await archive.arrayBuffer()));
        const actual = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
        if (actual !== digest) throw new Error('Native source archive digest mismatch.');
      }
      if (controller.signal.aborted || !live.current || token !== getAuthToken()) return;
      await saveNativeSourceZip(
        archive, 'dragon-native-' + item.attempt_id.slice(0, 12) + '-' + digest.slice(0, 12) + '.zip',
        MAX_SOURCE_ZIP_BYTES,
      );
      if (live.current && token === getAuthToken()) {
        setNotice('Source ZIP exported. Compilation and gameplay verification remain separate.');
      }
    } catch (e) {
      if (!controller.signal.aborted && live.current) {
        setError(e instanceof Error ? e.message : 'The archive could not be downloaded.');
      }
    } finally {
      if (downloadAbort.current === controller) downloadAbort.current = null;
      if (live.current) setDownloading(null);
    }
  }, [downloading]);

  return <ScrollView style={styles.root} contentContainerStyle={styles.content}>
    <Text style={styles.title}>Dragon knowledge and native design</Text>
    <Text style={styles.notice}>
      Delivery requires independently approved evidence, consented native practice
      and the shared resource runtime. Native source is not a compiled or released game.
    </Text>
    <DragonDeliveryWorkbench targets={targets} onGenerated={() => { void refreshProjects(); }}/>
    <View style={styles.panel}>
      <Text style={styles.subtitle}>Generated native projects</Text>
      <Text style={styles.notice}>
        Archives are loaded only for the authenticated owner. No source code is executed here.
      </Text>
      <TouchableOpacity accessibilityRole="button" onPress={() => void refreshProjects()}
        disabled={loadingProjects || downloading !== null} style={styles.button}>
        <Text style={styles.buttonText}>{loadingProjects ? 'Loading projects…' : 'Refresh native projects'}</Text>
      </TouchableOpacity>
      {loadingProjects && <ActivityIndicator color="#8dddc0"/>}
      {!loadingProjects && projects.length === 0 &&
        <Text style={styles.notice}>No generated native source projects recorded for this account.</Text>}
      {projects.map(item => <View key={item.attempt_id} style={styles.project}>
        <Text style={styles.projectTitle}>{titleCaseId(item.target_id)} · {titleCaseId(item.style)}</Text>
        <Text style={styles.notice}>Source only · {new Date(item.created_at * 1000).toLocaleString()}</Text>
        <Text style={styles.mono} selectable>Artifact {item.source_digest.slice(0, 20)}…</Text>
        <TouchableOpacity accessibilityRole="button"
          accessibilityLabel={'Download native source ZIP for ' + item.target_id}
          disabled={downloading !== null}
          onPress={() => { void downloadProject(item); }} style={styles.button}>
          <Text style={styles.buttonText}>{downloading === item.attempt_id
            ? 'Retrieving source ZIP…' : 'Download authenticated source ZIP'}</Text>
        </TouchableOpacity>
      </View>)}
    </View>
    {!!error && <Text accessibilityRole="alert" style={styles.warning}>{error}</Text>}
    {!!notice && <Text accessibilityLiveRegion="polite" style={styles.success}>{notice}</Text>}
  </ScrollView>;
}

export default function DragonDeliveryRoute() {
  return <StudioLoginGate><DeliveryScreen/></StudioLoginGate>;
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: '#091916'},
  content: {padding: 16, paddingBottom: 48, gap: 13},
  title: {color: '#e0f9eb', fontSize: 23, fontWeight: '800'},
  subtitle: {color: '#e0f9eb', fontSize: 18, fontWeight: '700'},
  notice: {fontSize: 13, color: '#a8c8bd', lineHeight: 20},
  warning: {fontSize: 13, color: '#ffd6a0'},
  success: {fontSize: 13, color: '#b1e7cb'},
  panel: {padding: 14, gap: 12, borderRadius: 13, backgroundColor: '#112820'},
  project: {gap: 7, padding: 12, borderRadius: 10, backgroundColor: '#17352a'},
  projectTitle: {fontSize: 15, fontWeight: '700', color: '#e2f9e9'},
  mono: {fontSize: 11, color: '#bedbd0'},
  button: {padding: 12, backgroundColor: '#276d55', borderRadius: 9, alignItems: 'center'},
  buttonText: {fontSize: 13, fontWeight: '700', color: '#fff'},
});
