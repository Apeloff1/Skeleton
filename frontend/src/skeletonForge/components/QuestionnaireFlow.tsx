/**
 * Guided GameForge questionnaire: vision → creative brief → design beats →
 * forge options → review, ending in a forge run. Presentational over the
 * pure reducer in ../questionnaire.
 */
import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { humanize } from '../graph';
import { DESIGN_AXES } from '../instruments';
import { GALAXY_CHOICES, galaxyGenre, mappedBriefGenre } from '../galaxyGenres';
import { GENRE_COUNT, GENRE_GROUPS, filterGenreChoices } from '../genreCatalog';
import DesignInstruments from './DesignInstruments';
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
  /** Navigate to the full historical Galaxy Studio matrix/slider questionnaire. */
  onOpenGalaxyStudio?: () => void;
  forging?: boolean;
  /** Short compose summary shown on the review step. */
  composeSummary?: string | null;
  /** Opens the plan viewer once a forge has produced one. */
  onViewPlan?: () => void;
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

/** Browsing defaults to the familiar 36; search reaches all registered genres. */
function GenrePicker({ value, onPick }: { value?: string; onPick: (v: string) => void }) {
  const [query, setQuery] = React.useState('');
  const [family, setFamily] = React.useState('popular');
  const matches = filterGenreChoices(query, family);
  const shown = matches.slice(0, 80);
  return (
    <View style={st.group} accessibilityRole="radiogroup" accessibilityLabel="What kind of game is it?" testID="q-group-brief-genre">
      <Text style={st.q}>What kind of game is it?</Text>
      <Text style={st.help}>{GENRE_COUNT} selectable game genres and subgenres. Each is a creative-brief hint mapped to a design era, not a promise of a dedicated playable engine.</Text>
      <TextInput
        testID="q-genre-search"
        value={query}
        onChangeText={setQuery}
        placeholder="Search all genres (for example: colony, racing, puzzle)"
        placeholderTextColor={C.dim}
        accessibilityLabel="Search game genres"
        autoCapitalize="none"
        maxLength={48}
        style={[st.input, { minHeight: TOUCH, marginBottom: 8 }]}
      />
      <View style={st.chips}>
        <Chip label="Popular 36" selected={family === 'popular'} onPress={() => setFamily('popular')} testID="q-genre-family-popular" />
        <Chip label="All" selected={family === 'all'} onPress={() => setFamily('all')} testID="q-genre-family-all" />
        {GENRE_GROUPS.map((g) => (
          <Chip key={g.id} label={g.label} selected={family === g.id} onPress={() => setFamily(g.id)} testID={'q-genre-family-' + g.id} />
        ))}
      </View>
      {value && !shown.includes(value) ? (
        <View style={st.chips}>
          <Chip label={'Selected: ' + humanize(value)} selected onPress={() => onPick(value)} testID={'q-brief-genre-' + value} />
        </View>
      ) : null}
      <Text style={st.help}>{shown.length} of {matches.length} matching genres shown{matches.length > shown.length ? '; refine search or choose a category' : ''}.</Text>
      <View style={st.chips}>
        {shown.map((genre) => (
          <Chip
            key={genre}
            label={humanize(genre)}
            selected={value === genre}
            color={C.accent}
            onPress={() => onPick(genre)}
            testID={'q-brief-genre-' + genre}
            a11yLabel={humanize(genre) + (value === genre ? ', selected' : '')}
          />
        ))}
      </View>
      {!shown.length ? <Text style={st.help}>No matching genre. Try a broader term or another category.</Text> : null}
    </View>
  );
}

function BriefStep({ state, dispatch }: QuestionnaireFlowProps) {
  return (
    <Card>
      <Text style={st.help}>Optional. The brief votes an era only when no design beat is answered; it always names and themes the game.</Text>
      {BRIEF_FACETS.map((f) => (
        f.id === 'genre' ? (
          <GenrePicker key={f.id} value={state.brief.genre} onPick={(v) => dispatch({ type: 'setBrief', facet: 'genre', value: v })} />
        ) : (
        <OptionGroup key={f.id} id={`brief-${f.id}`} prompt={f.prompt} options={f.options} value={state.brief[f.id]} onPick={(v) => dispatch({ type: 'setBrief', facet: f.id, value: v })} color={C.accent} />
        )
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

function OptionsStep({ state, dispatch, eras = [], generations = [], onOpenGalaxyStudio }: QuestionnaireFlowProps) {
  const [instrumentsOpen, setInstrumentsOpen] = React.useState(false);
  const [galaxyOpen, setGalaxyOpen] = React.useState(false);
  const [genreSearch, setGenreSearch] = React.useState('');
  const filteredGenres = GALAXY_CHOICES.filter((g) => (g.id + ' ' + g.name + ' ' + g.desc).toLowerCase().includes(genreSearch.trim().toLowerCase()));
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
      <View style={st.group} testID="q-native-quest-controls" accessibilityRole="radiogroup" accessibilityLabel="Native quest gameplay">
        <Text style={st.q}>Native quest gameplay (original quest runtime)</Text>
        <Text style={st.help}>Optional. Generate a real Godot room-entry quest with a visible objective HUD, room-triggered progression, and source-checked save snapshots. This does not add NPC conversations or combat quests.</Text>
        <View style={st.chips}>
          <Chip label="No quest" selected={!state.quest?.enabled}
            onPress={() => dispatch({ type: 'setQuestEnabled', value: false })}
            testID="q-native-quest-off" />
          <Chip label="Room-entry quest" selected={!!state.quest?.enabled}
            disabled={state.options.target !== 'godot'} color={C.green}
            onPress={() => dispatch({ type: 'setQuestEnabled', value: true })}
            testID="q-native-quest-on" />
        </View>
        {state.options.target !== 'godot' ? (
          <Text style={st.help} testID="q-native-quest-inactive">Native quests require Godot output; JSON blueprint export will not include quest gameplay.</Text>
        ) : null}
        {state.quest?.enabled && state.options.target === 'godot' ? (
          <View accessibilityRole="radiogroup" accessibilityLabel="Number of quest objectives" testID="q-native-quest-length">
            <Text style={st.help}>Quest objective count: {state.quest.length} (1–8). Each objective targets a reachable room in the emitted world.</Text>
            <View style={st.chips}>
              {[1, 2, 3, 4, 5, 6, 7, 8].map((n) => (
                <Chip key={n} label={String(n)} selected={state.quest?.length === n}
                  color={C.blue} onPress={() => dispatch({ type: 'setQuestLength', value: n })}
                  testID={'q-native-quest-' + n} />
              ))}
            </View>
          </View>
        ) : null}
      </View>
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
      <View style={st.group}>
        <Button label={galaxyOpen ? 'Hide 67-genre catalog' : 'Advanced: choose from all 67 Galaxy genres'}
          tone="secondary" compact testID="q-galaxy-genres-toggle"
          onPress={() => setGalaxyOpen((open) => !open)} />
      </View>
      {galaxyOpen ? (
        <View style={st.group} accessibilityRole="radiogroup" accessibilityLabel="Specialized Galaxy Studio genres">
          <Text style={st.help}>
            Your chosen specialization is preserved in the build vision. GameForge maps it
            to the nearest supported broad genre to choose a runtime dialect;
            this is not a claim that every specialized mechanic is implemented.
          </Text>
          <TextInput testID="q-galaxy-genre-search" style={[st.input, { minHeight: TOUCH }]}
            value={genreSearch} onChangeText={setGenreSearch}
            placeholder="Search 67 genres" accessibilityLabel="Search Galaxy genres"
            placeholderTextColor={C.dim} />
          <Text style={st.help}>{filteredGenres.length} matching genres. {filteredGenres.length > 24 ? 'Showing first 24; refine your search.' : ''}</Text>
          <View style={st.chips}>
            <Chip label="No specialization" selected={!state.galaxyGenre}
              onPress={() => dispatch({ type: 'setGalaxyGenre', genre: null })}
              testID="q-galaxy-genre-auto" />
            {filteredGenres.slice(0, 24).map((g) => (
              <Chip key={g.id} label={g.name} role="radio"
                selected={state.galaxyGenre === g.id}
                a11yLabel={g.name + '. Maps to ' + mappedBriefGenre(g.id)}
                onPress={() => dispatch({ type: 'setGalaxyGenre', genre: g.id })}
                testID={'q-galaxy-genre-' + g.id} />
            ))}
          </View>
          {state.galaxyGenre ? (
            <Text style={st.help} testID="q-galaxy-genre-selection">
              Selected: {galaxyGenre(state.galaxyGenre)?.name ?? '—'} ·
              GameForge category: {mappedBriefGenre(state.galaxyGenre)}
            </Text>
          ) : null}
        </View>
      ) : null}
      {onOpenGalaxyStudio ? (
        <View style={st.group}>
          <Text style={st.q}>Need the original full-production questionnaire?</Text>
          <Text style={st.help}>Open Galaxy Studio for its 14 production matrices, narrative phase controls, nine style selectors and 100 extended sliders. Galaxy and this Forge run currently have separate drafts.</Text>
          <Button label="Open full Galaxy Studio questionnaire" tone="secondary" compact onPress={onOpenGalaxyStudio} testID="q-open-galaxy-studio" />
        </View>
      ) : null}
      <View style={st.group}>
        <Button
          label={instrumentsOpen ? 'Hide design instruments' : 'Advanced: ten design sliders / knobs'}
          tone="secondary" compact onPress={() => setInstrumentsOpen((v) => !v)}
          testID="q-design-instruments-toggle"
        />
      </View>
      {instrumentsOpen ? (
        <DesignInstruments
          axes={state.instruments || {}}
          onAxis={(axis, value) => dispatch({ type: 'setAxis', axis, value })}
          onReset={() => dispatch({ type: 'resetAxes' })}
        />
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

function ReviewStep({ state, dispatch, beats, composeSummary, onViewPlan }: QuestionnaireFlowProps) {
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
      {state.galaxyGenre ? <Row k="Specialized genre" v={(galaxyGenre(state.galaxyGenre)?.name ?? state.galaxyGenre) + " → " + (mappedBriefGenre(state.galaxyGenre) ?? "unknown")} /> : null}
      {req.operator_axes ? <Row k="Design tuning" v={DESIGN_AXES.filter((axis) => req.operator_axes?.[axis.id] !== undefined).map((axis) => axis.label + ": " + Math.round((req.operator_axes?.[axis.id] ?? 0) * 100) + "%").join(" · ")} /> : null}
      {req.quest_content ? <Row k="Native quest" v={`${req.quest_length} room-entry objectives · Godot quest HUD and snapshot contract`} /> : null}
      {state.quest?.enabled && !req.quest_content ? <Banner tone="warn" testID="q-native-quest-not-exported">Native room quests are disabled for JSON blueprint output. Select Godot in Forge options to include one.</Banner> : null}
      <Row k="Era" v={req.era ? humanize(req.era) : 'decided by the forge'} />
      {req.generation ? <Row k="Hardware" v={humanize(req.generation)} /> : null}
      <Banner tone="idle">{ERA_SOURCE_COPY[eraSource(state)]}</Banner>
      {shadowed.length ? (
        <Banner tone="warn" testID="q-shadowed">
          Your design beat overrides the brief answer for: {shadowed.join(', ')}.
        </Banner>
      ) : null}
      <Button label="Start over" tone="ghost" compact onPress={() => dispatch({ type: 'reset' })} testID="q-reset" />
      {onViewPlan ? <Button label="View build plan" tone="secondary" compact onPress={onViewPlan} a11yHint="Opens the plan from the last forge" testID="q-view-plan" /> : null}
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
