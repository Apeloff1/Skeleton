/**
 * Guided GameForge questionnaire: vision → creative brief → design beats →
 * forge options → review, ending in a forge run. Presentational over the
 * pure reducer in ../questionnaire.
 */
import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { humanize } from '../graph';
import {
  ARCHETYPES, BRIEF_FACETS, ERA_SOURCE_COPY, STEP_LABELS, STEPS, TARGETS, VISION_MAX,
  blockReason, buildRunRequest, eraSource, progress, reachable, shadowedBriefFacets, stepIndex,
  type QuestionnaireAction, type QuestionnaireState, type Step,
} from '../questionnaire';
import type { Beat, EraRow, GenerationRow, RunRequest } from '../types';
import { Banner, Button, Card, Chip, Meter, SectionTitle } from './primitives';
import { C, TOUCH } from './theme';

export interface QuestionnaireFlowProps {
  state: QuestionnaireState;
  dispatch: (a: QuestionnaireAction) => void;
  beats: Beat[];
  beatsLive?: boolean;
  eras?: EraRow[];
  generations?: GenerationRow[];
  onForge: (req: RunRequest) => void;
  forging?: boolean;
  /** Short compose summary shown on the review step. */
  composeSummary?: string | null;
  testID?: string;
}

export default function QuestionnaireFlow(props: QuestionnaireFlowProps) {
  const { state, dispatch, beats, testID } = props;
  const prog = progress(state, beats);
  const blocked = blockReason(state);
  const idx = stepIndex(state.step);
  return (
    <View testID={testID}>
      <SectionTitle hint={`${prog.answered}/${prog.total} answered`}>📝 GameForge questionnaire</SectionTitle>
      <Stepper state={state} dispatch={dispatch} />
      <Meter ratio={prog.ratio} color={C.accent} label={`Questionnaire ${Math.round(prog.ratio * 100)} percent answered`} />
      <View style={st.body}>
        {state.step === 'vision' ? <VisionStep {...props} /> : null}
        {state.step === 'brief' ? <BriefStep {...props} /> : null}
        {state.step === 'beats' ? <BeatsStep {...props} /> : null}
        {state.step === 'options' ? <OptionsStep {...props} /> : null}
        {state.step === 'review' ? <ReviewStep {...props} /> : null}
      </View>
      {blocked ? <Text style={st.blocked} accessibilityLiveRegion="polite" testID="q-blocked">{blocked}</Text> : null}
      <View style={st.footer}>
        <Button label="Back" tone="ghost" onPress={() => dispatch({ type: 'back' })} disabled={idx === 0} testID="q-back" />
        {state.step !== 'review' ? (
          <Button
            label={`Next: ${STEP_LABELS[STEPS[idx + 1]]}`}
            tone="secondary"
            onPress={() => dispatch({ type: 'next' })}
            disabled={!!blocked}
            testID="q-next"
          />
        ) : (
          <Button
            label="⚒ Forge it"
            onPress={() => props.onForge(buildRunRequest(state))}
            busy={props.forging}
            a11yHint="Runs the GameForge pipeline with these answers"
            testID="q-forge"
          />
        )}
      </View>
    </View>
  );
}

function Stepper({ state, dispatch }: { state: QuestionnaireState; dispatch: (a: QuestionnaireAction) => void }) {
  const cur = stepIndex(state.step);
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} accessibilityRole="tablist" contentContainerStyle={st.stepper}>
      {STEPS.map((step, i) => {
        const current = step === state.step;
        const done = i < cur;
        const can = reachable(state, step);
        return (
          <Pressable
            key={step}
            testID={`q-step-${step}`}
            onPress={() => dispatch({ type: 'goto', step })}
            disabled={!can}
            accessibilityRole="tab"
            accessibilityLabel={`Step ${i + 1} of ${STEPS.length}: ${STEP_LABELS[step]}${done ? ', done' : ''}${current ? ', current' : ''}`}
            accessibilityState={{ selected: current, disabled: !can }}
            style={[st.step, current && st.stepCur, !can && st.stepOff]}
          >
            <Text style={[st.stepNum, (current || done) && { backgroundColor: current ? C.accent : C.green, color: '#0b1220' }]}>
              {done ? '✓' : i + 1}
            </Text>
            <Text style={[st.stepTxt, current && { color: C.textStrong }]}>{STEP_LABELS[step]}</Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

function VisionStep({ state, dispatch }: QuestionnaireFlowProps) {
  return (
    <Card>
      <Text style={st.q}>What are you making?</Text>
      <Text style={st.help}>Name the systems you want — combat, crafting, a storm timer, a companion, a stash. The graph shows exactly which words become systems.</Text>
      <TextInput
        testID="q-vision-input"
        value={state.vision}
        onChangeText={(v) => dispatch({ type: 'setVision', vision: v })}
        placeholder="A co-op heist: craft gear, beat the storm timer, a butler companion reads the room"
        placeholderTextColor={C.dim}
        multiline
        maxLength={VISION_MAX}
        accessibilityLabel="Game vision"
        style={st.input}
      />
      <Text style={st.counter}>{state.vision.length}/{VISION_MAX}</Text>
    </Card>
  );
}

function OptionGroup({ id, prompt, options, value, onPick, color = C.blue, caption }: {
  id: string; prompt: string; options: string[]; value?: string; onPick: (v: string) => void; color?: string; caption?: string;
}) {
  return (
    <View style={st.group} accessibilityRole="radiogroup" accessibilityLabel={prompt} testID={`q-group-${id}`}>
      <Text style={st.q}>{prompt}</Text>
      {caption ? <Text style={st.help}>{caption}</Text> : null}
      <View style={st.chips}>
        {options.map((o) => (
          <Chip key={o} label={humanize(o)} selected={value === o} color={color} onPress={() => onPick(o)} testID={`q-${id}-${o}`} a11yLabel={`${humanize(o)}${value === o ? ', selected' : ''}`} />
        ))}
      </View>
    </View>
  );
}

function BriefStep({ state, dispatch }: QuestionnaireFlowProps) {
  return (
    <Card>
      <Text style={st.help}>Optional. The brief votes an era only when no design beat is answered; it always names and themes the game.</Text>
      {BRIEF_FACETS.map((f) => (
        <OptionGroup key={f.id} id={`brief-${f.id}`} prompt={f.prompt} options={f.options} value={state.brief[f.id]} onPick={(v) => dispatch({ type: 'setBrief', facet: f.id, value: v })} color={C.accent} />
      ))}
    </Card>
  );
}

function BeatsStep({ state, dispatch, beats, beatsLive }: QuestionnaireFlowProps) {
  const answered = beats.filter((b) => state.beats[b.id]).length;
  return (
    <Card>
      <Text style={st.help}>
        {answered}/{beats.length} beats answered. Each answer votes an era and nudges the design tensor; skip any you have no opinion on.
        {beatsLive ? '' : ' (Offline copy — the server list could not be loaded.)'}
      </Text>
      {beats.map((b, i) => (
        <OptionGroup key={b.id} id={`beat-${b.id}`} prompt={`${i + 1}. ${b.prompt}`} options={b.options} value={state.beats[b.id]} onPick={(v) => dispatch({ type: 'setBeat', beat: b.id, value: v })} color={C.green} />
      ))}
    </Card>
  );
}

function OptionsStep({ state, dispatch, eras = [], generations = [] }: QuestionnaireFlowProps) {
  return (
    <Card>
      <View accessibilityRole="radiogroup" accessibilityLabel="Forge archetype" style={st.group}>
        <Text style={st.q}>How should the blueprint be built?</Text>
        {ARCHETYPES.map((a) => {
          const sel = state.options.archetype === a.id;
          return (
            <Pressable
              key={a.id}
              testID={`q-arch-${a.id}`}
              onPress={() => dispatch({ type: 'setOption', key: 'archetype', value: a.id })}
              accessibilityRole="radio"
              accessibilityState={{ checked: sel, selected: sel }}
              accessibilityLabel={`${a.label}. ${a.hint}${sel ? ' Selected.' : ''}`}
              style={[st.arch, sel && { borderColor: C.green, backgroundColor: C.green + '14' }]}
            >
              <Text style={[st.radio, sel && { color: C.green }]} importantForAccessibility="no">{sel ? '◉' : '○'}</Text>
              <View style={{ flex: 1 }}>
                <Text style={st.archTitle}>{a.label}{a.id === 'auto' ? '  ·  recommended' : ''}</Text>
                <Text style={st.help}>{a.hint}</Text>
              </View>
            </Pressable>
          );
        })}
      </View>
      <OptionGroup id="target" prompt="Output" options={TARGETS.map((t) => t.id)} value={state.options.target} onPick={(v) => dispatch({ type: 'setOption', key: 'target', value: v })} />
      <View style={st.group} accessibilityRole="radiogroup" accessibilityLabel="Era override">
        <Text style={st.q}>Pin an era? <Text style={st.help}>(optional)</Text></Text>
        <View style={st.chips}>
          <Chip label="Decide for me" selected={!state.options.era} onPress={() => dispatch({ type: 'setOption', key: 'era', value: null })} testID="q-era-auto" />
          {eras.map((e) => (
            <Chip key={e.id} label={humanize(e.id)} selected={state.options.era === e.id} color={C.amber} onPress={() => dispatch({ type: 'setOption', key: 'era', value: e.id })} testID={`q-era-${e.id}`} />
          ))}
        </View>
      </View>
      {generations.length ? (
        <View style={st.group} accessibilityRole="radiogroup" accessibilityLabel="Hardware generation">
          <Text style={st.q}>Hardware generation <Text style={st.help}>(optional)</Text></Text>
          <View style={st.chips}>
            <Chip label="Detect" selected={!state.options.generation} onPress={() => dispatch({ type: 'setOption', key: 'generation', value: null })} testID="q-gen-auto" />
            {generations.map((g) => (
              <Chip key={g.key} label={String(g.label ?? humanize(g.key))} selected={state.options.generation === g.key} color={C.blue} onPress={() => dispatch({ type: 'setOption', key: 'generation', value: g.key })} testID={`q-gen-${g.key}`} />
            ))}
          </View>
        </View>
      ) : null}
    </Card>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <View style={st.row} accessible accessibilityLabel={`${k}: ${v}`}>
      <Text style={st.rowK}>{k}</Text>
      <Text style={st.rowV}>{v}</Text>
    </View>
  );
}

function ReviewStep({ state, dispatch, beats, composeSummary }: QuestionnaireFlowProps) {
  const req = buildRunRequest(state);
  const shadowed = shadowedBriefFacets(state);
  const arch = ARCHETYPES.find((a) => a.id === req.archetype);
  const briefTxt = BRIEF_FACETS.filter((f) => state.brief[f.id]).map((f) => `${f.id}: ${humanize(state.brief[f.id])}`).join(' · ');
  const beatsTxt = beats.filter((b) => state.beats[b.id]).map((b) => `${b.id}: ${humanize(state.beats[b.id])}`).join(' · ');
  return (
    <Card testID="q-review">
      <Row k="Vision" v={req.vision || '— (none; the questionnaire writes one)'} />
      {composeSummary && req.archetype === 'auto' ? <Row k="Systems" v={composeSummary} /> : null}
      <Row k="Brief" v={briefTxt || '—'} />
      <Row k="Beats" v={beatsTxt || '—'} />
      <Row k="Archetype" v={arch?.label ?? req.archetype} />
      <Row k="Output" v={TARGETS.find((t) => t.id === req.target)?.label ?? req.target} />
      <Row k="Era" v={req.era ? humanize(req.era) : 'decided by the forge'} />
      {req.generation ? <Row k="Hardware" v={humanize(req.generation)} /> : null}
      <Banner tone="idle">{ERA_SOURCE_COPY[eraSource(state)]}</Banner>
      {shadowed.length ? (
        <Banner tone="warn" testID="q-shadowed">
          Your design beat overrides the brief answer for: {shadowed.join(', ')}.
        </Banner>
      ) : null}
      <Button label="Start over" tone="ghost" compact onPress={() => dispatch({ type: 'reset' })} testID="q-reset" />
    </Card>
  );
}

const st = StyleSheet.create({
  stepper: { gap: 6, paddingBottom: 8 },
  step: { flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: TOUCH, paddingHorizontal: 10, borderRadius: 10, borderWidth: 1, borderColor: C.border, backgroundColor: C.card },
  stepCur: { borderColor: C.accent },
  stepOff: { opacity: 0.45 },
  stepNum: { width: 22, height: 22, borderRadius: 11, textAlign: 'center', lineHeight: 22, fontSize: 12, fontWeight: '800', color: C.mute, backgroundColor: C.border, overflow: 'hidden' },
  stepTxt: { color: C.mute, fontSize: 13, fontWeight: '700' },
  body: { marginTop: 12 },
  q: { color: C.textStrong, fontSize: 14, fontWeight: '700', marginBottom: 6 },
  help: { color: C.mute, fontSize: 12, lineHeight: 17, marginBottom: 8, fontWeight: '400' },
  group: { marginBottom: 10 },
  chips: { flexDirection: 'row', flexWrap: 'wrap' },
  input: { minHeight: 96, color: C.text, fontSize: 15, lineHeight: 22, backgroundColor: C.cardAlt, borderRadius: 10, borderWidth: 1, borderColor: C.borderStrong, padding: 12, textAlignVertical: 'top' },
  counter: { color: C.dim, fontSize: 11, textAlign: 'right', marginTop: 4 },
  arch: { flexDirection: 'row', gap: 10, borderWidth: 1, borderColor: C.border, borderRadius: 10, padding: 10, marginBottom: 6, minHeight: TOUCH, backgroundColor: C.cardAlt },
  radio: { color: C.mute, fontSize: 18, lineHeight: 20 },
  archTitle: { color: C.textStrong, fontWeight: '700', fontSize: 13, marginBottom: 2 },
  row: { flexDirection: 'row', gap: 10, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: C.border },
  rowK: { color: C.mute, width: 84, fontSize: 12, fontWeight: '700' },
  rowV: { color: C.text, flex: 1, fontSize: 13 },
  blocked: { color: C.amber, fontSize: 12, marginTop: 4 },
  footer: { flexDirection: 'row', justifyContent: 'space-between', gap: 10, marginTop: 12, marginBottom: 12 },
});
