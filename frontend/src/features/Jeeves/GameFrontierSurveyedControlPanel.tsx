/** Surveyed-control editing and operator approval (GF-P0-118).
 *
 * Local operator review only: drafts never apply themselves and nothing is
 * sent to a server. Approval needs a submitted, valid draft and a named operator.
 */
import React from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet } from 'react-native';
import {
  initialSurveyState, applySurveyAction, validateSurvey, hasUnapprovedChanges,
  type SurveyAction, type SightingInput,
} from '../../product/frontierSurveyedControl';

const blankSighting = { sighting_id: '', control_point_id: '', true_bearing_deg: '', distance_m: '', uncertainty_m: '0' };

export default function GameFrontierSurveyedControlPanel({ now = () => Date.now() }: { now?: () => number }) {
  const [state, setState] = React.useState(initialSurveyState);
  const [operator, setOperator] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);
  const [draft, setDraft] = React.useState(blankSighting);
  const [reason, setReason] = React.useState('');
  const issues = validateSurvey(state);

  const act = (action: SurveyAction) => {
    const r = applySurveyAction(state, action, operator, now());
    setError(r.error);
    if (!r.error) setState(r.state);
    return !r.error;
  };
  const addSighting = () => {
    const s: SightingInput = {
      sighting_id: draft.sighting_id.trim(), control_point_id: draft.control_point_id.trim(),
      true_bearing_deg: Number(draft.true_bearing_deg), distance_m: Number(draft.distance_m),
      uncertainty_m: Number(draft.uncertainty_m),
    };
    if (act({ type: 'upsert_sighting', sighting: s })) setDraft(blankSighting);
  };
  const b = state.baseline;
  const editable = state.status !== 'submitted';

  return (
    <View style={s.card} accessibilityLabel="Surveyed control approval">
      <Text style={s.title}>Surveyed control</Text>
      <Text style={s.muted}>Local review. Nothing here is applied or sent until an operator approves it.</Text>
      <Field label="Operator" value={operator} onChange={setOperator} />
      <Text style={s.body}>Status: {state.status}{hasUnapprovedChanges(state) ? ' (unapproved changes)' : ''}</Text>

      <Text style={s.subtitle}>Baseline metadata (WGS84)</Text>
      {(['baseline_id', 'epoch', 'instrument', 'surveyor', 'notes'] as const).map(k => (
        <Field key={k} label={k} value={b[k]} editable={editable}
          onChange={v => act({ type: 'edit_baseline', patch: { [k]: v } })} />
      ))}

      <Text style={s.subtitle}>Sightings ({state.sightings.length})</Text>
      {state.sightings.length ? state.sightings.map(x => (
        <View key={x.sighting_id} style={s.row}>
          <Text style={[s.body, { flex: 1 }]}>{x.sighting_id} → {x.control_point_id}: {x.true_bearing_deg}°, {x.distance_m} m ±{x.uncertainty_m}</Text>
          {editable && <Btn label="Remove" onPress={() => act({ type: 'remove_sighting', sighting_id: x.sighting_id })} />}
        </View>
      )) : <Text style={s.muted}>No sightings yet.</Text>}
      {editable && (
        <>
          {(Object.keys(blankSighting) as (keyof typeof blankSighting)[]).map(k => (
            <Field key={k} label={k} value={draft[k]} onChange={v => setDraft({ ...draft, [k]: v })} />
          ))}
          <Btn label="Add or update sighting" onPress={addSighting} />
        </>
      )}

      {issues.length > 0 && editable && (
        <View>{issues.slice(0, 6).map(i => <Text key={i.field + i.message} style={s.warn}>{i.message}</Text>)}</View>
      )}
      {error && <Text style={s.error} accessibilityRole="alert">{error}</Text>}

      <View style={s.wrap}>
        {editable && <Btn label="Submit for approval" onPress={() => act({ type: 'submit' })} />}
        {state.status === 'submitted' && <>
          <Btn label="Approve" onPress={() => act({ type: 'approve' })} />
          <Btn label="Reject" onPress={() => { if (act({ type: 'reject', reason })) setReason(''); }} />
          <Btn label="Withdraw" onPress={() => act({ type: 'withdraw' })} />
        </>}
        {editable && <Btn label="Revert to approved" onPress={() => act({ type: 'revert' })} />}
      </View>
      {state.status === 'submitted' && <Field label="Rejection reason" value={reason} onChange={setReason} />}

      <Text style={s.subtitle}>Audit trail</Text>
      {state.audit.length ? state.audit.slice(-8).reverse().map(a => (
        <Text key={a.seq} style={s.muted}>#{a.seq} {a.action} by {a.actor} → {a.status_after}{a.reason ? ` (${a.reason})` : ''}</Text>
      )) : <Text style={s.muted}>No actions yet.</Text>}
    </View>
  );
}

function Field({ label, value, onChange, editable = true }: { label: string; value: string; onChange: (v: string) => void; editable?: boolean }) {
  return (
    <View style={s.row}>
      <Text style={[s.muted, { width: 120 }]}>{label}</Text>
      <TextInput style={s.input} value={value} onChangeText={onChange} editable={editable}
        accessibilityLabel={label} autoCapitalize="none" placeholderTextColor="#6b7a90" />
    </View>
  );
}
function Btn({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <TouchableOpacity accessibilityRole="button" onPress={onPress} style={s.btn}>
      <Text style={s.btnText}>{label}</Text>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#111c2e', borderRadius: 12, padding: 14, gap: 8, marginTop: 12 },
  title: { color: '#e8eef8', fontSize: 17, fontWeight: '700' },
  subtitle: { color: '#c8d4e6', fontSize: 14, fontWeight: '600', marginTop: 6 },
  body: { color: '#e8eef8', fontSize: 14 },
  muted: { color: '#8a9ab0', fontSize: 13 },
  warn: { color: '#ffd27a', fontSize: 12 },
  error: { color: '#ff8a8a', fontSize: 13 },
  row: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  input: { flex: 1, color: '#e8eef8', borderColor: '#2a3a55', borderWidth: 1, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 },
  btn: { backgroundColor: '#1d2c46', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 7 },
  btnText: { color: '#e8eef8', fontSize: 13 },
});
