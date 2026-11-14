/**
 * AI Debugger Modal v11.0.0
 * Autonomous Debugging System with AI-Powered Analysis
 */

import React, { useState, useEffect } from 'react';
import { API_BASE } from '../../utils/apiBase';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput,
  Modal, ActivityIndicator, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
const API_URL = API_BASE;

interface DebuggerModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  currentCode?: string;
  currentLanguage?: string;
  onApplyFix?: (fixedCode: string) => void;
}

type DebugMode = 'analyze' | 'security' | 'performance' | 'quickfix' | 'explain';

export const DebuggerModal: React.FC<DebuggerModalProps> = ({
  visible, onClose, colors, currentCode = '', currentLanguage = 'python', onApplyFix
}) => {
  const [mode, setMode] = useState<DebugMode | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [code, setCode] = useState(currentCode);
  const [errorMessage, setErrorMessage] = useState('');
  const [debugLevel, setDebugLevel] = useState<'quick' | 'standard' | 'deep'>('standard');

  useEffect(() => {
    if (visible && currentCode) {
      setCode(currentCode);
    }
  }, [visible, currentCode]);

  const analyzeCode = async () => {
    if (!code.trim()) return;
    setIsLoading(true);
    setResult(null);
    try {
      const response = await apiFetch(`${API_URL}/api/debugger/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code,
          language: currentLanguage,
          error_message: errorMessage || undefined,
          debug_level: debugLevel
        })
      });
      const data = await response.json();
      setResult(data);
    } catch (error) {
      console.error('Debug failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const runSecurityScan = async () => {
    if (!code.trim()) return;
    setIsLoading(true);
    setResult(null);
    try {
      const response = await apiFetch(`${API_URL}/api/debugger/security-scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, language: currentLanguage, scan_type: 'full' })
      });
      const data = await response.json();
      setResult(data);
    } catch (error) {
      console.error('Security scan failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const runPerformanceAnalysis = async () => {
    if (!code.trim()) return;
    setIsLoading(true);
    setResult(null);
    try {
      const response = await apiFetch(`${API_URL}/api/debugger/performance-analysis`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, language: currentLanguage })
      });
      const data = await response.json();
      setResult(data);
    } catch (error) {
      console.error('Performance analysis failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const getQuickFix = async () => {
    if (!code.trim()) return;
    setIsLoading(true);
    setResult(null);
    try {
      const response = await apiFetch(`${API_URL}/api/debugger/quick-fix?language=${currentLanguage}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(code)
      });
      const data = await response.json();
      setResult(data);
    } catch (error) {
      console.error('Quick fix failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const explainCode = async () => {
    if (!code.trim()) return;
    setIsLoading(true);
    setResult(null);
    try {
      const response = await apiFetch(`${API_URL}/api/debugger/explain-code?language=${currentLanguage}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(code)
      });
      const data = await response.json();
      setResult(data);
    } catch (error) {
      console.error('Explain failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAction = () => {
    switch (mode) {
      case 'analyze': analyzeCode(); break;
      case 'security': runSecurityScan(); break;
      case 'performance': runPerformanceAnalysis(); break;
      case 'quickfix': getQuickFix(); break;
      case 'explain': explainCode(); break;
    }
  };

  const modes = [
    { key: 'analyze', icon: 'bug-outline', label: 'Debug & Fix', desc: 'Find bugs and get fixes', color: '#EF4444' },
    { key: 'security', icon: 'shield-checkmark-outline', label: 'Security Scan', desc: 'OWASP vulnerability check', color: '#F59E0B' },
    { key: 'performance', icon: 'speedometer-outline', label: 'Performance', desc: 'Optimize for speed', color: '#10B981' },
    { key: 'quickfix', icon: 'flash-outline', label: 'Quick Fix', desc: 'Instant corrections', color: '#3B82F6' },
    { key: 'explain', icon: 'book-outline', label: 'Explain', desc: 'Understand code', color: '#8B5CF6' },
  ];

  const renderModeSelector = () => (
    <View style={styles.modesContainer}>
      <Text style={[styles.sectionTitle, { color: colors.textMuted }]}>Select Debug Mode</Text>
      {modes.map((m) => (
        <TouchableOpacity
          key={m.key}
          style={[styles.modeCard, { backgroundColor: colors.surfaceAlt, borderColor: mode === m.key ? m.color : colors.border }]}
          onPress={() => setMode(m.key as DebugMode)}
        >
          <View style={[styles.modeIcon, { backgroundColor: m.color + '20' }]}>
            <Ionicons name={m.icon as any} size={24} color={m.color} />
          </View>
          <View style={styles.modeInfo}>
            <Text style={[styles.modeLabel, { color: colors.text }]}>{m.label}</Text>
            <Text style={[styles.modeDesc, { color: colors.textMuted }]}>{m.desc}</Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color={colors.textMuted} />
        </TouchableOpacity>
      ))}
    </View>
  );

  const renderAnalyzeForm = () => (
    <View style={styles.formContainer}>
      <Text style={[styles.sectionTitle, { color: colors.textMuted }]}>Code to Debug</Text>
      <TextInput
        style={[styles.codeInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
        multiline
        value={code}
        onChangeText={setCode}
        placeholder="Paste your code here..."
        placeholderTextColor={colors.textMuted}
      />
      
      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Error Message (Optional)</Text>
      <TextInput
        style={[styles.textInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
        value={errorMessage}
        onChangeText={setErrorMessage}
        placeholder="Paste error or stack trace..."
        placeholderTextColor={colors.textMuted}
        multiline
      />

      <Text style={[styles.inputLabel, { color: colors.textMuted }]}>Debug Level</Text>
      <View style={styles.levelSelector}>
        {['quick', 'standard', 'deep'].map((level) => (
          <TouchableOpacity
            key={level}
            style={[styles.levelBtn, { backgroundColor: debugLevel === level ? colors.primary : colors.surfaceAlt }]}
            onPress={() => setDebugLevel(level as any)}
          >
            <Text style={[styles.levelText, { color: debugLevel === level ? '#FFF' : colors.text }]}>
              {level.charAt(0).toUpperCase() + level.slice(1)}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity
        style={[styles.actionBtn, { backgroundColor: colors.primary }]}
        onPress={handleAction}
        disabled={isLoading || !code.trim()}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="search" size={20} color="#FFF" />
            <Text style={styles.actionBtnText}>Analyze Code</Text>
          </>
        )}
      </TouchableOpacity>
    </View>
  );

  const renderResult = () => {
    if (!result) return null;
    
    return (
      <View style={styles.resultContainer}>
        {result.severity && (
          <View style={[styles.severityBadge, { backgroundColor: getSeverityColor(result.severity) + '20' }]}>
            <Text style={[styles.severityText, { color: getSeverityColor(result.severity) }]}>
              {result.issues_found || 0} issues • {result.severity.toUpperCase()}
            </Text>
          </View>
        )}
        
        {result.vulnerabilities && (
          <View style={[styles.statsRow, { backgroundColor: colors.surfaceAlt }]}>
            <View style={styles.statItem}>
              <Text style={[styles.statValue, { color: '#EF4444' }]}>{result.vulnerabilities.critical || 0}</Text>
              <Text style={[styles.statLabel, { color: colors.textMuted }]}>Critical</Text>
            </View>
            <View style={styles.statItem}>
              <Text style={[styles.statValue, { color: '#F59E0B' }]}>{result.vulnerabilities.high || 0}</Text>
              <Text style={[styles.statLabel, { color: colors.textMuted }]}>High</Text>
            </View>
            <View style={styles.statItem}>
              <Text style={[styles.statValue, { color: '#3B82F6' }]}>{result.vulnerabilities.medium || 0}</Text>
              <Text style={[styles.statLabel, { color: colors.textMuted }]}>Medium</Text>
            </View>
            <View style={styles.statItem}>
              <Text style={[styles.statValue, { color: '#10B981' }]}>{result.vulnerabilities.low || 0}</Text>
              <Text style={[styles.statLabel, { color: colors.textMuted }]}>Low</Text>
            </View>
          </View>
        )}

        <ScrollView style={styles.analysisScroll}>
          <Text style={[styles.analysisText, { color: colors.text }]}>
            {result.analysis?.raw_analysis || result.analysis || result.explanation || result.debug_assistance || result.review || JSON.stringify(result, null, 2)}
          </Text>
        </ScrollView>

        {result.fixed_code && onApplyFix && (
          <TouchableOpacity
            style={[styles.applyBtn, { backgroundColor: '#10B981' }]}
            onPress={() => {
              onApplyFix(result.fixed_code);
              onClose();
            }}
          >
            <Ionicons name="checkmark-circle" size={20} color="#FFF" />
            <Text style={styles.applyBtnText}>Apply Fix</Text>
          </TouchableOpacity>
        )}
      </View>
    );
  };

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'critical': return '#EF4444';
      case 'high': return '#F59E0B';
      case 'medium': return '#3B82F6';
      default: return '#10B981';
    }
  };

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <View style={[styles.header, { borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={mode ? () => { setMode(null); setResult(null); } : onClose} style={styles.backBtn}>
            <Ionicons name={mode ? "arrow-back" : "close"} size={24} color={colors.text} />
          </TouchableOpacity>
          <View style={styles.headerTitle}>
            <Ionicons name="bug" size={24} color="#EF4444" />
            <Text style={[styles.title, { color: colors.text }]}>AI Debugger</Text>
          </View>
          <View style={{ width: 40 }} />
        </View>

        <ScrollView style={styles.content} contentContainerStyle={styles.contentContainer}>
          {!mode && renderModeSelector()}
          {mode && !result && renderAnalyzeForm()}
          {result && renderResult()}
        </ScrollView>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1 },
  backBtn: { width: 40, height: 40, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  title: { fontSize: 18, fontWeight: '700' },
  content: { flex: 1 },
  contentContainer: { padding: 16 },
  modesContainer: { gap: 12 },
  sectionTitle: { fontSize: 13, fontWeight: '600', marginBottom: 12, textTransform: 'uppercase', letterSpacing: 0.5 },
  modeCard: { flexDirection: 'row', alignItems: 'center', padding: 16, borderRadius: 12, borderWidth: 2, gap: 14 },
  modeIcon: { width: 48, height: 48, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
  modeInfo: { flex: 1 },
  modeLabel: { fontSize: 16, fontWeight: '700' },
  modeDesc: { fontSize: 13, marginTop: 2 },
  formContainer: { gap: 16 },
  codeInput: { minHeight: 150, padding: 14, borderRadius: 12, borderWidth: 1, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', fontSize: 13, textAlignVertical: 'top' },
  inputLabel: { fontSize: 13, fontWeight: '600' },
  textInput: { padding: 14, borderRadius: 12, borderWidth: 1, minHeight: 80, textAlignVertical: 'top' },
  levelSelector: { flexDirection: 'row', gap: 10 },
  levelBtn: { flex: 1, paddingVertical: 12, borderRadius: 10, alignItems: 'center' },
  levelText: { fontSize: 14, fontWeight: '600' },
  actionBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 16, borderRadius: 12, gap: 10, marginTop: 8 },
  actionBtnText: { color: '#FFF', fontSize: 16, fontWeight: '700' },
  resultContainer: { gap: 16 },
  severityBadge: { alignSelf: 'flex-start', paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20 },
  severityText: { fontSize: 14, fontWeight: '700' },
  statsRow: { flexDirection: 'row', padding: 16, borderRadius: 12, justifyContent: 'space-around' },
  statItem: { alignItems: 'center' },
  statValue: { fontSize: 24, fontWeight: '800' },
  statLabel: { fontSize: 12, marginTop: 4 },
  analysisScroll: { maxHeight: 400 },
  analysisText: { fontSize: 14, lineHeight: 22 },
  applyBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 16, borderRadius: 12, gap: 10, marginTop: 16 },
  applyBtnText: { color: '#FFF', fontSize: 16, fontWeight: '700' },
});
