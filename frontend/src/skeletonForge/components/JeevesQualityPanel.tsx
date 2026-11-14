/** Local Jeeves game-quality coverage inspector. Read-only, opt-in metadata. */
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { errorText, fetchJeevesGameQualityCatalog, type JeevesGameQualityCatalog } from '../client';
import { C } from './theme';

export default function JeevesQualityPanel() {
  const [open, setOpen] = React.useState(false);
  const [catalog, setCatalog] = React.useState<JeevesGameQualityCatalog | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (!open) return undefined;
    const abort = new AbortController();
    void fetchJeevesGameQualityCatalog(abort.signal)
      .then(response => {
        if (abort.signal.aborted) return;
        if (response.ok && response.data && response.data.inference_started === false
            && response.data.model_quality_certified === false) {
          setCatalog(response.data);
        } else {
          setError(response.ok ? 'Unexpected evaluator contract' : errorText(response));
        }
      })
      .catch(() => { if (!abort.signal.aborted) setError('Offline quality catalog unavailable.'); });
    return () => abort.abort();
  }, [open]);
  return (
    <View testID="q-jeeves-quality-panel" style={styles.section}>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded: open }}
        testID="q-jeeves-quality-toggle"
        onPress={() => { setOpen(v => !v); setCatalog(null); setError(null); }}
        style={styles.button}>
        <Text style={styles.title}>{open ? 'Hide' : 'Inspect'} Jeeves local game-quality diagnostics</Text>
      </Pressable>
      {open ? (
        <View testID="q-jeeves-quality-detail">
          <Text style={styles.note}>Public diagnostic tasks assess structured game design, GDScript reasoning and correctness. No model is run by this panel.</Text>
          {catalog ? (
            <>
              <Text style={styles.title}>{catalog.task_count} deterministic public tasks · {catalog.dimensions.length} dimensions</Text>
              <Text style={styles.note}>{catalog.categories.join(' · ')}</Text>
              <Text style={styles.note}>A real local GGUF run and independently verified playthrough remain necessary; this catalog is not a quality certification.</Text>
            </>
          ) : null}
          {error ? <Text style={styles.note} accessibilityLiveRegion="polite">{error}</Text> : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { paddingTop: 12, paddingBottom: 12 },
  button: { padding: 12, borderRadius: 8, backgroundColor: C.cardAlt, borderWidth: 1, borderColor: C.borderStrong },
  title: { color: C.textStrong, fontWeight: '600' },
  note: { color: C.dim, fontSize: 12, marginTop: 8 },
});
