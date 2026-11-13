import React, { useEffect, useMemo, useState } from 'react';
import { Linking, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Clipboard from 'expo-clipboard';
import theme from '../../theme/tokens';

const C = theme.colors;
type Block =
  | { kind: 'paragraph' | 'quote'; text: string }
  | { kind: 'heading'; text: string; level: number }
  | { kind: 'list'; rows: { marker: string; text: string }[] }
  | { kind: 'code'; text: string; language: string }
  | { kind: 'table'; rows: string[][] }
  | { kind: 'rule' };

/** Render an inert Markdown subset. HTML and image URLs remain plain text. */
function markdown(text: string): Block[] {
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  const blocks: Block[] = [];
  let cursor = 0;
  while (cursor < lines.length) {
    const line = lines[cursor];
    if (!line.trim()) { cursor++; continue; }
    const fence = /^\s*(```+|~~~+)\s*([^\s]*)\s*$/.exec(line);
    if (fence) {
      const content: string[] = [];
      cursor++;
      while (cursor < lines.length) {
        const closing = /^\s*(`{3,}|~{3,})\s*$/.exec(lines[cursor]);
        if (closing && closing[1][0] === fence[1][0] && closing[1].length >= fence[1].length) break;
        content.push(lines[cursor++]);
      }
      if (cursor < lines.length) cursor++;
      blocks.push({ kind: 'code', text: content.join('\n'), language: fence[2].slice(0, 32) });
      continue;
    }
    const heading = /^(#{1,6})\s+(.+)$/.exec(line);
    if (heading) { blocks.push({ kind: 'heading', level: heading[1].length, text: heading[2].replace(/\s+#+$/, '') }); cursor++; continue; }
    if (/^\s*(?:---+|\*\*\*+|___+)\s*$/.test(line)) { blocks.push({ kind: 'rule' }); cursor++; continue; }
    if (/^\s*>/.test(line)) {
      const content: string[] = [];
      while (cursor < lines.length && /^\s*>/.test(lines[cursor])) content.push(lines[cursor++].replace(/^\s*>\s?/, ''));
      blocks.push({ kind: 'quote', text: content.join('\n') }); continue;
    }
    if (/^\s*(?:[-*+] |\d+[.)] )/.test(line)) {
      const rows: { marker: string; text: string }[] = [];
      while (cursor < lines.length) {
        const row = /^\s*([-*+]|\d+[.)])\s+(.+)$/.exec(lines[cursor]);
        if (!row) break;
        const task = /^\[([ xX])\]\s+(.+)$/.exec(row[2]);
        rows.push({ marker: task ? task[1] === ' ' ? '☐' : '☑' : /^\d/.test(row[1]) ? row[1] : '•', text: task ? task[2] : row[2] }); cursor++;
      }
      blocks.push({ kind: 'list', rows }); continue;
    }
    if (line.includes('|') && cursor + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[cursor + 1])) {
      const row = (value: string) => value.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(cell => cell.trim());
      const rows = [row(line)]; cursor += 2;
      while (cursor < lines.length && lines[cursor].includes('|') && lines[cursor].trim()) rows.push(row(lines[cursor++]));
      blocks.push({ kind: 'table', rows }); continue;
    }
    const content = [line]; cursor++;
    while (cursor < lines.length && lines[cursor].trim() && !/^\s*(?:#{1,6}\s|```|~~~|>|[-*+]\s|\d+[.)]\s)/.test(lines[cursor])) {
      if (/^\s*(?:---+|\*\*\*+|___+)\s*$/.test(lines[cursor])) break;
      content.push(lines[cursor++]);
    }
    blocks.push({ kind: 'paragraph', text: content.join('\n') });
  }
  return blocks;
}

function Inline({ text, notify }: { text: string; notify: (message: string) => void }) {
  const pattern = /(`[^`\n]+`|\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\n]+\*|~~[^~\n]+~~|(?<!!)\[[^\]\n]+\]\([^\s)]+\))/g;
  const parts: React.ReactNode[] = [];
  let end = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index || 0;
    if (start > end) parts.push(text.slice(end, start));
    const value = match[0];
    const key = `${start}:${value.length}`;
    if (value.startsWith('`')) parts.push(<Text key={key} style={s.inlineCode}>{value.slice(1, -1)}</Text>);
    else if (value.startsWith('**') || value.startsWith('__')) parts.push(<Text key={key} style={s.bold}>{value.slice(2, -2)}</Text>);
    else if (value.startsWith('~~')) parts.push(<Text key={key} style={s.strike}>{value.slice(2, -2)}</Text>);
    else if (value.startsWith('*')) parts.push(<Text key={key} style={s.italic}>{value.slice(1, -1)}</Text>);
    else {
      const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(value);
      if (link && /^(https?:\/\/|mailto:)/i.test(link[2])) {
        parts.push(<Text key={key} accessibilityRole="link" accessibilityLabel={`Open ${link[1]}`} style={s.link}
          onPress={() => { void Linking.openURL(link[2]).catch(() => notify('This link could not be opened.')); }}>{link[1]}</Text>);
      } else parts.push(value);
    }
    end = start + value.length;
  }
  if (end < text.length) parts.push(text.slice(end));
  return <>{parts}</>;
}

function CodeBlock({ text, language, notify }: { text: string; language: string; notify: (message: string) => void }) {
  const [copied, setCopied] = useState(false);
  useEffect(() => setCopied(false), [text]);
  const copy = async () => {
    try { await Clipboard.setStringAsync(text); setCopied(true); }
    catch { notify('Clipboard unavailable. Select the code to copy it.'); }
  };
  return <View style={s.code}>
    <View style={s.toolbar}>
      <Text style={s.language}>{language || 'Code'}</Text>
      <TouchableOpacity onPress={() => { void copy(); }} accessibilityRole="button" accessibilityLabel="Copy code" style={s.copy}>
        <Ionicons name={copied ? 'checkmark-outline' : 'copy-outline'} size={15} color={C.textMuted} />
        <Text style={s.copyLabel}>{copied ? 'Copied' : 'Copy code'}</Text>
      </TouchableOpacity>
    </View>
    <ScrollView horizontal showsHorizontalScrollIndicator contentContainerStyle={s.codeScroll}>
      <Text selectable style={s.codeText}>{text || ' '}</Text>
    </ScrollView>
  </View>;
}

export default function MessageContent({ text, notify, streaming = false }: {
  text: string; notify: (message: string) => void; streaming?: boolean;
}) {
  const blocks = useMemo(() => markdown(text), [text]);
  return <View style={s.content}>
    {blocks.map((block, index) => {
      if (block.kind === 'code') return <CodeBlock key={index} text={block.text} language={block.language} notify={notify} />;
      if (block.kind === 'rule') return <View key={index} style={s.rule} />;
      if (block.kind === 'list') return <View key={index} style={s.list}>{block.rows.map((row, item) =>
        <View key={item} style={s.listRow}><Text selectable style={s.marker}>{row.marker}</Text><Text selectable style={[s.text, s.listText]}><Inline text={row.text} notify={notify} /></Text></View>)}</View>;
      if (block.kind === 'table') return <ScrollView key={index} horizontal><View style={s.table}>{block.rows.map((row, rowIndex) =>
        <View key={rowIndex} style={[s.tableRow, rowIndex === 0 && s.tableHeader]}>{row.map((cell, column) =>
          <Text key={column} selectable style={[s.tableCell, rowIndex === 0 && s.bold]}><Inline text={cell} notify={notify} /></Text>)}</View>)}</View></ScrollView>;
      if (block.kind === 'heading') return <Text key={index} selectable accessibilityRole="header" style={[s.heading, block.level < 3 ? s.headingLarge : s.headingSmall]}><Inline text={block.text} notify={notify} /></Text>;
      return <Text key={index} selectable style={[s.text, block.kind === 'quote' && s.quote]}><Inline text={block.text} notify={notify} /></Text>;
    })}
    {streaming && <View accessibilityLabel="Response in progress" style={s.cursor} />}
  </View>;
}

const s = StyleSheet.create({
  content: { gap: theme.spacing.md, minWidth: 0 },
  text: { ...theme.typography.bodyLg, color: C.text, fontWeight: '400', lineHeight: 26 },
  bold: { fontWeight: '700' }, italic: { fontStyle: 'italic' }, strike: { textDecorationLine: 'line-through' },
  inlineCode: { ...theme.typography.mono, color: C.primaryHover, backgroundColor: C.primarySoft },
  link: { color: C.primaryHover, textDecorationLine: 'underline' },
  heading: { color: C.text, fontWeight: '700', marginTop: theme.spacing.sm },
  headingLarge: { ...theme.typography.h3 }, headingSmall: { ...theme.typography.h4 },
  quote: { color: C.textMuted, borderLeftWidth: 3, borderLeftColor: C.primary, paddingLeft: theme.spacing.base },
  rule: { height: 1, backgroundColor: C.border, marginVertical: theme.spacing.sm },
  list: { gap: theme.spacing.sm }, listRow: { flexDirection: 'row', alignItems: 'flex-start', gap: theme.spacing.md },
  marker: { ...theme.typography.bodyLg, color: C.textMuted, minWidth: 22, lineHeight: 26 }, listText: { flex: 1 },
  code: { borderWidth: 1, borderColor: C.borderStrong, backgroundColor: C.bg, borderRadius: theme.radii.md, overflow: 'hidden' },
  toolbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: C.bgElevated, paddingHorizontal: theme.spacing.base, minHeight: 42, gap: theme.spacing.lg },
  language: { ...theme.typography.caption, color: C.textMuted },
  copy: { flexDirection: 'row', alignItems: 'center', gap: theme.spacing.sm, paddingVertical: theme.spacing.md },
  copyLabel: { ...theme.typography.caption, color: C.textMuted },
  codeScroll: { padding: theme.spacing.base }, codeText: { ...theme.typography.mono, color: C.text, lineHeight: 22 },
  table: { borderWidth: 1, borderColor: C.border, borderRadius: theme.radii.sm, overflow: 'hidden' },
  tableRow: { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: C.border }, tableHeader: { backgroundColor: C.surfaceAlt },
  tableCell: { ...theme.typography.body, color: C.text, width: 180, padding: theme.spacing.md, borderRightWidth: 1, borderRightColor: C.border },
  cursor: { width: 6, height: 16, backgroundColor: C.primaryHover, borderRadius: theme.radii.xs },
});
