import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { getAuthToken } from '../../auth/gameforgeAuth';
import {
  createDragonCandidate, dragonEvidenceKey, getDragonCandidate, getDragonKnowledgeReadiness, listDragonCandidates,
  resumeDragonReview, reviewDragonCandidate, runDragonPractice, searchDragonReferences, getDragonPracticeHistory,
  type DragonKnowledgeCandidate, type DragonKnowledgeReadiness, type DragonPracticeReceipt, type DragonDesignReference,
} from '../../product/dragonKnowledgeClient';
import { ChatClientError } from '../../product/chatErrors';
import type { CrawlPassageSelection } from './CrawlerSourceLibrary';
import GameLearningFrame from './GameLearningFrame';
import s, { colors as C } from './CrawlerWorkspace.styles';

type Props = { visible: boolean; canWrite: boolean; draft: CrawlPassageSelection | null; clearDraft: () => void };
function human(value: string) { return value.replaceAll('_', ' '); }
function Button({ label, press, disabled = false, primary = false }: { label: string; press: () => void; disabled?: boolean; primary?: boolean }) {
  return <TouchableOpacity accessibilityRole="button" accessibilityLabel={label} accessibilityState={{ disabled }} disabled={disabled}
    onPress={press} style={[s.button, primary && k.primary, disabled && s.disabled]}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
}
function finite(value: number | undefined) { return value === undefined ? 'Not measured' : value.toLocaleString(undefined, { maximumFractionDigits: 4 }); }

/** Human review creates a scoped design reference; local practice is a measured exercise, not a truth or training grant. */
export default function DragonKnowledgePanel({ visible, canWrite, draft, clearDraft }: Props) {
  const router = useRouter();
  const [readiness, setReadiness] = useState<DragonKnowledgeReadiness | null>(null);
  const [candidates, setCandidates] = useState<DragonKnowledgeCandidate[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [filter, setFilter] = useState<DragonKnowledgeCandidate['state'] | undefined>();
  const [selected, setSelected] = useState<DragonKnowledgeCandidate | null>(null);
  const [statement, setStatement] = useState('');
  const [mechanic, setMechanic] = useState('');
  const [rationale, setRationale] = useState('');
  const [rightsRef, setRightsRef] = useState('');
  const [rights, setRights] = useState(false);
  const [practiceConsent, setPracticeConsent] = useState(false);
  const [steps, setSteps] = useState('128');
  const [seed, setSeed] = useState('0');
  const [receipt, setReceipt] = useState<DragonPracticeReceipt | null>(null);
  const [practiceHistory, setPracticeHistory] = useState<DragonPracticeReceipt[]>([]);
  const [referenceQuery, setReferenceQuery] = useState('');
  const [references, setReferences] = useState<DragonDesignReference[] | null>(null);
  const [busy, setBusy] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [inspect, setInspect] = useState(false);
  const [retry, setRetry] = useState<(() => void) | null>(null);
  const token = useRef(getAuthToken());
  const alive = useRef(true);
  const readController = useRef<AbortController | null>(null);
  const mutation = useRef<AbortController | null>(null);
  const safe = useCallback(() => alive.current && token.current === getAuthToken(), []);
  useEffect(() => { alive.current = true; return () => { alive.current = false; readController.current?.abort(); mutation.current?.abort(); }; }, []);
  const load = useCallback(async (more = false) => {
    readController.current?.abort(); const request = new AbortController(); readController.current = request;
    setLoading(true);
    try {
      const results = await Promise.allSettled([getDragonKnowledgeReadiness(request.signal), listDragonCandidates(filter, more ? cursor : null, request.signal)]);
      if (!safe() || request.signal.aborted) return;
      if (results[0].status === 'fulfilled') {
        const ready = results[0].value; setReadiness(ready);
        setMechanic(current => ready.mechanics.some(item => item.id === current) ? current : ready.mechanics[0]?.id || '');
      }
      if (results[1].status === 'fulfilled') {
        const page = results[1].value;
        setCandidates(previous => more ? [...previous, ...page.candidates.filter(item => !previous.some(old => old.candidate_id === item.candidate_id))].slice(-64) : page.candidates); setCursor(page.next_cursor);
        setSelected(current => current ? page.candidates.find(item => item.candidate_id === current.candidate_id) || current : null);
      }
      const failed = results.find(result => result.status === 'rejected');
      if (failed?.status === 'rejected') throw failed.reason;
    } catch (failure) { if (safe() && !request.signal.aborted) setError(failure instanceof Error ? failure.message : 'Dragon review readiness has not been observed.'); }
    finally { if (safe() && !request.signal.aborted) setLoading(false); }
  }, [filter, cursor, safe]);
  // Cursor is not a refresh trigger. A filter or opening the pane starts a
  // fresh canonical page; Load more preserves the exact issued cursor.
  const loadRef = useRef(load); loadRef.current = load;
  useEffect(() => { if (visible) void loadRef.current(false); else readController.current?.abort(); }, [visible, filter]);
  const draftRef = useRef(draft); draftRef.current = draft;
  useEffect(() => { if (draft) { setStatement(''); setSelected(null); setReceipt(null); setNotice('Selected preserved passage. Write the design statement you want a human to review.'); } }, [draft]);
  const run = (name: string, operation: (signal: AbortSignal) => Promise<void>) => {
    if (mutation.current) return;
    const execute = () => {
      if (mutation.current || !safe()) return;
      const request = new AbortController(); mutation.current = request; readController.current?.abort(); setLoading(false); setBusy(name); setError(''); setRetry(null);
      void operation(request.signal).catch(failure => {
        if (!safe() || request.signal.aborted) return;
        setError(failure instanceof Error ? failure.message : 'The Dragon action was not confirmed.');
        if (!(failure instanceof ChatClientError) || ['network', 'timeout', 'unavailable'].includes(failure.kind)) setRetry(() => execute);
      }).finally(() => { if (mutation.current === request) mutation.current = null; if (safe() && !request.signal.aborted) setBusy(''); });
    };
    execute();
  };
  const accept = (value: DragonKnowledgeCandidate) => {
    setSelected(previous => previous?.candidate_id === value.candidate_id && previous.version > value.version ? previous : value); setCandidates(previous => { const newer = previous.find(item => item.candidate_id === value.candidate_id && item.version > value.version); return [newer || value, ...previous.filter(item => item.candidate_id !== value.candidate_id)].slice(0, 64); });
    setRationale(''); setRightsRef(''); setRights(false); setPracticeConsent(false); setReceipt(null); setPracticeHistory([]);
  };
  const create = () => {
    if (!draft || !statement.trim() || !mechanic) return;
    const body = { session_id: draft.sessionId, source_id: draft.sourceId, start: draft.start, end: draft.end,
      statement: statement.trim(), mechanic, idempotency_key: dragonEvidenceKey('candidate') };
    run('Saving source-bound review candidate', async signal => {
      const value = await createDragonCandidate(body, signal);
      if (safe() && !signal.aborted) { accept(value); if (draftRef.current === draft) { clearDraft(); setStatement(''); } setNotice('The candidate is saved for human review. The source has not been approved or promoted.'); }
    });
  };
  const review = (decision: 'approve_design_reference' | 'reject') => {
    if (!selected || !rationale.trim()) { setError('Write the human review rationale first.'); return; }
    if (decision === 'approve_design_reference' && (!rights || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(rightsRef.trim()))) { setError('Acknowledge design-use rights and use a permission record ID containing letters, numbers, dots, hyphens, underscores or colons.'); return; }
    const current = selected;
    const body = { expected_version: current.version, decision, rationale: rationale.trim(),
      ...(decision === 'approve_design_reference' ? { rights_reference: rightsRef.trim(), rights_acknowledged: true as const } : {}), idempotency_key: dragonEvidenceKey('review') };
    run('Saving explicit human review', async signal => {
      const value = await reviewDragonCandidate(current, body, signal);
      if (safe() && !signal.aborted) { accept(value); setNotice(value.state === 'approved' ? 'Approved only as a research and design reference. Training rights, factual verification and XP were not granted.' : 'The candidate was rejected and its decision was retained.'); }
    });
  };
  const practice = () => {
    if (!selected || !practiceConsent) return;
    if (!/^\d+$/.test(steps) || Number(steps) < 16 || Number(steps) > 512 || !/^\d+$/.test(seed) || Number(seed) > 2147483647) { setError('Choose 16–512 practice steps and a seed from 0 to 2,147,483,647.'); return; }
    const current = selected;
    const body = { expected_version: current.version, max_steps: Number(steps), seed: Number(seed), practice_consent: true as const, idempotency_key: dragonEvidenceKey('practice') };
    run('Running bounded local reference practice', async signal => {
      const result = await runDragonPractice(current, body, signal);
      if (safe() && !signal.aborted) { setReceipt(result.practice); setPracticeHistory(previous => [result.practice, ...previous.filter(value => value.practice_id !== result.practice.practice_id)].slice(0, 128)); setNotice(result.replayed ? 'Recovered the exact committed practice receipt.' : 'Actual local reference steps were recorded. This does not verify the web claim or award mastery.'); }
    });
  };
  const supported = readiness?.mechanics.find(value => value.id === selected?.mechanic)?.practice_supported === true;
  const sourceUnexpired = !!selected && selected.current_source_usable === true && Number.isFinite(Date.parse(selected.valid_until)) && Date.parse(selected.valid_until) > Date.now();
  return <View style={k.stack}>
    <View style={s.card}><View style={s.row}><View style={[s.grow, { minWidth: 180 }]}><Text style={s.heading}>Review and practice</Text><Text style={s.small}>Capture → authored design note → human review → measured reference exercise</Text></View>
      <Button label={loading ? 'Checking…' : 'Refresh review state'} disabled={loading || !!busy} press={() => void load(false)} /></View>
      <View style={s.row}><View style={s.badge}><Text style={s.badgeText}>{readiness ? readiness.available ? 'Review services ready' : 'Review setup required' : 'Readiness not observed'}</Text></View></View>
      <Text style={s.message}>A human-approved reference records a permitted interpretation of a source. It is not independent verification, a training grant or earned XP.</Text>
      {readiness && Object.entries(readiness.checks).map(([name, check]) => <Text key={name} style={s.small}>{human(name)}: {check.available ? 'ready' : 'unavailable'}</Text>)}
      {readiness?.actions.map(action => <Text key={action.code} style={s.small}>{action.message}</Text>)}
      {!readiness?.available && <Button label="Open setup diagnostics" press={() => router.push('/setup' as never)} />}
      {!canWrite && <Text style={s.small}>Your account can prepare candidates and request admitted reference practice. Review decisions require a current editor or administrator.</Text>}
    </View>
    {!!error && <View style={s.card} accessibilityRole="alert"><Text style={s.error}>{error}</Text>{retry && <Button label="Retry the same saved action" disabled={!!busy} press={retry} />}</View>}
    {!!notice && <Text accessibilityLiveRegion="polite" style={s.small}>{notice}</Text>}
    {!!busy && <View style={s.row}><ActivityIndicator color={C.accent} /><Text style={s.message}>{busy}…</Text></View>}
    {draft && <View style={s.card}><Text style={s.heading}>Prepare a design-reference candidate</Text><Text style={s.label}>{draft.title || 'Selected source passage'}</Text>
      <Text selectable style={s.small}>{draft.sourceUrl}</Text><Text style={s.small}>Exact preserved characters {draft.start + 1}–{draft.end}</Text><Text selectable style={k.quote}>{draft.quote}</Text>
      <Text style={s.label}>Your authored design statement</Text><TextInput accessibilityLabel="Authored design statement" value={statement} onChangeText={setStatement} maxLength={2048} multiline style={[k.input, { minHeight: 100 }]} editable={!busy} placeholder="Describe the design idea the passage supports, including its limits." placeholderTextColor={C.muted} />
      <Text style={s.label}>Mechanic classification</Text><View style={s.row}>{readiness?.mechanics.map(value => <Button key={value.id} label={value.label} primary={mechanic === value.id} disabled={!!busy} press={() => setMechanic(value.id)} />)}</View>
      <View style={s.row}><Button label="Save candidate for human review" primary disabled={!!busy || !readiness?.capabilities.source_review || !statement.trim() || !mechanic} press={create} /><Button label="Discard draft" disabled={!!busy} press={clearDraft} /></View>
    </View>}
    <View style={s.card}><Text style={s.heading}>Find approved design references</Text><Text style={s.small}>Search only current human-reviewed design notes. A matching note is not independently verified truth or a model-training permission.</Text>
      <TextInput accessibilityLabel="Search approved design references" value={referenceQuery} onChangeText={setReferenceQuery} maxLength={300} editable={!busy} style={k.input} placeholder="Movement, exploration, level design…" placeholderTextColor={C.muted} />
      <Button label="Search design references" disabled={!!busy || !referenceQuery.trim() || !readiness?.available} press={() => {
        const query = referenceQuery.trim(); run('Reading current reviewed design references', async signal => { const result = await searchDragonReferences(query, signal); if (safe() && !signal.aborted) setReferences(result.references); });
      }} />
      {references !== null && !references.length && <Text style={s.small}>No current reviewed design reference matched this query.</Text>}
      {references?.map((value, index) => <View key={value.source_ref.source_id + ':' + index} style={k.candidate}><Text style={s.label}>{value.statement}</Text><Text selectable style={s.small}>{value.source_url}</Text><Text style={k.quote}>{value.exact_quote}</Text><Text style={s.small}>{human(value.mechanic)} · human-reviewed design reference · truth not verified · training not authorized</Text></View>)}
    </View>
    <View style={s.card}><Text style={s.heading}>Source-bound review inbox</Text><View style={s.row}>{([
      [undefined, 'All'], ['pending_review', 'Needs review'], ['approved', 'Approved design references'], ['rejected', 'Rejected'],
    ] as const).map(([state, label]) => <Button key={label} label={label} primary={filter === state} disabled={!!busy || loading} press={() => { setFilter(state); setSelected(null); }} />)}</View>
      {!candidates.length && <Text style={s.small}>No candidates were returned for this filter. Select a passage from a captured source to prepare one.</Text>}
      {candidates.map(value => <TouchableOpacity key={value.candidate_id} accessibilityRole="button" accessibilityState={{ selected: selected?.candidate_id === value.candidate_id }}
        disabled={!!busy} onPress={() => { run('Opening current source-bound candidate', async signal => { const current = await getDragonCandidate(value.candidate_id, signal); if (safe() && !signal.aborted) accept(current); }); }} style={[k.candidate, selected?.candidate_id === value.candidate_id && k.selected]}>
        <Text style={s.label}>{value.statement}</Text><Text style={s.small}>{human(value.state)} · {human(value.mechanic)}</Text><Text numberOfLines={2} style={s.small}>{value.title || value.source_url}</Text>
      </TouchableOpacity>)}
      {cursor && <Button label="Load more review records" disabled={loading || !!busy} press={() => void load(true)} />}
    </View>
    {selected && <View style={s.card}><View style={s.row}><Text style={[s.heading, s.grow]}>Selected design note</Text><View style={s.badge}><Text style={s.badgeText}>{human(selected.state)}</Text></View></View>
      <Text selectable style={s.message}>{selected.statement}</Text><Text selectable style={s.small}>{selected.source_url}</Text><Text selectable style={k.quote}>{selected.exact_quote}</Text>
      <Text style={s.small}>Source-use consent expires {new Date(selected.valid_until).toLocaleString()}. Review confidence is uncalibrated; this is not independently corroborated evidence.</Text>
      {!sourceUnexpired && <Text style={s.error}>Current source use is unavailable{selected.current_source_error ? `: ${human(selected.current_source_error)}` : ''}. New approval or practice cannot use this passage.</Text>}
      {selected.state === 'pending_review' && selected.prepared_review && <View style={k.review}><Text style={s.label}>Saved review awaiting confirmation</Text><Text style={s.message}>{selected.prepared_review.rationale}</Text><Text style={s.small}>{human(selected.prepared_review.decision)} · resumes only this exact previously saved decision, without a new grant.</Text><Button label="Resume saved review" disabled={!!busy || !canWrite || !sourceUnexpired} press={() => { const value = selected; run('Reconciling exact saved review', async signal => { const result = await resumeDragonReview(value, signal); if (safe() && !signal.aborted) { accept(result); setNotice('The original saved review was reconciled through its canonical owner.'); } }); }} /></View>}{selected.state === 'pending_review' && !selected.prepared_review && <View style={k.stack}><Text style={s.label}>Human review rationale</Text><TextInput accessibilityLabel="Human review rationale" value={rationale} onChangeText={setRationale} multiline maxLength={2048} editable={!busy} style={[k.input, { minHeight: 90 }]} placeholderTextColor={C.muted} placeholder="Explain the design-use decision and any limitations." />
        <Text style={s.label}>Permission reference for design use</Text><TextInput accessibilityLabel="Design-use permission reference" value={rightsRef} onChangeText={setRightsRef} maxLength={128} editable={!busy} style={k.input} placeholder="operator-research-design-consent" placeholderTextColor={C.muted} />
        <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: rights, disabled: !!busy }} disabled={!!busy} onPress={() => setRights(value => !value)} style={k.consent}><Ionicons name={rights ? 'checkbox-outline' : 'square-outline'} size={23} color={C.accent} /><Text style={[s.message, s.grow]}>I have permission to retain and use this exact source as a research and design reference. This does not grant model-training rights.</Text></TouchableOpacity>
        <View style={s.row}><Button label="Approve design reference" primary disabled={!!busy || !canWrite || !sourceUnexpired || !readiness?.capabilities.source_review || !rationale.trim() || !rightsRef.trim() || !rights} press={() => review('approve_design_reference')} /><Button label="Reject candidate" disabled={!!busy || !canWrite || !rationale.trim()} press={() => review('reject')} /></View>
      </View>}
      {selected.review && <View style={k.review}><Text style={s.label}>Recorded human decision</Text><Text style={s.message}>{selected.review.rationale}</Text><Text style={s.small}>{human(selected.review.decision)} · {new Date(selected.review.reviewed_at).toLocaleString()} · training not authorized</Text></View>}
      {selected.state === 'approved' && <View style={k.stack}><Text style={s.label}>Measured local reference practice</Text><Text style={s.small}>{supported ? 'Run the fixed original 8-bit reference environment for this supported mechanic. It measures local steps and rewards, not the source game or the truth of the web statement.' : 'This mechanic has no measured local practice adapter. Its reviewed design reference remains inspectable.'}</Text>
        {supported && <><View style={s.row}><View style={k.field}><Text style={s.small}>Practice steps (16–512)</Text><TextInput accessibilityLabel="Dragon practice steps" value={steps} onChangeText={setSteps} keyboardType="number-pad" maxLength={3} style={k.input} editable={!busy} /></View><View style={k.field}><Text style={s.small}>Seed</Text><TextInput accessibilityLabel="Dragon practice seed" value={seed} onChangeText={setSeed} keyboardType="number-pad" maxLength={10} style={k.input} editable={!busy} /></View></View>
          <TouchableOpacity accessibilityRole="checkbox" accessibilityState={{ checked: practiceConsent, disabled: !!busy }} disabled={!!busy} onPress={() => setPracticeConsent(value => !value)} style={k.consent}><Ionicons name={practiceConsent ? 'checkbox-outline' : 'square-outline'} size={23} color={C.accent} /><Text style={[s.message, s.grow]}>Run this bounded local reference exercise and retain its actual observation receipt.</Text></TouchableOpacity>
          <Button label="Run measured reference practice" primary disabled={!!busy || !sourceUnexpired || !practiceConsent || !readiness?.capabilities.measured_local_practice} press={practice} /></>}
      </View>}
      {selected.state === 'approved' && <View style={k.stack}><Button label="Read saved practice receipts" disabled={!!busy} press={() => {
        const candidateId = selected.candidate_id; run('Reading actual practice history', async signal => { const values = await getDragonPracticeHistory(candidateId, signal); if (safe() && !signal.aborted) setPracticeHistory(values); });
      }} />{practiceHistory.map(value => <TouchableOpacity key={value.practice_id} accessibilityRole="button" disabled={!!busy} onPress={() => setReceipt(value)} style={k.candidate}><Text style={s.label}>{value.steps} actual steps · return {finite(value.return)}</Text><Text style={s.small}>{human(value.status)} · retained reference attempt</Text></TouchableOpacity>)}</View>}
      <Button label={inspect ? 'Hide evidence identities' : 'Inspect source and review identities'} press={() => setInspect(value => !value)} />
      {inspect && <Text selectable style={k.code}>{JSON.stringify(selected, null, 2).slice(0, 16000)}</Text>}
    </View>}
    {receipt && <View style={s.card}><View style={s.row}><Text style={[s.heading, s.grow]}>Actual practice result</Text><View style={s.badge}><Text style={s.badgeText}>{human(receipt.status)}</Text></View></View>
      <View style={s.row}><View style={k.metric}><Text style={s.small}>Executed steps</Text><Text style={k.value}>{receipt.steps}</Text></View><View style={k.metric}><Text style={s.small}>Measured return</Text><Text style={k.value}>{finite(receipt.return)}</Text></View></View>
      {Object.entries(receipt.reward_components || {}).map(([name, value]) => <Text key={name} style={s.message}>{human(name)}: {finite(value)}</Text>)}
      {receipt.error_code && <Text style={s.error}>{human(receipt.error_code)}</Text>}{receipt.preview && <GameLearningFrame frame={receipt.preview} />}
      <Text style={s.small}>Original local reference environment · no source-game emulation, mastery, factual-verification or model-training claim.</Text>
      {typeof receipt.lesson === 'string' && <Text style={s.message}>{receipt.lesson}</Text>}
      <Button label="Inspect actual practice evidence" press={() => setInspect(value => !value)} />{inspect && <Text selectable style={k.code}>{JSON.stringify(receipt, null, 2).slice(0, 16000)}</Text>}
    </View>}
  </View>;
}
const k = StyleSheet.create({
  stack: { gap: 16 }, primary: { borderColor: C.accent, backgroundColor: '#29203e' },
  input: { minHeight: 44, borderWidth: 1, borderColor: C.edge, borderRadius: 9, color: C.text, backgroundColor: C.bg, padding: 12, textAlignVertical: 'top' },
  quote: { color: C.text, fontSize: 14, lineHeight: 23, backgroundColor: C.bg, borderLeftWidth: 3, borderColor: C.accent, padding: 14 },
  candidate: { borderWidth: 1, borderColor: C.edge, borderRadius: 11, padding: 14, gap: 7 }, selected: { borderColor: C.accent, backgroundColor: '#251f38' },
  consent: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, minHeight: 44, paddingVertical: 8 }, field: { flex: 1, minWidth: 120, gap: 6 },
  review: { borderTopWidth: 1, borderColor: C.edge, paddingTop: 14, gap: 7 }, metric: { flex: 1, minWidth: 120, gap: 6 }, value: { color: C.text, fontSize: 25, fontWeight: '700' },
  code: { color: C.muted, fontFamily: 'monospace', fontSize: 12, lineHeight: 19, backgroundColor: C.bg, padding: 12, borderRadius: 9 },
});
