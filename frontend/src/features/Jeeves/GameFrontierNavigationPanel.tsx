/** Minimap zoom, world-portal and underground/sky-island level controls (GF-P0-131).
 *
 * Layers come from the authored Forge Studio document; portals are only the
 * connectors the caller declares. Nothing is invented or sent anywhere.
 */
import React from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, ActivityIndicator } from 'react-native';
import { inspectForge, type ForgeLayer } from '../../product/gameFrontierAuthoringClient';
import {
  buildLevelStack, initialView, stepZoom, canZoom, viewportFor, switchLevel, jumpToLevel,
  panView, portalsFrom, travelThroughPortal, levelLabel,
  type FrontierPortal, type MinimapView,
} from '../../product/frontierMinimap';

type Props = { projectId?: string; portals?: FrontierPortal[]; layers?: ForgeLayer[] };

export default function GameFrontierNavigationPanel({ projectId: initialProject = '', portals = [], layers: givenLayers }: Props) {
  const [projectId, setProjectId] = React.useState(initialProject);
  const [layers, setLayers] = React.useState<ForgeLayer[] | null>(givenLayers ?? null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [view, setView] = React.useState<MinimapView | null>(null);
  const stack = React.useMemo(() => buildLevelStack(layers ?? []), [layers]);

  React.useEffect(() => { setView(initialView(stack)); }, [stack]);

  const load = React.useCallback(async () => {
    const id = projectId.trim();
    if (!id) { setError('Enter a project ID to load its layers.'); return; }
    setLoading(true); setError(null);
    try { setLayers((await inspectForge(id)).layers); }
    catch (e) { setError(e instanceof Error ? e.message : 'Failed to load the authored game.'); }
    finally { setLoading(false); }
  }, [projectId]);

  const level = view ? stack.find(l => l.id === view.layer) : undefined;
  const vp = view && level ? viewportFor(view, level) : null;
  const exits = view ? portalsFrom(portals, stack, view.layer) : [];

  return (
    <View style={s.card} accessibilityLabel="Frontier navigation controls">
      <Text style={s.title}>Minimap and levels</Text>
      {!givenLayers && (
        <View style={s.row}>
          <TextInput style={s.input} value={projectId} onChangeText={setProjectId}
            placeholder="Project ID" placeholderTextColor="#6b7a90" autoCapitalize="none" accessibilityLabel="Project ID" />
          <Btn label="Load" onPress={load} disabled={loading} />
        </View>
      )}
      {loading && <ActivityIndicator color="#7fb2ff" />}
      {error && <Text style={s.error} accessibilityRole="alert">{error}</Text>}
      {!loading && !error && layers && !stack.length && <Text style={s.muted}>This game has no valid layers yet.</Text>}
      {!loading && !layers && !error && <Text style={s.muted}>Load a project to navigate its layers.</Text>}
      {view && level && vp && (
        <>
          <Text style={s.body}>{levelLabel(level)}</Text>
          <Text style={s.muted}>Zoom ×{view.zoom} · tiles {vp.x0}–{vp.x1}, {vp.y0}–{vp.y1} of {level.size[0]}×{level.size[1]}</Text>
          <View style={s.row}>
            <Btn label="Zoom out" onPress={() => setView({ ...view, zoom: stepZoom(view.zoom, -1) })} disabled={!canZoom(view.zoom, -1)} />
            <Btn label="Zoom in" onPress={() => setView({ ...view, zoom: stepZoom(view.zoom, 1) })} disabled={!canZoom(view.zoom, 1)} />
          </View>
          <View style={s.row}>
            <Btn label="West" onPress={() => setView(panView(view, level, -1, 0))} />
            <Btn label="North" onPress={() => setView(panView(view, level, 0, -1))} />
            <Btn label="South" onPress={() => setView(panView(view, level, 0, 1))} />
            <Btn label="East" onPress={() => setView(panView(view, level, 1, 0))} />
          </View>
          <View style={s.row}>
            <Btn label="Level down" onPress={() => setView(switchLevel(stack, view, -1))} disabled={level.index === 0} />
            <Btn label="Level up" onPress={() => setView(switchLevel(stack, view, 1))} disabled={level.index === stack.length - 1} />
          </View>
          <View style={s.wrap}>
            {stack.slice().reverse().map(l => (
              <Btn key={l.id} label={levelLabel(l)} active={l.id === view.layer} onPress={() => setView(jumpToLevel(stack, view, l.id))} />
            ))}
          </View>
          <Text style={s.subtitle}>World portals here</Text>
          {exits.length ? exits.map(({ portal, exit }) => (
            <Btn key={portal.portal_id} label={`${portal.portal_id} (${portal.mode}) → ${exit.layer} @ ${exit.x},${exit.y}`}
              onPress={() => setView(travelThroughPortal(portals, stack, view, portal.portal_id))} />
          )) : <Text style={s.muted}>No declared portals leave this level.</Text>}
        </>
      )}
    </View>
  );
}

function Btn({ label, onPress, disabled, active }: { label: string; onPress: () => void; disabled?: boolean; active?: boolean }) {
  return (
    <TouchableOpacity accessibilityRole="button" accessibilityState={{ disabled: !!disabled, selected: !!active }}
      onPress={onPress} disabled={disabled} style={[s.btn, active && s.btnActive, disabled && s.btnDisabled]}>
      <Text style={s.btnText}>{label}</Text>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: '#111c2e', borderRadius: 12, padding: 14, gap: 8, marginTop: 12 },
  title: { color: '#e8eef8', fontSize: 17, fontWeight: '700' },
  subtitle: { color: '#c8d4e6', fontSize: 14, fontWeight: '600', marginTop: 6 },
  body: { color: '#e8eef8', fontSize: 14 },
  muted: { color: '#8a9ab0', fontSize: 13 },
  error: { color: '#ff8a8a', fontSize: 13 },
  row: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  input: { flex: 1, color: '#e8eef8', borderColor: '#2a3a55', borderWidth: 1, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 6 },
  btn: { backgroundColor: '#1d2c46', borderRadius: 8, paddingHorizontal: 10, paddingVertical: 7 },
  btnActive: { backgroundColor: '#2f5fa8' },
  btnDisabled: { opacity: 0.4 },
  btnText: { color: '#e8eef8', fontSize: 13 },
});
