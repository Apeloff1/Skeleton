/**
 * Operator run report — surfaces seal / playtest / repair status via
 * forgeOperator/runReport helpers over the last EngineRunPayload.
 */
import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { Banner, Card, Meter, SectionTitle, StatusPill } from '../../skeletonForge/components/primitives';
import { C, TONE_COLOR } from '../../skeletonForge/components/theme';
import type { Tone } from '../../skeletonForge/run';
import type { EngineRunPayload, EngineRunRequest } from '../types';
import {
  failedStage,
  groupFiles,
  operatorVerdict,
  playtestVerdict,
  repairSummary,
  stageTimeline,
  verificationSummary,
  type Verdict,
} from '../runReport';

export interface RunReportPanelProps {
  payload: EngineRunPayload | null;
  request?: Partial<EngineRunRequest> | null;
  /** Whether a seal header was attached to the request (never the secret itself). */
  sealAttached?: boolean;
  testID?: string;
}

function verdictTone(v: Verdict): Tone {
  if (v === 'ship') return 'ok';
  if (v === 'review') return 'warn';
  return 'bad';
}

function stageTone(state: string): Tone {
  if (state === 'ok' || state === 'retried') return 'ok';
  if (state === 'failed') return 'bad';
  if (state === 'skipped') return 'warn';
  return 'idle';
}

function playtestTone(state: string): Tone {
  if (state === 'passed') return 'ok';
  if (state === 'failed' || state === 'blocked') return 'bad';
  if (state === 'unavailable' || state === 'off') return 'warn';
  return 'idle';
}

export default function RunReportPanel({ payload, request, sealAttached = false, testID }: RunReportPanelProps) {
  const verdict = React.useMemo(() => operatorVerdict(payload, request ?? undefined), [payload, request]);
  const playtest = React.useMemo(
    () => playtestVerdict(payload, request?.playtest),
    [payload, request?.playtest],
  );
  const repair = React.useMemo(
    () => repairSummary(payload, request?.repair_mode),
    [payload, request?.repair_mode],
  );
  const verify = React.useMemo(() => verificationSummary(payload), [payload]);
  const stages = React.useMemo(() => stageTimeline(payload), [payload]);
  const failed = React.useMemo(() => failedStage(payload), [payload]);
  const files = React.useMemo(() => groupFiles(payload?.file_names), [payload?.file_names]);

  if (!payload) {
    return (
      <View testID={testID}>
        <SectionTitle>📋 Run report</SectionTitle>
        <Card>
          <Text style={st.idle}>
            No engine run yet. Forge with the engine from Compose / Run, then return here for seal, playtest and repair status.
          </Text>
        </Card>
      </View>
    );
  }

  const runId = payload.run?.run_id;
  const sealStage = stages.find((s) => s.name === 'seal');
  const sealOk = sealStage?.state === 'ok' || sealStage?.state === 'retried';

  return (
    <View testID={testID}>
      <SectionTitle hint={runId ? `run ${runId}` : undefined}>📋 Run report</SectionTitle>

      <Card testID="operator-report-verdict">
        <View style={st.head}>
          <StatusPill tone={verdictTone(verdict.verdict)} label={verdict.verdict.toUpperCase()} testID="operator-verdict" />
          <Text style={st.muted}>{payload.succeeded === false ? 'Pipeline failed' : 'Pipeline returned'}</Text>
        </View>
        {verdict.reasons.map((r, i) => (
          <Text key={`${r.level}-${i}`} style={[st.reason, { color: TONE_COLOR[verdictTone(r.level)] }]}>
            · {r.text}
          </Text>
        ))}
      </Card>

      <Card label="Seal status" testID="operator-report-seal">
        <View style={st.head}>
          <Text style={st.cardTitle}>Seal</Text>
          <StatusPill
            tone={sealOk ? 'ok' : sealStage?.state === 'failed' ? 'bad' : sealStage?.state === 'not_run' ? 'idle' : 'warn'}
            label={
              sealStage
                ? `stage ${sealStage.state}${sealStage.attempts > 1 ? ` · ${sealStage.attempts}×` : ''}`
                : 'no seal stage'
            }
            testID="operator-seal-status"
          />
        </View>
        <Text style={st.detail}>
          Request seal header: {sealAttached ? 'attached (caller-supplied)' : 'not attached'}
          {payload.ledger
            ? ` · ledger ${payload.ledger.valid ? 'valid' : 'INVALID'} @ height ${payload.ledger.height}`
            : ''}
        </Text>
        {sealStage?.error ? <Banner tone="bad">{sealStage.error}</Banner> : null}
      </Card>

      <Card label="Playtest" testID="operator-report-playtest">
        <View style={st.head}>
          <Text style={st.cardTitle}>Playtest</Text>
          <StatusPill tone={playtestTone(playtest.state)} label={playtest.label} testID="operator-playtest-status" />
        </View>
        <Text style={st.detail}>{playtest.detail}</Text>
        <View style={st.facts}>
          <Fact k="Mode" v={String(playtest.mode)} />
          <Fact k="Gating" v={playtest.gating ? 'yes' : 'no'} />
          <Fact k="Frames" v={playtest.frames == null ? '—' : String(playtest.frames)} />
          <Fact k="Binary" v={playtest.binarySource ?? '—'} />
        </View>
        {playtest.errors.length ? (
          <Banner tone="bad">{playtest.errors.slice(0, 3).join('\n')}</Banner>
        ) : null}
      </Card>

      <Card label="Repair" testID="operator-report-repair">
        <View style={st.head}>
          <Text style={st.cardTitle}>Repair</Text>
          <StatusPill
            tone={repair.clean ? 'ok' : repair.mode === 'suggest' && repair.proposed > 0 ? 'warn' : repair.applied > 0 ? 'ok' : 'idle'}
            label={repair.clean ? 'CLEAN' : `${repair.mode} · ${repair.applied} applied / ${repair.proposed} proposed`}
            testID="operator-repair-status"
          />
        </View>
        <Text style={st.detail}>
          {repair.reason || (repair.clean ? 'First verification round already accepted.' : 'Repair loop finished.')}
        </Text>
        <View style={st.facts}>
          <Fact k="Before" v={repair.beforeScore == null ? '—' : repair.beforeScore.toFixed(2)} />
          <Fact k="After" v={repair.afterScore == null ? '—' : repair.afterScore.toFixed(2)} />
          <Fact k="Paths" v={String(repair.paths.length)} />
        </View>
        {repair.byClass.length ? (
          <Text style={st.muted}>
            By class: {repair.byClass.map((c) => `${c.klass}×${c.count}`).join(', ')}
          </Text>
        ) : null}
      </Card>

      <Card label="Verification" testID="operator-report-verify">
        <View style={st.head}>
          <Text style={st.cardTitle}>Verification</Text>
          <StatusPill
            tone={verify.accepted === true ? 'ok' : verify.accepted === false ? 'bad' : 'idle'}
            label={
              verify.accepted === true
                ? 'Accepted'
                : verify.accepted === false
                  ? 'Rejected'
                  : 'No verdict'
            }
          />
        </View>
        <Meter
          ratio={verify.score ?? 0}
          color={verify.accepted === false ? C.red : C.green}
          label={`Score ${verify.score?.toFixed(2) ?? '—'} · threshold ${verify.threshold?.toFixed(2) ?? '—'}`}
        />
        <Text style={st.muted}>
          {verify.files.checked} checked · {verify.files.warned} warned · {verify.files.failed} failed
          {verify.weakestPath ? ` · weakest ${verify.weakestPath}` : ''}
        </Text>
        {failed ? (
          <Banner tone="bad">
            Failed stage “{failed.name}”{failed.error ? `: ${failed.error}` : ''}
          </Banner>
        ) : null}
      </Card>

      <Card label="Stages" testID="operator-report-stages">
        <Text style={st.cardTitle}>Stage timeline</Text>
        {stages.map((s) => (
          <View key={s.name} style={st.stageRow}>
            <StatusPill tone={stageTone(s.state)} label={s.state} />
            <Text style={st.stageName}>{s.name}</Text>
            <Text style={st.muted}>{s.durationS ? `${s.durationS.toFixed(1)}s` : ''}</Text>
          </View>
        ))}
      </Card>

      {files.length ? (
        <Card label="Artefacts" testID="operator-report-files">
          <Text style={st.cardTitle}>Emitted files</Text>
          {files.map((g) => (
            <Text key={g.folder} style={st.muted}>
              {g.folder}/ ({g.files.length})
            </Text>
          ))}
        </Card>
      ) : null}
    </View>
  );
}

function Fact({ k, v }: { k: string; v: string }) {
  return (
    <View style={st.fact}>
      <Text style={st.factK}>{k}</Text>
      <Text style={st.factV} numberOfLines={1}>
        {v}
      </Text>
    </View>
  );
}

const st = StyleSheet.create({
  idle: { color: C.mute, fontSize: 14, lineHeight: 20 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8, flexWrap: 'wrap' },
  cardTitle: { color: C.textStrong, fontWeight: '800', fontSize: 14 },
  detail: { color: C.text, fontSize: 13, lineHeight: 19, marginBottom: 8 },
  muted: { color: C.mute, fontSize: 12, marginTop: 4 },
  reason: { fontSize: 13, marginTop: 4, fontWeight: '600' },
  facts: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 6 },
  fact: { minWidth: '40%', flexGrow: 1 },
  factK: { color: C.dim, fontSize: 11, fontWeight: '700', textTransform: 'uppercase' },
  factV: { color: C.text, fontSize: 13, fontWeight: '600' },
  stageRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 6 },
  stageName: { color: C.text, fontWeight: '600', flex: 1 },
});
