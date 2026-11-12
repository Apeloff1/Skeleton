/**
 * Dragon release prototype: a real, authenticated end-to-end user journey.
 * Reuses the canonical Mongo-backed crawler, source library, Atlas and
 * reviewed-knowledge controls. No second worker, DB, provider or source owner.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator, SafeAreaView, ScrollView, Share, Switch,
  Text, TextInput, TouchableOpacity, View, useWindowDimensions,
} from 'react-native';
import { useRouter } from 'expo-router';
import { CryptoDigestAlgorithm, digestStringAsync } from 'expo-crypto';
import StudioLoginGate, { useStudioAuth } from '../../auth/StudioLoginGate';
import { getAuthToken } from '../../auth/gameforgeAuth';
import {
  createCrawl, crawlRequestKey, controlCrawl, exportCrawlSource,
  getCrawl, getCrawlSource, getCrawlerReadiness, listCrawls, listCrawlSources,
  runCrawl, type CapturedSource, type CrawlAtlasReport, type CrawlCommand,
  type CrawlCreate, type CrawlerReadiness, type CrawlSession,
} from '../../product/crawlerClient';
import { saveCrawlerExport } from '../../product/crawlerExport';
import { buildCrawlerEvidenceBundle } from '../../product/crawlerEvidenceBundle';
import { portablePilotReceipt } from '../../product/crawlerPilotReceipt';
import {
  bindPilotSnapshot, requireCurrentPilotSnapshot, type PilotSnapshotWitness,
} from './crawlerPilotContinuity';
import CrawlerResearchAtlasPanel from './CrawlerResearchAtlasPanel';
import CrawlerSourceLibrary, { type CrawlPassageSelection } from './CrawlerSourceLibrary';
import DragonKnowledgePanel from './DragonKnowledgePanel';
import {
  derivePilotGates, EMPTY_PILOT_FORM, PILOT_STAGES, preparePilotCreate,
  previewPilotScope, type PilotForm, type PilotStage,
} from './crawlerPilotFlow';
import s, { colors as C } from './CrawlerWorkspace.styles';

type Pending =
  | { kind: 'create'; body: CrawlCreate }
  | { kind: 'run'; id: string; body: CrawlCommand & { max_steps: number } }
  | { kind: 'control'; id: string; body: CrawlCommand & { action: 'pause' | 'resume' } };

const field = {
  backgroundColor: C.bg, borderWidth: 1, borderColor: C.edge,
  borderRadius: 9, padding: 12, color: C.text, fontSize: 15,
  minHeight: 46, textAlignVertical: 'top' as const,
};
const tiny = { fontSize: 13, color: C.muted, lineHeight: 20 };
const section = { paddingVertical: 14, gap: 12 };
const label = (v: string) => v.replaceAll('_', ' ');

function Button({ title, onPress, disabled = false, primary = false, testID }: {
  title: string; onPress: () => void; disabled?: boolean; primary?: boolean; testID?: string;
}) {
  return <TouchableOpacity
    testID={testID} accessibilityRole="button" accessibilityLabel={title}
    accessibilityState={{ disabled }} disabled={disabled} onPress={onPress}
    style={[s.button, primary && { backgroundColor: '#374272' }, disabled && s.disabled]}>
    <Text style={s.buttonText}>{title}</Text>
  </TouchableOpacity>;
}

function Metric({ name, value, detail }: {
  name: string; value: string; detail: string;
}) {
  return <View style={{ flexGrow: 1, flexBasis: 138, minWidth: 0,
    backgroundColor: C.bg, borderRadius: 10, padding: 14, gap: 7 }}>
    <Text style={tiny}>{name}</Text>
    <Text style={{ color: C.text, fontSize: 23, fontWeight: '800' }}>{value}</Text>
    <Text style={tiny}>{detail}</Text>
  </View>;
}

function Heading({ title, help }: { title: string; help: string }) {
  return <View style={{ gap: 6 }}>
    <Text style={s.heading} accessibilityRole="header">{title}</Text>
    <Text style={s.small}>{help}</Text>
  </View>;
}

function PilotContent() {
  const router = useRouter();
  const { width } = useWindowDimensions();
  const auth = useStudioAuth();
  const canWrite = auth.role === 'editor' || auth.role === 'admin';
  const [stage, setStage] = useState<PilotStage>('scope');
  const [form, setForm] = useState<PilotForm>({ ...EMPTY_PILOT_FORM });
  const [readiness, setReadiness] = useState<CrawlerReadiness | null>(null);
  const [sessions, setSessions] = useState<CrawlSession[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [session, setSession] = useState<CrawlSession | null>(null);
  const [sources, setSources] = useState<CapturedSource[]>([]);
  // Re-key the source-library component on every authority refresh. It owns
  // separately cached full text, search hits and review selections that a
  // mere sources=[] prop update would NOT clear.
  const [sourceViewEpoch, setSourceViewEpoch] = useState(0);
  const [sourceCursor, setSourceCursor] = useState<string | null>(null);
  const [reviewDraft, setReviewDraft] = useState<CrawlPassageSelection | null>(null);
  const [atlas, setAtlas] = useState<CrawlAtlasReport | null>(null);
  const [atlasWitness, setAtlasWitness] = useState<PilotSnapshotWitness | null>(null);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [exporting, setExporting] = useState(false);
  const [bundling, setBundling] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [scopePreview, setScopePreview] = useState(false);
  const account = useRef(getAuthToken());
  const sessionRef = useRef<CrawlSession | null>(null);
  const alive = useRef(true);
  const reads = useRef<AbortController | null>(null);
  const catalogueRead = useRef<AbortController | null>(null);
  const mutationAbort = useRef<AbortController | null>(null);
  const pending = useRef<Pending | null>(null);
  const lock = useRef(false);
  const preflightLock = useRef(false);
  const exportLock = useRef(false);
  const bundleLock = useRef(false);
  const bundleAbort = useRef<AbortController | null>(null);
  const shareLock = useRef(false);
  const shareAbort = useRef<AbortController | null>(null);
  const epoch = useRef(0);

  const fresh = (signal?: AbortSignal, original = account.current) =>
    alive.current && !signal?.aborted && getAuthToken() === original;

  const update = useCallback((value: CrawlSession) => {
    const before = sessionRef.current;
    sessionRef.current = value;
    setSession(value);
    setSessions(rows => [
      value,
      ...rows.filter(row => row.session_id !== value.session_id),
    ].slice(0, 128));
    if (before && (before.session_id !== value.session_id ||
      before.version !== value.version ||
      before.consent_current !== value.consent_current ||
      before.status !== value.status)) {
      // Revoked consent, revision and owner/session changes invalidate any
      // share already waiting on a server re-read. No stale receipt leaves.
      shareAbort.current?.abort(); bundleAbort.current?.abort();
      setSourceViewEpoch(value => value + 1);
      setAtlas(null);
      setAtlasWitness(null);
      setReviewDraft(null);
    }
  }, []);

  const reload = useCallback(async (id: string, keepStage = true) => {
    reads.current?.abort();
    const abort = new AbortController(); reads.current = abort;
    const token = account.current;
    // Unverified evidence is not retained while source authorization is
    // checked. Session titles/counters are separately preserved only after a
    // successful authenticated session read.
    shareAbort.current?.abort(); bundleAbort.current?.abort();
    setSourceViewEpoch(value => value + 1);
    setAtlas(null); setAtlasWitness(null); setReviewDraft(null);
    setSources([]); setSourceCursor(null);
    try {
      // A denied or unavailable source-library request must not hide the
      // authoritative session revision, counters or revoked consent. First
      // reconcile the session, then independently attempt source inventory.
      const current = await getCrawl(id, abort.signal);
      if (!fresh(abort.signal, token) || sessionRef.current?.session_id !== id) return;
      update(current);
      setSources([]); setSourceCursor(null);
      if (!keepStage) setStage('capture');
      try {
        const page = await listCrawlSources(id, undefined, abort.signal);
        if (!fresh(abort.signal, token) || sessionRef.current?.session_id !== id) return;
        setSources(page.sources);
        setSourceCursor(page.next_cursor);
        setError('');
        setNotice('Session revision and current source inventory were reconciled.');
      } catch {
        if (fresh(abort.signal, token)) {
          setAtlas(null); setAtlasWitness(null); setReviewDraft(null);
          setError('The session is current, but retained source rights or inventory could not be verified. Evidence was cleared; retry after checking authorization.');
        }
      }
    } catch {
      if (fresh(abort.signal, token) && sessionRef.current?.session_id === id) {
        // A refused owner read is not permission to keep showing previous
        // mission metadata, source content or a cached Atlas qualification.
        // Durable server state remains available through a fresh catalogue.
        sessionRef.current = null;
        setSession(null);
        setSessions([]);
        setNextCursor(null);
        setReadiness(null);
        setSources([]); setSourceCursor(null); setReviewDraft(null);
        setAtlas(null); setAtlasWitness(null);
        setError('This owned session or its current permissions could not be verified. Cached session metadata and evidence were cleared. Refresh authenticated admission before continuing.');
      }
    } finally {
      if (reads.current === abort) reads.current = null;
    }
  }, [update]);

  const overview = useCallback(async (more = false) => {
    catalogueRead.current?.abort();
    const abort = new AbortController(); catalogueRead.current = abort;
    const token = account.current;
    setLoaded(false);
    try {
      const [service, catalog] = await Promise.all([
        getCrawlerReadiness(abort.signal),
        listCrawls(more ? nextCursor || undefined : undefined, abort.signal),
      ]);
      if (!fresh(abort.signal, token)) return;
      setReadiness(service);
      setSessions(rows => {
        const joined = more ? rows.concat(catalog.sessions) : catalog.sessions;
        const found = new Set<string>();
        return joined.filter(row => {
          if (found.has(row.session_id)) return false;
          found.add(row.session_id);
          return true;
        }).slice(0, 128);
      });
      setNextCursor(catalog.next_cursor);
      setError('');
    } catch {
      if (fresh(abort.signal, token)) {
        setReadiness(null);
        setError('Crawler readiness or session catalogue could not be verified. Check setup and your sign-in.');
      }
    } finally {
      if (fresh(abort.signal, token)) setLoaded(true);
      if (catalogueRead.current === abort) catalogueRead.current = null;
    }
  }, [nextCursor]);

  useEffect(() => {
    alive.current = true;
    void overview();
    const timer = setInterval(() => {
      const current = getAuthToken();
      if (current === account.current) return;
      account.current = current;
      epoch.current++;
      reads.current?.abort(); catalogueRead.current?.abort();
      mutationAbort.current?.abort(); shareAbort.current?.abort(); bundleAbort.current?.abort(); pending.current = null;
      preflightLock.current = false; exportLock.current = false; bundleLock.current = false; shareLock.current = false;
      sessionRef.current = null;
      setSession(null); setSources([]); setSessions([]); setNextCursor(null);
      setSourceCursor(null); setReviewDraft(null); setAtlas(null); setAtlasWitness(null);
      setSharing(false); setBundling(false);
      setReadiness(null); setStage('scope'); setBusy(''); setLoaded(false);
      setForm({ ...EMPTY_PILOT_FORM }); setScopePreview(false);
      setError('Your sign-in changed. Refresh the pilot to load the new account scope.');
    }, 1000);
    return () => {
      alive.current = false;
      clearInterval(timer);
      epoch.current++;
      reads.current?.abort(); catalogueRead.current?.abort();
      mutationAbort.current?.abort(); shareAbort.current?.abort(); bundleAbort.current?.abort();
    };
    // Start once per signed-in screen lifetime; refresh is explicit thereafter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const select = (row: CrawlSession) => {
    if (lock.current || preflightLock.current || busy || pending.current || shareLock.current) return;
    reads.current?.abort();
    shareAbort.current?.abort(); bundleAbort.current?.abort();
    setSourceViewEpoch(value => value + 1);
    sessionRef.current = row;
    setSession(row); setSources([]); setSourceCursor(null);
    setAtlas(null); setAtlasWitness(null);
    setReviewDraft(null); setError(''); setNotice('');
    setStage('capture');
    void reload(row.session_id);
  };

  const submitPending = async () => {
    const command = pending.current;
    if (!command || lock.current || !fresh()) return;
    lock.current = true;
    const abort = new AbortController(); mutationAbort.current = abort;
    const token = account.current; const rev = epoch.current;
    setBusy(command.kind); setError(''); setNotice('');
    try {
      let result: CrawlSession;
      if (command.kind === 'create') result = await createCrawl(command.body, abort.signal);
      else if (command.kind === 'run') result = await runCrawl(command.id, command.body, abort.signal);
      else result = await controlCrawl(command.id, command.body, abort.signal);
      if (!fresh(abort.signal, token) || rev !== epoch.current) return;
      if (command.kind === 'create') {
        update(result); setSources([]); setSourceCursor(null);
        setReviewDraft(null); setAtlas(null); setAtlasWitness(null); setStage('capture');
        setForm(old => ({ ...old, consent: false, rights: false }));
      } else if (sessionRef.current?.session_id === result.session_id) update(result);
      pending.current = null;
      setNotice(command.kind === 'create'
        ? 'Owner-scoped mission created. No network request is launched until you explicitly run a bounded slice.'
        : 'Canonical server confirmed this operation. Recheck counters and source evidence.');
      if (command.kind !== 'create' && sessionRef.current?.session_id === result.session_id) {
        void reload(result.session_id);
      }
    } catch {
      if (fresh(abort.signal, token) && rev === epoch.current) {
        setError('This command has no verified success receipt. Inspect the authoritative session; use Retry same command only if needed. A new idempotency key would risk duplicate effects.');
      }
    } finally {
      if (fresh(undefined, token) && rev === epoch.current) setBusy('');
      if (mutationAbort.current === abort) mutationAbort.current = null;
      lock.current = false;
    }
  };

  const create = () => {
    if (!canWrite || readiness?.available !== true || pending.current || lock.current || preflightLock.current || shareLock.current) {
      setError('An editor account, configured crawler and fully resolved previous command are required.');
      return;
    }
    try {
      const body = preparePilotCreate(form, crawlRequestKey('pilot-create'));
      pending.current = { kind: 'create', body };
      void submitPending();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Capture scope is invalid.');
    }
  };

  const execute = async (kind: 'run' | 'pause' | 'resume') => {
    const current = sessionRef.current;
    if (!current || !current.consent_current || !canWrite
      || readiness?.available !== true || pending.current || lock.current || preflightLock.current || shareLock.current) {
      setError('Resolve consent, admission, account authority or the previous command before continuing.');
      return;
    }
    preflightLock.current = true;
    setBusy('checking current revision');
    try {
      const latest = await getCrawl(current.session_id);
      if (!fresh() || sessionRef.current?.session_id !== latest.session_id) return;
      update(latest);
      if (kind === 'run') {
        if (latest.capabilities?.can_run !== true) {
          setError('Canonical crawler does not currently allow this bounded slice.');
          return;
        }
        pending.current = { kind: 'run', id: latest.session_id, body: {
          idempotency_key: crawlRequestKey('pilot-run'),
          expected_version: latest.version,
          max_steps: 4,
        }};
      } else {
        const can = kind === 'pause' ? latest.capabilities?.can_pause : latest.capabilities?.can_resume;
        if (can !== true) {
          setError('Canonical crawler does not allow the requested state transition.');
          return;
        }
        pending.current = { kind: 'control', id: latest.session_id, body: {
          idempotency_key: crawlRequestKey('pilot-' + kind),
          expected_version: latest.version, action: kind,
        }};
      }
      setBusy('');
      await submitPending();
    } catch {
      if (fresh()) setError('Could not read the latest canonical revision. No new crawler command was submitted.');
    } finally {
      preflightLock.current = false;
      if (fresh()) setBusy('');
    }
  };

  const exportSelected = async (item: CapturedSource, format: 'json' | 'markdown') => {
    const current = sessionRef.current;
    if (!current || exporting || exportLock.current || !fresh()) return;
    exportLock.current = true;
    const token = account.current; setExporting(true); setError('');
    const abort = new AbortController();
    try {
      const file = await exportCrawlSource(current.session_id, item.source_id, format, abort.signal);
      if (!fresh(abort.signal, token) || sessionRef.current?.session_id !== current.session_id) return;
      await saveCrawlerExport(file);
      if (fresh(undefined, token)) setNotice('The selected source export was handed to your device; the source remains subject to its rights and use policy.');
    } catch {
      if (fresh(undefined, token)) setError('The authorized source export could not be completed. Refresh source policy and try again.');
    } finally {
      exportLock.current = false;
      if (fresh(undefined, token)) setExporting(false);
    }
  };


  const exportEvidenceBundle = async (includeBodies: boolean) => {
    const current = sessionRef.current;
    if (!current || !current.consent_current || !fresh() || !sources.length
      || bundleLock.current || exportLock.current || shareLock.current
      || lock.current || preflightLock.current || pending.current) return;
    bundleLock.current = true;
    const abort = new AbortController(); bundleAbort.current = abort;
    const token = account.current, sourceEpoch = epoch.current;
    const identity = current.session_id, originalVersion = current.version;
    setBundling(true); setError(''); setNotice('');
    try {
      const packet = await buildCrawlerEvidenceBundle({
        session: current, sourceIds: sources.slice(0, 8).map(row => row.source_id),
        includeBodies, signal: abort.signal,
        checkScope: () => fresh(abort.signal, token) && epoch.current === sourceEpoch
          && sessionRef.current?.session_id === identity
          && sessionRef.current?.version === originalVersion
          && sessionRef.current?.consent_current === true,
        getSession: getCrawl, getSource: getCrawlSource,
        exportSource: exportCrawlSource,
        sha256: text => digestStringAsync(CryptoDigestAlgorithm.SHA256, text),
      });
      if (!fresh(abort.signal, token) || epoch.current !== sourceEpoch) return;
      await saveCrawlerExport(packet);
      if (fresh(undefined, token) && epoch.current === sourceEpoch) {
        setNotice(includeBodies
          ? 'Authorized source bodies were exported after current rights checks (up to 8 sources). Revalidate rights and freshness before downstream use.'
          : 'Metadata-only provenance bundle exported without source bodies, URLs or search queries.');
      }
    } catch {
      if (fresh(undefined, token) && epoch.current === sourceEpoch) {
        setError('Evidence bundle was refused or interrupted. No partial bundle was shared. Recheck current consent, source-use policy, revision and export size.');
      }
    } finally {
      if (bundleAbort.current === abort) bundleAbort.current = null;
      bundleLock.current = false;
      if (fresh(undefined, token) && epoch.current === sourceEpoch) setBundling(false);
    }
  };

  const moreSources = async () => {
    const current = sessionRef.current;
    if (!current || !sourceCursor || busy || !fresh()) return;
    reads.current?.abort();
    const abort = new AbortController(); reads.current = abort;
    const token = account.current;
    try {
      const page = await listCrawlSources(current.session_id, sourceCursor, abort.signal);
      if (!fresh(abort.signal, token) || sessionRef.current?.session_id !== current.session_id) return;
      setSources(old => {
        const ids = new Set(old.map(row => row.source_id));
        return [...old, ...page.sources.filter(row => !ids.has(row.source_id))].slice(0, 64);
      });
      setSourceCursor(page.next_cursor);
    } catch {
      if (fresh(abort.signal, token)) setError('Could not load the next authorized source page.');
    }
  };

  const sharePilotReceipt = async () => {
    const current = sessionRef.current;
    const report = atlas;
    const witness = atlasWitness;
    if (!current || !report?.pilot_qualification || !witness || !fresh()
      || shareLock.current || lock.current || preflightLock.current || pending.current) return;
    shareLock.current = true;
    const abort = new AbortController();
    shareAbort.current = abort;
    const token = account.current;
    const startingEpoch = epoch.current;
    setSharing(true); setError('');
    try {
      // This is an authenticated, read-only CAS witness. It does NOT
      // authorize new source use, remote freshness, publication or training.
      const latest = await getCrawl(current.session_id, abort.signal);
      if (!fresh(abort.signal, token) || epoch.current !== startingEpoch ||
        sessionRef.current?.session_id !== current.session_id) return;
      requireCurrentPilotSnapshot(witness, sessionRef.current, latest, report);
      const message = portablePilotReceipt(report);
      if (!fresh(abort.signal, token) || epoch.current !== startingEpoch) return;
      await Share.share({ title: 'Dragon source-only pilot receipt', message });
      if (fresh(undefined, token) && epoch.current === startingEpoch) {
        setNotice('The historical, metadata-only snapshot was handed to the share interface. No current source-use or product release permission was granted.');
      }
    } catch {
      if (fresh(undefined, token) && epoch.current === startingEpoch) {
        setAtlas(null); setAtlasWitness(null);
        setError('The receipt was not shared. The current owned session or its revision could not be reverified. Reopen Research Atlas and inspect a fresh policy-bound snapshot.');
      }
    } finally {
      shareLock.current = false;
      if (shareAbort.current === abort) shareAbort.current = null;
      if (fresh(undefined, token) && epoch.current === startingEpoch) setSharing(false);
    }
  };

  const gates = derivePilotGates({ readiness, session, sources, atlas, canWrite });
  const mayWrite = canWrite && readiness?.available === true && session?.consent_current === true;
  const pilot = atlas?.pilot_qualification;
  let preview: ReturnType<typeof previewPilotScope> | null = null;
  let previewError = '';
  if (scopePreview) {
    try { preview = previewPilotScope(form.seedText); }
    catch (exc) { previewError = exc instanceof Error ? exc.message : 'The source list is invalid.'; }
  }
  const setField = <K extends keyof PilotForm,>(key: K, value: PilotForm[K]) => {
    setForm(old => ({ ...old, [key]: value }));
    setScopePreview(false);
  };

  return <SafeAreaView style={s.safe}>
    <ScrollView contentContainerStyle={[s.page, { maxWidth: 1350 }]}
      keyboardShouldPersistTaps="handled" testID="dragon-crawler-pilot">
      <View style={s.row}>
        <View style={[s.grow, width < 700 && { flexBasis: '100%' }]}>
          <Text style={s.eyebrow}>DRAGON · RELEASE PROTOTYPE</Text>
          <Text style={s.title} accessibilityRole="header">Your research mission</Text>
          <Text style={s.subtitle}>Public-source capture, evidence custody and guided research in one authenticated workflow. No content is automatically trusted or sent to training.</Text>
        </View>
        <Button title="Advanced crawler" onPress={() => router.push('/crawler' as never)} />
        <Button title="Setup" onPress={() => router.push('/setup' as never)} />
      </View>

      <View style={s.card}>
        <Heading title="Service and account readiness" help="A first-install user must be able to see why the service is unavailable without receiving a false green status." />
        <View style={s.row}>
          <Text style={[s.message, s.grow]}>{readiness
            ? readiness.available ? 'Configured crawler admission is reachable.' : readiness.message
            : loaded ? 'Readiness has not been confirmed.' : 'Checking authenticated application readiness…'}</Text>
          <Button title="Refresh admission" onPress={() => { void overview(); if (sessionRef.current) void reload(sessionRef.current.session_id); }} />
        </View>
        {!canWrite && <Text style={s.error}>Your current role is read-only. An editor or administrator must authorize new capture or resume work.</Text>}
        {readiness?.action && !readiness.available && <Text style={s.small}>{readiness.action}</Text>}
      </View>

      {!!error && <View style={s.card} accessibilityRole="alert">
        <Text style={s.error}>{error}</Text>
        <View style={s.row}>
          {pending.current && <Button title="Retry the same command" disabled={!!busy}
            onPress={() => void submitPending()} />}
          <Button title="Refresh canonical state" onPress={() =>
            sessionRef.current ? void reload(sessionRef.current.session_id) : void overview()} />
          <Button title="Dismiss" onPress={() => setError('')} />
        </View>
        {pending.current && <Text style={s.small}>Retry retains the original idempotency key and expected revision. Do not invent a new command until its outcome is reconciled.</Text>}
      </View>}
      {!!notice && <Text accessibilityLiveRegion="polite" style={s.small}>{notice}</Text>}
      {!!busy && <View style={s.row}><ActivityIndicator color={C.accent} /><Text style={s.small}>Verifying {label(busy)}…</Text></View>}

      <View style={s.card}>
        <Heading title="Six stages, one source of truth" help="Choose a stage; every capability uses the same authenticated crawler session. Production release remains independently gated." />
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
          {PILOT_STAGES.map((item, i) =>
            <TouchableOpacity key={item.id} testID={'pilot-stage-' + item.id}
              accessibilityRole="button" accessibilityLabel={'Stage ' + (i + 1) + ': ' + item.label}
              accessibilityState={{ selected: stage === item.id }}
              onPress={() => { setStage(item.id); setError(''); }}
              style={[s.button, stage === item.id && { backgroundColor: '#34405e', borderColor: C.accent }]}>
              <Text style={s.buttonText}>{i + 1}. {item.label}</Text>
            </TouchableOpacity>)}
        </View>
      </View>

      {stage === 'scope' && <View style={s.card}>
        <Heading title="1. Define an authorized scope" help="This wizard defaults to a small, conservative crawl. Only a trusted backend can decide whether DNS, robots, rights and network admission permit requests." />
        <Text style={s.label}>Mission title</Text>
        <TextInput testID="pilot-title" accessibilityLabel="Mission title" style={field}
          value={form.title} maxLength={160} onChangeText={v => setField('title', v)} />
        <Text style={s.label}>Public HTTPS URLs, one per line</Text>
        <TextInput testID="pilot-seeds" accessibilityLabel="Seed URLs"
          value={form.seedText} onChangeText={v => setField('seedText', v)}
          autoCapitalize="none" autoCorrect={false} maxLength={32768}
          multiline style={[field, { minHeight: 130 }]}
          placeholder="https://docs.example.org/start" placeholderTextColor={C.muted} />
        <Text style={s.label}>Research topics (optional)</Text>
        <TextInput accessibilityLabel="Research topics" style={field}
          value={form.topicText} maxLength={1280} onChangeText={v => setField('topicText', v)}
          autoCapitalize="none" placeholder="gameplay, mechanics, accessibility" placeholderTextColor={C.muted} />
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>
          {([
            ['Requests', 'maxRequests', 128], ['Documents', 'maxDocuments', 64],
            ['MiB total', 'maxMib', 32], ['Link depth', 'maxDepth', 3],
          ] as const).map(([name, key, ceiling]) =>
            <View key={key} style={{ flexGrow: 1, flexBasis: 115, minWidth: 90, gap: 7 }}>
              <Text style={s.small}>{name} · max {ceiling}</Text>
              <TextInput style={field} keyboardType="number-pad"
                accessibilityLabel={'Maximum ' + name}
                value={form[key]} onChangeText={v => setField(key, v)}
                maxLength={5} />
            </View>)}
        </View>
        <View style={s.row}>
          <Switch accessibilityLabel="Discover sitemaps from robots" value={form.discoverSitemaps}
            onValueChange={v => setField('discoverSitemaps', v)} />
          <Text style={[s.message, s.grow]}>Include bounded same-origin sitemap discovery.</Text>
        </View>
        <View style={s.row}>
          <Switch accessibilityLabel="Use host-balanced queue" value={form.balanceHosts}
            onValueChange={v => setField('balanceHosts', v)} />
          <Text style={[s.message, s.grow]}>Schedule fairly across the admitted host set.</Text>
        </View>
        <View style={s.row}>
          <Switch accessibilityLabel="Authorize bounded capture" value={form.consent}
            onValueChange={v => setField('consent', v)} />
          <Text style={[s.message, s.grow]}>I explicitly authorize these finite requests and their temporary source retention.</Text>
        </View>
        <View style={s.row}>
          <Switch accessibilityLabel="Acknowledge source rights" value={form.rights}
            onValueChange={v => setField('rights', v)} />
          <Text style={[s.message, s.grow]}>I have the necessary rights to capture these URLs; publication and training are separate permissions.</Text>
        </View>
        <View style={s.row}>
          <Button title="Preview host scope" onPress={() => setScopePreview(true)} />
          <Button testID="pilot-create" title="Create bounded mission" primary
            disabled={!canWrite || readiness?.available !== true || !!busy || !!pending.current
              || !form.consent || !form.rights}
            onPress={create} />
        </View>
        {scopePreview && (preview
          ? <View style={section}><Text style={s.label}>{preview.seeds.length} URLs · {preview.requestHostCount} distinct hosts</Text>
              {preview.hosts.map(host => <Text key={host} selectable style={tiny}>{host}</Text>)}
              <Text style={s.small}>The preview is not an SSRF, DNS, consent or robots certificate.</Text>
            </View>
          : <Text style={s.error}>{previewError}</Text>)}
        <View style={section}>
          <Text style={s.heading}>Resume an existing owned mission</Text>
          {!sessions.length && <Text style={s.small}>No sessions were returned. You can create one after setup or use Refresh admission.</Text>}
          {sessions.map(row => <TouchableOpacity key={row.session_id} accessibilityRole="button"
            accessibilityLabel={'Open mission ' + row.title}
            style={[s.check, session?.session_id === row.session_id && { borderLeftWidth: 3, borderColor: C.accent, paddingLeft: 10 }]}
            onPress={() => select(row)}>
            <Text style={s.label}>{row.title}</Text>
            <Text style={s.small}>{label(row.status)} · {row.counters.documents} sources · {row.counters.requests} requests · revision {row.version}</Text>
          </TouchableOpacity>)}
          {nextCursor && <Button title="Load more owned missions" disabled={!!busy}
            onPress={() => void overview(true)} />}
        </View>
      </View>}

      {stage === 'capture' && <View style={s.card}>
        <Heading title="2. Execute a bounded crawl" help="One button performs at most four canonical crawler steps. The server owns leases, checkpoint commits, host policy and uncertain-byte reservations." />
        {!session
          ? <Text style={s.error}>No owned session selected. Start with Scope & consent.</Text>
          : <>
            <Text style={s.heading}>{session.title} · {label(session.status)}</Text>
            <Text style={s.small}>Revision {session.version} · last updated {new Date(session.updated_at).toLocaleString()} · consent {session.consent_current ? 'current' : 'expired'}</Text>
            <View style={s.row}>
              <Metric name="Committed requests" value={String(session.counters.requests)}
                detail={'Limit ' + session.limits.max_requests} />
              <Metric name="Captured documents" value={String(session.counters.documents)}
                detail={'Limit ' + session.limits.max_documents} />
              <Metric name="Downloaded MiB" value={(session.counters.bytes / 1048576).toFixed(2)}
                detail={'Budget ' + (session.limits.max_total_bytes / 1048576).toFixed(1)} />
              <Metric name="Frontier queue" value={String(session.frontier_count)} detail="Pending eligible URLs" />
            </View>
            {typeof session.counters.reserved_bytes === 'number'
              && session.counters.reserved_bytes > 0
              && <Text style={s.error}>Uncertain dispatch capacity retained: {session.counters.reserved_bytes} bytes. Refresh before new commands; never silently refund.</Text>}
            {session.worker?.active && <Text style={s.small}>The canonical worker is active. Do not submit a competing physical worker.</Text>}
            <View style={s.row}>
              <Button title="Run 4-step slice" primary
                disabled={!mayWrite || !!busy || !!pending.current || session.capabilities?.can_run !== true}
                onPress={() => void execute('run')} />
              <Button title="Pause" disabled={!mayWrite || !!busy || !!pending.current || session.capabilities?.can_pause !== true}
                onPress={() => void execute('pause')} />
              <Button title="Resume" disabled={!mayWrite || !!busy || !!pending.current || session.capabilities?.can_resume !== true}
                onPress={() => void execute('resume')} />
              <Button title="Reconcile snapshot" disabled={!!busy}
                onPress={() => void reload(session.session_id)} />
            </View>
            {session.error?.message && <Text style={s.error}>{session.error.message}</Text>}
            {!session.consent_current && <Text style={s.error}>Consent is no longer valid. No new network operation is permitted; retained evidence may also be unavailable.</Text>}
            <Text style={s.small}>Need advanced automation, cancellation, permanent deletion or detailed worker diagnostics? Use Advanced crawler; this short mission intentionally does not bypass those existing controls.</Text>
            <View style={s.row}>
              <Button title="Open full operations" onPress={() =>
                router.push(('/crawler?session=' + encodeURIComponent(session.session_id)) as never)} />
              <Button title="Review captured sources" onPress={() => setStage('sources')} />
            </View>
          </>}
      </View>}

      {stage === 'sources' && <View style={section}>
        <View style={s.card}>
          <Heading title="3. Inspect retained evidence" help="Source bodies are untrusted external material. Rights, freshness, hashes and current policy must be rechecked before viewing, using or exporting each source." />
          {!session
            ? <Text style={s.error}>Select an owned capture session to inspect sources.</Text>
            : <View style={s.row}>
              <Text style={s.small}>{session.source_count} recorded captures · {sources.length} loaded in this session</Text>
              <Button title="Refresh current source policy" onPress={() => void reload(session.session_id)} />
            </View>}
        </View>
        {session && <View style={s.card}>
          <Heading title="Audited multi-source evidence bundle" help="Export up to 8 owned sources. Every source and the session are re-read, and content mode requires the server's per-source rights-checked export. A revision or consent change refuses the entire bundle." />
          <Text style={s.small}>Sources loaded: {sources.length}. The first 8 authorized sources will be included. This is not permission to publish, train, or claim remote freshness.</Text>
          <View style={s.row}>
            <Button testID="dragon-export-metadata-bundle" title={bundling ? 'Verifying sources…' : 'Export provenance only'}
              disabled={bundling || exporting || !session.consent_current || sources.length === 0 || !!busy}
              onPress={() => { void exportEvidenceBundle(false); }} />
            <Button testID="dragon-export-authorized-bundle" title={bundling ? 'Verifying rights…' : 'Export authorized source copies'}
              disabled={bundling || exporting || !session.consent_current || sources.length === 0 || !!busy}
              onPress={() => { void exportEvidenceBundle(true); }} />
          </View>
          {bundling && <ActivityIndicator color={C.accent} />}
        </View>}
        {session && <CrawlerSourceLibrary key={session.session_id + ':' + sourceViewEpoch} session={session}
          sources={sources} more={!!sourceCursor} busy={!!busy || exporting}
          canWrite={canWrite} loadMore={() => void moreSources()}
          refresh={() => void reload(session.session_id)}
          onReview={selected => { setReviewDraft(selected); setStage('review'); }}
          exportSource={(item, format) => { void exportSelected(item, format); }}
          policyChanged={value => {
            if (sessionRef.current?.session_id !== value.session.session_id) return;
            if (value.session.version < sessionRef.current.version) {
              void reload(value.session.session_id); return;
            }
            shareAbort.current?.abort(); bundleAbort.current?.abort();
            setSourceViewEpoch(epoch => epoch + 1);
            update(value.session); setAtlas(null); setAtlasWitness(null); setReviewDraft(null);
            setSources(rows => rows.map(row =>
              row.source_id === value.source.source_id ? value.source : row));
          }} />}
      </View>}

      {stage === 'research' && <View style={section}>
        <View style={s.card}>
          <Heading title="4. Source-bound research" help="The existing Atlas assembles an immutable, policy-checked evidence graph, citation manifest, forensic review queue and release-pilot receipt. No new website is fetched here." />
          {!session && <Text style={s.error}>Select and capture an owned source first.</Text>}
          {session && !session.consent_current && <Text style={s.error}>Consent has expired. Atlas cannot be run until the canonical authority permits source use.</Text>}
        </View>
        {session && <CrawlerResearchAtlasPanel key={session.session_id}
          session={session} onReport={(value, requestedVersion) => {
            const current = sessionRef.current;
            if (!fresh() || current?.session_id !== session.session_id ||
              (value !== null && current.version !== requestedVersion)) return;
            if (!value) { setAtlas(null); setAtlasWitness(null); return; }
            try {
              const witness = bindPilotSnapshot(current, value, requestedVersion);
              setAtlasWitness(witness);
              setAtlas(value);
            } catch {
              setAtlas(null); setAtlasWitness(null);
              setError('Research receipt has no current bound owner/session revision; reinspect the authorized evidence.');
            }
          }} />}
      </View>}

      {stage === 'review' && <View style={section}>
        <View style={s.card}>
          <Heading title="5. Human verification and design reference review" help="Select a preserved source passage in the library. This stage uses the existing reviewed-knowledge subsystem and never automatically endorses extracted instructions or rights claims." />
          {reviewDraft
            ? <Text style={s.small}>Selected source: {reviewDraft.title} · preserved span {reviewDraft.start}–{reviewDraft.end}</Text>
            : <Text style={s.small}>No source passage has been selected. Open Source library, select a current passage, then choose Review.</Text>}
          <Button title="Choose source passage" onPress={() => setStage('sources')} />
        </View>
        <DragonKnowledgePanel key={session?.session_id || 'none'} visible
          canWrite={canWrite} draft={reviewDraft}
          clearDraft={() => setReviewDraft(null)} />
      </View>}

      {stage === 'receipt' && <View style={s.card}>
        <Heading title="6. Pilot evidence and release gates" help="A source-only pilot can be useful to signed-in users without being certified for general release. Production release requires separate exact-head and device evidence." />
        <View style={s.row}>
          <Metric name="Pilot state" value={pilot ? label(pilot.pilot_status) : 'No receipt'}
            detail="Human review remains required" />
          <Metric name="Source checks" value={pilot
            ? (pilot.pilot_check_count - pilot.blocked_checks.length) + '/' + pilot.pilot_check_count : '0/10'}
            detail="Not production certification" />
          <Metric name="Release checks" value="0/10" detail="External gates never self-certify" />
        </View>
        {pilot && <Text selectable style={s.small}>Exact Atlas {pilot.atlas_digest} · receipt {pilot.qualification_digest}</Text>}
        <View style={section}>
          <Text style={s.heading}>Release readiness matrix</Text>
          {gates.map(gate => <View key={gate.id} style={s.check}>
            <View style={s.row}>
              <Text style={[s.label, s.grow]}>{gate.title}</Text>
              <Text style={gate.status === 'ready' ? { color: C.green } : s.error}>{label(gate.status)}</Text>
            </View>
            <Text style={s.small}>{gate.reason}</Text>
          </View>)}
        </View>
        {pilot && <View style={section}>
          <Text style={s.heading}>Operator repairs for this snapshot</Text>
          {pilot.operator_actions.length
            ? pilot.operator_actions.map(code => <Text key={code} style={s.error}>{label(code)}</Text>)
            : <Text style={s.small}>Source-only checks have no outstanding blockers; independent human and release verification remain required.</Text>}
          <Text style={s.small}>All {pilot.external_release_checks.length} external release gates are unqualified by this source-only receipt. Skips, pending runs and historical checks cannot count as green.</Text>
          <Button title={sharing ? "Verifying receipt revision…" : "Share source-only pilot receipt"}
            disabled={sharing || !!busy || !!pending.current || !atlasWitness}
            onPress={() => void sharePilotReceipt()} />
        </View>}
        <View style={s.row}>
          <Button title="Reinspect current Atlas" onPress={() => setStage('research')} />
          <Button title="Go to full crawler operations" onPress={() =>
            router.push('/crawler' as never)} />
        </View>
        <Text style={s.error}>Release authorized: NO. Publishing and model-training permission: NO. This user prototype is subject to deployment, independent security review and first-install acceptance.</Text>
      </View>}

      <View style={s.card}>
        <Heading title="Source-only mission progress" help="These are observations from the active session, not assertions that a feature, factual claim or product has been certified." />
        {gates.map(gate => <View key={gate.id} style={s.row}>
          <Text style={[s.small, s.grow]}>{gate.title}</Text>
          <Text style={gate.status === 'ready' ? { color: C.green } : s.small}>
            {label(gate.status)}
          </Text>
        </View>)}
        <Text style={s.small}>Production release remains blocked until exact-head CI, CodeQL/security, product E2E, independent Windows/WSL2/Docker/native hardware, recovery, rollback, provenance and source-rights review all succeed.</Text>
      </View>
    </ScrollView>
  </SafeAreaView>;
}

export default function CrawlerReleasePrototype() {
  return <StudioLoginGate title="Dragon research pilot" requireAuthenticated>
    <PilotContent />
  </StudioLoginGate>;
}
