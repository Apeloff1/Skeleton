import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { normalizeDragonWisdomReview, type DragonWisdomReview } from './dragonWisdomReview';

export default function DragonWisdomSquares({ review }: { review: DragonWisdomReview }) {
  // Data originates from an authenticated product boundary. Digest syntax is
  // display validation only; it is not signature/receipt authentication.
  if (!normalizeDragonWisdomReview(review)) return <Text accessibilityRole="alert" style={s.note}>Dragon review unavailable: completed, validated review required.</Text>;
  return <View style={s.root}>
    <Text style={s.title}>Dragon's final review</Text>
    <Text style={s.note}>{review.completed_rounds} improvement cycles completed</Text>
    <View style={s.grid}>
      {review.squares.map(square => <View key={square.id} style={[s.square, square.status === 'blocked' && s.blocked]}>
        <Text style={s.label}>{square.label}</Text>
        <Text style={s.score}>{square.score.toFixed(0)}/100</Text>
        <Text style={s.status}>{square.status}</Text>
        <Text style={s.note}>{square.industry_score === null ? 'Industry comparison: unknown' :
          `Measured peers: ${square.industry_score.toFixed(0)} · ${(square.industry_delta ?? 0) >= 0 ? '+' : ''}${square.industry_delta?.toFixed(0)}`}</Text>
      </View>)}
    </View>
    {review.blockers.length > 0 && <Text accessibilityRole="alert" style={s.warning}>Release review blocked: {review.blockers.slice(0, 8).join('; ')}{review.blockers.length > 8 ? `; plus ${review.blockers.length - 8} more` : ''}</Text>}
    {review.improvements.slice(0, 4).map((item, index) => <Text key={`${item.target}-${item.axis}-${index}`} style={s.note}>{item.target}: {item.instruction}</Text>)}
    <Text style={s.note}>Quality advice. Independent legal clearance and release checks still apply.</Text>
  </View>;
}

const s = StyleSheet.create({
  root: { gap: 8, padding: 12, borderRadius: 14, backgroundColor: '#111827' },
  title: { color: '#fef3c7', fontSize: 16, fontWeight: '700' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  square: { flexBasis: '46%', flexGrow: 1, padding: 12, borderRadius: 12, borderWidth: 1, borderColor: '#475569', gap: 4 },
  blocked: { borderColor: '#fb7185' },
  label: { color: '#e2e8f0', fontSize: 12, fontWeight: '700' },
  score: { color: '#f8fafc', fontSize: 24, fontWeight: '800' },
  status: { color: '#fbbf24', fontSize: 11 },
  note: { color: '#cbd5e1', fontSize: 11, lineHeight: 16 },
  warning: { color: '#fda4af', fontSize: 12, lineHeight: 18 },
});
