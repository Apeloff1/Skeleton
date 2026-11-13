import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { getAuthToken } from '../../auth/gameforgeAuth';
import { ChatClientError } from '../../product/chatErrors';
import { authorizeWorkflowTemplate, getAIWorkflowCatalog, workflowTemplateSummary, type WorkflowCatalogObservation, type WorkflowSurface, type WorkflowTemplate } from '../../product/aiWorkflowClient';
import { useStudioForeground } from './useStudioForeground';

export type WorkflowTemplatePickerProps = {
  surface: WorkflowSurface; disabled?: boolean;
  contextKey?: string;
  onApply: (template: WorkflowTemplate) => void | Promise<void>;
  unavailableReason?: (template: WorkflowTemplate) => string | null;
};

/** Scoped ephemeral form configuration. It never creates or advances a workflow. */
export default function WorkflowTemplatePicker({ surface, disabled = false, contextKey = '', onApply, unavailableReason }: WorkflowTemplatePickerProps) {
  const foreground = useStudioForeground();
  const { height } = useWindowDimensions();
  const [expanded, setExpanded] = useState(false);
  const [observed, setObserved] = useState<WorkflowCatalogObservation | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [accountEpoch, setAccountEpoch] = useState(0);
  const request = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const mounted = useRef(true);
  const token = useRef(getAuthToken());
  const active = useRef(false);
  const applying = useRef(false);
  const callbacks = useRef({ onApply, unavailableReason });
  callbacks.current = { onApply, unavailableReason };
  const context = useRef({ surface, key: contextKey });
  context.current = { surface, key: contextKey };
  const previousContext = useRef(context.current);
  active.current = expanded && foreground;
  const blocked = useRef(disabled);
  blocked.current = disabled;

  const clear = useCallback(() => {
    generation.current += 1; request.current?.abort(); request.current = null; applying.current = false;
    setObserved(null); setBusy(null); setError(null); setNotice(null);
  }, []);
  useEffect(() => {
    mounted.current = true;
    const timer = setInterval(() => {
      if (token.current === getAuthToken()) return;
      token.current = getAuthToken(); clear(); setAccountEpoch(epoch => epoch + 1);
    }, 1000);
    return () => { mounted.current = false; clearInterval(timer); generation.current += 1; request.current?.abort(); };
  }, [clear]);
  const refresh = useCallback(async () => {
    if (!active.current || applying.current) return;
    const epoch = ++generation.current;
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    const captured = getAuthToken(); token.current = captured;
    setBusy('catalog'); setError(null); setNotice(null); setObserved(null);
    const current = () => mounted.current && active.current && !controller.signal.aborted && generation.current === epoch && captured === getAuthToken();
    try {
      const value = await getAIWorkflowCatalog(controller.signal);
      if (current()) setObserved(value);
    } catch (cause) {
      if (current()) setError(cause instanceof Error ? cause.message : 'Workflow templates could not be loaded.');
    } finally {
      if (current()) { setBusy(null); request.current = null; }
    }
  }, []);
  useEffect(() => {
    if (!expanded || !foreground) { clear(); return; }
    void refresh();
    return () => { generation.current += 1; request.current?.abort(); };
  }, [surface, expanded, foreground, accountEpoch, clear, refresh]);
  useEffect(() => {
    if (!disabled || !applying.current) return;
    generation.current += 1; request.current?.abort(); request.current = null; applying.current = false; setBusy(null);
  }, [disabled]);
  useEffect(() => {
    const previous = previousContext.current;
    previousContext.current = context.current;
    if (previous.surface === surface && previous.key === contextKey || !applying.current) return;
    generation.current += 1; request.current?.abort(); applying.current = false; request.current = null;
    setBusy(null); setNotice(null); setError('The draft or selected model changed. Review the template for the current form before applying it again.');
  }, [surface, contextKey]);

  const apply = async (selected: WorkflowTemplate) => {
    if (!active.current || blocked.current || applying.current || busy || !observed || selected.surface !== surface) return;
    const reason = callbacks.current.unavailableReason?.(selected);
    if (reason) { setError(reason); return; }
    const controller = new AbortController(); request.current = controller;
    const epoch = ++generation.current;
    const origin = context.current;
    applying.current = true; setBusy(selected.template_id); setError(null); setNotice(null);
    const current = () => mounted.current && active.current && !blocked.current && !controller.signal.aborted
      && generation.current === epoch && observed.scope.token === getAuthToken()
      && context.current.surface === origin.surface && context.current.key === origin.key;
    try {
      const fresh = await authorizeWorkflowTemplate(observed, selected, controller.signal);
      if (!current()) return;
      const rejection = callbacks.current.unavailableReason?.(fresh);
      if (rejection) throw new ChatClientError(rejection, { kind: 'validation', retryable: false });
      await callbacks.current.onApply(fresh);
      if (current()) setNotice(`${fresh.title} settings staged. Review the form before submitting.`);
    } catch (cause) {
      if (current()) {
        setError(cause instanceof Error ? cause.message : 'The template settings could not be staged.');
        if (cause instanceof ChatClientError && ['authorization', 'conflict'].includes(cause.kind)) setObserved(null);
      }
    } finally {
      if (mounted.current && generation.current === epoch) { setBusy(null); applying.current = false; request.current = null; }
    }
  };
  const visible = expanded && foreground && observed?.scope.token === getAuthToken() ? observed : null;
  const templates = visible?.catalog.templates.filter(item => item.surface === surface) ?? [];
  return <View style={s.panel}>
    <TouchableOpacity accessibilityRole="button" accessibilityState={{ expanded }} onPress={() => setExpanded(value => !value)} style={s.header}>
      <View style={s.copy}><Text style={s.title}>Workflow templates</Text><Text style={s.caption}>Bounded starting settings for this form</Text></View><Text style={s.action}>{expanded ? 'Hide' : 'Browse'}</Text>
    </TouchableOpacity>
    {expanded && <ScrollView nestedScrollEnabled keyboardShouldPersistTaps="handled" style={{ maxHeight: Math.min(320, Math.max(120, height * .3)) }} contentContainerStyle={s.body}>
      <Text style={s.caption}>Applying a template stages budget settings only. Your content, model selection, permissions and consent stay in your control. Nothing starts until you submit the form.</Text>
      {!foreground && <Text style={s.caption}>Return to this screen to inspect templates.</Text>}
      {busy === 'catalog' && <View style={s.row}><ActivityIndicator size="small" color="#c4b5fd" /><Text style={s.caption}>Reading the scoped template catalog…</Text></View>}
      {templates.map(item => {
        const reason = unavailableReason?.(item);
        const unavailable = disabled || !!busy || !!reason;
        return <View style={s.template} key={item.template_id}>
          <Text style={s.title}>{item.title}</Text><Text style={s.caption}>{item.description}</Text>
          {workflowTemplateSummary(item).map(line => <Text key={line} style={s.budget}>{line}</Text>)}
          {item.requirements.map(requirement => <Text style={s.caption} key={requirement}>• {requirement}</Text>)}
          {reason && <Text style={s.warning}>{reason}</Text>}
          <TouchableOpacity accessibilityRole="button" accessibilityLabel={`Apply ${item.title} settings`} accessibilityState={{ disabled: unavailable }} disabled={unavailable} onPress={() => { void apply(item); }} style={[s.button, unavailable && s.disabled]}><Text style={s.action}>{busy === item.template_id ? 'Checking current template…' : 'Apply settings'}</Text></TouchableOpacity>
        </View>;
      })}
      {visible && !templates.length && <Text style={s.caption}>This catalog has no templates for this form.</Text>}
      {error && <Text accessibilityRole="alert" style={s.error}>{error}</Text>}
      {notice && <Text accessibilityLiveRegion="polite" style={s.notice}>{notice}</Text>}
      {foreground && <TouchableOpacity accessibilityRole="button" accessibilityState={{ disabled: !!busy }} disabled={!!busy} onPress={() => { void refresh(); }} style={[s.button, !!busy && s.disabled]}><Text style={s.action}>Reload templates</Text></TouchableOpacity>}
    </ScrollView>}
  </View>;
}

const s = StyleSheet.create({
  panel: { gap: 8, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#334155', paddingTop: 8 }, body: { gap: 8 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 44 }, copy: { flex: 1, gap: 3 },
  title: { color: '#e2e8f0', fontWeight: '600', fontSize: 12, lineHeight: 18 }, caption: { color: '#94a3b8', fontSize: 11, lineHeight: 17 },
  action: { color: '#ddd6fe', fontWeight: '600', fontSize: 11 }, row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  template: { backgroundColor: '#111c30', borderWidth: 1, borderColor: '#334155', borderRadius: 9, padding: 10, gap: 6 },
  budget: { color: '#c4b5fd', fontSize: 11, lineHeight: 17 }, button: { alignSelf: 'flex-start', justifyContent: 'center', minHeight: 40, borderRadius: 8, borderWidth: 1, borderColor: '#51406f', backgroundColor: '#211c38', paddingHorizontal: 12 },
  disabled: { opacity: .4 }, warning: { color: '#fcd34d', fontSize: 11, lineHeight: 17 }, error: { color: '#fca5a5', fontSize: 11, lineHeight: 17 }, notice: { color: '#86efac', fontSize: 11, lineHeight: 17 },
});
