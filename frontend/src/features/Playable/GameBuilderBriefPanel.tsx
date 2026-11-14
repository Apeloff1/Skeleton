import React from 'react';
import { StyleSheet, Switch, Text, TextInput, TouchableOpacity, useWindowDimensions, View } from 'react-native';
import {
  applyReviewedGameBuilderBrief, changeGameBuilderStarter, GAME_BUILDER_DIFFICULTIES,
  GAME_BUILDER_FIELD_LIMITS, GAME_BUILDER_STARTERS, gameBuilderStarter, newGameBuilderDraft,
  reviewGameBuilderBrief, type GameBuilderBriefDraft, type ReviewedGameBuilderBrief,
} from './gameBuilderBrief';

/** A local editor for creator input. Only the existing Generate action starts model work. */
export default function GameBuilderBriefPanel({ brief, onApply, disabled = false }: {
  brief: string; onApply: (value: string) => void; disabled?: boolean;
}) {
  const { width } = useWindowDimensions();
  const [draft, setDraft] = React.useState<GameBuilderBriefDraft>(() => newGameBuilderDraft());
  const [expanded, setExpanded] = React.useState(false);
  const [review, setReview] = React.useState<ReviewedGameBuilderBrief | null>(null);
  const [replaceApproved, setReplaceApproved] = React.useState(false);
  const [message, setMessage] = React.useState('');
  const [error, setError] = React.useState('');
  const starter = gameBuilderStarter(draft.genre);
  const staleReview = !!review && review.previousBrief !== brief;

  React.useEffect(() => { setReplaceApproved(false); }, [brief]);
  const change = <K extends keyof GameBuilderBriefDraft>(key: K, value: GameBuilderBriefDraft[K]) => {
    setDraft(current => ({ ...current, [key]: value }));
    setReview(null); setReplaceApproved(false); setError(''); setMessage('');
  };
  const prepare = () => {
    try {
      setReview(reviewGameBuilderBrief(draft, brief)); setReplaceApproved(false);
      setError(''); setMessage('Review the design below, then choose how to apply it.');
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The brief could not be reviewed.'); }
  };
  const apply = (mode: 'append' | 'replace') => {
    if (!review || disabled) return;
    try {
      const result = applyReviewedGameBuilderBrief(review, brief, mode, replaceApproved);
      onApply(result); setReview(null); setReplaceApproved(false);
      setMessage('Design applied to your game brief. Edit it below, then choose Generate & Play when you are ready.');
      setError('');
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'The brief could not be applied.'); }
  };

  return <View testID="pl-brief-builder" style={s.panel}>
    <View style={s.heading}>
      <View style={s.headingCopy}>
        <Text style={s.eyebrow}>FROM A SPARK TO A PLAYABLE IDEA</Text>
        <Text style={s.title} accessibilityRole="header">Make something worth playing.</Text>
        <Text style={s.subtitle}>Start with a small, complete experience. Shape its loop, give it a purpose, and make the controls feel good.</Text>
      </View>
      <Text style={s.localBadge}>BRIEF DESIGN</Text>
    </View>

    <View style={[s.starters, width < 620 && s.startersNarrow]}>
      {GAME_BUILDER_STARTERS.map(item => {
        const selected = draft.genre === item.id;
        return <TouchableOpacity key={item.id} testID={`pl-builder-starter-${item.id}`}
          accessibilityRole="button" accessibilityLabel={`Choose ${item.subtitle.toLowerCase()}: ${item.title}`}
          accessibilityState={{ selected, disabled }} disabled={disabled}
          onPress={() => {
            if (!selected) { setDraft(current => changeGameBuilderStarter(current, item.id)); setReview(null); }
            setExpanded(true); setError(''); setMessage(''); setReplaceApproved(false);
          }} style={[s.starter, selected && s.starterSelected, width < 620 && s.starterNarrow]}>
          <Text style={[s.starterSymbol, { color: item.color }]}>{item.symbol}</Text>
          <View style={s.starterCopy}><Text style={s.starterTitle}>{item.title}</Text>
            <Text style={s.starterSubtitle}>{item.subtitle}</Text></View>
          <Text style={[s.starterSelectedMark, { color: selected ? item.color : '#64748B' }]}>{selected ? 'Selected' : 'Explore →'}</Text>
        </TouchableOpacity>;
      })}
    </View>

    <TouchableOpacity testID="pl-builder-toggle" accessibilityRole="button"
      accessibilityState={{ expanded }} disabled={disabled} onPress={() => setExpanded(value => !value)} style={s.toggle}>
      <Text style={s.toggleText}>{expanded ? '− Close design editor' : '+ Shape this idea'}</Text>
      <Text style={s.toggleHint}>Your written brief stays intact until you apply.</Text>
    </TouchableOpacity>

    {expanded && <View testID="pl-builder-editor" style={s.editor}>
      <Text style={s.fieldLabel}>01 / Choose the moment-to-moment loop</Text>
      <View style={s.loopOptions}>
        {starter.loops.map(loop => <TouchableOpacity key={loop.id} testID={`pl-builder-loop-${loop.id}`}
          accessibilityRole="button" accessibilityState={{ selected: draft.coreLoop === loop.id, disabled }}
          disabled={disabled} onPress={() => change('coreLoop', loop.id)}
          style={[s.loop, draft.coreLoop === loop.id && s.loopSelected]}>
          <Text style={s.loopTitle}>{loop.title}</Text><Text style={s.loopDescription}>{loop.description}</Text>
        </TouchableOpacity>)}
      </View>
      <Text style={s.fieldLabel}>02 / Set the feeling</Text>
      <Text style={s.inputLabel}>World and atmosphere</Text>
      <TextInput testID="pl-builder-theme" accessibilityLabel="Game theme and atmosphere" value={draft.theme}
        editable={!disabled} onChangeText={value => change('theme', value)} maxLength={GAME_BUILDER_FIELD_LIMITS.theme}
        placeholder="A place, a mood, a visual idea…" placeholderTextColor="#8291AA" style={s.input} />
      <View style={s.difficulties}>
        {GAME_BUILDER_DIFFICULTIES.map(item => <TouchableOpacity key={item.id} testID={`pl-builder-difficulty-${item.id}`}
          accessibilityRole="button" accessibilityLabel={`${item.title} difficulty. ${item.description}`}
          accessibilityState={{ selected: draft.difficulty === item.id, disabled }} disabled={disabled}
          onPress={() => change('difficulty', item.id)} style={[s.difficulty, draft.difficulty === item.id && s.difficultySelected]}>
          <Text style={[s.difficultyText, draft.difficulty === item.id && s.difficultyTextSelected]}>{item.title}</Text>
        </TouchableOpacity>)}
      </View>
      <Text style={s.fieldLabel}>03 / Give the player a reason to finish</Text>
      <Text style={s.inputLabel}>Player objective</Text>
      <TextInput testID="pl-builder-objective" accessibilityLabel="Player objective" value={draft.objective}
        editable={!disabled} onChangeText={value => change('objective', value)} maxLength={GAME_BUILDER_FIELD_LIMITS.objective}
        placeholder="What will the player accomplish?" placeholderTextColor="#8291AA" style={s.input} />
      <Text style={s.inputLabel}>Your constraints <Text style={s.optional}>(optional)</Text></Text>
      <TextInput testID="pl-builder-constraints" accessibilityLabel="Additional game design constraints" value={draft.constraints}
        editable={!disabled} onChangeText={value => change('constraints', value)} maxLength={GAME_BUILDER_FIELD_LIMITS.constraints}
        placeholder="For example: no flashing effects; one-handed controls; a color-blind-friendly palette." multiline
        placeholderTextColor="#8291AA" style={[s.input, s.constraints]} />

      <View style={s.acceptance} testID="pl-builder-acceptance">
        <Text style={s.acceptanceTitle}>A complete little game should let you…</Text>
        {starter.acceptance.map((item, index) => <View key={item} style={s.checkRow}>
          <Text style={s.checkIndex}>{String(index + 1).padStart(2, '0')}</Text><Text style={s.checkText}>{item}</Text>
        </View>)}
        <Text style={s.acceptanceNote}>These are requirements to check after generation. They are not completed playtests.</Text>
      </View>
      <TouchableOpacity testID="pl-builder-review" accessibilityRole="button" disabled={disabled} onPress={prepare}
        style={[s.reviewButton, disabled && s.disabled]}><Text style={s.reviewButtonText}>Review design brief →</Text></TouchableOpacity>

      {review && <View testID="pl-builder-review-panel" style={s.review}>
        <View style={s.reviewHeading}><Text style={s.reviewTitle}>Your design, ready to review</Text>
          <Text style={s.reviewBadge}>NO GENERATION STARTED</Text></View>
        <Text testID="pl-builder-preview" selectable style={s.preview}>{review.text}</Text>
        {!!brief.trim() && <Text style={s.acceptanceNote}>Adding keeps your written brief above this design. If its genre or objective differs, reconcile the text below before generating, or explicitly approve replacement.</Text>}
        {staleReview && <Text testID="pl-builder-conflict" accessibilityRole="alert" style={s.error}>
          Your written brief changed after this review. Choose Review design brief again to use its latest text.
        </Text>}
        <TouchableOpacity testID="pl-builder-append" accessibilityRole="button" disabled={disabled || staleReview}
          onPress={() => apply('append')} style={[s.applyButton, (disabled || staleReview) && s.disabled]}>
          <Text style={s.applyButtonText}>{brief.trim() ? 'Add design to my written brief' : 'Apply reviewed brief'}</Text>
        </TouchableOpacity>
        {!!brief.trim() && <View style={s.replaceArea}>
          <View style={s.replaceRow}><Text style={s.replaceLabel}>Replace my written brief instead</Text>
            <Switch testID="pl-builder-replace-approval" accessibilityLabel="Approve replacing my existing written brief"
              disabled={disabled || staleReview} value={replaceApproved} onValueChange={setReplaceApproved}
              trackColor={{ false: '#334155', true: '#5B5EB8' }} />
          </View>
          <TouchableOpacity testID="pl-builder-replace" accessibilityRole="button" disabled={disabled || staleReview || !replaceApproved}
            onPress={() => apply('replace')} style={[s.replaceButton, (disabled || staleReview || !replaceApproved) && s.disabled]}>
            <Text style={s.replaceButtonText}>Replace with reviewed design</Text>
          </TouchableOpacity>
        </View>}
      </View>}
    </View>}
    {!!error && <Text testID="pl-builder-error" accessibilityRole="alert" style={s.error}>{error}</Text>}
    {!!message && <Text testID="pl-builder-message" accessibilityLiveRegion="polite" style={s.message}>{message}</Text>}
  </View>;
}

const s = StyleSheet.create({
  panel: { marginTop: 18, marginBottom: 8, borderWidth: 1, borderColor: '#344057', borderRadius: 20, padding: 20, backgroundColor: '#141B28' },
  heading: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'flex-start', gap: 12 },
  headingCopy: { flex: 1, minWidth: 210 },
  eyebrow: { color: '#AFC3E5', fontSize: 9, fontWeight: '700', letterSpacing: 1.5, marginBottom: 10 },
  title: { color: '#F1F5FC', fontSize: 27, fontWeight: '500', lineHeight: 34, letterSpacing: -0.7 },
  subtitle: { color: '#B2BED2', fontSize: 13, lineHeight: 21, marginTop: 10, maxWidth: 650 },
  localBadge: { color: '#C4D1EE', fontSize: 9, fontWeight: '700', letterSpacing: 1, paddingHorizontal: 10, paddingVertical: 7, borderWidth: 1, borderColor: '#445575', borderRadius: 20 },
  starters: { flexDirection: 'row', gap: 10, marginTop: 24 },
  startersNarrow: { flexDirection: 'column' },
  starter: { flex: 1, padding: 15, minHeight: 150, borderWidth: 1, borderColor: '#354056', borderRadius: 13, backgroundColor: '#192132' },
  starterSelected: { backgroundColor: '#253049', borderColor: '#8DA6D7' },
  starterNarrow: { flexDirection: 'row', alignItems: 'center', minHeight: 86, gap: 12 },
  starterSymbol: { fontSize: 29, lineHeight: 34, marginBottom: 10 },
  starterCopy: { flex: 1 }, starterTitle: { color: '#EDF2FE', fontSize: 14, fontWeight: '700' },
  starterSubtitle: { color: '#B1BED6', fontSize: 11, lineHeight: 17, marginTop: 4 },
  starterSelectedMark: { fontSize: 10, fontWeight: '700', marginTop: 12 },
  toggle: { marginTop: 18, paddingVertical: 10, gap: 5 },
  toggleText: { color: '#D3DFF8', fontSize: 12, fontWeight: '700' },
  toggleHint: { color: '#A8B6CE', fontSize: 11, lineHeight: 17 },
  editor: { borderTopWidth: 1, borderTopColor: '#36445E', marginTop: 8, paddingTop: 6 },
  fieldLabel: { color: '#CBD9F1', fontSize: 11, fontWeight: '700', letterSpacing: 0.4, marginTop: 23, marginBottom: 11 },
  loopOptions: { gap: 9 }, loop: { backgroundColor: '#182131', padding: 13, borderWidth: 1, borderColor: '#35445E', borderRadius: 10 },
  loopSelected: { backgroundColor: '#243450', borderColor: '#8BA6D8' },
  loopTitle: { color: '#E3EDFE', fontSize: 12, fontWeight: '700' },
  loopDescription: { color: '#B4C3DA', fontSize: 11, lineHeight: 18, marginTop: 5 },
  inputLabel: { color: '#C2CFE5', fontSize: 11, marginBottom: 8, marginTop: 9 }, optional: { color: '#98A9C4' },
  input: { borderWidth: 1, borderColor: '#485C7F', backgroundColor: '#101925', borderRadius: 9, padding: 12, color: '#EDF3FF', fontSize: 12, lineHeight: 20 },
  constraints: { minHeight: 82, textAlignVertical: 'top' },
  difficulties: { flexDirection: 'row', flexWrap: 'wrap', gap: 7, marginTop: 14 },
  difficulty: { minHeight: 44, minWidth: 82, justifyContent: 'center', alignItems: 'center', paddingVertical: 10, paddingHorizontal: 13, borderRadius: 22, borderWidth: 1, borderColor: '#3F4D66' },
  difficultySelected: { backgroundColor: '#D1DDFA', borderColor: '#D1DDFA' },
  difficultyText: { color: '#C1CEE4', fontSize: 11, fontWeight: '600' }, difficultyTextSelected: { color: '#192C4B' },
  acceptance: { backgroundColor: '#182738', padding: 14, borderRadius: 11, borderWidth: 1, borderColor: '#3D5673', marginTop: 21, gap: 11 },
  acceptanceTitle: { color: '#DCEBFC', fontSize: 12, fontWeight: '700', marginBottom: 3 },
  checkRow: { flexDirection: 'row', gap: 10 }, checkIndex: { color: '#A1BEDF', fontSize: 10, lineHeight: 18, width: 20 },
  checkText: { flex: 1, color: '#C1D0E4', fontSize: 11, lineHeight: 18 },
  acceptanceNote: { color: '#A8BDD7', fontSize: 10, lineHeight: 17, paddingTop: 7, borderTopWidth: 1, borderTopColor: '#35506C' },
  reviewButton: { minHeight: 44, justifyContent: 'center', marginTop: 18, alignSelf: 'flex-start', backgroundColor: '#D1DDFA', borderRadius: 10, paddingHorizontal: 17, paddingVertical: 12 },
  reviewButtonText: { color: '#172A49', fontSize: 12, fontWeight: '800' },
  review: { borderWidth: 1, borderColor: '#596F97', backgroundColor: '#101A2A', borderRadius: 12, padding: 14, marginTop: 18 },
  reviewHeading: { flexDirection: 'row', flexWrap: 'wrap', gap: 9, alignItems: 'center', marginBottom: 15 },
  reviewTitle: { color: '#E3ECFC', fontSize: 13, fontWeight: '700' }, reviewBadge: { color: '#C2D4F0', fontSize: 8, letterSpacing: 0.7 },
  preview: { color: '#C6D2E5', fontSize: 11, lineHeight: 19 },
  applyButton: { minHeight: 44, justifyContent: 'center', marginTop: 18, borderRadius: 9, backgroundColor: '#BBD1F5', padding: 12, alignItems: 'center' },
  applyButtonText: { color: '#17304D', fontSize: 12, fontWeight: '800' },
  replaceArea: { marginTop: 14, paddingTop: 12, borderTopWidth: 1, borderTopColor: '#3C4F6D' },
  replaceRow: { flexDirection: 'row', justifyContent: 'space-between', gap: 12, alignItems: 'center' },
  replaceLabel: { flex: 1, color: '#B8C9E4', fontSize: 11, lineHeight: 17 },
  replaceButton: { minHeight: 44, justifyContent: 'center', alignSelf: 'flex-start', marginTop: 9, borderWidth: 1, borderColor: '#647A9E', borderRadius: 8, padding: 10 },
  replaceButtonText: { color: '#D1DEF2', fontSize: 11 },
  message: { color: '#BDE3D1', fontSize: 11, lineHeight: 18, marginTop: 14 },
  error: { color: '#FFC5B9', fontSize: 12, lineHeight: 19, marginTop: 14 }, disabled: { opacity: 0.45 },
});
