// ============================================================================
// CODEDOCK - CODE EDITOR COMPONENT
// ============================================================================

import React, { memo, useCallback } from 'react';
import { 
  View, Text, StyleSheet, TextInput, ScrollView, 
  TouchableOpacity, Platform, KeyboardAvoidingView 
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { ThemeColors } from '../../constants/themes';
import { Language } from '../../types';

interface CodeEditorProps {
  code: string;
  onCodeChange: (code: string) => void;
  fileName: string;
  onFileNameChange: (name: string) => void;
  language: Language | null;
  colors: ThemeColors;
  executionTime: number | null;
  isExecuting: boolean;
  onRun: () => void;
  onClear: () => void;
}

// eslint-disable-next-line react/display-name
export const CodeEditor: React.FC<CodeEditorProps> = memo(({
  code,
  onCodeChange,
  fileName,
  onFileNameChange,
  language,
  colors,
  executionTime,
  isExecuting,
  onRun,
  onClear,
}) => {
  const lines = code.split('\n');
  const lineCount = lines.length;

  const renderLineNumbers = useCallback(() => {
    return lines.map((_, index) => (
      <Text 
        key={index} 
        style={[styles.lineNumber, { color: colors.lineNumbers }]}
      >
        {index + 1}
      </Text>
    ));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lines.length, colors.lineNumbers]);

  return (
    <KeyboardAvoidingView 
      style={styles.container} 
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
    >
      {/* Editor Header */}
      <View style={[styles.header, { borderBottomColor: colors.borderSubtle }]}>
        <View style={[styles.tab, { backgroundColor: colors.primary + '20', borderBottomColor: colors.primary }]}>
          <TextInput
            style={[styles.fileNameInput, { color: colors.text }]}
            value={fileName}
            onChangeText={onFileNameChange}
            placeholder="filename"
            placeholderTextColor={colors.textMuted}
          />
          <Text style={[styles.extension, { color: colors.textMuted }]}>
            {language?.extension || ''}
          </Text>
        </View>
        {executionTime !== null && (
          <Text style={[styles.execTime, { color: colors.success }]}>
            {executionTime.toFixed(1)}ms
          </Text>
        )}
      </View>

      {/* Code Area */}
      <ScrollView style={styles.editorScroll} showsVerticalScrollIndicator={false}>
        <View style={styles.editorContent}>
          {/* Line Numbers */}
          <View style={[styles.lineNumbersContainer, { borderRightColor: colors.borderSubtle }]}>
            {renderLineNumbers()}
          </View>

          {/* Code Input */}
          <TextInput
            style={[styles.codeInput, { color: colors.text }]}
            value={code}
            onChangeText={onCodeChange}
            multiline
            autoCapitalize="none"
            autoCorrect={false}
            spellCheck={false}
            textAlignVertical="top"
            placeholder="// Write your code here..."
            placeholderTextColor={colors.textMuted}
          />
        </View>
      </ScrollView>

      {/* Action Bar */}
      <View style={[styles.actionBar, { backgroundColor: colors.surfaceAlt, borderTopColor: colors.border }]}>
        <View style={styles.actionLeft}>
          <Text style={[styles.lineInfo, { color: colors.textMuted }]}>
            {lineCount} lines • {code.length} chars
          </Text>
        </View>

        <View style={styles.actionRight}>
          <TouchableOpacity 
            style={[styles.clearButton, { borderColor: colors.border }]} 
            onPress={onClear}
          >
            <Ionicons name="trash-outline" size={16} color={colors.error} />
            <Text style={[styles.clearButtonText, { color: colors.error }]}>Clear</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[
              styles.runButton,
              { backgroundColor: isExecuting ? colors.textMuted : colors.success },
            ]}
            onPress={onRun}
            disabled={isExecuting}
          >
            <Ionicons name={isExecuting ? 'hourglass' : 'play'} size={18} color="#FFF" />
            <Text style={styles.runButtonText}>{isExecuting ? 'Running...' : 'Run'}</Text>
          </TouchableOpacity>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
});

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
  },
  tab: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 6,
    borderBottomWidth: 2,
  },
  fileNameInput: {
    fontSize: 13,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  extension: {
    fontSize: 13,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
  },
  execTime: {
    fontSize: 12,
    fontWeight: '600',
  },
  editorScroll: {
    flex: 1,
  },
  editorContent: {
    flexDirection: 'row',
    paddingVertical: 8,
  },
  lineNumbersContainer: {
    paddingHorizontal: 12,
    borderRightWidth: 1,
    alignItems: 'flex-end',
    minWidth: 45,
  },
  lineNumber: {
    fontSize: 13,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    lineHeight: 22,
  },
  codeInput: {
    flex: 1,
    paddingHorizontal: 12,
    fontSize: 14,
    fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace',
    lineHeight: 22,
    minHeight: 200,
  },
  actionBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderTopWidth: 1,
  },
  actionLeft: {
    flex: 1,
  },
  lineInfo: {
    fontSize: 12,
  },
  actionRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  clearButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    borderWidth: 1,
    gap: 6,
  },
  clearButtonText: {
    fontSize: 13,
    fontWeight: '600',
  },
  runButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
    gap: 8,
  },
  runButtonText: {
    color: '#FFF',
    fontSize: 15,
    fontWeight: '700',
  },
});

export default CodeEditor;
