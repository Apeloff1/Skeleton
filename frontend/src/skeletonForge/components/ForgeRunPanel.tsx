/**
 * Forge run panel: live status while POST /api/skeleton/run is in flight,
 * then the real stage track, verify loop, repair, playtest and the
 * resulting era + blueprint.
 *
 * The run endpoint is synchronous, so while it is in flight we show the
 * canonical stage list as "queued" with an elapsed clock rather than
 * inventing per-stage progress we cannot observe.
 */
import React from 'react';
import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { featureMeta, humanize } from '../graph';
import type { RunPhase } from '../hooks';
import { formatElapsed, formatScore, pendingStages, summarizeRun, type StageView } from '../run';
import type { RunPayload } from '../types';
import { Banner, Button, Card, Meter, SectionTitle, StatusPill } from './primitives';
import { C, TONE_COLOR, TONE_GLYPH } from './theme';

export interface ForgeRunPanelProps {
  phase: RunPhase;
  payload: RunPayload | null;
  error?: string | null;
  startedAt?: number | null;
  finishedAt?: number | null;
  /** Current clock (ms) — injected so the panel stays pure/testable. */
  now?: number;
  onCancel?: () => void;
  onRetry?: () => void;
  onViewEra?: (era: string) => void;
  testID?: string;
}

export default function ForgeRunPanel({ phase, payload, error, startedAt, finishedAt, now = Date.now(), onCancel, onRetry, onViewEra, testID }: ForgeRunPanelProps) {
  const elapsed = startedAt != null ? (finishedAt ?? now) - startedAt : 0;
  const sum = React.useMemo(() => summarizeRun(payload), [payload]);

  if (phase === 'idle') {
    return (
      <View testID={testID}>
        <SectionTitle>⚒ Forge run</SectionTitle>
        <Card>
          <Text style={st.idle}>No run yet. Finish the questionnaire and press “Forge it”. You will see each pipeline stage, the verify-and-repair loop, and the era and blueprint the forge chose.</Text>
        </Card>
      </View>
    );
  }

  const running = phase === 'running';
  const stages = running ? pendingStages() : sum.stages;
  const headTone = running ? 'idle' : phase === 'error' || !sum.succeeded ? 'bad' : 'ok';
  const headLabel = running ? `Forging… ${formatElapsed(elapsed)}` : phase === 'error' ? 'Run failed' : sum.succeeded ? `Forged in ${formatElapsed(elapsed)}` : 'Run finished with failures';

  return (
    <View testID={testID}>
      <SectionTitle hint={sum.runId ? `run ${sum.runId}` : undefined}>⚒ Forge run</SectionTitle>
      <Card>
        <View style={st.head} accessibilityLiveRegion="polite">
          <StatusPill tone={headTone} label={headLabel} testID="run-status" />
          {running ? <ActivityIndicator color={C.accent} accessibilityLabel="Forge running" /> : null}
          <View style={{ flex: 1 }} />
          {running && onCancel ? <Button label="Cancel" tone="ghost" compact onPress={onCancel} testID="run-cancel" /> : null}
          {!running && onRetry ? <Button label="Run again" tone="secondary" compact onPress={onRetry} testID="run-retry" /> : null}
        </View>
        {phase === 'error' && error ? <Banner tone="bad" testID="run-error">{error}</Banner> : null}
        <Meter
          ratio={running ? 0 : sum.completed / Math.max(1, sum.total)}
          color={headTone === 'bad' ? C.red : C.green}
          label={running ? 'Pipeline running' : `${sum.completed} of ${sum.total} stages succeeded`}
        />
        <Text style={st.meterTxt}>
          {running ? 'The server runs all stages in one request — results land together.' : `${sum.completed}/${sum.total} stages succeeded`}
        </Text>
        <StageTrack stages={stages} running={running} />
      </Card>

      {!running && payload ? (
        <>
          <Card label="Result" testID="run-result">
            <Text style={st.kicker}>RESULTING ERA</Text>
            <View style={st.eraRow}>
              <Text style={st.era} accessibilityRole="header" testID="run-era">{sum.era ? humanize(sum.era) : '—'}</Text>
              {sum.era && onViewEra ? <Button label="View era" tone="ghost" compact onPress={() => onViewEra(sum.era as string)} testID="run-view-era" /> : null}
            </View>
            <View style={st.facts}>
              <Fact k="Blueprint" v={sum.blueprintId ?? '—'} mono />
              <Fact k="Files" v={String(sum.fileCount)} />
              <Fact k="Primary DPS" v={sum.primaryDps === null ? '—' : String(sum.primaryDps)} />
              <Fact k="Simulation" v={sum.simPassed === null ? '—' : sum.simPassed ? 'passed' : 'failed'} />
              <Fact k="Ledger" v={sum.ledgerValid === null ? '—' : sum.ledgerValid ? 'valid' : 'INVALID'} />
              {sum.generation ? <Fact k="Hardware" v={humanize(sum.generation)} /> : null}
            </View>
            {sum.composedFeatures.length ? (
              <View style={st.feats} accessibilityLabel={`Composed systems: ${sum.composedFeatures.join(', ')}${sum.composedFallback ? ' (fallback)' : ''}`}>
                {sum.composedFeatures.map((f) => {
                  const m = featureMeta(f);
                  return <Text key={f} style={[st.feat, { borderColor: m.color, color: m.color }]}>{m.glyph} {m.label}</Text>;
                })}
                {sum.composedFallback ? <Text style={[st.feat, { borderColor: C.amber, color: C.amber }]}>fallback</Text> : null}
              </View>
            ) : null}
          </Card>

          <Card label="Verification" testID="run-verify">
            <View style={st.head}>
              <Text style={st.cardTitle}>Verify loop</Text>
              <StatusPill tone={sum.verify.tone} label={sum.verify.state === 'passed' ? 'Verified' : sum.verify.state === 'failed' ? 'Verification failed' : 'Not verified'} />
            </View>
            <Meter ratio={sum.verify.score ?? 0} color={TONE_COLOR[sum.verify.tone]} label={`Verification score ${formatScore(sum.verify.score)}${sum.verify.threshold !== null ? `, accept at ${formatScore(sum.verify.threshold)}` : ''}`} height={8} />
            <Text style={st.meterTxt}>
              Score {formatScore(sum.verify.score)}{sum.verify.threshold !== null ? ` · accept ≥ ${formatScore(sum.verify.threshold)}` : ''} · {sum.verify.rounds} round{sum.verify.rounds === 1 ? '' : 's'}
              {sum.verify.stoppedReason ? ` · stopped: ${sum.verify.stoppedReason}` : ''}
            </Text>
            {sum.verify.history.length > 1 ? <History history={sum.verify.history} threshold={sum.verify.threshold} /> : null}
            <View style={st.facts}>
              <Fact k="Checked" v={sum.verify.filesChecked === null ? '—' : String(sum.verify.filesChecked)} />
              <Fact k="Warned" v={sum.verify.warned === null ? '—' : String(sum.verify.warned)} />
              <Fact k="Failed" v={sum.verify.failed === null ? '—' : String(sum.verify.failed)} />
              <Fact k="Blocking" v={String(sum.verify.blocking)} />
            </View>
            {sum.verify.weakest ? <Text style={st.small}>Weakest file: <Text style={st.mono}>{sum.verify.weakest}</Text></Text> : null}
            <View style={[st.head, { marginTop: 10 }]}>
              <Text style={st.cardTitle}>Repair</Text>
              <StatusPill tone={sum.repair.tone} label={sum.repair.label} testID="run-repair" />
            </View>
            {sum.repair.detail ? <Text style={st.small}>{sum.repair.detail}</Text> : null}
            <View style={[st.head, { marginTop: 10 }]}>
              <Text style={st.cardTitle}>Playtest</Text>
              <StatusPill tone={sum.playtest.tone} label={sum.playtest.label} />
            </View>
          </Card>

          {sum.advice || sum.briefing ? (
            <Card label="Jeeves">
              <Text style={st.cardTitle}>✦ Jeeves</Text>
              {sum.advice ? <Text style={st.advice}>{sum.advice}</Text> : null}
              {sum.briefing ? <Text style={st.small}>{sum.briefing}</Text> : null}
            </Card>
          ) : null}
        </>
      ) : null}
    </View>
  );
}

function StageTrack({ stages, running }: { stages: StageView[]; running: boolean }) {
  return (
    <View style={st.track} accessibilityRole="list" accessibilityLabel="Pipeline stages">
      {stages.map((s, i) => {
        const tone = running ? 'idle' : s.tone;
        const color = TONE_COLOR[tone];
        const status = running ? 'queued' : s.status;
        return (
          <View key={s.name} style={st.stage} accessible accessibilityLabel={`Stage ${i + 1}, ${s.label}: ${status}${s.durationMs !== null && !running ? `, ${s.durationMs} milliseconds` : ''}${s.error ? `, error ${s.error}` : ''}`} testID={`stage-${s.name}`}>
            <Text style={[st.stageDot, { color, borderColor: color }]} importantForAccessibility="no">{running ? '·' : TONE_GLYPH[tone]}</Text>
            <View style={{ flex: 1 }}>
              <Text style={st.stageName}>{s.label} <Text style={st.stageId}>{s.name}</Text></Text>
              {s.error && !running ? <Text style={st.stageErr}>{s.error}</Text> : null}
            </View>
            <Text style={st.stageMs}>{running ? '' : s.durationMs !== null ? `${s.durationMs} ms` : s.status}</Text>
          </View>
        );
      })}
    </View>
  );
}

function History({ history, threshold }: { history: number[]; threshold: number | null }) {
  return (
    <View style={st.hist} accessibilityLabel={`Score by round: ${history.map((h) => formatScore(h)).join(', ')}`}>
      {history.map((h, i) => {
        const ok = threshold === null || h >= threshold;
        return (
          <View key={i} style={st.histCol}>
            <View style={[st.histBar, { height: Math.max(4, Math.round(h * 40)), backgroundColor: ok ? C.green : C.amber }]} />
            <Text style={st.histTxt}>R{i + 1}</Text>
          </View>
        );
      })}
    </View>
  );
}

function Fact({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <View style={st.fact} accessible accessibilityLabel={`${k}: ${v}`}>
      <Text style={st.factK}>{k}</Text>
      <Text style={[st.factV, mono && st.mono]} numberOfLines={1}>{v}</Text>
    </View>
  );
}

const st = StyleSheet.create({
  idle: { color: C.mute, fontSize: 13, lineHeight: 19 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 8 },
  meterTxt: { color: C.mute, fontSize: 12, marginTop: 6, marginBottom: 6 },
  track: { marginTop: 4 },
  stage: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: C.border },
  stageDot: { width: 22, height: 22, borderRadius: 11, borderWidth: 1, textAlign: 'center', lineHeight: 20, fontSize: 12, fontWeight: '800' },
  stageName: { color: C.text, fontSize: 13, fontWeight: '600' },
  stageId: { color: C.dim, fontSize: 11, fontWeight: '400' },
  stageErr: { color: C.red, fontSize: 11, marginTop: 2 },
  stageMs: { color: C.dim, fontSize: 11 },
  kicker: { color: C.mute, fontSize: 11, fontWeight: '800', letterSpacing: 1 },
  eraRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8, flexWrap: 'wrap' },
  era: { color: C.textStrong, fontSize: 24, fontWeight: '900' },
  facts: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 6 },
  fact: { backgroundColor: C.cardAlt, borderRadius: 8, borderWidth: 1, borderColor: C.border, paddingHorizontal: 10, paddingVertical: 6, minWidth: 92, flexGrow: 1 },
  factK: { color: C.dim, fontSize: 10, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.6 },
  factV: { color: C.textStrong, fontSize: 14, fontWeight: '700', marginTop: 2 },
  mono: { fontFamily: 'monospace', fontSize: 12 },
  feats: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 },
  feat: { borderWidth: 1, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2, fontSize: 12, fontWeight: '700' },
  cardTitle: { color: C.textStrong, fontSize: 14, fontWeight: '800' },
  small: { color: C.mute, fontSize: 12, marginTop: 4, lineHeight: 17 },
  advice: { color: C.text, fontSize: 14, marginTop: 6, lineHeight: 20 },
  hist: { flexDirection: 'row', alignItems: 'flex-end', gap: 8, height: 60, marginVertical: 6 },
  histCol: { alignItems: 'center' },
  histBar: { width: 16, borderRadius: 3 },
  histTxt: { color: C.dim, fontSize: 10, marginTop: 2 },
});
