/**
 * B019 visual scene + logic editor.
 *
 * Renders a B012 design graph (scenes, mechanics, worlds… and their
 * relationships) for inspection and visual editing. Edits go through the pure
 * graphEdits ops, are reviewed as a B016 semantic diff, and are only submitted
 * as B014 `edit` creator commands after explicit operator approval.
 */
import React, { useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import theme from '../../../theme/tokens';
import { commandsForSession, type CreatorEditCommand } from '../creatorCommand';
import { designGraphDigest, serializeDesignGraph, type DesignGraph } from '../designGraph';
import {
  addNode, applyEdit, removeNode, renameNode, setNodeAttribute, startSession, undo, type EditSession,
} from '../graphEdits';
import { semanticDiff } from '../semanticDiff';
import { strings } from '../strings';

export interface VisualSceneEditorProps {
  source: DesignGraph;
  /** Host submits approved commands (no creator HTTP route on main yet). */
  onSubmitCommands: (commands: CreatorEditCommand[]) => void | Promise<void>;
  initialSelection?: string;
  initialSession?: EditSession;
  testID?: string;
}

const c = theme.colors;
const s = theme.spacing;

function Button(props: { label: string; onPress: () => void; disabled?: boolean; tone?: 'primary' | 'plain' | 'danger'; testID?: string }) {
  const tone = props.tone ?? 'plain';
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={props.label}
      accessibilityState={{ disabled: !!props.disabled }}
      disabled={props.disabled}
      onPress={props.onPress}
      testID={props.testID}
      hitSlop={theme.hitSlop}
      style={[styles.btn, tone === 'primary' && styles.btnPrimary, tone === 'danger' && styles.btnDanger, props.disabled && styles.btnDisabled]}
    >
      <Text style={[styles.btnText, tone === 'primary' && { color: c.onPrimary }]}>{props.label}</Text>
    </Pressable>
  );
}

export function VisualSceneEditor({ source, onSubmitCommands, initialSelection, initialSession, testID }: VisualSceneEditorProps) {
  const [session, setSession] = useState<EditSession>(() => initialSession ?? startSession(source));
  const [selected, setSelected] = useState<string | undefined>(initialSelection);
  const [labelDraft, setLabelDraft] = useState('');
  const [attrKey, setAttrKey] = useState('');
  const [attrValue, setAttrValue] = useState('');
  const [reviewing, setReviewing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState<number | null>(null);

  const graph = session.working;
  const diff = useMemo(() => semanticDiff(session.base, session.working), [session]);
  const roundTrip = useMemo(() => serializeDesignGraph(session.working) === serializeDesignGraph(session.base), [session]);
  const node = graph.nodes.find((n) => n.id === selected);

  const run = (fn: Parameters<typeof applyEdit>[1]) => {
    if (submitting) return;
    try {
      const next = applyEdit(session, fn);
      setSession(next);
      setError(null);
      setSubmitted(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const addScene = () => {
    let i = 1;
    while (graph.nodes.some((n) => n.id === `scene.new-${i}`)) i += 1;
    const id = `scene.new-${i}`;
    run((g) => addNode(g, { id, kind: 'scene', label: `${strings.newSceneLabel} ${i}` }));
    setSelected(id);
  };

  const parseValue = (raw: string): unknown => {
    if (raw === 'true' || raw === 'false') return raw === 'true';
    if (raw !== '' && /^-?\d+$/.test(raw)) return Number(raw);
    return raw;
  };

  const approve = async () => {
    if (submitting || !reviewing) return;
    const submittedSession = session;
    if (designGraphDigest(source) !== designGraphDigest(submittedSession.base)) {
      setError('Source graph changed. Reload before approving edits.');
      setReviewing(false);
      return;
    }
    try {
      const commands = commandsForSession(submittedSession);
      if (commands.length === 0) throw new Error('No approved commands to submit.');
      setSubmitting(true);
      await onSubmitCommands(commands);
      setSubmitted(commands.length);
      setReviewing(false);
      setSession((current) => current === submittedSession ? startSession(current.working) : current);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <View style={styles.root} testID={testID ?? 'visual-scene-editor'} accessibilityLabel={strings.title}>
      <Text accessibilityRole="header" style={styles.h1}>{strings.title}</Text>
      <Text style={styles.meta} testID="vse-digest">{graph.projectId} · rev {graph.revision} · {designGraphDigest(graph).slice(0, 12)}</Text>
      <View style={styles.row}>
        <Button label={strings.addScene} onPress={addScene} testID="vse-add-scene" />
        <Button label={strings.undo} onPress={() => setSession((cur) => undo(cur))} disabled={!session.history.length} testID="vse-undo" />
        <Button label={`${strings.review} (${strings.changeSummary(diff.changes.length)})`} onPress={() => setReviewing(true)} disabled={!diff.changes.length} tone="primary" testID="vse-review" />
      </View>
      {designGraphDigest(source) !== designGraphDigest(session.base) ? (
        <View>
          <Text accessibilityRole="alert" style={styles.error}>Source changed: pending edits are held until reload.</Text>
          <Button label="Reload current source" onPress={() => {
            if (submitting) return;
            setSession(startSession(source));
            setReviewing(false);
            setSelected(undefined);
            setError(null);
          }} disabled={submitting} />
        </View>
      ) : null}
      {error ? <Text accessibilityRole="alert" style={styles.error} testID="vse-error">{error}</Text> : null}
      {submitted !== null ? <Text accessibilityLiveRegion="polite" style={styles.ok} testID="vse-submitted">{strings.submitted(submitted)}</Text> : null}
      <View style={styles.columns}>
        <ScrollView style={styles.col} accessibilityLabel={strings.nodes}>
          <Text accessibilityRole="header" style={styles.h2}>{strings.nodes}</Text>
          {graph.nodes.map((n) => (
            <Pressable
              key={n.id}
              accessibilityRole="button"
              accessibilityLabel={strings.selectNode(n.label, n.kind)}
              accessibilityState={{ selected: n.id === selected }}
              onPress={() => { setSelected(n.id); setLabelDraft(n.label); }}
              testID={`vse-node-${n.id}`}
              style={[styles.node, n.id === selected && styles.nodeSelected]}
            >
              <Text style={styles.kind}>{n.kind}</Text>
              <Text style={styles.text}>{n.label}</Text>
            </Pressable>
          ))}
          <Text accessibilityRole="header" style={styles.h2}>{strings.relationships}</Text>
          {graph.edges.map((e) => (
            <Text key={e.id} style={styles.meta} testID={`vse-edge-${e.id}`}>{e.source} —{e.kind}→ {e.target}</Text>
          ))}
        </ScrollView>
        <View style={styles.col} accessibilityLabel={strings.inspector}>
          <Text accessibilityRole="header" style={styles.h2}>{strings.inspector}</Text>
          {!node ? <Text style={styles.meta}>{strings.noSelection}</Text> : (
            <View testID="vse-inspector">
              <Text style={styles.text}>{node.id}</Text>
              {Object.keys(node.attributes).map((k) => (
                <Text key={k} style={styles.meta} testID={`vse-attr-${k}`}>{k} = {String(node.attributes[k])}</Text>
              ))}
              <TextInput accessibilityLabel={strings.label} value={labelDraft} onChangeText={setLabelDraft} style={styles.input} testID="vse-label-input" />
              <Button label={strings.rename} onPress={() => run((g) => renameNode(g, node.id, labelDraft))} testID="vse-rename" />
              <TextInput accessibilityLabel={strings.attrKey} value={attrKey} onChangeText={setAttrKey} style={styles.input} testID="vse-attr-key" />
              <TextInput accessibilityLabel={strings.attrValue} value={attrValue} onChangeText={setAttrValue} style={styles.input} testID="vse-attr-value" />
              <Button label={strings.setAttr} onPress={() => run((g) => setNodeAttribute(g, node.id, attrKey, parseValue(attrValue)))} disabled={!attrKey} testID="vse-set-attr" />
              <Button label={strings.remove} tone="danger" onPress={() => { run((g) => removeNode(g, node.id)); setSelected(undefined); }} testID="vse-remove" />
            </View>
          )}
        </View>
      </View>
      <Text style={roundTrip ? styles.ok : styles.meta} testID="vse-roundtrip">{roundTrip ? `${strings.roundTripOk}: ${strings.noChanges}` : strings.changeSummary(diff.changes.length)}</Text>
      {reviewing ? (
        <View style={styles.approval} accessibilityRole="alert" accessibilityLabel={strings.approvalTitle} testID="vse-approval">
          <Text accessibilityRole="header" style={styles.h2}>{strings.approvalTitle}</Text>
          <Text style={styles.meta}>{strings.approvalHint}</Text>
          {diff.changes.map((ch, i) => (
            <Text key={i} style={styles.text} testID="vse-change">{ch.action} {ch.subject}</Text>
          ))}
          <View style={styles.row}>
            <Button label={strings.approve} tone="primary" onPress={approve} disabled={submitting || designGraphDigest(source) !== designGraphDigest(session.base)} testID="vse-approve" />
            <Button label={strings.cancel} onPress={() => setReviewing(false)} testID="vse-cancel" />
          </View>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { padding: s.base, gap: s.md, backgroundColor: c.bg },
  row: { flexDirection: 'row', gap: s.sm, flexWrap: 'wrap' },
  columns: { flexDirection: 'row', gap: s.md },
  col: { flex: 1, gap: s.sm },
  h1: { color: c.text, fontSize: 20, fontWeight: '700' },
  h2: { color: c.text, fontSize: 16, fontWeight: '600', marginTop: s.sm },
  text: { color: c.text },
  meta: { color: c.textMuted },
  kind: { color: c.accentCyan, fontSize: 12 },
  error: { color: c.danger },
  ok: { color: c.success },
  node: { padding: s.sm, borderRadius: theme.radii.md, borderWidth: 1, borderColor: c.border, backgroundColor: c.surface },
  nodeSelected: { borderColor: c.borderFocus, backgroundColor: c.primarySoft },
  input: { borderWidth: 1, borderColor: c.border, borderRadius: theme.radii.sm, padding: s.sm, color: c.text, marginVertical: s.xs },
  btn: { paddingVertical: s.sm, paddingHorizontal: s.md, borderRadius: theme.radii.md, borderWidth: 1, borderColor: c.borderStrong, minHeight: 44, justifyContent: 'center' },
  btnPrimary: { backgroundColor: c.primary, borderColor: c.primary },
  btnDanger: { borderColor: c.danger },
  btnDisabled: { opacity: 0.5 },
  btnText: { color: c.text, fontWeight: '600' },
  approval: { padding: s.base, borderRadius: theme.radii.lg, borderWidth: 1, borderColor: c.warning, backgroundColor: c.bgElevated, gap: s.sm },
});

export default VisualSceneEditor;
