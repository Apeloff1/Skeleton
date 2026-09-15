/**
 * /worldforge — Cosmic-Scale Procedural World Engine (2026).
 *
 * Generate worlds across 5 scales (Region → Planet → System → Galaxy → Cosmos),
 * customise via a slider/toggle questionnaire (terrain + climate + palette +
 * structures: cities/harbors/observatories…), apply 100+ presets, forge a world FROM
 * a saved game's files (and save it back tagged WG), and read AI lore. Modern
 * 2026 visuals: atmosphere glow, gradient field, crisp relief.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  StyleSheet, SafeAreaView, TextInput, useWindowDimensions, RefreshControl, Modal, Platform, Image,
  Linking, Share,
} from 'react-native';
import Slider from '@react-native-community/slider';
import { useRouter } from 'expo-router';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

type Tile = { b: string; c: string };
type Dist = { biome: string; label: string; emoji: string; color: string; pct: number };
type Poi = { x: number; y: number; kind: string; icon: string; name: string };
type Stats = { tiles: number; biomes: number; land_pct: number; water_pct: number; river_tiles: number; lakes: number; settlements: number; koppen?: string; trade_routes?: number };
type Koppen = { code: string; name: string; summary: string; dominant_biome?: string };
type Bio = { index: number; rating: string; richness: number; evenness: number };
type Hazards = { overall: string; ratings: Record<string, { score: number; label: string }> };
type World = { scale: string; seed: number; size: number; name: string; palette: string; climate: string; grid: Tile[][]; distribution: Dist[]; pois: Poi[]; stats: Stats; koppen?: Koppen; routes?: any[]; biodiversity?: Bio; hazards?: Hazards; systems?: Record<string, any> };
type ScaleDef = { id: string; label: string; emoji: string; desc: string };
type GameSrc = { source: string; id: string; title: string; genre: string };

const COSMIC = new Set(['system', 'galaxy', 'cosmos']);
const MODE_LABELS: Record<string, string> = {
  cartographic: '🗺️ Map', atlas: '🛰️ Atlas', blueprint: '📐 Blueprint',
  globe: '🌍 Globe', spin: '🌀 Spin', nasa: '🌌 Galaxy', bloom: '✨ Bloom',
  photoreal: '✨ Photoreal',
};
const DEFAULT_MODES: Record<string, string[]> = {
  region: ['cartographic', 'atlas', 'blueprint'], planet: ['globe', 'spin'],
  system: ['nasa', 'bloom'], galaxy: ['nasa', 'bloom'], cosmos: ['nasa', 'bloom'],
};

export default function Worldforge() {
  const router = useRouter();
  const haptics = useHaptics();
  const { width } = useWindowDimensions();

  const [scales, setScales] = React.useState<ScaleDef[]>([]);
  const [scale, setScale] = React.useState('region');
  const [seedInput, setSeedInput] = React.useState('1337');
  const [cfg, setCfg] = React.useState<any>({
    seed: 1337, size: 44, palette: 'natural', climate: 'temperate',
    sea_level: 0.30, mountain_level: 0.72, moisture_bias: 0, temperature_bias: 0,
    river_density: 0.04, settlement_density: 1.0, features: {},
  });
  const [palettes, setPalettes] = React.useState<string[]>([]);
  const [climates, setClimates] = React.useState<string[]>([]);
  const [toggles, setToggles] = React.useState<{ key: string; icon: string }[]>([]);
  const [world, setWorld] = React.useState<World | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [lore, setLore] = React.useState<string | null>(null);
  const [loreLoading, setLoreLoading] = React.useState(false);
  const [nameKey, setNameKey] = React.useState<any>(null);
  const [nameKeyLoading, setNameKeyLoading] = React.useState(false);
  const [showSystems, setShowSystems] = React.useState(false);
  const [atlasLayer, setAtlasLayer] = React.useState('');
  const [showCustomize, setShowCustomize] = React.useState(false);
  const [showGames, setShowGames] = React.useState(false);
  const [games, setGames] = React.useState<GameSrc[]>([]);
  const [forging, setForging] = React.useState<string | null>(null);
  const [wgBadge, setWgBadge] = React.useState<string | null>(null);
  const skipGen = React.useRef(false);
  const [renderKey, setRenderKey] = React.useState(1);
  const [playMsg, setPlayMsg] = React.useState<string | null>(null);
  const [playing, setPlaying] = React.useState(false);
  const [renderModes, setRenderModes] = React.useState<Record<string, string[]>>(DEFAULT_MODES);
  const [mode, setMode] = React.useState('cartographic');
  const [zoom, setZoom] = React.useState(1);
  const [panX, setPanX] = React.useState(0);
  const [panY, setPanY] = React.useState(0);
  const [quest, setQuest] = React.useState<any>(null);
  const [questLoading, setQuestLoading] = React.useState(false);
  const [showQuest, setShowQuest] = React.useState(false);
  const [questArc, setQuestArc] = React.useState('');
  const [showMono, setShowMono] = React.useState(false);
  const [mono, setMono] = React.useState<any>(null);
  const [monoLoading, setMonoLoading] = React.useState(false);
  const [monoElapsed, setMonoElapsed] = React.useState(0);
  const [monoSaved, setMonoSaved] = React.useState(false);
  const [showPoster, setShowPoster] = React.useState(false);
  const [poster, setPoster] = React.useState<any>(null);
  const [posterLoading, setPosterLoading] = React.useState(false);
  const [posterElapsed, setPosterElapsed] = React.useState(0);
  const [posterStyle, setPosterStyle] = React.useState('satellite');
  const [posterSaved, setPosterSaved] = React.useState(false);
  const [photoImg, setPhotoImg] = React.useState<string | null>(null);
  const [photoLoading, setPhotoLoading] = React.useState(false);
  const [photoElapsed, setPhotoElapsed] = React.useState(0);
  const [showSim, setShowSim] = React.useState(false);
  const [sim, setSim] = React.useState<any>(null);
  const [simLoading, setSimLoading] = React.useState(false);

  // load option schema once
  React.useEffect(() => {
    (async () => {
      const o = await api.get<any>('/api/worldforge/options', { timeoutMs: 12000 });
      if (o.ok && o.data) {
        setScales(o.data.scales || []);
        setPalettes(o.data.palettes || []);
        setClimates(o.data.climates || []);
        setToggles((o.data.feature_toggles || []).map((t: any) => ({ key: t.key, icon: t.icon })));
        if (o.data.render_modes) setRenderModes(o.data.render_modes);
      }
    })();
  }, []);

  const generate = React.useCallback(async (overrideScale?: string, overrideCfg?: any) => {
    setLoading(true); setLore(null); setWgBadge(null); setRenderKey((k) => k + 1);
    const c = { ...cfg, ...(overrideCfg || {}) };
    const sc = overrideScale || scale;
    const body = { ...c, scale: sc, noise_scale: 0.08, rx: 0, ry: 0 };
    const r = await api.post<World>('/api/worldforge/world', body, { timeoutMs: 20000 });
    if (r.ok && r.data) setWorld(r.data);
    setLoading(false);
  }, [cfg, scale]);

  React.useEffect(() => { if (skipGen.current) { skipGen.current = false; return; } generate(); }, [scale]); // eslint-disable-line react-hooks/exhaustive-deps

  React.useEffect(() => {
    const list = renderModes[scale] || DEFAULT_MODES[scale] || ['cartographic'];
    setMode(list[0]); setZoom(1); setPanX(0); setPanY(0);
  }, [scale, renderModes]);  

  const applySeed = () => {
    const n = parseInt(seedInput, 10);
    haptics.selection();
    const seed = Number.isFinite(n) ? n : 1337;
    setCfg((c: any) => ({ ...c, seed })); generate(undefined, { seed });
  };
  const reroll = () => {
    const n = Math.floor(Math.random() * 9_000_000) + 1000;
    haptics.notify('success'); setSeedInput(String(n));
    setCfg((c: any) => ({ ...c, seed: n })); generate(undefined, { seed: n });
  };
  const setScaleAndGen = (s: string) => { haptics.selection(); setScale(s); };
  const toggleFeature = (k: string) => {
    haptics.selection();
    setCfg((c: any) => ({ ...c, features: { ...c.features, [k]: !c.features[k] } }));
  };
  const setParam = (k: string, v: number) => setCfg((c: any) => ({ ...c, [k]: v }));

  const genLore = async () => {
    haptics.notify('success'); setLoreLoading(true); setLore(null);
    const r = await api.post<{ lore?: string; error?: string }>('/api/worldforge/lore',
      { seed: cfg.seed, size: 40, world_scale: scale, palette: cfg.palette, climate: cfg.climate },
      { timeoutMs: 60000 });
    setLoreLoading(false);
    setLore(r.ok && r.data?.lore ? r.data.lore : (r.data?.error || 'Lore unavailable'));
  };

  const genNameKey = async () => {
    haptics.notify('success'); setNameKeyLoading(true); setNameKey(null);
    const r = await api.post<any>('/api/worldforge/name-key',
      { seed: cfg.seed, size: cfg.size, world_scale: scale, palette: cfg.palette, climate: cfg.climate },
      { timeoutMs: 20000 });
    setNameKeyLoading(false);
    setNameKey(r.ok && r.data ? r.data : { error: 'Name key unavailable' });
  };

  const playWorld = async () => {
    if (!world) return;
    haptics.notify('success'); setPlaying(true); setPlayMsg('🎮 Forging your playable from this world…');
    const top = world.distribution.slice(0, 4).map((d) => d.label).join(', ');
    const places = world.pois.slice(0, 3).map((p) => `${p.name} (${p.kind})`).join(', ');
    const brief = `A ${world.scale}-scale adventure set in ${world.name}, a world of ${top}.`
      + (places ? ` Key locations: ${places}.` : '')
      + ` Palette ${world.palette}, climate ${world.climate}. Build an explorable, juicy mini-game that captures this world.`;
    const r = await api.post<any>('/api/playable/generate/async',
      { brief, title: world.name, depth: 'studio', forged_from: world.name }, { timeoutMs: 20000 });
    if (!(r.ok && r.data?.job_id)) { setPlaying(false); setPlayMsg(r.data?.error || 'Could not start generation'); return; }
    const jid = r.data.job_id;
    let pid = '';
    for (let i = 0; i < 70; i++) {
      await new Promise((res) => setTimeout(res, 4000));
      const j = await api.get<any>(`/api/playable/job/${jid}`, { timeoutMs: 12000 });
      const d = j.data;
      if (d?.job_status === 'done' && (d.playable_id || d.status === 'ready')) { pid = d.playable_id; break; }
      if (d?.job_status === 'error' || (d?.job_status === 'done' && !d.playable_id)) break;
      if (i % 3 === 0) setPlayMsg(`🎮 Forging your playable from this world… (${i * 4}s)`);
    }
    setPlaying(false);
    if (!pid) { setPlayMsg('Generation is taking a while — check your library shortly.'); setTimeout(() => router.push('/playable' as any), 1200); return; }
    setPlayMsg('✨ Game ready — opening & auto-wiring living NPCs, physics & FX…');
    setTimeout(() => router.push({ pathname: '/playable', params: { id: pid, autopolish: '1' } } as any), 1200);
  };

  const openGames = async () => {
    setShowGames(true);
    const r = await api.get<{ games: GameSrc[] }>('/api/worldforge/sources?limit=30', { timeoutMs: 12000 });
    if (r.ok && r.data) setGames(r.data.games || []);
  };
  const forgeFromGame = async (g: GameSrc) => {
    haptics.notify('success'); setForging(g.id);
    const r = await api.post<any>('/api/worldforge/from-game',
      { source: g.source, source_id: g.id, save: true }, { timeoutMs: 25000 });
    setForging(null);
    if (r.ok && r.data?.world) {
      setShowGames(false);
      skipGen.current = true;        // don't let the scale-change effect overwrite the forged world
      const pc = r.data.parsed_config || {};
      const feats: any = {};
      (pc.features || []).forEach((f: string) => { feats[f] = true; });
      setCfg((c: any) => ({ ...c, seed: pc.seed ?? c.seed, palette: pc.palette ?? c.palette,
        climate: pc.climate ?? c.climate, features: feats, size: 56 }));
      setRenderKey((k) => k + 1);
      setWorld(r.data.world);
      setScale(r.data.world.scale);
      setLore(null);
      setWgBadge(r.data.saved ? `Saved to Vault as (WG) ${r.data.world.name}` : null);
    }
  };

  const mapW = Math.min(width - 32, 380);
  const isCosmic = COSMIC.has(scale);
  const featCsv = Object.keys(cfg.features || {}).filter((k) => cfg.features[k]).join(',');
  const modeList = renderModes[scale] || DEFAULT_MODES[scale] || ['cartographic'];
  const isPlanetSpin = scale === 'planet' && mode === 'spin';
  const atlasOn = !isCosmic && !!atlasLayer;
  const effMode = atlasOn ? 'thematic' : (scale === 'planet' ? 'globe' : mode);
  const canZoom = scale === 'region' || (scale === 'planet' && !isPlanetSpin);
  const commonParams = `scale=${scale}&seed=${cfg.seed}&size=${cfg.size}`
    + `&palette=${cfg.palette}&climate=${cfg.climate}&sea_level=${cfg.sea_level}`
    + `&mountain_level=${cfg.mountain_level}&moisture_bias=${cfg.moisture_bias}`
    + `&temperature_bias=${cfg.temperature_bias}&river_density=${cfg.river_density}`
    + `&settlement_density=${cfg.settlement_density}&features=${featCsv}`
    + `&mode=${effMode}&layer=${atlasLayer}&zoom=${zoom}&pan_x=${panX}&pan_y=${panY}`;
  const renderUrl = `${BACKEND}/api/worldforge/${isPlanetSpin && !atlasOn ? 'render.gif' : 'render'}?${commonParams}`
    + `&q=${renderKey}-${mode}-${atlasLayer}-${zoom}-${panX}-${panY}`;

  const zoomIn = () => { haptics.selection(); setZoom((z) => Math.min(8, +(z * 1.6).toFixed(2))); };
  const zoomOut = () => { haptics.selection(); setZoom((z) => Math.max(1, +(z / 1.6).toFixed(2))); };
  const resetView = () => { haptics.selection(); setZoom(1); setPanX(0); setPanY(0); };
  const panStep = Math.max(2, Math.round((cfg.size / zoom) / 3));
  const panBy = (dx: number, dy: number) => { haptics.selection(); setPanX((p) => p + dx * panStep); setPanY((p) => p + dy * panStep); };
  const shareWorld = async () => {
    if (!world) return;
    haptics.notify('success');
    const url = `${BACKEND}/api/worldforge/export?${commonParams}&name=${encodeURIComponent(world.name)}`;
    try {
      if (Platform.OS === 'web') await Linking.openURL(url);
      else await Share.share({ message: `${world.name} — forged in Worldforge`, url });
    } catch { /* user cancelled */ }
  };
  const genQuest = async () => {
    haptics.notify('success'); setShowQuest(true); setQuestLoading(true); setQuest(null);
    const r = await api.post<any>('/api/worldforge/quest',
      { seed: cfg.seed, world_scale: isCosmic ? 'region' : scale, palette: cfg.palette, climate: cfg.climate, size: cfg.size, arc: questArc },
      { timeoutMs: 90000 });
    setQuestLoading(false);
    setQuest(r.ok && r.data ? r.data : { error: 'Quest unavailable' });
  };
  const genMonograph = async () => {
    haptics.notify('success'); setShowMono(true); setMono(null); setMonoLoading(true); setMonoElapsed(0); setMonoSaved(false);
    const r = await api.post<any>('/api/worldforge/monograph/async',
      { seed: cfg.seed, world_scale: scale, palette: cfg.palette, climate: cfg.climate, size: cfg.size },
      { timeoutMs: 20000 });
    if (!r.ok || !r.data?.job_id) { setMonoLoading(false); setMono({ error: 'Could not start survey' }); return; }
    const jid = r.data.job_id;
    const t0 = Date.now();
    const poll = async (): Promise<void> => {
      const jr = await api.get<any>(`/api/worldforge/monograph/job/${jid}`, { timeoutMs: 15000 });
      const el = Math.round((Date.now() - t0) / 1000);
      setMonoElapsed(el);
      if (jr.ok && jr.data?.status === 'done') { setMono(jr.data); setMonoLoading(false); return; }
      if (jr.ok && jr.data?.status === 'error') { setMono({ error: jr.data.error || 'Survey failed' }); setMonoLoading(false); return; }
      if (el > 300) { setMono({ error: 'Survey timed out — try again' }); setMonoLoading(false); return; }
      setTimeout(poll, 3000);
    };
    setTimeout(poll, 3000);
  };
  const saveMonograph = async () => {
    if (!mono?.monograph) return;
    haptics.notify('success');
    const r = await api.post<any>('/api/worldforge/monograph/save',
      { name: mono.name || world?.name || 'World', scale: mono.scale || scale, seed: cfg.seed, model: mono.model || '', monograph: mono.monograph },
      { timeoutMs: 20000 });
    if (r.ok && r.data?.saved) setMonoSaved(true);
  };
  const copyMonograph = async () => {
    if (!mono?.monograph) return;
    haptics.selection();
    try {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && navigator.clipboard) {
        await navigator.clipboard.writeText(mono.monograph);
      } else {
        await Share.share({ message: mono.monograph, title: `${mono.name || 'Worldforge'} — monograph` });
      }
    } catch { /* cancelled */ }
  };
  const genPoster = async (style: string) => {
    haptics.notify('success'); setPosterStyle(style); setShowPoster(true); setPoster(null); setPosterLoading(true); setPosterElapsed(0); setPosterSaved(false);
    const r = await api.post<any>('/api/worldforge/poster/async',
      { seed: cfg.seed, world_scale: scale, palette: cfg.palette, climate: cfg.climate, size: cfg.size, style },
      { timeoutMs: 20000 });
    if (!r.ok || !r.data?.job_id) { setPosterLoading(false); setPoster({ error: 'Could not start poster' }); return; }
    const jid = r.data.job_id; const t0 = Date.now();
    const poll = async (): Promise<void> => {
      const jr = await api.get<any>(`/api/worldforge/poster/job/${jid}`, { timeoutMs: 15000 });
      const el = Math.round((Date.now() - t0) / 1000); setPosterElapsed(el);
      if (jr.ok && jr.data?.status === 'done') { setPoster(jr.data); setPosterLoading(false); return; }
      if (jr.ok && jr.data?.status === 'error') { setPoster({ error: jr.data.error || 'Poster failed' }); setPosterLoading(false); return; }
      if (el > 90) { setPoster({ error: 'Poster timed out — try again' }); setPosterLoading(false); return; }
      setTimeout(poll, 2500);
    };
    setTimeout(poll, 2500);
  };
  const openHeightmap = async () => {
    haptics.selection();
    const url = `${BACKEND}/api/worldforge/heightmap.png?scale=${COSMIC.has(scale) ? 'region' : scale}&seed=${cfg.seed}&size=${Math.max(cfg.size, 64)}&palette=${cfg.palette}&climate=${cfg.climate}&zoom=${zoom}&pan_x=${panX}&pan_y=${panY}`;
    try { await Linking.openURL(url); } catch { /* noop */ }
  };
  const runSim = async () => {
    haptics.notify('success'); setShowSim(true); setSim(null); setSimLoading(true);
    const r = await api.post<any>('/api/worldforge/simulate',
      { seed: cfg.seed, world_scale: COSMIC.has(scale) ? 'region' : scale, palette: cfg.palette, climate: cfg.climate, size: cfg.size, ticks: 24 },
      { timeoutMs: 25000 });
    setSimLoading(false);
    setSim(r.ok && r.data ? r.data : { error: 'Simulation failed' });
  };
  const savePoster = async () => {
    if (!poster?.image) return;
    haptics.notify('success');
    const r = await api.post<any>('/api/worldforge/poster/save',
      { name: poster.name || world?.name || 'World', scale, seed: cfg.seed, style: poster.style || posterStyle, image: poster.image },
      { timeoutMs: 25000 });
    if (r.ok && r.data?.saved) setPosterSaved(true);
  };
  const genInlinePhotoreal = async () => {
    const style = scale === 'planet' ? 'globe' : 'satellite';
    haptics.notify('success'); setPhotoLoading(true); setPhotoImg(null); setPhotoElapsed(0);
    const r = await api.post<any>('/api/worldforge/poster/async',
      { seed: cfg.seed, world_scale: scale, palette: cfg.palette, climate: cfg.climate, size: cfg.size, style },
      { timeoutMs: 20000 });
    if (!r.ok || !r.data?.job_id) { setPhotoLoading(false); return; }
    const jid = r.data.job_id; const t0 = Date.now();
    const poll = async (): Promise<void> => {
      const jr = await api.get<any>(`/api/worldforge/poster/job/${jid}`, { timeoutMs: 15000 });
      setPhotoElapsed(Math.round((Date.now() - t0) / 1000));
      if (jr.ok && jr.data?.status === 'done') { setPhotoImg(jr.data.image); setPhotoLoading(false); return; }
      if (jr.ok && jr.data?.status === 'error') { setPhotoLoading(false); return; }
      if ((Date.now() - t0) / 1000 > 90) { setPhotoLoading(false); return; }
      setTimeout(poll, 2500);
    };
    setTimeout(poll, 2500);
  };

  return (
    <SafeAreaView style={styles.safe} testID="worldforge-screen">
      <View style={styles.header}>
        <TouchableOpacity testID="wf-back" onPress={() => router.back()} style={styles.backBtn}><Text style={styles.backTxt}>‹ Back</Text></TouchableOpacity>
        <Text style={styles.title}>🌌 Worldforge</Text>
        <TouchableOpacity testID="wf-customize-open" onPress={() => setShowCustomize(true)} style={styles.gearBtn}><Text style={styles.gearTxt}>⚙️</Text></TouchableOpacity>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: 16, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={() => generate()} tintColor="#60A5FA" />}
      >
        {/* scale selector */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 14 }}>
          {scales.map((s) => (
            <TouchableOpacity key={s.id} testID={`wf-scale-${s.id}`}
              style={[styles.scaleChip, s.id === scale && styles.scaleChipOn]} onPress={() => setScaleAndGen(s.id)}>
              <Text style={styles.scaleEmoji}>{s.emoji}</Text>
              <Text style={[styles.scaleLabel, s.id === scale && styles.scaleLabelOn]}>{s.label}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* render mode switch */}
        {modeList.length > 1 ? (
          <View style={styles.modeRow}>
            {modeList.map((m) => (
              <TouchableOpacity key={m} testID={`wf-mode-${m}`}
                style={[styles.modeChip, m === mode && styles.modeChipOn]}
                onPress={() => { haptics.selection(); setMode(m); if (m === 'photoreal') genInlinePhotoreal(); }}>
                <Text style={[styles.modeTxt, m === mode && styles.modeTxtOn]}>{MODE_LABELS[m] || m}</Text>
              </TouchableOpacity>
            ))}
          </View>
        ) : null}

        {/* controls */}
        <View style={styles.controls}>
          <TextInput testID="wf-seed-input" style={styles.seedInput} value={seedInput} onChangeText={setSeedInput}
            keyboardType="number-pad" placeholder="seed" placeholderTextColor="#52525b" onSubmitEditing={applySeed} returnKeyType="go" />
          <TouchableOpacity testID="wf-generate" style={styles.genBtn} onPress={applySeed}><Text style={styles.genTxt}>Forge</Text></TouchableOpacity>
          <TouchableOpacity testID="wf-reroll" style={styles.rerollBtn} onPress={reroll}><Text style={styles.rerollTxt}>🎲</Text></TouchableOpacity>
        </View>
        <View style={{ flexDirection: 'row', gap: 8, marginBottom: 14 }}>
          <TouchableOpacity testID="wf-from-game" style={[styles.fromGameBtn, { flex: 1, marginBottom: 0 }]} onPress={openGames}>
            <Text style={styles.fromGameTxt}>🎮 From a game</Text>
          </TouchableOpacity>
          <TouchableOpacity testID="wf-gallery" style={[styles.fromGameBtn, { flex: 1, marginBottom: 0 }]} onPress={() => router.push('/worlds-gallery' as any)}>
            <Text style={styles.fromGameTxt}>🖼 Gallery</Text>
          </TouchableOpacity>
        </View>

        {/* map */}
        <View style={[styles.mapWrap, isCosmic && styles.mapWrapCosmic, { width: mapW + 16, alignSelf: 'center' }]}>
          {mode === 'photoreal' ? (
            photoImg ? (
              <Image testID="wf-map" source={{ uri: photoImg }} style={[styles.worldImg, { width: mapW, height: mapW }]} resizeMode="cover" />
            ) : (
              <View style={[styles.worldImg, { width: mapW, height: mapW, alignItems: 'center', justifyContent: 'center' }]}>
                <ActivityIndicator color="#60A5FA" />
                <Text style={styles.monoHint}>{photoLoading ? `AI photoreal render… (${photoElapsed}s)` : 'Tap ✨ Photoreal to render'}</Text>
              </View>
            )
          ) : (
            <>
            {!isCosmic ? (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.atlasRow} contentContainerStyle={styles.atlasRowInner}>
                {[['', '🗺️ Biome'], ['elevation', '⛰️ Elevation'], ['temperature', '🌡️ Temp'], ['moisture', '💧 Moisture'], ['fertility', '🌱 Fertility'], ['seismic', '⚡ Seismic'], ['plates', '🪨 Plates']].map(([k, lbl]) => (
                  <TouchableOpacity key={k} testID={`wf-atlas-${k || 'biome'}`} onPress={() => setAtlasLayer(k)} style={[styles.atlasBtn, atlasLayer === k && styles.atlasBtnOn]}>
                    <Text style={[styles.atlasBtnTxt, atlasLayer === k && styles.atlasBtnTxtOn]}>{lbl}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            ) : null}
            <Image testID="wf-map" source={{ uri: renderUrl }} style={[styles.worldImg, { width: mapW, height: mapW }]} resizeMode="cover" />
            </>
          )}
          {loading && mode !== 'photoreal' ? <View style={styles.imgLoading}><ActivityIndicator color="#60A5FA" /></View> : null}
        </View>

        {canZoom ? (
          <View style={styles.zoomBar} testID="wf-zoom-bar">
            <TouchableOpacity testID="wf-zoom-out" style={styles.zoomBtn} onPress={zoomOut}><Text style={styles.zoomTxt}>−</Text></TouchableOpacity>
            <Text style={styles.zoomLbl}>{zoom.toFixed(1)}×</Text>
            <TouchableOpacity testID="wf-zoom-in" style={styles.zoomBtn} onPress={zoomIn}><Text style={styles.zoomTxt}>+</Text></TouchableOpacity>
            <View style={styles.panPad}>
              <TouchableOpacity testID="wf-pan-left" style={styles.panBtn} onPress={() => panBy(-1, 0)}><Text style={styles.zoomTxt}>‹</Text></TouchableOpacity>
              <TouchableOpacity testID="wf-pan-up" style={styles.panBtn} onPress={() => panBy(0, -1)}><Text style={styles.zoomTxt}>▴</Text></TouchableOpacity>
              <TouchableOpacity testID="wf-pan-down" style={styles.panBtn} onPress={() => panBy(0, 1)}><Text style={styles.zoomTxt}>▾</Text></TouchableOpacity>
              <TouchableOpacity testID="wf-pan-right" style={styles.panBtn} onPress={() => panBy(1, 0)}><Text style={styles.zoomTxt}>›</Text></TouchableOpacity>
            </View>
            <TouchableOpacity testID="wf-zoom-reset" style={styles.resetBtn} onPress={resetView}><Text style={styles.resetTxt}>Reset</Text></TouchableOpacity>
          </View>
        ) : null}

        {wgBadge ? <View testID="wf-wg-badge" style={styles.wgBadge}><Text style={styles.wgBadgeTxt}>💾 {wgBadge}</Text></View> : null}

        {world ? (
          <>
            <View testID="wf-name" style={[styles.nameBanner, isCosmic && styles.nameBannerCosmic]}>
              <Text style={[styles.nameText, isCosmic && styles.nameTextCosmic]}>{isCosmic ? '🛰️' : '🗺️'} {world.name}</Text>
              <Text style={styles.nameSub}>{world.scale} · {world.palette}/{world.climate} · seed {world.seed}</Text>
            </View>

            <View testID="wf-stats" style={styles.statsRow}>
              <View style={styles.stat}><Text style={styles.statNum}>{world.stats.biomes}</Text><Text style={styles.statLbl}>{isCosmic ? 'Objects' : 'Biomes'}</Text></View>
              <View style={styles.stat}><Text style={styles.statNum}>{world.stats.land_pct}%</Text><Text style={styles.statLbl}>{isCosmic ? 'Filled' : 'Land'}</Text></View>
              {isCosmic ? null : <View style={styles.stat}><Text style={styles.statNum}>{world.stats.river_tiles}</Text><Text style={styles.statLbl}>Rivers</Text></View>}
              <View style={styles.stat}><Text style={styles.statNum}>{world.stats.settlements}</Text><Text style={styles.statLbl}>{isCosmic ? 'Bodies' : 'Towns'}</Text></View>
            </View>

            {!isCosmic && world.koppen ? (
              <View testID="wf-climate" style={styles.climateCard}>
                <View style={styles.climateHead}>
                  <View style={styles.koppenBadge}><Text style={styles.koppenCode}>{world.koppen.code}</Text></View>
                  <Text style={styles.climateName}>{world.koppen.name}</Text>
                  {typeof world.stats.trade_routes === 'number' ? (
                    <View style={styles.routeChip}><Text style={styles.routeChipTxt}>🛤️ {world.stats.trade_routes} routes</Text></View>
                  ) : null}
                </View>
                <Text style={styles.climateSummary}>Köppen–Geiger climate · {world.koppen.summary}</Text>
                {(world.biodiversity || world.hazards) ? (
                  <View style={styles.climateChips}>
                    {world.biodiversity ? (
                      <View style={styles.bioChip}><Text style={styles.bioChipTxt}>🌿 Biodiversity {world.biodiversity.index} · {world.biodiversity.rating}</Text></View>
                    ) : null}
                    {world.hazards ? (
                      <View style={[styles.hazChip, world.hazards.overall === 'high' && styles.hazChipHigh]}>
                        <Text style={styles.hazChipTxt}>⚠️ Hazard: {world.hazards.overall}</Text>
                      </View>
                    ) : null}
                  </View>
                ) : null}
              </View>
            ) : null}

            {!isCosmic && world.systems ? (
              <View style={styles.sysWrap}>
                <TouchableOpacity testID="wf-systems-toggle" style={styles.sysBtn} onPress={() => setShowSystems(v => !v)}>
                  <Text style={styles.sysBtnTxt}>🌍 Planetary systems {showSystems ? '▲' : '▼'}</Text>
                </TouchableOpacity>
                {showSystems ? (
                  <View testID="wf-systems-card" style={styles.sysCard}>
                    {[
                      ['🪨 Tectonics', world.systems.tectonics?.note],
                      ['☀️ Insolation', world.systems.insolation?.note],
                      ['🧲 Magnetosphere', world.systems.magnetosphere?.note],
                      ['🌫️ Atmosphere', world.systems.atmosphere?.note],
                      ['🌬️ Winds', world.systems.winds?.note],
                      ['🌊 Currents', world.systems.currents?.note],
                      ['💧 Hydrology', world.systems.hydrology?.note],
                      ['🌡️ Energy balance', world.systems.energy_balance?.note],
                      ['🌙 Tides', world.systems.tides?.note],
                      ['🌾 Phenology', world.systems.phenology?.note],
                      ['🍃 Productivity', world.systems.productivity?.note],
                      ['⛰️ Lithology', world.systems.lithology?.note],
                      ['⛏️ Resources', `${(world.systems.resources?.deposits || []).join(', ')} · arable ${world.systems.resources?.arable_pct}%`],
                      ['🌱 Soils', world.systems.soil?.note],
                      ['🏙️ Settlement hierarchy', world.systems.settlement_hierarchy?.note],
                      ['🛤️ Network', world.systems.network?.note],
                      ['👥 Population', world.systems.population?.note],
                      ['💰 Macro-economy', world.systems.macro_economy?.note],
                      ['🌍 Habitability', world.systems.habitability?.note],
                      ['🛰️ Orbital', world.systems.orbital?.note],
                      ['❄️ Cryosphere', world.systems.cryosphere?.note],
                      ['🔋 Renewables', world.systems.renewables?.note],
                      ['🌽 Agriculture', world.systems.agriculture?.note],
                      ['🌫️ Air quality', world.systems.air_quality?.note],
                      ['🏖️ Coastal', world.systems.coastal?.note],
                      ['🦌 Wildlife corridors', world.systems.wildlife_corridors?.note],
                      ['🔭 Astronomy', world.systems.astronomy?.note],
                      ['🚰 Water security', world.systems.water_security?.note],
                      ['⚠️ Disaster risk', world.systems.risk_index?.note],
                    ].map(([label, note], i) => (
                      <View key={i} style={styles.sysRow}>
                        <Text style={styles.sysLabel}>{label}</Text>
                        <Text style={styles.sysNote}>{note}</Text>
                      </View>
                    ))}
                  </View>
                ) : null}
              </View>
            ) : null}

            {world.pois?.length ? (
              <View style={styles.poiWrap}>
                {world.pois.slice(0, 10).map((p, i) => (
                  <View key={`pc-${i}`} style={styles.poiChip}>
                    <Text style={styles.poiTxt}>{p.icon} {p.name}</Text>
                    <Text style={styles.poiKind}>{p.kind}</Text>
                  </View>
                ))}
              </View>
            ) : null}

            <Text style={styles.sectionTitle}>{isCosmic ? 'Composition' : 'Biome distribution'}</Text>
            {world.distribution.map((d) => (
              <View key={d.biome} testID={`wf-biome-${d.biome}`} style={styles.legendRow}>
                <View style={[styles.swatch, { backgroundColor: d.color }]} />
                <Text style={styles.legendName}>{d.emoji} {d.label}</Text>
                <View style={styles.barTrack}><View style={[styles.barFill, { width: `${d.pct}%`, backgroundColor: d.color }]} /></View>
                <Text style={styles.legendPct}>{d.pct}%</Text>
              </View>
            ))}

            <TouchableOpacity testID="wf-lore" style={styles.loreBtn} onPress={genLore} disabled={loreLoading}>
              {loreLoading ? <ActivityIndicator color="#fff" /> : <Text style={styles.loreBtnTxt}>📜 Forge AI lore for {world.name}</Text>}
            </TouchableOpacity>
            {lore ? (
              <View testID="wf-lore-card" style={styles.loreCard}>
                <Text style={styles.loreCardTitle}>CHRONICLE OF {world.name.toUpperCase()}</Text>
                <Text style={styles.loreCardTxt}>{lore}</Text>
              </View>
            ) : null}
            <TouchableOpacity testID="wf-namekey" style={styles.namekeyBtn} onPress={genNameKey} disabled={nameKeyLoading}>
              {nameKeyLoading ? <ActivityIndicator color="#fff" /> : <Text style={styles.namekeyBtnTxt}>📄 Scientific name key — toponym etymology</Text>}
            </TouchableOpacity>
            {nameKey ? (
              nameKey.error ? (
                <View testID="wf-namekey-card" style={styles.loreCard}><Text style={styles.loreCardTxt}>{nameKey.error}</Text></View>
              ) : (
                <View testID="wf-namekey-card" style={styles.namekeyCard}>
                  <Text style={styles.loreCardTitle}>NAME KEY · {String(nameKey.region_name || '').toUpperCase()}</Text>
                  <Text style={styles.namekeyNote}>{nameKey.convention}</Text>
                  {(nameKey.entries || []).map((e: any, i: number) => (
                    <View key={i} testID={`wf-namekey-${i}`} style={styles.namekeyRow}>
                      <Text style={styles.namekeyName}>{e.icon} {e.name}</Text>
                      {(e.etymology || []).map((c: any, j: number) => (
                        <Text key={j} style={styles.namekeyGloss}>
                          <Text style={styles.namekeyPart}>{c.part}</Text> — {c.meaning}
                        </Text>
                      ))}
                    </View>
                  ))}
                </View>
              )
            ) : null}
            <TouchableOpacity testID="wf-play" style={styles.playBtn} onPress={playWorld} disabled={playing}>
              {playing ? <ActivityIndicator color="#fff" /> : <Text style={styles.playTxt}>🎮 Play this world — build a game</Text>}
            </TouchableOpacity>
            {playMsg ? <View testID="wf-play-msg" style={styles.playMsg}><Text style={styles.playMsgTxt}>{playMsg}</Text></View> : null}
            <View style={{ flexDirection: 'row', gap: 10, marginTop: 12 }}>
              <TouchableOpacity testID="wf-quest" style={[styles.questBtn, { flex: 1 }]} onPress={genQuest}>
                <Text style={styles.questBtnTxt}>🗺️ Generate quest</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="wf-share" style={[styles.shareBtn, { flex: 1 }]} onPress={shareWorld}>
                <Text style={styles.shareTxt}>📤 Share / Export</Text>
              </TouchableOpacity>
            </View>
            <TouchableOpacity testID="wf-monograph" style={styles.monoBtn} onPress={genMonograph}>
              <Text style={styles.monoBtnTxt}>📖 NASA Scientific Survey — full monograph</Text>
            </TouchableOpacity>
            <View style={styles.toolRow}>
              <TouchableOpacity testID="wf-poster" style={styles.toolBtn} onPress={() => genPoster('satellite')}><Text style={styles.toolTxt}>🖼️ Poster</Text></TouchableOpacity>
              <TouchableOpacity testID="wf-simulate" style={styles.toolBtn} onPress={runSim}><Text style={styles.toolTxt}>🧪 Simulate</Text></TouchableOpacity>
              <TouchableOpacity testID="wf-heightmap" style={styles.toolBtn} onPress={openHeightmap}><Text style={styles.toolTxt}>⛰️ Heightmap</Text></TouchableOpacity>
              <TouchableOpacity testID="wf-vault" style={styles.toolBtn} onPress={() => { haptics.selection(); router.push('/worldforge-vault'); }}><Text style={styles.toolTxt}>📚 Vault</Text></TouchableOpacity>
              <TouchableOpacity testID="wf-explore-map" style={styles.toolBtn} onPress={() => { haptics.selection(); router.push({ pathname: '/worldforge-map', params: { seed: String(cfg.seed), scale, palette: cfg.palette, climate: cfg.climate, size: String(cfg.size), mode: effMode } }); }}><Text style={styles.toolTxt}>🛰️ Explore map</Text></TouchableOpacity>
            </View>
            <Text style={styles.hint}>Same config → same world. Tap ⚙️ to customise terrain, climate, palette &amp; structures (cities · harbors · observatories…), or forge a world from one of your games and save it to the Vault.</Text>
          </>
        ) : null}
      </ScrollView>

      {/* ── CUSTOMIZE QUESTIONNAIRE ── */}
      <Modal visible={showCustomize} animationType="slide" transparent onRequestClose={() => setShowCustomize(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>⚙️ Customize world</Text>
              <TouchableOpacity testID="wf-customize-apply" onPress={() => { setShowCustomize(false); generate(); }} style={styles.applyBtn}><Text style={styles.applyTxt}>Apply</Text></TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={{ paddingBottom: 30 }}>
              <Text style={styles.qLabel}>Palette</Text>
              <View style={styles.chipRow}>
                {palettes.map((p) => (
                  <TouchableOpacity key={p} testID={`wf-palette-${p}`} style={[styles.optChip, cfg.palette === p && styles.optChipOn]} onPress={() => { haptics.selection(); setCfg((c: any) => ({ ...c, palette: p })); }}>
                    <Text style={[styles.optTxt, cfg.palette === p && styles.optTxtOn]}>{p}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={styles.qLabel}>Climate</Text>
              <View style={styles.chipRow}>
                {climates.map((cl) => (
                  <TouchableOpacity key={cl} testID={`wf-climate-${cl}`} style={[styles.optChip, cfg.climate === cl && styles.optChipOn]} onPress={() => { haptics.selection(); setCfg((c: any) => ({ ...c, climate: cl })); }}>
                    <Text style={[styles.optTxt, cfg.climate === cl && styles.optTxtOn]}>{cl}</Text>
                  </TouchableOpacity>
                ))}
              </View>
              <Text style={styles.qLabel}>Structures</Text>
              <View style={styles.chipRow}>
                {toggles.map((t) => (
                  <TouchableOpacity key={t.key} testID={`wf-toggle-${t.key}`} style={[styles.optChip, cfg.features[t.key] && styles.optChipOn]} onPress={() => toggleFeature(t.key)}>
                    <Text style={[styles.optTxt, cfg.features[t.key] && styles.optTxtOn]}>{t.icon} {t.key}</Text>
                  </TouchableOpacity>
                ))}
              </View>

              <SliderRow label="World size" value={cfg.size} min={16} max={96} step={4} onChange={(v) => setParam('size', v)} fmt={(v) => `${v}`} />
              <SliderRow label="Sea level" value={cfg.sea_level} min={0.1} max={0.6} step={0.02} onChange={(v) => setParam('sea_level', v)} />
              <SliderRow label="Mountain height" value={cfg.mountain_level} min={0.55} max={0.9} step={0.02} onChange={(v) => setParam('mountain_level', v)} />
              <SliderRow label="Moisture" value={cfg.moisture_bias} min={-0.4} max={0.4} step={0.04} onChange={(v) => setParam('moisture_bias', v)} />
              <SliderRow label="Temperature" value={cfg.temperature_bias} min={-0.4} max={0.4} step={0.04} onChange={(v) => setParam('temperature_bias', v)} />
              <SliderRow label="River density" value={cfg.river_density} min={0} max={0.15} step={0.01} onChange={(v) => setParam('river_density', v)} />
              <SliderRow label="Structure density" value={cfg.settlement_density} min={0} max={3} step={0.25} onChange={(v) => setParam('settlement_density', v)} />
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* ── GAME SOURCES ── */}
      <Modal visible={showGames} animationType="slide" transparent onRequestClose={() => setShowGames(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>🎮 Forge from a game</Text>
              <TouchableOpacity onPress={() => setShowGames(false)} style={styles.applyBtn}><Text style={styles.applyTxt}>Close</Text></TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={{ paddingBottom: 30 }}>
              {games.length === 0 ? <ActivityIndicator color="#60A5FA" style={{ marginTop: 30 }} /> :
                games.map((g) => (
                  <TouchableOpacity key={g.id} testID={`wf-game-${g.id}`} style={styles.gameRow} disabled={!!forging} onPress={() => forgeFromGame(g)}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.gameTitle} numberOfLines={1}>{g.title}</Text>
                      <Text style={styles.gameMeta}>{g.source} · {g.genre || 'game'}</Text>
                    </View>
                    {forging === g.id ? <ActivityIndicator color="#60A5FA" /> : <Text style={styles.gameForge}>Forge →</Text>}
                  </TouchableOpacity>
                ))}
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* ── SCIENTIFIC MONOGRAPH ── */}
      <Modal visible={showMono} animationType="slide" transparent onRequestClose={() => setShowMono(false)}>
        <View style={styles.modalBackdrop}>
          <View style={[styles.modalSheet, { maxHeight: '92%' }]}>
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>📖 Scientific Survey</Text>
              <TouchableOpacity onPress={() => setShowMono(false)} style={styles.applyBtn}><Text style={styles.applyTxt}>Close</Text></TouchableOpacity>
            </View>
            {monoLoading ? (
              <View style={{ alignItems: 'center', paddingVertical: 36 }}>
                <ActivityIndicator color="#60A5FA" />
                <Text style={styles.monoProg}>Surveying {world?.name || 'world'}… ({monoElapsed}s)</Text>
                <Text style={styles.monoHint}>NASA-grade monograph: geology, climate, hydrology, biomes, settlements, economy & trade — grounded in this exact world. Takes ~2–3 min.</Text>
              </View>
            ) : mono?.error ? <Text style={styles.qErr}>{mono.error}</Text> :
              mono?.monograph ? (
                <ScrollView contentContainerStyle={{ paddingBottom: 40 }}>
                  <View style={styles.monoActions}>
                    <TouchableOpacity testID="wf-mono-save" style={[styles.monoActBtn, monoSaved && styles.monoActBtnDone]} onPress={saveMonograph} disabled={monoSaved}>
                      <Text style={styles.monoActTxt}>{monoSaved ? '✓ Saved to Vault' : '💾 Save to Vault'}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity testID="wf-mono-copy" style={styles.monoActBtn} onPress={copyMonograph}>
                      <Text style={styles.monoActTxt}>{Platform.OS === 'web' ? '📋 Copy' : '📤 Share'}</Text>
                    </TouchableOpacity>
                  </View>
                  <Text testID="wf-monograph-card" style={styles.monoText} selectable>{mono.monograph}</Text>
                  <Text style={styles.monoMeta}>{mono.model} · {mono.elapsed}s · {mono.monograph.length.toLocaleString()} chars</Text>
                </ScrollView>
              ) : null}
          </View>
        </View>
      </Modal>

      {/* ── PHOTOREAL POSTER ── */}
      <Modal visible={showPoster} animationType="slide" transparent onRequestClose={() => setShowPoster(false)}>
        <View style={styles.modalBackdrop}>
          <View style={[styles.modalSheet, { maxHeight: '92%' }]}>
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>🖼️ Photoreal Poster</Text>
              <TouchableOpacity onPress={() => setShowPoster(false)} style={styles.applyBtn}><Text style={styles.applyTxt}>Close</Text></TouchableOpacity>
            </View>
            <View style={styles.posterStyleRow}>
              {['satellite', 'globe', 'relief', 'night'].map((s) => (
                <TouchableOpacity key={s} testID={`wf-poster-${s}`} style={[styles.posterChip, posterStyle === s && styles.posterChipOn]} onPress={() => genPoster(s)} disabled={posterLoading}>
                  <Text style={[styles.posterChipTxt, posterStyle === s && styles.posterChipTxtOn]}>{s}</Text>
                </TouchableOpacity>
              ))}
            </View>
            {posterLoading ? (
              <View style={{ alignItems: 'center', paddingVertical: 40 }}>
                <ActivityIndicator color="#60A5FA" />
                <Text style={styles.monoProg}>Rendering {posterStyle} poster… ({posterElapsed}s)</Text>
                <Text style={styles.monoHint}>Gemini Nano-Banana photoreal render of {world?.name}.</Text>
              </View>
            ) : poster?.error ? <Text style={styles.qErr}>{poster.error}</Text> :
              poster?.image ? (
                <ScrollView contentContainerStyle={{ paddingBottom: 30, alignItems: 'center' }}>
                  <Image testID="wf-poster-img" source={{ uri: poster.image }} style={styles.posterImg} resizeMode="contain" />
                  <TouchableOpacity testID="wf-poster-save" style={[styles.monoActBtn, { alignSelf: 'stretch', marginTop: 12 }, posterSaved && styles.monoActBtnDone]} onPress={savePoster} disabled={posterSaved}>
                    <Text style={styles.monoActTxt}>{posterSaved ? '✓ Saved to gallery' : '💾 Save to gallery'}</Text>
                  </TouchableOpacity>
                  <Text style={styles.monoMeta}>Nano-Banana · {poster.elapsed}s · {poster.style}</Text>
                </ScrollView>
              ) : null}
          </View>
        </View>
      </Modal>

      {/* ── WORLD SIMULATION ── */}
      <Modal visible={showSim} animationType="slide" transparent onRequestClose={() => setShowSim(false)}>
        <View style={styles.modalBackdrop}>
          <View style={[styles.modalSheet, { maxHeight: '90%' }]}>
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>🧪 World Simulation</Text>
              <TouchableOpacity onPress={() => setShowSim(false)} style={styles.applyBtn}><Text style={styles.applyTxt}>Close</Text></TouchableOpacity>
            </View>
            {simLoading ? <ActivityIndicator color="#60A5FA" style={{ marginTop: 30 }} /> :
              sim?.error ? <Text style={styles.qErr}>{sim.error}</Text> :
                sim?.summary ? (
                  <ScrollView contentContainerStyle={{ paddingBottom: 30 }} testID="wf-sim-card">
                    <View style={styles.simStatsRow}>
                      <View style={styles.simStat}><Text style={styles.simStatN}>{sim.summary.final_pop.toLocaleString()}</Text><Text style={styles.simStatL}>final pop</Text></View>
                      <View style={styles.simStat}><Text style={styles.simStatN}>{sim.summary.settlements}</Text><Text style={styles.simStatL}>settlements</Text></View>
                      <View style={styles.simStat}><Text style={styles.simStatN}>{sim.summary.founded}</Text><Text style={styles.simStatL}>founded</Text></View>
                      <View style={styles.simStat}><Text style={styles.simStatN}>{sim.ticks}</Text><Text style={styles.simStatL}>ticks</Text></View>
                    </View>
                    <Text style={styles.simSection}>Population over time</Text>
                    <View style={styles.simChart}>
                      {sim.series.map((s: any, i: number) => {
                        const peak = sim.summary.peak_pop || 1;
                        const h = Math.max(3, Math.round((s.total_pop / peak) * 70));
                        return <View key={i} style={[styles.simBar, { height: h }]} />;
                      })}
                    </View>
                    <Text style={styles.simSection}>Agents</Text>
                    {sim.agents.map((a: any, i: number) => (
                      <View key={i} style={styles.simAgent}>
                        <Text style={styles.simAgentN}>{a.name} · {a.kind}</Text>
                        <Text style={styles.simAgentM}>pop {a.pop.toLocaleString()} · fertility {a.fertility} · water {a.water}</Text>
                      </View>
                    ))}
                  </ScrollView>
                ) : null}
          </View>
        </View>
      </Modal>

      {/* ── QUEST GRAPH ── */}
      <Modal visible={showQuest} animationType="slide" transparent onRequestClose={() => setShowQuest(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>🗺️ Quest graph</Text>
              <TouchableOpacity onPress={() => setShowQuest(false)} style={styles.applyBtn}><Text style={styles.applyTxt}>Close</Text></TouchableOpacity>
            </View>
            <View style={{ flexDirection: 'row', gap: 8, marginBottom: 10 }}>
              <TextInput style={[styles.seedInput, { flex: 1 }]} value={questArc} onChangeText={setQuestArc}
                placeholder="optional theme (e.g. a lost relic)" placeholderTextColor="#52525b" />
              <TouchableOpacity testID="wf-quest-regen" style={styles.genBtn} onPress={genQuest}><Text style={styles.genTxt}>Forge</Text></TouchableOpacity>
            </View>
            <ScrollView contentContainerStyle={{ paddingBottom: 30 }}>
              {questLoading ? <ActivityIndicator color="#60A5FA" style={{ marginTop: 30 }} /> :
                quest?.error ? <Text style={styles.qErr}>{quest.error}</Text> :
                  quest?.quest ? (
                    <View testID="wf-quest-card">
                      <Text style={styles.questTitle}>{quest.quest.title}</Text>
                      <Text style={styles.questPremise}>{quest.quest.premise}</Text>
                      {quest.consistency ? (
                        <View style={[styles.consBadge, quest.consistency.ok ? styles.consOk : styles.consWarn]}>
                          <Text style={styles.consTxt}>{quest.consistency.ok
                            ? `✓ Lore-consistent · ${quest.consistency.node_count} nodes`
                            : `⚠ ${quest.consistency.unknown_locations.length} unknown loc · ${quest.consistency.dangling_branches.length} dangling`}</Text>
                        </View>
                      ) : null}
                      {(quest.quest.factions || []).length ? <Text style={styles.questMeta}>Factions: {(quest.quest.factions || []).join(' vs ')}</Text> : null}
                      {(quest.quest.nodes || []).map((nd: any, i: number) => (
                        <View key={nd.id || i} style={styles.questNode}>
                          <Text style={styles.qnTitle}>{nd.id ? `[${nd.id}] ` : ''}{nd.title}</Text>
                          <Text style={styles.qnLoc}>📍 {nd.location} — {nd.objective}</Text>
                          {(nd.branches || []).map((br: any, j: number) => (
                            <Text key={j} style={styles.qnBranch}>↳ {br.choice} → {br.to}{br.consequence ? ` (${br.consequence})` : ''}</Text>
                          ))}
                        </View>
                      ))}
                      {quest.quest.epilogue ? <Text style={styles.questEpilogue}>{quest.quest.epilogue}</Text> : null}
                    </View>
                  ) : null}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

function SliderRow({ label, value, min, max, step, onChange, fmt }:
  { label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void; fmt?: (v: number) => string }) {
  return (
    <View style={styles.sliderRow}>
      <View style={styles.sliderHead}>
        <Text style={styles.sliderLabel}>{label}</Text>
        <Text style={styles.sliderVal}>{fmt ? fmt(value) : value.toFixed(2)}</Text>
      </View>
      <Slider minimumValue={min} maximumValue={max} step={step} value={value}
        onValueChange={onChange} minimumTrackTintColor="#60A5FA" maximumTrackTintColor="#262626"
        thumbTintColor={Platform.OS === 'android' ? '#60A5FA' : undefined} />
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#070710' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: '#1e2030' },
  backBtn: { paddingVertical: 6, paddingRight: 12 }, backTxt: { color: '#94a3b8', fontSize: 15 },
  title: { flex: 1, color: '#f1f5f9', fontSize: 20, fontWeight: '800' },
  gearBtn: { padding: 6 }, gearTxt: { fontSize: 20 },
  scaleChip: { backgroundColor: '#10131f', borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10, marginRight: 8, alignItems: 'center', borderWidth: 1, borderColor: '#1e2030', minWidth: 78 },
  scaleChipOn: { borderColor: '#60A5FA', backgroundColor: '#0c2030' },
  scaleEmoji: { fontSize: 20 }, scaleLabel: { color: '#94a3b8', fontSize: 12, marginTop: 2, fontWeight: '700' }, scaleLabelOn: { color: '#93C5FD' },
  controls: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  seedInput: { flex: 1, backgroundColor: '#10131f', borderRadius: 10, borderWidth: 1, borderColor: '#1e2030', color: '#f1f5f9', paddingHorizontal: 12, paddingVertical: 11, fontSize: 15 },
  genBtn: { backgroundColor: '#3B82F6', borderRadius: 10, paddingHorizontal: 18, justifyContent: 'center' }, genTxt: { color: '#fff', fontWeight: '800' },
  rerollBtn: { backgroundColor: '#1e2030', borderRadius: 10, paddingHorizontal: 14, justifyContent: 'center' }, rerollTxt: { fontSize: 18 },
  fromGameBtn: { backgroundColor: '#10131f', borderRadius: 10, paddingVertical: 12, alignItems: 'center', marginBottom: 14, borderWidth: 1, borderColor: '#334155' },
  fromGameTxt: { color: '#93C5FD', fontWeight: '700' },
  mapWrap: { backgroundColor: '#0a0c14', padding: 8, borderRadius: 16, borderWidth: 1, borderColor: '#1e2030' },
  mapWrapCosmic: { backgroundColor: '#04040a', borderColor: '#2a1a4a' },
  mapLoading: { alignItems: 'center', justifyContent: 'center' },
  wgBadge: { backgroundColor: '#0c2030', borderRadius: 10, padding: 12, marginTop: 12, borderWidth: 1, borderColor: '#3B82F6' },
  wgBadgeTxt: { color: '#93C5FD', fontWeight: '700' },
  nameBanner: { backgroundColor: '#0d1f17', borderRadius: 12, padding: 14, marginTop: 14, marginBottom: 14, borderWidth: 1, borderColor: '#14532d' },
  nameBannerCosmic: { backgroundColor: '#120a26', borderColor: '#4c1d95' },
  nameText: { color: '#4ade80', fontSize: 20, fontWeight: '800' }, nameTextCosmic: { color: '#c4b5fd' },
  nameSub: { color: '#64748b', fontSize: 12, marginTop: 2, textTransform: 'capitalize' },
  statsRow: { flexDirection: 'row', gap: 10, marginBottom: 14 },
  stat: { flex: 1, backgroundColor: '#10131f', borderRadius: 12, paddingVertical: 14, alignItems: 'center', borderWidth: 1, borderColor: '#1e2030' },
  statNum: { color: '#60A5FA', fontSize: 20, fontWeight: '800' }, statLbl: { color: '#64748b', fontSize: 12, marginTop: 2 },
  poiWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 16 },
  poiChip: { backgroundColor: '#10131f', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, borderWidth: 1, borderColor: '#1e2030' },
  poiTxt: { color: '#e2e8f0', fontSize: 12, fontWeight: '700' }, poiKind: { color: '#64748b', fontSize: 10, textTransform: 'capitalize' },
  sectionTitle: { color: '#cbd5e1', fontSize: 15, fontWeight: '800', marginBottom: 10 },
  legendRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 8, gap: 8 },
  swatch: { width: 18, height: 18, borderRadius: 4 },
  legendName: { color: '#e2e8f0', fontSize: 13, width: 140 },
  barTrack: { flex: 1, height: 8, backgroundColor: '#161821', borderRadius: 4, overflow: 'hidden' },
  barFill: { height: '100%', borderRadius: 4 },
  legendPct: { color: '#94a3b8', fontSize: 12, width: 42, textAlign: 'right' },
  loreBtn: { backgroundColor: '#0369a1', borderRadius: 12, paddingVertical: 14, alignItems: 'center', marginTop: 18 },
  loreBtnTxt: { color: '#fff', fontWeight: '800', fontSize: 15 },
  loreCard: { backgroundColor: '#0a1a2a', borderRadius: 12, padding: 16, marginTop: 12, borderWidth: 1, borderColor: '#3B82F6' },
  loreCardTitle: { color: '#93C5FD', fontSize: 11, fontWeight: '800', letterSpacing: 1, marginBottom: 8 },
  loreCardTxt: { color: '#dbeafe', fontSize: 14, lineHeight: 22 },
  namekeyBtn: { backgroundColor: '#155e4b', borderRadius: 12, paddingVertical: 13, alignItems: 'center', marginTop: 12 },
  namekeyBtnTxt: { color: '#fff', fontWeight: '800', fontSize: 14 },
  namekeyCard: { backgroundColor: '#0a1f18', borderRadius: 12, padding: 16, marginTop: 12, borderWidth: 1, borderColor: '#10b981' },
  namekeyNote: { color: '#6ee7b7', fontSize: 12, lineHeight: 18, marginBottom: 12, fontStyle: 'italic' },
  namekeyRow: { marginBottom: 12, borderLeftWidth: 2, borderLeftColor: '#10b981', paddingLeft: 10 },
  namekeyName: { color: '#d1fae5', fontSize: 15, fontWeight: '800', marginBottom: 3 },
  namekeyGloss: { color: '#a7f3d0', fontSize: 12, lineHeight: 18 },
  namekeyPart: { color: '#fff', fontWeight: '700' },
  climateCard: { backgroundColor: '#0b1622', borderRadius: 12, padding: 14, marginTop: 10, borderWidth: 1, borderColor: '#1d3a4f' },
  climateHead: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 8 },
  koppenBadge: { backgroundColor: '#3B82F6', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4 },
  koppenCode: { color: '#04141f', fontWeight: '900', fontSize: 14, letterSpacing: 0.5 },
  climateName: { color: '#DBEAFE', fontWeight: '800', fontSize: 15, flexShrink: 1 },
  routeChip: { backgroundColor: '#1e293b', borderRadius: 8, paddingHorizontal: 9, paddingVertical: 4, marginLeft: 'auto' },
  routeChipTxt: { color: '#93c5fd', fontWeight: '700', fontSize: 12 },
  climateSummary: { color: '#93C5FD', fontSize: 12, lineHeight: 18, marginTop: 8 },
  climateChips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
  bioChip: { backgroundColor: '#14321f', borderRadius: 8, paddingHorizontal: 9, paddingVertical: 4, borderWidth: 1, borderColor: '#16734a' },
  bioChipTxt: { color: '#86efac', fontWeight: '700', fontSize: 12 },
  hazChip: { backgroundColor: '#332514', borderRadius: 8, paddingHorizontal: 9, paddingVertical: 4, borderWidth: 1, borderColor: '#a16207' },
  hazChipHigh: { backgroundColor: '#3b1717', borderColor: '#dc2626' },
  hazChipTxt: { color: '#fbbf24', fontWeight: '700', fontSize: 12 },
  sysWrap: { marginTop: 10 },
  sysBtn: { backgroundColor: '#1a2433', borderRadius: 10, paddingVertical: 11, alignItems: 'center', borderWidth: 1, borderColor: '#2b3a52' },
  sysBtnTxt: { color: '#cbd5e1', fontWeight: '800', fontSize: 14 },
  sysCard: { backgroundColor: '#0c1420', borderRadius: 12, padding: 14, marginTop: 8, borderWidth: 1, borderColor: '#243044' },
  sysRow: { marginBottom: 11, borderLeftWidth: 2, borderLeftColor: '#3b82f6', paddingLeft: 10 },
  sysLabel: { color: '#e2e8f0', fontWeight: '800', fontSize: 13, marginBottom: 2 },
  sysNote: { color: '#94a3b8', fontSize: 12, lineHeight: 18 },
  atlasRow: { marginBottom: 8 },
  atlasRowInner: { gap: 7, paddingVertical: 2 },
  atlasBtn: { backgroundColor: '#161e2c', borderRadius: 8, paddingHorizontal: 13, minHeight: 44, justifyContent: 'center', borderWidth: 1, borderColor: '#283246' },
  atlasBtnOn: { backgroundColor: '#3B82F6', borderColor: '#60A5FA' },
  atlasBtnTxt: { color: '#9fb2c8', fontWeight: '700', fontSize: 12 },
  atlasBtnTxtOn: { color: '#04141f', fontWeight: '800' },
  hint: { color: '#64748b', fontSize: 13, marginTop: 14, lineHeight: 20 },
  modalBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  modalSheet: { backgroundColor: '#0a0c14', borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 18, maxHeight: '85%', borderTopWidth: 1, borderColor: '#1e2030' },
  modalHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 },
  modalTitle: { color: '#f1f5f9', fontSize: 18, fontWeight: '800' },
  applyBtn: { backgroundColor: '#3B82F6', borderRadius: 10, paddingHorizontal: 18, paddingVertical: 9 }, applyTxt: { color: '#fff', fontWeight: '800' },
  qLabel: { color: '#94a3b8', fontSize: 13, fontWeight: '700', marginTop: 14, marginBottom: 8 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  optChip: { backgroundColor: '#10131f', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1, borderColor: '#1e2030' },
  optChipOn: { borderColor: '#60A5FA', backgroundColor: '#0c2030' },
  optTxt: { color: '#94a3b8', fontSize: 13, textTransform: 'capitalize' }, optTxtOn: { color: '#93C5FD', fontWeight: '700' },
  sliderRow: { marginTop: 16 },
  sliderHead: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 2 },
  sliderLabel: { color: '#cbd5e1', fontSize: 14, fontWeight: '600' }, sliderVal: { color: '#60A5FA', fontSize: 14, fontWeight: '700' },
  gameRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#10131f', borderRadius: 10, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: '#1e2030' },
  gameTitle: { color: '#e2e8f0', fontSize: 15, fontWeight: '700' }, gameMeta: { color: '#64748b', fontSize: 12, marginTop: 2, textTransform: 'capitalize' },
  gameForge: { color: '#93C5FD', fontWeight: '800' },
  worldImg: { borderRadius: 12, backgroundColor: '#04040a' },
  imgLoading: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, alignItems: 'center', justifyContent: 'center' },
  playBtn: { backgroundColor: '#16a34a', borderRadius: 12, paddingVertical: 14, alignItems: 'center', marginTop: 12 },
  playTxt: { color: '#fff', fontWeight: '800', fontSize: 15 },
  playMsg: { backgroundColor: '#0d1f17', borderRadius: 10, padding: 12, marginTop: 10, borderWidth: 1, borderColor: '#16a34a' },
  playMsgTxt: { color: '#4ade80', fontWeight: '700' },
  modeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 12 },
  modeChip: { backgroundColor: '#10131f', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8, borderWidth: 1, borderColor: '#1e2030' },
  modeChipOn: { borderColor: '#a855f7', backgroundColor: '#1a1030' },
  modeTxt: { color: '#94a3b8', fontSize: 13, fontWeight: '700' }, modeTxtOn: { color: '#d8b4fe' },
  zoomBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: 10 },
  zoomBtn: { backgroundColor: '#10131f', borderRadius: 10, width: 40, height: 40, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#334155' },
  zoomTxt: { color: '#93C5FD', fontSize: 20, fontWeight: '800' },
  zoomLbl: { color: '#cbd5e1', fontSize: 14, fontWeight: '800', minWidth: 42, textAlign: 'center' },
  panPad: { flexDirection: 'row', gap: 4, marginLeft: 4 },
  panBtn: { backgroundColor: '#10131f', borderRadius: 8, width: 36, height: 40, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#1e2030' },
  resetBtn: { backgroundColor: '#1e2030', borderRadius: 10, paddingHorizontal: 12, height: 40, justifyContent: 'center', marginLeft: 4 },
  resetTxt: { color: '#94a3b8', fontWeight: '700', fontSize: 13 },
  questBtn: { backgroundColor: '#5b21b6', borderRadius: 12, paddingVertical: 14, alignItems: 'center' },
  questBtnTxt: { color: '#fff', fontWeight: '800', fontSize: 14 },
  shareBtn: { backgroundColor: '#0369a1', borderRadius: 12, paddingVertical: 14, alignItems: 'center' },
  shareTxt: { color: '#fff', fontWeight: '800', fontSize: 14 },
  qErr: { color: '#fca5a5', fontSize: 14, marginTop: 20, textAlign: 'center' },
  questTitle: { color: '#f1f5f9', fontSize: 19, fontWeight: '800', marginTop: 4 },
  questPremise: { color: '#cbd5e1', fontSize: 14, lineHeight: 21, marginTop: 6 },
  consBadge: { borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6, marginTop: 10, alignSelf: 'flex-start', borderWidth: 1 },
  consOk: { backgroundColor: '#0d1f17', borderColor: '#16a34a' },
  consWarn: { backgroundColor: '#2a1208', borderColor: '#b45309' },
  consTxt: { color: '#e2e8f0', fontSize: 12, fontWeight: '700' },
  questMeta: { color: '#a78bfa', fontSize: 13, fontWeight: '700', marginTop: 10 },
  questNode: { backgroundColor: '#10131f', borderRadius: 10, padding: 12, marginTop: 10, borderWidth: 1, borderColor: '#2a1a4a' },
  qnTitle: { color: '#d8b4fe', fontSize: 14, fontWeight: '800' },
  qnLoc: { color: '#cbd5e1', fontSize: 13, marginTop: 4 },
  qnBranch: { color: '#93C5FD', fontSize: 12, marginTop: 4, marginLeft: 6 },
  questEpilogue: { color: '#94a3b8', fontSize: 13, lineHeight: 20, marginTop: 12, fontStyle: 'italic' },
  monoBtn: { backgroundColor: '#0f3d2e', borderRadius: 12, paddingVertical: 14, alignItems: 'center', marginTop: 10, borderWidth: 1, borderColor: '#10b981' },
  monoBtnTxt: { color: '#6ee7b7', fontWeight: '800', fontSize: 14 },
  monoProg: { color: '#93C5FD', fontSize: 15, fontWeight: '800', marginTop: 14 },
  monoHint: { color: '#94a3b8', fontSize: 12.5, lineHeight: 19, marginTop: 8, textAlign: 'center', paddingHorizontal: 10 },
  monoText: { color: '#cbd5e1', fontSize: 12.5, lineHeight: 19, fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' }) },
  monoMeta: { color: '#64748b', fontSize: 11, marginTop: 14, textAlign: 'center' },
  monoActions: { flexDirection: 'row', gap: 10, marginBottom: 14 },
  monoActBtn: { flex: 1, backgroundColor: '#1e2030', borderRadius: 10, paddingVertical: 11, alignItems: 'center', borderWidth: 1, borderColor: '#334155' },
  monoActBtnDone: { backgroundColor: '#0d1f17', borderColor: '#16a34a' },
  monoActTxt: { color: '#cbd5e1', fontWeight: '800', fontSize: 13 },
  toolRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 10 },
  toolBtn: { flexGrow: 1, flexBasis: '47%', backgroundColor: '#10131f', borderRadius: 10, paddingVertical: 12, alignItems: 'center', borderWidth: 1, borderColor: '#1e2030' },
  toolTxt: { color: '#cbd5e1', fontWeight: '800', fontSize: 13 },
  posterStyleRow: { flexDirection: 'row', gap: 6, marginBottom: 12 },
  posterChip: { flex: 1, backgroundColor: '#10131f', borderRadius: 9, paddingVertical: 8, alignItems: 'center', borderWidth: 1, borderColor: '#1e2030' },
  posterChipOn: { borderColor: '#10b981', backgroundColor: '#0f3d2e' },
  posterChipTxt: { color: '#94a3b8', fontSize: 12, fontWeight: '700' },
  posterChipTxtOn: { color: '#6ee7b7' },
  posterImg: { width: '100%', aspectRatio: 1, borderRadius: 12, backgroundColor: '#000' },
  simStatsRow: { flexDirection: 'row', gap: 8, marginBottom: 14 },
  simStat: { flex: 1, backgroundColor: '#10131f', borderRadius: 10, paddingVertical: 12, alignItems: 'center', borderWidth: 1, borderColor: '#1e2030' },
  simStatN: { color: '#93C5FD', fontSize: 16, fontWeight: '800' },
  simStatL: { color: '#94a3b8', fontSize: 10.5, marginTop: 3 },
  simSection: { color: '#a78bfa', fontSize: 13, fontWeight: '800', marginTop: 8, marginBottom: 8 },
  simChart: { flexDirection: 'row', alignItems: 'flex-end', gap: 2, height: 78, backgroundColor: '#0b0e18', borderRadius: 8, padding: 6 },
  simBar: { flex: 1, backgroundColor: '#60A5FA', borderRadius: 2, minWidth: 3 },
  simAgent: { backgroundColor: '#10131f', borderRadius: 9, padding: 10, marginTop: 8, borderWidth: 1, borderColor: '#1e2030' },
  simAgentN: { color: '#e2e8f0', fontSize: 13.5, fontWeight: '800' },
  simAgentM: { color: '#94a3b8', fontSize: 12, marginTop: 3 },
});
