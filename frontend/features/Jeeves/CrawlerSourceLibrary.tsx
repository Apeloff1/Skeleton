import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Linking, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import {
  getCrawlSource, getCrawlText, searchCrawlSources,
  type CapturedSource, type CrawlSearchHit, type CrawlSession, type CrawlTextPage,
} from '../../src/product/crawlerClient';
import s, { colors as C } from './CrawlerWorkspace.styles';

export type CrawlPassageSelection = {
  sessionId: string; sourceId: string; start: number; end: number; quote: string;
  contentDigest: string; sourceUrl: string; title: string;
};
type Props = {
  session: CrawlSession; sources: CapturedSource[]; more: boolean; busy: boolean;
  loadMore: () => void; refresh: () => void;
  onReview: (passage: CrawlPassageSelection) => void;
  exportSource: (source: CapturedSource, format: 'json' | 'markdown') => void;
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
export default function CrawlerSourceLibrary({ session, sources, more, busy, loadMore, refresh, onReview, exportSource }: Props) {
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
  const readRequest = useRef<AbortController | null>(null);
  const searchRequest = useRef<AbortController | null>(null);
  const generation = useRef(0);
  useEffect(() => {
    generation.current++;
    return () => { generation.current++; readRequest.current?.abort(); searchRequest.current?.abort(); };
  }, [session.session_id]);
  const open = async (source: CapturedSource | CrawlSearchHit, offset = 0) => {
    readRequest.current?.abort(); const request = new AbortController(); readRequest.current = request;
    const epoch = generation.current; setReading(true); setError(''); setPage(null); setPassage(null); setRestrictedPreview(null);
    let item: CapturedSource | null = null;
    try {
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
      if (!request.signal.aborted && epoch === generation.current) { setPage(null); setPassage(null); if (item) { setSelected(item); setRestrictedPreview(item.text?.slice(0, 16000) || 'No preserved text preview was returned.'); } else setSelected(null); setError(failure instanceof Error ? failure.message : 'The preserved source could not be read.'); }
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
      </TouchableOpacity>)}
      {more && <Button title="Load more captured sources" disabled={busy} press={loadMore} />}
    </View>}
    {reading && <View style={s.row}><ActivityIndicator color={C.accent} /><Text style={s.small}>Reading a preserved text page…</Text></View>}
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
});
