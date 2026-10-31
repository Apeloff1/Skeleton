/** Authenticated source-derived Epic travel audits, no fictitious native portal claims. */
import React, { useMemo, useState } from 'react';
import { ScrollView, Text, TextInput, TouchableOpacity, View } from 'react-native';
import {
  auditForgeEpicRoutes, type ForgeDocument,
  type ForgeEpicRouteAudit, type ForgeEpicRouteRequest,
} from '../../product/gameFrontierAuthoringClient';

type Props = {
  projectId: string;
  document: ForgeDocument | null;
  selectedLayer: string;
  siblingLayers: string[];
  disabled: boolean;
};

function SampleButton({label, press, disabled}: {
  label: string; press: () => void; disabled: boolean;
}) {
  return <TouchableOpacity accessibilityRole="button" accessibilityLabel={label}
      disabled={disabled} onPress={press}
      style={{borderWidth:1, borderRadius:7, borderColor:'#52748c',
              padding:10, opacity:disabled ? .5 : 1}}>
    <Text style={{color:'#e2f1ff'}}>{label}</Text>
  </TouchableOpacity>;
}

export default function GameFrontierEpicRoutePanel({
  projectId, document: source, selectedLayer, siblingLayers, disabled,
}: Props) {
  const [payload, setPayload] = useState('');
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState<ForgeEpicRouteAudit | null>(null);
  const [error, setError] = useState('');
  const scopedLayers = useMemo(
    () => [selectedLayer, ...siblingLayers.filter(name => name !== selectedLayer)]
      .filter((name, index, selected) => selected.indexOf(name) === index).slice(0,8),
    [selectedLayer, siblingLayers],
  );
  const sample = () => {
    const layers = scopedLayers.map(id => source?.layers.find(x => x.id === id))
      .filter((v): v is NonNullable<typeof v> => !!v);
    if (!layers.length) return;
    const nodes = layers.map(layer => ({
      layer: layer.id,
      x: Math.floor((layer.size[0] - 1) / 2),
      y: Math.floor((layer.size[1] - 1) / 2),
    }));
    const connectors: ForgeEpicRouteRequest['connectors'] = [];
    for (let i = 1; i < nodes.length; i += 1) {
      connectors.push({
        connector_id: 'epic_proposed_lift_' + i,
        from: nodes[i-1], to: nodes[i],
        mode: 'elevator', bidirectional: true,
      });
    }
    const first = layers[0];
    const start = {layer:first.id, x:0, y:nodes[0].y};
    const last = layers[layers.length-1];
    const goal = {
      layer:last.id, x:last.size[0]-1, y:nodes[nodes.length-1].y,
    };
    const data: ForgeEpicRouteRequest = {
      layer_ids: layers.map(layer => layer.id),
      connectors,
      itineraries: [
        {journey_id:'epic_world_crossing', start, goal,
         require_alternate:false},
      ],
    };
    setPayload(JSON.stringify(data, null, 2));
    setReport(null); setError('');
  };
  const run = async () => {
    if (!source || busy || disabled) return;
    setBusy(true); setError(''); setReport(null);
    try {
      const parsed: unknown = JSON.parse(payload);
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error('Supply typed layers, connectors and itineraries as JSON.');
      }
      const result = await auditForgeEpicRoutes(projectId,
        parsed as ForgeEpicRouteRequest);
      if (result.project_sha256 !== source.source_sha256 ||
          result.source_version !== source.expected_version) {
        throw new Error('The saved game revision changed. Reload before interpreting witnesses.');
      }
      setReport(result);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  };
  return <View style={{gap:7}}>
    <Text style={{color:'#e4f0ff', fontWeight:'700'}}>
      Epic cross-layer expedition and transfer assurance
    </Text>
    <Text style={{color:'#a8c3d8', fontSize:12}}>
      Inspect real authored tile corridors and proposed stairs, bridges,
      elevators, ferries, shuttles or portals across up to eight source layers.
      Witnesses and independently replayed receipts do not establish that
      the transfer has run in a native Godot game.
    </Text>
    <View style={{flexDirection:'row', flexWrap:'wrap', gap:8}}>
      <SampleButton label="Generate from selected Epic layers"
        disabled={disabled || busy || !source} press={sample}/>
      <SampleButton label={busy ? 'Checking source…' : 'Audit Epic itineraries'}
        disabled={disabled || busy || !source || !payload} press={() => {void run();}}/>
    </View>
    <TextInput accessibilityLabel="Epic inter-layer route and portal proposals JSON"
      value={payload} onChangeText={setPayload} multiline
      autoCapitalize="none" autoCorrect={false}
      editable={!busy && !disabled} maxLength={64000}
      style={{color:'#e7f3ff', backgroundColor:'#202936',
              fontFamily:'monospace', padding:12,
              minHeight:130, textAlignVertical:'top', borderRadius:8}}
    />
    {!!error && <Text accessibilityRole="alert" style={{color:'#ffb0a8'}}>{error}</Text>}
    {report && <View style={{gap:5}}>
      <Text style={{color:report.failed_count ? '#f3cc88' : '#b9dfc8'}}>
        {report.passed_count}/{report.journey_count} source journeys reachable
        {' · '}{report.layer_ids.length} live layers
        {' · '}{report.connectors.length} transfer proposals
      </Text>
      {report.journeys.map(j => <Text key={j.journey_id}
        style={{color:j.passed ? '#b6ddeb' : '#e9c096'}}>
        {j.journey_id}: {j.primary.reachable
          ? j.primary.steps + ' tile moves, ' + j.primary.transfers + ' crossings'
          : 'unreachable'}
        {j.require_alternate
          ? j.alternate?.reachable ? ' · independent alternate verified'
            : ' · no independent alternate' : ''}
        {j.failure ? ' · '+j.failure : ''}
      </Text>)}
      <ScrollView horizontal>
        <Text selectable style={{color:'#91a9bf', fontSize:11}}>
          Source SHA-256: {report.project_sha256}{'\n'}
          Independent replay receipt: {report.receipt_sha256}
        </Text>
      </ScrollView>
      <Text style={{color:'#9fb3c8',fontSize:11}}>
        Source-only connectivity. Transfers remain proposals requiring native
        implementation, physics, gameplay approval and full controller replay.
      </Text>
    </View>}
  </View>;
}
