import React, { useEffect, useState } from 'react';
import { Modal, SafeAreaView, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { COOPERATION_ROLES, cooperationModelReady, cooperationStageCount, minimumCooperationTokens,
  type ChatCooperationModel, type ChatCooperationPolicy, type ChatCooperationRole } from '../../product/chatCooperation';

type Props = {
  enabled: boolean; change: (value: boolean) => void; disabled?: boolean; answerTokenLimit?: number; available?: boolean;
  policy: ChatCooperationPolicy; changePolicy: (value: ChatCooperationPolicy) => void;
  models: readonly ChatCooperationModel[]; mainModel?: ChatCooperationModel;
  fieldError: string | null; changeFieldError: (value: string | null) => void;
  issues: readonly string[]; refreshModels: () => Promise<void>;
};
function Choice({ label, selected = false, disabled = false, press }: { label: string; selected?: boolean; disabled?: boolean; press: () => void }) {
  return <TouchableOpacity accessibilityRole="radio" accessibilityLabel={label} accessibilityState={{ checked: selected, disabled }}
    disabled={disabled} onPress={press} style={[s.button, selected && s.selected, disabled && s.disabled]}>
    <Text style={s.label}>{selected ? '● ' : '○ '}{label}</Text>
  </TouchableOpacity>;
}

export default function ChatResponseReviewControl({ enabled, change, disabled = false, answerTokenLimit, available = true,
  policy, changePolicy, models, mainModel, fieldError, changeFieldError, issues, refreshModels }: Props) {
  const [advanced, setAdvanced] = useState(false);
  const [rolePicker, setRolePicker] = useState<ChatCooperationRole | null>(null);
  const [capDraft, setCapDraft] = useState(String(policy.max_stage_output_tokens));
  const [refreshing, setRefreshing] = useState(false);
  const blocked = disabled || !enabled && !available;
  const stageCount = cooperationStageCount(policy);
  const minimum = minimumCooperationTokens(policy);
  useEffect(() => { setCapDraft(String(policy.max_stage_output_tokens)); changeFieldError(null); }, [policy, changeFieldError]);
  useEffect(() => { if (!enabled) { setAdvanced(false); setRolePicker(null); } }, [enabled]);
  const cap = (value: string) => {
    setCapDraft(value); const number = Number(value);
    if (!/^\d+$/.test(value) || !Number.isSafeInteger(number) || number < 64 || number > 4096) {
      changeFieldError('Choose a per-stage ceiling between 64 and 4,096 tokens.'); return;
    }
    changeFieldError(null); changePolicy({ ...policy, max_stage_output_tokens: number });
  };
  const choose = (role: ChatCooperationRole, model?: ChatCooperationModel) => {
    const roles = { ...policy.roles };
    if (model) roles[role] = { provider_id: model.provider_id, model_id: model.model_id }; else delete roles[role];
    changePolicy({ ...policy, roles }); setRolePicker(null);
  };
  const close = () => { setAdvanced(false); setRolePicker(null); };
  const issueText = [fieldError, ...issues].filter((value): value is string => !!value);
  const chosenModels = COOPERATION_ROLES.map(({ role }) => {
    const pair = policy.roles[role];
    return pair ? models.find(model => model.provider_id === pair.provider_id && model.model_id === pair.model_id) : mainModel;
  });
  const knownContexts = [mainModel, ...chosenModels].filter((model): model is ChatCooperationModel => !!model)
    .map(model => model.context_window).filter((value): value is number => typeof value === 'number' && value > 0);
  const sharedContext = mainModel && chosenModels.every(Boolean) && knownContexts.length ? Math.min(...knownContexts) : null;
  const pickedPair = rolePicker ? policy.roles[rolePicker] : null;
  const pickerTitle = COOPERATION_ROLES.find(row => row.role === rolePicker)?.label || '';

  return <View style={s.group}>
    <View style={s.row}>
      <TouchableOpacity accessibilityRole="checkbox" accessibilityLabel="Review and refine the next answer"
        accessibilityState={{ checked: enabled, disabled: blocked }} disabled={blocked} onPress={() => change(!enabled)}
        style={[s.button, enabled && s.selected, blocked && s.disabled]}>
        <Text style={s.label}>{enabled ? '☑' : '☐'} Review and refine{!available ? ' · unavailable' : ''}</Text>
      </TouchableOpacity>
      {enabled && <TouchableOpacity accessibilityRole="button" accessibilityLabel="Advanced response review settings"
        accessibilityState={{ expanded: advanced, disabled }} disabled={disabled} onPress={() => setAdvanced(true)} style={s.button}>
        <Text style={s.label}>Advanced · {policy.review_rounds} {policy.review_rounds === 1 ? 'round' : 'rounds'}</Text>
      </TouchableOpacity>}
    </View>
    {enabled && <>
      <Text style={s.detail}>Plan, draft, then review and refine for {policy.review_rounds} {policy.review_rounds === 1 ? 'round' : 'rounds'} ({stageCount} model stages). All stages share the total answer budget{answerTokenLimit ? ` of ${answerTokenLimit.toLocaleString()} tokens` : ' set by the engine'}; at least {minimum.toLocaleString()} total tokens are required. Resume keeps the exact saved settings.</Text>
      {issueText.map((issue, index) => <Text key={index} accessibilityRole="alert" style={s.error}>{issue}</Text>)}
    </>}
    <Modal visible={advanced} animationType="slide" onRequestClose={close}>
      <SafeAreaView style={s.modal}><ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
        <View style={s.between}><Text accessibilityRole="header" style={s.heading}>{rolePicker ? `${pickerTitle} model` : 'Response review settings'}</Text>
          <TouchableOpacity accessibilityRole="button" accessibilityLabel="Close response review settings" onPress={close} style={s.button}><Text style={s.label}>Close</Text></TouchableOpacity>
        </View>
        {rolePicker ? <>
          <TouchableOpacity accessibilityRole="button" onPress={() => setRolePicker(null)} style={s.button}><Text style={s.label}>← Back to response review settings</Text></TouchableOpacity>
          <Text style={s.detail}>Choose an exact, already configured text model for {pickerTitle.toLowerCase()}. Changing this option never activates a model or starts inference.</Text>
          <Choice label={`Use main turn model for ${pickerTitle.toLowerCase()}`} selected={!pickedPair} disabled={disabled} press={() => choose(rolePicker)} />
          {models.map(model => {
            const ready = cooperationModelReady(model);
            const selected = pickedPair?.provider_id === model.provider_id && pickedPair.model_id === model.model_id;
            return <View key={model.id} style={[s.card, selected && s.selected]}>
              <Choice label={`${model.label} for ${pickerTitle.toLowerCase()}`} selected={selected} disabled={disabled || !ready} press={() => choose(rolePicker, model)} />
              <Text style={s.detail}>{model.credential_free ? 'Local model' : 'Hosted model'} · {ready ? 'Available text generation' : model.readiness?.message || 'Unavailable for this workflow'}</Text>
              <Text style={s.detail}>{model.context_window?.toLocaleString() || 'Unobserved'} context tokens · {model.max_output_tokens?.toLocaleString() || 'Unobserved'} maximum output tokens</Text>
            </View>;
          })}
          {!models.length && <Text style={s.error}>No configured model inventory is currently observed. Existing role selections are preserved.</Text>}
        </> : <>
          <Text style={s.detail}>These settings apply to the next new turn. Saved pending work resumes with its original policy. All four roles use the main turn model unless you explicitly choose another configured model.</Text>
          <Text style={s.section}>Review rounds</Text>
          <View style={s.row}>{[1, 2, 3].map(rounds => <Choice key={rounds} label={`${rounds} review ${rounds === 1 ? 'round' : 'rounds'}`} selected={policy.review_rounds === rounds} disabled={disabled} press={() => changePolicy({ ...policy, review_rounds: rounds })} />)}</View>
          <Text style={s.detail}>{stageCount} model stages · minimum total answer budget {minimum.toLocaleString()} tokens{answerTokenLimit ? ` · current ${answerTokenLimit.toLocaleString()}` : ' · engine-set budget'}. The total allowance is shared; adding rounds does not increase it.</Text>
          <Text style={s.section}>Per-stage output ceiling</Text>
          <TextInput accessibilityLabel="Maximum tokens per review stage" value={capDraft} editable={!disabled} onChangeText={cap} keyboardType="number-pad" maxLength={4} style={s.input} />
          <View style={s.row}>{[64, 128, 256, 512, 1024, 2048, 4096].map(value => <Choice key={value} label={`Set review stage cap to ${value.toLocaleString()} tokens`} selected={policy.max_stage_output_tokens === value} disabled={disabled} press={() => cap(String(value))} />)}</View>
          <Text style={s.detail}>Each stage also respects its selected model’s physical output limit and the remaining shared budget. A ceiling is not a promise that the model will use that many tokens.</Text>
          <Text style={s.section}>Models by role</Text>
          {COOPERATION_ROLES.map(({ role, label }, index) => {
            const pair = policy.roles[role]; const model = chosenModels[index];
            const missing = !!pair && (!model || !cooperationModelReady(model));
            return <View key={role} style={s.card}>
              <Text style={s.section}>{label}</Text>
              <Text style={missing ? s.error : s.detail}>{pair ? model?.label || `${pair.provider_id} · ${pair.model_id} (not observed)` : mainModel ? `Main turn model · ${mainModel.label}` : 'Main turn model · engine-configured route'}</Text>
              {model && <Text style={s.detail}>{model.context_window?.toLocaleString() || 'Unobserved'} context tokens · stage ceiling at most {Math.min(policy.max_stage_output_tokens, model.max_output_tokens ?? policy.max_stage_output_tokens).toLocaleString()} output tokens before shared-budget admission</Text>}
              <TouchableOpacity accessibilityRole="button" accessibilityLabel={`Choose ${label.toLowerCase()} model`} accessibilityState={{ disabled }} disabled={disabled} onPress={() => setRolePicker(role)} style={s.button}><Text style={s.label}>Choose {label.toLowerCase()} model</Text></TouchableOpacity>
            </View>;
          })}
          <Text style={s.detail}>{sharedContext ? `Shared context capacity is at most ${sharedContext.toLocaleString()} tokens across the chosen models.` : 'The engine checks the shared context capacity of inherited and explicitly chosen models.'} The saved conversation and generated stage material must fit; the engine refuses incompatible requests rather than dropping context.</Text>
          <Text style={s.detail}>Several roles may use the same model. Multiple stages or models do not certify independent review or better results.</Text>
        </>}
        <TouchableOpacity accessibilityRole="button" accessibilityLabel="Refresh models for response review" accessibilityState={{ disabled: refreshing || disabled }} disabled={refreshing || disabled} onPress={() => { setRefreshing(true); void refreshModels().catch(() => {}).finally(() => setRefreshing(false)); }} style={s.button}><Text style={s.label}>{refreshing ? 'Refreshing observed models…' : 'Refresh observed models'}</Text></TouchableOpacity>
        {issueText.map((issue, index) => <Text key={index} accessibilityRole="alert" style={s.error}>{issue}</Text>)}
      </ScrollView></SafeAreaView>
    </Modal>
  </View>;
}

const s = StyleSheet.create({
  group: { gap: 4 }, row: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 }, between: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12 },
  button: { minHeight: 44, paddingHorizontal: 10, paddingVertical: 9, alignSelf: 'flex-start', justifyContent: 'center', borderRadius: 8, borderWidth: 1, borderColor: '#28364e' },
  label: { color: '#cbd5e1', fontSize: 11, fontWeight: '600' }, detail: { color: '#94a3b8', fontSize: 12, lineHeight: 18, maxWidth: 760 },
  selected: { backgroundColor: '#292042', borderColor: '#6d52a4' }, disabled: { opacity: 0.4 }, error: { color: '#fca5a5', fontSize: 12, lineHeight: 18 },
  modal: { flex: 1, backgroundColor: '#0b1220' }, content: { maxWidth: 820, width: '100%', alignSelf: 'center', padding: 22, gap: 14, paddingBottom: 40 },
  heading: { flex: 1, color: '#e2e8f0', fontSize: 20, fontWeight: '700' }, section: { color: '#cbd5e1', fontSize: 13, fontWeight: '700' },
  input: { color: '#e2e8f0', backgroundColor: '#111a2e', borderColor: '#28364e', borderWidth: 1, borderRadius: 9, paddingHorizontal: 13, paddingVertical: 12, fontSize: 15, maxWidth: 240 },
  card: { gap: 9, padding: 13, backgroundColor: '#111a2e', borderColor: '#28364e', borderWidth: 1, borderRadius: 12 },
});
