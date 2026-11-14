/**
 * SOTA recovery of Prood's DeepSlider control language into the GameForge
 * questionnaire. A track drag edits only a local draft; Forge applies it
 * explicitly on a run. No global/server-session cockpit state is assumed.
 */
import React from 'react';
import { Pressable, StyleSheet, Text, View, type GestureResponderEvent } from 'react-native';
import { DESIGN_AXES, normaliseAxisEdit, type DesignAxis } from '../instruments';
import { Button, Card } from './primitives';
import { C, TOUCH } from './theme';

export interface DesignInstrumentsProps {
  axes: Record<string, number>;
  onAxis: (axis: DesignAxis, value: number | null) => void;
  onReset: () => void;
}

function AxisControl({ axis, label, hint, value, onChange }: {
  axis: DesignAxis;
  label: string;
  hint: string;
  value?: number;
  onChange: (value: number | null) => void;
}) {
  const [width, setWidth] = React.useState(0);
  const edited = typeof value === 'number' && Number.isFinite(value);
  const current = edited ? value! : 0.5;
  const percent = Math.round(current * 100);
  const adjust = (delta: number) => {
    const next = normaliseAxisEdit(Math.round((current + delta) * 20) / 20);
    if (next !== null) onChange(next);
  };
  const point = (event: GestureResponderEvent) => {
    if (width <= 0) return;
    const fraction = Math.max(0, Math.min(1, event.nativeEvent.locationX / width));
    const next = normaliseAxisEdit(Math.round(fraction * 20) / 20);
    if (next !== null) onChange(next);
  };
  return (
    <View style={s.control} testID={'instrument-' + axis}>
      <View style={s.heading}>
        <Text style={s.label}>{label}</Text>
        <Text style={s.value} testID={'instrument-value-' + axis}>
          {edited ? percent + '% override' : 'Automatic'}
        </Text>
      </View>
      <Text style={s.help}>{hint}</Text>
      <View style={s.trackRow}>
        <Pressable
          accessibilityRole="button" accessibilityLabel={'Decrease ' + label}
          onPress={() => adjust(-0.05)} style={s.bump} testID={'instrument-minus-' + axis}
        ><Text style={s.bumpText}>−</Text></Pressable>
        <View
          testID={'instrument-track-' + axis}
          accessibilityRole="adjustable"
          accessibilityLabel={label}
          accessibilityHint="Drag to override the game design value, or use accessibility increment and decrement"
          accessibilityValue={{ min: 0, max: 100, now: percent, text: edited ? percent + ' percent' : 'Automatic; 50 percent starting point' }}
          accessibilityActions={[{ name: 'increment', label: 'Increase by five percent' }, { name: 'decrement', label: 'Decrease by five percent' }]}
          onAccessibilityAction={(event) => {
            if (event.nativeEvent.actionName === 'increment') adjust(0.05);
            else if (event.nativeEvent.actionName === 'decrement') adjust(-0.05);
          }}
          onLayout={(e) => setWidth(e.nativeEvent.layout.width)}
          onStartShouldSetResponder={() => true}
          onMoveShouldSetResponder={() => true}
          onResponderGrant={point}
          onResponderMove={point}
          style={s.track}
        >
          <View style={[s.fill, { width: (percent + '%') as any }]} />
          <View style={[s.thumb, { left: (percent + '%') as any }]} />
        </View>
        <Pressable
          accessibilityRole="button" accessibilityLabel={'Increase ' + label}
          onPress={() => adjust(0.05)} style={s.bump} testID={'instrument-plus-' + axis}
        ><Text style={s.bumpText}>+</Text></Pressable>
        <Button label="Auto" tone="ghost" compact disabled={!edited} onPress={() => onChange(null)} testID={'instrument-auto-' + axis} />
      </View>
    </View>
  );
}

export default function DesignInstruments({ axes, onAxis, onReset }: DesignInstrumentsProps) {
  const count = DESIGN_AXES.filter((axis) => axes[axis.id] !== undefined).length;
  return (
    <Card testID="gameforge-design-instruments" label="Design instrument panel">
      <View style={s.heading}>
        <Text style={s.title}>🎛 Game design instruments</Text>
        <Text style={s.value}>{count} of {DESIGN_AXES.length} overridden</Text>
      </View>
      <Text style={s.help}>
        Fine-tune the actual ten-axis GameForge design tensor. Values you leave automatic
        are determined by your creative brief, design beats and era. Changes are applied
        to the next Forge run, not stored in a shared server cockpit.
      </Text>
      {DESIGN_AXES.map((axis) => (
        <AxisControl
          key={axis.id} axis={axis.id} label={axis.label} hint={axis.hint}
          value={axes[axis.id]} onChange={(value) => onAxis(axis.id, value)}
        />
      ))}
      <Button label="Reset all instruments to automatic" tone="ghost" compact onPress={onReset} disabled={!count} testID="instrument-reset-all" />
    </Card>
  );
}

const s = StyleSheet.create({
  control: { paddingTop: 12, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: C.border },
  heading: { flexDirection: 'row', justifyContent: 'space-between', flexWrap: 'wrap', alignItems: 'center', gap: 8 },
  title: { color: C.textStrong, fontWeight: '800', fontSize: 15, marginBottom: 7 },
  label: { color: C.textStrong, fontWeight: '700', fontSize: 13 },
  value: { color: C.green, fontSize: 12, fontWeight: '700' },
  help: { color: C.mute, fontSize: 12, lineHeight: 19, marginTop: 5, marginBottom: 8 },
  trackRow: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  bump: { width: TOUCH, minHeight: TOUCH, borderRadius: 9, borderWidth: 1, borderColor: C.borderStrong, justifyContent: 'center', alignItems: 'center', backgroundColor: C.cardAlt },
  bumpText: { color: C.textStrong, fontSize: 22, fontWeight: '700' },
  track: { flex: 1, height: TOUCH, borderRadius: 9, borderWidth: 1, borderColor: C.borderStrong, justifyContent: 'center', backgroundColor: C.cardAlt, overflow: 'hidden' },
  fill: { height: '100%', backgroundColor: C.blue, position: 'absolute', left: 0, opacity: 0.48 },
  thumb: { width: 6, height: '100%', backgroundColor: C.textStrong, position: 'absolute', marginLeft: -3 },
});
