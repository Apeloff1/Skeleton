// Gamified live progress spine for the Snowball pipeline.
// Turns the flat action list into a vertical quest ladder with XP + levels.
import React, { useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

const T = {
  card: '#141414', border: '#1F2937', accent: '#7C9CFF', accent2: '#A78BFA',
  good: '#34D399', warn: '#FBBF24', text: '#E5E7EB', dim: '#94A3B8', muted: '#64748B',
  glow: '#A78BFA',
};

export type SpineStage = {
  key: string;
  title: string;
  desc: string;
  icon: any;
  xp: number;
  status: 'locked' | 'active' | 'done';
  busy?: boolean;
  cta: string;
  doneCta?: string;
};

const RANKS = ['Apprentice Smith', 'Journeyman', 'Artisan', 'Master Forger', 'Snowball Architect', 'Legendary Demiurge'];

export default function SnowballSpine({ stages, onRun, sceneTimeline }: { stages: SpineStage[]; onRun: (key: string) => void; sceneTimeline?: { stage: string; families: string[]; assets: number }[] }) {
  const { earnedXp, totalXp, level, rank, intoLevel, perLevel, doneCount } = useMemo(() => {
    const total = stages.reduce((a, s) => a + s.xp, 0);
    const earned = stages.filter((s) => s.status === 'done').reduce((a, s) => a + s.xp, 0);
    const PER = 250;
    const lvl = Math.floor(earned / PER) + 1;
    return {
      earnedXp: earned, totalXp: total, level: lvl,
      rank: RANKS[Math.min(lvl - 1, RANKS.length - 1)],
      intoLevel: earned % PER, perLevel: PER,
      doneCount: stages.filter((s) => s.status === 'done').length,
    };
  }, [stages]);

  const pct = Math.round((earnedXp / Math.max(1, totalXp)) * 100);

  return (
    <View style={styles.wrap} testID="snowball-spine">
      {/* Gamified header */}
      <View style={styles.hero}>
        <View style={styles.levelBadge}>
          <Text style={styles.levelNum}>{level}</Text>
          <Text style={styles.levelLbl}>LVL</Text>
        </View>
        <View style={{ flex: 1 }}>
          <Text style={styles.rank}>{rank}</Text>
          <Text style={styles.heroSub}>{doneCount}/{stages.length} stages · {earnedXp} XP earned</Text>
          <View style={styles.xpTrack}>
            <View style={[styles.xpFill, { width: `${(intoLevel / perLevel) * 100}%` }]} />
          </View>
          <Text style={styles.xpHint}>{intoLevel}/{perLevel} XP to next level · {pct}% pipeline complete</Text>
        </View>
      </View>

      {/* Vertical quest ladder */}
      {stages.map((s, i) => {
        const last = i === stages.length - 1;
        const done = s.status === 'done';
        const active = s.status === 'active';
        const dotColor = done ? T.good : active ? T.accent2 : '#2A2440';
        return (
          <View key={s.key} style={styles.row}>
            {/* spine rail */}
            <View style={styles.rail}>
              <View style={[styles.dot, { backgroundColor: dotColor, borderColor: active ? T.glow : dotColor }, active && styles.dotGlow]}>
                {done ? <Ionicons name="checkmark" size={14} color="#0A0A0A" />
                  : active ? <Text style={styles.dotNum}>{i + 1}</Text>
                    : <Ionicons name="lock-closed" size={11} color={T.muted} />}
              </View>
              {!last && <View style={[styles.line, { backgroundColor: done ? T.good : '#2A2440' }]} />}
            </View>

            {/* node card */}
            <TouchableOpacity
              activeOpacity={0.85}
              disabled={s.busy}
              onPress={() => onRun(s.key)}
              testID={`spine-${s.key}`}
              style={[styles.node,
                done && styles.nodeDone,
                active && styles.nodeActive,
                s.status === 'locked' && styles.nodeLocked]}>
              <View style={styles.nodeTop}>
                <Ionicons name={s.icon} size={17} color={done ? T.good : active ? T.accent2 : T.muted} />
                <Text style={[styles.nodeTitle, s.status === 'locked' && { color: T.muted }]} numberOfLines={1}>{s.title}</Text>
                <View style={[styles.xpChip, done && { backgroundColor: '#0B2E22', borderColor: '#0B5138' }]}>
                  <Text style={[styles.xpChipTxt, done && { color: T.good }]}>{done ? '✓ ' : '+'}{s.xp} XP</Text>
                </View>
              </View>
              <Text style={styles.nodeDesc} numberOfLines={2}>{s.desc}</Text>
              <View style={[styles.runBtn,
                done ? styles.runDone : active ? styles.runActive : styles.runLocked]}>
                {s.busy ? <ActivityIndicator size="small" color={done ? T.good : '#0A0A0A'} />
                  : <Ionicons name={done ? 'refresh' : 'play'} size={13} color={done ? T.good : active ? '#0A0A0A' : T.muted} />}
                <Text style={[styles.runTxt,
                  done ? { color: T.good } : active ? { color: '#0A0A0A' } : { color: T.muted }]}>
                  {s.busy ? 'Working…' : done ? (s.doneCta || 'Re-run') : s.cta}
                </Text>
              </View>
              {s.key === 'assets' && sceneTimeline && sceneTimeline.length > 0 && (
                <View style={styles.timeline} testID="spine-scene-timeline">
                  {sceneTimeline.map((sc, ti) => (
                    <View key={sc.stage + ti} style={styles.tlRow}>
                      <View style={styles.tlDot} />
                      <Text style={styles.tlStage} numberOfLines={1}>{sc.stage}</Text>
                      <Text style={styles.tlFam} numberOfLines={1}>{(sc.families || []).join(' · ') || '—'}</Text>
                      <Text style={styles.tlCount}>{sc.assets}</Text>
                    </View>
                  ))}
                </View>
              )}
            </TouchableOpacity>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: 16 },
  hero: { flexDirection: 'row', gap: 12, alignItems: 'center', backgroundColor: '#160F2B', borderWidth: 1, borderColor: '#3B2A6B', borderRadius: 16, padding: 14, marginBottom: 14 },
  levelBadge: { width: 56, height: 56, borderRadius: 16, backgroundColor: '#A78BFA', alignItems: 'center', justifyContent: 'center' },
  levelNum: { color: '#0A0A0A', fontSize: 22, fontWeight: '900', lineHeight: 24 },
  levelLbl: { color: '#0A0A0A', fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  rank: { color: T.text, fontSize: 16, fontWeight: '900' },
  heroSub: { color: T.dim, fontSize: 11, marginTop: 1 },
  xpTrack: { height: 9, borderRadius: 5, backgroundColor: '#0F0A1E', overflow: 'hidden', marginTop: 7 },
  xpFill: { height: 9, borderRadius: 5, backgroundColor: '#A78BFA' },
  xpHint: { color: T.muted, fontSize: 10, marginTop: 4, fontWeight: '600' },
  row: { flexDirection: 'row', gap: 12 },
  rail: { alignItems: 'center', width: 30 },
  dot: { width: 30, height: 30, borderRadius: 15, borderWidth: 2, alignItems: 'center', justifyContent: 'center' },
  dotGlow: { boxShadow: '0px 0px 8px rgba(167,139,250,0.9)', elevation: 6 },
  dotNum: { color: '#0A0A0A', fontSize: 13, fontWeight: '900' },
  line: { width: 3, flex: 1, marginVertical: 2, borderRadius: 2, minHeight: 18 },
  node: { flex: 1, backgroundColor: T.card, borderWidth: 1, borderColor: T.border, borderRadius: 14, padding: 12, marginBottom: 12 },
  nodeDone: { borderColor: '#0B5138' },
  nodeActive: { borderColor: T.accent2, backgroundColor: '#171228' },
  nodeLocked: { opacity: 0.6 },
  nodeTop: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  nodeTitle: { color: T.text, fontSize: 14, fontWeight: '800', flex: 1 },
  xpChip: { backgroundColor: '#1E1633', borderWidth: 1, borderColor: '#3B2A6B', borderRadius: 999, paddingHorizontal: 9, paddingVertical: 3 },
  xpChipTxt: { color: T.accent2, fontSize: 10, fontWeight: '900' },
  nodeDesc: { color: T.dim, fontSize: 11, marginTop: 5, lineHeight: 15 },
  runBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, borderRadius: 10, paddingVertical: 9, marginTop: 10 },
  runActive: { backgroundColor: T.accent2 },
  runDone: { backgroundColor: 'transparent', borderWidth: 1, borderColor: '#0B5138' },
  runLocked: { backgroundColor: '#0F172A' },
  runTxt: { fontSize: 12, fontWeight: '900' },
  timeline: { marginTop: 10, borderTopWidth: 1, borderTopColor: '#221B3A', paddingTop: 8, gap: 5 },
  tlRow: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  tlDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#34D399' },
  tlStage: { color: '#E5E7EB', fontSize: 10, fontWeight: '800', width: 64, textTransform: 'capitalize' },
  tlFam: { color: '#94A3B8', fontSize: 9.5, flex: 1 },
  tlCount: { color: '#A78BFA', fontSize: 10, fontWeight: '900' },
});
