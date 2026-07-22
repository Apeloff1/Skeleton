import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, Modal, SafeAreaView, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const API = process.env.EXPO_PUBLIC_BACKEND_URL || '';

const LANGS = [
  { id: 'python', name: 'Python 3', icon: 'logo-python' as const, color: '#3B82F6', template: 'def solution():\n    # Write your code here\n    print("Hello, World!")\n\nsolution()' },
  { id: 'javascript', name: 'JavaScript', icon: 'logo-javascript' as const, color: '#F59E0B', template: 'function solution() {\n  // Write your code here\n  console.log("Hello, World!");\n}\n\nsolution();' },
  { id: 'typescript', name: 'TypeScript', icon: 'code-slash' as const, color: '#3178C6', template: 'function solution(): void {\n  console.log("Hello, TypeScript!");\n}\n\nsolution();' },
  { id: 'go', name: 'Go', icon: 'code-working' as const, color: '#00ADD8', template: 'package main\n\nimport "fmt"\n\nfunc main() {\n\tfmt.Println("Hello, Go!")\n}' },
  { id: 'rust', name: 'Rust', icon: 'hardware-chip' as const, color: '#CE422B', template: 'fn main() {\n    println!("Hello, Rust!");\n    \n    let x: i32 = 42;\n    println!("The answer is {}", x);\n}' },
  { id: 'c', name: 'C', icon: 'terminal' as const, color: '#A8B9CC', template: '#include <stdio.h>\n\nint main() {\n    printf("Hello, C!\\n");\n    return 0;\n}' },
  { id: 'cpp', name: 'C++', icon: 'rocket' as const, color: '#00599C', template: '#include <iostream>\nusing namespace std;\n\nint main() {\n    cout << "Hello, C++!" << endl;\n    return 0;\n}' },
];

interface Props { visible: boolean; onClose: () => void; }

export const CodePlaygroundModal: React.FC<Props> = ({ visible, onClose }) => {
  const [lang, setLang] = useState(LANGS[0]);
  const [code, setCode] = useState(LANGS[0].template);
  const [output, setOutput] = useState('');
  const [running, setRunning] = useState(false);
  const [execTime, setExecTime] = useState<number|null>(null);
  const [showSnippets, setShowSnippets] = useState(false);
  const [snippets, setSnippets] = useState<any[]>([]);

  const runCode = async () => {
    setRunning(true); setOutput(''); setExecTime(null);
    const start = Date.now();
    try {
      const res = await apiFetch(`${API}/api/playground/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ language: lang.id, code }),
      });
      const data = await res.json();
      setExecTime(Date.now() - start);
      if (data.error && data.output) {
        setOutput(`${data.output}\n--- STDERR ---\n${data.error}`);
      } else {
        setOutput(data.output || data.error || 'No output');
      }
    } catch {
      setOutput('Error: Could not connect to playground');
      setExecTime(Date.now() - start);
    } finally { setRunning(false); }
  };

  const loadSnippets = async () => {
    try {
      const res = await apiFetch(`${API}/api/enhance/snippets?language=${lang.id}&limit=20`);
      const data = await res.json();
      setSnippets(data.snippets || []);
      setShowSnippets(true);
    } catch { setSnippets([]); setShowSnippets(true); }
  };

  const selectLang = (l: typeof LANGS[0]) => {
    setLang(l); setCode(l.template); setOutput(''); setExecTime(null); setShowSnippets(false);
  };

  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaView style={st.container}>
        <View style={st.header}>
          <TouchableOpacity testID="pg-close" onPress={onClose} style={st.headerBtn}>
            <Ionicons name="close" size={24} color="#F8FAFC" />
          </TouchableOpacity>
          <Text style={st.headerTitle}>Code Playground</Text>
          <TouchableOpacity testID="pg-snippets" onPress={loadSnippets} style={st.headerBtn}>
            <Ionicons name="code-slash" size={22} color="#F59E0B" />
          </TouchableOpacity>
        </View>

        {/* Language Tabs — Scrollable */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={st.langBar} contentContainerStyle={st.langBarContent}>
          {LANGS.map(l => (
            <TouchableOpacity
              key={l.id}
              testID={`pg-lang-${l.id}`}
              style={[st.langTab, lang.id === l.id && { backgroundColor: l.color + '20', borderColor: l.color }]}
              onPress={() => selectLang(l)}
            >
              <Ionicons name={l.icon} size={16} color={lang.id === l.id ? l.color : '#64748B'} />
              <Text style={[st.langText, lang.id === l.id && { color: l.color }]}>{l.name}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {showSnippets ? (
          <ScrollView style={st.snippetList}>
            <Text style={st.sectionTitle}>CODE SNIPPETS — {lang.name}</Text>
            {snippets.length === 0 && <Text style={st.emptyText}>No snippets available for {lang.name}</Text>}
            {snippets.map((sn: any) => (
              <TouchableOpacity key={sn.id} style={st.snippetCard} onPress={() => { setCode(sn.code || ''); setShowSnippets(false); }}>
                <Text style={st.snippetTitle}>{sn.title}</Text>
                <Text style={st.snippetCode} numberOfLines={3}>{sn.code}</Text>
              </TouchableOpacity>
            ))}
            <TouchableOpacity style={st.backBtn} onPress={() => setShowSnippets(false)}>
              <Text style={st.backBtnText}>Back to Editor</Text>
            </TouchableOpacity>
          </ScrollView>
        ) : (
          <View style={st.editorArea}>
            <View style={st.editorHeader}>
              <Text style={st.editorLabel}>CODE</Text>
              <View style={st.langIndicator}>
                <View style={[st.langDot, { backgroundColor: lang.color }]} />
                <Text style={[st.langIndicatorText, { color: lang.color }]}>{lang.name}</Text>
              </View>
            </View>
            <TextInput
              testID="pg-editor"
              style={st.editor}
              multiline
              value={code}
              onChangeText={setCode}
              textAlignVertical="top"
              autoCapitalize="none"
              autoCorrect={false}
              spellCheck={false}
            />
            <TouchableOpacity
              testID="pg-run"
              style={[st.runBtn, { backgroundColor: lang.color }]}
              onPress={runCode}
              disabled={running}
            >
              {running ? (
                <ActivityIndicator color="#FFF" />
              ) : (
                <>
                  <Ionicons name="play" size={18} color="#FFF" />
                  <Text style={st.runBtnText}>Run {lang.name}</Text>
                </>
              )}
            </TouchableOpacity>
            <View style={st.outputHeader}>
              <Text style={st.editorLabel}>OUTPUT</Text>
              {execTime !== null && (
                <Text style={st.execTime}>{execTime}ms</Text>
              )}
            </View>
            <ScrollView style={st.outputBox}>
              <Text style={[st.outputText, output && !output.startsWith('Error') && { color: '#A7F3D0' }]}>
                {output || 'Output will appear here...'}
              </Text>
            </ScrollView>
          </View>
        )}
      </SafeAreaView>
    </Modal>
  );
};

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0F172A' },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, backgroundColor: '#1E293B', borderBottomWidth: 1, borderBottomColor: '#334155' },
  headerBtn: { width: 44, height: 44, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { flex: 1, fontSize: 18, fontWeight: '700', color: '#F8FAFC', textAlign: 'center' },
  langBar: { maxHeight: 52 },
  langBarContent: { paddingHorizontal: 12, paddingVertical: 8, gap: 8 },
  langTab: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 8, borderRadius: 10, borderWidth: 1, borderColor: '#334155', gap: 6, marginRight: 4 },
  langText: { fontSize: 12, fontWeight: '700', color: '#94A3B8' },
  editorArea: { flex: 1, paddingHorizontal: 12 },
  editorHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 6 },
  editorLabel: { fontSize: 11, fontWeight: '700', color: '#64748B', letterSpacing: 1 },
  langIndicator: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  langDot: { width: 8, height: 8, borderRadius: 4 },
  langIndicatorText: { fontSize: 11, fontWeight: '700' },
  editor: { flex: 1, backgroundColor: '#1E293B', borderRadius: 10, padding: 14, color: '#E2E8F0', fontFamily: 'monospace', fontSize: 13, lineHeight: 20, minHeight: 160, maxHeight: 260, borderWidth: 1, borderColor: '#334155' },
  runBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 12, borderRadius: 10, marginVertical: 8 },
  runBtnText: { fontSize: 15, fontWeight: '700', color: '#FFF' },
  outputHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 4 },
  execTime: { fontSize: 11, fontWeight: '700', color: '#22C55E' },
  outputBox: { flex: 1, backgroundColor: '#0D1117', borderRadius: 10, padding: 14, borderWidth: 1, borderColor: '#21262D', minHeight: 80 },
  outputText: { color: '#8B949E', fontFamily: 'monospace', fontSize: 13, lineHeight: 20 },
  sectionTitle: { fontSize: 12, fontWeight: '700', color: '#64748B', letterSpacing: 1, marginTop: 12, marginBottom: 8, paddingHorizontal: 12 },
  emptyText: { color: '#64748B', fontSize: 13, textAlign: 'center', paddingVertical: 20 },
  snippetList: { flex: 1, paddingHorizontal: 12 },
  snippetCard: { padding: 12, backgroundColor: '#1E293B', borderRadius: 10, marginBottom: 8 },
  snippetTitle: { fontSize: 14, fontWeight: '700', color: '#F8FAFC' },
  snippetCode: { fontSize: 11, color: '#94A3B8', fontFamily: 'monospace', marginTop: 4 },
  backBtn: { alignItems: 'center', paddingVertical: 12, marginTop: 8 },
  backBtnText: { fontSize: 14, fontWeight: '600', color: '#3B82F6' },
});
