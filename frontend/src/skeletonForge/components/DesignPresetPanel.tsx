/**
 * Opt-in, local-only and bounded Forge design preset library.
 *
 * The Galaxy handoff still stays in memory by default. No questionnaire,
 * provider credential or user-authenticated project is silently persisted.
 */
import React from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';
import type { QuestionnaireAction, QuestionnaireState } from '../questionnaire';
import {
  DESIGN_PRESET_STORAGE_KEY, MAX_SAVED_PRESETS,
  type DesignPreset, decodeDesignPresets, deleteDesignPreset,
  encodeDesignPresets, makeDesignPreset, normalisePresetState, saveDesignPreset,
} from '../designPresets';
import { Button } from './primitives';
import { C, TOUCH } from './theme';

type Props = { state: QuestionnaireState; dispatch: (action: QuestionnaireAction) => void };

/** AsyncStorage is loaded lazily so offline SSR contract tests remain pure. */
async function localStore() {
  const store = await import('@react-native-async-storage/async-storage');
  return store.default;
}

export default function DesignPresetPanel({ state, dispatch }: Props) {
  const [expanded, setExpanded] = React.useState(false);
  const [ready, setReady] = React.useState(false);
  const [busy, setBusy] = React.useState(false);
  const [name, setName] = React.useState('');
  const [confirmDelete, setConfirmDelete] = React.useState<string | null>(null);
  const [records, setRecords] = React.useState<DesignPreset[]>([]);
  const [notice, setNotice] = React.useState<string | null>(null);
  const savingRef = React.useRef(false);

  React.useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const store = await localStore();
        const raw = await store.getItem(DESIGN_PRESET_STORAGE_KEY);
        const restored = decodeDesignPresets(raw);
        if (active) {
          setRecords(restored);
          setNotice(null);
        }
      } catch {
        if (active) setNotice('Saved preset data could not be validated. No existing designs were overwritten.');
      } finally {
        if (active) setReady(true);
      }
    })();
    return () => { active = false; };
  }, []);

  const save = async () => {
    if (!ready || savingRef.current) return;
    savingRef.current = true;
    setBusy(true);
    try {
      const record = makeDesignPreset(name, state);
      const next = saveDesignPreset(records, record);
      const encoded = encodeDesignPresets(next);
      const storage = await localStore();
      await storage.setItem(DESIGN_PRESET_STORAGE_KEY, encoded);
      setRecords(next);
      setName('');
      setNotice('Saved "' + record.name + '" on this device.');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not save this design.');
    } finally {
      setBusy(false);
      savingRef.current = false;
    }
  };

  const load = (saved: DesignPreset) => {
    if (!ready || busy) return;
    try {
      const checked = normalisePresetState(saved.state);
      dispatch({ type: 'restoreDesignPreset', state: checked });
      setNotice('Loaded "' + saved.name + '". Review settings before generating.');
    } catch {
      setNotice('Preset validation failed. The active design was not changed.');
    }
  };

  const remove = async (saved: DesignPreset) => {
    if (!ready || savingRef.current) return;
    savingRef.current = true;
    setBusy(true);
    try {
      const next = deleteDesignPreset(records, saved.name);
      const storage = await localStore();
      await storage.setItem(DESIGN_PRESET_STORAGE_KEY, encodeDesignPresets(next));
      setRecords(next);
      setNotice('Deleted local preset "' + saved.name + '".');
      setConfirmDelete(null);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Could not delete the saved design.');
    } finally {
      savingRef.current = false;
      setBusy(false);
    }
  };

  return (
    <View style={st.container} testID="q-design-preset-library">
      <Button tone="secondary" compact
        label={expanded ? 'Hide saved game designs' : 'Save / load game designs'}
        onPress={() => setExpanded(!expanded)}
        testID="q-design-presets-toggle" />
      {expanded ? (
        <View style={st.contents} testID="q-design-presets-expanded">
          <Text style={st.heading} accessibilityRole="header">
            Device-local design presets ({records.length}/{MAX_SAVED_PRESETS})
          </Text>
          <Text style={st.help}>
            Save and revisit the full questionnaire, Galaxy matrices, cockpit knobs,
            native quest and playable mode. Saving is explicit and stays on this
            device. These local records are not encrypted project vaults:
            avoid putting secrets in a design. No account or cloud sync.
          </Text>
          <TextInput
            value={name}
            onChangeText={setName}
            maxLength={64}
            placeholder="Design preset name"
            placeholderTextColor={C.mute}
            accessibilityLabel="Name for saved game design"
            style={st.input}
            testID="q-design-preset-name"
          />
          <Button label="Save current design" onPress={() => { void save(); }}
            disabled={!ready || busy || !name.trim()} compact
            testID="q-design-preset-save" />
          {records.map((item) => (
            <View key={item.name} style={st.entry} testID="q-design-preset-entry">
              <Text style={st.entryName} numberOfLines={2}>{item.name}</Text>
              <View style={st.actions}>
                <Button label="Load" tone="secondary" compact
                  disabled={!ready || busy} onPress={() => load(item)}
                  testID="q-design-preset-load" />
                {confirmDelete === item.name ? (
                  <Button label="Confirm deletion" tone="danger" compact
                    disabled={busy} onPress={() => { void remove(item); }}
                    testID="q-design-preset-confirm-delete" />
                ) : (
                  <Button label="Delete" tone="ghost" compact
                    disabled={busy} onPress={() => setConfirmDelete(item.name)}
                    testID="q-design-preset-delete" />
                )}
              </View>
            </View>
          ))}
          {notice ? <Text style={st.notice} accessibilityRole="alert" testID="q-design-preset-notice">{notice}</Text> : null}
        </View>
      ) : null}
    </View>
  );
}

const st = StyleSheet.create({
  container: { marginVertical: 12, gap: 8 },
  contents: { gap: 12, borderWidth: 1, borderColor: C.border, borderRadius: 12, padding: 12 },
  heading: { color: C.textStrong, fontWeight: '700', fontSize: 15 },
  help: { color: C.mute, fontSize: 12, lineHeight: 18 },
  input: { color: C.textStrong, borderWidth: 1, borderColor: C.border, borderRadius: 8,
    paddingHorizontal: 12, paddingVertical: 9, minHeight: TOUCH },
  entry: { borderTopWidth: 1, borderTopColor: C.border, paddingTop: 8, gap: 6 },
  entryName: { color: C.textStrong, fontSize: 14, fontWeight: '600' },
  actions: { flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' },
  notice: { color: C.text, fontSize: 12 },
});
