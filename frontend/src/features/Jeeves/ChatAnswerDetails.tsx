import React, { useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import type { ConversationMessage } from '../../product/governedConversationClient';

/** Counts come from the committed message, never from claims inside the answer. */
export default function ChatAnswerDetails({ message }: { message: ConversationMessage }) {
  const [open, setOpen] = useState(false);
  if (message.author_type !== 'assistant') return null;
  const sources = message.context_source_snapshot?.length ?? 0;
  const citations = message.citation_refs.length;
  const tools = message.tool_receipt_refs.length;
  const models = message.provider_receipt_refs.length;
  return <View style={s.group}>
    <TouchableOpacity accessibilityRole="button" accessibilityLabel="Answer details" accessibilityState={{ expanded: open }}
      onPress={() => setOpen(value => !value)} style={s.button}>
      <Text style={s.summary}>Saved answer{sources ? ` · ${sources} context sources` : ''}{citations ? ` · ${citations} citations` : ''}{tools ? ` · ${tools} tool receipts` : ''}{models ? ` · ${models} model receipts` : ''} {open ? '▴' : '▾'}</Text>
    </TouchableOpacity>
    {open && <View style={s.group}>
      <Text style={s.text}>This reply is recorded on the current conversation branch. Its details describe the recorded work; they do not rate the answer’s accuracy.</Text>
      <Text style={s.text}>{sources ? `${sources} authorized source snapshots were selected for this turn.` : 'No context source snapshots are recorded for this turn.'}</Text>
      {!!tools && <Text style={s.text}>{tools} tool receipts are linked to this answer. Proposed actions in the reply still require their own execution.</Text>}
      {!!message.memory_refs?.length && <Text style={s.text}>{message.memory_refs.length} memory references are linked to this turn.</Text>}
      {!!message.context_digest && <Text selectable style={s.identity}>Context record: {message.context_digest.slice(0, 16)}…</Text>}
      {!!message.ai_result_id && <Text selectable style={s.identity}>Result: {message.ai_result_id}</Text>}
    </View>}
  </View>;
}

const s = StyleSheet.create({
  group: { gap: 5 }, button: { alignSelf: 'flex-start', minHeight: 36, justifyContent: 'center' },
  summary: { color: '#a5b4c9', fontSize: 11 }, text: { color: '#94a3b8', fontSize: 11, lineHeight: 17 },
  identity: { color: '#94a3b8', fontSize: 10, lineHeight: 16 },
});
