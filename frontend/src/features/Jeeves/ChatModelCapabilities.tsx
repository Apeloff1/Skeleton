import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

const LABELS: Record<string, string> = {
  'text-generation': 'Text', 'tool-calling': 'Tool calls', 'tool-calls': 'Tool calls', 'structured-output': 'Structured answers',
  'image-generation': 'Image generation', 'image-understanding': 'Image input',
  'speech-generation': 'Speech output', 'speech-recognition': 'Speech input', embeddings: 'Embeddings',
};

const FAMILIES: Record<string, string> = { native_transformer: 'Local Transformer', gguf_open_weight: 'GGUF open-weight model', numpy_recurrent_baseline: 'Recurrent language model', reference_ngram: 'Reference language model', operator_callable: 'Operator-configured local model' };

/** Declared model capabilities are separate from which tools this chat grants. */
export default function ChatModelCapabilities({ capabilities, contextWindow, outputLimit, modelFamily }: {
  capabilities: readonly string[];
  contextWindow?: number | null;
  outputLimit?: number | null;
  modelFamily?: string;
}) {
  const labels = [...new Set(capabilities)].filter(value => Object.hasOwn(LABELS, value));
  return <View style={s.group}>
    {modelFamily && FAMILIES[modelFamily] && <Text style={s.detail}>{FAMILIES[modelFamily]}</Text>}
    {!!labels.length && <View style={s.row}>{labels.map(value => <Text key={value} style={s.chip}>{LABELS[value]}</Text>)}</View>}
    {(contextWindow || outputLimit) ? <Text style={s.detail}>
      {contextWindow ? `${contextWindow.toLocaleString()} context tokens` : ''}
      {contextWindow && outputLimit ? ' · ' : ''}
      {outputLimit ? `${outputLimit.toLocaleString()} maximum answer tokens` : ''}
    </Text> : null}
  </View>;
}

const s = StyleSheet.create({
  group: { gap: 6 }, row: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { color: '#c4b5fd', borderColor: '#463568', borderWidth: 1, borderRadius: 8, paddingVertical: 3, paddingHorizontal: 7, fontSize: 10 },
  detail: { color: '#94a3b8', fontSize: 11, lineHeight: 17 },
});
