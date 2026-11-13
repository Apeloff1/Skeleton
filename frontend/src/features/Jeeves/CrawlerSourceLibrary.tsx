import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Linking, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  configureCrawlSourceUse, crawlRequestKey, getCrawlSource, getCrawlText, searchCrawlSources,
  type CrawlCommand,
  type CapturedSource, type CrawlSearchHit, type CrawlSession, type CrawlTextPage,
} from '../../product/crawlerClient';
import { ChatClientError } from '../../product/chatErrors';
import s, { colors as C } from './CrawlerWorkspace.styles';

export type CrawlPassageSelection = {
  sessionId: string; sourceId: string; start: number; end: number; quote: string;
  contentDigest: string; sourceUrl: string; title: string;
};
type Props = {
  session: CrawlSession; sources: CapturedSource[]; more: boolean; busy: boolean; canWrite: boolean;
  loadMore: () => void; refresh: () => void;
  onReview: (passage: CrawlPassageSelection) => void;
  exportSource: (source: CapturedSource, format: 'json' | 'markdown') => void;
  policyChanged: (value: { session: CrawlSession; source: CapturedSource }) => void;
};
function Button({ title, press, disabled = false }: { title: string; press: () => void; disabled?: boolean }) {
  return <TouchableOpacity accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={press}
    style={[s.button, disabled && s.disabled]}><Text style={s.buttonText}>{title}</Text></TouchableOpacity>;
}
function snippets(page: CrawlTextPage) {
  const chars = Array.from(page.text);
  const result: { start: number; end: number; text: string }[] = [];
  for (let begin = 0; begin < chars.length;) {
    let end = Math.min(begin + 1000, chars.length);
    if (end < chars.length) {
      for (let at = end; at > begin + 250; at--) if (chars[at - 1] === '\n') { end = at; break; }
    }
    let first = begin, last = end;
    while (first < last && /\s/.test(chars[first])) first++;
    while (last > first && /\s/.test(chars[last - 1])) last--;
    if (last > first) result.push({ start: page.offset + first, end: page.offset + last, text: chars.slice(first, last).join('') });
    begin = end;
  }
  return result;
}

/** Bounded text pages stay source material. Selecting a passage only prepares a review draft. */
export default function CrawlerSourceLibrary({ session, sources, more, busy, canWrite, loadMore, refresh, onReview, exportSource, policyChanged }: Props) {
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState<CrawlSearchHit[] | null>(null);
  const [selected, setSelected] = useState<CapturedSource | null>(null);
  const [page, setPage] = useState<CrawlTextPage | null>(null);
  const [passage, setPassage] = useState<{ start: number; end: number; text: string } | null>(null);
  const [restrictedPreview, setRestrictedPreview] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState('');
  const [inspect, setInspect] = useState(false);
  const [maxAge, setMaxAge] = useState('86400');
  const [savingPolicy, setSavingPolicy] = useState(false);
  const [policyNotice, setPolicyNotice] = useState('');
  const [policyRetry, setPolicyRetry] = useState<{ sourceId: string; body: CrawlCommand & { enabled: boolean; max_age_seconds: number } } | null>(null);
  const policyRequest = useRef<AbortController | null>(null);
  const policyLock = useRef(false);
  const readRequest = useRef<AbortController | null>(null);
  const searchRequest = useRef<AbortController | null>(null);
  const generation = useRef(0);
  useEffect(() => {
    generation.current++;
    return () => { generation.current++; readRequest.current?.abort(); searchRequest.current?.abort(); policyRequest.current?.abort(); };
  }, [session.session_id]);
  useEffect(() => { setMaxAge(String(selected?.use_policy?.max_age_seconds ?? 86400)); }, [selected?.source_id, selected?.use_policy?.version]);
  useEffect(() => {
    if (!selected) return;
    const current = sources.find(item => item.source_id === selected.source_id);
    if (!current?.use_policy || !current.freshness) return;
    if (current.use_policy.version < (selected.use_policy?.version ?? 0)) return;
    if (current.use_policy.version !== selected.use_policy?.version || !current.freshness.usable) {
      readRequest.current?.abort(); searchRequest.current?.abort();
      setReading(false); setSearching(false); setSelected(current); setPage(null); setPassage(null); setRestrictedPreview(null); setHits(null);
    }
  }, [sources, selected]);
  useEffect(() => {
    if (!selected?.freshness || !page) return;
    const expiry = Date.parse(selected.freshness.valid_until);
    const timer = setTimeout(() => {
      readRequest.current?.abort(); setPage(null); setPassage(null); setRestrictedPreview(null);
      setError('This capture reached its permitted age. Refresh source settings before selecting it again.');
      refresh();
    }, Math.max(0, Math.min(86400000, expiry - Date.now())));
    return () => clearTimeout(timer);
  }, [selected, page, refresh]);
  const savePolicy = async (command: { sourceId: string; body: CrawlCommand & { enabled: boolean; max_age_seconds: number } }) => {
    if (policyLock.current) return;
    policyLock.current = true;
    const request = new AbortController(); policyRequest.current = request;
    const epoch = generation.current; setSavingPolicy(true); setError(''); setPolicyNotice('');
    readRequest.current?.abort(); searchRequest.current?.abort(); setReading(false); setSearching(false);
    setPage(null); setPassage(null); setRestrictedPreview(null); setHits(null);
    try {
      const value = await configureCrawlSourceUse(session.session_id, command.sourceId, command.body, request.signal);
      if (request.signal.aborted || epoch !== generation.current) return;
      setPolicyRetry(null); setSelected(value.source); policyChanged(value);
      setPolicyNotice(value.source.freshness?.usable ? 'Current source-use settings are saved. Open the source again to select a passage.'
        : value.source.use_policy?.enabled ? 'Settings saved. This capture is outside its permitted age; enabling use does not fetch a newer page.'
          : 'Source use is disabled for Jeeves and reviewed design references. The original capture remains in your inventory.');
    } catch (failure) {
      if (request.signal.aborted || epoch !== generation.current) return;
      if (failure instanceof ChatClientError && failure.kind === 'conflict') {
        setPolicyRetry(null); setSelected(null); refresh();
        setError('The crawl changed before this update. Current settings are refreshing; review them and apply your change again.');
      } else {
        setPolicyRetry(failure instanceof ChatClientError && failure.retryable ? command : null);
        setError(failure instanceof Error ? failure.message : 'Source-use settings could not be saved.');
      }
    } finally {
      policyLock.current = false;
      if (!request.signal.aborted && epoch === generation.current) setSavingPolicy(false);
    }
  };
  const changePolicy = (enabled: boolean) => {
    if (!selected?.use_policy || policyRetry) return;
    const age = enabled ? Number(maxAge) : selected.use_policy.max_age_seconds;
    if (!/^\d{2,5}$/.test(enabled ? maxAge : String(age)) || !Number.isSafeInteger(age) || age < 60 || age > 86400) {
      setError('Set a capture-age limit from 60 to 86,400 seconds.'); return;
    }
    void savePolicy({ sourceId: selected.source_id, body: {
      idempotency_key: crawlRequestKey('source-use'), expected_version: session.version, enabled, max_age_seconds: age,
    } });
  };
  const open = async (source: CapturedSource | CrawlSearchHit, offset = 0) => {
    if (policyLock.current) return;
    readRequest.current?.abort(); const request = new AbortController(); readRequest.current = request;
    const epoch = generation.current; setReading(true); setError(''); setPage(null); setPassage(null); setRestrictedPreview(null);
    let item: CapturedSource | null = null;
    try {
      if ('freshness' in source && source.freshness && (!source.freshness.usable || Date.parse(source.freshness.valid_until) <= Date.now())) {
        setSelected(source as CapturedSource); return;
      }
      item = await getCrawlSource(session.session_id, source.source_id, request.signal);
      if (request.signal.aborted || epoch !== generation.current) return;
      setSelected(item);
      const value = await getCrawlText(session.session_id, item.source_id, offset, item.content_digest, request.signal);
      if (request.signal.aborted || epoch !== generation.current) return;
      setPage(value);
      if ('start' in source && source.start >= value.offset && source.end <= value.end) {
        const text = Array.from(value.text).slice(source.start - value.offset, source.end - value.offset).join('');
        if (text === source.text && source.end - source.start <= 1000) setPassage({ start: source.start, end: source.end, text });
      }
    } catch (failure) {
      if (!request.signal.aborted && epoch === generation.current) {
        setPage(null); setPassage(null);
        if (failure instanceof ChatClientError && ['authorization', 'conflict'].includes(failure.kind)) {
          setSelected(null); setRestrictedPreview(null); setHits(null); refresh();
        } else if (item) {
          setSelected(item); setRestrictedPreview(item.text?.slice(0, 16000) || 'No preserved text preview was returned.');
        } else setSelected(null);
        setError(failure instanceof Error ? failure.message : 'The preserved source could not be read.');
      }
    } finally { if (!request.signal.aborted && epoch === generation.current) setReading(false); }
  };
  const search = async () => {
    searchRequest.current?.abort(); const request = new AbortController(); searchRequest.current = request;
    const epoch = generation.current; setSearching(true); setError('');
    try {
      const value = await searchCrawlSources(session.session_id, query, request.signal);
      if (!request.signal.aborted && epoch === generation.current) setHits(value.hits);
    } catch (failure) {
      if (!request.signal.aborted && epoch === generation.current) setError(failure instanceof Error ? failure.message : 'Source search is unavailable.');
    } finally { if (!request.signal.aborted && epoch === generation.current) setSearching(false); }
  };
  const draftReview = () => {
    if (!selected || !page || !passage) return;
    onReview({ sessionId: session.session_id, sourceId: selected.source_id, start: passage.start, end: passage.end,
      quote: passage.text, contentDigest: page.content_digest, sourceUrl: selected.url, title: selected.title });
  };
  return <View style={s.card}>
    <View style={s.row}><View style={[s.grow, { minWidth: 160 }]}><Text style={s.heading}>Captured source library</Text>
      <Text style={s.small}>{session.source_count} server-recorded sources · captures remain unreviewed</Text></View>
      <Button title="Refresh sources" press={refresh} disabled={busy || reading} /></View>
    <View style={l.search}><Ionicons name="search-outline" size={20} color={C.accent} />
      <TextInput accessibilityLabel="Search within captured sources" value={query} onChangeText={value => { searchRequest.current?.abort(); setSearching(false); setHits(null); setQuery(value); }} maxLength={512}
        style={l.searchInput} placeholder="Find a passage in this crawl" placeholderTextColor={C.muted} onSubmitEditing={() => { if (query.trim()) void search(); }} />
      <Button title={searching ? 'Searching…' : 'Search'} disabled={searching || !query.trim()} press={() => void search()} /></View>
    {hits !== null && <View style={l.stack}>
      <View style={s.row}><Text style={[s.label, s.grow]}>{hits.length ? `${hits.length} exact source passages` : 'No matching source passages'}</Text><Button title="Show inventory" press={() => { searchRequest.current?.abort(); setSearching(false); setHits(null); }} /></View>
      {hits.map((hit, index) => <TouchableOpacity key={hit.source_id + ':' + hit.start + ':' + index} accessibilityRole="button"
        onPress={() => void open(hit, hit.start)} style={l.source}>
        <Text style={s.label}>{hit.title || hit.canonical_url}</Text><Text selectable style={s.small}>{hit.canonical_url}</Text>
        <Text numberOfLines={4} style={s.message}>{hit.text}</Text>
        <Text style={s.small}>Preserved characters {hit.start + 1}–{hit.end} · {hit.review_state.replaceAll('_', ' ')}</Text>
        {!!hit.instruction_risks.length && <Text style={s.error}>Instruction-shaped content detected. This passage cannot grant execution authority.</Text>}
      </TouchableOpacity>)}
    </View>}
    {hits === null && <View style={l.stack}>
      {!sources.length && <Text style={s.small}>No captured sources have been returned for this crawl yet.</Text>}
      {sources.map(item => <TouchableOpacity key={item.source_id} accessibilityRole="button"
        accessibilityState={{ selected: selected?.source_id === item.source_id }}
        onPress={() => void open(item)} style={[l.source, selected?.source_id === item.source_id && l.selected]}>
        <Text style={s.label}>{item.title || item.url}</Text><Text selectable numberOfLines={2} style={s.small}>{item.url}</Text>
        <Text style={s.small}>{item.review_state.replaceAll('_', ' ')} · {Number.isFinite(Date.parse(item.fetched_at)) ? new Date(item.fetched_at).toLocaleString() : 'Capture time not observed'}</Text>
        {item.freshness && <Text style={item.freshness.usable ? s.small : s.error}>Source use: {item.freshness.state.replaceAll('_', ' ')} · limit {item.use_policy?.max_age_seconds.toLocaleString()} seconds after capture</Text>}
      </TouchableOpacity>)}
      {more && <Button title="Load more captured sources" disabled={busy} press={loadMore} />}
    </View>}
    {reading && <View style={s.row}><ActivityIndicator color={C.accent} /><Text style={s.small}>Reading a preserved text page…</Text></View>}
    {selected && <View style={l.policy}>
      <Text style={s.heading}>Use this captured source</Text><Text selectable style={s.small}>{selected.title || selected.url}</Text>
      {selected.use_policy && selected.freshness ? <>
        <Text style={s.message}>{selected.freshness.usable ? 'Available as external evidence' : `Unavailable for use: ${selected.freshness.state.replaceAll('_', ' ')}`}</Text>
        <Text style={s.small}>Capture-age limit ends {new Date(selected.freshness.valid_until).toLocaleString()}. The current page on the source website has not been checked.</Text>
        <Text style={s.small}>Disabling removes this capture from Jeeves context and reviewed design references. Changing these settings requires affected design references to be reviewed again.</Text>
        {canWrite && <View style={l.search}><Text style={s.label}>Maximum capture age, seconds</Text><TextInput accessibilityLabel="Maximum source capture age in seconds" keyboardType="number-pad" value={maxAge} maxLength={5}
          editable={!busy && !savingPolicy && !policyRetry} onChangeText={setMaxAge} style={l.ageInput} />
          <Text style={s.small}>60–86,400; measured from the original capture</Text></View>}
        <View style={s.row}>
          <Button title={savingPolicy ? 'Saving source settings…' : 'Disable source use'} disabled={savingPolicy || !!policyRetry || !selected.use_policy.enabled} press={() => changePolicy(false)} />
          {canWrite && <Button title={selected.use_policy.enabled ? 'Save capture-age limit' : 'Enable source use'} disabled={busy || savingPolicy || !!policyRetry || !session.consent_current || ['cancelled', 'deleted'].includes(session.status)} press={() => changePolicy(true)} />}
          {selected.freshness.usable && !page && <Button title="Read current source" disabled={busy || savingPolicy || !!policyRetry || reading} press={() => void open(selected)} />}
          {!page && <Button title="Close source settings" disabled={savingPolicy} press={() => setSelected(null)} />}
        </View>
        {!canWrite && <Text style={s.small}>You can disable this source. An editor or administrator must enable it or change its capture-age limit.</Text>}
      </> : <Text style={s.small}>Source-use controls have not been returned by the server. Refresh sources before changing settings.</Text>}
    </View>}
    {policyRetry && <View style={l.policy}><Text style={s.small}>The last source-use change has no confirmed outcome. Retry the saved request to resolve it before applying another change.</Text>
      <View style={s.row}><Button title="Retry saved source-use change" disabled={busy || savingPolicy} press={() => void savePolicy(policyRetry)} />
        <Button title="Refresh and discard saved request" disabled={savingPolicy} press={() => { setPolicyRetry(null); setSelected(null); setPolicyNotice('Review refreshed settings before making another change.'); refresh(); }} /></View></View>}
    {!!policyNotice && <Text accessibilityLiveRegion="polite" style={s.small}>{policyNotice}</Text>}
    {selected && restrictedPreview !== null && <View style={l.inspector}>
      <Text style={s.heading}>Preserved inspection preview</Text><Text selectable style={s.small}>{selected.url}</Text>
      <Text style={s.small}>This read-only preview does not admit a new source passage or review. Current consent is required for passage search and use.</Text>
      <Text selectable style={s.message}>{restrictedPreview}</Text>
      <View style={s.row}><Button title="Export source JSON" disabled={busy} press={() => exportSource(selected, 'json')} /><Button title="Close inspection" press={() => { setSelected(null); setRestrictedPreview(null); }} /></View>
    </View>}
    {selected && page && <View style={l.inspector}>
      <View style={s.row}><Text style={[s.heading, s.grow]}>{selected.title || 'Preserved source text'}</Text>
        <Button title="Close source" press={() => { readRequest.current?.abort(); setSelected(null); setPage(null); setPassage(null); }} /></View>
      <Text selectable style={s.small}>{selected.url}</Text>
      <Text style={s.small}>Characters {page.offset + (page.text ? 1 : 0)}–{page.end} of {page.total_chars.toLocaleString()} · digest-checked Unicode text</Text>
      <Text style={s.message}>Choose a passage to prepare a design note. Reading or capturing a page does not approve its claims.</Text>
      <View style={l.stack}>{snippets(page).map(item => <TouchableOpacity key={item.start} accessibilityRole="radio"
        accessibilityState={{ checked: passage?.start === item.start && passage?.end === item.end }}
        accessibilityLabel={`Select preserved passage, characters ${item.start + 1} to ${item.end}`}
        onPress={() => setPassage(item)} style={[l.passage, passage?.start === item.start && l.selected]}>
        <Text selectable style={s.message}>{item.text}</Text>
      </TouchableOpacity>)}</View>
      <View style={s.row}>
        <Button title="Previous text page" disabled={reading || page.offset === 0} press={() => void open(selected, Math.max(0, page.offset - 8000))} />
        <Button title="Next text page" disabled={reading || page.next_offset === null} press={() => { if (page.next_offset !== null) void open(selected, page.next_offset); }} />
        <Button title="Prepare design note from selected passage" disabled={!passage || reading} press={draftReview} />
      </View>
      <View style={s.row}><Button title="Export source JSON" disabled={busy} press={() => exportSource(selected, 'json')} />
        <Button title="Export source Markdown" disabled={busy} press={() => exportSource(selected, 'markdown')} />
        <Button title="Open original URL" press={() => { try { const url = new URL(selected.url); if (['http:', 'https:'].includes(url.protocol) && !url.username && !url.password) void Linking.openURL(url.href).catch(() => setError('The original URL could not be opened.')); } catch { setError('The original URL is invalid.'); } }} />
        <Button title={inspect ? 'Hide provenance' : 'Inspect provenance'} press={() => setInspect(value => !value)} /></View>
      {inspect && <Text selectable style={l.code}>{JSON.stringify({ source_id: selected.source_id, content_digest: page.content_digest, source_classification: page.source_classification, provenance: selected.provenance }, null, 2).slice(0, 12000)}</Text>}
    </View>}
    {!!error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
  </View>;
}
const l = StyleSheet.create({
  stack: { gap: 10 }, search: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 10 },
  searchInput: { flexGrow: 1, flexBasis: 200, minWidth: 0, minHeight: 44, color: C.text, borderWidth: 1, borderColor: C.edge, borderRadius: 9, padding: 12 },
  source: { padding: 14, borderWidth: 1, borderColor: C.edge, borderRadius: 11, gap: 6, backgroundColor: C.bg },
  selected: { borderColor: C.accent, backgroundColor: '#251f38' }, inspector: { borderTopWidth: 1, borderColor: C.edge, paddingTop: 18, gap: 14 },
  passage: { borderWidth: 1, borderColor: C.edge, borderRadius: 10, padding: 14 },
  code: { color: C.muted, fontFamily: 'monospace', fontSize: 12, lineHeight: 19, padding: 12, backgroundColor: C.bg, borderRadius: 9 },
  policy: { borderWidth: 1, borderColor: C.edge, borderRadius: 11, padding: 14, gap: 10, backgroundColor: C.bg },
  ageInput: { minWidth: 110, minHeight: 44, color: C.text, borderWidth: 1, borderColor: C.edge, borderRadius: 9, padding: 10 },
});
