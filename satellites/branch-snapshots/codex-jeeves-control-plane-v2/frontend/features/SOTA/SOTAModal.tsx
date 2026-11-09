/**
 * SOTA 2026 Features Modal v11.3.0
 * Predictive Assistance, Auto-Refactoring, Multi-Model Orchestration
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

interface SOTAModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  currentCode?: string;
  currentLanguage?: string;
  onApplyCode?: (code: string) => void;
}

type SOTAFeature = 'predict' | 'refactor' | 'multi_model' | 'code_intel' | 'autocomplete';

export const SOTAModal: React.FC<SOTAModalProps> = ({
  visible, onClose, colors, currentCode, currentLanguage, onApplyCode
}) => {
  const [selectedFeature, setSelectedFeature] = useState<SOTAFeature | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [code, setCode] = useState(currentCode || '');
  const [task, setTask] = useState('');
  const [info, setInfo] = useState<any>(null);

  useEffect(() => {
    if (visible) {
      setCode(currentCode || '');
      fetchInfo();
    }
  }, [visible, currentCode]);

  const fetchInfo = async () => {
    try {
      const res = await apiFetch(`${API_URL}/api/sota/info`);
      const data = await res.json();
      setInfo(data);
    } catch (e) {
      console.error('Failed to fetch SOTA info:', e);
    }
  };

  const features = [
    { id: 'predict' as SOTAFeature, name: 'Predictive AI', icon: 'flash', color: '#3B82F6', desc: 'AI predicts your next action' },
    { id: 'refactor' as SOTAFeature, name: 'Auto Refactor', icon: 'git-compare', color: '#10B981', desc: 'Autonomous code improvement' },
    { id: 'multi_model' as SOTAFeature, name: 'Multi-Model', icon: 'layers', color: '#8B5CF6', desc: 'Multiple AI models consensus' },
    { id: 'code_intel' as SOTAFeature, name: 'Code Intel', icon: 'bulb', color: '#F59E0B', desc: 'Deep code understanding' },
    { id: 'autocomplete' as SOTAFeature, name: 'Smart Complete', icon: 'code-slash', color: '#EF4444', desc: 'Context-aware completion' },
  ];

  const runFeature = async () => {
    if (!selectedFeature) return;
    setLoading(true);
    setResult(null);

    try {
      let endpoint = '';
      let body: any = {};

      switch (selectedFeature) {
        case 'predict':
          endpoint = '/api/sota/predict';
          body = { code, language: currentLanguage || 'python', recent_actions: [] };
          break;
        case 'refactor':
          endpoint = '/api/sota/refactor';
          body = { code, language: currentLanguage || 'python', focus: 'all', preserve_behavior: true };
          break;
        case 'multi_model':
          endpoint = '/api/sota/multi-model';
          body = { task: task || 'Improve this code', code, language: currentLanguage || 'python', consensus_mode: 'best' };
          break;
        case 'code_intel':
          endpoint = '/api/sota/code-intel';
          body = { code, language: currentLanguage || 'python', analysis_types: ['complexity', 'patterns', 'suggestions'] };
          break;
        case 'autocomplete':
          endpoint = '/api/sota/autocomplete';
          body = { code, language: currentLanguage || 'python', cursor_line: code.split('\n').length, cursor_column: 0, trigger: 'manual' };
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
      console.error('SOTA feature error:', e);
    } finally {
      setLoading(false);
    }
  };

  const renderFeatureContent = () => {
    if (!selectedFeature) return null;

    return (
      <View style={styles.featureContent}>
        <TouchableOpacity style={styles.backButton} onPress={() => { setSelectedFeature(null); setResult(null); }}>
          <Ionicons name="arrow-back" size={20} color={colors.text} />
          <Text style={[styles.backText, { color: colors.text }]}>Back</Text>
        </TouchableOpacity>

        {/* Code Input */}
        <Text style={[styles.inputLabel, { color: colors.text }]}>Code</Text>
        <TextInput
          style={[styles.codeInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
          value={code}
          onChangeText={setCode}
          multiline
          numberOfLines={8}
          placeholder="Enter your code here..."
          placeholderTextColor={colors.textMuted}
        />

        {/* Task input for multi-model */}
        {selectedFeature === 'multi_model' && (
          <>
            <Text style={[styles.inputLabel, { color: colors.text }]}>Task Description</Text>
            <TextInput
              style={[styles.taskInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
              value={task}
              onChangeText={setTask}
              placeholder="What should the AI do with this code?"
              placeholderTextColor={colors.textMuted}
            />
          </>
        )}

        <TouchableOpacity
          style={[styles.runButton, { backgroundColor: loading ? colors.surfaceAlt : features.find(f => f.id === selectedFeature)?.color }]}
          onPress={runFeature}
          disabled={loading || !code.trim()}
        >
          {loading ? (
            <ActivityIndicator color="#FFF" />
          ) : (
            <>
              <Ionicons name="flash" size={20} color="#FFF" />
              <Text style={styles.runButtonText}>Run {features.find(f => f.id === selectedFeature)?.name}</Text>
            </>
          )}
        </TouchableOpacity>

        {/* Results */}
        {result && (
          <View style={[styles.resultContainer, { backgroundColor: colors.surfaceAlt }]}>
            <Text style={[styles.resultTitle, { color: colors.text }]}>Result</Text>
            <ScrollView style={styles.resultScroll} nestedScrollEnabled>
              <Text style={[styles.resultText, { color: colors.text }]}>
                {result.predictions?.next_code ||
                 result.refactored_analysis ||
                 result.final_output ||
                 result.analysis ||
                 result.completions ||
                 JSON.stringify(result, null, 2)}
              </Text>
            </ScrollView>
          </View>
        )}
      </View>
    );
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={[styles.modal, { backgroundColor: colors.surface }]}>
          {/* Header */}
          <View style={[styles.header, { borderBottomColor: colors.border }]}>
            <View style={styles.headerTitle}>
              <Ionicons name="rocket" size={24} color="#F59E0B" />
              <Text style={[styles.title, { color: colors.text }]}>SOTA 2026</Text>
            </View>
            <TouchableOpacity onPress={onClose}>
              <Ionicons name="close" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
            {!selectedFeature ? (
              <>
                <Text style={[styles.subtitle, { color: colors.textMuted }]}>
                  Bleeding-edge AI coding features
                </Text>

                {/* Feature Cards */}
                <View style={styles.featureGrid}>
                  {features.map((feature) => (
                    <TouchableOpacity
                      key={feature.id}
                      style={[styles.featureCard, { backgroundColor: feature.color + '15' }]}
                      onPress={() => setSelectedFeature(feature.id)}
                    >
                      <View style={[styles.featureIcon, { backgroundColor: feature.color + '25' }]}>
                        <Ionicons name={feature.icon as any} size={24} color={feature.color} />
                      </View>
                      <Text style={[styles.featureName, { color: colors.text }]}>{feature.name}</Text>
                      <Text style={[styles.featureDesc, { color: colors.textMuted }]}>{feature.desc}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                {/* Info */}
                {info && (
                  <View style={[styles.infoSection, { backgroundColor: colors.surfaceAlt }]}>
                    <Text style={[styles.infoTitle, { color: colors.text }]}>Capabilities</Text>
                    {Object.entries(info.features || {}).slice(0, 3).map(([key, val]: [string, any]) => (
                      <View key={key} style={styles.infoItem}>
                        <Text style={[styles.infoName, { color: colors.text }]}>{val.description}</Text>
                        <Text style={[styles.infoCaps, { color: colors.textMuted }]}>
                          {val.capabilities?.join(' • ')}
                        </Text>
                      </View>
                    ))}
                  </View>
                )}
              </>
            ) : (
              renderFeatureContent()
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
  subtitle: {
    fontSize: 14,
    marginBottom: 16,
    textAlign: 'center',
  },
  featureGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    marginBottom: 20,
  },
  featureCard: {
    width: '47%',
    padding: 16,
    borderRadius: 14,
    alignItems: 'center',
  },
  featureIcon: {
    width: 50,
    height: 50,
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 10,
  },
  featureName: {
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 4,
  },
  featureDesc: {
    fontSize: 12,
    textAlign: 'center',
  },
  infoSection: {
    padding: 16,
    borderRadius: 14,
  },
  infoTitle: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 12,
  },
  infoItem: {
    marginBottom: 12,
  },
  infoName: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 4,
  },
  infoCaps: {
    fontSize: 12,
  },
  featureContent: {
    paddingBottom: 20,
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
  inputLabel: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
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
  taskInput: {
    padding: 12,
    borderRadius: 10,
    borderWidth: 1,
    fontSize: 14,
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
