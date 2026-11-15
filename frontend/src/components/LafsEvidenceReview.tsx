/** Explicit installation-operator source review; nothing is auto-approved. */
import React from 'react';
import { ActivityIndicator, Text, TextInput, TouchableOpacity, View, StyleSheet } from 'react-native';
import api, { subscribeApiSessionChanges } from '../utils/apiClient';

type Source = {
  id: string;
  evidence_status: string;
  payload: { title?: string; extract?: string; source_url?: string; revision?: number };
  provenance: { evidence_sha256?: string; response_sha256?: string; fetched_at?: number };
};

const validId = (value: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
const validDigest = (value: unknown): value is string => typeof value === 'string' && /^[0-9a-f]{64}$/.test(value);

export default function LafsEvidenceReview() {
  const [rows, setRows] = React.useState<Source[]>([]);
  const [selected, setSelected] = React.useState<Source | null>(null);
  const [reviewFilter, setReviewFilter] = React.useState<'pending' | 'approved'>('pending');
  const [note, setNote] = React.useState('');
  const [topic, setTopic] = React.useState('');
  const [status, setStatus] = React.useState('');
  const [busy, setBusy] = React.useState(false);
  const active = React.useRef(false);
  const epoch = React.useRef(0);
  const inFlight = React.useRef(false);

  React.useEffect(() => {
    active.current = true;
    const unsub = subscribeApiSessionChanges(() => {
      epoch.current += 1;
      inFlight.current = false;
      setRows([]); setSelected(null); setNote(''); setTopic(''); setStatus(''); setBusy(false);
    });
    return () => { active.current = false; epoch.current += 1; unsub(); };
  }, []);

  const run = async (job: (current: () => boolean) => Promise<void>) => {
    if (inFlight.current) return;
    inFlight.current = true;
    const generation = epoch.current;
    const current = () => active.current && epoch.current === generation;
    setBusy(true); setStatus('');
    try { await job(current); }
    catch { if (current()) setStatus('Source operation unavailable. Refresh and retry.'); }
    finally { if (current()) { inFlight.current = false; setBusy(false); } }
  };

  const refresh = async (current: () => boolean, filter: 'pending' | 'approved' = reviewFilter) => {
    const res = await api.get<{ sources: Source[] }>(`/api/lafs/sources/pending?limit=30&status=${filter}`, { retries: 0 });
    if (!current()) return;
    if (!res.ok || !Array.isArray(res.data?.sources)) {
      setRows([]); setSelected(null);
      setStatus('Source review is unavailable or installation-operator access is required.');
      return;
    }
    setRows(res.data.sources.filter(row => validId(row.id)));
    setSelected(null); setNote('');
  };

  const ingest = () => run(async current => {
    const value = topic.trim();
    if (value.length < 2 || value.length > 160) return;
    const res = await api.post<any>('/api/lafs/learn/online', { topic: value, reinforce: false, domain: 'Meta', log_type: 'Discovery' }, { retries: 0 });
    if (!current()) return;
    if (!res.ok) { setStatus('Source admission failed or online learning is disabled.'); return; }
    setTopic('');
    await refresh(current);
    if (current()) setStatus(res.data?.learned ? 'Revision retained for manual review.' : 'This evidence revision is already retained.');
  });

  const decide = (decision: 'approved' | 'rejected' | 'revoked') => run(async current => {
    const row = selected;
    const digest = row?.provenance?.evidence_sha256;
    if (!row || !validId(row.id) || !validDigest(digest) || !note.trim() ||
      (decision === 'revoked' ? row.evidence_status !== 'approved' : row.evidence_status !== 'pending')) return;
    const res = await api.post<any>(`/api/lafs/sources/${row.id}/review`,
      { digest, decision, note: note.trim() }, { retries: 0 });
    if (!current()) return;
    if (!res.ok) { setStatus('Review was not committed. Reload the exact revision before trying again.'); return; }
    await refresh(current);
    if (current()) setStatus('Review committed. Approval permits retrieval, not instruction authority.');
  });

  const reviewable = (selected?.evidence_status === 'pending' || selected?.evidence_status === 'approved') &&
    validDigest(selected?.provenance?.evidence_sha256);
  return <View style={s.card}>
    <Text style={s.heading}>LAFS source review</Text>
    <Text style={s.body}>External text is retained as untrusted evidence. Only explicit review enables retrieval.</Text>
    <View style={s.row}>
      <TextInput style={s.input} value={topic} onChangeText={setTopic} maxLength={160} placeholder="Wikipedia topic"
        placeholderTextColor="#94a3b8" accessibilityLabel="Source topic" />
      <TouchableOpacity style={s.button} disabled={busy || topic.trim().length < 2} onPress={ingest}><Text style={s.buttonText}>Ingest</Text></TouchableOpacity>
    </View>
    <View style={s.row}>
      <TouchableOpacity style={s.button} disabled={busy} onPress={() => { setReviewFilter('pending'); void run(current => refresh(current, 'pending')); }}><Text style={s.buttonText}>Pending evidence</Text></TouchableOpacity>
      <TouchableOpacity style={s.button} disabled={busy} onPress={() => { setReviewFilter('approved'); void run(current => refresh(current, 'approved')); }}><Text style={s.buttonText}>Approved evidence</Text></TouchableOpacity>
    </View>
    {busy && <ActivityIndicator color="#93c5fd" />}
    {!!status && <Text style={s.body}>{status}</Text>}
    {rows.map(row => <TouchableOpacity style={s.item} key={row.id} disabled={busy} onPress={() => { setSelected(row); setNote(''); }}>
      <Text style={s.title}>{row.payload?.title || row.id}</Text>
      <Text style={s.body}>{row.evidence_status} · revision {row.payload?.revision ?? 'unknown'}</Text>
    </TouchableOpacity>)}
    {selected && <View style={s.item}>
      <Text style={s.title}>{selected.payload?.title || 'Historical evidence'}</Text>
      <Text selectable style={s.body}>{selected.payload?.source_url || 'Original source not verified'}</Text>
      <Text selectable style={s.body}>Evidence SHA-256: {selected.provenance?.evidence_sha256 || 'unavailable'}</Text>
      <Text selectable style={s.body}>Response SHA-256: {selected.provenance?.response_sha256 || 'unavailable'}</Text>
      <Text selectable style={s.extract}>{selected.payload?.extract || 'No retained extract'}</Text>
      {reviewable ? <>
        <TextInput style={s.input} value={note} onChangeText={setNote} maxLength={1024} multiline
          placeholder="Record review rationale" placeholderTextColor="#94a3b8" accessibilityLabel="Review rationale" />
        <View style={s.row}>
          {selected.evidence_status === 'pending' ? <>
            <TouchableOpacity style={s.button} disabled={busy || !note.trim()} onPress={() => decide('approved')}><Text style={s.buttonText}>Approve exact evidence</Text></TouchableOpacity>
            <TouchableOpacity style={s.button} disabled={busy || !note.trim()} onPress={() => decide('rejected')}><Text style={s.buttonText}>Reject</Text></TouchableOpacity>
          </> : <TouchableOpacity style={s.button} disabled={busy || !note.trim()} onPress={() => decide('revoked')}><Text style={s.buttonText}>Revoke retrieval</Text></TouchableOpacity>}
        </View>
      </> : <Text style={s.body}>Legacy evidence requires fresh source ingestion before review.</Text>}
    </View>}
  </View>;
}

const s = StyleSheet.create({
  card: { backgroundColor: '#111827', borderRadius: 12, padding: 12, gap: 9, marginBottom: 12 },
  heading: { color: '#e2e8f0', fontSize: 16, fontWeight: '700' },
  title: { color: '#e2e8f0', fontSize: 13, fontWeight: '600' },
  body: { color: '#94a3b8', fontSize: 12, lineHeight: 18 },
  extract: { color: '#e2e8f0', fontSize: 13, lineHeight: 20 },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' },
  input: { flexGrow: 1, minWidth: 140, color: '#e2e8f0', borderWidth: 1, borderColor: '#334155', borderRadius: 8, padding: 9 },
  button: { backgroundColor: '#24486e', padding: 10, borderRadius: 8 },
  buttonText: { color: '#f8fafc', fontSize: 12, fontWeight: '600' },
  item: { backgroundColor: '#0b1220', borderRadius: 8, padding: 9, gap: 5 },
});
