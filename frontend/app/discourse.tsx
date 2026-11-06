/**
 * /discourse — Discourse & Discord (multi-AI debate for the creative process).
 *
 * The authenticated canonical engine selects ready models. One available
 * model is labeled self-review instead of fabricated cross-provider consensus.
 * Work is admitted once and the UI observes its durable status independently.
 */
import React from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator, TextInput,
  StyleSheet, SafeAreaView, Platform, KeyboardAvoidingView, Switch,
} from 'react-native';
import { useRouter } from 'expo-router';
import api, { subscribeApiSessionChanges } from '../src/utils/apiClient';
import { useHaptics } from '../src/hooks/useHaptics';
import {
  discoverDiscourseJobs, pollDiscourseJob, submitDiscourseJob,
  type DiscourseJobSummary, type DiscourseOutcome, type DiscourseResult,
} from '../src/features/discourse/discourseJob';

export default function DiscourseScreen() {
  const router = useRouter();
  const haptics = useHaptics();
  const [prompt, setPrompt] = React.useState('Design one original core mechanic for a calm puzzle game about light.');
  const [discord, setDiscord] = React.useState(true);
  const [busy, setBusy] = React.useState(false);
  const [res, setRes] = React.useState<DiscourseResult | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [canResume, setCanResume] = React.useState(false);
  const [progress, setProgress] = React.useState<string | null>(null);
  const [recentJobs, setRecentJobs] = React.useState<DiscourseJobSummary[]>([]);
  const [discoveryError, setDiscoveryError] = React.useState<string | null>(null);
  const [discoveryBusy, setDiscoveryBusy] = React.useState(false);
  const observer = React.useRef<AbortController | null>(null);
  const sessionEpoch = React.useRef(0);
  const mounted = React.useRef(true);
  const occupied = React.useRef(false);

  const recoverRecentJobs = React.useCallback(async (signal?: AbortSignal) => {
    if (!mounted.current || signal?.aborted) return;
    const epoch = sessionEpoch.current;
    setDiscoveryBusy(true);
    const result = await discoverDiscourseJobs(api, { signal });
    if (!mounted.current || signal?.aborted || epoch !== sessionEpoch.current) return;
    if (result.ok) {
      setRecentJobs(result.jobs);
      setDiscoveryError(null);
    } else {
      setRecentJobs([]);
      setDiscoveryError(result.error);
    }
    setDiscoveryBusy(false);
  }, []);

  React.useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    void recoverRecentJobs(controller.signal);
    return () => {
      mounted.current = false;
      controller.abort();
      observer.current?.abort();
      observer.current = null;
    };
  }, [recoverRecentJobs]);

  React.useEffect(() => subscribeApiSessionChanges(() => {
    sessionEpoch.current += 1;
    // A login/logout clears every displayed private prompt, verdict and
    // receipt from the previous principal without relying on navigation.
    observer.current?.abort();
    // Detach BEFORE abort completion can resolve: an old account's response
    // must never pass the observer identity check after login/logout.
    observer.current = null;
    occupied.current = false;
    setBusy(false);
    // A typed brief is private to the previous authenticated account too.
    setPrompt('');
    setRes(null);
    setJobId(null);
    setCanResume(false);
    setError(null);
    setProgress(null);
    setRecentJobs([]);
    setDiscoveryError(null);
    setDiscoveryBusy(false);
    void recoverRecentJobs();
  }), [recoverRecentJobs]);

  const beginObserve = React.useCallback(async (resumeId?: string) => {
    if (occupied.current) return;
    if (!resumeId && (prompt.trim().length < 4 || prompt.length > 20_000)) {
      setError('Enter a prompt between 4 and 20,000 characters.');
      return;
    }
    occupied.current = true;
    observer.current?.abort();
    const controller = new AbortController();
    observer.current = controller;
    setBusy(true);
    setError(null);
    setRes(null);
    setCanResume(false);
    setProgress(resumeId ? 'Reconnecting to the existing job…' : 'Submitting one private job…');
    if (!resumeId) setJobId(null);

    const onProgress = (update: { status: 'submitting' | 'running'; jobId: string | null; attempts: number }) => {
      if (!mounted.current || observer.current !== controller) return;
      if (update.jobId) setJobId(update.jobId);
      setProgress(update.status === 'submitting'
        ? 'Submitting your job…'
        : 'Observing model execution (check ' + update.attempts + ')…');
    };

    let outcome: DiscourseOutcome;
    try {
      if (resumeId) {
        outcome = await pollDiscourseJob(api, resumeId, {
          signal: controller.signal, onProgress,
        });
      } else {
        outcome = await submitDiscourseJob(api, {
          task: 'creative', prompt: prompt.trim(), discord,
        }, {
          signal: controller.signal, onProgress,
        });
      }
    } catch {
      // No automatic POST replay: a transport error may hide committed work.
      outcome = { ok: false, jobId: resumeId || null,
        error: 'observation_unavailable', recoverable: !!resumeId };
    }
    if (mounted.current && observer.current === controller) {
      if (outcome.ok) {
        setJobId(outcome.jobId);
        setRes(outcome.result);
        setProgress(null);
      } else {
        setJobId(outcome.jobId);
        setError(outcome.error === 'admission_unconfirmed_do_not_retry'
          ? 'The server did not confirm admission. Do not resubmit until you check job history.'
          : outcome.error);
        setCanResume(outcome.recoverable && !!outcome.jobId);
        setProgress(null);
      }
      setBusy(false);
    }
    if (observer.current === controller) {
      observer.current = null;
      occupied.current = false;
    }
  }, [prompt, discord]);

  const run = React.useCallback(() => {
    haptics.selection();
    void beginObserve();
  }, [beginObserve, haptics]);

  const resume = React.useCallback(() => {
    if (jobId && canResume) void beginObserve(jobId);
  }, [beginObserve, canResume, jobId]);


  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.header}>
        <TouchableOpacity testID="dc-back" onPress={() => router.back()} style={styles.backBtn}>
          <Text style={styles.backTxt}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Discourse & Discord</Text>
        <View style={styles.backBtn} />
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView style={styles.scroll} contentContainerStyle={{ paddingBottom: 40 }} keyboardShouldPersistTaps="handled">
          <Text style={styles.label}>Creative prompt</Text>
          <TextInput
            testID="dc-prompt"
            style={styles.input}
            value={prompt}
            onChangeText={setPrompt}
            placeholder="What should the AI panel deliberate?"
            placeholderTextColor="#475569"
            multiline
            maxLength={20_000}
            editable={!busy}
          />
          <View style={styles.row}>
            <Text style={styles.discordLbl}>⚔️ Discord (cross red-team critique)</Text>
            <Switch value={discord} onValueChange={(v) => { haptics.selection(); setDiscord(v); }} />
          </View>
          <TouchableOpacity testID="dc-run" style={[styles.cta, busy && { opacity: 0.5 }]} onPress={run} disabled={busy}>
            {busy ? (
              <View style={styles.busyRow}><ActivityIndicator color="#fff" /><Text style={styles.ctaTxt}>  Panel deliberating…</Text></View>
            ) : <Text style={styles.ctaTxt}>Deliberate →</Text>}
          </TouchableOpacity>
          {busy ? (
            <View>
              <Text style={styles.hint}>{progress || 'Observing an admitted private job…'}</Text>
              <TouchableOpacity testID="dc-stop-observing" style={styles.secondaryCta}
                onPress={() => observer.current?.abort()}>
                <Text style={styles.secondaryTxt}>Stop observing (job may continue)</Text>
              </TouchableOpacity>
            </View>
          ) : null}
          {jobId ? <Text testID="dc-job-id" style={styles.hint}>Job: {jobId}</Text> : null}
          {error ? <Text style={styles.err}>{error}</Text> : null}
          {!busy && canResume && jobId ? (
            <TouchableOpacity testID="dc-resume" style={styles.secondaryCta} onPress={resume}>
              <Text style={styles.secondaryTxt}>Resume checking this job</Text>
            </TouchableOpacity>
          ) : null}

          <View testID="dc-private-job-history" style={styles.jobHistory}>
            <Text style={styles.label}>Previous private deliberations</Text>
            <Text style={styles.hint}>
              Retrieved from your authenticated account, not a shared device cache.
              A stored running status does not confirm the worker survived a restart.
            </Text>
            <TouchableOpacity testID="dc-refresh-jobs" style={styles.secondaryCta}
              disabled={busy || discoveryBusy}
              onPress={() => { void recoverRecentJobs(); }}>
              <Text style={styles.secondaryTxt}>
                {discoveryBusy ? 'Checking private jobs…' : 'Refresh recent jobs'}
              </Text>
            </TouchableOpacity>
            {discoveryError ? (
              <Text style={styles.hint}>Private job history is unavailable: {discoveryError}</Text>
            ) : null}
            {recentJobs.map(job => (
              <TouchableOpacity key={job.jobId}
                testID={'dc-recover-' + job.jobId}
                style={styles.secondaryCta} disabled={busy}
                onPress={() => { void beginObserve(job.jobId); }}>
                <Text style={styles.secondaryTxt}>
                  {job.status === 'done' ? 'View saved result' : 'Check previous job'}
                  {' · '}{job.jobId.slice(0, 10)}{' · '}{job.status}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {res ? (
            <View testID="dc-result">
              <View style={styles.winner}>
                <Text style={styles.winnerTag}>
                  {res.deliberation_mode === 'single_model_self_review' ? 'Single-model review' : '🏆 WINNER'} · {res.winner_model} · {res.winner_score ?? '—'}/100
                </Text>
                {res.deliberation_mode ? (
                  <Text style={styles.modeHint}>
                    {res.deliberation_mode === 'cross_provider'
                      ? 'Multiple authorized providers participated.'
                      : res.deliberation_mode === 'multiple_models_one_provider'
                        ? 'Multiple authorized models from one provider participated.'
                        : 'Only one authorized model was available; no independent model consensus is claimed.'}
                  </Text>
                ) : null}
                <Text style={styles.winnerTxt}>{res.winner_content}</Text>
                {res.judge_why ? <Text style={styles.judgeWhy}>Judge ({res.judge_model}): {res.judge_why}</Text> : null}
              </View>

              <Text style={styles.sectionTitle}>The panel ({res.candidates.length})</Text>
              {res.candidates.map((c, i) => (
                <View key={i} style={[styles.cand, i === res.winner_index && styles.candWin]} testID={`dc-cand-${i}`}>
                  <View style={styles.candHead}>
                    <Text style={styles.candModel}>{c.model}</Text>
                    <Text style={styles.candScore}>Q {c.quality ?? '–'} · F {c.fidelity ?? '–'} → {c.score ?? '–'}</Text>
                  </View>
                  <Text style={styles.candTxt} numberOfLines={6}>{c.content}</Text>
                  {c.critique ? (
                    <View style={styles.critBox}>
                      <Text style={styles.critLbl}>⚔️ Critique</Text>
                      <Text style={styles.critTxt} numberOfLines={5}>{c.critique}</Text>
                    </View>
                  ) : null}
                </View>
              ))}
            </View>
          ) : null}
        </ScrollView>
      </KeyboardAvoidingView>
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
  label: { color: '#cbd5e1', fontSize: 13, fontWeight: '700', marginTop: 14, marginBottom: 8 },
  input: {
    backgroundColor: '#0A0A0A', borderRadius: 10, color: '#e2e8f0', padding: 12,
    minHeight: 80, fontSize: 14, textAlignVertical: 'top', borderWidth: 1, borderColor: '#1F1F1F',
  },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 12 },
  discordLbl: { color: '#cbd5e1', fontSize: 13, fontWeight: '600' },
  cta: { backgroundColor: '#8B5CF6', borderRadius: 10, paddingVertical: 13, alignItems: 'center', marginTop: 14 },
  busyRow: { flexDirection: 'row', alignItems: 'center' },
  ctaTxt: { color: '#fff', fontWeight: '800', fontSize: 14 },
  secondaryCta: { borderColor: '#64748b', borderWidth: 1, borderRadius: 10,
    paddingVertical: 11, paddingHorizontal: 12, alignItems: 'center', marginTop: 10 },
  secondaryTxt: { color: '#cbd5e1', fontWeight: '700', fontSize: 12 },
  modeHint: { color: '#86efac', fontSize: 12, marginTop: 6 },
  jobHistory: { marginTop: 16, marginBottom: 18, paddingVertical: 12 },
  hint: { color: '#64748b', fontSize: 12, marginTop: 8, textAlign: 'center' },
  err: { color: '#fca5a5', fontSize: 13, marginTop: 12 },
  winner: { backgroundColor: '#0f2417', borderColor: '#22c55e', borderWidth: 1, borderRadius: 12, padding: 14, marginTop: 18 },
  winnerTag: { color: '#4ade80', fontSize: 13, fontWeight: '800' },
  winnerTxt: { color: '#e2e8f0', fontSize: 15, lineHeight: 22, marginTop: 8 },
  judgeWhy: { color: '#86efac', fontSize: 12, marginTop: 10, fontStyle: 'italic' },
  sectionTitle: { color: '#cbd5e1', fontSize: 13, fontWeight: '700', marginTop: 20, marginBottom: 8 },
  cand: { backgroundColor: '#0A0A0A', borderRadius: 10, padding: 12, marginBottom: 10, borderWidth: 1, borderColor: '#1F1F1F' },
  candWin: { borderColor: '#22c55e' },
  candHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  candModel: { color: '#fff', fontSize: 13, fontWeight: '700' },
  candScore: { color: '#fbbf24', fontSize: 12, fontWeight: '700' },
  candTxt: { color: '#cbd5e1', fontSize: 13, lineHeight: 19 },
  critBox: { backgroundColor: '#1a0f12', borderRadius: 8, padding: 10, marginTop: 8 },
  critLbl: { color: '#f87171', fontSize: 11, fontWeight: '800' },
  critTxt: { color: '#fca5a5', fontSize: 12, marginTop: 4, lineHeight: 17 },
});
