import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Text, View } from 'react-native';
import { getAuthEpoch, subscribeAuthChanges } from '../../../auth/gameforgeAuth';
import { getJourneyCatalog, prepareJourneyDraft, type JourneyCatalog, type JourneyDraft } from '../../../product/aiJourneyClient';
import { workbenchStore } from '../workbench/store';
import type { Source } from '../workbench/types';
import { JourneyButton, JourneyDialog, JourneyField, colors, human, ui } from './journeyUI';
import type { JourneyId, JourneyRequest } from './journeyDraft';

const COPY: Record<JourneyId, { icon: string; outcome: string }> = {
  research: { icon: '◈', outcome: 'Compare evidence → save a cited notebook entry' },
  plan: { icon: '↗', outcome: 'Define a goal → prove the task graph → save tasks' },
  creative: { icon: '✦', outcome: 'Explore a direction → review story, cast, quests or scenes' },
  study: { icon: '▤', outcome: 'Understand a concept → edit cards → practice later' },
  studio: { icon: '⌘', outcome: 'Inspect a project → review a scoped production goal' },
};
export default function GuidedJourneysPanel({ getDraft, onStage, disabled = false, projectId, maxOutputTokens }: {
  getDraft: () => string;
  onStage: (draft: JourneyDraft, expectedDraft: string, mode: 'append' | 'replace', useBudget: boolean) => void | Promise<void>;
  disabled?: boolean; projectId?: string; maxOutputTokens?: number;
}) {
  const [open, setOpen] = useState(false);
  const [catalog, setCatalog] = useState<JourneyCatalog | null>(null);
  const [chosen, setChosen] = useState<JourneyId>('research');
  const [goal, setGoal] = useState('');
  const [options, setOptions] = useState<Record<string, string | number>>({});
  const [sources, setSources] = useState<Source[]>([]);
  const [selectedSources, setSelectedSources] = useState<string[]>([]);
  const [prepared, setPrepared] = useState<JourneyDraft | null>(null);
  const [reviewedDraft, setReviewedDraft] = useState('');
  const [budget, setBudget] = useState(false);
  const [showExact, setShowExact] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const active = useRef(false); const generation = useRef(0); const abort = useRef<AbortController | null>(null);
  const callbacks = useRef({ getDraft, onStage, disabled }); callbacks.current = { getDraft, onStage, disabled };
  const clearPreview = () => { generation.current += 1; abort.current?.abort(); setPrepared(null); setBusy(false); setError(''); setNotice(''); };
  useEffect(() => subscribeAuthChanges(() => { generation.current += 1; abort.current?.abort(); active.current = false; setOpen(false); setCatalog(null); setGoal(''); setPrepared(null); setSelectedSources([]); setSources([]); setError(''); setNotice(''); setBusy(false); }), []);
  useEffect(() => () => { active.current = false; generation.current += 1; abort.current?.abort(); }, []);
  const load = async () => {
    const id = ++generation.current; const epoch = getAuthEpoch(); abort.current?.abort(); const controller = new AbortController(); abort.current = controller;
    setBusy(true); setError('');
    try {
      const [value] = await Promise.all([getJourneyCatalog(controller.signal), workbenchStore.initialize()]);
      if (!active.current || generation.current !== id || epoch !== getAuthEpoch()) return;
      setCatalog(value); setOptions(value.journeys.find(item => item.journey_id === chosen)?.default_options || {});
      const state = workbenchStore.getSnapshot().state;
      const destination = projectId || state.activeProjectId;
      setSources(state.sources.filter(item => item.projectId === destination)); setSelectedSources([]);
    } catch (cause) { if (active.current && generation.current === id && epoch === getAuthEpoch()) setError(cause instanceof Error ? cause.message : 'Guided journeys could not be opened.'); }
    finally { if (active.current && generation.current === id) setBusy(false); }
  };
  const show = () => { active.current = true; setOpen(true); setPrepared(null); setNotice(''); void load(); };
  const close = () => { active.current = false; generation.current += 1; abort.current?.abort(); setBusy(false); setOpen(false); };
  const choose = (id: JourneyId) => { clearPreview(); setChosen(id); setOptions(catalog?.journeys.find(item => item.journey_id === id)?.default_options || {}); };
  const definition = catalog?.journeys.find(item => item.journey_id === chosen);
  const prepare = async () => {
    if (busy || !definition || !goal.trim() || callbacks.current.disabled) return;
    const id = ++generation.current; const epoch = getAuthEpoch(); abort.current?.abort(); const controller = new AbortController(); abort.current = controller;
    const original = callbacks.current.getDraft(); setBusy(true); setError(''); setNotice(''); setPrepared(null);
    const request: JourneyRequest = { journey_id: chosen, goal, options,
      source_refs: selectedSources.map((sourceId, index) => { const source = sources.find(item => item.id === sourceId)!; return { id: 'source-' + (index + 1), label: source.title, locator: source.locator.slice(0, 512) || 'No locator supplied', excerpt: source.excerpt.slice(0, 800) }; }) };
    try {
      const draft = await prepareJourneyDraft(request, controller.signal);
      if (!active.current || generation.current !== id || epoch !== getAuthEpoch() || callbacks.current.disabled) return;
      setPrepared(draft); setReviewedDraft(original); setBudget(false); setShowExact(false);
    } catch (cause) { if (active.current && generation.current === id && epoch === getAuthEpoch()) setError(cause instanceof Error ? cause.message : 'The journey could not be prepared.'); }
    finally { if (active.current && generation.current === id) setBusy(false); }
  };
  const apply = async (mode: 'append' | 'replace') => {
    if (!prepared || busy || callbacks.current.disabled) return;
    const id = ++generation.current; const epoch = getAuthEpoch(); setBusy(true); setError('');
    try {
      await callbacks.current.onStage(prepared, reviewedDraft, mode, budget);
      if (!active.current || generation.current !== id || epoch !== getAuthEpoch()) return;
      setNotice('The reviewed request is in your message. Read it, then use Send when ready.'); setPrepared(null);
    } catch (cause) { if (active.current && generation.current === id && epoch === getAuthEpoch()) setError(cause instanceof Error ? cause.message : 'The draft was not staged.'); }
    finally { if (active.current && generation.current === id) setBusy(false); }
  };
  return <><JourneyButton label="Guided journeys" onPress={show} disabled={disabled} testID="journey-open" />{open && <JourneyDialog title="Make something useful" close={close}>
    <Text style={ui.muted}>Choose an outcome, shape the request, and review the result before saving it to your work. Your existing chat and studio tools stay in charge of execution.</Text>
    <View style={ui.row}>{catalog?.journeys.map(item => <View key={item.journey_id} style={[ui.card, { flexGrow: 1, flexBasis: 240 }, chosen === item.journey_id && ui.selected]}><Text style={ui.title}>{COPY[item.journey_id].icon} {item.title}</Text><Text style={ui.muted}>{COPY[item.journey_id].outcome}</Text><JourneyButton label={'Choose ' + item.title} selected={chosen === item.journey_id} onPress={() => choose(item.journey_id)} disabled={busy} testID={'journey-choose-' + item.journey_id} /></View>)}</View>
    {definition && <><JourneyField label="What would you like to accomplish?" testID="journey-goal" value={goal} multiline onChange={value => { clearPreview(); setGoal(value); }} disabled={busy} /><View style={ui.card}><Text style={ui.title}>Shape the outcome</Text>{Object.entries(definition.options).map(([key, option]) => <View style={ui.stack} key={key}><Text style={ui.label}>{option.label || human(key)}</Text>{option.type === 'choice' ? <View style={ui.row}>{option.choices?.map(value => <JourneyButton key={value} label={human(value)} selected={options[key] === value} disabled={busy} onPress={() => { clearPreview(); setOptions(previous => ({ ...previous, [key]: value })); }} testID={'journey-option-' + key + '-' + value} />)}</View> : <JourneyField label={`${human(key)} (${option.minimum}–${option.maximum})`} value={String(options[key] ?? '')} numeric disabled={busy} testID={'journey-option-' + key} onChange={value => { clearPreview(); setOptions(previous => ({ ...previous, [key]: /^\d+$/.test(value) ? Number(value) : value })); }} />}</View>)}</View>
      <View style={ui.card}><Text style={ui.title}>Sources you choose</Text><Text style={ui.muted}>These are the only extra source excerpts this journey adds. Existing conversation context and captured-context settings still apply when you send. Each selection shows the exact text sent to Jeeves. Up to eight sources.</Text>{!sources.length && <Text style={ui.muted}>No sources in the selected workbench project. Add references in Workbench, or continue with an explicitly uncited request.</Text>}{sources.map(source => <View key={source.id} style={ui.stack}><JourneyButton label={(selectedSources.includes(source.id) ? '✓ ' : '+ ') + source.title} disabled={busy || !selectedSources.includes(source.id) && selectedSources.length >= 8} selected={selectedSources.includes(source.id)} onPress={() => { clearPreview(); setSelectedSources(previous => previous.includes(source.id) ? previous.filter(item => item !== source.id) : [...previous, source.id]); }} />{selectedSources.includes(source.id) && <Text selectable style={ui.mono}>{source.locator.slice(0, 512)}{'\n'}{source.excerpt.slice(0, 800) || '(No excerpt supplied)'}</Text>}</View>)}</View>
      <JourneyButton label="Prepare request preview" onPress={() => { void prepare(); }} disabled={busy || !goal.trim()} testID="journey-prepare" /></>}
    {prepared && <View style={ui.card} testID="journey-preview"><Text style={ui.title}>Review the exact next message</Text><Text style={ui.muted}>Destination: {human(prepared.destination)} · Suggested answer budget: {prepared.chat_settings.max_tokens.toLocaleString()} tokens · Minimum structured output budget: {prepared.minimum_output_tokens.toLocaleString()} tokens</Text><Text selectable style={ui.text}>{prepared.request.goal}</Text><Text style={ui.muted}>{Object.entries(prepared.options).map(([key, value]) => human(key) + ": " + human(String(value))).join(" · ")}</Text><Text style={ui.muted}>{prepared.source_refs.length} explicitly selected source(s). The request asks for a typed {human(prepared.output_kind)} result.</Text><JourneyButton label={showExact ? "Hide exact message and output structure" : "Inspect exact message and output structure"} onPress={() => setShowExact(value => !value)} testID="journey-inspect-exact" />{showExact && <Text selectable style={ui.mono}>{prepared.prompt}</Text>}<JourneyButton label="Use suggested chat budget too" selected={budget} disabled={busy || maxOutputTokens === undefined || prepared.chat_settings.max_tokens > maxOutputTokens} onPress={() => setBudget(value => !value)} testID="journey-use-budget" />{maxOutputTokens !== undefined && maxOutputTokens < prepared.minimum_output_tokens && <Text style={ui.error}>The current model limit is below this result’s recommended minimum. Choose a model with enough output capacity before sending.</Text>}<View style={ui.row}><JourneyButton label="Append to my message" onPress={() => { void apply('append'); }} disabled={busy || disabled} testID="journey-append" /><JourneyButton label={reviewedDraft ? 'Replace my message with this request' : 'Use this request'} onPress={() => { void apply('replace'); }} disabled={busy || disabled} testID="journey-replace" /></View></View>}
    {busy && <View style={ui.row}><ActivityIndicator color={colors.accent} /><Text style={ui.muted}>Preparing your review…</Text></View>}{error && <Text accessibilityRole="alert" style={ui.error}>{error}</Text>}{notice && <Text accessibilityLiveRegion="polite" style={ui.success}>{notice}</Text>}{!catalog && !busy && <JourneyButton label="Retry journey catalog" onPress={() => { void load(); }} />}
  </JourneyDialog>}</>;
}
