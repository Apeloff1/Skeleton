/** Read-only input inspection; never captures physical device events in the editor. */
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { errorText, fetchGenreControls } from '../client';
import type { GenreControlProfile } from '../types';
import { C } from './theme';

export default function GenreControlsPreview({ genre }: { genre: string }) {
  const [open, setOpen] = React.useState(false);
  const [profile, setProfile] = React.useState<GenreControlProfile | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    setProfile(null);
    setError(null);
    if (!open) return undefined;
    const ctrl = new AbortController();
    setLoading(true);
    void (async () => {
      try {
        const response = await fetchGenreControls(genre, ctrl.signal);
        if (ctrl.signal.aborted) return;
        const data = response.data;
        if (!response.ok || !data || data.genre !== genre ||
            !Array.isArray(data.actions) || !Array.isArray(data.bindings) ||
            data.bindings.length > 128) {
          setError(response.ok ? 'Control profile unavailable' : errorText(response));
        } else {
          setProfile(data);
        }
      } catch {
        if (!ctrl.signal.aborted) setError('Control profile unavailable');
      } finally {
        if (!ctrl.signal.aborted) setLoading(false);
      }
    })();
    return () => ctrl.abort();
  }, [genre, open]);

  return (
    <View style={styles.wrapper} testID="q-genre-control-preview">
      <Pressable
        testID="q-genre-controls-toggle"
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        onPress={() => setOpen((value) => !value)}
        style={styles.toggle}
      >
        <Text style={styles.title}>{open ? 'Hide' : 'Inspect'} keyboard, gamepad and touch controls</Text>
      </Pressable>
      {open ? (
        <View testID="q-genre-controls-detail">
          <Text style={styles.note}>Semantic input layout only. This does not certify native hardware support or a dedicated playable engine.</Text>
          {loading ? <Text style={styles.note}>Loading controls…</Text> : null}
          {error ? <Text style={styles.note} accessibilityLiveRegion="polite">{error}</Text> : null}
          {profile ? (
            <View>
              <Text style={styles.title}>{profile.family} · {profile.actions.length} actions · {profile.bindings.length} bindings</Text>
              {profile.bindings.slice(0, 16).map((binding, index) => (
                <Text key={`${binding.action}:${binding.control}:${index}`} style={styles.binding}>
                  {binding.action} — {binding.control}
                </Text>
              ))}
              {profile.bindings.length > 16 ? <Text style={styles.note}>Showing 16 of {profile.bindings.length} bindings.</Text> : null}
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { marginTop: 12, paddingTop: 12, borderTopWidth: 1, borderTopColor: C.dim },
  toggle: { paddingVertical: 10, paddingHorizontal: 12, borderRadius: 8, backgroundColor: C.blue },
  title: { color: C.textStrong, fontWeight: '600' },
  note: { color: C.dim, fontSize: 12, marginVertical: 8 },
  binding: { color: C.textStrong, fontSize: 12, marginVertical: 3 },
});
