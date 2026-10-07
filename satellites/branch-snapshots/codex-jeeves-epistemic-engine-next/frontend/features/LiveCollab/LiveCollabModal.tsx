/**
 * Live Collaboration Modal v11.3.0
 * AI Pair Programming, Live Sessions, Collaborative Debugging
 */

import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput,
  Modal, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';

import { apiFetch } from '../../utils/apiController';
const API_URL = Constants.expoConfig?.extra?.apiUrl || process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface LiveCollabModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  currentCode?: string;
  currentLanguage?: string;
  onCodeUpdate?: (code: string) => void;
}

type CollabMode = 'pair' | 'suggest' | 'debug' | 'explain' | 'refactor';

export const LiveCollabModal: React.FC<LiveCollabModalProps> = ({
  visible, onClose, colors, currentCode, currentLanguage, onCodeUpdate
}) => {
  const [mode, setMode] = useState<CollabMode | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [code, setCode] = useState(currentCode || '');
  const [task, setTask] = useState('');
  const [error, setError] = useState('');
  const [aiRole, setAiRole] = useState<'copilot' | 'driver' | 'navigator' | 'reviewer'>('copilot');
  const [info, setInfo] = useState<any>(null);

  useEffect(() => {
    if (visible) {
      setCode(currentCode || '');
      fetchInfo();
    }
  }, [visible, currentCode]);

  const fetchInfo = async () => {
    try {
      const res = await apiFetch(`${API_URL}/api/collab/info`);
      const data = await res.json();
      setInfo(data);
    } catch (e) {
      console.error('Failed to fetch collab info:', e);
    }
  };

  const modes = [
    { id: 'pair' as CollabMode, name: 'AI Pair Programming', icon: 'people', color: '#8B5CF6', desc: 'Code together with AI' },
    { id: 'suggest' as CollabMode, name: 'Live Suggestions', icon: 'bulb', color: '#3B82F6', desc: 'Real-time code hints' },
    { id: 'debug' as CollabMode, name: 'Collab Debug', icon: 'bug', color: '#EF4444', desc: 'Debug with AI partner' },
    { id: 'explain' as CollabMode, name: 'Live Explain', icon: 'chatbubbles', color: '#10B981', desc: 'Understand code instantly' },
    { id: 'refactor' as CollabMode, name: 'Instant Refactor', icon: 'git-compare', color: '#F59E0B', desc: 'Quick improvements' },
  ];

  const aiRoles = [
    { id: 'copilot' as const, name: 'Copilot', desc: 'Helps complete your code' },
    { id: 'driver' as const, name: 'Driver', desc: 'Writes code, you navigate' },
    { id: 'navigator' as const, name: 'Navigator', desc: 'Guides your coding' },
    { id: 'reviewer' as const, name: 'Reviewer', desc: 'Reviews as you code' },
  ];

  const runCollab = async () => {
    if (!mode) return;
    setLoading(true);
    setResult(null);

    try {
      let endpoint = '';
      let body: any = {};

      switch (mode) {
        case 'pair':
          endpoint = '/api/collab/pair-program';
          body = { code, language: currentLanguage || 'python', task: task || 'Help me improve this code', ai_role: aiRole };
          break;
        case 'suggest':
          endpoint = '/api/collab/live-suggest';
          body = { code, language: currentLanguage || 'python', cursor_line: code.split('\n').length, cursor_col: 0, recent_changes: [] };
          break;
        case 'debug':
          endpoint = '/api/collab/collab-debug';
          body = { code, language: currentLanguage || 'python', error: error || 'Unknown error', include_fix: true };
          break;
        case 'explain':
          endpoint = '/api/collab/explain-live';
          body = { code, language: currentLanguage || 'python', explain_level: 'detailed', highlight_lines: [] };
          break;
        case 'refactor':
          endpoint = '/api/collab/refactor-suggest';
          body = { code, language: currentLanguage || 'python', focus_areas: ['readability', 'performance'] };
          break;
      }

      const res = await apiFetch(`${API_URL}${endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      setResult(data);
    } catch (e) {
      console.error('Collab error:', e);
    } finally {
      setLoading(false);
    }
  };

  const getResultContent = () => {
    if (!result) return '';
    return result.response ||
           result.suggestions ||
           result.debug_analysis ||
           result.explanation ||
           JSON.stringify(result, null, 2);
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={[styles.modal, { backgroundColor: colors.surface }]}>
          {/* Header */}
          <View style={[styles.header, { borderBottomColor: colors.border }]}>
            <View style={styles.headerTitle}>
              <Ionicons name="people-circle" size={24} color="#8B5CF6" />
              <Text style={[styles.title, { color: colors.text }]}>Live Collaboration</Text>
            </View>
            <TouchableOpacity onPress={onClose}>
              <Ionicons name="close" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
            {!mode ? (
              <>
                {/* Session Info */}
                {info && (
                  <View style={[styles.sessionBanner, { backgroundColor: '#8B5CF615' }]}>
                    <Text style={[styles.sessionText, { color: colors.text }]}>
                      {info.active_sessions} Active Sessions • 5 Collab Modes
                    </Text>
                  </View>
                )}

                {/* Mode Selection */}
                <Text style={[styles.sectionTitle, { color: colors.text }]}>Choose Mode</Text>
                <View style={styles.modeGrid}>
                  {modes.map((m) => (
                    <TouchableOpacity
                      key={m.id}
                      style={[styles.modeCard, { backgroundColor: m.color + '15' }]}
                      onPress={() => setMode(m.id)}
                    >
                      <View style={[styles.modeIcon, { backgroundColor: m.color + '25' }]}>
                        <Ionicons name={m.icon as any} size={24} color={m.color} />
                      </View>
                      <Text style={[styles.modeName, { color: colors.text }]}>{m.name}</Text>
                      <Text style={[styles.modeDesc, { color: colors.textMuted }]}>{m.desc}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                {/* Features List */}
                {info?.features && (
                  <View style={[styles.featuresList, { backgroundColor: colors.surfaceAlt }]}>
                    {info.features.map((f: any) => (
                      <View key={f.id} style={styles.featureItem}>
                        <Text style={[styles.featureName, { color: colors.text }]}>{f.name}</Text>
                        <Text style={[styles.featureDesc, { color: colors.textMuted }]}>{f.desc}</Text>
                      </View>
                    ))}
                  </View>
                )}
              </>
            ) : (
              <>
                {/* Back Button */}
                <TouchableOpacity style={styles.backButton} onPress={() => { setMode(null); setResult(null); }}>
                  <Ionicons name="arrow-back" size={20} color={colors.text} />
                  <Text style={[styles.backText, { color: colors.text }]}>Back</Text>
                </TouchableOpacity>

                {/* Mode Header */}
                <View style={[styles.modeHeader, { backgroundColor: modes.find(m => m.id === mode)?.color + '15' }]}>
                  <Ionicons name={modes.find(m => m.id === mode)?.icon as any} size={28} color={modes.find(m => m.id === mode)?.color} />
                  <Text style={[styles.modeTitle, { color: colors.text }]}>{modes.find(m => m.id === mode)?.name}</Text>
                </View>

                {/* AI Role Selection for Pair Programming */}
                {mode === 'pair' && (
                  <View style={styles.roleSection}>
                    <Text style={[styles.inputLabel, { color: colors.text }]}>AI Role</Text>
                    <View style={styles.roleGrid}>
                      {aiRoles.map((role) => (
                        <TouchableOpacity
                          key={role.id}
                          style={[
                            styles.roleCard,
                            { 
                              backgroundColor: aiRole === role.id ? '#8B5CF625' : colors.surfaceAlt,
                              borderColor: aiRole === role.id ? '#8B5CF6' : colors.border
                            }
                          ]}
                          onPress={() => setAiRole(role.id)}
                        >
                          <Text style={[styles.roleName, { color: colors.text }]}>{role.name}</Text>
                          <Text style={[styles.roleDesc, { color: colors.textMuted }]}>{role.desc}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>
                )}

                {/* Task Input for Pair/Debug */}
                {(mode === 'pair' || mode === 'debug') && (
                  <>
                    <Text style={[styles.inputLabel, { color: colors.text }]}>
                      {mode === 'debug' ? 'Error Message (optional)' : 'Task Description'}
                    </Text>
                    <TextInput
                      style={[styles.taskInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
                      value={mode === 'debug' ? error : task}
                      onChangeText={mode === 'debug' ? setError : setTask}
                      placeholder={mode === 'debug' ? 'Paste error message...' : 'What do you want to accomplish?'}
                      placeholderTextColor={colors.textMuted}
                      multiline={mode === 'debug'}
                    />
                  </>
                )}

                {/* Code Input */}
                <Text style={[styles.inputLabel, { color: colors.text }]}>Your Code</Text>
                <TextInput
                  style={[styles.codeInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
                  value={code}
                  onChangeText={setCode}
                  multiline
                  numberOfLines={8}
                  placeholder="Enter your code..."
                  placeholderTextColor={colors.textMuted}
                />

                <TouchableOpacity
                  style={[styles.runButton, { backgroundColor: loading ? colors.surfaceAlt : modes.find(m => m.id === mode)?.color }]}
                  onPress={runCollab}
                  disabled={loading || !code.trim()}
                >
                  {loading ? (
                    <ActivityIndicator color="#FFF" />
                  ) : (
                    <>
                      <Ionicons name="flash" size={20} color="#FFF" />
                      <Text style={styles.runButtonText}>Start Collaboration</Text>
                    </>
                  )}
                </TouchableOpacity>

                {/* Result */}
                {result && (
                  <View style={[styles.resultContainer, { backgroundColor: colors.surfaceAlt }]}>
                    <Text style={[styles.resultTitle, { color: colors.text }]}>AI Response</Text>
                    <ScrollView style={styles.resultScroll} nestedScrollEnabled>
                      <Text style={[styles.resultText, { color: colors.text }]}>
                        {getResultContent()}
                      </Text>
                    </ScrollView>
                  </View>
                )}
              </>
            )}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  modal: {
    maxHeight: '90%',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
  },
  headerTitle: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
  },
  content: {
    padding: 16,
  },
  sessionBanner: {
    padding: 12,
    borderRadius: 10,
    marginBottom: 16,
  },
  sessionText: {
    fontSize: 14,
    fontWeight: '600',
    textAlign: 'center',
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 12,
  },
  modeGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginBottom: 20,
  },
  modeCard: {
    width: '48%',
    padding: 14,
    borderRadius: 12,
    alignItems: 'center',
  },
  modeIcon: {
    width: 48,
    height: 48,
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 10,
  },
  modeName: {
    fontSize: 13,
    fontWeight: '700',
    textAlign: 'center',
    marginBottom: 4,
  },
  modeDesc: {
    fontSize: 11,
    textAlign: 'center',
  },
  featuresList: {
    padding: 14,
    borderRadius: 12,
    gap: 12,
  },
  featureItem: {
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(0,0,0,0.05)',
    paddingBottom: 10,
  },
  featureName: {
    fontSize: 14,
    fontWeight: '600',
  },
  featureDesc: {
    fontSize: 12,
    marginTop: 2,
  },
  backButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 16,
  },
  backText: {
    fontSize: 14,
    fontWeight: '600',
  },
  modeHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 16,
    borderRadius: 12,
    marginBottom: 16,
  },
  modeTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  roleSection: {
    marginBottom: 16,
  },
  roleGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  roleCard: {
    width: '48%',
    padding: 12,
    borderRadius: 10,
    borderWidth: 2,
  },
  roleName: {
    fontSize: 13,
    fontWeight: '700',
  },
  roleDesc: {
    fontSize: 11,
    marginTop: 2,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
  },
  taskInput: {
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
    fontSize: 14,
    marginBottom: 16,
    minHeight: 50,
  },
  codeInput: {
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
    fontSize: 13,
    fontFamily: 'monospace',
    minHeight: 150,
    textAlignVertical: 'top',
    marginBottom: 16,
  },
  runButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    borderRadius: 12,
    gap: 10,
  },
  runButtonText: {
    color: '#FFF',
    fontSize: 16,
    fontWeight: '700',
  },
  resultContainer: {
    marginTop: 16,
    padding: 14,
    borderRadius: 12,
  },
  resultTitle: {
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 10,
  },
  resultScroll: {
    maxHeight: 250,
  },
  resultText: {
    fontSize: 13,
    lineHeight: 20,
  },
});
