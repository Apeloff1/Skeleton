import React from 'react';
import { Platform, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';

type Segment = { kind: 'text' | 'code'; content: string; language?: string };

/** Fenced code is displayed as inert, selectable text; no HTML is executed. */
function segments(text: string): Segment[] {
  const parts: Segment[] = [];
  const fence = /^```([^\n]*)\n([\s\S]*?)^```\s*$/gm;
  let end = 0;
  for (const match of text.matchAll(fence)) {
    const start = match.index || 0;
    if (start > end) parts.push({ kind: 'text', content: text.slice(end, start).trim() });
    parts.push({ kind: 'code', content: match[2].replace(/\n$/, ''), language: match[1].trim().slice(0, 30) });
    end = start + match[0].length;
  }
  if (end < text.length) parts.push({ kind: 'text', content: text.slice(end).trim() });
  return parts;
}

export default function MessageContent({ text, notify }: { text: string; notify: (message: string) => void }) {
  return <View style={styles.content}>
    {segments(text).map((segment, index) => segment.kind === 'text'
      ? <Text key={index} selectable style={styles.text}>{segment.content}</Text>
      : <View key={index} style={styles.code}>
        <View style={styles.toolbar}>
          <Text style={styles.language}>{segment.language || 'code'}</Text>
          <TouchableOpacity accessibilityRole="button" accessibilityLabel="Copy code" style={styles.copy}
            onPress={() => { void Clipboard.setStringAsync(segment.content).then(() => notify('Code copied.')).catch(() => notify('Clipboard unavailable. Select the code to copy it.')); }}>
            <Ionicons name="copy-outline" size={14} color="#c4b5fd" /><Text style={styles.copyLabel}>Copy code</Text>
          </TouchableOpacity>
        </View>
        <ScrollView horizontal contentContainerStyle={styles.codeScroll}>
          <Text selectable style={styles.codeText}>{segment.content}</Text>
        </ScrollView>
      </View>)}
  </View>;
}

const styles = StyleSheet.create({
  content: { gap: 12 }, text: { color: '#e2e8f0', fontSize: 15, lineHeight: 23 },
  code: { borderWidth: 1, borderColor: '#334155', backgroundColor: '#080f1c', borderRadius: 10, overflow: 'hidden' },
  toolbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#172135', paddingHorizontal: 12, paddingVertical: 7, gap: 20 },
  language: { color: '#94a3b8', fontSize: 11 }, copy: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingVertical: 6 },
  copyLabel: { color: '#c4b5fd', fontSize: 11 }, codeScroll: { padding: 14 },
  codeText: { color: '#d1fae5', fontSize: 13, lineHeight: 21, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace' },
});
