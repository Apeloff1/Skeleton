/** Three-hatchling Dragon research cockpit; authenticated, read-only evidence. */
import React from 'react';
import { View, Text, ScrollView, TextInput, TouchableOpacity, ActivityIndicator, StyleSheet, SafeAreaView } from 'react-native';
import StudioLoginGate from '../src/auth/StudioLoginGate';
import { getAuthToken, authHeaders } from '../src/auth/gameforgeAuth';
import api from '../src/utils/apiClient';

type Lane = 'article' | 'video' | 'updates';
type Child = {
  lane: Lane; source_id: string; status: string; capture_digest: string | null;
  observed_at: number | null; improvements: string[]; review_required: boolean;
  growth: { stage: string; level: number; accepted_evidence_count: number };
};
type Family = {
  schema: string; hatchlings: Child[]; mother_stage: string;
  mother_level: number | null; review_ready_count: number;
  distinct_source_count: number;
};
type Hypothesis = {
  hypothesis_digest: string; shared_terms: string[];
  article: { exact_quote: string };
  video: { exact_quote: string; start_ms: number; end_ms: number };
  updates: { exact_quote: string };
};
type Review = { status: string; hypotheses: Hypothesis[] };
const ID = /^source-[0-9a-f]{64}$/;
const LANES: ReadonlyArray<{ lane: Lane; label: string; activity: string }> = [
  { lane: 'article', label: '📖 Article hatchling', activity: 'Exact web article citations' },
  { lane: 'video', label: '🎬 Video hatchling', activity: 'Timecoded licensed transcripts' },
  { lane: 'updates', label: '🔎 Update hatchling', activity: 'Changed-source comparisons' },
];
const COLORS = { bg: '#07131f', card: '#142238', text: '#f8fafc', muted: '#b2c2d1', line: '#36516a' };

function ResearchScreen() {
  const [sources, setSources] = React.useState<Record<Lane, string>>({
    article: '', video: '', updates: '',
  });
  const [family, setFamily] = React.useState<Family | null>(null);
  const [review, setReview] = React.useState<Review | null>(null);
  const [error, setError] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const [showQuotes, setShowQuotes] = React.useState(false);
  const attempt = React.useRef(0);
  const controller = React.useRef<AbortController | null>(null);
  const valid = LANES.every(item => ID.test(sources[item.lane]))
    && sources.article !== sources.video && sources.updates !== sources.video;

  React.useEffect(() => () => { controller.current?.abort(); attempt.current += 1; }, []);
  const change = (lane: Lane, raw: string) => {
    controller.current?.abort();
    attempt.current += 1;
    setSources(prev => ({ ...prev, [lane]: raw.trim().toLowerCase() }));
    setBusy(false); setFamily(null); setReview(null); setShowQuotes(false); setError('');
  };
  const load = async () => {
    if (!valid || busy) return;
    const id = ++attempt.current;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true); setError(''); setFamily(null); setReview(null);
    setShowQuotes(false);
    const query = 'article=' + encodeURIComponent(sources.article)
      + '&video=' + encodeURIComponent(sources.video)
      + '&updates=' + encodeURIComponent(sources.updates);
    const options = {
      timeoutMs: 12000, retries: 0, signal: abort.signal,
      headers: getAuthToken() ? authHeaders() : {},
    };
    try {
      const one = await api.get<Family>('/api/dragon-research/status?' + query, options);
      if (abort.signal.aborted || id !== attempt.current) return;
      if (!one.ok || one.data?.schema !== 'skeleton.dragon.three_hatchlings.v1') {
        setError(one.status === 503
          ? 'Trusted Dragon research storage is not configured. No data was read.'
          : 'The requested evidence is unavailable for this signed-in account.');
        return;
      }
      if (one.data.hatchlings.length !== 3
        || one.data.hatchlings.some((c, i) =>
          c.lane !== LANES[i].lane || c.source_id !== sources[c.lane])) {
        setError('The backend Dragon evidence did not match the selected source identities.');
        return;
      }
      setFamily(one.data);
      const two = await api.get<Review>('/api/dragon-research/mother-review?' + query, options);
      if (abort.signal.aborted || id !== attempt.current) return;
      if (two.ok && two.data) setReview(two.data);
      else setError('Mother review unavailable; individual hatchling status remains visible.');
    } catch {
      if (!abort.signal.aborted && id === attempt.current)
        setError('Research service unavailable. No background worker was started.');
    } finally {
      if (id === attempt.current) setBusy(false);
      if (controller.current === abort) controller.current = null;
    }
  };
  return (
    <SafeAreaView style={styles.root}>
      <ScrollView contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        <Text style={styles.title}>🐉 The Dragon family</Text>
        <Text style={styles.sub}>Three idle-only hatchlings · one mother · independently reviewed knowledge</Text>
        <Text style={styles.warning}>
          Research evidence is not approved knowledge, XP, or model training.
        </Text>
        {LANES.map(item => {
          const c = family?.hatchlings.find(child => child.lane === item.lane);
          return (
            <View key={item.lane} style={styles.card} testID={'dragon-' + item.lane}>
              <Text style={styles.heading}>{item.label}</Text>
              <Text style={styles.muted}>{item.activity}</Text>
              <TextInput
                accessibilityLabel={item.label + ' canonical source ID'}
                style={styles.input} value={sources[item.lane]}
                onChangeText={value => change(item.lane, value)}
                placeholder="source- followed by 64 hex characters"
                placeholderTextColor="#8397a8" autoCapitalize="none"
                autoCorrect={false} maxLength={71}
              />
              <Text style={styles.muted}>
                {c ? 'Stage: ' + c.growth.stage + ' · Level ' + c.growth.level
                  + ' · Accepted evidence: ' + c.growth.accepted_evidence_count
                  : 'No verified progress loaded'}
              </Text>
              <Text style={styles.muted}>{c?.status || 'Awaiting verified evidence'}</Text>
              {c?.observed_at != null && (
                <Text style={styles.muted}>
                  {'Observed UTC: ' + new Date(c.observed_at * 1000).toISOString()}
                </Text>
              )}
              {(c?.improvements || []).map((note, i) => (
                <Text key={item.lane + i} style={styles.note}>{note}</Text>
              ))}
            </View>
          );
        })}
        <TouchableOpacity
          style={[styles.button, (!valid || busy) && styles.disabled]}
          disabled={!valid || busy}
          accessibilityRole="button" testID="dragon-family-load"
          onPress={() => { void load(); }}
        >
          <Text style={styles.buttonText}>
            {busy ? 'Reading evidence…' : 'Inspect all three hatchlings'}
          </Text>
        </TouchableOpacity>
        {busy && <ActivityIndicator />}
        {!!error && <Text accessibilityRole="alert" style={styles.warning}>{error}</Text>}
        {family && (
          <View style={styles.card}>
            <Text style={styles.heading}>🐲 Mother Dragon</Text>
            <Text style={styles.muted}>
              {'Stage: ' + family.mother_stage + ' · Level: '
                + (family.mother_level ?? 'not initialized')}
            </Text>
            <Text style={styles.muted}>
              {'Review-ready: ' + family.review_ready_count + '/3'
                + ' · Distinct source identities: ' + family.distinct_source_count}
            </Text>
            <Text style={styles.warning}>Three roles do not imply three independent sources.</Text>
            {review && (
              <>
                <Text style={styles.muted}>{review.status}</Text>
                <Text style={styles.muted}>
                  {'Unverified research questions: ' + review.hypotheses.length}
                </Text>
                {review.hypotheses.length > 0 && (
                  <TouchableOpacity accessibilityRole="button"
                    onPress={() => setShowQuotes(!showQuotes)}>
                    <Text style={styles.action}>{showQuotes ? 'Hide excerpts' : 'Show exact excerpts'}</Text>
                  </TouchableOpacity>
                )}
                {showQuotes && review.hypotheses.slice(0, 12).map((h, i) => (
                  <View style={styles.evidence} key={h.hypothesis_digest || String(i)}>
                    <Text style={styles.heading}>{'Research question ' + (i + 1)}</Text>
                    <Text style={styles.muted}>{h.shared_terms.join(', ')}</Text>
                    <Text style={styles.quote}>{'Article: ' + h.article.exact_quote}</Text>
                    <Text style={styles.quote}>
                      {'Video ' + h.video.start_ms + '–' + h.video.end_ms
                        + 'ms: ' + h.video.exact_quote}
                    </Text>
                    <Text style={styles.quote}>{'Update: ' + h.updates.exact_quote}</Text>
                    <Text style={styles.warning}>Requires independent Wiki/HOAG review.</Text>
                  </View>
                ))}
              </>
            )}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

export default function DragonResearchRoute() {
  return <StudioLoginGate><ResearchScreen /></StudioLoginGate>;
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: COLORS.bg },
  body: { padding: 18, paddingBottom: 55, gap: 14 },
  title: { fontSize: 25, fontWeight: '800', color: COLORS.text },
  sub: { color: COLORS.muted, fontSize: 14 },
  card: { borderRadius: 14, padding: 15, backgroundColor: COLORS.card,
    borderColor: COLORS.line, borderWidth: 1, gap: 8 },
  heading: { fontSize: 17, color: COLORS.text, fontWeight: '700' },
  muted: { color: COLORS.muted, fontSize: 13 },
  warning: { color: '#ffce80', fontSize: 13, fontWeight: '600' },
  note: { color: '#8ce1d1', fontSize: 12 },
  input: { borderWidth: 1, borderRadius: 9, borderColor: COLORS.line,
    color: COLORS.text, padding: 11, fontSize: 13 },
  button: { backgroundColor: '#287c74', padding: 14,
    borderRadius: 11, alignItems: 'center' },
  buttonText: { color: '#fff', fontWeight: '700', fontSize: 14 },
  disabled: { opacity: 0.5 },
  action: { color: '#8ce1d1', fontSize: 14, fontWeight: '700' },
  evidence: { borderTopColor: COLORS.line, borderTopWidth: 1, paddingTop: 10, gap: 7 },
  quote: { color: COLORS.text, fontSize: 12, lineHeight: 18 },
});
