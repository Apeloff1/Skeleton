/**
 * BuildJourney — Galaxy Studio's single, gamified build flow.
 *
 * One coherent quest: 7 industry-standard milestones with live progress, a
 * creator RANK + XP bar, a momentum streak, milestone-gated "Continue" CTAs,
 * earned badges, a single next-best-action, and a shareable "build complete"
 * card. Everything is derived from real persisted state (GET /journey/{id}),
 * so rolling/locking/forging advances it instantly.
 */
import React from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ActivityIndicator, Share,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../utils/apiClient';

const C = {
  card: '#11101c', alt: '#1a1830', border: '#2c2a44', text: '#f1eefb',
  muted: '#9a93c0', gold: '#FBBF24', green: '#34D399', purple: '#A78BFA',
  cyan: '#3B82F6', amber: '#F59E0B', dim: '#5b557e',
};

const STATE_ICON: Record<string, string> = { done: '✅', active: '👉', locked: '🔒' };

type Milestone = {
  key: string; label: string; icon: string; tagline: string; state: string;
  progress_pct: number; xp: number; xp_earned: number; badge: string;
  badge_icon: string; badge_earned: boolean; route: string; cta: string;
  unlocked: boolean;
};
type Journey = {
  title: string; era_label: string; genre: string;
  milestones: Milestone[]; milestones_done: number; milestones_total: number;
  completion_pct: number; total_xp: number; earned_xp: number; streak: number;
  rank: { level: number; rank: string; rank_icon: string; next_rank?: string; xp_to_next: number };
  badges: { key: string; name: string; icon: string }[]; badges_total: number;
  next_best_action?: { key: string; label: string; icon: string; cta: string; route: string; tagline: string };
  complete: boolean;
  stats: { stages_built: number; stages_total: number; stage_gamefiles: number; forged_assets: number; file_count_standard: number };
  share_card: any;
};

export default function BuildJourney({
  game, refreshKey, onNavigate,
}: { game: string; refreshKey?: number; onNavigate: (route: string) => void }) {
  const [j, setJ] = React.useState<Journey | null>(null);
  const [loading, setLoading] = React.useState(true);

  const load = React.useCallback(async () => {
    if (!game) { setLoading(false); return; }
    const r = await api.get<Journey>(`/api/galaxy-studio/journey/${game}`, { timeoutMs: 15000 });
    if (r.ok && r.data && !(r.data as any).error) setJ(r.data);
    setLoading(false);
  }, [game]);

  React.useEffect(() => { load(); }, [load, refreshKey]);

  const share = React.useCallback(async () => {
    if (!j) return;
    const s = j.share_card;
    const msg = `${s.rank_icon} ${s.title} — ${s.completion_pct}% complete\n` +
      `${s.rank} · ${s.earned_xp} XP · ${s.milestones} milestones · ${s.badges.join(' ')}\n` +
      `${s.era} · ${Number(s.file_target).toLocaleString()} target files · ${s.assets} assets forged\n` +
      `Built with ${s.stamp}`;
    try { await Share.share({ message: msg }); } catch { /* user cancelled */ }
  }, [j]);

  if (loading) {
    return <View style={s.hero}><ActivityIndicator color={C.purple} /></View>;
  }
  if (!j) {
    return (
      <View style={s.hero} testID="journey-empty">
        <Text style={s.heroTitle}>🚀 Your Build Journey</Text>
        <Text style={s.heroSub}>Pick or start a build to begin the quest.</Text>
      </View>
    );
  }

  const nba = j.next_best_action;
  const xpPct = j.total_xp ? Math.min(100, (j.earned_xp / j.total_xp) * 100) : 0;

  return (
    <View testID="build-journey">
      {/* Hero — rank, completion ring, XP, streak */}
      <View style={s.hero}>
        <View style={s.heroTop}>
          <View style={s.ring}>
            <Text style={s.ringPct}>{j.completion_pct}%</Text>
            <Text style={s.ringLbl}>complete</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.heroTitle} numberOfLines={1}>{j.rank.rank_icon} {j.title}</Text>
            <Text style={s.heroSub} numberOfLines={1}>{j.era_label}{j.genre ? ` · ${j.genre}` : ''}</Text>
            <View style={s.rankRow}>
              <View style={s.rankPill}><Text style={s.rankTxt}>Lv {j.rank.level} · {j.rank.rank}</Text></View>
              {j.streak > 0 && <View style={s.streakPill}><Text style={s.streakTxt}>🔥 {j.streak} streak</Text></View>}
            </View>
          </View>
        </View>

        {/* XP bar */}
        <View style={s.xpRow}>
          <Text style={s.xpLbl}>XP {j.earned_xp}/{j.total_xp}</Text>
          {j.rank.next_rank ? <Text style={s.xpNext}>{j.rank.xp_to_next} → {j.rank.next_rank}</Text> : <Text style={s.xpNext}>Max rank</Text>}
        </View>
        <View style={s.track}><View style={[s.fill, { width: `${xpPct}%`, backgroundColor: C.gold }]} /></View>

        {/* quick stats */}
        <View style={s.statRow}>
          <Text style={s.stat}>🧱 {j.stats.stages_built}/{j.stats.stages_total} stages</Text>
          <Text style={s.stat}>📦 {j.stats.forged_assets} assets</Text>
          <Text style={s.stat}>🎯 {j.milestones_done}/{j.milestones_total} milestones</Text>
        </View>
      </View>

      {/* Next best action */}
      {nba && !j.complete && (
        <TouchableOpacity style={s.nba} testID="journey-nba" activeOpacity={0.9}
          onPress={() => onNavigate(nba.route)}>
          <Text style={s.nbaIcon}>{nba.icon}</Text>
          <View style={{ flex: 1 }}>
            <Text style={s.nbaKick}>NEXT UP</Text>
            <Text style={s.nbaLabel}>{nba.cta}</Text>
            <Text style={s.nbaTag} numberOfLines={1}>{nba.tagline}</Text>
          </View>
          <Ionicons name="arrow-forward-circle" size={30} color="#0b0b12" />
        </TouchableOpacity>
      )}

      {/* Completion / share card */}
      {j.complete && (
        <View style={s.complete} testID="journey-complete">
          <Text style={s.completeBig}>🏆 Build Complete!</Text>
          <Text style={s.completeSub}>{j.rank.rank_icon} {j.rank.rank} · {j.earned_xp} XP · {j.badges.length} badges</Text>
          <TouchableOpacity style={s.shareBtn} onPress={share} testID="journey-share">
            <Ionicons name="share-social" size={16} color="#0b0b12" />
            <Text style={s.shareTxt}>Share your build</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* Milestone rail */}
      <Text style={s.section}>🗺️ The Journey</Text>
      {j.milestones.map((m, i) => (
        <View key={m.key} style={[s.ms, m.state === 'active' && s.msActive]} testID={`journey-ms-${m.key}`}>
          <View style={s.msLeft}>
            <Text style={s.msState}>{STATE_ICON[m.state]}</Text>
            {i < j.milestones.length - 1 && <View style={s.msLine} />}
          </View>
          <View style={{ flex: 1 }}>
            <View style={s.msHead}>
              <Text style={s.msIcon}>{m.icon}</Text>
              <Text style={s.msLabel}>{m.label}</Text>
              <View style={[s.xpChip, m.state === 'done' && { borderColor: C.gold }]}>
                <Text style={[s.xpChipTxt, m.state === 'done' && { color: C.gold }]}>
                  {m.state === 'done' ? `+${m.xp}` : `${m.xp_earned}/${m.xp}`} XP
                </Text>
              </View>
            </View>
            <Text style={s.msTag} numberOfLines={2}>{m.tagline}</Text>
            <View style={s.msTrack}>
              <View style={[s.fill, {
                width: `${m.progress_pct}%`,
                backgroundColor: m.state === 'done' ? C.green : m.state === 'active' ? C.cyan : C.dim,
              }]} />
            </View>
            <View style={s.msFoot}>
              <Text style={[s.badge, m.badge_earned && { color: C.gold }]}>
                {m.badge_icon} {m.badge}{m.badge_earned ? ' ✓' : ''}
              </Text>
              {m.state === 'active' ? (
                <TouchableOpacity style={s.contBtn} onPress={() => onNavigate(m.route)} testID={`journey-continue-${m.key}`}>
                  <Text style={s.contTxt}>{m.cta} →</Text>
                </TouchableOpacity>
              ) : m.state === 'done' ? (
                <TouchableOpacity onPress={() => onNavigate(m.route)} testID={`journey-revisit-${m.key}`}>
                  <Text style={s.revisit}>Revisit</Text>
                </TouchableOpacity>
              ) : (
                <Text style={s.lockedTxt}>Unlocks after {j.milestones[i - 1]?.label || 'previous'}</Text>
              )}
            </View>
          </View>
        </View>
      ))}

      {/* Badge case */}
      <Text style={s.section}>🏅 Badge Case ({j.badges.length}/{j.badges_total})</Text>
      <View style={s.badgeCase}>
        {j.milestones.map((m) => (
          <View key={m.key} style={[s.badgeSlot, m.badge_earned && s.badgeSlotOn]}>
            <Text style={[s.badgeSlotIcon, !m.badge_earned && { opacity: 0.3 }]}>{m.badge_icon}</Text>
            <Text style={[s.badgeSlotTxt, m.badge_earned && { color: C.gold }]} numberOfLines={1}>{m.badge}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  hero: { backgroundColor: C.card, borderRadius: 16, borderWidth: 1, borderColor: C.border, padding: 16, marginBottom: 14 },
  heroTop: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  ring: { width: 76, height: 76, borderRadius: 38, borderWidth: 5, borderColor: C.purple, alignItems: 'center', justifyContent: 'center' },
  ringPct: { color: C.text, fontSize: 20, fontWeight: '900' },
  ringLbl: { color: C.muted, fontSize: 9, fontWeight: '700' },
  heroTitle: { color: C.text, fontSize: 17, fontWeight: '900' },
  heroSub: { color: C.muted, fontSize: 12, marginTop: 2 },
  rankRow: { flexDirection: 'row', gap: 7, marginTop: 7 },
  rankPill: { backgroundColor: C.alt, borderRadius: 8, paddingHorizontal: 9, paddingVertical: 4, borderWidth: 1, borderColor: C.purple },
  rankTxt: { color: C.purple, fontSize: 11, fontWeight: '800' },
  streakPill: { backgroundColor: '#2a1a10', borderRadius: 8, paddingHorizontal: 9, paddingVertical: 4, borderWidth: 1, borderColor: C.amber },
  streakTxt: { color: C.amber, fontSize: 11, fontWeight: '800' },
  xpRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 14 },
  xpLbl: { color: C.text, fontSize: 11, fontWeight: '700' },
  xpNext: { color: C.muted, fontSize: 11 },
  track: { height: 8, backgroundColor: C.alt, borderRadius: 4, marginTop: 6, overflow: 'hidden' },
  fill: { height: 8, borderRadius: 4 },
  statRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 12 },
  stat: { color: C.text, fontSize: 11, fontWeight: '600' },
  nba: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: C.cyan, borderRadius: 14, padding: 14, marginBottom: 14 },
  nbaIcon: { fontSize: 28 },
  nbaKick: { color: '#0b3540', fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  nbaLabel: { color: '#06222a', fontSize: 16, fontWeight: '900' },
  nbaTag: { color: '#0b3540', fontSize: 11, marginTop: 1 },
  complete: { backgroundColor: '#1a2418', borderRadius: 14, borderWidth: 1, borderColor: C.green, padding: 16, marginBottom: 14, alignItems: 'center' },
  completeBig: { color: C.green, fontSize: 20, fontWeight: '900' },
  completeSub: { color: C.text, fontSize: 12, marginTop: 4 },
  shareBtn: { flexDirection: 'row', alignItems: 'center', gap: 7, backgroundColor: C.green, borderRadius: 10, paddingHorizontal: 16, paddingVertical: 9, marginTop: 12 },
  shareTxt: { color: '#0b0b12', fontWeight: '800', fontSize: 13 },
  section: { color: C.text, fontSize: 14, fontWeight: '800', marginTop: 4, marginBottom: 10 },
  ms: { flexDirection: 'row', gap: 12, paddingBottom: 6 },
  msActive: { backgroundColor: C.card, borderRadius: 12, borderWidth: 1, borderColor: C.cyan, padding: 10, marginBottom: 6 },
  msLeft: { alignItems: 'center', width: 24 },
  msState: { fontSize: 18 },
  msLine: { flex: 1, width: 2, backgroundColor: C.border, marginTop: 4 },
  msHead: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  msIcon: { fontSize: 16 },
  msLabel: { color: C.text, fontSize: 14, fontWeight: '800', flex: 1 },
  xpChip: { borderWidth: 1, borderColor: C.border, borderRadius: 7, paddingHorizontal: 7, paddingVertical: 2 },
  xpChipTxt: { color: C.muted, fontSize: 10, fontWeight: '800' },
  msTag: { color: C.muted, fontSize: 11, marginTop: 3 },
  msTrack: { height: 6, backgroundColor: C.alt, borderRadius: 3, marginTop: 7, overflow: 'hidden' },
  msFoot: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 8, marginBottom: 6 },
  badge: { color: C.muted, fontSize: 11, fontWeight: '700' },
  contBtn: { backgroundColor: C.cyan, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6 },
  contTxt: { color: '#06222a', fontSize: 12, fontWeight: '800' },
  revisit: { color: C.purple, fontSize: 11, fontWeight: '700' },
  lockedTxt: { color: C.dim, fontSize: 10, fontStyle: 'italic' },
  badgeCase: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 14 },
  badgeSlot: { width: '31%', backgroundColor: C.card, borderRadius: 10, borderWidth: 1, borderColor: C.border, padding: 10, alignItems: 'center' },
  badgeSlotOn: { borderColor: C.gold, backgroundColor: '#221d10' },
  badgeSlotIcon: { fontSize: 22 },
  badgeSlotTxt: { color: C.muted, fontSize: 9, fontWeight: '700', marginTop: 4 },
});
