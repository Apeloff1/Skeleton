/**
 * Organism factory strip — surfaces P0–P4 + wave kernels inside Galaxy Studio.
 * Uses the same T palette. No new look.
 */
import React from 'react';
import { View, Text } from 'react-native';
import { T, s } from './GalaxyStudioFactoryModal.styles';

const ROWS: { label: string; value: string }[] = [
  { label: 'day / spec', value: 'game/data/spec.json' },
  { label: 'godot slice', value: '27 files + walk score' },
  { label: 'cockpit', value: 'speed / heat / collapse' },
  { label: 'snowball', value: 'mass +0.25–0.40' },
  { label: 'field', value: 'unique bind + CDX' },
  { label: 'ship', value: 'godot.zip data.zip web.zip' },
  { label: 'kernels', value: 'looped 27 · obscure 29 · social 20 · wave 6' },
];

export function OrganismPreviewPanel() {
  return (
    <View
      testID="organism-preview-panel"
      style={{
        backgroundColor: T.surfaceAlt,
        borderRadius: 10,
        padding: 10,
        borderWidth: 1,
        borderColor: T.border,
        marginBottom: 14,
      }}
    >
      <Text style={{ color: T.accent, fontSize: 11, fontWeight: '800', letterSpacing: 0.6, textTransform: 'uppercase', marginBottom: 8 }}>
        Organism live
      </Text>
      {ROWS.map((row) => (
        <View key={row.label} style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
          <Text style={{ color: T.textMuted, fontSize: 11, fontWeight: '700' }}>{row.label}</Text>
          <Text style={{ color: T.text, fontSize: 11, fontWeight: '600', flexShrink: 1, textAlign: 'right', marginLeft: 8 }}>
            {row.value}
          </Text>
        </View>
      ))}
    </View>
  );
}

export default OrganismPreviewPanel;
// keep styles import used so Metro does not drop s if tree-shaken oddly
void s;
