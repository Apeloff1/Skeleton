import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, AppState, Platform, SafeAreaView, ScrollView, Share, Switch, Text, TextInput, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import StudioLoginGate, { useStudioAuth } from '../../src/auth/StudioLoginGate';
import { getAuthToken } from '../../src/auth/gameforgeAuth';
import { createCrawl, controlCrawl, crawlRequestKey, eraseCrawl, getCrawlEvents, exportCrawlSource, getCrawl, getCrawlerReadiness, listCrawls, listCrawlSources, runCrawl, type CapturedSource, type CrawlCreate, type CrawlEvent, type CrawlerReadiness, type CrawlSession, type SourceExport } from '../../src/product/crawlerClient';
import { ChatClientError } from '../../src/product/chatErrors';
import s, { colors } from './CrawlerWorkspace.styles';
import CrawlerAutomationPanel from './CrawlerAutomationPanel';
import CrawlerSourceLibrary, { type CrawlPassageSelection } from './CrawlerSourceLibrary';
import DragonKnowledgePanel from './DragonKnowledgePanel';

function bytes(value: number): string { return value < 1024 ? `${value} B` : value < 1048576 ? `${(value / 1024).toFixed(1)} KB` : `${(value / 1048576).toFixed(1)} MB`; }
function label(value: string): string { return value.replaceAll('_', ' '); }
async function saveExport(file: SourceExport): Promise<void> {
  const filename = file.filename.replace(/[^a-zA-Z0-9._-]/g, '-').slice(0, 160) || 'captured-source.json';
  if (Platform.OS === 'web') {
    const url = URL.createObjectURL(new Blob([file.content], { type: file.media_type })); const a = document.createElement('a');
    try { a.href = url; a.download = filename; document.body.appendChild(a); a.click(); } finally { a.remove(); setTimeout(() => URL.revokeObjectURL(url), 5000); } return;
  }
  if (!FileSystem.cacheDirectory || !await Sharing.isAvailableAsync()) { await Share.share({ title: filename, message: file.content }); return; }
  const uri = FileSystem.cacheDirectory + Date.now() + '-' + filename;
  try { await FileSystem.writeAsStringAsync(uri, file.content, { encoding: FileSystem.EncodingType.UTF8 }); await Sharing.shareAsync(uri, { mimeType: file.media_type }); }
  finally { await FileSystem.deleteAsync(uri, { idempotent: true }).catch(() => {}); }
}
function Button({ title, onPress, disabled = false }: { title: string; onPress: () => void; disabled?: boolean }) {
  return <TouchableOpacity accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={[s.button, disabled && s.disabled]}><Text style={s.buttonText}>{title}</Text></TouchableOpacity>;
}
function CrawlerContent() {
  const router = useRouter(); const { width } = useWindowDimensions(); const auth = useStudioAuth();
  const params = useLocalSearchParams<{ session?: string; pane?: string }>();
  const requestedSession = typeof params.session === 'string' && /^[A-Za-z0-9_-]{1,128}$/.test(params.session) ? params.session : null;
  const [pane, setPane] = useState<'capture' | 'review'>(params.pane === 'review' ? 'review' : 'capture');
  const [reviewDraft, setReviewDraft] = useState<CrawlPassageSelection | null>(null);
  const restoredSession = useRef<string | null>(null);
  const scroll = useRef<React.ElementRef<typeof ScrollView>>(null);
  const choosePane = (value: 'capture' | 'review') => { setPane(value); router.setParams({ pane: value }); scroll.current?.scrollTo({ y: 0, animated: false }); };
  useEffect(() => { if (params.pane === 'capture' || params.pane === 'review') setPane(params.pane); }, [params.pane]);
  const [readiness, setReadiness] = useState<CrawlerReadiness | null>(null);
  const [sessions, setSessions] = useState<CrawlSession[]>([]); const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [active, setActive] = useState<CrawlSession | null>(null); const activeRef = useRef<CrawlSession | null>(null);
  const [sources, setSources] = useState<CapturedSource[]>([]); const [sourceCursor, setSourceCursor] = useState<string | null>(null);
  const [events, setEvents] = useState<CrawlEvent[]>([]); const [truncatedEvents, setTruncatedEvents] = useState(false);
  const [title, setTitle] = useState(''); const [seeds, setSeeds] = useState(''); const [topics, setTopics] = useState('');
  const [requests, setRequests] = useState('24'); const [documents, setDocuments] = useState('16'); const [megabytes, setMegabytes] = useState('8'); const [depth, setDepth] = useState('1');
  const [consent, setConsent] = useState(false); const [rights, setRights] = useState(false); const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(''); const [running, setRunning] = useState(false); const [error, setError] = useState(''); const [notice, setNotice] = useState('');
  const [retry, setRetry] = useState<(() => Promise<void>) | null>(null);
  const generation = useRef(0); const requestsRef = useRef(new Set<AbortController>()); const token = useRef(getAuthToken());
  const canWrite = auth.role === 'editor' || auth.role === 'admin';
  const accept = useCallback((value: CrawlSession) => {
    setSessions(rows => { const found = rows.find(row => row.session_id === value.session_id); if (found && found.version > value.version) return rows; return [value, ...rows.filter(row => row.session_id !== value.session_id)].slice(0, 128); });
    if (activeRef.current?.session_id === value.session_id && value.version >= activeRef.current.version) { activeRef.current = value; setActive(value); }
  }, []);
  const perform = useCallback(async (task: (signal: AbortSignal) => Promise<void>) => {
    const current = new AbortController(); const epoch = generation.current; requestsRef.current.add(current);
    try { await task(current.signal); }
    catch (err) { if (!current.signal.aborted && epoch === generation.current) { setError(err instanceof Error ? err.message : 'The crawler request failed.'); if (err instanceof ChatClientError && err.kind === 'authorization') setNotice('Check your account and permissions. Capturing requires an editor account.'); } }
    finally { requestsRef.current.delete(current); }
  }, []);
  const refresh = useCallback(async () => {
    await perform(async signal => {
      const results = await Promise.allSettled([getCrawlerReadiness(signal), listCrawls(undefined, signal)]);
      if (signal.aborted) return;
      if (results[0].status === 'fulfilled') setReadiness(results[0].value);
      if (results[1].status === 'fulfilled') { setSessions(results[1].value.sessions); setNextCursor(results[1].value.next_cursor); }
      else throw results[1].reason;
      if (results[0].status === 'rejected') throw results[0].reason;
    });
  }, [perform]);
  useFocusEffect(useCallback(() => { void refresh(); return () => { generation.current++; requestsRef.current.forEach(row => row.abort()); requestsRef.current.clear(); }; }, [refresh]));
  useEffect(() => { const timer = setInterval(() => { if (token.current !== getAuthToken()) { token.current = getAuthToken(); generation.current++; requestsRef.current.forEach(row => row.abort()); activeRef.current = null; setActive(null); setReadiness(null); setBusy(''); setRunning(false); setSessions([]); setSources([]); setEvents([]); setReviewDraft(null); setSeeds(''); setTopics(''); setConsent(false); setRights(false); setRetry(null); setError('Your account changed. Reopen web capture to load its sources.'); } }, 1000); return () => clearInterval(timer); }, []);
  useEffect(() => {
    if (!active || !(active.automation?.enabled || active.worker?.active || active.worker?.quiescent === false || ['running', 'queued'].includes(active.status))) return;
    let stopped = false; const current = new AbortController(); let timer: ReturnType<typeof setTimeout>;
    const poll = async () => { try { if (!['active', 'unknown'].includes(AppState.currentState)) return; const value = await getCrawl(active.session_id, current.signal); if (!stopped) accept(value); } catch {} finally { if (!stopped) timer = setTimeout(() => void poll(), 3000); } };
    timer = setTimeout(() => void poll(), 3000); return () => { stopped = true; clearTimeout(timer); current.abort(); };
  }, [active?.session_id, active?.status, active?.automation?.enabled, active?.worker?.active, active?.worker?.quiescent, accept]);
  useEffect(() => {
    if (!active) return;
    const current = new AbortController(); const id = active.session_id;
    void getCrawlEvents(id, current.signal).then(page => { if (!current.signal.aborted && activeRef.current?.session_id === id) { setEvents(page.events); setTruncatedEvents(page.history_truncated); } }).catch(() => {});
    return () => current.abort();
  }, [active?.session_id, active?.version]);
  const open = useCallback((row: CrawlSession, preservePane = false) => {
    restoredSession.current = row.session_id; if (!preservePane) setPane('capture'); router.setParams({ session: row.session_id, ...(preservePane ? {} : { pane: 'capture' }) });
    generation.current++; requestsRef.current.forEach(item => item.abort()); activeRef.current = row; setActive(row); setSources([]); setEvents([]); setError(''); setRetry(null); setCreating(false); setRunning(false); setBusy('');
    void perform(async signal => { const [current, page, observed] = await Promise.all([getCrawl(row.session_id, signal), listCrawlSources(row.session_id, undefined, signal), getCrawlerReadiness(signal).catch(() => null)]); if (!signal.aborted && activeRef.current?.session_id === row.session_id) { accept(current); setSources(page.sources); setSourceCursor(page.next_cursor); if (observed) setReadiness(observed); } });
  }, [perform, accept, router]);
  useEffect(() => {
    if (!requestedSession || restoredSession.current === requestedSession) return;
    restoredSession.current = requestedSession;
    void perform(async signal => { const value = await getCrawl(requestedSession, signal); if (!signal.aborted) open(value, true); });
  }, [requestedSession, perform, open]);
  const mutate = async (name: string, operation: (signal: AbortSignal) => Promise<CrawlSession>, isRun = false) => {
    const epoch = generation.current; setError(''); setRetry(null); if (isRun) setRunning(true); else setBusy(name);
    await perform(async signal => {
      try { const value = await operation(signal); if (!signal.aborted && epoch === generation.current) { accept(value); setNotice(isRun ? 'The bounded slice finished. Counters show only committed requests and captures.' : 'The server confirmed this command.'); if (activeRef.current?.session_id === value.session_id) { const page = await listCrawlSources(value.session_id, undefined, signal); if (!signal.aborted) { setSources(page.sources); setSourceCursor(page.next_cursor); } } } }
      catch (err) { if (!signal.aborted && epoch === generation.current && (!(err instanceof ChatClientError) || ['network', 'timeout', 'unavailable'].includes(err.kind))) setRetry(() => () => mutate(name, operation, isRun)); throw err; }
    });
    if (epoch === generation.current) { if (isRun) setRunning(false); else setBusy(''); }
  };
  const create = () => {
    const numeric = [Number(requests), Number(documents), Number(megabytes), Number(depth)];
    if (!numeric.every(Number.isInteger) || numeric[0] < 1 || numeric[0] > 128 || numeric[1] < 1 || numeric[1] > 64 || numeric[2] < 1 || numeric[2] > 32 || numeric[3] < 0 || numeric[3] > 3) { setError('Use requests 1–128, documents 1–64, MB 1–32 and depth 0–3.'); return; }
    const body: CrawlCreate = { idempotency_key: crawlRequestKey('create'), seeds: seeds.split(/\r?\n/).map(item => item.trim()).filter(Boolean), title: title.trim() || undefined, topics: topics.split(',').map(item => item.trim()).filter(Boolean), max_requests: numeric[0], max_documents: numeric[1], max_bytes: numeric[2] * 1048576, max_depth: numeric[3], consent: true, rights_acknowledged: true };
    void mutate('Creating crawl', async signal => { const value = await createCrawl(body, signal); if (!signal.aborted) { activeRef.current = value; setActive(value); setCreating(false); setSeeds(''); setConsent(false); setRights(false); } return value; });
  };
  const control = (action: 'pause' | 'resume' | 'cancel') => {
    if (!active) return;
    const id = active.session_id; const key = crawlRequestKey(action); let attempt = 0;
    const commands: { idempotency_key: string; expected_version: number; action: 'pause' | 'resume' | 'cancel' }[] = [];
    const execute = async (signal: AbortSignal): Promise<CrawlSession> => {
      while (attempt < 3) {
        if (!commands[attempt]) { const current = await getCrawl(id, signal); commands[attempt] = { idempotency_key: key + ':' + attempt, expected_version: current.version, action }; }
        try { return await controlCrawl(id, commands[attempt], signal); }
        catch (err) { if (err instanceof ChatClientError && err.status === 409 && err.code === 'crawler_conflict') { attempt++; continue; } throw err; }
      }
      throw new ChatClientError('The crawl is changing too quickly to confirm this control. Refresh and try again.', { kind: 'conflict', code: 'crawler_conflict' });
    };
    const act = () => void mutate(label(action), execute);
    if (action !== 'cancel') { act(); return; }
    if (Platform.OS === 'web') { if (globalThis.confirm('Cancel this crawl? Captured sources remain available. This session cannot be resumed after cancellation.')) act(); }
    else Alert.alert('Cancel crawl?', 'Captured sources remain available.', [{ text: 'Keep crawl', style: 'cancel' }, { text: 'Cancel crawl', style: 'destructive', onPress: act }]);
  };
  const erase = () => {
    if (!active) return; const id = active.session_id; const body = { idempotency_key: crawlRequestKey('erase'), expected_version: active.version };
    const operation = async () => {
      const epoch = generation.current; setBusy('Erasing sources'); setError(''); setRetry(null);
      await perform(async signal => {
        try { await eraseCrawl(id, body, signal); if (!signal.aborted && epoch === generation.current) { setSessions(rows => rows.filter(row => row.session_id !== id)); activeRef.current = null; setActive(null); setSources([]); setEvents([]); setNotice('The server erased this crawl and its captured content. Exported copies remain outside the app.'); } }
        catch (err) { if (!signal.aborted && epoch === generation.current && (!(err instanceof ChatClientError) || ['network', 'timeout', 'unavailable'].includes(err.kind))) setRetry(() => operation); throw err; }
      });
      if (epoch === generation.current) setBusy('');
    };
    const message = 'Permanently erase this crawl and its captured source text? This also withdraws it from future chat context. Exported copies cannot be recalled.';
    if (Platform.OS === 'web') { if (globalThis.confirm(message)) void operation(); }
    else Alert.alert('Erase captured sources?', message, [{ text: 'Keep sources', style: 'cancel' }, { text: 'Erase', style: 'destructive', onPress: () => void operation() }]);
  };
  const refreshActive = () => { if (!active) { void refresh(); return; } const id = active.session_id; void perform(async signal => { const [value, page] = await Promise.all([getCrawl(id, signal), listCrawlSources(id, undefined, signal)]); if (!signal.aborted && activeRef.current?.session_id === id) { accept(value); setSources(page.sources); setSourceCursor(page.next_cursor); } }); };
  return <SafeAreaView style={s.safe}><ScrollView ref={scroll} contentContainerStyle={[s.page, { maxWidth: 1480 }]} keyboardShouldPersistTaps="handled">
    <View style={s.row}><View style={[s.grow, width < 600 && { flexBasis: '100%', flexGrow: 0, flexShrink: 0 }]}><Text style={s.eyebrow}>DRAGON · WEB KNOWLEDGE</Text><Text style={s.title}>Capture with a clear scope</Text></View><Button title="Setup" onPress={() => router.push('/setup' as never)} /><Button title="AI chat" onPress={() => router.push('/jeeves-chat' as never)} /><Button title="Home" onPress={() => router.push('/product' as never)} /></View>
    <Text style={s.subtitle}>Choose public URLs, authorize a bounded crawl and inspect what was actually captured. Capture does not review a source or train a model.</Text>
    <View style={s.card}><View style={s.row}><Text style={[s.heading, s.grow]}>{readiness ? readiness.available ? 'Capture service ready' : 'Capture needs setup' : 'Readiness not observed'}</Text><Button title="Refresh" onPress={() => { setError(''); void refresh(); refreshActive(); }} /></View><Text style={s.message}>{readiness?.message || 'Check the application and your account to inspect crawler readiness.'}</Text>{!readiness?.available && readiness?.action && <Text style={s.small}>{readiness.action}</Text>}<Text style={s.small}>Live reachability is checked when a request runs. Public host policy, robots rules, limits and consent are enforced by the crawler.</Text>{!canWrite && <Text style={s.error}>Your account can inspect sources. An editor or administrator is required to create or control a crawl.</Text>}</View>
    {!!error && <View style={s.card} accessibilityRole="alert"><Text style={s.error}>{error}</Text><View style={s.row}>{retry && <Button title="Retry the same request" disabled={!!busy || running} onPress={() => void retry()} />}<Button title="Refresh current state" onPress={refreshActive} /><Button title="Dismiss" onPress={() => setError('')} /></View></View>}
    {!!notice && <Text accessibilityLiveRegion="polite" style={s.small}>{notice}</Text>}
    <View style={s.row} accessibilityRole="tablist"><TouchableOpacity accessibilityRole="tab" accessibilityState={{ selected: pane === 'capture' }} onPress={() => choosePane('capture')} style={s.button}><Text style={s.buttonText}>Capture operations</Text></TouchableOpacity><TouchableOpacity accessibilityRole="tab" accessibilityState={{ selected: pane === 'review' }} onPress={() => choosePane('review')} style={s.button}><Text style={s.buttonText}>Review & practice{reviewDraft ? ' · selected passage' : ''}</Text></TouchableOpacity></View>
    <View style={pane === 'capture' ? undefined : { display: 'none' }}>
    <View style={[s.twoColumns, width < 900 && { flexDirection: 'column' }]}><View style={[s.column, s.card, { flexBasis: 280, maxWidth: width > 900 ? 360 : undefined }]}><View style={s.row}><Text style={[s.heading, s.grow]}>Your crawls</Text><Button title="New" disabled={!canWrite || !!busy || running} onPress={() => { setCreating(true); setError(''); }} /></View>
      {!sessions.length && <Text style={s.small}>No captured sessions loaded. Create one after readiness and permissions are confirmed.</Text>}
      {sessions.map(row => <TouchableOpacity key={row.session_id} accessibilityRole="button" accessibilityState={{ selected: active?.session_id === row.session_id }} style={[s.check, active?.session_id === row.session_id && { backgroundColor: '#251f38', padding: 12, borderRadius: 8 }]} onPress={() => open(row)}><Text style={s.label}>{row.title}</Text><Text style={s.small}>{label(row.status)} · {row.counters.documents} captures · {row.counters.requests} requests</Text></TouchableOpacity>)}
      {nextCursor && <Button title="Load more crawls" onPress={() => void perform(async signal => { const page = await listCrawls(nextCursor, signal); if (!signal.aborted) { setSessions(rows => [...rows, ...page.sessions.filter(row => !rows.some(old => old.session_id === row.session_id))].slice(0, 128)); setNextCursor(page.next_cursor); } })} />}
    </View><View style={[s.column, { flexBasis: 620, gap: 20 }]}>
      {(creating || !active) && <View style={s.card}><Text style={s.heading}>New bounded crawl</Text><Text style={s.small}>Only explicitly selected seed hosts are admitted. Consent expires within 24 hours. Create the source scope first, then authorize a finite automatic run or one manual slice.</Text>
        <Text style={s.label}>Name (optional)</Text><TextInput accessibilityLabel="Crawl name" value={title} onChangeText={setTitle} maxLength={160} style={field} placeholder="Engine documentation" placeholderTextColor={colors.muted} />
        <Text style={s.label}>Seed URLs · one per line</Text><TextInput accessibilityLabel="Seed URLs" value={seeds} onChangeText={setSeeds} maxLength={32768} multiline style={[field, { minHeight: 110 }]} placeholder={'https://example.org/docs/\nhttps://example.org/guide/'} placeholderTextColor={colors.muted} autoCapitalize="none" />
        <Text style={s.label}>Topics (optional, comma separated)</Text><TextInput accessibilityLabel="Crawl topics" value={topics} onChangeText={setTopics} maxLength={1280} style={field} placeholder="movement, tools, scripting" placeholderTextColor={colors.muted} />
        <View style={s.row}>{[['Requests', requests, setRequests], ['Documents', documents, setDocuments], ['MB', megabytes, setMegabytes], ['Link depth', depth, setDepth]].map(([name, value, setter]) => <View key={name as string} style={{ minWidth: 90, flex: 1, gap: 6 }}><Text style={s.small}>{name as string}</Text><TextInput accessibilityLabel={`Maximum ${name as string}`} keyboardType="number-pad" value={value as string} onChangeText={setter as (v: string) => void} maxLength={3} style={field} /></View>)}</View>
        <View style={s.row}><Switch value={consent} onValueChange={setConsent} accessibilityLabel="Authorize this bounded capture" /><Text style={[s.message, s.grow]}>I authorize the app to request and store this bounded set of public sources.</Text></View><View style={s.row}><Switch value={rights} onValueChange={setRights} accessibilityLabel="Acknowledge source rights" /><Text style={[s.message, s.grow]}>I have permission to capture these sources and understand their use remains governed by source rights.</Text></View>
        <Button title={busy === 'Creating crawl' ? 'Creating…' : 'Create crawl'} disabled={!canWrite || readiness?.available !== true || !consent || !rights || !seeds.trim() || !!busy || running} onPress={create} />
      </View>}
      {active && !creating && <><View style={s.card}><View style={s.row}><Text style={[s.heading, s.grow]}>{active.title}</Text><View style={s.badge}><Text style={s.badgeText}>{label(active.status)}</Text></View></View>
        <Text style={s.small}>Last committed snapshot: {new Date(active.updated_at).toLocaleString()}</Text>
        <Text style={s.small}>{active.consent_current ? `Capture consent valid until ${new Date(active.consent_expires_at).toLocaleString()}` : 'Capture consent expired. Inspect retained records or create a new authorized crawl.'}</Text>
        <Text style={s.message}>Measured downloads: {bytes(active.counters.bytes)} / {bytes(active.limits.max_total_bytes)}</Text>
        {typeof active.counters.reserved_bytes === 'number' && active.counters.reserved_bytes > 0 && <Text style={s.small}>Unconfirmed transport allowance: {bytes(active.counters.reserved_bytes)} reserved separately from measured downloaded bytes.</Text>}
        {active.error?.message && <Text style={s.error}>{active.error.message}</Text>}
        <View style={s.row}><Button title="Erase this crawl and its captured sources" disabled={!!busy || running || (active.capabilities ? !active.capabilities.can_erase : !canWrite)} onPress={erase} />{(running || !!busy) && <ActivityIndicator color={colors.accent} />}</View>
      </View>
      <CrawlerAutomationPanel key={active.session_id} session={active} canWrite={canWrite} busy={!!busy || running}
        run={(name, operation) => { void mutate(name, operation); }} control={control} refresh={refreshActive}
        manual={() => { const id = active.session_id; const body = { idempotency_key: crawlRequestKey('run'), expected_version: active.version, max_steps: 4 }; void mutate('Run', signal => runCrawl(id, body, signal), true); }} />
      <View style={s.card}><Text style={s.heading}>Actual URL queue</Text>{active.queue.length ? active.queue.map((item, index) => <View key={`${item.url}-${index}`} style={s.check}><Text selectable style={s.message}>{item.url}</Text><Text style={s.small}>Depth {item.depth} · {item.attempts} attempts · {item.ready_at * 1000 <= Date.now() ? 'eligible now' : `next eligible ${new Date(item.ready_at * 1000).toLocaleTimeString()}`}</Text></View>) : <Text style={s.small}>No pending URL is listed in the current snapshot.</Text>}{active.frontier_count > active.queue.length && <Text style={s.small}>Showing the first {active.queue.length} of {active.frontier_count} queued URLs.</Text>}</View>
      <View style={s.card}><Text style={s.heading}>Recent crawl events</Text>{truncatedEvents && <Text style={s.small}>The runtime retains a bounded event tail. Older events are unavailable; no history has been reconstructed.</Text>}{events.length ? [...events].reverse().map(event => <View key={event.sequence} style={s.check}><Text style={s.label}>{label(event.kind)}</Text><Text style={s.small}>{new Date(event.at * 1000).toLocaleTimeString()}{event.reason ? ` · ${label(event.reason)}` : ''}</Text>{event.url && <Text selectable style={s.small}>{event.url}</Text>}</View>) : <Text style={s.small}>No event is recorded in the current bounded history.</Text>}</View>
      <CrawlerSourceLibrary key={active.session_id + ':' + token.current} session={active} sources={sources} more={!!sourceCursor} busy={!!busy || running}
        refresh={refreshActive}
        loadMore={() => { if (sourceCursor) void perform(async signal => { const page = await listCrawlSources(active.session_id, sourceCursor, signal); if (!signal.aborted && activeRef.current?.session_id === active.session_id) { setSources(rows => [...rows, ...page.sources.filter(row => !rows.some(old => old.source_id === row.source_id))].slice(0, 64)); setSourceCursor(page.next_cursor); } }); }}
        onReview={passage => { setReviewDraft(passage); choosePane('review'); }}
        exportSource={(item, format) => { void perform(async signal => { const file = await exportCrawlSource(active.session_id, item.source_id, format, signal); if (!signal.aborted) await saveExport(file); }); }} />
      </>}
    </View></View>
    </View>
    <View style={pane === 'review' ? undefined : { display: 'none' }}><DragonKnowledgePanel key={token.current} visible={pane === 'review'} canWrite={canWrite} draft={reviewDraft} clearDraft={() => setReviewDraft(null)} /></View>
  </ScrollView></SafeAreaView>;
}
const field = { backgroundColor: colors.bg, borderWidth: 1, borderColor: colors.edge, borderRadius: 9, padding: 12, color: colors.text, fontSize: 14, textAlignVertical: 'top' as const };
export default function CrawlerWorkspace() { return <StudioLoginGate title="Web capture" requireAuthenticated><CrawlerContent /></StudioLoginGate>; }
