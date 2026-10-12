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
type SourceOption = {
  source_id: string; kind: 'article' | 'video';
  host: string; label: string; research_status: string;
};
type SourceCatalog = {
  schema: string; entries: SourceOption[];
  has_more: boolean; next_after_source: string | null;
};
type ResearchMission = {
  lane: Lane; source_id: string; label: string; host: string;
  action: string; next_step: string; evidence_digest: string | null;
  observed_at: number | null; requires_idle: boolean;
  requires_operator_authorization: boolean;
  requires_independent_wiki_review: boolean;
};
type ResearchWorkboard = {
  schema: string; missions: ResearchMission[];
  has_more: boolean; next_after_source: string | null;
  read_only: boolean; network_requests: number;
  workers_started: number; training_authorized: boolean;
};
type HistoryEvent = {
  lane: Lane; source_id: string; event_digest: string;
  observation_at: number; sequence: number;
  kind: string; change_note: string;
};
type FamilyHistory = {
  schema: string; entries: HistoryEvent[];
  total_events: number; truncated: boolean;
  event_counts: Record<Lane, number>;
  read_only: boolean; xp_awarded: number;
  training_authorized: boolean;
};
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
  const [available, setAvailable] = React.useState<SourceOption[]>([]);
  const [catalogCursor, setCatalogCursor] = React.useState<string | null>(null);
  const [catalogLoaded, setCatalogLoaded] = React.useState(false);
  const [missions, setMissions] = React.useState<ResearchMission[]>([]);
  const [workboardLoaded, setWorkboardLoaded] = React.useState(false);
  const [workboardCursor, setWorkboardCursor] = React.useState<string | null>(null);
  const [history, setHistory] = React.useState<FamilyHistory | null>(null);
  const [catalogSearch, setCatalogSearch] = React.useState("");
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
    setBusy(false); setFamily(null); setReview(null);
    setHistory(null); setShowQuotes(false); setError('');
  };
  const reviewWorkboard = async (cursor: string | null = null) => {
    if (busy) return;
    const id = ++attempt.current;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true); setError('');
    try {
      const path = '/api/dragon-research/workboard?limit=30'
        + (cursor ? '&after_source=' + encodeURIComponent(cursor) : '');
      const result = await api.get<ResearchWorkboard>(path, {
        timeoutMs: 12000, retries: 0, signal: abort.signal,
        headers: getAuthToken() ? authHeaders() : {},
      });
      if (abort.signal.aborted || id !== attempt.current) return;
      if (!result.ok || result.data?.schema !==
          'skeleton.dragon.research_workboard.v1'
        || result.data.read_only !== true
        || result.data.training_authorized !== false
        || result.data.workers_started !== 0) {
        setError('Review workboard unavailable or returned untrusted state.');
        return;
      }
      const verified = result.data.missions.filter(m =>
        ID.test(m.source_id) && LANES.some(l => l.lane === m.lane));
      setMissions(existing => {
        const previous = cursor ? existing : [];
        const seen = new Map<string, ResearchMission>();
        for (const task of [...previous,...verified])
          seen.set(task.source_id + ':' + task.lane, task);
        return Array.from(seen.values());
      });
      setWorkboardCursor(result.data.has_more
        ? result.data.next_after_source : null);
      setWorkboardLoaded(true);
    } catch {
      if (!abort.signal.aborted && id === attempt.current)
        setError('Research workboard unavailable. No research was started.');
    } finally {
      if (id === attempt.current) setBusy(false);
      if (controller.current === abort) controller.current = null;
    }
  };

  const discover = async (cursor: string | null = null) => {
    if (busy) return;
    const id = ++attempt.current;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true); setError('');
    try {
      const url = '/api/dragon-research/sources?limit=60'
        + (cursor ? '&after_source=' + encodeURIComponent(cursor) : '');
      const response = await api.get<SourceCatalog>(url, {
        timeoutMs: 12000, retries: 0, signal: abort.signal,
        headers: getAuthToken() ? authHeaders() : {},
      });
      if (abort.signal.aborted || id !== attempt.current) return;
      if (!response.ok || response.data?.schema !==
          'skeleton.dragon.research_source_catalog.v1') {
        setError(response.status === 503
          ? 'The operator has not configured the trusted research runtime.'
          : 'Available research sources could not be verified.');
        return;
      }
      const entries = response.data.entries.filter(item =>
        ID.test(item.source_id)
        && (item.kind === 'article' || item.kind === 'video'));
      setAvailable(existing => {
        const byId = new Map<string, SourceOption>(
          (cursor ? existing : []).map(item =>
            [item.source_id, item] as const)
        );
        for (const item of entries) byId.set(item.source_id, item);
        return Array.from(byId.values());
      });
      const article = entries.find(item => item.kind === 'article');
      const video = entries.find(item => item.kind === 'video');
      setSources(prev => ({
        article: prev.article || article?.source_id || '',
        updates: prev.updates || article?.source_id || '',
        video: prev.video || video?.source_id || '',
      }));
      setCatalogLoaded(true);
      setCatalogCursor(response.data.has_more
        ? response.data.next_after_source : null);
    } catch {
      if (!abort.signal.aborted && id === attempt.current)
        setError('Source discovery unavailable. No crawling was started.');
    } finally {
      if (id === attempt.current) setBusy(false);
      if (controller.current === abort) controller.current = null;
    }
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
    } catch {
      if (!abort.signal.aborted && id === attempt.current)
        setError('Research service unavailable. No background worker was started.');
    } finally {
      if (id === attempt.current) setBusy(false);
      if (controller.current === abort) controller.current = null;
    }
  };
  const readHistory = async () => {
    if (!valid || busy) return;
    const id = ++attempt.current;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true); setError('');
    const query = 'article=' + encodeURIComponent(sources.article)
      + '&video=' + encodeURIComponent(sources.video)
      + '&updates=' + encodeURIComponent(sources.updates);
    try {
      const result = await api.get<FamilyHistory>(
        '/api/dragon-research/history?' + query + '&limit=100',
        { timeoutMs: 12000, retries: 0, signal: abort.signal,
          headers: getAuthToken() ? authHeaders() : {} });
      if (abort.signal.aborted || id !== attempt.current) return;
      if (!result.ok || result.data?.schema !==
          'skeleton.dragon.three_hatchling_history.v1'
          || result.data.read_only !== true
          || result.data.xp_awarded !== 0
          || result.data.training_authorized !== false) {
        setError('Historical evidence could not be verified.');
        return;
      }
      setHistory(result.data);
    } catch {
      if (!abort.signal.aborted && id === attempt.current)
        setError('Historical evidence unavailable. No worker was started.');
    } finally {
      if (id === attempt.current) setBusy(false);
      if (controller.current === abort) controller.current = null;
    }
  };

  const inspectMother = async () => {
    if (!family || busy || !valid) return;
    const id = ++attempt.current;
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    setBusy(true); setError('');
    const query = 'article=' + encodeURIComponent(sources.article)
      + '&video=' + encodeURIComponent(sources.video)
      + '&updates=' + encodeURIComponent(sources.updates);
    try {
      const result = await api.get<Review>(
        '/api/dragon-research/mother-review?' + query,
        { timeoutMs: 12000, retries: 0, signal: abort.signal,
          headers: getAuthToken() ? authHeaders() : {} },
      );
      if (abort.signal.aborted || id !== attempt.current) return;
      if (result.ok && result.data) {
        setReview(result.data); setShowQuotes(true);
      } else {
        setError(result.status === 403
          ? 'Editor access is required to inspect exact source excerpts.'
          : 'Mother evidence is unavailable for these research sources.');
      }
    } catch {
      if (!abort.signal.aborted && id === attempt.current)
        setError('Could not retrieve the editor-only mother review.');
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
        <TouchableOpacity
          accessibilityRole="button" testID="dragon-discover-sources"
          disabled={busy} onPress={() => { void discover(null); }}
          style={[styles.button, busy && styles.disabled]}>
          <Text style={styles.buttonText}>
            {catalogLoaded ? 'Refresh available sources' : 'Discover my research sources'}
          </Text>
        </TouchableOpacity>
        {catalogLoaded && available.length === 0 && (
          <Text style={styles.warning}>
            No registered sources for this account. An operator must first curate and authorize the research catalog.
          </Text>
        )}
        {available.length > 0 && (
          <TextInput
            style={styles.input} accessibilityLabel="Filter registered research sources"
            value={catalogSearch} onChangeText={setCatalogSearch}
            placeholder="Filter sources by title or host"
            placeholderTextColor="#8397a8"
            autoCorrect={false} maxLength={80}
          />
        )}
        {LANES.map(item => {
          const c = family?.hatchlings.find(child => child.lane === item.lane);
          return (
            <View key={item.lane} style={styles.card} testID={'dragon-' + item.lane}>
              <Text style={styles.heading}>{item.label}</Text>
              <Text style={styles.muted}>{item.activity}</Text>
              <Text style={styles.muted}>Choose a verified, owner-scoped source:</Text>
              {available.filter(source => item.lane === 'video'
                ? source.kind === 'video' : source.kind === 'article'
              ).filter(source => !catalogSearch || (
                source.label + " " + source.host
              ).toLowerCase().includes(catalogSearch.toLowerCase()))
                .slice(0, 24).map(source => (
                <TouchableOpacity key={source.source_id}
                  accessibilityRole="button"
                  accessibilityLabel={'Select ' + source.label + ' for ' + item.lane}
                  onPress={() => change(item.lane, source.source_id)}
                  style={[styles.choice,
                    sources[item.lane] === source.source_id && styles.selected]}>
                  <Text style={styles.muted}>
                    {source.label + ' · ' + source.host + ' · ' + source.research_status}
                  </Text>
                </TouchableOpacity>
              ))}
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
        {!!catalogCursor && (
          <TouchableOpacity accessibilityRole="button"
            disabled={busy} style={[styles.button,busy && styles.disabled]}
            onPress={() => { void discover(catalogCursor); }}>
            <Text style={styles.buttonText}>More registered research sources</Text>
          </TouchableOpacity>
        )}
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
        <TouchableOpacity
          accessibilityRole="button" testID="dragon-research-workboard"
          disabled={busy} style={[styles.button, busy && styles.disabled]}
          onPress={() => { void reviewWorkboard(null); }}>
          <Text style={styles.buttonText}>Review all hatchling research work</Text>
        </TouchableOpacity>
        {workboardLoaded && (
          <View style={styles.card}>
            <Text style={styles.heading}>📋 Research workboard</Text>
            <Text style={styles.warning}>Suggested work is not approved knowledge or permission to crawl.</Text>
            {LANES.map(item => (
              <View key={item.lane}>
                <Text style={styles.heading}>{item.label}</Text>
                {missions.filter(m => m.lane === item.lane).slice(0, 30)
                  .map(m => (
                    <View style={styles.evidence}
                      key={m.lane + ':' + m.source_id}>
                      <Text style={styles.muted}>{m.label + ' · ' + m.host}</Text>
                      <Text style={styles.quote}>{m.next_step}</Text>
                      {m.observed_at != null && (
                        <Text style={styles.muted}>
                          {'Observed: ' + new Date(m.observed_at * 1000).toISOString()}
                        </Text>
                      )}
                      <Text style={styles.muted}>
                        {m.requires_idle
                          ? 'Only an idle, independently admitted worker may execute.'
                          : m.requires_independent_wiki_review
                            ? 'Requires independent Wiki review.'
                            : 'No autonomous action authorized.'}
                      </Text>
                    </View>
                  ))}
              </View>
            ))}
            {missions.length === 0 && (
              <Text style={styles.muted}>No eligible research sources on this page.</Text>
            )}
            {!!workboardCursor && (
              <TouchableOpacity accessibilityRole="button"
                disabled={busy} onPress={() => {
                  void reviewWorkboard(workboardCursor);
                }}>
                <Text style={styles.action}>More research work</Text>
              </TouchableOpacity>
            )}
          </View>
        )}
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
            <TouchableOpacity accessibilityRole="button"
              testID="dragon-history-refresh" disabled={busy}
              onPress={() => { void readHistory(); }}>
              <Text style={styles.action}>View timestamped hatchling changes</Text>
            </TouchableOpacity>
            {history && (
              <View style={styles.evidence}>
                <Text style={styles.heading}>
                  {'Family change history · ' + history.total_events + ' audited events'}
                </Text>
                {history.truncated && (
                  <Text style={styles.warning}>
                    Only the 100 most recent events are displayed.
                  </Text>
                )}
                {history.entries.map(event => (
                  <View key={event.event_digest} style={styles.evidence}>
                    <Text style={styles.muted}>
                      {event.lane.toUpperCase() + ' · '
                        + new Date(event.observation_at * 1000).toISOString()}
                    </Text>
                    <Text style={styles.quote}>{event.change_note}</Text>
                    <Text style={styles.muted}>
                      {'Change: ' + event.kind + ' · Source evidence ' +
                        event.event_digest.slice(0, 12)}
                    </Text>
                  </View>
                ))}
              </View>
            )}
            {!review && (
              <TouchableOpacity accessibilityRole="button"
                testID="dragon-inspect-mother-evidence" disabled={busy}
                onPress={() => { void inspectMother(); }}>
                <Text style={styles.action}>Inspect editor-only research evidence</Text>
              </TouchableOpacity>
            )}
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
  choice: { borderWidth: 1, borderColor: COLORS.line, padding: 9, borderRadius: 7 },
  selected: { backgroundColor: '#245a5a' },
});
