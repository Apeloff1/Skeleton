/**
 * Renders the vision with each trigger word tinted by the system it spawned
 * and a superscript glyph, so the mapping survives colour-blindness.
 */
import React from 'react';
import { StyleSheet, Text } from 'react-native';
import { featureMeta, highlightVision } from '../graph';
import { C } from './theme';

export default function VisionHighlight({ vision, matches, testID }: { vision: string; matches: Record<string, string[]> | null | undefined; testID?: string }) {
  const segs = highlightVision(vision, matches);
  if (!segs.length) return <Text style={st.empty} testID={testID}>Your vision will appear here with trigger words highlighted.</Text>;
  return (
    <Text style={st.text} testID={testID}>
      {segs.map((seg, i) => {
        if (!seg.features.length) return <Text key={i}>{seg.text}</Text>;
        const meta = featureMeta(seg.features[0]);
        const names = seg.features.map((f) => featureMeta(f).label).join(' and ');
        return (
          <Text
            key={i}
            style={[st.hit, { color: meta.color, backgroundColor: meta.color + '22' }]}
            accessibilityLabel={`${seg.text}, triggers ${names}`}
          >
            {seg.text}
            <Text style={st.sup}>{seg.features.map((f) => featureMeta(f).glyph).join('')}</Text>
          </Text>
        );
      })}
    </Text>
  );
}

const st = StyleSheet.create({
  text: { color: C.text, fontSize: 15, lineHeight: 24 },
  hit: { fontWeight: '800', borderRadius: 4 },
  sup: { fontSize: 10 },
  empty: { color: C.dim, fontSize: 13, fontStyle: 'italic' },
});
