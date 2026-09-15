/**
 * /playable — Real Playable Export (Phase V.1).
 *
 * Closes the brief → playable loop: type a brief (or reuse a design-spec),
 * the Model Router generates a self-contained, mobile-touch HTML5 game, the
 * backend gates it on structural playability, and it plays LIVE in-app inside
 * a WebView.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator, TextInput,
  StyleSheet, SafeAreaView, Platform, KeyboardAvoidingView, Dimensions,
  Animated, Easing, Image, Switch, Modal, Alert,
} from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { useRouter, useLocalSearchParams } from 'expo-router';
import api from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';
import { safeGetItem, safeSetItem } from '../utils/safeStorage';
import { awardXp, getVisitorId } from '../src/utils/liveops';
import theme from '../theme/tokens';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';

/**
 * GeneratingPreview — premium "compiling" placeholder shown while a build runs.
 * A brand-violet halo + scanline bar pulse (RN Animated, cross-platform incl. web)
 * so the long generation feels alive rather than a dead spinner.
 */
function GeneratingPreview({ label }: { label: string }) {
  const pulse = React.useRef(new Animated.Value(0)).current;
  React.useEffect(() => {
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(pulse, { toValue: 1, duration: 1100, easing: Easing.inOut(Easing.ease), useNativeDriver: false }),
      Animated.timing(pulse, { toValue: 0, duration: 1100, easing: Easing.inOut(Easing.ease), useNativeDriver: false }),
    ]));
    loop.start();
    return () => loop.stop();
  }, [pulse]);
  const glowOpacity = pulse.interpolate({ inputRange: [0, 1], outputRange: [0.2, 0.85] });
  const barLeft = pulse.interpolate({ inputRange: [0, 1], outputRange: ['-30%', '100%'] });
  return (
    <View testID="pl-generating" style={genStyles.wrap}>
      <Animated.View style={[genStyles.halo, { opacity: glowOpacity, pointerEvents: 'none' }]} />
      <Animated.View style={[genStyles.scanBar, { left: barLeft, pointerEvents: 'none' }]} />
      <Text style={genStyles.spark}>✨</Text>
      <Text style={genStyles.label}>{label}</Text>
      <Text style={genStyles.sub}>Compiling the matrix…</Text>
    </View>
  );
}

const genStyles = StyleSheet.create({
  wrap: {
    marginTop: 20, height: 200, borderRadius: 16, borderWidth: 1.5, borderColor: '#2E1B5B',
    backgroundColor: '#0b0814', alignItems: 'center', justifyContent: 'center', overflow: 'hidden',
  },
  halo: {
    ...StyleSheet.absoluteFillObject, borderRadius: 16, borderWidth: 2, borderColor: '#8B5CF6',
    ...Platform.select({ ios: { shadowColor: '#8B5CF6', shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.9, shadowRadius: 22 }, default: {} }),
  },
  scanBar: { position: 'absolute', top: 0, bottom: 0, width: '30%', backgroundColor: 'rgba(139,92,246,0.10)' },
  spark: { fontSize: 30, marginBottom: 10 },
  label: { color: '#ddd6fe', fontSize: 14, fontWeight: '800', textAlign: 'center', paddingHorizontal: 20 },
  sub: { color: '#7c6fb0', fontSize: 12, marginTop: 6, fontWeight: '600' },
});

// Cross-platform game preview: an <iframe> on Expo Web, the native
// react-native-webview elsewhere (lazy-required so web bundling never breaks).
let _WebView: any = null;
function _tryLoadWebView() {
  if (_WebView) return _WebView;
  try {
     
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    _WebView = require('react-native-webview').WebView;
  } catch {
    _WebView = null;
  }
  return _WebView;
}
const GamePreview: React.FC<{ uri: string; testID?: string; onGameError?: (msg: string) => void }> = ({ uri, testID, onGameError }) => {
  // Listen for runtime errors posted by the injected reporter (web iframe path).
  React.useEffect(() => {
    if (Platform.OS !== 'web' || !onGameError || typeof window === 'undefined') return;
    const handler = (e: any) => {
      const d = e?.data;
      if (d && d.__pl_error) onGameError(String(d.message || 'Runtime error'));
    };
    window.addEventListener('message', handler);
    return () => window.removeEventListener('message', handler);
  }, [onGameError]);

  if (Platform.OS === 'web') {
    return React.createElement('iframe', {
      src: uri, title: 'game-preview', 'data-testid': testID,
      style: { border: 0, background: '#000', width: '100%', height: '100%' },
    });
  }
  const W = _tryLoadWebView();
  if (!W) {
    return (
      <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: '#000' }}>
        <Text style={{ color: '#94a3b8', fontSize: 12 }}>Preview unavailable on this device</Text>
      </View>
    );
  }
  return (
    <W
      testID={testID}
      source={{ uri }}
      style={{ flex: 1, backgroundColor: '#000' }}
      originWhitelist={['*']}
      javaScriptEnabled
      domStorageEnabled
      scalesPageToFit={false}
      allowsInlineMediaPlayback
      mediaPlaybackRequiresUserAction={false}
      onMessage={(e: any) => {
        try {
          const d = JSON.parse(e?.nativeEvent?.data || '{}');
          if (d && d.__pl_error && onGameError) onGameError(String(d.message || 'Runtime error'));
        } catch { /* ignore non-JSON messages */ }
      }}
    />
  );
};

interface Evaluation {
  available?: boolean; overall?: number; verdict?: string;
  playability?: number; coherence?: number; fun?: number; polish?: number;
  critique?: string; top_fix?: string; judge_model?: string;
  difficulty?: string; length?: string;
}
interface Playable {
  playable_id: string; title: string; genre: string; status: string;
  playability_score: number; missing_checks: string[]; bytes: number;
  model?: string; raw_path: string; llm_error?: string | null;
  repair_attempts?: number; evaluation?: Evaluation; parent_id?: string | null;
  tweak?: string; intricacy?: number; repair_trail?: any[];
}
interface ListItem {
  playable_id: string; title: string; genre: string; status: string;
  playability_score: number; created_at: string; parent_id?: string | null; has_cover?: boolean;
  remix_count?: number; champion_weeks?: number; reactions?: Record<string, number>;
}

// Small cover thumbnail used in lists (real art when available, else glyph).
function MiniCover({ id, hasCover, size = 38 }: { id: string; hasCover?: boolean; size?: number }) {
  const [err, setErr] = React.useState(false);
  if (hasCover && !err) {
    return <Image source={{ uri: `${BACKEND}/api/playable/${id}/cover.png` }} style={{ width: size, height: size, borderRadius: 8, backgroundColor: '#141414' }} onError={() => setErr(true)} />;
  }
  return <View style={{ width: size, height: size, borderRadius: 8, backgroundColor: '#16203a', alignItems: 'center', justifyContent: 'center' }}><Text style={{ fontSize: size * 0.45 }}>🎮</Text></View>;
}
interface LineageNode { playable_id: string; title: string; derive_mode?: string; status?: string; }
interface Lineage { ancestors: LineageNode[]; children: LineageNode[]; }

const TWEAK_CHIPS = ['Make it harder', 'Add a boss', 'Faster pace', 'New color theme', 'Add power-ups'];

// One-tap polish chain — mirrors backend routes/playable_polish.py _STEPS (sentience → physics → aesthetics).
const POLISH_STEPS: { n: number; icon: string; label: string }[] = [
  { n: 1, icon: '👾', label: 'Living NPCs' },
  { n: 2, icon: '🧲', label: 'Physics' },
  { n: 3, icon: '🎨', label: 'FX + Audio' },
];

export default function PlayableScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ id?: string; remix?: string; brief?: string; autopolish?: string }>();
  const autopolishedRef = React.useRef(false);
  const haptics = useHaptics();
  const tweakRef = React.useRef<TextInput>(null);
  const [brief, setBrief] = React.useState('A one-thumb arcade game where you tap to make a glowing orb hop between rising platforms — go as high as you can without falling.');
  const [busy, setBusy] = React.useState(false);
  const [busyLabel, setBusyLabel] = React.useState('Building your game…');
  const [polish, setPolish] = React.useState<{ step: number; total: number } | null>(null);
  const [game, setGame] = React.useState<Playable | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [recent, setRecent] = React.useState<ListItem[]>([]);
  const [webKey, setWebKey] = React.useState(0);
  const [gameError, setGameError] = React.useState<string | null>(null);
  const [repairing, setRepairing] = React.useState(false);
  const [repairMsg, setRepairMsg] = React.useState('');
  const [tweak, setTweak] = React.useState('');
  const [fix, setFix] = React.useState('');
  const [lineage, setLineage] = React.useState<Lineage | null>(null);
  const [copied, setCopied] = React.useState(false);
  const [depth, setDepth] = React.useState<'studio' | 'fast'>('studio');
  const [showCompare, setShowCompare] = React.useState(false);
  const [vote, setVote] = React.useState<{ this: number; opp: number } | null>(null);
  const [showImport, setShowImport] = React.useState(false);
  const [importBuilds, setImportBuilds] = React.useState<any[]>([]);
  const [assetPack, setAssetPack] = React.useState<any>(null);
  const [pipeline, setPipeline] = React.useState<any>(null);
  const [forging, setForging] = React.useState<string | null>(null);

  const loadPipeline = React.useCallback(async (pid: string) => {
    const pr = await api.get<any>(`/api/playable/${pid}/pipeline`, { timeoutMs: 12_000 });
    if (pr.ok && pr.data && !pr.data.error) setPipeline(pr.data);
  }, []);

  const forgeStage = React.useCallback(async (st: any) => {
    const pid = game?.playable_id;
    if (!pid || !st.forge) return;
    setForging(st.key);
    const r = await api.post<any>(`/api/pipeline/${pid}/forge/${st.forge}/async`, {}, { timeoutMs: 15_000 });
    if (r.ok && r.data?.job_id) {
      const jid = r.data.job_id;
      for (let i = 0; i < 30; i++) {
        await new Promise(res => setTimeout(res, 3500));
        const jr = await api.get<any>(`/api/playable/job/${jid}`, { timeoutMs: 12_000 });
        if (jr.data?.job_status === 'done' || jr.data?.job_status === 'error') break;
      }
      await loadPipeline(pid);
    }
    setForging(null);
  }, [game?.playable_id, loadPipeline]);
  const [board, setBoard] = React.useState<any[]>([]);
  const [boardAssetsOnly, setBoardAssetsOnly] = React.useState(false);
  const [showBoard, setShowBoard] = React.useState(false);
  const [variants, setVariants] = React.useState<any[] | null>(null);
  const [series, setSeries] = React.useState<any[] | null>(null);
  const [autoCover, setAutoCover] = React.useState(false);
  const [autoCoverPid, setAutoCoverPid] = React.useState<string | null>(null);
  const autoCoverRef = React.useRef(false);
  React.useEffect(() => { autoCoverRef.current = autoCover; }, [autoCover]);
  // persist the auto-cover preference
  React.useEffect(() => { (async () => {
    const v = await safeGetItem('@playable/autoCover');
    if (v === '1') { setAutoCover(true); autoCoverRef.current = true; }
  })(); }, []);
  const toggleAutoCover = React.useCallback((v: boolean) => {
    setAutoCover(v); autoCoverRef.current = v; safeSetItem('@playable/autoCover', v ? '1' : '0');
  }, []);

  const loadRecent = React.useCallback(async () => {
    const r = await api.get<{ playables: ListItem[] }>('/api/playable/list?limit=10');
    if (r.ok && r.data) setRecent(r.data.playables || []);
  }, []);

  const loadLineage = React.useCallback(async (id: string) => {
    setLineage(null);
    const r = await api.get<Lineage>(`/api/playable/${id}/lineage`, { timeoutMs: 12_000 });
    if (r.ok && r.data && ((r.data.ancestors || []).length || (r.data.children || []).length)) {
      setLineage({ ancestors: r.data.ancestors || [], children: r.data.children || [] });
    }
  }, []);

  const loadBoard = React.useCallback(async () => {
    const r = await api.get<{ leaderboard: any[] }>(
      `/api/playable/leaderboard?limit=15${boardAssetsOnly ? '&assets=complete' : ''}`, { timeoutMs: 12_000 });
    if (r.ok && r.data) setBoard(r.data.leaderboard || []);
  }, [boardAssetsOnly]);

  const loadImportBuilds = React.useCallback(async () => {
    const r = await api.get<{ builds: any[] }>('/api/playable/import/builds?limit=40', { timeoutMs: 12_000 });
    if (r.ok && r.data) setImportBuilds(r.data.builds || []);
  }, []);

  React.useEffect(() => { loadRecent(); loadBoard(); loadImportBuilds(); }, [loadRecent, loadBoard, loadImportBuilds]);
  // refresh lineage whenever the shown game changes
  React.useEffect(() => { if (game?.playable_id) loadLineage(game.playable_id); }, [game?.playable_id, loadLineage]);
  // load the game's Asset-Genesis pack status (completion tag + thumbnails)
  React.useEffect(() => {
    let alive = true;
    const pid = game?.playable_id;
    if (!pid) { setAssetPack(null); return; }
    (async () => {
      const r = await api.get<any>(`/api/assets/genesis/game/${pid}`, { timeoutMs: 12_000 });
      if (alive && r.ok && r.data && !r.data.error) setAssetPack(r.data);
      await loadPipeline(pid);
    })();
    return () => { alive = false; };
  }, [game?.playable_id, loadPipeline]);

  const shareGame = React.useCallback(async () => {
    if (!game) return;
    haptics.selection();
    // Prefer the in-app deep link (opens the game with full play + evolve/remix).
    // On web, an absolute /playable?id= URL; on native, the codedock:// scheme.
    const url = Platform.OS === 'web'
      ? (typeof window !== 'undefined' ? `${window.location.origin}/playable?id=${game.playable_id}` : `${BACKEND}/playable?id=${game.playable_id}`)
      : `codedock://playable?id=${game.playable_id}`;
    try {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && (navigator as any).clipboard) {
        await (navigator as any).clipboard.writeText(url);
      } else {
        await Clipboard.setStringAsync(url);
      }
      setCopied(true); haptics.notify('success'); setTimeout(() => setCopied(false), 2000);
      awardXp('share');
    } catch {
      setError('Could not copy link.');
    }
  }, [game, haptics]);

  // ── AI cover art (Nano Banana): generate on demand, cached server-side ──
  const shareCard = React.useCallback(async () => {
    if (!game) return;
    haptics.selection();
    const base = Platform.OS === 'web' && typeof window !== 'undefined' ? window.location.origin : BACKEND;
    const url = `${base}/api/playable/${game.playable_id}/card.png`;
    try {
      if (Platform.OS === 'web' && typeof navigator !== 'undefined' && (navigator as any).clipboard) {
        await (navigator as any).clipboard.writeText(url);
      } else {
        await Clipboard.setStringAsync(url);
      }
      setCopied(true); haptics.notify('success'); setTimeout(() => setCopied(false), 2000);
    } catch { setError('Could not copy card link.'); }
  }, [game, haptics]);

  // ── 📚 Save to Collection (Creator Marketplace) ──
  const [collModal, setCollModal] = React.useState(false);  const [collList, setCollList] = React.useState<{ collection_id: string; name: string; count: number }[]>([]);
  const [collBusy, setCollBusy] = React.useState(false);
  const [newColl, setNewColl] = React.useState('');
  const [collMsg, setCollMsg] = React.useState('');
  const loadColls = React.useCallback(async () => {
    const r = await api.get<{ collections: any[] }>('/api/collections', { timeoutMs: 12_000 });
    if (r.ok && r.data) setCollList((r.data.collections || []).map((c: any) => ({ collection_id: c.collection_id, name: c.name, count: c.count })));
  }, []);
  const openCollModal = React.useCallback(() => { if (!game) return; haptics.selection(); setCollMsg(''); setCollModal(true); loadColls(); }, [game, haptics, loadColls]);

  // ── 🚩 Report (Trust & Safety) ──
  const [reportModal, setReportModal] = React.useState(false);
  const [reportBusy, setReportBusy] = React.useState(false);
  const [reportMsg, setReportMsg] = React.useState('');
  const submitReport = React.useCallback(async (reason: string) => {
    if (!game) return;
    haptics.selection();
    setReportBusy(true);
    const visitor = await getVisitorId();
    const r = await api.post('/api/governance/report', { playable_id: game.playable_id, reason, reporter_id: visitor }, { timeoutMs: 12_000 });
    setReportBusy(false);
    if (r.ok) { setReportMsg('✓ Thanks — our moderators will review this game.'); setTimeout(() => setReportModal(false), 1400); }
    else setReportMsg('Could not submit report. Please try again.');
  }, [game, haptics]);

  // ── ⚖️ Creator appeal (shown only when this game is restricted by moderation) ──
  const [modStatus, setModStatus] = React.useState<string>('ok');
  const [appealModal, setAppealModal] = React.useState(false);
  const [appealReason, setAppealReason] = React.useState('');
  const [appealBusy, setAppealBusy] = React.useState(false);
  const [appealMsg, setAppealMsg] = React.useState('');
  React.useEffect(() => {
    const pid = game?.playable_id;
    if (!pid) { setModStatus('ok'); return; }
    let alive = true;
    api.get<{ moderation_status?: string }>(`/api/governance/status/${pid}`, { timeoutMs: 10_000 })
      .then((res) => { if (alive && res.ok && res.data) setModStatus(res.data.moderation_status || 'ok'); });
    return () => { alive = false; };
  }, [game?.playable_id]);
  const submitAppeal = React.useCallback(async () => {
    if (!game || appealReason.trim().length < 10) { setAppealMsg('Please write at least 10 characters.'); return; }
    haptics.selection();
    setAppealBusy(true);
    const visitor = await getVisitorId();
    const r = await api.post<{ appeal_id?: string; error?: string }>('/api/governance/appeal',
      { playable_id: game.playable_id, reason: appealReason.trim(), creator_id: visitor }, { timeoutMs: 12_000 });
    setAppealBusy(false);
    if (r.ok && r.data?.appeal_id) { setAppealMsg('✓ Appeal submitted — a moderator will re-review your game.'); setTimeout(() => setAppealModal(false), 1500); }
    else setAppealMsg(r.data?.error || 'Could not submit appeal.');
  }, [game, appealReason, haptics]);
  const addToColl = React.useCallback(async (cid: string, name: string) => {
    if (!game) return;
    haptics.selection();
    const r = await api.post<{ added: boolean }>(`/api/collections/${cid}/games`, { playable_id: game.playable_id }, { timeoutMs: 12_000 });
    if (r.ok) { setCollMsg(r.data?.added ? `Added to “${name}” ✓` : `Already in “${name}”`); haptics.notify('success'); }
    else haptics.notify('error');
  }, [game, haptics]);
  const createAndAdd = React.useCallback(async () => {
    const name = newColl.trim();
    if (!name || !game || collBusy) return;
    haptics.selection(); setCollBusy(true);
    const c = await api.post<{ collection_id: string }>('/api/collections', { name }, { timeoutMs: 12_000 });
    if (c.ok && c.data?.collection_id) {
      await api.post(`/api/collections/${c.data.collection_id}/games`, { playable_id: game.playable_id }, { timeoutMs: 12_000 });
      setNewColl(''); setCollMsg(`Created “${name}” & added ✓`); haptics.notify('success'); loadColls();
    } else haptics.notify('error');
    setCollBusy(false);
  }, [newColl, game, collBusy, haptics, loadColls]);

  // ── 🔥 Emoji reactions ──
  const REACTIONS = ['🔥', '❤️', '😂', '😮', '👍'];
  const sendReaction = React.useCallback(async (emoji: string) => {
    if (!game) return;
    haptics.selection();
    // optimistic bump
    setGame((g) => g ? { ...g, reactions: { ...(g.reactions || {}), [emoji]: ((g.reactions || {})[emoji] || 0) + 1 } } : g);
    const r = await api.post<{ reactions: Record<string, number> }>(`/api/playable/${game.playable_id}/react`, { emoji }, { timeoutMs: 10_000, retries: 0 });
    if (r.ok && r.data?.reactions) setGame((g) => g ? { ...g, reactions: r.data!.reactions } : g);
    awardXp('react');
  }, [game, haptics]);

  // 🔧 Auto-repair (async): kick a background repair job and poll /job/{id} so a
  // long (~100s) LLM repair never hits a public-ingress edge timeout.
  const autoRepair = React.useCallback(async () => {
    if (!game || repairing) return;
    haptics.selection(); setRepairing(true); setRepairMsg('Analyzing the crash…');
    const start = await api.post<{ job_id?: string }>(
      `/api/playable/${game.playable_id}/repair/async`, { error: gameError || '' }, { timeoutMs: 15_000, retries: 0 });
    if (!start.ok || !start.data?.job_id) {
      setRepairing(false); setRepairMsg('Could not start repair — please try again.'); haptics.notify('error'); return;
    }
    const jobId = start.data.job_id;
    let done = false;
    for (let i = 0; i < 80 && !done; i++) {
      await new Promise((r) => setTimeout(r, 3000));
      const st = await api.get<{ job_status?: string; repaired?: boolean; score?: number }>(
        `/api/playable/job/${jobId}`, { timeoutMs: 12_000, retries: 0 });
      const js = st.ok ? st.data?.job_status : undefined;
      if (js === 'done') {
        done = true;
        if (st.data?.repaired) {
          setRepairMsg(`✓ Fixed — playability ${st.data.score}/100. Reloading…`);
          haptics.notify('success'); setGameError(null); setWebKey((k) => k + 1);
        } else {
          setRepairMsg('Could not auto-fix this one — try ✨ New game or 🔱 Remix.'); haptics.notify('error');
        }
      } else if (js === 'error') {
        done = true; setRepairMsg('Repair failed — please try again.'); haptics.notify('error');
      } else {
        setRepairMsg(`🔧 Repairing… (${(i + 1) * 3}s)`);
      }
    }
    if (!done) setRepairMsg('Still working in the background — reopen the game shortly.');
    setRepairing(false);
  }, [game, repairing, gameError, haptics]);
  const [coverBust, setCoverBust] = React.useState(0);
  const [coverHidden, setCoverHidden] = React.useState(false);
  const [coverBusy, setCoverBusy] = React.useState(false);
  // re-probe the cover whenever the shown game changes
  React.useEffect(() => { setCoverHidden(false); setCoverBust((b) => b + 1); }, [game?.playable_id]);

  const makeCover = React.useCallback(async () => {
    if (!game || coverBusy) return;
    haptics.selection(); setCoverBusy(true);
    const r = await api.post<{ has_cover?: boolean }>(`/api/playable/${game.playable_id}/cover`, {}, { timeoutMs: 75_000, retries: 0 });
    setCoverBusy(false);
    if (r.ok && r.data?.has_cover) { setCoverHidden(false); setCoverBust((b) => b + 1); haptics.notify('success'); }
    else { haptics.notify('error'); }
  }, [game, coverBusy, haptics]);

  // 🔁 Regenerate cover (force fresh art, bypassing the cache).
  const regenCover = React.useCallback(async () => {
    if (!game || coverBusy) return;
    haptics.selection(); setCoverBusy(true);
    const r = await api.post<{ has_cover?: boolean }>(`/api/playable/${game.playable_id}/cover?force=true`, {}, { timeoutMs: 75_000, retries: 0 });
    setCoverBusy(false);
    if (r.ok && r.data?.has_cover) { setCoverHidden(false); setCoverBust((b) => b + 1); haptics.notify('success'); }
    else { haptics.notify('error'); }
  }, [game, coverBusy, haptics]);

  // 🖼️ Generate 3 cover OPTIONS to pick a favourite from.
  const [coverOpts, setCoverOpts] = React.useState<number[] | null>(null);
  const [coverOptsBusy, setCoverOptsBusy] = React.useState(false);
  React.useEffect(() => { setCoverOpts(null); }, [game?.playable_id]);
  const genCoverOptions = React.useCallback(async () => {
    if (!game || coverOptsBusy) return;
    haptics.selection(); setCoverOptsBusy(true); setCoverOpts(null);
    const r = await api.post<{ options?: number[] }>(`/api/playable/${game.playable_id}/cover/options?count=3`, {}, { timeoutMs: 120_000, retries: 0 });
    setCoverOptsBusy(false);
    if (r.ok && r.data?.options?.length) { setCoverOpts(r.data.options); haptics.notify('success'); }
    else { haptics.notify('error'); }
  }, [game, coverOptsBusy, haptics]);
  const selectCoverOption = React.useCallback(async (idx: number) => {
    if (!game) return;
    haptics.selection();
    const r = await api.post<{ has_cover?: boolean }>(`/api/playable/${game.playable_id}/cover/select`, { index: idx }, { timeoutMs: 15_000, retries: 0 });
    if (r.ok && r.data?.has_cover) { setCoverOpts(null); setCoverHidden(false); setCoverBust((b) => b + 1); haptics.notify('success'); }
  }, [game, haptics]);

  // Opt-in auto-cover: when a FRESH build completes and the toggle is on, mint a
  // cover automatically (idempotent endpoint → never double-spends if it exists).
  React.useEffect(() => {
    if (autoCoverPid && game?.playable_id === autoCoverPid) {
      const t = setTimeout(() => { makeCover(); setAutoCoverPid(null); }, 900);
      return () => clearTimeout(t);
    }
  }, [autoCoverPid, game?.playable_id, makeCover]);

  // Shared job poller (used by generate / remix / sequel / competitor / prequel /
  // expansion / variants). Rigorous quality refinement chains several LLM rounds,
  // and Expansion (3× volume) can run 15+ min, so allow a very generous window.
  const pollJob = React.useCallback(async (jobId: string) => {
    const deadline = Date.now() + 2_400_000;
    while (Date.now() < deadline) {
      await new Promise((res) => setTimeout(res, 3000));
      const j = await api.get<any>(`/api/playable/job/${jobId}`, { timeoutMs: 15_000 });
      const d = j.data;
      if (!j.ok || !d) continue;
      if (d.job_status === 'running' && d.kind === 'polish' && d.step) {
        const tot = d.step_total || 3;
        setBusyLabel(`✨ Polishing ${d.step}/${tot}${d.step_label ? ' · ' + d.step_label : ''}…`);
      }
      if (d.job_status === 'done' && d.kind === 'series') {
        setSeries(d.series || []); loadRecent(); setBusy(false); haptics.notify('success');
        if (autoCoverRef.current) {
          const ids = (d.series || []).filter((s: any) => s.status === 'ready' && s.playable_id).map((s: any) => s.playable_id);
          (async () => {
            for (const id of ids) {
              const cr = await api.post<{ has_cover?: boolean }>(`/api/playable/${id}/cover`, {}, { timeoutMs: 75_000, retries: 0 });
              if (cr.ok && cr.data?.has_cover) setSeries((prev) => prev ? prev.map((s) => s.playable_id === id ? { ...s, has_cover: true } : s) : prev);
            }
          })();
        }
        return;
      }
      if (d.job_status === 'done' && d.kind === 'variants') {
        setVariants(d.variants || []); loadRecent(); setBusy(false); haptics.notify('success');
        if (autoCoverRef.current) {
          const ids = (d.variants || []).filter((v: any) => v.status === 'ready' && v.playable_id).map((v: any) => v.playable_id);
          (async () => {
            for (const id of ids) {
              const cr = await api.post<{ has_cover?: boolean }>(`/api/playable/${id}/cover`, {}, { timeoutMs: 75_000, retries: 0 });
              if (cr.ok && cr.data?.has_cover) {
                setVariants((prev) => prev ? prev.map((v) => v.playable_id === id ? { ...v, has_cover: true } : v) : prev);
              }
            }
          })();
        }
        return;
      }
      if (d.job_status === 'done' && (d.kind === 'finetune' || d.kind === 'bugsquash')) {
        if (d.edited && d.status === 'ready') {
          setGame(d as Playable); setWebKey((k) => k + 1); setGameError(null); loadRecent();
          setBusy(false); haptics.notify('success');
        } else {
          setError(d.error || `Couldn't apply that safely (score ${d.score ?? '–'}/100). Try rephrasing the request.`);
          setBusy(false); haptics.notify('error');
        }
        return;
      }
      if (d.job_status === 'done' && d.kind === 'polish') {
        setPolish(null);
        const n = Array.isArray(d.applied) ? d.applied.length : 0;
        if (n > 0) {
          setGame((g) => g ? ({ ...g, version: d.version ?? g.version, playability_score: d.score ?? g.playability_score } as Playable) : g);
          setWebKey((k) => k + 1); setGameError(null); loadRecent();
          setBusy(false); haptics.notify('success');
        } else {
          setError("Polish couldn't apply any layer safely — the game stayed unchanged.");
          setBusy(false); haptics.notify('error');
        }
        return;
      }
      if (d.job_status === 'done' && (d.kind === 'sentience' || d.kind === 'aesthetics' || d.kind === 'physics' || d.kind === 'factions')) {
        if (d.applied) {
          setGame((g) => g ? ({ ...g, version: d.version, playability_score: d.score } as Playable) : g);
          setWebKey((k) => k + 1); setGameError(null); loadRecent();
          setBusy(false); haptics.notify('success');
        } else {
          setError(d.error || `Couldn't apply that safely (score ${d.score ?? '–'}/100). The game stayed unchanged.`);
          setBusy(false); haptics.notify('error');
        }
        return;
      }
      if (d.job_status === 'done' && d.status === 'ready') {
        setGame(d as Playable); setWebKey((k) => k + 1); loadRecent(); setBusy(false); haptics.notify('success');
        if (autoCoverRef.current) setAutoCoverPid((d as Playable).playable_id);
        return;
      }
      if (d.job_status === 'done' && d.status === 'failed') {
        setError(`Generation did not produce a runnable game (score ${d.playability_score}/100, missing: ${(d.missing_checks || []).join(', ')}). Try again or refine the brief.`);
        setBusy(false); haptics.notify('error'); return;
      }
      if (d.job_status === 'error') {
        setError(d.error || 'generation failed'); setBusy(false); haptics.notify('error'); return;
      }
    }
    setError('Timed out building the game. Please try again.');
    setBusy(false); haptics.notify('error');
  }, [loadRecent, haptics]);

  const generate = React.useCallback(async () => {
    if (brief.trim().length < 8 || busy) return;
    haptics.selection();
    setBusy(true); setBusyLabel(depth === 'fast' ? 'Quick-building your game…' : 'Crafting a studio-grade game…'); setError(null); setGame(null);
    const creatorId = await getVisitorId();
    const kick = await api.post<{ job_id?: string; error?: string }>(
      '/api/playable/generate/async', { brief, depth, creator_id: creatorId }, { timeoutMs: 20_000, retries: 1 });
    const jobId = kick.data?.job_id;
    if (!kick.ok || !jobId) {
      setError(kick.data?.error || kick.error || `HTTP ${kick.status}`); setBusy(false); return;
    }
    awardXp('generate');
    await pollJob(jobId);
  }, [brief, busy, haptics, pollJob, depth]);

  const runDerive = React.useCallback(async (mode: 'remix' | 'sequel' | 'competitor' | 'prequel' | 'expansion' | 'interlude' | 'conclusion', instruction: string) => {
    const t = instruction.trim();
    if (!game || busy) return;
    if (mode === 'remix' && t.length < 3) return;  // remix needs a tweak
    haptics.selection();
    const labels: Record<string, string> = {
      remix: 'Remixing your game…', sequel: 'Building the sequel…',
      competitor: 'Spinning up a rival (PvP + puzzles, 2×)…',
      prequel: 'Crafting the cozy prequel…',
      expansion: 'Building the deluxe 2.5× expansion… (can take 12-20 min)',
      interlude: 'Writing the lore-rich interlude…',
      conclusion: 'Building the grand finale + multiple endings…',
    };
    setBusy(true); setBusyLabel(labels[mode]); setError(null); setVariants(null); setSeries(null);
    const kick = await api.post<{ job_id?: string; error?: string }>(
      `/api/playable/${game.playable_id}/${mode}/async`, { tweak: t, depth }, { timeoutMs: 20_000, retries: 1 });
    const jobId = kick.data?.job_id;
    if (!kick.ok || !jobId) {
      setError(kick.data?.error || kick.error || `HTTP ${kick.status}`); setBusy(false); return;
    }
    if (mode === 'remix') awardXp('remix');
    setTweak('');
    await pollJob(jobId);
  }, [game, busy, haptics, pollJob, depth]);
  const runRemix = React.useCallback((instruction: string) => runDerive('remix', instruction), [runDerive]);

  const runEdit = React.useCallback(async (mode: 'finetune' | 'bugsquash', instruction: string) => {
    const t = instruction.trim();
    if (!game || busy || t.length < 3) return;
    haptics.selection();
    setBusy(true);
    setBusyLabel(mode === 'finetune' ? 'Fine-tuning this game in place…' : 'Squashing that bug…');
    setError(null); setVariants(null); setSeries(null);
    const kick = await api.post<{ job_id?: string; error?: string }>(
      `/api/playable/${game.playable_id}/${mode}/async`, { instruction: t }, { timeoutMs: 20_000, retries: 1 });
    const jobId = kick.data?.job_id;
    if (!kick.ok || !jobId) {
      setError(kick.data?.error || kick.error || `HTTP ${kick.status}`); setBusy(false); return;
    }
    setFix('');
    await pollJob(jobId);
  }, [game, busy, haptics, pollJob]);

  const runEnhance = React.useCallback(async (mode: 'sentience' | 'aesthetics' | 'physics' | 'factions', worldId?: string) => {
    if (!game || busy) return;
    haptics.selection();
    setPolish(null);
    setBusy(true);
    setBusyLabel(mode === 'sentience'
      ? 'Bringing NPCs to life (memory + behaviour AI)…'
      : mode === 'physics'
        ? 'Wiring deterministic physics (gravity + collision)…'
        : mode === 'factions'
          ? 'Adding a live faction/world-events backdrop…'
          : 'Adding neural FX + adaptive audio…');
    setError(null); setVariants(null); setSeries(null);
    const suffix = mode === 'factions' && worldId ? `?world_id=${encodeURIComponent(worldId)}` : '';
    const kick = await api.post<{ job_id?: string; error?: string }>(
      `/api/playable/${game.playable_id}/apply-${mode}/async${suffix}`, {}, { timeoutMs: 20_000, retries: 1 });
    const jobId = kick.data?.job_id;
    if (!kick.ok || !jobId) {
      setError(kick.data?.error || kick.error || `HTTP ${kick.status}`); setBusy(false); return;
    }
    await pollJob(jobId);
  }, [game, busy, haptics, pollJob]);

  const pickWorldThenFactions = React.useCallback(async () => {
    if (!game || busy) return;
    haptics.selection();
    const r = await api.get<any>('/api/worldforge/worlds?limit=6', { timeoutMs: 10_000 });
    const arr = Array.isArray(r.data) ? r.data : (r.data?.worlds || []);
    if (!arr.length) { runEnhance('factions'); return; }
    const opts: any[] = arr.slice(0, 3).map((w: any) => ({
      text: `🌍 ${w.name || 'World'}`, onPress: () => runEnhance('factions', w.world_id),
    }));
    opts.push({ text: 'Generic factions', onPress: () => runEnhance('factions') });
    opts.push({ text: 'Cancel', style: 'cancel' });
    Alert.alert('Seed world events', 'Use faction names from one of your worlds?', opts);
  }, [game, busy, haptics, runEnhance]);

  const runPolish = React.useCallback(async () => {
    if (!game || busy) return;
    haptics.selection();
    setBusy(true);
    setPolish({ step: 0, total: 3 });
    setBusyLabel('✨ One-tap polish: Living NPCs → Physics → FX + Audio (this takes several minutes)…');
    setError(null); setVariants(null); setSeries(null);
    const kick = await api.post<{ job_id?: string; error?: string }>(
      `/api/playable/${game.playable_id}/polish/async`, {}, { timeoutMs: 20_000, retries: 1 });
    const jobId = kick.data?.job_id;
    if (!kick.ok || !jobId) {
      setError(kick.data?.error || kick.error || `HTTP ${kick.status}`); setBusy(false); return;
    }
    await pollJob(jobId);
  }, [game, busy, haptics, pollJob]);

  const runVariants = React.useCallback(async () => {
    if (!game || busy) return;
    haptics.selection();
    setBusy(true); setBusyLabel('Generating 4 colour variants…'); setError(null); setVariants(null); setSeries(null);
    const kick = await api.post<{ job_id?: string; error?: string }>(
      `/api/playable/${game.playable_id}/variants/async`, { depth }, { timeoutMs: 20_000, retries: 1 });
    const jobId = kick.data?.job_id;
    if (!kick.ok || !jobId) {
      setError(kick.data?.error || kick.error || `HTTP ${kick.status}`); setBusy(false); return;
    }
    await pollJob(jobId);
  }, [game, busy, haptics, pollJob, depth]);

  const runSeries = React.useCallback(async () => {
    if (!game || busy) return;
    haptics.selection();
    setBusy(true); setBusyLabel('Building a snowball series (3 escalating games)…'); setError(null); setVariants(null); setSeries(null);
    const kick = await api.post<{ job_id?: string; error?: string }>(
      `/api/playable/${game.playable_id}/series/async`, { depth, steps: 3 }, { timeoutMs: 20_000, retries: 1 });
    const jobId = kick.data?.job_id;
    if (!kick.ok || !jobId) {
      setError(kick.data?.error || kick.error || `HTTP ${kick.status}`); setBusy(false); return;
    }
    await pollJob(jobId);
  }, [game, busy, haptics, pollJob, depth]);

  const castVote = React.useCallback(async (winner: 'this' | 'parent') => {
    if (!game || !game.parent_id) return;
    haptics.selection();
    const winnerId = winner === 'this' ? game.playable_id : game.parent_id;
    const r = await api.post<any>(`/api/playable/${game.playable_id}/vote`,
      { opponent_id: game.parent_id, winner_id: winnerId }, { timeoutMs: 12_000 });
    if (r.ok && r.data && r.data.this) {
      setVote({ this: r.data.this.wins || 0, opp: r.data.opponent.wins || 0 });
      awardXp('vote');
    }
  }, [game, haptics]);

  const runImport = React.useCallback(async (buildId: string) => {
    if (busy) return;
    haptics.selection();
    setShowImport(false);
    setBusy(true); setBusyLabel('Importing from Vault…'); setError(null); setGame(null);
    const kick = await api.post<{ job_id?: string; error?: string }>(
      '/api/playable/import-build/async', { build_id: buildId, depth }, { timeoutMs: 20_000, retries: 1 });
    const jobId = kick.data?.job_id;
    if (!kick.ok || !jobId) {
      setError(kick.data?.error || kick.error || `HTTP ${kick.status}`); setBusy(false); return;
    }
    await pollJob(jobId);
  }, [busy, haptics, depth, pollJob]);

  const openRecent = React.useCallback(async (id: string) => {
    haptics.selection();
    const r = await api.get<Playable>(`/api/playable/${id}`);
    if (r.ok && r.data && (r.data as any).playable_id) {
      const d = r.data as any;
      setGame({ ...d, raw_path: `/api/playable/${id}/raw` });
      setError(null); setWebKey((k) => k + 1); setVariants(null);
      // ▶ count this open as a play (best-effort, powers Trending).
      api.post(`/api/playable/${id}/play`, {}, { timeoutMs: 8_000, retries: 0 }).catch(() => {});
      awardXp('play');
    }
  }, [haptics]);

  // Deep link: /playable?id=<pid> opens that game directly (shared links, Vault).
  // Optional &remix=1 (marketplace "remix this top game") focuses the evolve box.
  const deepLinkedRef = React.useRef<string | null>(null);
  React.useEffect(() => {
    const id = (params.id || '').toString().trim();
    if (id && deepLinkedRef.current !== id) {
      deepLinkedRef.current = id;
      openRecent(id);
    }
  }, [params.id, openRecent]);

  // Daily Challenge deep-link: /playable?brief=<prompt> prefills the brief box.
  const briefSeededRef = React.useRef(false);
  React.useEffect(() => {
    const b = (params.brief || '').toString().trim();
    if (b && !briefSeededRef.current) {
      briefSeededRef.current = true;
      setBrief(b);
    }
  }, [params.brief]);

  React.useEffect(() => {
    if (params.remix && game?.playable_id) {
      const t = setTimeout(() => { try { tweakRef.current?.focus(); } catch {} }, 600);
      return () => clearTimeout(t);
    }
  }, [params.remix, game?.playable_id]);

  // 🌍 "Make this a game" one-flow: arriving from Worldforge with ?autopolish=1 auto-runs
  // the polish chain (Living NPCs → Physics → FX) once the generated game has loaded.
  React.useEffect(() => {
    if (params.autopolish === '1' && game?.playable_id && !busy && !autopolishedRef.current) {
      autopolishedRef.current = true;
      runPolish();
    }
  }, [params.autopolish, game?.playable_id, busy, runPolish]);

  const winH = Dimensions.get('window').height;
  const playH = Math.max(360, Math.round(winH * 0.62));

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity testID="pl-back" onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backTxt}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Playable Export</Text>
        <View style={styles.backBtn} />
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView style={styles.scroll} contentContainerStyle={{ paddingBottom: 48 }} keyboardShouldPersistTaps="handled">
          <Text style={styles.subtitle}>🕹️ Brief → real, self-contained game you play right here.</Text>

          <View style={styles.toolbar}>
            <TouchableOpacity testID="pl-import-toggle" style={styles.toolBtn} onPress={() => { haptics.selection(); loadImportBuilds(); setShowImport((s) => !s); }}>
              <Text style={styles.toolBtnTxt}>📦 Import from Vault</Text>
            </TouchableOpacity>
            <TouchableOpacity testID="pl-board-toggle" style={[styles.toolBtn, styles.toolBtnGold]} onPress={() => { haptics.selection(); loadBoard(); setShowBoard((s) => !s); }}>
              <Text style={styles.toolBtnTxt}>🏆 Top Games</Text>
            </TouchableOpacity>
          </View>

          {showImport ? (
            <View testID="pl-import-panel" style={styles.panel}>
              <Text style={styles.panelTitle}>Import a game built with the Galaxy questionnaire</Text>
              {importBuilds.length === 0 ? (
                <Text style={styles.panelEmpty}>No vault builds found yet. Design one in Galaxy Studio first.</Text>
              ) : importBuilds.slice(0, 30).map((b) => (
                <TouchableOpacity key={b.build_id} testID={`pl-build-${b.build_id}`} style={styles.buildRow} disabled={busy} onPress={() => runImport(b.build_id)}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.buildTitle} numberOfLines={1}>{b.title || 'Untitled'}</Text>
                    <Text style={styles.buildSub}>{b.genre || 'game'}{b.subgenre ? ` · ${b.subgenre}` : ''} · {b.status}</Text>
                  </View>
                  <Text style={styles.buildImport}>Import →</Text>
                </TouchableOpacity>
              ))}
            </View>
          ) : null}

          {showBoard ? (
            <View testID="pl-board-panel" style={[styles.panel, styles.panelGold]}>
              <Text style={styles.panelTitle}>🏆 Top Games — ranked by votes, judge score & intricacy</Text>
              <TouchableOpacity testID="pl-board-assets-filter" onPress={() => setBoardAssetsOnly(v => !v)}
                style={[styles.assetsFilterChip, boardAssetsOnly && styles.assetsFilterChipOn]} activeOpacity={0.85}>
                <Text style={[styles.assetsFilterTxt, boardAssetsOnly && styles.assetsFilterTxtOn]}>🎨 Assets complete</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="pl-open-top" style={styles.openTopBtn} onPress={() => { haptics.selection(); router.push('/top'); }}>
                <Text style={styles.openTopTxt}>🌐 Open full public board (/top) ↗</Text>
              </TouchableOpacity>
              {board.length === 0 ? (
                <Text style={styles.panelEmpty}>No ranked games yet.</Text>
              ) : board.map((g) => (
                <TouchableOpacity key={g.playable_id} testID={`pl-board-${g.playable_id}`} style={styles.boardRow} onPress={() => { setShowBoard(false); openRecent(g.playable_id); }}>
                  <Text style={[styles.boardRank, g.rank <= 3 && styles.boardRankTop]}>#{g.rank}</Text>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.boardTitle} numberOfLines={1}>{g.title}{g.imported ? ' 📦' : ''}{g.asset_status === 'complete' ? ' 🎨' : ''}{g.derive_mode ? ` · ${g.derive_mode}` : ''}</Text>
                    <Text style={styles.boardSub}>{g.genre} · ⭐{g.overall ?? '–'} · 🧬{g.intricacy ?? '–'} · ⚔️{g.wins}/{g.matches}</Text>
                  </View>
                  <Text style={styles.boardScore}>{g.score}</Text>
                </TouchableOpacity>
              ))}
            </View>
          ) : null}

          <Text style={styles.label}>Game brief</Text>
          <TextInput
            testID="pl-brief"
            style={styles.input}
            value={brief}
            onChangeText={setBrief}
            placeholder="Describe the game you want to play…"
            placeholderTextColor="#475569"
            multiline
          />
          <Text style={styles.label}>Quality mode</Text>
          <View style={styles.depthRow}>
            <TouchableOpacity testID="pl-depth-fast" style={[styles.depthBtn, depth === 'fast' && styles.depthBtnActive]} disabled={busy} onPress={() => setDepth('fast')}>
              <Text style={[styles.depthTxt, depth === 'fast' && styles.depthTxtActive]}>⚡ Fast</Text>
              <Text style={styles.depthSub}>~1 min · quick</Text>
            </TouchableOpacity>
            <TouchableOpacity testID="pl-depth-studio" style={[styles.depthBtn, depth === 'studio' && styles.depthBtnActive]} disabled={busy} onPress={() => setDepth('studio')}>
              <Text style={[styles.depthTxt, depth === 'studio' && styles.depthTxtActive]}>💎 Studio</Text>
              <Text style={styles.depthSub}>~3-5 min · max intricacy</Text>
            </TouchableOpacity>
          </View>
          <View style={styles.autoCoverRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.autoCoverLabel}>🎨 Auto-cover new games</Text>
              <Text style={styles.autoCoverSub}>Generate AI art when a build finishes (~1 credit each)</Text>
            </View>
            <Switch
              testID="pl-autocover"
              value={autoCover}
              onValueChange={toggleAutoCover}
              trackColor={{ false: '#404040', true: '#7e22ce' }}
              thumbColor={Platform.OS === 'android' ? (autoCover ? '#c084fc' : '#94a3b8') : undefined}
            />
          </View>
          <TouchableOpacity testID="pl-generate" style={[styles.cta, busy && { opacity: 0.5 }]} onPress={generate} disabled={busy}>
            {busy ? (
              <View style={styles.busyRow}><ActivityIndicator color="#fff" /><Text style={styles.ctaTxt}>  {busyLabel}</Text></View>
            ) : <Text style={styles.ctaTxt}>🎮 Generate & Play →</Text>}
          </TouchableOpacity>
          {busy ? <Text style={styles.hint}>{depth === 'fast' ? 'Fast mode: one focused, runnable game, gate-checked (~1 min).' : 'Studio mode: a richly intricate game, auto-repaired, judge-scored, then quality-refined (~3-5 min).'}</Text> : null}
          {error ? <Text testID="pl-error" style={styles.err}>{error}</Text> : null}

          {busy && !game ? <GeneratingPreview label={busyLabel} /> : null}

          {game ? (
            <View testID="pl-result">
              {!coverHidden ? (
                <Image
                  key={`cover-${coverBust}`}
                  testID="pl-cover"
                  source={{ uri: `${BACKEND}/api/playable/${game.playable_id}/cover.png?v=${coverBust}` }}
                  style={styles.coverBanner}
                  resizeMode="cover"
                  onError={() => setCoverHidden(true)}
                />
              ) : null}

              {/* 🎨 Cover-art controls: mint / regenerate / pick from 3 options */}
              <View style={styles.coverBar}>
                <TouchableOpacity testID="pl-cover-make" style={styles.coverBtn} disabled={coverBusy} onPress={coverHidden ? makeCover : regenCover}>
                  <Text style={styles.coverBtnTxt}>{coverBusy ? '🎨 …' : coverHidden ? '🎨 Cover art' : '🔁 Regenerate'}</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="pl-cover-options" style={styles.coverBtn} disabled={coverOptsBusy} onPress={genCoverOptions}>
                  <Text style={styles.coverBtnTxt}>{coverOptsBusy ? '🖼️ Making 3…' : '🖼️ 3 options'}</Text>
                </TouchableOpacity>
              </View>
              {coverOpts && coverOpts.length ? (
                <View testID="pl-cover-opts">
                  <Text style={styles.coverOptsHint}>Pick your favourite cover:</Text>
                  <View style={styles.coverOptsRow}>
                    {coverOpts.map((idx) => (
                      <TouchableOpacity key={idx} testID={`pl-cover-opt-${idx}`} style={styles.coverOptWrap} onPress={() => selectCoverOption(idx)}>
                        <Image
                          source={{ uri: `${BACKEND}/api/playable/${game.playable_id}/cover/opt/${idx}.png` }}
                          style={styles.coverOptImg}
                          resizeMode="cover"
                        />
                        <Text style={styles.coverOptPick}>Use this</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                </View>
              ) : null}

              <View style={styles.metaRow}>
                <Text style={styles.gameTitle} numberOfLines={1}>{game.title}</Text>
                <Text style={styles.scoreBadge}>▶ {game.playability_score}/100</Text>
              </View>
              {game.evaluation && game.evaluation.available && (game.evaluation.difficulty || game.evaluation.length) ? (
                <View testID="pl-tags" style={styles.tagRow}>
                  {game.evaluation.difficulty ? (
                    <View style={[styles.tagChip, styles.tagDiff]}><Text style={styles.tagTxt}>🎯 {game.evaluation.difficulty}</Text></View>
                  ) : null}
                  {game.evaluation.length ? (
                    <View style={[styles.tagChip, styles.tagLen]}><Text style={styles.tagTxt}>⏱️ {game.evaluation.length}</Text></View>
                  ) : null}
                </View>
              ) : null}

              <View testID="pl-reactions" style={styles.reactionBar}>
                {REACTIONS.map((e) => {
                  const n = (game.reactions || {})[e] || 0;
                  return (
                    <TouchableOpacity key={e} testID={`pl-react-${e}`} style={styles.reactBtn} onPress={() => sendReaction(e)}>
                      <Text style={styles.reactEmoji}>{e}</Text>
                      {n > 0 ? <Text style={styles.reactCount}>{n}</Text> : null}
                    </TouchableOpacity>
                  );
                })}
              </View>
              <Text style={styles.metaSub}>
                {game.genre} · {game.model || 'ai'} · {(game.bytes / 1024).toFixed(1)} KB
                {typeof game.intricacy === 'number' ? ` · 🧬 intricacy ${game.intricacy}/7` : ''}
                {(() => { const n = (game.repair_trail || []).filter((t: any) => t.kind === 'quality_repair').length; return n ? ` · ✨ quality-refined ×${n}` : ''; })()}
                {game.repair_trail && (game.repair_trail).some((t: any) => t.kind === 'structural_repair') ? ' · 🔧 repaired' : ''}
                {game.parent_id ? ' · 🎚️ derived' : ''}
              </Text>

              {pipeline && (
                <View testID="pl-pipeline" style={styles.pipeBox}>
                  <View style={styles.pipeHead}>
                    <Text style={styles.pipeTitle}>🧭 Studio Pipeline</Text>
                    <Text style={styles.pipePct}>{pipeline.done}/{pipeline.total} · {pipeline.percent}%</Text>
                  </View>
                  <View style={styles.pipeBarTrack}>
                    <View style={[styles.pipeBarFill, { width: `${pipeline.percent}%` }]} />
                  </View>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 8 }}>
                    {(pipeline.stages || []).map((st: any) => {
                      const canForge = st.forge && st.status !== 'done';
                      return (
                      <TouchableOpacity key={st.key} testID={`pl-stage-${st.key}`}
                        onPress={() => {
                          if (forging) return;
                          if (canForge) forgeStage(st);
                          else if (st.route) router.push(`${st.route}` as any);
                        }}
                        style={[styles.pipeStage,
                          st.status === 'done' ? styles.pipeDone : st.status === 'partial' ? styles.pipePartial : styles.pipeTodo]}
                        activeOpacity={0.85}>
                        {forging === st.key ? <ActivityIndicator size="small" color="#60A5FA" /> : (
                          <Text style={styles.pipeStageIcon}>{st.status === 'done' ? '✅' : st.status === 'partial' ? '🟡' : st.icon}</Text>
                        )}
                        <Text style={styles.pipeStageLabel} numberOfLines={1}>{st.label}</Text>
                        <Text style={styles.pipeStageDetail} numberOfLines={1}>{canForge ? '⚒ tap to forge' : st.detail}</Text>
                      </TouchableOpacity>
                    ); })}
                  </ScrollView>
                  {pipeline.next && (
                    <Text style={styles.pipeNext}>Next up → <Text style={styles.pipeNextBold}>{pipeline.next_label}</Text></Text>
                  )}
                  <View style={{ flexDirection: 'row', gap: 8 }}>
                    <TouchableOpacity testID="pl-kb-btn" onPress={() => router.push(`/game-kb?game=${game.playable_id}` as any)}
                      style={[styles.kbBtn, { flex: 1 }]} activeOpacity={0.85}>
                      <Text style={styles.kbBtnTxt}>🗄️ Knowledge Base</Text>
                    </TouchableOpacity>
                    <TouchableOpacity testID="pl-mode-btn" onPress={() => router.push(`/create-mode?parent=${game.playable_id}` as any)}
                      style={[styles.kbBtn, styles.modeBtn, { flex: 1 }]} activeOpacity={0.85}>
                      <Text style={[styles.kbBtnTxt, styles.modeBtnTxt]}>🎬 Create from this</Text>
                    </TouchableOpacity>
                  </View>
                  <TouchableOpacity testID="pl-snowball-btn" onPress={() => router.push(`/snowball?game=${game.playable_id}` as any)}
                    style={[styles.kbBtn, styles.snowballBtn]} activeOpacity={0.85}>
                    <Text style={[styles.kbBtnTxt, styles.snowballBtnTxt]}>☃️ Snowball Build (manual, stage-by-stage)</Text>
                  </TouchableOpacity>
                  <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                    <TouchableOpacity testID="pl-graph-btn" onPress={() => router.push(`/canon-graph?game=${game.playable_id}` as any)}
                      style={[styles.kbBtn, { flex: 1, marginTop: 0, backgroundColor: '#10231f', borderColor: '#1E40AF' }]} activeOpacity={0.85}>
                      <Text style={[styles.kbBtnTxt, { color: '#34d399' }]}>🕸️ Canon Graph</Text>
                    </TouchableOpacity>
                    <TouchableOpacity testID="pl-groupchat-btn" onPress={() => router.push(`/groupchat?game=${game.playable_id}` as any)}
                      style={[styles.kbBtn, { flex: 1, marginTop: 0, backgroundColor: '#1a1636', borderColor: '#4338ca' }]} activeOpacity={0.85}>
                      <Text style={[styles.kbBtnTxt, { color: '#a5b4fc' }]}>🤖 Auto-Build</Text>
                    </TouchableOpacity>
                  </View>
                </View>
              )}

              {assetPack && (
                <View testID="pl-asset-pack" style={styles.assetPackBox}>
                  <View style={styles.assetPackHead}>
                    <Text style={styles.assetPackTitle}>🎨 Asset Pack</Text>
                    <View style={[styles.apTag,
                      assetPack.asset_status === 'complete' ? styles.apTagDone : assetPack.asset_status === 'partial' ? styles.apTagPartial : styles.apTagNone]}>
                      <Text style={styles.apTagTxt}>{assetPack.tag}</Text>
                    </View>
                  </View>
                  {(assetPack.assets || []).length > 0 ? (
                    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 4 }}>
                      {(assetPack.assets || []).map((a: any) => (
                        <Image key={a.asset_id} testID={`pl-ap-${a.asset_id}`}
                          source={{ uri: `${BACKEND}/api/assets/genesis/${a.asset_id}.png` }}
                          style={styles.apThumb} resizeMode="cover" />
                      ))}
                    </ScrollView>
                  ) : (
                    <Text style={styles.apEmpty}>No generated art yet for this game.</Text>
                  )}
                  <TouchableOpacity testID="pl-skin-btn"
                    onPress={() => router.push(`/asset-genesis?game=${game.playable_id}` as any)}
                    style={styles.apBtn} activeOpacity={0.85}>
                    <Text style={styles.apBtnTxt}>{assetPack.applied ? '🎨 Manage / re-skin in Asset Genesis' : '⚡ Skin this game with AI art'}</Text>
                  </TouchableOpacity>
                </View>
              )}

              {lineage && (lineage.ancestors.length > 0 || lineage.children.length > 0) ? (
                <View testID="pl-lineage" style={styles.lineageBox}>
                  <View style={styles.lineageHead}>
                    <Text style={styles.lineageTitle}>🌳 Remix lineage</Text>
                    <Text style={styles.lineageCount}>
                      {lineage.ancestors.length} parent{lineage.ancestors.length === 1 ? '' : 's'} · {lineage.children.length} remix{lineage.children.length === 1 ? '' : 'es'}
                    </Text>
                  </View>
                  {(game.remix_count || lineage.ancestors.length) ? (
                    <Text testID="pl-attribution" style={styles.attribution}>
                      {game.remix_count ? `🔱 Remixed ${game.remix_count} time${game.remix_count === 1 ? '' : 's'}` : ''}
                      {game.remix_count && lineage.ancestors.length ? ' · ' : ''}
                      {lineage.ancestors.length ? `🌱 Original: ${lineage.ancestors[0].title}` : ''}
                    </Text>
                  ) : null}
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.lineageRow}>
                    {lineage.ancestors.map((a) => (
                      <React.Fragment key={a.playable_id}>
                        <TouchableOpacity testID={`pl-anc-${a.playable_id}`} style={styles.lineChip} onPress={() => openRecent(a.playable_id)}>
                          <MiniCover id={a.playable_id} hasCover={(a as any).has_cover} size={22} />
                          <Text style={styles.lineChipTxt} numberOfLines={1}>{a.derive_mode ? `${a.derive_mode} ·` : '🌱'} {a.title}</Text>
                        </TouchableOpacity>
                        <Text style={styles.lineArrow}>→</Text>
                      </React.Fragment>
                    ))}
                    <View style={styles.lineHere}><Text style={styles.lineHereTxt} numberOfLines={1}>● this game</Text></View>
                    {lineage.children.map((c) => (
                      <React.Fragment key={c.playable_id}>
                        <Text style={styles.lineArrow}>→</Text>
                        <TouchableOpacity testID={`pl-child-${c.playable_id}`} style={[styles.lineChip, styles.lineChildChip]} onPress={() => openRecent(c.playable_id)}>
                          <MiniCover id={c.playable_id} hasCover={(c as any).has_cover} size={22} />
                          <Text style={styles.lineChipTxt} numberOfLines={1}>{c.derive_mode ? `${c.derive_mode} ·` : '🔱'} {c.title}</Text>
                        </TouchableOpacity>
                      </React.Fragment>
                    ))}
                  </ScrollView>
                </View>
              ) : null}

              {game.evaluation && game.evaluation.available ? (
                <View testID="pl-eval" style={styles.evalBox}>
                  <View style={styles.evalHead}>
                    <Text style={styles.evalTitle}>🧪 Judge ({game.evaluation.judge_model}) · {game.evaluation.overall}/100</Text>
                    <Text style={[styles.verdict, game.evaluation.verdict === 'ship' ? styles.vShip : game.evaluation.verdict === 'reject' ? styles.vReject : styles.vPolish]}>
                      {(game.evaluation.verdict || '').toUpperCase()}
                    </Text>
                  </View>
                  <Text style={styles.evalAxes}>
                    Playability {game.evaluation.playability} · Coherence {game.evaluation.coherence} · Fun {game.evaluation.fun} · Polish {game.evaluation.polish}
                  </Text>
                  {game.evaluation.critique ? <Text style={styles.evalCrit}>{game.evaluation.critique}</Text> : null}
                  {game.evaluation.top_fix ? <Text style={styles.evalFix}>💡 {game.evaluation.top_fix}</Text> : null}
                </View>
              ) : null}

              <View style={[styles.gameWrap, { height: playH }]}>
                <GamePreview
                  key={webKey}
                  testID="pl-webview"
                  uri={`${BACKEND}${game.raw_path}`}
                  onGameError={(msg) => setGameError(msg)}
                />
              </View>
              {gameError ? (
                <View testID="pl-repair-banner" style={styles.repairBanner}>
                  <Text style={styles.repairTitle}>⚠️ This game hit a runtime error</Text>
                  <Text style={styles.repairMsg} numberOfLines={2}>{gameError}</Text>
                  <View style={styles.repairRow}>
                    <TouchableOpacity testID="pl-repair-btn" style={[styles.repairBtn, repairing && { opacity: 0.5 }]} disabled={repairing} onPress={autoRepair}>
                      <Text style={styles.repairBtnTxt}>{repairing ? '🔧 Repairing…' : '🔧 Auto-repair'}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity testID="pl-repair-dismiss" style={styles.repairDismiss} onPress={() => setGameError(null)}>
                      <Text style={styles.repairDismissTxt}>Dismiss</Text>
                    </TouchableOpacity>
                  </View>
                  {repairMsg ? <Text style={styles.repairResult}>{repairMsg}</Text> : null}
                </View>
              ) : null}
              {(modStatus === 'hidden' || modStatus === 'warned' || modStatus === 'review') ? (
                <View testID="pl-modnotice" style={styles.modNotice}>
                  <Text style={styles.modNoticeTxt}>
                    {modStatus === 'hidden'
                      ? '🔒 This game is under review and is temporarily hidden from public discovery.'
                      : modStatus === 'warned'
                      ? '⚠️ This game has been flagged and is under moderator review.'
                      : '⏳ This game is queued for moderator review.'}
                  </Text>
                </View>
              ) : null}
              {(game as any).forged_from ? (
                <View testID="pl-forged" style={styles.forgedBadge}>
                  <Text style={styles.forgedTxt}>🌍 Forged from {(game as any).forged_from}</Text>
                </View>
              ) : null}
              {busy ? (
                <View testID="pl-busy" style={styles.busyBanner}>
                  {polish ? (
                    <View style={styles.polishSteps}>
                      {POLISH_STEPS.map((s) => {
                        const st = polish.step > s.n ? 'done' : polish.step === s.n ? 'run' : 'wait';
                        return (
                          <View key={s.n} style={styles.polishStep}>
                            <Text style={styles.polishStepIcon}>{st === 'done' ? '✓' : st === 'run' ? '⟳' : '◦'}</Text>
                            <Text style={[styles.polishStepTxt, st === 'wait' && { opacity: 0.45 }]}>{s.icon} {s.label}</Text>
                          </View>
                        );
                      })}
                    </View>
                  ) : (
                    <View style={styles.busyRow}>
                      <ActivityIndicator color="#fff" />
                      <Text style={styles.busyBannerTxt}>  {busyLabel}</Text>
                    </View>
                  )}
                </View>
              ) : null}
              <View style={styles.actionRow}>
                <TouchableOpacity testID="pl-reload" style={styles.smallBtn} onPress={() => { haptics.selection(); setWebKey((k) => k + 1); }}>
                  <Text style={styles.smallBtnTxt}>↻ Restart</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="pl-sentience-btn" style={[styles.smallBtn, styles.smallBtnSentience, busy && { opacity: 0.5 }]} disabled={busy} onPress={() => runEnhance('sentience')}>
                  <Text style={styles.smallBtnTxt}>👾 Living NPCs</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="pl-aesthetics-btn" style={[styles.smallBtn, styles.smallBtnAesthetics, busy && { opacity: 0.5 }]} disabled={busy} onPress={() => runEnhance('aesthetics')}>
                  <Text style={styles.smallBtnTxt}>🎨 FX + Audio</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="pl-physics-btn" style={[styles.smallBtn, styles.smallBtnPhysics, busy && { opacity: 0.5 }]} disabled={busy} onPress={() => runEnhance('physics')}>
                  <Text style={styles.smallBtnTxt}>🧲 Physics</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="pl-factions-btn" style={[styles.smallBtn, styles.smallBtnFactions, busy && { opacity: 0.5 }]} disabled={busy} onPress={pickWorldThenFactions}>
                  <Text style={styles.smallBtnTxt}>🏛️ World Events</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="pl-polish-btn" style={[styles.smallBtn, styles.smallBtnPolish, busy && { opacity: 0.5 }]} disabled={busy} onPress={runPolish}>
                  <Text style={styles.smallBtnTxt}>✨ One-Tap Polish</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="pl-share" style={[styles.smallBtn, styles.smallBtnShare]} onPress={shareGame}>
                  <Text style={styles.smallBtnTxt}>{copied ? '✓ Copied' : '🔗 Share'}</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="pl-regen" style={[styles.smallBtn, styles.smallBtnAlt]} onPress={generate}>
                  <Text style={styles.smallBtnTxt}>✨ New game</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="pl-cover-btn" style={[styles.smallBtn, styles.smallBtnCover, coverBusy && { opacity: 0.5 }]} disabled={coverBusy} onPress={makeCover}>
                  <Text style={styles.smallBtnTxt}>{coverBusy ? '🎨 …' : '🎨 Cover'}</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="pl-card-btn" style={[styles.smallBtn, styles.smallBtnCard]} onPress={shareCard}>
                  <Text style={styles.smallBtnTxt}>🖼️ Card</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="pl-collect-btn" style={[styles.smallBtn, styles.smallBtnCollect]} onPress={openCollModal}>
                  <Text style={styles.smallBtnTxt}>📚 Save</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="pl-sell-btn" style={[styles.smallBtn, styles.smallBtnSell]} onPress={() => { haptics.selection(); router.push(`/marketplace?sell=${game.playable_id}` as any); }}>
                  <Text style={styles.smallBtnTxt}>🛒 Sell</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="pl-tournament-btn" style={[styles.smallBtn, styles.smallBtnTrn]} onPress={() => { haptics.selection(); router.push('/tournaments' as any); }}>
                  <Text style={styles.smallBtnTxt}>🏆 Compete</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="pl-report-btn" style={[styles.smallBtn, styles.smallBtnReport]} onPress={() => { haptics.selection(); setReportMsg(''); setReportModal(true); }}>
                  <Text style={styles.smallBtnTxt}>🚩 Report</Text>
                </TouchableOpacity>
                {(modStatus === 'hidden' || modStatus === 'warned' || modStatus === 'review') ? (
                  <TouchableOpacity testID="pl-appeal-btn" style={[styles.smallBtn, styles.smallBtnAppeal]} onPress={() => { haptics.selection(); setAppealReason(''); setAppealMsg(''); setAppealModal(true); }}>
                    <Text style={styles.smallBtnTxt}>⚖️ Appeal</Text>
                  </TouchableOpacity>
                ) : null}
              </View>

              {/* ── vs Play: head-to-head against the parent (derived games only) ── */}
              {game.parent_id ? (
                <View style={styles.vsBox}>
                  <TouchableOpacity testID="pl-vs-toggle" style={styles.vsToggle} onPress={() => { haptics.selection(); setShowCompare((s) => !s); setVote(null); }}>
                    <Text style={styles.vsToggleTxt}>{showCompare ? '▾ Hide vs Original' : '⚔️ vs Original — compare & vote'}</Text>
                  </TouchableOpacity>
                  {showCompare ? (
                    <View testID="pl-compare">
                      <View style={styles.vsCol}>
                        <Text style={styles.vsLabel}>🔵 This {game.derive_mode ? `(${game.derive_mode})` : ''}{vote ? ` · ${vote.this} wins` : ''}</Text>
                        <View style={styles.vsPreview}>
                          <GamePreview key={`vs-this-${webKey}`} uri={`${BACKEND}${game.raw_path}`} />
                        </View>
                        <TouchableOpacity testID="pl-vote-this" style={[styles.voteBtn, styles.voteThis]} onPress={() => castVote('this')}>
                          <Text style={styles.smallBtnTxt}>▲ Vote this</Text>
                        </TouchableOpacity>
                      </View>
                      <View style={styles.vsCol}>
                        <Text style={styles.vsLabel}>🟣 Original{vote ? ` · ${vote.opp} wins` : ''}</Text>
                        <View style={styles.vsPreview}>
                          <GamePreview key={`vs-parent-${webKey}`} uri={`${BACKEND}/api/playable/${game.parent_id}/raw`} />
                        </View>
                        <TouchableOpacity testID="pl-vote-parent" style={[styles.voteBtn, styles.voteParent]} onPress={() => castVote('parent')}>
                          <Text style={styles.smallBtnTxt}>▲ Vote original</Text>
                        </TouchableOpacity>
                      </View>
                      {vote ? <Text style={styles.voteResult}>{vote.this === vote.opp ? "It's a tie!" : vote.this > vote.opp ? '🔵 This is winning!' : '🟣 Original is winning!'}</Text> : null}
                    </View>
                  ) : null}
                </View>
              ) : null}

              {/* ── Evolve this game: remix / sequel / competitor ── */}
              <View style={styles.remixBox}>
                <Text style={styles.remixTitle}>🎚️ Evolve this game</Text>
                <View style={styles.chipRow}>
                  {TWEAK_CHIPS.map((c) => (
                    <TouchableOpacity key={c} testID={`pl-chip-${c}`} style={styles.chip} disabled={busy} onPress={() => runRemix(c)}>
                      <Text style={styles.chipTxt}>{c}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
                <TextInput
                  testID="pl-tweak"
                  ref={tweakRef}
                  style={styles.tweakInput}
                  value={tweak}
                  onChangeText={setTweak}
                  placeholder="…or describe your own change / direction"
                  placeholderTextColor="#475569"
                />
                <TouchableOpacity testID="pl-remix" style={[styles.remixBtn, (busy || tweak.trim().length < 3) && { opacity: 0.5 }]} disabled={busy || tweak.trim().length < 3} onPress={() => runDerive('remix', tweak)}>
                  <Text style={styles.smallBtnTxt}>🎚️ Remix →</Text>
                </TouchableOpacity>
                <View style={styles.deriveRow}>
                  <TouchableOpacity testID="pl-sequel" style={[styles.deriveBtn, styles.sequelBtn, busy && { opacity: 0.5 }]} disabled={busy} onPress={() => runDerive('sequel', tweak)}>
                    <Text style={styles.smallBtnTxt}>📈 Sequel</Text>
                  </TouchableOpacity>
                  <TouchableOpacity testID="pl-prequel" style={[styles.deriveBtn, styles.prequelBtn, busy && { opacity: 0.5 }]} disabled={busy} onPress={() => runDerive('prequel', tweak)}>
                    <Text style={styles.smallBtnTxt}>🌅 Prequel</Text>
                  </TouchableOpacity>
                </View>
                <View style={styles.deriveRow}>
                  <TouchableOpacity testID="pl-competitor" style={[styles.deriveBtn, styles.competitorBtn, busy && { opacity: 0.5 }]} disabled={busy} onPress={() => runDerive('competitor', tweak)}>
                    <Text style={styles.smallBtnTxt}>🥊 Competitor</Text>
                  </TouchableOpacity>
                  <TouchableOpacity testID="pl-expansion" style={[styles.deriveBtn, styles.expansionBtn, busy && { opacity: 0.5 }]} disabled={busy} onPress={() => runDerive('expansion', tweak)}>
                    <Text style={styles.smallBtnTxt}>🚀 Expansion 2.5×</Text>
                  </TouchableOpacity>
                </View>
                <View style={styles.deriveRow}>
                  <TouchableOpacity testID="pl-interlude" style={[styles.deriveBtn, styles.interludeBtn, busy && { opacity: 0.5 }]} disabled={busy} onPress={() => runDerive('interlude', tweak)}>
                    <Text style={styles.smallBtnTxt}>📖 Interlude</Text>
                  </TouchableOpacity>
                  <TouchableOpacity testID="pl-conclusion" style={[styles.deriveBtn, styles.conclusionBtn, busy && { opacity: 0.5 }]} disabled={busy} onPress={() => runDerive('conclusion', tweak)}>
                    <Text style={styles.smallBtnTxt}>🏁 Conclusion</Text>
                  </TouchableOpacity>
                </View>
                <TouchableOpacity testID="pl-series" style={[styles.seriesBtn, busy && { opacity: 0.5 }]} disabled={busy} onPress={runSeries}>
                  <Text style={styles.smallBtnTxt}>❄️ Build a Snowball Series (3 escalating games)</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="pl-variants" style={[styles.variantsBtn, busy && { opacity: 0.5 }]} disabled={busy} onPress={runVariants}>
                  <Text style={styles.smallBtnTxt}>🎨 Generate 4 Colour Variants</Text>
                  <View style={styles.variantDots}>
                    {['#ef4444', '#3b82f6', '#22c55e', '#eab308'].map((c) => (
                      <View key={c} style={[styles.variantDot, { backgroundColor: c }]} />
                    ))}
                  </View>
                </TouchableOpacity>
                <Text style={styles.deriveHint}>Sequel/Prequel = chapters · Competitor = rival (PvP, 2×) · Expansion = deluxe 2.5× · Interlude = lore + new mechanics · Conclusion = finale with 3+ endings · Series = snowball of escalating games · Variants = 4 colour remakes. The box above is optional direction.</Text>

                {variants ? (
                  <View testID="pl-variants-result" style={styles.variantsResult}>
                    <Text style={styles.variantsTitle}>🎨 4 Variants — tap to play</Text>
                    <View style={styles.variantsGrid}>
                      {variants.map((v) => (
                        <TouchableOpacity
                          key={v.color}
                          testID={`pl-variant-${v.color}`}
                          style={[styles.variantCard, { borderColor: v.hex }]}
                          disabled={v.status !== 'ready' || !v.playable_id}
                          onPress={() => v.playable_id && openRecent(v.playable_id)}
                        >
                          {v.has_cover && v.playable_id ? (
                            <View style={[styles.variantCoverWrap, { borderColor: v.hex }]}>
                              <MiniCover id={v.playable_id} hasCover size={50} />
                            </View>
                          ) : (
                            <View style={[styles.variantSwatch, { backgroundColor: v.hex }]} />
                          )}
                          <Text style={styles.variantName}>{(v.color || '').toUpperCase()}</Text>
                          <Text style={styles.variantMeta}>
                            {v.status === 'ready' ? `▶ ${v.playability_score ?? '–'} · ${((v.bytes || 0) / 1024).toFixed(0)}KB` : 'failed'}
                          </Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>
                ) : null}

                {series ? (
                  <View testID="pl-series-result" style={styles.variantsResult}>
                    <Text style={styles.variantsTitle}>❄️ Snowball Series — each builds on the last</Text>
                    {series.map((s) => (
                      <TouchableOpacity
                        key={s.playable_id || s.step}
                        testID={`pl-series-${s.step}`}
                        style={styles.seriesRow}
                        disabled={s.status !== 'ready' || !s.playable_id}
                        onPress={() => s.playable_id && openRecent(s.playable_id)}
                      >
                        <View style={styles.seriesStep}><Text style={styles.seriesStepTxt}>{s.step}</Text></View>
                        {s.has_cover && s.playable_id
                          ? <MiniCover id={s.playable_id} hasCover size={40} />
                          : <View style={styles.seriesGlyph}><Text style={{ fontSize: 18 }}>{s.status === 'ready' ? '❄️' : '⚠️'}</Text></View>}
                        <View style={{ flex: 1, marginLeft: 10, minWidth: 0 }}>
                          <Text style={styles.recentTitle} numberOfLines={1}>{s.title || `Entry ${s.step}`}</Text>
                          <Text style={styles.recentSub}>
                            {s.status === 'ready' ? `▶ ${s.playability_score ?? '–'}/100 · ${((s.bytes || 0) / 1024).toFixed(0)}KB` : 'failed — chain stopped'}
                          </Text>
                        </View>
                      </TouchableOpacity>
                    ))}
                  </View>
                ) : null}

                {/* ── 🛠️ Fix & fine-tune — precise IN-PLACE edits to THIS game ── */}
                <View testID="pl-edit-box" style={styles.editBox}>
                  <Text style={styles.remixTitle}>🛠️ Fix & fine-tune (edits this game in place)</Text>
                  <TextInput
                    testID="pl-fix-input"
                    style={styles.tweakInput}
                    value={fix}
                    onChangeText={setFix}
                    placeholder="e.g. make the player jump higher · or: the score doesn't reset on restart"
                    placeholderTextColor="#475569"
                    multiline
                  />
                  <View style={styles.deriveRow}>
                    <TouchableOpacity testID="pl-finetune" style={[styles.deriveBtn, styles.finetuneBtn, (busy || fix.trim().length < 3) && { opacity: 0.5 }]} disabled={busy || fix.trim().length < 3} onPress={() => runEdit('finetune', fix)}>
                      <Text style={styles.smallBtnTxt}>✏️ Finetune</Text>
                    </TouchableOpacity>
                    <TouchableOpacity testID="pl-bugsquash" style={[styles.deriveBtn, styles.bugsquashBtn, (busy || fix.trim().length < 3) && { opacity: 0.5 }]} disabled={busy || fix.trim().length < 3} onPress={() => runEdit('bugsquash', fix)}>
                      <Text style={styles.smallBtnTxt}>🐛 Bugsquash</Text>
                    </TouchableOpacity>
                  </View>
                  <Text style={styles.deriveHint}>Finetune = apply exactly your change, nothing else · Bugsquash = describe a bug and fix it at the root. Both edit THIS game in place (the original derive/remix buttons above spawn a new game).</Text>
                </View>
              </View>
            </View>
          ) : null}

          {recent.length > 0 ? (
            <View style={styles.recentBox}>
              <Text style={styles.sectionTitle}>Recent builds</Text>
              {recent.map((p) => (
                <TouchableOpacity key={p.playable_id} testID={`pl-recent-${p.playable_id}`} style={styles.recentRow} onPress={() => openRecent(p.playable_id)}>
                  <MiniCover id={p.playable_id} hasCover={p.has_cover} size={38} />
                  <View style={{ flex: 1, marginLeft: 10 }}>
                    <Text style={styles.recentTitle} numberOfLines={1}>{p.title}</Text>
                    <Text style={styles.recentSub}>{p.genre} · {p.status}</Text>
                  </View>
                  <Text style={[styles.recentScore, p.status !== 'ready' && { color: '#f87171' }]}>{p.playability_score}</Text>
                </TouchableOpacity>
              ))}
            </View>
          ) : null}
        </ScrollView>
      </KeyboardAvoidingView>

      {/* 📚 Save-to-Collection modal */}
      <Modal visible={collModal} transparent animationType="fade" onRequestClose={() => setCollModal(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard} testID="pl-coll-modal">
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>📚 Save to collection</Text>
              <TouchableOpacity testID="pl-coll-close" hitSlop={theme.hitSlop.md} onPress={() => setCollModal(false)}>
                <Text style={styles.modalClose}>✕</Text>
              </TouchableOpacity>
            </View>
            {collMsg ? <Text style={styles.collMsg}>{collMsg}</Text> : null}
            <View style={styles.collCreateRow}>
              <TextInput
                testID="pl-coll-new"
                style={styles.collInput}
                placeholder="New collection…"
                placeholderTextColor="#64748b"
                value={newColl}
                onChangeText={setNewColl}
                onSubmitEditing={createAndAdd}
                returnKeyType="done"
                maxLength={80}
              />
              <TouchableOpacity testID="pl-coll-create" style={[styles.collCreateBtn, (!newColl.trim() || collBusy) && { opacity: 0.4 }]} disabled={!newColl.trim() || collBusy} onPress={createAndAdd}>
                <Text style={styles.collCreateTxt}>{collBusy ? '…' : '+ New'}</Text>
              </TouchableOpacity>
            </View>
            <ScrollView style={styles.collScroll}>
              {collList.length === 0 ? (
                <Text style={styles.collEmpty}>No collections yet — create one above.</Text>
              ) : collList.map((c) => (
                <TouchableOpacity key={c.collection_id} testID={`pl-coll-${c.collection_id}`} style={styles.collRow} onPress={() => addToColl(c.collection_id, c.name)}>
                  <Text style={styles.collName} numberOfLines={1}>📁 {c.name}</Text>
                  <Text style={styles.collCount}>{c.count} · add ＋</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* ── 🚩 Report modal ── */}
      <Modal visible={reportModal} transparent animationType="fade" onRequestClose={() => setReportModal(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard} testID="pl-report-modal">
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>🚩 Report this game</Text>
              <TouchableOpacity testID="pl-report-close" hitSlop={theme.hitSlop.md} onPress={() => setReportModal(false)}>
                <Text style={styles.modalClose}>✕</Text>
              </TouchableOpacity>
            </View>
            {reportMsg ? <Text style={styles.collMsg}>{reportMsg}</Text> : (
              <Text style={styles.reportHint}>Why are you reporting it? Our moderators review every report.</Text>
            )}
            {!reportMsg ? (
              <View style={styles.reportReasons}>
                {([
                  ['inappropriate', '🔞 Inappropriate'],
                  ['offensive', '😡 Offensive'],
                  ['copyright', '©️ Copyright / stolen'],
                  ['broken', '🐞 Broken / not playable'],
                  ['spam', '🗑️ Spam'],
                  ['other', '❓ Other'],
                ] as [string, string][]).map(([reason, label]) => (
                  <TouchableOpacity
                    key={reason}
                    testID={`pl-report-${reason}`}
                    disabled={reportBusy}
                    style={[styles.reportChip, reportBusy && { opacity: 0.5 }]}
                    onPress={() => submitReport(reason)}
                  >
                    <Text style={styles.reportChipTxt}>{label}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            ) : null}
          </View>
        </View>
      </Modal>

      {/* ── ⚖️ Appeal modal (creator) ── */}
      <Modal visible={appealModal} transparent animationType="fade" onRequestClose={() => setAppealModal(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard} testID="pl-appeal-modal">
            <View style={styles.modalHead}>
              <Text style={styles.modalTitle}>⚖️ Appeal moderation</Text>
              <TouchableOpacity testID="pl-appeal-close" hitSlop={theme.hitSlop.md} onPress={() => setAppealModal(false)}>
                <Text style={styles.modalClose}>✕</Text>
              </TouchableOpacity>
            </View>
            {appealMsg ? <Text style={styles.collMsg}>{appealMsg}</Text> : (
              <>
                <Text style={styles.reportHint}>This game is currently restricted. Tell our moderators why it should be reinstated.</Text>
                <TextInput
                  testID="pl-appeal-input"
                  style={styles.appealInput}
                  placeholder="Explain your appeal (min 10 characters)…"
                  placeholderTextColor="#6b7280"
                  value={appealReason}
                  onChangeText={setAppealReason}
                  multiline
                  maxLength={1000}
                />
                <TouchableOpacity testID="pl-appeal-submit" disabled={appealBusy} style={[styles.appealSubmit, appealBusy && { opacity: 0.5 }]} onPress={submitAppeal}>
                  <Text style={styles.appealSubmitTxt}>{appealBusy ? 'Submitting…' : 'Submit appeal'}</Text>
                </TouchableOpacity>
              </>
            )}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#0A0A0A' },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingTop: Platform.OS === 'ios' ? 8 : 16, paddingBottom: 12,
    borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#1F1F1F',
  },
  backBtn: { paddingVertical: 6, paddingHorizontal: 10, width: 64 },
  backTxt: { color: '#93c5fd', fontSize: 16 },
  title: { color: '#fff', fontSize: 16, fontWeight: '700' },
  scroll: { flex: 1, paddingHorizontal: 14 },
  subtitle: { color: '#94a3b8', fontSize: 13, marginTop: 12 },
  label: { color: '#cbd5e1', fontSize: 13, fontWeight: '700', marginTop: 14, marginBottom: 8 },
  input: {
    backgroundColor: '#0A0A0A', borderRadius: 10, color: '#e2e8f0', padding: 12,
    minHeight: 80, fontSize: 14, textAlignVertical: 'top', borderWidth: 1, borderColor: '#1F1F1F',
  },
  cta: { backgroundColor: '#10b981', borderRadius: 10, paddingVertical: 13, alignItems: 'center', marginTop: 14 },
  busyRow: { flexDirection: 'row', alignItems: 'center' },
  busyBanner: { backgroundColor: '#1b1430', borderRadius: 12, borderWidth: 1, borderColor: '#7c3aed', padding: 12, marginTop: 12 },
  busyBannerTxt: { color: '#e2e8f0', fontWeight: '700', fontSize: 14 },
  polishSteps: { gap: 8 },
  polishStep: { flexDirection: 'row', alignItems: 'center' },
  polishStepIcon: { color: '#a78bfa', fontWeight: '800', fontSize: 16, width: 22 },
  polishStepTxt: { color: '#e2e8f0', fontSize: 14, fontWeight: '600' },
  ctaTxt: { color: '#fff', fontWeight: '800', fontSize: 14 },
  hint: { color: '#64748b', fontSize: 12, marginTop: 8, textAlign: 'center' },
  err: { color: '#fca5a5', fontSize: 13, marginTop: 12, lineHeight: 19 },
  metaRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 20 },
  gameTitle: { color: '#fff', fontSize: 16, fontWeight: '800', flex: 1, marginRight: 10 },
  scoreBadge: { color: '#fbbf24', fontSize: 13, fontWeight: '900', backgroundColor: 'rgba(251,191,36,0.12)', borderWidth: 1, borderColor: 'rgba(251,191,36,0.45)', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4, overflow: 'hidden' },
  metaSub: { color: '#64748b', fontSize: 12, marginTop: 3, marginBottom: 10 },
  gameWrap: { borderRadius: 14, overflow: 'hidden', borderWidth: 1.5, borderColor: '#2E1B5B', backgroundColor: '#000' },
  web: { flex: 1, backgroundColor: '#000' },
  actionRow: { flexDirection: 'row', gap: 10, marginTop: 12, flexWrap: 'wrap' },
  modNotice: { backgroundColor: 'rgba(245,200,66,0.12)', borderWidth: 1, borderColor: 'rgba(245,200,66,0.45)', borderRadius: 12, padding: 12, marginTop: 12 },
  modNoticeTxt: { color: '#fde68a', fontSize: 13, lineHeight: 18, fontWeight: '600' },
  smallBtn: { flexGrow: 1, flexBasis: '30%', minWidth: 96, backgroundColor: '#1F1F1F', borderRadius: 10, paddingVertical: 11, paddingHorizontal: 6, alignItems: 'center' },
  smallBtnAlt: { backgroundColor: '#2E1B5B' },
  smallBtnShare: { backgroundColor: '#0f766e' },
  smallBtnCover: { backgroundColor: '#7e22ce' },
  smallBtnCard: { backgroundColor: '#1d4ed8' },
  smallBtnCollect: { backgroundColor: '#7e22ce' },
  smallBtnSell: { backgroundColor: '#16a34a' },
  smallBtnTrn: { backgroundColor: '#ca8a04' },
  smallBtnReport: { backgroundColor: '#7f1d1d' },
  smallBtnSentience: { backgroundColor: '#4338ca' },
  smallBtnAesthetics: { backgroundColor: '#be185d' },
  smallBtnPhysics: { backgroundColor: '#0f766e' },
  smallBtnFactions: { backgroundColor: '#b45309' },
  smallBtnPolish: { backgroundColor: '#7c3aed' },
  forgedBadge: { alignSelf: 'flex-start', backgroundColor: '#10241c', borderColor: '#16A34A', borderWidth: 1, borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6, marginTop: 12 },
  forgedTxt: { color: '#4ade80', fontWeight: '700', fontSize: 12 },
  smallBtnAppeal: { backgroundColor: '#1e3a5f' },
  appealInput: { backgroundColor: '#1f1f1f', borderRadius: 12, borderWidth: 1, borderColor: '#404040', color: '#e5e5e5', fontSize: 14, padding: 12, minHeight: 90, textAlignVertical: 'top', marginBottom: 12 },
  appealSubmit: { backgroundColor: '#2563eb', borderRadius: 12, paddingVertical: 13, alignItems: 'center', minHeight: 48, justifyContent: 'center' },
  appealSubmitTxt: { color: '#fff', fontSize: 15, fontWeight: '800' },
  reportHint: { color: '#94a3b8', fontSize: 13, lineHeight: 19, marginBottom: 12 },
  reportReasons: { gap: 8 },
  reportChip: { backgroundColor: '#1f1f1f', borderRadius: 12, borderWidth: 1, borderColor: '#404040', paddingVertical: 13, paddingHorizontal: 14, minHeight: 44, justifyContent: 'center' },
  reportChipTxt: { color: '#e5e5e5', fontSize: 14, fontWeight: '700' },
  attribution: { color: '#cbd5e1', fontSize: 11.5, fontWeight: '600', marginTop: 4, marginBottom: 2 },
  modalBackdrop: { flex: 1, backgroundColor: 'rgba(2,6,18,0.72)', justifyContent: 'center', paddingHorizontal: 20 },
  modalCard: { backgroundColor: '#0f1629', borderRadius: 18, borderWidth: 1, borderColor: '#2E1B5B', padding: 16, maxHeight: '70%' },
  modalHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
  modalTitle: { color: '#fff', fontSize: 16, fontWeight: '800' },
  modalClose: { color: '#94a3b8', fontSize: 18, fontWeight: '800' },
  collMsg: { color: '#4ade80', fontSize: 12.5, fontWeight: '700', marginBottom: 8 },
  collCreateRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  collInput: { flex: 1, backgroundColor: '#0b1020', borderRadius: 10, borderWidth: 1, borderColor: '#2E1B5B', color: '#fff', paddingHorizontal: 12, paddingVertical: 9, fontSize: 14 },
  collCreateBtn: { paddingHorizontal: 14, justifyContent: 'center', borderRadius: 10, backgroundColor: '#7e22ce' },
  collCreateTxt: { color: '#fff', fontWeight: '800', fontSize: 13 },
  collScroll: { maxHeight: 280 },
  collEmpty: { color: '#94a3b8', fontSize: 13, textAlign: 'center', paddingVertical: 20 },
  collRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 12, paddingHorizontal: 12, borderRadius: 10, backgroundColor: '#161b2e', marginBottom: 6 },
  collName: { color: '#e2e8f0', fontSize: 14, fontWeight: '700', flex: 1, marginRight: 8 },
  collCount: { color: '#c084fc', fontSize: 12, fontWeight: '700' },

  autoCoverRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#141414', borderRadius: 12, borderWidth: 1, borderColor: '#2E1B5B', paddingHorizontal: 14, paddingVertical: 10, marginTop: 12 },
  autoCoverLabel: { color: '#e2e8f0', fontSize: 13, fontWeight: '700' },
  autoCoverSub: { color: '#64748b', fontSize: 11, marginTop: 2 },
  coverBanner: { width: '100%', height: 150, borderRadius: 14, marginTop: 16, marginBottom: 4, borderWidth: 1, borderColor: '#2E1B5B', backgroundColor: '#141414' },
  coverBar: { flexDirection: 'row', gap: 8, marginTop: 8 },
  coverBtn: { flex: 1, paddingVertical: 9, borderRadius: 10, alignItems: 'center', borderWidth: 1, borderColor: '#7e22ce', backgroundColor: 'rgba(126,34,206,0.15)' },
  coverBtnTxt: { color: '#e9d5ff', fontSize: 13, fontWeight: '700' },
  coverOptsHint: { color: '#94a3b8', fontSize: 12, fontWeight: '600', marginTop: 10, marginBottom: 6 },
  coverOptsRow: { flexDirection: 'row', gap: 8 },
  coverOptWrap: { flex: 1, alignItems: 'center' },
  coverOptImg: { width: '100%', height: 90, borderRadius: 10, borderWidth: 1, borderColor: '#2E1B5B', backgroundColor: '#141414' },
  coverOptPick: { color: '#c084fc', fontSize: 11, fontWeight: '700', marginTop: 4 },
  tagRow: { flexDirection: 'row', gap: 8, marginTop: 6, marginBottom: 2 },
  tagChip: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, borderWidth: 1 },
  tagDiff: { borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.12)' },
  tagLen: { borderColor: '#60A5FA', backgroundColor: 'rgba(56,189,248,0.12)' },
  tagTxt: { color: '#e2e8f0', fontSize: 12, fontWeight: '700' },
  reactionBar: { flexDirection: 'row', gap: 8, marginTop: 10, flexWrap: 'wrap' },
  reactBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 999, borderWidth: 1, borderColor: '#404040', backgroundColor: '#161b2e' },
  reactEmoji: { fontSize: 17 },
  reactCount: { color: '#cbd5e1', fontSize: 13, fontWeight: '800' },
  repairBanner: { marginTop: 10, padding: 14, borderRadius: 14, borderWidth: 1.5, borderColor: '#f59e0b', backgroundColor: 'rgba(245,158,11,0.10)' },
  repairTitle: { color: '#fbbf24', fontSize: 14, fontWeight: '800' },
  repairMsg: { color: '#cbd5e1', fontSize: 12, marginTop: 3, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
  repairRow: { flexDirection: 'row', gap: 10, marginTop: 10, alignItems: 'center' },
  repairBtn: { paddingHorizontal: 16, paddingVertical: 9, borderRadius: 10, backgroundColor: '#d97706' },
  repairBtnTxt: { color: '#fff', fontWeight: '800', fontSize: 13 },
  repairDismiss: { paddingHorizontal: 12, paddingVertical: 9 },
  repairDismissTxt: { color: '#94a3b8', fontWeight: '700', fontSize: 13 },
  repairResult: { color: '#86efac', fontSize: 12.5, fontWeight: '700', marginTop: 8 },

  smallBtnTxt: { color: '#e2e8f0', fontWeight: '700', fontSize: 13 },
  recentBox: { marginTop: 26 },
  sectionTitle: { color: '#cbd5e1', fontSize: 13, fontWeight: '700', marginBottom: 8 },
  recentRow: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: '#0A0A0A',
    borderRadius: 10, padding: 12, marginBottom: 8, borderWidth: 1, borderColor: '#1F1F1F',
  },
  recentTitle: { color: '#e2e8f0', fontSize: 14, fontWeight: '600' },
  recentSub: { color: '#64748b', fontSize: 12, marginTop: 2 },
  recentScore: { color: '#10B981', fontSize: 15, fontWeight: '800', marginLeft: 10 },
  // depth toggle
  depthRow: { flexDirection: 'row', gap: 10, marginBottom: 4 },
  depthBtn: { flex: 1, backgroundColor: '#0A0A0A', borderRadius: 10, paddingVertical: 10, paddingHorizontal: 8, borderWidth: 1.5, borderColor: '#1F1F1F', alignItems: 'center' },
  depthBtnActive: { borderColor: '#10b981', backgroundColor: '#0c1f17' },
  depthTxt: { color: '#94a3b8', fontSize: 14, fontWeight: '800' },
  depthTxtActive: { color: '#10B981' },
  depthSub: { color: '#64748b', fontSize: 11, marginTop: 2 },
  // vs play
  vsBox: { marginTop: 12 },
  vsToggle: { backgroundColor: '#1F1F1F', borderRadius: 10, paddingVertical: 12, minHeight: 46, alignItems: 'center', justifyContent: 'center' },
  vsToggleTxt: { color: '#fbbf24', fontSize: 14, fontWeight: '800' },
  vsCol: { marginTop: 12 },
  vsLabel: { color: '#cbd5e1', fontSize: 13, fontWeight: '700', marginBottom: 6 },
  vsPreview: { height: 300, borderRadius: 12, overflow: 'hidden', borderWidth: 1, borderColor: '#1F1F1F', backgroundColor: '#000' },
  voteBtn: { borderRadius: 10, paddingVertical: 12, minHeight: 46, alignItems: 'center', justifyContent: 'center', marginTop: 8 },
  voteThis: { backgroundColor: '#1d4ed8' },
  voteParent: { backgroundColor: '#8B5CF6' },
  voteResult: { color: '#fbbf24', fontSize: 14, fontWeight: '800', textAlign: 'center', marginTop: 12 },
  // toolbar + panels (import / leaderboard)
  toolbar: { flexDirection: 'row', gap: 10, marginTop: 14 },
  toolBtn: { flex: 1, backgroundColor: '#16213a', borderRadius: 12, paddingVertical: 13, minHeight: 46, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#1e3a5f' },
  toolBtnGold: { backgroundColor: '#2a2410', borderColor: '#854d0e' },
  toolBtnTxt: { color: '#e2e8f0', fontWeight: '800', fontSize: 13 },
  panel: { marginTop: 12, backgroundColor: '#0d1526', borderRadius: 14, padding: 12, borderWidth: 1, borderColor: '#1e3a5f' },
  panelGold: { backgroundColor: '#1a160a', borderColor: '#854d0e' },
  panelTitle: { color: '#cbd5e1', fontSize: 12, fontWeight: '800', marginBottom: 10 },
  openTopBtn: { backgroundColor: '#3a2e10', borderRadius: 8, paddingVertical: 9, alignItems: 'center', marginBottom: 10, borderWidth: 1, borderColor: '#854d0e' },
  openTopTxt: { color: '#fde68a', fontSize: 12, fontWeight: '800' },
  panelEmpty: { color: '#64748b', fontSize: 13, paddingVertical: 6 },
  buildRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#121d33', borderRadius: 10, padding: 11, marginBottom: 8, borderWidth: 1, borderColor: '#1e3a5f' },
  buildTitle: { color: '#e2e8f0', fontSize: 14, fontWeight: '700' },
  buildSub: { color: '#64748b', fontSize: 12, marginTop: 2 },
  buildImport: { color: '#60A5FA', fontSize: 13, fontWeight: '800', marginLeft: 10 },
  boardRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#1c1708', borderRadius: 10, padding: 11, marginBottom: 8, borderWidth: 1, borderColor: '#3a2e10' },
  boardRank: { color: '#94a3b8', fontSize: 15, fontWeight: '900', width: 38 },
  boardRankTop: { color: '#fbbf24' },
  boardTitle: { color: '#fde68a', fontSize: 14, fontWeight: '700' },
  boardSub: { color: '#a8a29e', fontSize: 11, marginTop: 2 },
  boardScore: { color: '#fbbf24', fontSize: 15, fontWeight: '900', marginLeft: 8 },
  // lineage
  lineageBox: { backgroundColor: '#0c1410', borderRadius: 10, padding: 12, borderWidth: 1, borderColor: '#14532d', marginBottom: 12, marginTop: 4 },
  assetPackBox: { backgroundColor: '#150f24', borderRadius: 10, padding: 12, borderWidth: 1, borderColor: '#3B2A66', marginBottom: 12, marginTop: 4 },
  assetPackHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  assetPackTitle: { color: '#E2E8F0', fontSize: 14, fontWeight: '800' },
  apTag: { paddingHorizontal: 9, paddingVertical: 4, borderRadius: 11, borderWidth: 1 },
  apTagDone: { backgroundColor: '#10B98122', borderColor: '#10B981' },
  apTagPartial: { backgroundColor: '#F59E0B22', borderColor: '#F59E0B' },
  apTagNone: { backgroundColor: '#33415522', borderColor: '#475569' },
  apTagTxt: { color: '#E2E8F0', fontSize: 10, fontWeight: '800' },
  apThumb: { width: 60, height: 60, borderRadius: 8, backgroundColor: '#0E1626' },
  apEmpty: { color: '#64748B', fontSize: 12, paddingVertical: 8 },
  apBtn: { marginTop: 10, borderRadius: 10, paddingVertical: 11, alignItems: 'center', backgroundColor: '#7C3AED' },
  apBtnTxt: { color: '#fff', fontSize: 13, fontWeight: '800' },
  pipeBox: { backgroundColor: '#0d1424', borderRadius: 10, padding: 12, borderWidth: 1, borderColor: '#1e3a5f', marginBottom: 12, marginTop: 4 },
  pipeHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  pipeTitle: { color: '#E2E8F0', fontSize: 14, fontWeight: '800' },
  pipePct: { color: '#60A5FA', fontSize: 12, fontWeight: '800' },
  pipeBarTrack: { height: 6, borderRadius: 3, backgroundColor: '#1e293b', marginTop: 8, overflow: 'hidden' },
  pipeBarFill: { height: 6, borderRadius: 3, backgroundColor: '#60A5FA' },
  pipeStage: { width: 96, padding: 8, borderRadius: 9, borderWidth: 1, alignItems: 'center' },
  pipeDone: { backgroundColor: '#10B98114', borderColor: '#10B981' },
  pipePartial: { backgroundColor: '#F59E0B14', borderColor: '#F59E0B' },
  pipeTodo: { backgroundColor: '#0E1626', borderColor: '#334155' },
  pipeStageIcon: { fontSize: 18 },
  pipeStageLabel: { color: '#CBD5E1', fontSize: 11, fontWeight: '700', marginTop: 3, textAlign: 'center' },
  pipeStageDetail: { color: '#64748B', fontSize: 9, marginTop: 2, textAlign: 'center' },
  pipeNext: { color: '#94A3B8', fontSize: 12, marginTop: 6 },
  pipeNextBold: { color: '#60A5FA', fontWeight: '800' },
  kbBtn: { marginTop: 10, borderRadius: 9, paddingVertical: 10, alignItems: 'center', backgroundColor: '#0e2436', borderWidth: 1, borderColor: '#1e3a5f' },
  kbBtnTxt: { color: '#93C5FD', fontSize: 13, fontWeight: '800' },
  modeBtn: { backgroundColor: '#1a1636', borderColor: '#4338ca' },
  modeBtnTxt: { color: '#a5b4fc' },
  snowballBtn: { marginTop: 8, backgroundColor: '#0a1f30', borderColor: '#1E40AF' },
  snowballBtnTxt: { color: '#93C5FD' },
  assetsFilterChip: { alignSelf: 'flex-start', marginTop: 8, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 16, borderWidth: 1, borderColor: '#334155', backgroundColor: '#0f172a' },
  assetsFilterChipOn: { borderColor: '#7C3AED', backgroundColor: '#7C3AED22' },
  assetsFilterTxt: { color: '#94A3B8', fontSize: 12, fontWeight: '700' },
  assetsFilterTxtOn: { color: '#C4B5FD' },
  lineageHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
  lineageTitle: { color: '#86efac', fontSize: 12, fontWeight: '800' },
  lineageCount: { color: '#5b8c6f', fontSize: 11, fontWeight: '700' },
  lineageRow: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingRight: 8 },
  lineChip: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: '#14241a', borderRadius: 8, paddingHorizontal: 8, paddingVertical: 6, borderWidth: 1, borderColor: '#1f3d2c', maxWidth: 170 },
  lineChildChip: { backgroundColor: '#1a1430', borderColor: '#3b2a6b' },
  lineChipTxt: { color: '#cbd5e1', fontSize: 12, fontWeight: '600' },
  lineArrow: { color: '#475569', fontSize: 15, fontWeight: '800' },
  lineHere: { backgroundColor: '#fbbf24', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 7, borderWidth: 1, borderColor: '#fde68a' },
  lineHereTxt: { color: '#3a2e10', fontSize: 12, fontWeight: '900' },
  // eval harness
  evalBox: { backgroundColor: '#0f1b2a', borderRadius: 10, padding: 12, borderWidth: 1, borderColor: '#1e3a5f', marginBottom: 12 },
  evalHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  evalTitle: { color: '#93c5fd', fontSize: 13, fontWeight: '800', flex: 1, marginRight: 8 },
  verdict: { fontSize: 11, fontWeight: '900', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, overflow: 'hidden' },
  vShip: { color: '#052e16', backgroundColor: '#4ade80' },
  vPolish: { color: '#422006', backgroundColor: '#fbbf24' },
  vReject: { color: '#450a0a', backgroundColor: '#f87171' },
  evalAxes: { color: '#cbd5e1', fontSize: 12, marginTop: 8 },
  evalCrit: { color: '#94a3b8', fontSize: 12, marginTop: 8, lineHeight: 17, fontStyle: 'italic' },
  evalFix: { color: '#86efac', fontSize: 12, marginTop: 6, lineHeight: 17 },
  // remix
  remixBox: { marginTop: 16, backgroundColor: '#160f24', borderRadius: 12, padding: 12, borderWidth: 1, borderColor: '#2e1065' },
  remixTitle: { color: '#c4b5fd', fontSize: 13, fontWeight: '800', marginBottom: 10 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 10 },
  chip: { backgroundColor: '#241844', borderRadius: 16, paddingHorizontal: 12, paddingVertical: 7, borderWidth: 1, borderColor: '#3b2a6b' },
  chipTxt: { color: '#ddd6fe', fontSize: 12, fontWeight: '600' },
  tweakInput: { backgroundColor: '#0e0a18', borderRadius: 10, color: '#e2e8f0', padding: 11, fontSize: 14, borderWidth: 1, borderColor: '#2e1065' },
  remixBtn: { backgroundColor: '#8B5CF6', borderRadius: 10, paddingVertical: 14, minHeight: 46, justifyContent: 'center', alignItems: 'center', marginTop: 10 },
  deriveRow: { flexDirection: 'row', gap: 10, marginTop: 10 },
  deriveBtn: { flex: 1, borderRadius: 10, paddingVertical: 13, minHeight: 46, justifyContent: 'center', alignItems: 'center' },
  sequelBtn: { backgroundColor: '#0369a1' },
  competitorBtn: { backgroundColor: '#b91c1c' },
  prequelBtn: { backgroundColor: '#b45309' },
  expansionBtn: { backgroundColor: '#7e22ce' },
  variantsBtn: { backgroundColor: '#141414', borderRadius: 10, paddingVertical: 13, minHeight: 46, justifyContent: 'center', alignItems: 'center', marginTop: 10, borderWidth: 1, borderColor: '#404040', flexDirection: 'row', gap: 10 },
  interludeBtn: { backgroundColor: '#1E40AF' },
  conclusionBtn: { backgroundColor: '#9f1239' },
  editBox: { marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#2e1065' },
  finetuneBtn: { backgroundColor: '#15803d' },
  bugsquashBtn: { backgroundColor: '#a16207' },
  seriesBtn: { backgroundColor: '#1e3a5f', borderRadius: 10, paddingVertical: 13, minHeight: 46, justifyContent: 'center', alignItems: 'center', marginTop: 10, borderWidth: 1, borderColor: '#3b82f6' },
  seriesRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#0d1626', borderRadius: 10, padding: 10, marginTop: 8, borderWidth: 1, borderColor: '#1e3a5f' },
  seriesStep: { width: 24, height: 24, borderRadius: 12, backgroundColor: '#3b82f6', alignItems: 'center', justifyContent: 'center', marginRight: 8 },
  seriesStepTxt: { color: '#fff', fontSize: 13, fontWeight: '900' },
  seriesGlyph: { width: 40, height: 40, borderRadius: 8, backgroundColor: '#16203a', alignItems: 'center', justifyContent: 'center' },
  variantDots: { flexDirection: 'row', gap: 5 },
  variantDot: { width: 12, height: 12, borderRadius: 6 },
  variantsResult: { marginTop: 14 },
  variantsTitle: { color: '#cbd5e1', fontSize: 13, fontWeight: '800', marginBottom: 10 },
  variantsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  variantCard: { width: '47%', backgroundColor: '#141414', borderRadius: 12, borderWidth: 2, padding: 12, alignItems: 'center' },
  variantSwatch: { width: 40, height: 40, borderRadius: 20, marginBottom: 8 },
  variantCoverWrap: { width: 56, height: 56, borderRadius: 12, borderWidth: 2, marginBottom: 8, overflow: 'hidden', alignItems: 'center', justifyContent: 'center' },
  variantName: { color: '#e2e8f0', fontSize: 13, fontWeight: '900', letterSpacing: 1 },
  variantMeta: { color: '#94a3b8', fontSize: 11, marginTop: 4 },
  deriveHint: { color: '#64748b', fontSize: 11, marginTop: 10, lineHeight: 16 },
});
