import React, { useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import type { CrawlSession, DragonCompanion } from '../../product/crawlerClient';
import s, { colors } from './CrawlerWorkspace.styles';

const FORMS = ['Hatchling', 'Scout', 'Scholar', 'Pathfinder', 'Archivist'];
const QUESTS: Record<DragonCompanion['quest'], { title: string; detail: string }> = {
  explore: { title: 'Explore the unknown', detail: 'Prefer promising unfamiliar material and recent improvements in useful yield.' },
  synthesize: { title: 'Complete the research mosaic', detail: 'Prioritize missing lexical topic coverage, not unsupported claims.' },
  diversify: { title: 'Discover another habitat', detail: 'Seek distinct admitted origins and research formats without counting copies as independent.' },
  conserve: { title: 'Conserve the expedition', detail: 'Preserve the finite request and byte budget; existing cost-aware ordering remains active.' },
  recover: { title: 'Recover safely', detail: 'Allow existing backoff and recovery controls to work. Failures do not earn growth.' },
  rest: { title: 'Rest in the den', detail: 'No ready or authorized expedition. Rest has no penalty, deadline, or streak loss.' },
};
const SKILLS: { key: keyof DragonCompanion['skills']; title: string; description: string }[] = [
  { key: 'discovery', title: 'Discovery', description: 'Distinct, relevant lexical content.' },
  { key: 'understanding', title: 'Topic coverage', description: 'Covered query terms and distinct-origin support; not factual understanding.' },
  { key: 'diversity', title: 'Habitat diversity', description: 'Novel origins and artifact formats.' },
  { key: 'discipline', title: 'Acquisition efficiency', description: 'Useful captures relative to settled requests.' },
  { key: 'resilience', title: 'Operational resilience', description: 'Bounded outcome estimate, not a reliability guarantee.' },
];
const STAGES = [0, 120, 300, 550, 800, 1000];
const HABITATS: Record<string, string> = {
  web: 'Web forest', document: 'Archive vault', structured: 'Data crystals',
  media: 'Media caverns', text: 'Scribe library', artifact: 'Artifact forge',
};

function Meter({ value, title, tint = colors.accent }: { value: number; title: string; tint?: string }) {
  const percent = Math.round(value * 100);
  return <View accessible accessibilityLabel={title + ': ' + percent + '%'} style={local.meter}>
    <View style={local.meterRow}><Text style={s.label}>{title}</Text><Text style={s.small}>{percent}%</Text></View>
    <View style={local.track}><View style={[local.fill, { width: (percent + '%') as `${number}%`, backgroundColor: tint }]} /></View>
  </View>;
}

export default function DragonCompanionPanel({ session }: { session: CrawlSession }) {
  const d = session.companion;
  const [details, setDetails] = useState(false);
  const [habitatsOpen, setHabitatsOpen] = useState(true);
  if (!d) return <View style={s.card}><Text style={s.heading}>Dragon companion</Text><Text style={s.small}>No validated companion projection is available from this backend.</Text></View>;
  const quest = QUESTS[d.quest];
  const next = STAGES[Math.min(d.stage + 1, STAGES.length - 1)];
  const previous = STAGES[d.stage];
  const stageProgress = (d.growth - previous) / Math.max(1, next - previous);
  const asleep = !session.consent_current || ['paused', 'cancelled', 'completed', 'budget_exhausted', 'failed', 'interrupted'].includes(session.status) || d.posture === 'resting';
  const posture = asleep ? 'resting' : d.posture;
  const mode = typeof session.limits.frontier_strategy === 'string' && session.limits.frontier_strategy.startsWith('companion');
  return <View style={s.card}>
    <Text style={s.eyebrow}>DRAGON · LIVING RESEARCH COMPANION</Text>
    <View style={local.hero}>
      <View accessible accessibilityLabel={FORMS[d.stage] + ', ' + posture} style={[local.den, asleep && local.sleepDen]}>
        <View style={[local.aura, { borderColor: d.stage >= 3 ? '#fbbf24' : '#a78bfa' }]} />
        <Text style={local.dragon}>{d.stage >= 3 ? '🐉' : '🐲'}</Text>
        <Text style={local.pose}>{posture.toUpperCase()}</Text>
      </View>
      <View style={local.heroInfo}>
        <Text style={s.heading}>{FORMS[d.stage]}</Text>
        <Text style={s.small}>Evolution {d.stage + 1}/5 · {d.style} temperament</Text>
        <Meter title="Evolution progress" value={stageProgress} />
        <Text style={s.small}>{d.growth}/1000 evidence-growth index · {d.stage === 4 ? 'final form' : 'next form at ' + next}</Text>
        <Text style={s.small}>{mode ? 'Adaptive companion expedition' : 'Observation only — other frontier strategy selected'}</Text>
      </View>
    </View>
    <Meter title="Expedition energy (remaining budget)" value={d.energy} tint={colors.green} />
    <View style={local.quest}>
      <Text style={s.label}>{asleep ? QUESTS.rest.title : quest.title}</Text>
      <Text style={s.small}>{asleep ? QUESTS.rest.detail : quest.detail}</Text>
    </View>
    {SKILLS.map(skill => <View key={skill.key}><Meter value={d.skills[skill.key]} title={skill.title} tint={skill.key === 'resilience' ? colors.green : colors.accent} />{details && <Text style={s.small}>{skill.description}</Text>}</View>)}
    <TouchableOpacity accessibilityRole="button" accessibilityState={{ expanded: habitatsOpen }} style={s.button} onPress={() => setHabitatsOpen(v => !v)}><Text style={s.buttonText}>{habitatsOpen ? 'Hide habitat collection' : 'Explore habitat collection'}</Text></TouchableOpacity>
    {habitatsOpen && <View style={local.habitats}>{Object.entries(HABITATS).map(([key, label]) =>
      <View key={key} style={[local.habitat, d.habitats[key] ? local.unlocked : null]}><Text style={s.label}>{label}</Text><Text style={s.small}>{d.habitats[key] ? d.habitats[key] + ' novel captures' : 'Not discovered'}</Text></View>)}</View>}
    <View style={s.check}><Text style={s.small}>{d.captured_sources} unique captures · {d.novel_origins} novel origins · {d.covered_terms}/{d.term_count} query terms · {d.multi_origin_terms} multi-origin terms</Text>
      <Text style={s.small}>Learning progress {Math.round(d.learning_progress * 100)}% · relevant novelty yield {Math.round(d.novelty_yield * 100)}%</Text>
      <Text style={s.small}>{d.quarantines} quarantine incidents · {d.recovery_observations} observed recoveries. No reward for incidents or repeated failures.</Text>
    </View>
    <TouchableOpacity accessibilityRole="button" accessibilityState={{ expanded: details }} style={s.button} onPress={() => setDetails(v => !v)}><Text style={s.buttonText}>{details ? 'Hide metric explanations' : 'Inspect how Dragon learns'}</Text></TouchableOpacity>
    <Text style={s.small}>This companion visualizes one bounded crawl. No hunger timers, lost streaks, hidden work, model-weight changes or expanded source permissions. The captured evidence is unreviewed.</Text>
  </View>;
}

const local = StyleSheet.create({
  hero: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', gap: 18 },
  den: { width: 132, height: 132, borderRadius: 24, borderWidth: 1, borderColor: '#64558c', backgroundColor: '#211a36', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  sleepDen: { backgroundColor: '#17223a', borderColor: '#526381' },
  aura: { position: 'absolute', width: 105, height: 105, borderRadius: 54, borderWidth: 2, opacity: .55 },
  dragon: { fontSize: 56, lineHeight: 70 },
  pose: { fontSize: 10, fontWeight: '700', color: colors.muted, letterSpacing: 1 },
  heroInfo: { flex: 1, minWidth: 160, gap: 6 },
  meter: { gap: 5, marginVertical: 3 },
  meterRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  track: { height: 8, borderRadius: 8, backgroundColor: colors.edge, overflow: 'hidden' },
  fill: { height: 8, borderRadius: 8 },
  quest: { padding: 14, borderRadius: 12, borderWidth: 1, borderColor: '#64558c', backgroundColor: '#1c1831', gap: 6 },
  habitats: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  habitat: { flexGrow: 1, flexBasis: 130, padding: 10, borderRadius: 10, borderWidth: 1, borderColor: colors.edge, gap: 4 },
  unlocked: { borderColor: '#635080', backgroundColor: '#211a36' },
});
