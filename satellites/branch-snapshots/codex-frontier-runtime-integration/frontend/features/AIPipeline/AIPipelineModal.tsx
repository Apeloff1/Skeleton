/**
 * AI Pipeline Modal v11.0.0
 * Text-to-Code Generation & Code Analysis Interface
 */

import React, { useState, useCallback } from 'react';
import { API_BASE } from '../../utils/apiBase';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput,
  Modal, ActivityIndicator, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

import { apiFetch } from '../../utils/apiController';
import { toast } from '../../components/Toast';
const API_URL = API_BASE;

interface AIPipelineModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  onCodeGenerated?: (code: string, language: string) => void;
}

type TabType = 'generate' | 'analyze' | 'providers';

interface Provider {
  name: string;
  models: string[];
  capabilities: string[];
  status: string;
}

export const AIPipelineModal: React.FC<AIPipelineModalProps> = ({
  visible, onClose, colors, onCodeGenerated
}) => {
  const [activeTab, setActiveTab] = useState<TabType>('generate');
  const [isLoading, setIsLoading] = useState(false);
  
  // Generate state
  const [description, setDescription] = useState('');
  const [targetLanguage, setTargetLanguage] = useState('python');
  const [generatedCode, setGeneratedCode] = useState('');
  
  // Analyze state
  const [codeToAnalyze, setCodeToAnalyze] = useState('');
  const [analysisType, setAnalysisType] = useState('explain');
  const [analysisResult, setAnalysisResult] = useState('');
  
  // Providers state
  const [providers, setProviders] = useState<Provider[]>([]);
  const [pipelineInfo, setPipelineInfo] = useState<any>(null);

  const languages = [
    'python', 'javascript', 'typescript', 'java', 'cpp', 'c', 'rust', 'go', 'swift', 'kotlin'
  ];

  const analysisTypes = [
    { key: 'explain', label: '📖 Explain', desc: 'Explain what the code does' },
    { key: 'optimize', label: '⚡ Optimize', desc: 'Suggest optimizations' },
    { key: 'debug', label: '🐛 Debug', desc: 'Find potential bugs' },
    { key: 'document', label: '📝 Document', desc: 'Generate documentation' },
    { key: 'refactor', label: '🔧 Refactor', desc: 'Suggest refactoring' },
    { key: 'test', label: '🧪 Test', desc: 'Generate test cases' },
  ];

  const generateCode = useCallback(async () => {
    if (!description.trim()) {
      toast.error('Please describe what you want to generate');
      return;
    }

    setIsLoading(true);
    setGeneratedCode('');

    try {
      const response = await apiFetch(`${API_URL}/api/pipeline/text-to-code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          description,
          language: targetLanguage,
          style: 'clean',
          include_comments: true,
        }),
      });

      const data = await response.json();
      if (data.generated_code) {
        setGeneratedCode(data.generated_code);
      } else if (data.result?.code) {
        setGeneratedCode(data.result.code);
      } else {
        setGeneratedCode('// No code generated. Try rephrasing your description.');
      }
    } catch (error: any) {
      toast.error(`Failed to generate code: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  }, [description, targetLanguage]);

  const analyzeCode = useCallback(async () => {
    if (!codeToAnalyze.trim()) {
      toast.error('Please enter code to analyze');
      return;
    }

    setIsLoading(true);
    setAnalysisResult('');

    try {
      const response = await apiFetch(`${API_URL}/api/pipeline/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: codeToAnalyze,
          analysis_type: analysisType,
          language: targetLanguage,
        }),
      });

      const data = await response.json();
      if (data.analysis) {
        setAnalysisResult(data.analysis);
      } else if (data.result?.analysis) {
        setAnalysisResult(data.result.analysis);
      } else {
        setAnalysisResult('Analysis complete. No specific findings.');
      }
    } catch (error: any) {
      toast.error(`Failed to analyze code: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  }, [codeToAnalyze, analysisType, targetLanguage]);

  const loadProviders = useCallback(async () => {
    setIsLoading(true);
    try {
      const [providersRes, infoRes] = await Promise.all([
        apiFetch(`${API_URL}/api/pipeline/providers`),
        apiFetch(`${API_URL}/api/pipeline/info`),
      ]);
      
      const providersData = await providersRes.json();
      const infoData = await infoRes.json();
      
      setProviders(providersData.providers || []);
      setPipelineInfo(infoData);
    } catch (error: any) {
      toast.error(`Failed to load providers: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const useGeneratedCode = () => {
    if (generatedCode && onCodeGenerated) {
      onCodeGenerated(generatedCode, targetLanguage);
      onClose();
    }
  };

  const renderTabs = () => (
    <View style={[styles.tabs, { borderBottomColor: colors.border }]}>
      {[
        { key: 'generate', label: '✨ Generate', icon: 'create-outline' },
        { key: 'analyze', label: '🔍 Analyze', icon: 'analytics-outline' },
        { key: 'providers', label: '🤖 Providers', icon: 'hardware-chip-outline' },
      ].map((tab) => (
        <TouchableOpacity
          key={tab.key}
          style={[
            styles.tab,
            activeTab === tab.key && { borderBottomColor: colors.primary, borderBottomWidth: 2 }
          ]}
          onPress={() => {
            setActiveTab(tab.key as TabType);
            if (tab.key === 'providers' && providers.length === 0) {
              loadProviders();
            }
          }}
        >
          <Text style={[styles.tabText, { color: activeTab === tab.key ? colors.primary : colors.textSecondary }]}>
            {tab.label}
          </Text>
        </TouchableOpacity>
      ))}
    </View>
  );

  const renderGenerateTab = () => (
    <ScrollView style={styles.tabContent} showsVerticalScrollIndicator={false}>
      <Text style={[styles.label, { color: colors.text }]}>🎯 Describe what you want to create:</Text>
      <TextInput
        style={[styles.textArea, { backgroundColor: colors.codeBackground, color: colors.text, borderColor: colors.border }]}
        placeholder="E.g., Create a function that sorts an array using quicksort algorithm with detailed comments..."
        placeholderTextColor={colors.textSecondary}
        value={description}
        onChangeText={setDescription}
        multiline
        numberOfLines={4}
      />

      <Text style={[styles.label, { color: colors.text, marginTop: 16 }]}>🔤 Target Language:</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.languageScroll}>
        {languages.map((lang) => (
          <TouchableOpacity
            key={lang}
            style={[
              styles.langChip,
              { backgroundColor: targetLanguage === lang ? colors.primary : colors.cardBackground, borderColor: colors.border }
            ]}
            onPress={() => setTargetLanguage(lang)}
          >
            <Text style={[styles.langChipText, { color: targetLanguage === lang ? '#FFF' : colors.text }]}>
              {lang.charAt(0).toUpperCase() + lang.slice(1)}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: colors.primary }]}
        onPress={generateCode}
        disabled={isLoading}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="sparkles" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Generate Code with AI</Text>
          </>
        )}
      </TouchableOpacity>

      {generatedCode ? (
        <View style={[styles.resultBox, { backgroundColor: colors.codeBackground, borderColor: colors.border }]}>
          <View style={styles.resultHeader}>
            <Text style={[styles.resultTitle, { color: colors.text }]}>✅ Generated Code:</Text>
            <TouchableOpacity
              style={[styles.useCodeBtn, { backgroundColor: colors.success }]}
              onPress={useGeneratedCode}
            >
              <Ionicons name="code-slash" size={16} color="#FFF" />
              <Text style={styles.useCodeBtnText}>Use Code</Text>
            </TouchableOpacity>
          </View>
          <ScrollView style={styles.codeScroll} nestedScrollEnabled>
            <Text style={[styles.codeText, { color: colors.text }]}>{generatedCode}</Text>
          </ScrollView>
        </View>
      ) : null}
    </ScrollView>
  );

  const renderAnalyzeTab = () => (
    <ScrollView style={styles.tabContent} showsVerticalScrollIndicator={false}>
      <Text style={[styles.label, { color: colors.text }]}>📝 Paste code to analyze:</Text>
      <TextInput
        style={[styles.textArea, { backgroundColor: colors.codeBackground, color: colors.text, borderColor: colors.border, minHeight: 120 }]}
        placeholder="Paste your code here..."
        placeholderTextColor={colors.textSecondary}
        value={codeToAnalyze}
        onChangeText={setCodeToAnalyze}
        multiline
      />

      <Text style={[styles.label, { color: colors.text, marginTop: 16 }]}>🔍 Analysis Type:</Text>
      <View style={styles.analysisGrid}>
        {analysisTypes.map((type) => (
          <TouchableOpacity
            key={type.key}
            style={[
              styles.analysisChip,
              { backgroundColor: analysisType === type.key ? colors.primary : colors.cardBackground, borderColor: colors.border }
            ]}
            onPress={() => setAnalysisType(type.key)}
          >
            <Text style={[styles.analysisChipLabel, { color: analysisType === type.key ? '#FFF' : colors.text }]}>
              {type.label}
            </Text>
            <Text style={[styles.analysisChipDesc, { color: analysisType === type.key ? 'rgba(255,255,255,0.8)' : colors.textSecondary }]}>
              {type.desc}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      <TouchableOpacity
        style={[styles.generateBtn, { backgroundColor: colors.primary }]}
        onPress={analyzeCode}
        disabled={isLoading}
      >
        {isLoading ? (
          <ActivityIndicator color="#FFF" />
        ) : (
          <>
            <Ionicons name="search" size={20} color="#FFF" />
            <Text style={styles.generateBtnText}>Analyze Code</Text>
          </>
        )}
      </TouchableOpacity>

      {analysisResult ? (
        <View style={[styles.resultBox, { backgroundColor: colors.codeBackground, borderColor: colors.border }]}>
          <Text style={[styles.resultTitle, { color: colors.text }]}>📊 Analysis Result:</Text>
          <ScrollView style={styles.codeScroll} nestedScrollEnabled>
            <Text style={[styles.analysisText, { color: colors.text }]}>{analysisResult}</Text>
          </ScrollView>
        </View>
      ) : null}
    </ScrollView>
  );

  const renderProvidersTab = () => (
    <ScrollView style={styles.tabContent} showsVerticalScrollIndicator={false}>
      {isLoading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={[styles.loadingText, { color: colors.textSecondary }]}>Loading providers...</Text>
        </View>
      ) : (
        <>
          {pipelineInfo && (
            <View style={[styles.infoCard, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}>
              <Text style={[styles.infoTitle, { color: colors.text }]}>🚀 Pipeline System v{pipelineInfo.version}</Text>
              <Text style={[styles.infoText, { color: colors.textSecondary }]}>
                {pipelineInfo.total_providers} Providers • {pipelineInfo.total_pipeline_types} Pipeline Types
              </Text>
              <View style={styles.pipelineTypes}>
                {pipelineInfo.pipeline_types?.slice(0, 6).map((type: string, i: number) => (
                  <View key={i} style={[styles.pipelineChip, { backgroundColor: colors.primary + '20' }]}>
                    <Text style={[styles.pipelineChipText, { color: colors.primary }]}>{type}</Text>
                  </View>
                ))}
              </View>
            </View>
          )}

          <Text style={[styles.sectionTitle, { color: colors.text }]}>🤖 AI Providers</Text>
          {providers.map((provider, index) => (
            <View key={index} style={[styles.providerCard, { backgroundColor: colors.cardBackground, borderColor: colors.border }]}>
              <View style={styles.providerHeader}>
                <Text style={[styles.providerName, { color: colors.text }]}>{provider.name}</Text>
                <View style={[styles.statusBadge, { backgroundColor: provider.status === 'active' ? '#10B981' : '#EF4444' }]}>
                  <Text style={styles.statusText}>{provider.status}</Text>
                </View>
              </View>
              <Text style={[styles.providerLabel, { color: colors.textSecondary }]}>Models:</Text>
              <View style={styles.modelList}>
                {provider.models?.map((model, i) => (
                  <Text key={i} style={[styles.modelText, { color: colors.text }]}>• {model}</Text>
                ))}
              </View>
              <Text style={[styles.providerLabel, { color: colors.textSecondary, marginTop: 8 }]}>Capabilities:</Text>
              <View style={styles.capsList}>
                {provider.capabilities?.map((cap, i) => (
                  <View key={i} style={[styles.capChip, { backgroundColor: colors.primary + '20' }]}>
                    <Text style={[styles.capText, { color: colors.primary }]}>{cap}</Text>
                  </View>
                ))}
              </View>
            </View>
          ))}
        </>
      )}
    </ScrollView>
  );

  return (
    <Modal visible={visible} animationType="slide" transparent={false}>
      <View style={[styles.container, { backgroundColor: colors.background }]}>
        <View style={[styles.header, { borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
            <Ionicons name="close" size={24} color={colors.text} />
          </TouchableOpacity>
          <Text style={[styles.title, { color: colors.text }]}>🧠 AI Pipeline</Text>
          <View style={styles.placeholder} />
        </View>

        {renderTabs()}
        
        {activeTab === 'generate' && renderGenerateTab()}
        {activeTab === 'analyze' && renderAnalyzeTab()}
        {activeTab === 'providers' && renderProvidersTab()}
      </View>
    </Modal>
  );
};

const styles = StyleSheet.create({
  container: { flex: 1, paddingTop: Platform.OS === 'ios' ? 50 : 30 },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingBottom: 12, borderBottomWidth: 1 },
  closeBtn: { padding: 8 },
  title: { fontSize: 20, fontWeight: 'bold' },
  placeholder: { width: 40 },
  tabs: { flexDirection: 'row', borderBottomWidth: 1 },
  tab: { flex: 1, paddingVertical: 12, alignItems: 'center' },
  tabText: { fontSize: 14, fontWeight: '600' },
  tabContent: { flex: 1, padding: 16 },
  label: { fontSize: 14, fontWeight: '600', marginBottom: 8 },
  textArea: { borderWidth: 1, borderRadius: 8, padding: 12, fontSize: 14, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', minHeight: 100, textAlignVertical: 'top' },
  languageScroll: { marginBottom: 16 },
  langChip: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20, marginRight: 8, borderWidth: 1 },
  langChipText: { fontSize: 13, fontWeight: '500' },
  generateBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: 14, borderRadius: 8, gap: 8, marginTop: 8 },
  generateBtnText: { color: '#FFF', fontSize: 16, fontWeight: '600' },
  resultBox: { marginTop: 16, borderRadius: 8, borderWidth: 1, padding: 12 },
  resultHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  resultTitle: { fontSize: 14, fontWeight: '600' },
  useCodeBtn: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 6, gap: 4 },
  useCodeBtnText: { color: '#FFF', fontSize: 12, fontWeight: '600' },
  codeScroll: { maxHeight: 200 },
  codeText: { fontSize: 12, fontFamily: Platform.OS === 'ios' ? 'Menlo' : 'monospace', lineHeight: 18 },
  analysisGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 16 },
  analysisChip: { width: '48%', padding: 12, borderRadius: 8, borderWidth: 1 },
  analysisChipLabel: { fontSize: 14, fontWeight: '600' },
  analysisChipDesc: { fontSize: 11, marginTop: 2 },
  analysisText: { fontSize: 13, lineHeight: 20 },
  loadingContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingTop: 60 },
  loadingText: { marginTop: 12, fontSize: 14 },
  infoCard: { padding: 16, borderRadius: 12, borderWidth: 1, marginBottom: 16 },
  infoTitle: { fontSize: 18, fontWeight: 'bold', marginBottom: 4 },
  infoText: { fontSize: 13 },
  pipelineTypes: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 12 },
  pipelineChip: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  pipelineChipText: { fontSize: 11, fontWeight: '500' },
  sectionTitle: { fontSize: 16, fontWeight: 'bold', marginBottom: 12 },
  providerCard: { padding: 16, borderRadius: 12, borderWidth: 1, marginBottom: 12 },
  providerHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  providerName: { fontSize: 16, fontWeight: 'bold' },
  statusBadge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 },
  statusText: { color: '#FFF', fontSize: 10, fontWeight: '600' },
  providerLabel: { fontSize: 12, fontWeight: '600', marginBottom: 4 },
  modelList: { marginLeft: 8 },
  modelText: { fontSize: 12, marginBottom: 2 },
  capsList: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
  capChip: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10 },
  capText: { fontSize: 10, fontWeight: '500' },
});

export default AIPipelineModal;
