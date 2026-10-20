import React, { useMemo, useState } from 'react';
import { StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { ChatClientError } from '../../product/chatErrors';
import { runtimePolicyFieldBounds, validateRuntimePolicyChange, type RuntimeControlChange, type RuntimeControlObservation, type RuntimePolicySection, type RuntimePolicyValues } from '../../product/runtimeOptimizationClient';

type Draft = Partial<Record<RuntimePolicySection, Record<string, string | boolean>>>;
const SECTIONS: RuntimePolicySection[] = ['serving', 'learning', 'maintenance'];
const TITLES = { serving: 'Selected model serving', learning: 'Tenant operational learning', maintenance: 'Host idle maintenance' };
function title(name: string): string { return name.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase()); }
function Action({ label, disabled, onPress }: { label: string; disabled?: boolean; onPress: () => void }) {
  return <TouchableOpacity accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={onPress} style={[s.button, disabled && s.disabled]}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>;
}

/** Ephemeral policy drafts only. The server's catalog and CAS own admission. */
export default function RuntimePolicyEditor({ observed, servingRouteId, disabled, maintenanceDisabled, onApply }: {
  observed: RuntimeControlObservation; servingRouteId?: string; disabled: boolean; maintenanceDisabled: boolean;
  onApply: (change: RuntimeControlChange, expectedVersion: number, routeId?: string) => Promise<boolean>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [section, setSection] = useState<RuntimePolicySection>('serving');
  const [base, setBase] = useState<{ observation: RuntimeControlObservation; routeId?: string } | null>(null);
  const [draft, setDraft] = useState<Draft>({});
  const controls = observed.state.policy_controls;
  const origin = base?.observation ?? observed;
  const routeId = base ? base.routeId : servingRouteId;
  const originLimits = routeId ? origin.state.policy_controls?.serving.route_limits?.[routeId] : origin.state.policy_controls?.serving.global_limits;
  const currentLimits = servingRouteId ? observed.state.policy_controls?.serving.route_limits?.[servingRouteId] : observed.state.policy_controls?.serving.global_limits;
  const stale = !!base && (base.observation.state.policy_version !== observed.state.policy_version || base.routeId !== servingRouteId
    || originLimits?.max_concurrency !== currentLimits?.max_concurrency || originLimits?.max_queue_size !== currentLimits?.max_queue_size
    || base.observation.scope.principalId !== observed.scope.principalId || base.observation.scope.tenantId !== observed.scope.tenantId
    || (base.routeId ? base.observation.state.serving.models?.find(row => row.route_id === base.routeId)?.model_digest : undefined) !== (servingRouteId ? observed.state.serving.models?.find(row => row.route_id === servingRouteId)?.model_digest : undefined));
  const values = (part: RuntimePolicySection): RuntimePolicyValues | undefined => part === 'serving' && routeId ? origin.state.serving.models?.find(row => row.route_id === routeId)?.policy : origin.state[part].policy;
  const preparation = useMemo(() => {
    const change: RuntimeControlChange = {};
    const errors: string[] = [];
    let changes = 0;
    for (const part of SECTIONS) {
      const original = part === 'serving' && routeId ? origin.state.serving.models?.find(row => row.route_id === routeId)?.policy : origin.state[part].policy;
      const patch: RuntimePolicyValues = {};
      for (const [name, text] of Object.entries(draft[part] ?? {})) {
        const field = origin.state.policy_controls?.[part].fields[name];
        if (!field) { errors.push(`${title(name)} is no longer declared.`); continue; }
        if (typeof text === 'string' && (!text.trim() || !/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(text.trim()))) { errors.push(`${title(name)} needs a finite number.`); continue; }
        const value = typeof text === 'boolean' ? text : Number(text);
        if (value !== original?.[name]) { patch[name] = value; changes += 1; }
      }
      if (Object.keys(patch).length) change[part] = patch;
    }
    if (change.serving && routeId) change.serving_route_id = routeId;
    try { if (changes) validateRuntimePolicyChange(origin, change); } catch (cause) { errors.push(cause instanceof ChatClientError ? cause.message : 'The draft does not match the observed policy bounds.'); }
    return { change, changes, errors };
  }, [draft, origin, routeId]);
  const reset = () => { setBase(null); setDraft({}); };
  const edit = (part: RuntimePolicySection, name: string, value: string | boolean) => {
    if (disabled || stale || part === 'maintenance' && maintenanceDisabled) return;
    if (!base) setBase({ observation: observed, routeId: servingRouteId });
    setDraft(current => ({ ...current, [part]: { ...current[part], [name]: value } }));
  };
  if (!controls) return <Text style={s.caption}>Advanced policy fields have not been reported by this engine.</Text>;
  const fields = origin.state.policy_controls?.[section].fields ?? {};
  const unavailable = !controls[section].available || observed.state[section].available === false;
  const blocked = disabled || stale || unavailable || section === 'maintenance' && maintenanceDisabled;
  const changedMaintenanceBlocked = maintenanceDisabled && !!preparation.change.maintenance;
  const reductions = Object.entries(preparation.change.learning ?? {}).some(([name, value]) => ['replay_capacity', 'partition_limit', 'retained_outcomes', 'outcome_max_age_days', 'maintenance_receipt_retention'].includes(name) && typeof value === 'number' && typeof origin.state.learning.policy?.[name] === 'number' && value < Number(origin.state.learning.policy[name]));
  return <View style={s.panel}>
    <TouchableOpacity accessibilityRole="button" accessibilityState={{ expanded }} onPress={() => setExpanded(value => !value)} style={s.header}><View style={s.copy}><Text style={s.title}>Advanced runtime policy</Text><Text style={s.caption}>{preparation.changes ? `${preparation.changes} staged changes · based on policy ${origin.state.policy_version}` : 'Serving, replay, retention, fairness and bounded housekeeping'}</Text></View><Text style={s.buttonText}>{expanded ? 'Hide' : 'Configure'}</Text></TouchableOpacity>
    {expanded && <>
      <Text style={s.caption}>Values and bounds come from this engine. Serving and maintenance affect the host; learning affects your tenant. Apply saves only the changed fields against the observed policy version.</Text>
      <View style={s.actions}>{SECTIONS.map(part => <TouchableOpacity key={part} accessibilityRole="button" accessibilityState={{ selected: section === part }} onPress={() => setSection(part)} style={[s.tab, section === part && s.selected]}><Text style={s.buttonText}>{part === 'serving' ? 'Serving' : part === 'learning' ? 'Learning' : 'Maintenance'}</Text></TouchableOpacity>)}</View>
      <Text style={s.title}>{TITLES[section]}</Text>
      {section === 'serving' && <Text style={s.caption}>{routeId ?? 'All legacy/default local serving routes'} · controls remain inside activated operator concurrency and queue ceilings.</Text>}
      {unavailable && <Text style={s.warning}>This policy owner is unavailable. The observed fields are read-only.</Text>}
      {stale && <Text accessibilityRole="alert" style={s.warning}>The policy version, selected model or operator limits changed while this draft was open. Discard the draft, review the current values and prepare your changes again.</Text>}
      {Object.entries(fields).map(([name, field]) => {
        const original = values(section)?.[name];
        const value = draft[section]?.[name] ?? original;
        const seen = field.type === 'boolean' ? typeof original === 'boolean' : typeof original === 'number' && Number.isFinite(original);
        const bounds = runtimePolicyFieldBounds(field, section, name, origin.state.policy_controls!, routeId);
        const hasCapacity = bounds.min === undefined || bounds.max === undefined || bounds.min <= bounds.max;
        const inputDisabled = blocked || !seen;
        const changed = Object.hasOwn(draft[section] ?? {}, name) && (typeof value === 'boolean' ? value : Number(value)) !== original;
        return <View key={name} style={[s.field, changed && s.changed]}><View style={s.fieldHeader}><Text style={s.fieldTitle}>{title(name)}{changed ? ' · changed' : ''}</Text>{field.type === 'boolean' ? <Switch accessibilityLabel={title(name)} value={value === true} disabled={inputDisabled} onValueChange={next => edit(section, name, next)} trackColor={{ false: '#334155', true: '#6d28d9' }} /> : <TextInput accessibilityLabel={title(name)} editable={!inputDisabled && hasCapacity} value={seen ? String(value ?? '') : ''} placeholder="Not observed" placeholderTextColor="#64748b" keyboardType="numeric" inputMode="decimal" maxLength={32} selectTextOnFocus onChangeText={next => edit(section, name, next)} style={[s.input, (inputDisabled || !hasCapacity) && s.disabled]} />}</View><Text style={s.caption}>{field.description}</Text><Text style={s.bound}>{seen ? `Current: ${String(original)}` : 'No canonical current value reported'}{field.type === 'boolean' ? '' : hasCapacity ? ` · ${bounds.min}–${bounds.max} ${field.unit} · ${field.type === 'integer' ? 'whole numbers' : 'finite numbers'}` : ' · No activated operator capacity is available for this field'}</Text></View>;
      })}
      {!!controls[section].constraints.length && <Text style={s.caption}>Constraints: {controls[section].constraints.join('; ')}.</Text>}
      {reductions && <Text style={s.warning}>This draft reduces numeric replay or retention. The owning service may trim derived records during bounded updates; lowering retention does not remove canonical results or grant new learning authority.</Text>}
      {preparation.errors.slice(0, 4).map((message, index) => <Text key={index} accessibilityRole="alert" style={s.warning}>{message}</Text>)}
      <View style={s.actions}><Action label={`Apply ${preparation.changes || ''} staged ${preparation.changes === 1 ? 'change' : 'changes'}`} disabled={disabled || stale || !preparation.changes || !!preparation.errors.length || changedMaintenanceBlocked} onPress={() => { void onApply(preparation.change, origin.state.policy_version, routeId).then(confirmed => { if (confirmed) reset(); }); }} /><Action label={stale ? 'Discard and load current values' : 'Discard draft'} disabled={disabled} onPress={reset} /></View>
      {observed.scope.role !== 'admin' && <Text style={s.caption}>An administrator account is required to change runtime policy.</Text>}
    </>}
  </View>;
}

const s = StyleSheet.create({
  panel: { borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: '#334155', paddingTop: 12, gap: 10 }, header: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 44 }, copy: { flex: 1, gap: 3 }, title: { color: '#e2e8f0', fontSize: 12, lineHeight: 19, fontWeight: '600' }, caption: { color: '#94a3b8', fontSize: 11, lineHeight: 17 }, bound: { color: '#a5b4cc', fontSize: 10, lineHeight: 16 }, actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 }, tab: { minHeight: 40, paddingHorizontal: 12, justifyContent: 'center', backgroundColor: '#152034', borderRadius: 8, borderWidth: 1, borderColor: '#334155' }, selected: { borderColor: '#a78bfa', backgroundColor: '#251e3d' }, button: { minHeight: 44, paddingHorizontal: 12, justifyContent: 'center', backgroundColor: '#211c38', borderRadius: 8, borderWidth: 1, borderColor: '#4c4274' }, buttonText: { color: '#ddd6fe', fontWeight: '600', fontSize: 11 }, field: { padding: 10, gap: 5, borderRadius: 9, backgroundColor: '#111c30', borderWidth: 1, borderColor: '#27364c' }, changed: { borderColor: '#7c5cb5' }, fieldHeader: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center', justifyContent: 'space-between' }, fieldTitle: { flex: 1, minWidth: 150, color: '#cbd5e1', fontSize: 11, lineHeight: 17, fontWeight: '600' }, input: { minHeight: 42, width: 130, borderWidth: 1, borderColor: '#475569', borderRadius: 7, paddingHorizontal: 10, color: '#f1f5f9', fontSize: 12, backgroundColor: '#0b1425' }, disabled: { opacity: .4 }, warning: { color: '#fcd34d', fontSize: 11, lineHeight: 17 },
});
