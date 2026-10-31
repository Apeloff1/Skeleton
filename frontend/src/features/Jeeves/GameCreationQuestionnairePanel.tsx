import React, { useMemo, useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';

type Field = 'intent' | 'constraints' | 'variants';
type Answers = Record<Field, string>;
type Facet = typeof FACETS[number];
const FACETS = [
  'concept', 'story', 'world', 'geography', 'character', 'npc',
  'dialogue', 'scene', 'quest', 'faction', 'level', 'mechanics',
  'combat', 'physics', 'environment', 'asset', 'animation', 'music',
  'audio', 'cinematics', 'interface', 'inventory', 'economy',
  'procedural', 'camera', 'engine', 'platform', 'testing',
  'release', 'training',
] as const;

const QUESTIONS: Record<Field, string> = {
  intent: 'Creative intent: What must Jeeves create?',
  constraints: 'Rules: What must never be violated?',
  variants: 'Alternatives: Which branches and variations are required?',
};
const BLANK: Answers = { intent: '', constraints: '', variants: '' };
const FIELDS: Field[] = ['intent', 'constraints', 'variants'];
const MAX_GOAL = 7500;

function label(value: string): string {
  return value.replace(/_/g, ' ').replace(/(^|\s)\S/g, letter => letter.toUpperCase());
}

function formatGoal(chosen: { facet: Facet; answers: Answers }[]): string {
  const lines = [
    'Create and review this ORIGINAL game through Jeeves, the standalone AI game director.',
    'Use the current saved project, its real tools, forges and owned assets.',
    'The following sections are user-authored goals, NOT executed commands or grants.',
    'Respect existing canon, rights, engine constraints, and device budgets.',
    'Plan the requested steps through the current scoped studio owner.',
    'Before each authorized edit, show the proposed effect and scope.',
    'After each actual action attach command identity, project revision, source evidence,',
    'model/tool decision, receipt and outcome. Unavailable facilities must be reported.',
    'Never claim compilation, playtesting, game release or model training without evidence.',
  ];
  chosen.forEach(({ facet, answers }, index) => {
    lines.push('FACET ' + (index + 1) + ': ' + facet);
    FIELDS.forEach(key => lines.push(key.toUpperCase() + ': ' + answers[key]));
  });
  return lines.join('\n');
}

function facetAnswers(catalog: Partial<Record<Facet, Answers>>, key: Facet): Answers {
  return catalog[key] || BLANK;
}

export default function GameCreationQuestionnairePanel({
  disabled, onCompose,
}: { disabled?: boolean; onCompose: (goal: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const [facet, setFacet] = useState<Facet>('concept');
  const [drafts, setDrafts] = useState<Partial<Record<Facet, Answers>>>({});
  const [selected, setSelected] = useState<Facet[]>([]);
  const [notice, setNotice] = useState('');
  const current = facetAnswers(drafts, facet);
  const chosen = useMemo(() => selected.map(name => ({
    facet: name, answers: facetAnswers(drafts, name),
  })), [selected, drafts]);
  const allComplete = chosen.length > 0 && chosen.every(({ answers }) =>
    FIELDS.every(key => answers[key].trim().length > 0));
  const goal = useMemo(() => allComplete ? formatGoal(chosen) : '', [allComplete, chosen]);
  const overBudget = goal.length > MAX_GOAL;

  const edit = (field: Field, value: string) => {
    setDrafts(previous => ({
      ...previous,
      [facet]: { ...facetAnswers(previous, facet), [field]: value },
    }));
    setNotice('');
  };
  const toggle = (name: Facet) => {
    setSelected(previous => previous.includes(name)
      ? previous.filter(value => value !== name)
      : FACETS.filter(value => previous.includes(value) || value === name));
    setFacet(name);
    setNotice('');
  };

  return (
    <View style={styles.panel}>
      <TouchableOpacity accessibilityRole="button"
        accessibilityState={{ expanded }}
        disabled={disabled}
        onPress={() => setExpanded(value => !value)} style={styles.toggle}>
        <Text style={styles.title}>Jeeves · 30 game-creation forges {expanded ? '▲' : '▼'}</Text>
      </TouchableOpacity>
      <Text style={styles.help}>
        Design with Jeeves across game systems, narrative, media, and production.
        Each facet becomes a scoped user goal, not an automatic edit.
      </Text>
      {expanded && (
        <View>
          <Text style={styles.heading}>Choose creation facets ({selected.length} selected)</Text>
          <ScrollView horizontal accessibilityLabel="Game creation facets">
            <View style={styles.columns}>
              {FACETS.map(name => (
                <TouchableOpacity key={name} accessibilityRole="checkbox"
                  accessibilityLabel={'Select ' + label(name)}
                  accessibilityState={{ checked: selected.includes(name), disabled }}
                  disabled={disabled}
                  onPress={() => toggle(name)}
                  style={[styles.chip, selected.includes(name) && styles.selected]}>
                  <Text style={styles.text}>{selected.includes(name) ? '✓ ' : '+ '}{label(name)}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </ScrollView>
          <Text style={styles.heading}>Questionnaire · {label(facet)}</Text>
          {FIELDS.map(field => (
            <View key={field} style={styles.field}>
              <Text style={styles.text}>{QUESTIONS[field]}</Text>
              <TextInput
                accessibilityLabel={label(facet) + ': ' + QUESTIONS[field]}
                multiline value={current[field]} onChangeText={text => edit(field, text)}
                editable={!disabled}
                maxLength={4096}
                placeholder={'Describe ' + field + ' for ' + facet}
                placeholderTextColor="#8794a9"
                style={styles.input} />
            </View>
          ))}
          <Text style={styles.help}>
            {selected.length === 0
              ? 'Select at least one facet.'
              : !allComplete
                ? 'Fill all three questions for each selected facet.'
                : overBudget
                  ? 'The goal exceeds the current 7,500-character studio draft budget. Select fewer facets or shorten answers.'
                  : 'Ready to prepare a proposal inside the existing scoped Jeeves assistant.'}
          </Text>
          <TouchableOpacity accessibilityRole="button"
            accessibilityState={{ disabled: !!disabled || !allComplete || overBudget }}
            disabled={!!disabled || !allComplete || overBudget}
            onPress={() => { onCompose(goal); setNotice('Goal prepared in the studio form. Review and choose Plan or Run. No action was executed.'); }}
            style={[styles.submit, (!!disabled || !allComplete || overBudget) && styles.inactive]}>
            <Text style={styles.buttonText}>Prepare Jeeves game-production goal</Text>
          </TouchableOpacity>
          {!!notice && <Text accessibilityLiveRegion="polite" style={styles.help}>{notice}</Text>}
          <Text style={styles.warning}>
            Multimodal generation, automated forge execution, rights clearance and model weights
            require the corresponding installed owner, explicit authorization and actual evidence receipts.
          </Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { padding: 12, borderRadius: 12, borderWidth: 1, borderColor: '#48566e', marginVertical: 12, gap: 8 },
  toggle: { paddingVertical: 6 },
  title: { color: '#f1f5fc', fontSize: 17, fontWeight: '700' },
  heading: { color: '#eef4fc', fontSize: 14, fontWeight: '600', marginTop: 8 },
  help: { color: '#c1ccdd', fontSize: 12, lineHeight: 18 },
  warning: { color: '#dcbf8d', fontSize: 12, lineHeight: 18, marginTop: 6 },
  columns: { flexDirection: 'row', flexWrap: 'wrap', width: 950, gap: 5, paddingVertical: 8 },
  chip: { paddingVertical: 7, paddingHorizontal: 9, borderRadius: 8, borderWidth: 1, borderColor: '#4f627c' },
  selected: { backgroundColor: '#214e70' },
  text: { color: '#e3e8f2', fontSize: 13 },
  field: { marginTop: 6, gap: 5 },
  input: { color: '#f1f5fc', fontSize: 13, minHeight: 65, textAlignVertical: 'top', borderColor: '#667a96', borderWidth: 1, borderRadius: 8, padding: 8 },
  submit: { backgroundColor: '#2777ac', borderRadius: 8, padding: 11, marginTop: 8 },
  inactive: { opacity: 0.45 },
  buttonText: { color: '#fff', fontWeight: '600', fontSize: 13, textAlign: 'center' },
});
