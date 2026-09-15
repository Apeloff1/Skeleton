/**
 * /asset-genesis — Asset Genesis Forge (2026).
 *
 * Pipeline stage between Narrative/Mechanics Forge → Implementation: turns a brief
 * into REAL AI-generated, game-ready art (Nano Banana) — single assets or a coherent
 * style-matched PACK (player / enemy / item / background). Assets persist to a gallery
 * and can be grounded in a game's world+narrative (the Central Game Knowledge Base).
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator, StyleSheet,
  SafeAreaView, TextInput, Image, RefreshControl, useWindowDimensions, Linking,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Opt = { id: string; hint: string };
type Styles = { kinds: Opt[]; styles: Opt[]; palettes: Opt[]; default_pack: string[] };
type AssetRow = { asset_id: string; kind: string; description: string; created_at: string; pack_id?: string };
type PackItem = { kind: string; ok: boolean; data_uri: string | null; asset_id: string | null };

const KIND_EMOJI: Record<string, string> = {
  character: '🦸', enemy: '👾', item: '💎', tileset: '🧱', background: '🌄',
  keyart: '🖼️', icon: '🔶', prop: '📦',
};

export default function AssetGenesis() {
  const router = useRouter();
  const params = useLocalSearchParams<{ game?: string }>();
  const haptics = useHaptics();
  const { width } = useWindowDimensions();

  const [opts, setOpts] = React.useState<Styles | null>(null);
  const [desc, setDesc] = React.useState('a brave fox knight with a tiny sword');
  const [kind, setKind] = React.useState('character');
  const [style, setStyle] = React.useState('flat_vector');
  const [palette, setPalette] = React.useState('vibrant');
  const [packMode, setPackMode] = React.useState(false);

  const [busy, setBusy] = React.useState(false);
  const [status, setStatus] = React.useState('');
  const [single, setSingle] = React.useState<string | null>(null); // data_uri
  const [pack, setPack] = React.useState<PackItem[]>([]);

  const [gallery, setGallery] = React.useState<AssetRow[]>([]);
  const [refreshing, setRefreshing] = React.useState(false);

  // Ground-in-a-game + apply-to-game (in-game art injector)
  const [games, setGames] = React.useState<{ playable_id: string; title: string }[]>([]);
  const [gameId, setGameId] = React.useState<string | null>(null);
  const [applying, setApplying] = React.useState(false);
  const [applyStatus, setApplyStatus] = React.useState('');
  const gameTitle = games.find(g => g.playable_id === gameId)?.title || gameCtx?.title || '';
  const [gameCtx, setGameCtx] = React.useState<any>(null);
  const [selected, setSelected] = React.useState<Record<string, string>>({});

  const loadGameCtx = React.useCallback(async (gid: string) => {
    setGameCtx(null);
    const r = await api.get<any>(`/api/assets/genesis/game/${gid}`, { timeoutMs: 12000 });
    if (r.ok && r.data) setGameCtx(r.data);
  }, []);
  React.useEffect(() => { if (gameId) loadGameCtx(gameId); else setGameCtx(null); }, [gameId, loadGameCtx]);
  React.useEffect(() => { if (params?.game) setGameId(String(params.game)); }, [params?.game]);

  const loadGames = React.useCallback(async () => {
    const r = await api.get<{ playables: any[] }>('/api/playable/list', { timeoutMs: 12000 });
    if (r.ok && r.data) {
      const ready = (r.data.playables || [])
        .filter((p: any) => p.status === 'ready')
        .slice(0, 14)
        .map((p: any) => ({ playable_id: p.playable_id, title: p.title || 'Untitled' }));
      setGames(ready);
    }
  }, []);

  const loadStyles = React.useCallback(async () => {
    const r = await api.get<Styles>('/api/assets/genesis/styles', { timeoutMs: 12000 });
    if (r.ok && r.data) setOpts(r.data);
  }, []);

  const loadGallery = React.useCallback(async () => {
    const r = await api.get<{ assets: AssetRow[] }>('/api/assets/genesis/list?limit=40', { timeoutMs: 12000 });
    if (r.ok && r.data) setGallery(r.data.assets || []);
  }, []);

  React.useEffect(() => { loadStyles(); loadGallery(); loadGames(); }, [loadStyles, loadGallery, loadGames]);

  const onRefresh = React.useCallback(async () => {
    setRefreshing(true); await loadGallery(); setRefreshing(false);
  }, [loadGallery]);

  const poll = React.useCallback(async (jobId: string, isPack: boolean) => {
    const t0 = Date.now();
    for (let i = 0; i < 60; i++) {
      await new Promise(r => setTimeout(r, 3000));
      const r = await api.get<any>(`/api/assets/genesis/job/${jobId}`, { timeoutMs: 12000 });
      const d = r.data || {};
      const secs = Math.round((Date.now() - t0) / 1000);
      if (d.status === 'error' || r.status >= 500) {
        setStatus(`❌ ${d.error || 'generation failed'}`); return false;
      }
      if (isPack) {
        setStatus(`🎨 Forging pack… ${d.done || 0}/${d.total || 0} (${secs}s)`);
        if (d.status === 'done') {
          setPack(d.items || []); setStatus(`✅ Pack ready (${d.elapsed || secs}s)`); return true;
        }
      } else {
        setStatus(`🎨 Generating… ${secs}s`);
        if (d.status === 'done' && d.data_uri) {
          setSingle(d.data_uri); setStatus(`✅ Done (${d.elapsed || secs}s)`); return true;
        }
      }
    }
    setStatus('⌛ Timed out — check the gallery shortly.'); return false;
  }, []);

  const generate = React.useCallback(async () => {
    if (!desc.trim()) { setStatus('Enter a description first.'); return; }
    haptics.impact?.('medium');
    setBusy(true); setSingle(null); setPack([]); setStatus('Submitting…');
    const path = packMode ? '/api/assets/genesis/pack/async' : '/api/assets/genesis/async';
    const body: any = { description: desc.trim(), style, palette };
    if (!packMode) body.kind = kind;
    if (gameId) body.game_id = gameId;
    const r = await api.post<any>(path, body, { timeoutMs: 15000 });
    if (!r.ok || !r.data?.job_id) {
      setStatus(`❌ ${r.data?.error || r.error || 'could not start'}`); setBusy(false); return;
    }
    await poll(r.data.job_id, packMode);
    await loadGallery();
    setBusy(false);
  }, [desc, kind, style, palette, packMode, gameId, poll, loadGallery, haptics]);

  const applyToGame = React.useCallback(async () => {
    if (!gameId) return;
    haptics.impact?.('medium');
    setApplying(true); setApplyStatus('Submitting…');
    const sel = Object.keys(selected).length ? selected : undefined;
    const r = await api.post<any>(`/api/playable/${gameId}/apply-assets/async`, { selected: sel }, { timeoutMs: 15000 });
    if (!r.ok || !r.data?.job_id) {
      setApplyStatus(`❌ ${r.data?.error || r.error || 'could not start'}`); setApplying(false); return;
    }
    const jobId = r.data.job_id;
    const t0 = Date.now();
    for (let i = 0; i < 60; i++) {
      await new Promise(res => setTimeout(res, 4000));
      const jr = await api.get<any>(`/api/playable/job/${jobId}`, { timeoutMs: 12000 });
      const d = jr.data || {};
      const secs = Math.round((Date.now() - t0) / 1000);
      if (d.job_status === 'error') { setApplyStatus(`❌ ${d.error || 'apply failed'}`); break; }
      if (d.job_status === 'done') {
        if (d.applied) setApplyStatus(`✅ Art applied → v${d.version} (${(d.applied_keys || []).join(', ')}). Open the game to see it!`);
        else setApplyStatus(`⚠️ Could not apply cleanly (${d.error || 'kept original'}).`);
        break;
      }
      setApplyStatus(`🎮 Wiring art into the game… ${secs}s`);
    }
    setApplying(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gameId, haptics]);

  const openGame = React.useCallback(() => {
    if (gameId) Linking.openURL(`${BACKEND}/api/playable/${gameId}/raw`);
  }, [gameId]);

  // One-tap: generate a full coherent pack grounded in the game, then skin the game.
  const generateAndSkin = React.useCallback(async () => {
    if (!gameId) return;
    haptics.impact?.('heavy');
    setBusy(true); setSingle(null); setPack([]);
    setStatus('🎒 Forging a matched asset pack…');
    const r = await api.post<any>('/api/assets/genesis/pack/async',
      { description: desc.trim() || gameTitle, style, palette, game_id: gameId }, { timeoutMs: 15000 });
    if (!r.ok || !r.data?.job_id) { setStatus(`❌ ${r.data?.error || 'pack failed'}`); setBusy(false); return; }
    const ok = await poll(r.data.job_id, true);
    await loadGallery();
    setBusy(false);
    if (ok) { await loadGameCtx(gameId); setStatus('✅ Pack ready — now skinning the game…'); await applyToGame(); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gameId, desc, gameTitle, style, palette, poll, loadGallery, loadGameCtx, haptics]);

  const Chip = ({ id, active, onPress, label }: { id: string; active: boolean; onPress: () => void; label: string }) => (
    <TouchableOpacity key={id} testID={`ag-chip-${id}`} onPress={onPress}
      style={[s.chip, active && s.chipActive]} activeOpacity={0.85}>
      <Text style={[s.chipTxt, active && s.chipTxtActive]}>{label}</Text>
    </TouchableOpacity>
  );

  const previewW = Math.min(width - 32, 360);
  const thumb = (width - 32 - 24) / 3;

  return (
    <SafeAreaView style={s.safe} testID="asset-genesis-screen">
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="ag-back" style={s.backBtn} hitSlop={{ top: 12, bottom: 12, left: 12, right: 12 }}>
          <Text style={s.backTxt}>‹ Back</Text>
        </TouchableOpacity>
        <Text style={s.title}>🎨 Asset Genesis</Text>
        <View style={{ width: 54 }} />
      </View>

      <ScrollView style={s.body} contentContainerStyle={{ paddingBottom: 48 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor="#A78BFA" />}>

        <Text style={s.sub}>Generate real, game-ready art — single assets or a coherent style-matched pack.</Text>

        {/* Ground in a game (optional) */}
        {games.length > 0 && (
          <View testID="ag-game-picker">
            <Text style={s.label}>🎮 Ground in a game (optional)</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 2 }}>
              <TouchableOpacity testID="ag-game-none" onPress={() => setGameId(null)}
                style={[s.chip, !gameId && s.chipActive]} activeOpacity={0.85}>
                <Text style={[s.chipTxt, !gameId && s.chipTxtActive]}>None</Text>
              </TouchableOpacity>
              {games.map(g => (
                <TouchableOpacity key={g.playable_id} testID={`ag-game-${g.playable_id}`}
                  onPress={() => setGameId(g.playable_id)}
                  style={[s.chip, gameId === g.playable_id && s.chipActive]} activeOpacity={0.85}>
                  <Text style={[s.chipTxt, gameId === g.playable_id && s.chipTxtActive]} numberOfLines={1}>
                    {g.title.slice(0, 22)}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
            {!!gameId && <Text style={s.groundHint}>Art will be styled for & linked to “{gameTitle}”.</Text>}
          </View>
        )}

        <Text style={s.label}>Describe the asset</Text>
        <TextInput testID="ag-desc" value={desc} onChangeText={setDesc} multiline
          placeholder="e.g. a neon cyber-samurai with a glowing katana"
          placeholderTextColor="#64748B" style={s.input} />

        {/* Pack toggle */}
        <View style={s.row}>
          <TouchableOpacity testID="ag-mode-single" onPress={() => setPackMode(false)}
            style={[s.modeBtn, !packMode && s.modeBtnActive]} activeOpacity={0.85}>
            <Text style={[s.modeTxt, !packMode && s.modeTxtActive]}>Single asset</Text>
          </TouchableOpacity>
          <TouchableOpacity testID="ag-mode-pack" onPress={() => setPackMode(true)}
            style={[s.modeBtn, packMode && s.modeBtnActive]} activeOpacity={0.85}>
            <Text style={[s.modeTxt, packMode && s.modeTxtActive]}>🎒 Full pack</Text>
          </TouchableOpacity>
        </View>

        {!packMode && (
          <>
            <Text style={s.label}>Kind</Text>
            <View style={s.chipWrap}>
              {(opts?.kinds || []).map(k => (
                <Chip key={k.id} id={k.id} active={kind === k.id} onPress={() => setKind(k.id)}
                  label={`${KIND_EMOJI[k.id] || '•'} ${k.id}`} />
              ))}
            </View>
          </>
        )}
        {packMode && (
          <Text style={s.packHint}>Forges a matched set: {(opts?.default_pack || []).join(' · ')}</Text>
        )}

        <Text style={s.label}>Art style</Text>
        <View style={s.chipWrap}>
          {(opts?.styles || []).map(k => (
            <Chip key={k.id} id={`style-${k.id}`} active={style === k.id} onPress={() => setStyle(k.id)}
              label={k.id.replace('_', ' ')} />
          ))}
        </View>

        <Text style={s.label}>Palette</Text>
        <View style={s.chipWrap}>
          {(opts?.palettes || []).map(k => (
            <Chip key={k.id} id={`pal-${k.id}`} active={palette === k.id} onPress={() => setPalette(k.id)}
              label={k.id} />
          ))}
        </View>

        <TouchableOpacity testID="ag-generate" onPress={generate} disabled={busy}
          style={[s.cta, busy && s.ctaDisabled]} activeOpacity={0.9}>
          {busy ? <ActivityIndicator color="#fff" /> : (
            <Text style={s.ctaTxt}>{packMode ? '✨ Forge asset pack' : '✨ Generate asset'}</Text>
          )}
        </TouchableOpacity>

        {!!status && <Text testID="ag-status" style={s.status}>{status}</Text>}

        {/* Single result */}
        {single && (
          <View style={s.resultCard} testID="ag-result-single">
            <Image source={{ uri: single }} style={{ width: previewW, height: previewW, borderRadius: 14 }} resizeMode="contain" />
          </View>
        )}

        {/* Pack result */}
        {pack.length > 0 && (
          <View style={s.packGrid} testID="ag-result-pack">
            {pack.map((it, i) => (
              <View key={i} style={[s.packCell, { width: (previewW - 12) / 2 }]}>
                <Text style={s.packKind}>{KIND_EMOJI[it.kind] || '•'} {it.kind}</Text>
                {it.data_uri
                  ? <Image source={{ uri: it.data_uri }} style={{ width: (previewW - 12) / 2 - 16, height: (previewW - 12) / 2 - 16, borderRadius: 10 }} resizeMode="contain" />
                  : <Text style={s.packFail}>failed</Text>}
              </View>
            ))}
          </View>
        )}

        {/* Apply linked art to the selected game (in-game art injector) */}
        {!!gameId && (
          <View style={s.applyCard} testID="ag-apply-card">
            <View style={s.applyHeadRow}>
              <Text style={s.applyTitle}>🎮 {gameTitle}</Text>
              {!!gameCtx?.tag && (
                <View testID="ag-asset-tag" style={[s.tag,
                  gameCtx.asset_status === 'complete' ? s.tagDone : gameCtx.asset_status === 'partial' ? s.tagPartial : s.tagNone]}>
                  <Text style={s.tagTxt}>{gameCtx.tag}</Text>
                </View>
              )}
            </View>
            {!!gameCtx && (
              <View style={s.slotRow}>
                {(gameCtx.required_kinds || []).map((k: string) => {
                  const has = (gameCtx.generated_kinds || []).includes(k);
                  return (
                    <View key={k} style={[s.slot, has && s.slotOn]}>
                      <Text style={[s.slotTxt, has && s.slotTxtOn]}>{has ? '✓' : '○'} {KIND_EMOJI[k] || ''}{k}</Text>
                    </View>
                  );
                })}
              </View>
            )}

            {/* Per-slot asset picker — pin a specific asset per kind */}
            {!!gameCtx && (gameCtx.assets || []).length > 0 && (
              <View testID="ag-slot-picker" style={{ marginTop: 12 }}>
                {(gameCtx.required_kinds || []).map((k: string) => {
                  const opts = (gameCtx.assets || []).filter((a: any) => a.kind === k);
                  if (opts.length === 0) return null;
                  const chosen = selected[k] || opts[0].asset_id;
                  return (
                    <View key={k} style={{ marginBottom: 8 }}>
                      <Text style={s.pickKind}>{KIND_EMOJI[k] || '•'} {k}{opts.length > 1 ? `  (${opts.length})` : ''}</Text>
                      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
                        {opts.map((a: any) => {
                          const on = a.asset_id === chosen;
                          return (
                            <TouchableOpacity key={a.asset_id} testID={`ag-pick-${a.asset_id}`}
                              onPress={() => setSelected(prev => ({ ...prev, [k]: a.asset_id }))} activeOpacity={0.85}>
                              <Image source={{ uri: `${BACKEND}/api/assets/genesis/${a.asset_id}.png` }}
                                style={[s.pickThumb, on && s.pickThumbOn]} resizeMode="cover" />
                            </TouchableOpacity>
                          );
                        })}
                      </ScrollView>
                    </View>
                  );
                })}
              </View>
            )}
            {!!gameCtx?.files && (
              <Text style={s.filesLine}>📁 files: {(gameCtx.files || []).map((f: any) => f.name).join(' · ')}</Text>
            )}

            <TouchableOpacity testID="ag-gen-skin-btn" onPress={generateAndSkin} disabled={busy || applying}
              style={[s.applyBtn, s.skinBtn, (busy || applying) && s.ctaDisabled]} activeOpacity={0.9}>
              {busy ? <ActivityIndicator color="#fff" /> : <Text style={s.applyBtnTxt}>⚡ Generate full pack + skin game</Text>}
            </TouchableOpacity>
            <TouchableOpacity testID="ag-apply-btn" onPress={applyToGame} disabled={applying || busy}
              style={[s.applyBtnGhost, (applying || busy) && s.ctaDisabled]} activeOpacity={0.9}>
              {applying ? <ActivityIndicator color="#C4B5FD" /> : <Text style={s.applyGhostTxt}>🎨 Apply existing art only</Text>}
            </TouchableOpacity>
            {!!applyStatus && <Text testID="ag-apply-status" style={s.status}>{applyStatus}</Text>}
            {applyStatus.startsWith('✅') && (
              <TouchableOpacity testID="ag-open-game" onPress={openGame} style={s.openBtn} activeOpacity={0.85}>
                <Text style={s.openBtnTxt}>▶ Open game</Text>
              </TouchableOpacity>
            )}
          </View>
        )}

        {/* Gallery */}
        <View style={s.galleryHead}>
          <Text style={s.galleryTitle}>🖼 Recent assets</Text>
          <Text style={s.galleryCount}>{gallery.length}</Text>
        </View>
        {gallery.length === 0 ? (
          <Text testID="ag-gallery-empty" style={s.empty}>No assets yet — forge your first above.</Text>
        ) : (
          <View style={s.galleryGrid}>
            {gallery.map(a => (
              <View key={a.asset_id} testID={`ag-asset-${a.asset_id}`} style={[s.gCell, { width: thumb }]}>
                <Image source={{ uri: `${BACKEND}/api/assets/genesis/${a.asset_id}.png` }}
                  style={{ width: thumb - 12, height: thumb - 12, borderRadius: 8, backgroundColor: '#1E293B' }} resizeMode="cover" />
                <Text style={s.gKind} numberOfLines={1}>{KIND_EMOJI[a.kind] || '•'} {a.kind}</Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#0B1020' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#1E293B',
  },
  backBtn: { paddingVertical: 6, minWidth: 54 },
  backTxt: { color: '#A78BFA', fontSize: 16, fontWeight: '600' },
  title: { color: '#F1F5F9', fontSize: 18, fontWeight: '800' },
  body: { flex: 1, paddingHorizontal: 16 },
  sub: { color: '#94A3B8', fontSize: 13, marginTop: 14, marginBottom: 8, lineHeight: 18 },
  label: { color: '#CBD5E1', fontSize: 13, fontWeight: '700', marginTop: 16, marginBottom: 8 },
  input: {
    backgroundColor: '#131A2E', borderRadius: 12, borderWidth: 1, borderColor: '#27324A',
    color: '#F1F5F9', padding: 14, fontSize: 15, minHeight: 56, textAlignVertical: 'top',
  },
  row: { flexDirection: 'row', gap: 10, marginTop: 16 },
  modeBtn: {
    flex: 1, paddingVertical: 12, borderRadius: 12, alignItems: 'center',
    backgroundColor: '#131A2E', borderWidth: 1, borderColor: '#27324A', minHeight: 44, justifyContent: 'center',
  },
  modeBtnActive: { backgroundColor: '#8B5CF620', borderColor: '#8B5CF6' },
  modeTxt: { color: '#94A3B8', fontWeight: '700', fontSize: 14 },
  modeTxtActive: { color: '#C4B5FD' },
  packHint: { color: '#A78BFA', fontSize: 13, marginTop: 12, fontStyle: 'italic' },
  groundHint: { color: '#A78BFA', fontSize: 12, marginTop: 8 },
  applyCard: { marginTop: 22, backgroundColor: '#131A2E', borderRadius: 16, padding: 16, borderWidth: 1, borderColor: '#3B2A66' },
  applyHeadRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 },
  applyTitle: { color: '#F1F5F9', fontSize: 15, fontWeight: '800', flexShrink: 1 },
  tag: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 12, borderWidth: 1 },
  tagDone: { backgroundColor: '#10B98122', borderColor: '#10B981' },
  tagPartial: { backgroundColor: '#F59E0B22', borderColor: '#F59E0B' },
  tagNone: { backgroundColor: '#33415522', borderColor: '#475569' },
  tagTxt: { color: '#E2E8F0', fontSize: 11, fontWeight: '800' },
  slotRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 12 },
  slot: { paddingHorizontal: 9, paddingVertical: 6, borderRadius: 10, backgroundColor: '#0E1626', borderWidth: 1, borderColor: '#27324A' },
  slotOn: { backgroundColor: '#10B98118', borderColor: '#10B981' },
  slotTxt: { color: '#64748B', fontSize: 11, fontWeight: '700' },
  slotTxtOn: { color: '#34D399' },
  filesLine: { color: '#64748B', fontSize: 11, marginTop: 10 },
  pickKind: { color: '#C4B5FD', fontSize: 11, fontWeight: '700', marginBottom: 5 },
  pickThumb: { width: 48, height: 48, borderRadius: 8, backgroundColor: '#0E1626', borderWidth: 2, borderColor: 'transparent' },
  pickThumbOn: { borderColor: '#8B5CF6' },
  applyHint: { color: '#94A3B8', fontSize: 12, marginTop: 6, marginBottom: 12, lineHeight: 17 },
  applyBtn: { backgroundColor: '#7C3AED', borderRadius: 12, paddingVertical: 14, alignItems: 'center', justifyContent: 'center', minHeight: 48 },
  skinBtn: { marginTop: 14 },
  applyBtnGhost: { marginTop: 10, borderRadius: 12, paddingVertical: 13, alignItems: 'center', justifyContent: 'center', minHeight: 46, borderWidth: 1, borderColor: '#7C3AED', backgroundColor: 'transparent' },
  applyGhostTxt: { color: '#C4B5FD', fontSize: 14, fontWeight: '700' },
  applyBtnTxt: { color: '#fff', fontSize: 15, fontWeight: '800' },
  openBtn: { marginTop: 12, borderRadius: 12, paddingVertical: 12, alignItems: 'center', backgroundColor: '#10B98120', borderWidth: 1, borderColor: '#10B981' },
  openBtnTxt: { color: '#34D399', fontSize: 14, fontWeight: '800' },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    paddingHorizontal: 14, paddingVertical: 9, borderRadius: 20, backgroundColor: '#131A2E',
    borderWidth: 1, borderColor: '#27324A', minHeight: 38, justifyContent: 'center',
  },
  chipActive: { backgroundColor: '#8B5CF620', borderColor: '#8B5CF6' },
  chipTxt: { color: '#94A3B8', fontSize: 13, fontWeight: '600' },
  chipTxtActive: { color: '#C4B5FD' },
  cta: {
    marginTop: 22, backgroundColor: '#8B5CF6', borderRadius: 14, paddingVertical: 16,
    alignItems: 'center', justifyContent: 'center', minHeight: 52,
  },
  ctaDisabled: { opacity: 0.6 },
  ctaTxt: { color: '#fff', fontSize: 16, fontWeight: '800' },
  status: { color: '#CBD5E1', fontSize: 13, marginTop: 14, textAlign: 'center' },
  resultCard: { marginTop: 18, alignItems: 'center', backgroundColor: '#131A2E', borderRadius: 16, padding: 12 },
  packGrid: { marginTop: 18, flexDirection: 'row', flexWrap: 'wrap', gap: 12, justifyContent: 'center' },
  packCell: { backgroundColor: '#131A2E', borderRadius: 14, padding: 8, alignItems: 'center' },
  packKind: { color: '#C4B5FD', fontSize: 12, fontWeight: '700', marginBottom: 6 },
  packFail: { color: '#EF4444', fontSize: 12, padding: 20 },
  galleryHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 30, marginBottom: 12 },
  galleryTitle: { color: '#F1F5F9', fontSize: 16, fontWeight: '800' },
  galleryCount: { color: '#64748B', fontSize: 14, fontWeight: '700' },
  empty: { color: '#64748B', fontSize: 13, textAlign: 'center', paddingVertical: 24 },
  galleryGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  gCell: { alignItems: 'center', marginBottom: 10 },
  gKind: { color: '#94A3B8', fontSize: 11, marginTop: 4, fontWeight: '600' },
});
