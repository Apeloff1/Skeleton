/** Typed, lossless controls over the existing Forge operation parameter document. */
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { StyleSheet, Text, TextInput, TouchableOpacity, View } from 'react-native';
import type { ForgeDocument } from '../../../product/gameFrontierAuthoringClient';
import {
  appendForgeParameter, duplicateForgeParameter, inspectForgeParameters,
  parseForgeNumber, removeForgeParameter, replaceForgeParameter,
  type ParameterNode, type ParameterPath,
} from './forgeParameterEditor';

type Props = {
  raw: string;
  onChange: (raw: string) => void;
  action: string;
  document: ForgeDocument | null;
  disabled?: boolean;
  onIssueChange?: (issue: string | null) => void;
};
type Edit = (expected: string, operation: (current: string) => string, structural?: boolean) => boolean;
type ValueKind = 'string' | 'number' | 'boolean' | 'object' | 'array' | 'null';
const VALUE_KINDS: { kind: ValueKind; label: string }[] = [
  { kind: 'string', label: 'Text' }, { kind: 'number', label: 'Number' },
  { kind: 'boolean', label: 'True / false' }, { kind: 'object', label: 'Object' },
  { kind: 'array', label: 'List' }, { kind: 'null', label: 'Empty' },
];
const INITIAL_FIELDS = 96;
const MAX_FIELDS = 512;
const MAX_DEPTH = 6;
const ARRAY_PAGE = 24;
const pathKey = (path: ParameterPath) => JSON.stringify(path);
const pathLabel = (path: ParameterPath) => 'Parameters' + path.map(part => '[' + JSON.stringify(part) + ']').join('');
const human = (value: string) => value.replace(/([a-z\d])([A-Z])/g, '$1 $2').replace(/[_-]+/g, ' ').trim();
const name = (path: ParameterPath) => typeof path[path.length - 1] === 'number'
  ? 'Item ' + (Number(path[path.length - 1]) + 1)
  : human(String(path[path.length - 1] ?? 'Parameters')).slice(0, 100) || '(empty name)';
// JSON permits escaped lone surrogates in keys. encodeURIComponent throws on
// those values; encode each scalar and retain an explicit code-unit escape.
const encoded = (value: string) => Array.from(value).map(part => {
  try { return encodeURIComponent(part).replace(/_/g, '%5F'); } catch { return '_u' + part.charCodeAt(0).toString(16); }
}).join('');
const fieldId = (path: ParameterPath) => 'forge-param-' + (path.length
  ? 'field-' + path.map(part => encoded(String(part))).join('/') : 'root');
const emptyValue = (kind: ValueKind): unknown => ({ string: '', number: 0, boolean: false, object: {}, array: [], null: null })[kind];

function Button({ label, press, disabled, selected, id, a11y }: {
  label: string; press: () => void; disabled?: boolean; selected?: boolean; id?: string; a11y?: string;
}) {
  return <TouchableOpacity accessibilityRole="button" accessibilityLabel={a11y || label}
    accessibilityState={{ disabled: !!disabled, selected: !!selected }} disabled={disabled}
    onPress={press} testID={id} style={[styles.button, selected && styles.selected, disabled && styles.disabled]}>
    <Text style={styles.buttonText}>{label}</Text>
  </TouchableOpacity>;
}

function NumberField({ node, raw, disabled, edit, report }: {
  node: ParameterNode; raw: string; disabled: boolean; edit: Edit;
  report: (key: string, issue: string | null) => void;
}) {
  const key = pathKey(node.path);
  const original = raw.slice(node.start, node.end);
  const [draft, setDraft] = useState(original);
  const [issue, setIssue] = useState<string | null>(null);
  useEffect(() => { setDraft(original); setIssue(null); report(key, null); }, [original, key, report]);
  useEffect(() => () => { report(key, null); }, [key, report]);
  return <View style={styles.stack}>
    <TextInput accessibilityLabel={pathLabel(node.path)} testID={fieldId(node.path) + '-input'}
      value={draft} editable={!disabled} autoCorrect={false} autoCapitalize="none"
      selectTextOnFocus style={styles.input} onChangeText={value => {
        setDraft(value);
        try {
          const number = parseForgeNumber(value);
          if (!edit(raw, current => replaceForgeParameter(current, raw, node.path, number))) {
            throw new Error('The draft changed before this number was applied. Review its current value or restore it.');
          }
          setIssue(null); report(key, null);
        } catch (cause) {
          const message = cause instanceof Error ? cause.message : 'Finish this number before queueing.';
          setIssue(message); report(key, pathLabel(node.path) + ': ' + message);
        }
      }} />
    {issue && <><Text accessibilityRole="alert" style={styles.error}>{issue}</Text>
      <Button label={'Restore current ' + name(node.path)} a11y={'Restore current value of ' + pathLabel(node.path)}
        id={fieldId(node.path) + '-restore'} disabled={disabled} press={() => {
        setDraft(original); setIssue(null); report(key, null);
      }} /></>}
  </View>;
}

type Suggestion = { label: string; value: string };
function references(node: ParameterNode, document: ForgeDocument | null): Suggestion[] {
  if (!document || node.kind !== 'string') return [];
  const key = node.path[node.path.length - 1];
  const id = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 128;
  let choices: Suggestion[] = [];
  if (key === 'layer' && Array.isArray(document.layers)) choices = document.layers.slice(0, 128)
    .filter(item => item && id(item.id)).map(item => ({ label: item.id, value: item.id }));
  if (key === 'prefab_id' && Array.isArray(document.prefab_catalog)) choices = document.prefab_catalog.slice(0, 128)
    .filter(item => item && id(item.id)).map(item => ({ label: item.id, value: item.id }));
  if (key === 'quest_id' && Array.isArray(document.quest_catalog)) choices = document.quest_catalog.slice(0, 128)
    .filter(item => item && id(item.id)).map(item => ({ label: item.title || item.id, value: item.id }));
  if ((key === 'actor_id' || key === 'new_actor_id' || key === 'target') && Array.isArray(document.actor_catalog)) choices = document.actor_catalog.slice(0, 128)
    .filter(item => item && id(item.prefab_id) && Number.isSafeInteger(item.index) && item.index >= 0)
    .map(item => ({ label: item.prefab_id + ':' + item.index, value: item.prefab_id + ':' + item.index }));
  return choices.filter((choice, index) => choices.findIndex(other => other.value === choice.value) === index);
}

function ProjectReferences({ node, document, raw, disabled, edit }: {
  node: ParameterNode; document: ForgeDocument | null; raw: string; disabled: boolean; edit: Edit;
}) {
  const [open, setOpen] = useState(false);
  const [all, setAll] = useState(false);
  const choices = references(node, document);
  if (!choices.length) return null;
  return <View style={styles.stack}>
    <Button label={open ? 'Hide project references' : 'Choose an existing project reference'} disabled={disabled}
      press={() => setOpen(value => !value)} />
    {open && <><Text style={styles.help}>Choose a reference when this action uses an existing item, or keep your own value.</Text>
      <View style={styles.row}>{choices.slice(0, all ? 128 : 12).map(choice => <Button key={choice.value}
        label={choice.label} selected={node.value === choice.value} disabled={disabled}
        press={() => { edit(raw, current => replaceForgeParameter(current, raw, node.path, choice.value)); }} />)}</View>
      {!all && choices.length > 12 && <Button label={'Show all ' + choices.length + ' references'} disabled={disabled}
        press={() => setAll(true)} />}</>}
  </View>;
}

function AddValue({ node, raw, disabled, edit }: { node: ParameterNode; raw: string; disabled: boolean; edit: Edit }) {
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState('');
  const [kind, setKind] = useState<ValueKind>('string');
  const isObject = node.kind === 'object';
  return <View style={styles.stack}>
    <Button label={open ? 'Close add value' : isObject ? 'Add a parameter' : 'Add a list item'} disabled={disabled}
      id={fieldId(node.path) + '-add-open'} press={() => setOpen(value => !value)} />
    {open && <View style={styles.addBox}>
      {isObject && <TextInput accessibilityLabel={pathLabel(node.path) + ' new parameter name'}
        value={key} onChangeText={setKey} editable={!disabled} autoCapitalize="none" autoCorrect={false}
        placeholder="Parameter name" placeholderTextColor="#8da4b8" maxLength={1024} style={styles.input} />}
      <Text style={styles.help}>Choose the value type. The server preview checks whether this action accepts it.</Text>
      <View style={styles.row}>{VALUE_KINDS.map(item => <Button key={item.kind} label={item.label}
        selected={kind === item.kind} disabled={disabled} press={() => setKind(item.kind)} />)}</View>
      <Button label={isObject ? 'Add named parameter' : 'Add selected list item'} disabled={disabled || (isObject && !key.length)}
        id={fieldId(node.path) + '-add-confirm'} press={() => {
          if (edit(raw, current => appendForgeParameter(current, raw, node.path, isObject ? key : null, emptyValue(kind)), true)) {
            setKey(''); setOpen(false);
          }
        }} />
    </View>}
  </View>;
}

export default function ForgeParameterEditor({ raw, onChange, action, document, disabled = false, onIssueChange }: Props) {
  const inspection = useMemo(() => inspectForgeParameters(raw), [raw]);
  const [mode, setMode] = useState<'guided' | 'json'>('guided');
  const [fieldLimit, setFieldLimit] = useState(INITIAL_FIELDS);
  const [arrayLimits, setArrayLimits] = useState<Map<string, number>>(() => new Map());
  const [issues, setIssues] = useState<Map<string, string>>(() => new Map());
  const [editError, setEditError] = useState<string | null>(null);
  const [structureEpoch, setStructureEpoch] = useState(0);
  const currentRaw = useRef(raw);
  const lastPropRaw = useRef(raw);
  if (lastPropRaw.current !== raw) { currentRaw.current = raw; lastPropRaw.current = raw; }
  const issueCallback = useRef(onIssueChange); issueCallback.current = onIssueChange;
  const firstIssue = issues.values().next().value as string | undefined;
  const blockingIssue = !inspection.ok ? inspection.error : firstIssue || editError;
  useEffect(() => { issueCallback.current?.(blockingIssue || null); }, [blockingIssue]);
  useEffect(() => () => { issueCallback.current?.(null); }, []);
  useEffect(() => { if (!inspection.ok) setMode('json'); }, [inspection.ok]);
  const report = useCallback((key: string, issue: string | null) => {
    setIssues(current => {
      if (issue === null && !current.has(key) || issue !== null && current.get(key) === issue) return current;
      const next = new Map(current); if (issue === null) next.delete(key); else next.set(key, issue); return next;
    });
  }, []);
  const edit: Edit = useCallback((expected: string, operation: (current: string) => string, structural = false) => {
    if (disabled) return false;
    if (currentRaw.current !== expected) { setEditError('The parameter draft changed. Review the current values before editing again.'); return false; }
    try {
      const next = operation(currentRaw.current);
      onChange(next); currentRaw.current = next; setEditError(null);
      if (structural) { setStructureEpoch(value => value + 1); setIssues(new Map()); }
      return true;
    } catch (cause) {
      setEditError(cause instanceof Error ? cause.message : 'This edit could not be applied. Your JSON is retained.');
      return false;
    }
  }, [disabled, onChange]);
  const structuralDisabled = disabled || issues.size > 0;
  const openJSON = () => { setIssues(new Map()); setEditError(null); setMode('json'); };
  let remaining = fieldLimit;
  const renderField = (node: ParameterNode, depth: number): React.ReactNode => {
    if (remaining-- <= 0) return null;
    const container = node.kind === 'object' || node.kind === 'array';
    const path = pathKey(node.path);
    const arrayLimit = arrayLimits.get(path) || ARRAY_PAGE;
    const children = node.kind === 'array' ? node.children.slice(0, arrayLimit) : node.children;
    return <View key={structureEpoch + ':' + path} testID={fieldId(node.path)} style={[styles.field, depth > 0 && styles.nested]}>
      <View style={styles.heading}><Text style={styles.label}>{name(node.path)}</Text>
        <Text style={styles.type}>{node.kind === 'array' ? 'List · ' + node.children.length : VALUE_KINDS.find(item => item.kind === node.kind)?.label}</Text></View>
      {node.kind === 'string' && <>
        <TextInput accessibilityLabel={pathLabel(node.path)} testID={fieldId(node.path) + '-input'}
          value={node.value as string} editable={!disabled} autoCapitalize="none" autoCorrect={false}
          multiline={String(node.value).includes('\n') || String(node.value).length > 96}
          style={styles.input} onChangeText={value => { edit(raw, current => replaceForgeParameter(current, raw, node.path, value)); }} />
        <ProjectReferences node={node} document={document} raw={raw} disabled={disabled} edit={edit} />
      </>}
      {node.kind === 'number' && <NumberField node={node} raw={raw} disabled={disabled} edit={edit} report={report} />}
      {node.kind === 'boolean' && <View style={styles.row}>{[true, false].map(value => <Button key={String(value)}
        label={String(value)} selected={node.value === value} disabled={disabled}
        id={fieldId(node.path) + '-' + String(value)} press={() => { edit(raw, current => replaceForgeParameter(current, raw, node.path, value)); }} />)}</View>}
      {node.kind === 'null' && <><Text style={styles.help}>Empty value. Choose a type to give it a value.</Text>
        <View style={styles.row}>{VALUE_KINDS.filter(item => item.kind !== 'null').map(item => <Button key={item.kind}
          label={'Use ' + item.label.toLowerCase()} disabled={structuralDisabled}
          press={() => { edit(raw, current => replaceForgeParameter(current, raw, node.path, emptyValue(item.kind)), true); }} />)}</View></>}
      {container && (depth < MAX_DEPTH ? <>
        {!node.children.length && <Text style={styles.help}>{node.kind === 'array' ? 'No list items yet.' : 'No parameters yet.'}</Text>}
        {children.map(child => renderField(child, depth + 1))}
        {node.kind === 'array' && node.children.length > arrayLimit && <Button label={'Show next ' + Math.min(ARRAY_PAGE, node.children.length - arrayLimit) + ' list items'}
          disabled={disabled} press={() => setArrayLimits(current => new Map(current).set(path, arrayLimit + ARRAY_PAGE))} />}
        <AddValue node={node} raw={raw} disabled={structuralDisabled} edit={edit} />
      </> : <><Text style={styles.help}>Edit deeper values in Advanced JSON. Their original content is retained.</Text>
        <Button label="Open Advanced JSON" disabled={disabled || issues.size > 0} press={openJSON} /></>)}
      <View style={styles.row}>
        {typeof node.path[node.path.length - 1] === 'number' && <Button label={'Duplicate ' + name(node.path)} a11y={'Duplicate ' + pathLabel(node.path)}
          disabled={structuralDisabled} id={fieldId(node.path) + '-duplicate'}
          press={() => { edit(raw, current => duplicateForgeParameter(current, raw, node.path), true); }} />}
        <Button label={'Remove ' + name(node.path)} a11y={'Remove ' + pathLabel(node.path)} disabled={structuralDisabled} id={fieldId(node.path) + '-remove'}
          press={() => { edit(raw, current => removeForgeParameter(current, raw, node.path), true); }} />
      </View>
    </View>;
  };
  return <View style={styles.editor} testID="forge-parameter-editor">
    <View style={styles.heading}><View style={styles.titleBlock}>
      <Text style={styles.title}>Shape this action</Text>
      <Text style={styles.help}>Edit values, review the changes, then save them to your game.</Text>
    </View><View style={styles.row}>
      <Button label="Guided fields" id="forge-parameters-guided" selected={mode === 'guided'}
        disabled={disabled || !inspection.ok} press={() => setMode('guided')} />
      <Button label={issues.size ? 'Discard unfinished field edits and open JSON' : 'Advanced JSON'}
        id="forge-parameters-advanced" selected={mode === 'json'} disabled={disabled} press={openJSON} />
    </View></View>
    {inspection.ok && <Text style={styles.help}>{human(action)} · {inspection.fieldCount} values{inspection.bytes > 96000 ? ' · ' + inspection.bytes.toLocaleString() + ' of 128,000 JSON bytes' : ''}</Text>}
    {!inspection.ok && <Text accessibilityRole="alert" style={styles.error}>{inspection.error} Your exact JSON remains available below.</Text>}
    {editError && <View style={styles.stack}><Text accessibilityRole="alert" style={styles.error}>{editError}</Text>
      <Button label="Dismiss edit issue" disabled={disabled} press={() => setEditError(null)} /></View>}
    {issues.size > 0 && <Text accessibilityRole="alert" style={styles.error}>Finish or restore the highlighted number fields before queueing or changing the structure.</Text>}
    {mode === 'guided' && inspection.ok ? <>
      {inspection.root.children.map(node => renderField(node, 0))}
      {!inspection.root.children.length && <Text style={styles.help}>This action has no parameters yet. Add one or use Advanced JSON.</Text>}
      <AddValue node={inspection.root} raw={raw} disabled={structuralDisabled} edit={edit} />
      {inspection.fieldCount > fieldLimit && (fieldLimit < MAX_FIELDS
        ? <Button label={'Show more fields (' + fieldLimit + ' currently available)'} disabled={disabled}
          press={() => setFieldLimit(value => Math.min(MAX_FIELDS, value + INITIAL_FIELDS))} />
        : <Text style={styles.help}>For a larger document, use Advanced JSON. Every remaining value is preserved.</Text>)}
    </> : <TextInput accessibilityLabel="Authoring tool parameters JSON" testID="forge-parameters-json"
      value={raw} onChangeText={value => { currentRaw.current = value; setEditError(null); onChange(value); }}
      editable={!disabled} multiline autoCapitalize="none" autoCorrect={false} maxLength={512000}
      style={[styles.input, styles.json]} />}
    <Text style={styles.help}>The preview checks this action against your project. Editing these values does not save or run anything.</Text>
  </View>;
}

const styles = StyleSheet.create({
  editor: { gap: 12, padding: 14, backgroundColor: '#131f2d', borderWidth: 1, borderColor: '#30465a', borderRadius: 12 },
  titleBlock: { flex: 1, minWidth: 180, gap: 4 },
  title: { color: '#edf5fb', fontWeight: '700', fontSize: 17 },
  heading: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 8, justifyContent: 'space-between' },
  label: { color: '#e0edf7', fontWeight: '600', flexShrink: 1 },
  type: { color: '#a8bfd0', fontSize: 12 },
  field: { gap: 8, paddingVertical: 12, borderTopWidth: 1, borderTopColor: '#2b4051' },
  nested: { marginLeft: 8, paddingLeft: 10, borderLeftWidth: 1, borderLeftColor: '#344d60' },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  stack: { gap: 7 },
  help: { color: '#adc3d3', fontSize: 12, lineHeight: 18, flexShrink: 1 },
  error: { color: '#ffbbb0', fontSize: 12, lineHeight: 18 },
  input: { color: '#f0f7fc', backgroundColor: '#202f40', borderWidth: 1, borderColor: '#4b657b', borderRadius: 8, padding: 11, minHeight: 44, minWidth: 0, width: '100%', textAlignVertical: 'top' },
  json: { minHeight: 160, fontFamily: 'monospace' },
  button: { minHeight: 44, paddingVertical: 9, paddingHorizontal: 11, borderRadius: 7, backgroundColor: '#263b50', borderWidth: 1, borderColor: '#48667f', alignItems: 'center', justifyContent: 'center', flexShrink: 1 },
  buttonText: { color: '#e1effa', fontSize: 12, fontWeight: '600' },
  selected: { borderColor: '#6dd8bc', backgroundColor: '#19483f' },
  disabled: { opacity: 0.45 },
  addBox: { gap: 9, padding: 12, borderRadius: 8, backgroundColor: '#1a2a39' },
});
