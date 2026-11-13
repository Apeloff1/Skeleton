import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import type { ChatModelRuntimeFacts } from '../../product/chatModelCatalog';

const LABELS: Record<string, string> = {
  'text-generation': 'Text', 'tool-calling': 'Tool calls', 'tool-calls': 'Tool calls', 'structured-output': 'Structured answers',
  'image-generation': 'Image generation', 'image-understanding': 'Image input',
  'speech-generation': 'Speech output', 'speech-recognition': 'Speech input', embeddings: 'Embeddings',
};

const FAMILIES: Record<string, string> = { native_transformer: 'Local Transformer', gguf_open_weight: 'GGUF open-weight model', numpy_recurrent_baseline: 'Recurrent language model', reference_ngram: 'Reference language model', operator_callable: 'Operator-configured local model' };

/** Declared model capabilities are separate from which tools this chat grants. */
export default function ChatModelCapabilities({ capabilities, contextWindow, outputLimit, modelFamily, activation, tokenizer, limitsSource, runtimeFacts }: {
  capabilities: readonly string[];
  contextWindow?: number | null;
  outputLimit?: number | null;
  modelFamily?: string;
  activation?: Record<string, unknown> | null;
  tokenizer?: string;
  limitsSource?: string;
  runtimeFacts?: ChatModelRuntimeFacts;
}) {
  const labels = [...new Set(capabilities)].filter(value => Object.hasOwn(LABELS, value));
  const fingerprint = (value: unknown): string | null => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value) ? `${value.slice(0, 10)}…${value.slice(-6)}` : null;
  const modelDigest = fingerprint(activation?.model_digest);
  const catalogDigest = fingerprint(activation?.catalog_digest);
  return <View style={s.group}>
    {modelFamily && FAMILIES[modelFamily] && <Text style={s.detail}>{FAMILIES[modelFamily]}</Text>}
    {!!labels.length && <View style={s.row}>{labels.map(value => <Text key={value} style={s.chip}>{LABELS[value]}</Text>)}</View>}
    {(contextWindow || outputLimit) ? <Text style={s.detail}>
      {contextWindow ? `${contextWindow.toLocaleString()} context tokens` : ''}
      {contextWindow && outputLimit ? ' · ' : ''}
      {outputLimit ? `${outputLimit.toLocaleString()} maximum answer tokens` : ''}
    </Text> : null}
    {modelDigest && <Text style={s.detail}>Model fingerprint {modelDigest}{typeof activation?.source_model_id === 'string' ? ` · source model ${activation.source_model_id}` : ''}</Text>}
    {catalogDigest && <Text style={s.detail}>Pinned catalog {catalogDigest}</Text>}
    {(tokenizer || limitsSource) && <Text style={s.detail}>{tokenizer ? `Tokenizer: ${tokenizer.replaceAll('_', ' ')}` : ''}{tokenizer && limitsSource ? ' · ' : ''}{limitsSource ? `Limits: ${limitsSource.replaceAll('_', ' ')}` : ''}</Text>}
    {runtimeFacts?.serving_state && <Text style={s.detail}>Admission {runtimeFacts.serving_state.draining ? 'draining' : 'open'} · {runtimeFacts.serving_state.active.toLocaleString()} active · {runtimeFacts.serving_state.queued.toLocaleString()} queued · capacity {runtimeFacts.serving_state.effective_concurrency.toLocaleString()}</Text>}
    {runtimeFacts?.semantic_verifier_configured !== undefined && <Text style={s.detail}>Semantic verifier {runtimeFacts.semantic_verifier_configured ? 'configured' : 'not configured'}{runtimeFacts.semantic_verifier_configured && runtimeFacts.semantic_verifier_route ? ' · this is the configured verifier route' : ''}</Text>}
    {typeof runtimeFacts?.generation_limits?.max_output_utf8_bytes === 'number' && <Text style={s.detail}>Maximum generated text {runtimeFacts.generation_limits.max_output_utf8_bytes.toLocaleString()} UTF-8 bytes · token limits still apply</Text>}
  </View>;
}

const s = StyleSheet.create({
  group: { gap: 6 }, row: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  chip: { color: '#c4b5fd', borderColor: '#463568', borderWidth: 1, borderRadius: 8, paddingVertical: 3, paddingHorizontal: 7, fontSize: 10 },
  detail: { color: '#94a3b8', fontSize: 11, lineHeight: 17 },
});
