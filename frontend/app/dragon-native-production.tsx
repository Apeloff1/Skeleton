/**
 * Dragon native homebrew — integrated creator UI for the authenticated,
 * source-only production API. This screen never compiles ROMs or grants
 * emulator, hardware, license, training or publication authority.
 */
import React from 'react';
import {
  ActivityIndicator, Platform, SafeAreaView, ScrollView, StyleSheet,
  Text, TextInput, TouchableOpacity, View,
} from 'react-native';
import { useRouter } from 'expo-router';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';

import StudioLoginGate, { useStudioAuth } from '../src/auth/StudioLoginGate';
import { authHeaders, getAuthToken } from '../src/auth/gameforgeAuth';
import { API_BASE } from '../utils/apiBase';

type PlatformCapability = {
  id: string;
  family: string;
  status: string;
  native_source_emitter: boolean;
  supported_styles: readonly string[];
  local_verified_rom_compiler: boolean;
  toolchain: string;
};

type NativePlan = {
  status: 'source_ready' | 'blocked';
  can_export_sources: boolean;
  evidence: string;
  targets: Array<{
    target: string; state: string; reason: string;
    target_palette: string | null; target_stages: number | null;
    target_candidates: number | null; adaptations: string[];
  }>;
};

type CapabilityPayload = {
  ok: boolean;
  targets: PlatformCapability[];
  claim_boundary: string;
};

const API = (API_BASE || '').replace(/\/$/, '');
const ENDPOINT = API + '/api/dragon-academy/native/production';
const MAX_DOWNLOAD_BYTES = 3_000_000;
const MAX_TARGETS = 3;
const PALETTES = ['vga_dusk', 'dmg_green', 'handheld', 'cga', 'crt_arcade', 'modern_neon'] as const;
const HEROES = ['hatchling', 'knight', 'explorer', 'pilot', 'astronaut', 'robot'] as const;
const THEMES = ['ancient_ruins', 'crystals', 'forest', 'ice', 'space', 'volcano', 'clockwork'] as const;

function supported(capability: PlatformCapability, style: string): boolean {
  return capability.native_source_emitter &&
    capability.status !== 'licensed_sdk' &&
    capability.supported_styles.includes(style);
}

function formatStyle(style: string): string {
  return style.replace(/_/g, ' ');
}

async function saveBundle(blob: Blob, name: string): Promise<void> {
  if (!blob.size || blob.size > MAX_DOWNLOAD_BYTES) {
    throw new Error('The native source ZIP exceeds the maximum download size.');
  }
  if (Platform.OS === 'web') {
    const url = URL.createObjectURL(blob);
    try {
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = name;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
    } finally {
      setTimeout(() => URL.revokeObjectURL(url), 15_000);
    }
    return;
  }
  if (!FileSystem.documentDirectory) {
    throw new Error('Device storage for native source ZIPs is unavailable.');
  }
  // The backend enforces a strict 3-MiB source-only bundle. Do not persist
  // credentials, private rights notes, or request payloads with the archive.
  const base64 = await new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('Unable to decode the native source archive.'));
    reader.onload = () => {
      if (typeof reader.result !== 'string') {
        reject(new Error('Invalid native source archive result.'));
        return;
      }
      const separator = reader.result.indexOf(',');
      if (separator < 0) {
        reject(new Error('Invalid source archive encoding.'));
        return;
      }
      resolve(reader.result.slice(separator + 1));
    };
    reader.readAsDataURL(blob);
  });
  const destination = FileSystem.documentDirectory + name;
  await FileSystem.writeAsStringAsync(destination, base64, {
    encoding: FileSystem.EncodingType.Base64,
  });
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(destination, {
      mimeType: 'application/zip',
      dialogTitle: 'Share original Dragon native sources',
    });
  }
}

function NativeSourceEditor() {
  const router = useRouter();
  const { role } = useStudioAuth();
  const [catalog, setCatalog] = React.useState<PlatformCapability[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [title, setTitle] = React.useState('Original Dragon Adventure');
  const [style, setStyle] = React.useState('arcade_score_attack');
  const [palette, setPalette] = React.useState<string>('vga_dusk');
  const [hero, setHero] = React.useState<string>('hatchling');
  const [questTheme, setQuestTheme] = React.useState<string>('ancient_ruins');
  const [difficulty, setDifficulty] = React.useState(4);
  const [stageCount, setStageCount] = React.useState(4);
  const [searchBudget, setSearchBudget] = React.useState(8);
  const [targets, setTargets] = React.useState<string[]>(['game_boy']);
  const [attested, setAttested] = React.useState(false);
  const [approved, setApproved] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [failure, setFailure] = React.useState('');
  const [success, setSuccess] = React.useState('');
  const [preview, setPreview] = React.useState<NativePlan | null>(null);
  const active = React.useRef<AbortController | null>(null);
  const isEditor = role === 'editor' || role === 'admin';

  React.useEffect(() => {
    const controller = new AbortController();
    active.current = controller;
    void (async () => {
      try {
        const response = await fetch(ENDPOINT + '/capabilities', {
          method: 'GET',
          headers: authHeaders(),
          signal: controller.signal,
          cache: 'no-store',
        });
        if (!response.ok) throw new Error('Native hardware capability catalog is unavailable.');
        const data = await response.json() as CapabilityPayload;
        if (!data.ok || !Array.isArray(data.targets) || data.targets.length > 200) {
          throw new Error('Invalid native hardware capability response.');
        }
        const valid = data.targets.filter((item) =>
          item && typeof item.id === 'string' &&
          item.id.length < 70 && typeof item.family === 'string' &&
          item.family.length < 90 && Array.isArray(item.supported_styles) &&
          item.supported_styles.length <= 40 && item.supported_styles.every(
            (value: unknown) => typeof value === 'string' && value.length <= 64));
        if (!controller.signal.aborted) {
          setCatalog(valid);
          setTargets(previous => previous.filter(
            id => valid.some(item => item.id === id && supported(item, 'arcade_score_attack')),
          ));
        }
      } catch {
        if (!controller.signal.aborted) setFailure('Unable to load verified platform availability.');
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    })();
    return () => controller.abort();
  }, []);

  React.useEffect(() => () => { active.current?.abort(); }, []);

  const styles = React.useMemo(() => Array.from(new Set(
    catalog.filter(item => item.native_source_emitter &&
      item.status !== 'licensed_sdk')
      .flatMap(item => item.supported_styles),
  )).sort(), [catalog]);

  const eligible = React.useMemo(
    () => catalog.filter(item => supported(item, style)),
    [catalog, style],
  );

  const chooseStyle = (next: string) => {
    if (busy) return;
    setStyle(next);
    setTargets(current => current.filter(id =>
      catalog.some(item => item.id === id && supported(item, next))));
    setSuccess('');
  };

  const chooseTarget = (id: string) => {
    if (busy) return;
    setTargets(current => current.includes(id)
      ? current.filter(value => value !== id)
      : current.length >= MAX_TARGETS ? current : [...current, id]);
    setSuccess('');
  };

  const usesCartridgeTargets = targets.some(id =>
    !['pc_linux', 'pc_windows', 'pc_macos', 'steam_deck'].includes(id));
  const usesDesktopTargets = targets.some(id =>
    ['pc_linux', 'pc_windows', 'pc_macos', 'steam_deck'].includes(id));

  const sourcePayload = (forGeneration: boolean) => ({
    title: title.trim(), style, targets, seed: 1,
    original_work_attested: attested, approved: forGeneration && approved,
    rights_basis: 'original_homebrew', rights_reference: '',
    portable_design: {
      palette, hero, quest_theme: questTheme, difficulty,
      stages: stageCount, candidates: searchBudget,
      project_notes: 'Original native homebrew; platform-scaled design',
    },
  });

  React.useEffect(() => { setPreview(null); }, [
    title, style, targets, palette, hero, questTheme,
    difficulty, stageCount, searchBudget, attested,
  ]);

  const previewTargets = async () => {
    if (busy || !isEditor || !attested || !title.trim() ||
        !/^[A-Za-z][A-Za-z0-9 ._'!-]{2,79}$/.test(title.trim()) ||
        !targets.length || targets.length > MAX_TARGETS) return;
    setBusy(true);
    setFailure('');
    setPreview(null);
    try {
      if (!getAuthToken()) {
        throw new Error('An authenticated editor session is required.');
      }
      const response = await fetch(ENDPOINT + '/preview', {
        method: 'POST', cache: 'no-store',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(sourcePayload(false)),
      });
      if (!response.ok) throw new Error('Native feasibility preview was rejected.');
      const report = await response.json() as NativePlan;
      if (!report || !Array.isArray(report.targets) ||
          report.targets.length !== targets.length ||
          !['source_ready', 'blocked'].includes(report.status)) {
        throw new Error('Invalid native feasibility report.');
      }
      setPreview(report);
    } catch {
      setFailure('Preview unavailable. No source or ROM was generated.');
    } finally {
      setBusy(false);
    }
  };

  const generate = async () => {
    if (busy || !isEditor || !attested || !approved || !title.trim() ||
        !/^[A-Za-z][A-Za-z0-9 ._'!-]{2,79}$/.test(title.trim()) || targets.length < 1 ||
        targets.length > MAX_TARGETS || !targets.every(id =>
          eligible.some(item => item.id === id))) return;
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    setFailure('');
    setSuccess('');
    try {
      if (!getAuthToken()) {
        throw new Error('An authenticated editor session is required for source exports.');
      }
      const response = await fetch(ENDPOINT + '/source-bundle', {
        method: 'POST',
        headers: authHeaders({ 'Content-Type': 'application/json' }),
        signal: controller.signal,
        cache: 'no-store',
        body: JSON.stringify(sourcePayload(true)),
      });
      if (!response.ok) {
        throw new Error(response.status === 401 || response.status === 403
          ? 'Creator authorization was rejected. Sign in with an editor account.'
          : 'The selected native game platforms could not be exported.');
      }
      if (!response.headers.get('content-type')?.includes('application/zip') ||
          response.headers.get('x-dragon-claim') !== 'source-only-not-a-compiled-game') {
        throw new Error('Unexpected response: a verified source-only ZIP is required.');
      }
      const declared = Number(response.headers.get('content-length') || 0);
      if (declared > MAX_DOWNLOAD_BYTES) {
        throw new Error('The native source archive exceeds the output limit.');
      }
      const blob = await response.blob();
      if (controller.signal.aborted) return;
      const identity = response.headers.get('x-dragon-request-id') || '';
      if (!/^[a-f0-9]{64}$/.test(identity)) {
        throw new Error('Source bundle lacks canonical production identity.');
      }
      await saveBundle(blob, 'dragon-original-' + identity.slice(0, 20) + '.zip');
      if (!controller.signal.aborted) {
        setSuccess('Original source ZIP delivered. Compile with an authorized local toolchain. Emulator and hardware playtesting are still required.');
      }
    } catch {
      if (!controller.signal.aborted) {
        setFailure('The source archive could not be delivered. No completed game or ROM was produced.');
      }
    } finally {
      if (!controller.signal.aborted) setBusy(false);
    }
  };

  return (
    <SafeAreaView style={stylesUi.root}>
      <ScrollView contentContainerStyle={stylesUi.page}>
        <TouchableOpacity accessibilityRole="button" onPress={() => router.back()}>
          <Text style={stylesUi.link}>‹ Back to Studio</Text>
        </TouchableOpacity>
        <Text style={stylesUi.heading}>Dragon Native Homebrew</Text>
        <Text style={stylesUi.copy}>
          Build original game source for actual console and PC toolchains.
          This is not an HTML imitation or a precompiled ROM. Supported
          gameplay differs by hardware.
        </Text>
        {!isEditor && (
          <Text accessibilityRole="alert" style={stylesUi.warning}>
            Native source export requires a signed-in editor or administrator.
          </Text>
        )}
        <Text style={stylesUi.label}>Game title</Text>
        <TextInput testID="dragon-native-title" style={stylesUi.input}
          value={title} onChangeText={value => { setTitle(value); setSuccess(''); }}
          maxLength={80} editable={!busy}
          placeholder="Original homebrew title" placeholderTextColor="#8895a6" />
        <Text style={stylesUi.label}>Implemented gameplay styles</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={stylesUi.chips}>
          {styles.map(item => (
            <TouchableOpacity key={item} accessibilityRole="button"
              accessibilityState={{ selected: item === style }}
              disabled={busy} onPress={() => chooseStyle(item)}
              style={[stylesUi.chip, item === style && stylesUi.selected]}>
              <Text style={stylesUi.chipText}>{formatStyle(item)}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
        <Text style={stylesUi.label}>Choose up to {MAX_TARGETS} supported targets ({targets.length} selected)</Text>
        <Text style={stylesUi.hint}>
          Only platforms with a real existing emitter for this gameplay mode are selectable.
          An emitter alone does not prove that a ROM or a game has compiled.
        </Text>
        {loading && <ActivityIndicator color="#70bd9c" />}
        {!loading && eligible.length === 0 &&
          <Text style={stylesUi.warning}>No native source emitters for this style.</Text>}
        {eligible.map(item => (
          <TouchableOpacity key={item.id} accessibilityRole="checkbox"
            accessibilityState={{ checked: targets.includes(item.id),
              disabled: busy || (!targets.includes(item.id) && targets.length >= MAX_TARGETS) }}
            disabled={busy || (!targets.includes(item.id) && targets.length >= MAX_TARGETS)}
            onPress={() => chooseTarget(item.id)} style={stylesUi.platform}>
            <Text style={stylesUi.platformTitle}>
              {targets.includes(item.id) ? '☑ ' : '☐ '}{item.id.replace(/_/g, ' ')}
            </Text>
            <Text style={stylesUi.hint}>
              {item.family} · {item.toolchain} ·
              {item.local_verified_rom_compiler ? ' local ROM toolchain adapter' : ' source generator only'}
            </Text>
          </TouchableOpacity>
        ))}

        <Text style={stylesUi.label}>Game design controls</Text>
        <Text style={stylesUi.hint}>
          These controls are applied where the destination emitter implements them.
          Retro cartridge emitters use one stage and one candidate and may not
          apply the protagonist, theme, palette or difficulty visually.
          The release receipt records these adaptations.
        </Text>
        <Text style={stylesUi.label}>Protagonist</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={stylesUi.chips}>
          {HEROES.map(item => (
            <TouchableOpacity key={item} accessibilityRole="button"
              accessibilityState={{ selected: hero === item }} disabled={busy}
              onPress={() => setHero(item)}
              style={[stylesUi.chip, hero === item && stylesUi.selected]}>
              <Text style={stylesUi.chipText}>{formatStyle(item)}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
        <Text style={stylesUi.label}>World theme</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={stylesUi.chips}>
          {THEMES.map(item => (
            <TouchableOpacity key={item} accessibilityRole="button"
              accessibilityState={{ selected: questTheme === item }} disabled={busy}
              onPress={() => setQuestTheme(item)}
              style={[stylesUi.chip, questTheme === item && stylesUi.selected]}>
              <Text style={stylesUi.chipText}>{formatStyle(item)}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
        <Text style={stylesUi.label}>Color palette</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={stylesUi.chips}>
          {PALETTES.map(item => (
            <TouchableOpacity key={item} accessibilityRole="button"
              accessibilityState={{ selected: palette === item }} disabled={busy}
              onPress={() => setPalette(item)}
              style={[stylesUi.chip, palette === item && stylesUi.selected]}>
              <Text style={stylesUi.chipText}>{formatStyle(item)}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>
        {([
          ['Difficulty', difficulty, 1, 10, setDifficulty],
          ['Campaign stages', stageCount, 1, 8, setStageCount],
          ['Candidate search budget', searchBudget, 1, 24, setSearchBudget],
        ] as const).map(([name, value, low, high, setter]) => (
          <View style={stylesUi.counter} key={name}>
            <View style={{ flex: 1 }}>
              <Text style={stylesUi.label}>{name}</Text>
              <Text style={stylesUi.hint}>{value} / {high}</Text>
            </View>
            <TouchableOpacity accessibilityRole="button"
              accessibilityLabel={'Reduce ' + name} disabled={busy || value <= low}
              style={stylesUi.counterButton} onPress={() => setter(
                Math.max(low, value - 1))}>
              <Text style={stylesUi.actionText}>−</Text>
            </TouchableOpacity>
            <TouchableOpacity accessibilityRole="button"
              accessibilityLabel={'Increase ' + name} disabled={busy || value >= high}
              style={stylesUi.counterButton} onPress={() => setter(
                Math.min(high, value + 1))}>
              <Text style={stylesUi.actionText}>+</Text>
            </TouchableOpacity>
          </View>
        ))}
        {usesCartridgeTargets && (
          <Text style={stylesUi.warning}>
            Cartridge adaptation: one stage and one candidate per original
            console template. Full cinematic campaigns, character/theme
            customization and equivalent cross-console mechanics are not claimed.
          </Text>
        )}
        {usesDesktopTargets && (
          <Text style={stylesUi.hint}>
            Desktop targets use the requested seed and bounded stage, candidate,
            difficulty, world theme and hero settings where implemented.
          </Text>
        )}

        <TouchableOpacity accessibilityRole="checkbox"
          accessibilityState={{ checked: attested }} disabled={busy}
          style={stylesUi.consent} onPress={() => setAttested(!attested)}>
          <Text style={stylesUi.copy}>
            {attested ? '☑ ' : '☐ '}I attest this project uses my original work,
            or content I am authorized to use. This is not legal clearance.
          </Text>
        </TouchableOpacity>
        <TouchableOpacity accessibilityRole="checkbox"
          accessibilityState={{ checked: approved }} disabled={busy}
          style={stylesUi.consent} onPress={() => setApproved(!approved)}>
          <Text style={stylesUi.copy}>
            {approved ? '☑ ' : '☐ '}I authorize generation of these native source artifacts.
          </Text>
        </TouchableOpacity>

        <TouchableOpacity accessibilityRole="button"
          testID="dragon-native-preview"
          disabled={busy || loading || !isEditor || !attested ||
            targets.length < 1 || !title.trim()}
          style={[stylesUi.counterButton, { padding: 13 },
            (busy || !isEditor || !attested || loading) && stylesUi.disabled]}
          onPress={previewTargets}>
          <Text style={stylesUi.actionText}>Preview hardware adaptations (no build)</Text>
        </TouchableOpacity>
        {preview && (
          <View style={stylesUi.preview}>
            <Text style={stylesUi.label}>Source-only readiness</Text>
            <Text style={preview.can_export_sources ? stylesUi.ok : stylesUi.warning}>
              {preview.can_export_sources ? 'All selected source emitters available' : 'At least one target is blocked'}
            </Text>
            {preview.targets.map(item => (
              <View key={item.target} style={stylesUi.platform}>
                <Text style={stylesUi.platformTitle}>
                  {item.target.replace(/_/g, ' ')} · {item.state.replace(/_/g, ' ')}
                </Text>
                <Text style={stylesUi.hint}>{item.reason}</Text>
                {item.target_palette && (
                  <Text style={stylesUi.hint}>
                    Actual palette: {formatStyle(item.target_palette)}
                    {' · '}stages: {item.target_stages}
                    {' · '}candidates: {item.target_candidates}
                  </Text>
                )}
                {item.adaptations.map(adaptation => (
                  <Text key={adaptation} style={stylesUi.warning}>
                    Adaptation: {formatStyle(adaptation)}
                  </Text>
                ))}
              </View>
            ))}
            <Text style={stylesUi.hint}>
              Preview estimates source feasibility only. It does not create,
              compile, execute or legally approve a game.
            </Text>
          </View>
        )}

        <TouchableOpacity accessibilityRole="button" testID="dragon-native-export"
          disabled={busy || loading || !isEditor || !attested || !approved ||
            targets.length < 1 || !title.trim()}
          style={[stylesUi.action, (busy || !isEditor || !attested || !approved ||
            targets.length < 1 || loading) && stylesUi.disabled]} onPress={generate}>
          <Text style={stylesUi.actionText}>
            {busy ? 'Generating source ZIP…' : 'Generate original native source ZIP'}
          </Text>
        </TouchableOpacity>
        {failure ? <Text accessibilityRole="alert" style={stylesUi.warning}>{failure}</Text> : null}
        {success ? <Text accessibilityRole="alert" style={stylesUi.ok}>{success}</Text> : null}
        <Text style={stylesUi.hint}>
          Your source ZIP is produced in memory and returned directly to this device.
          The app does not compile console binaries, approve third-party rights,
          promote Dragon knowledge, or grant progression XP.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

export default function DragonNativeProductionRoute() {
  return <StudioLoginGate><NativeSourceEditor /></StudioLoginGate>;
}

const stylesUi = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0c1420' },
  page: { padding: 20, gap: 13, paddingBottom: 42, maxWidth: 940, width: '100%', alignSelf: 'center' },
  heading: { fontSize: 26, color: '#e5f4ed', fontWeight: '700' },
  label: { fontWeight: '700', fontSize: 16, color: '#d5e7dc', marginTop: 10 },
  copy: { fontSize: 14, lineHeight: 21, color: '#c2d3cd' },
  hint: { fontSize: 12, lineHeight: 19, color: '#9aaabb' },
  link: { fontSize: 15, color: '#9fddbc', paddingVertical: 8 },
  chips: { gap: 8, paddingVertical: 8 },
  chip: { borderRadius: 16, paddingHorizontal: 12, paddingVertical: 9, backgroundColor: '#253d4b' },
  selected: { backgroundColor: '#416d58' },
  chipText: { fontSize: 13, color: '#effff7' },
  input: { borderWidth: 1, borderColor: '#45675b', borderRadius: 10,
    padding: 12, color: '#f7fffc', backgroundColor: '#182833' },
  platform: { backgroundColor: '#192a34', borderRadius: 12, padding: 12, gap: 5 },
  preview: { backgroundColor: '#142834', borderWidth: 1, borderColor: '#345660',
    borderRadius: 14, padding: 14, gap: 10 },
  counter: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 4 },
  counterButton: { backgroundColor: '#326f56', borderRadius: 10, minWidth: 42,
    padding: 10, alignItems: 'center' },
  platformTitle: { fontWeight: '700', color: '#e4f7ec', fontSize: 15 },
  consent: { padding: 14, borderRadius: 12, backgroundColor: '#1d3540' },
  action: { backgroundColor: '#326f56', borderRadius: 12, alignItems: 'center', padding: 15 },
  disabled: { opacity: 0.45 },
  actionText: { fontWeight: '700', color: '#fff' },
  warning: { color: '#f6bab1', fontSize: 14, lineHeight: 22 },
  ok: { color: '#aff2c8', fontSize: 14, lineHeight: 22 },
});
