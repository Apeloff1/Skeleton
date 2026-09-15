/**
 * Code Intelligence Modal v11.3.0
 * Semantic Search, Auto-Docs, Migration, Test Gen, Bug Prediction & More
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

interface CodeIntelligenceModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  currentCode?: string;
  currentLanguage?: string;
}

type IntelFeature = {
  id: string;
  name: string;
  desc: string;
  icon: string;
  color: string;
  endpoint: string;
};

export const CodeIntelligenceModal: React.FC<CodeIntelligenceModalProps> = ({
  visible, onClose, colors, currentCode, currentLanguage
}) => {
  const [selectedFeature, setSelectedFeature] = useState<IntelFeature | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [code, setCode] = useState(currentCode || '');
  const [info, setInfo] = useState<any>(null);

  useEffect(() => {
    if (visible) {
      setCode(currentCode || '');
      fetchInfo();
    }
  }, [visible, currentCode]);

  const fetchInfo = async () => {
    try {
      const res = await apiFetch(`${API_URL}/api/intelligence/info`);
      const data = await res.json();
      setInfo(data);
    } catch (e) {
      console.error('Failed to fetch intelligence info:', e);
    }
  };

  const features: IntelFeature[] = [
    { id: 'auto-document', name: 'Auto Docs', desc: 'Generate documentation', icon: 'document-text', color: '#3B82F6', endpoint: '/api/intelligence/auto-document' },
    { id: 'generate-tests', name: 'Test Gen', desc: 'Auto-generate tests', icon: 'checkmark-circle', color: '#10B981', endpoint: '/api/intelligence/generate-tests' },
    { id: 'predict-bugs', name: 'Bug Predict', desc: 'Predict potential bugs', icon: 'bug', color: '#EF4444', endpoint: '/api/intelligence/predict-bugs' },
    { id: 'code-review', name: 'AI Review', desc: 'Automated code review', icon: 'eye', color: '#8B5CF6', endpoint: '/api/intelligence/code-review' },
    { id: 'profile-performance', name: 'Performance', desc: 'Optimize code', icon: 'speedometer', color: '#F59E0B', endpoint: '/api/intelligence/profile-performance' },
    { id: 'analyze-architecture', name: 'Architecture', desc: 'Design analysis', icon: 'git-branch', color: '#2563EB', endpoint: '/api/intelligence/analyze-architecture' },
  ];

  const runFeature = async () => {
    if (!selectedFeature || !code.trim()) return;
    setLoading(true);
    setResult(null);

    try {
      const body: any = {
        code,
        language: currentLanguage || 'python',
      };

      // Add feature-specific params
      if (selectedFeature.id === 'auto-document') {
        body.doc_style = 'google';
        body.include_examples = true;
      } else if (selectedFeature.id === 'generate-tests') {
        body.framework = 'pytest';
        body.coverage_target = 'high';
        body.include_edge_cases = true;
      } else if (selectedFeature.id === 'code-review') {
        body.review_type = 'full';
      } else if (selectedFeature.id === 'profile-performance') {
        body.optimize_for = 'speed';
      } else if (selectedFeature.id === 'analyze-architecture') {
        body.analysis_depth = 'full';
      }

      const res = await apiFetch(`${API_URL}${selectedFeature.endpoint}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await res.json();
      setResult(data);
    } catch (e) {
      console.error('Intelligence feature error:', e);
    } finally {
      setLoading(false);
    }
  };

  const getResultText = () => {
    if (!result) return '';
    return result.documentation ||
           result.tests ||
           result.predictions ||
           result.review ||
           result.performance_analysis ||
           result.architecture_analysis ||
           JSON.stringify(result, null, 2);
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={[styles.modal, { backgroundColor: colors.surface }]}>
          {/* Header */}
          <View style={[styles.header, { borderBottomColor: colors.border }]}>
            <View style={styles.headerTitle}>
              <Ionicons name="bulb" size={24} color="#F59E0B" />
              <Text style={[styles.title, { color: colors.text }]}>Code Intelligence</Text>
            </View>
            <TouchableOpacity onPress={onClose}>
              <Ionicons name="close" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
            {!selectedFeature ? (
              <>
                {/* Feature Count */}
                {info && (
                  <View style={[styles.infoBanner, { backgroundColor: '#F59E0B15' }]}>
                    <Text style={[styles.infoText, { color: colors.text }]}>
                      {info.total_features} AI-Powered Features
                    </Text>
                  </View>
                )}

                {/* Feature Grid */}
                <View style={styles.featureGrid}>
                  {features.map((feature) => (
                    <TouchableOpacity
                      key={feature.id}
                      style={[styles.featureCard, { backgroundColor: feature.color + '15' }]}
                      onPress={() => setSelectedFeature(feature)}
                    >
                      <View style={[styles.featureIcon, { backgroundColor: feature.color + '25' }]}>
                        <Ionicons name={feature.icon as any} size={22} color={feature.color} />
                      </View>
                      <Text style={[styles.featureName, { color: colors.text }]}>{feature.name}</Text>
                      <Text style={[styles.featureDesc, { color: colors.textMuted }]}>{feature.desc}</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                {/* All Features List */}
                <Text style={[styles.sectionTitle, { color: colors.text }]}>All Capabilities</Text>
                <View style={[styles.capsList, { backgroundColor: colors.surfaceAlt }]}>
                  {info?.features?.map((f: any) => (
                    <View key={f.id} style={styles.capsItem}>
                      <Ionicons name="checkmark-circle" size={16} color="#10B981" />
                      <Text style={[styles.capsText, { color: colors.text }]}>{f.name}</Text>
                    </View>
                  ))}
                </View>
              </>
            ) : (
              <>
                {/* Back & Feature Header */}
                <TouchableOpacity style={styles.backButton} onPress={() => { setSelectedFeature(null); setResult(null); }}>
                  <Ionicons name="arrow-back" size={20} color={colors.text} />
                  <Text style={[styles.backText, { color: colors.text }]}>Back</Text>
                </TouchableOpacity>

                <View style={[styles.featureHeader, { backgroundColor: selectedFeature.color + '15' }]}>
                  <Ionicons name={selectedFeature.icon as any} size={28} color={selectedFeature.color} />
                  <Text style={[styles.featureTitle, { color: colors.text }]}>{selectedFeature.name}</Text>
                </View>

                {/* Code Input */}
                <Text style={[styles.inputLabel, { color: colors.text }]}>Your Code</Text>
                <TextInput
                  style={[styles.codeInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
                  value={code}
                  onChangeText={setCode}
                  multiline
                  numberOfLines={10}
                  placeholder="Paste your code here..."
                  placeholderTextColor={colors.textMuted}
                />

                <TouchableOpacity
                  style={[styles.runButton, { backgroundColor: loading ? colors.surfaceAlt : selectedFeature.color }]}
                  onPress={runFeature}
                  disabled={loading || !code.trim()}
                >
                  {loading ? (
                    <ActivityIndicator color="#FFF" />
                  ) : (
                    <>
                      <Ionicons name="flash" size={20} color="#FFF" />
                      <Text style={styles.runButtonText}>Run {selectedFeature.name}</Text>
                    </>
                  )}
                </TouchableOpacity>

                {/* Result */}
                {result && (
                  <View style={[styles.resultContainer, { backgroundColor: colors.surfaceAlt }]}>
                    <Text style={[styles.resultTitle, { color: colors.text }]}>Analysis Result</Text>
                    <ScrollView style={styles.resultScroll} nestedScrollEnabled>
                      <Text style={[styles.resultText, { color: colors.text }]}>
                        {getResultText()}
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
  infoBanner: {
    padding: 12,
    borderRadius: 10,
    marginBottom: 16,
  },
  infoText: {
    fontSize: 14,
    fontWeight: '600',
    textAlign: 'center',
  },
  featureGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginBottom: 20,
  },
  featureCard: {
    width: '31%',
    padding: 12,
    borderRadius: 12,
    alignItems: 'center',
  },
  featureIcon: {
    width: 44,
    height: 44,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 8,
  },
  featureName: {
    fontSize: 12,
    fontWeight: '700',
    textAlign: 'center',
  },
  featureDesc: {
    fontSize: 10,
    textAlign: 'center',
    marginTop: 2,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 10,
  },
  capsList: {
    padding: 14,
    borderRadius: 12,
    gap: 8,
  },
  capsItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  capsText: {
    fontSize: 13,
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
  featureHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 16,
    borderRadius: 12,
    marginBottom: 16,
  },
  featureTitle: {
    fontSize: 18,
    fontWeight: '700',
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
    minHeight: 180,
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
    maxHeight: 300,
  },
  resultText: {
    fontSize: 13,
    lineHeight: 20,
  },
});
