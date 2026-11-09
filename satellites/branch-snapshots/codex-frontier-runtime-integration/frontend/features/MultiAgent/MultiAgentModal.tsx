/**
 * Multi-Agent Orchestration Modal v11.3.0
 * AI Agent Swarms for Complex Task Execution
 */

import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView, TextInput,
  Modal, ActivityIndicator, Dimensions,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Constants from 'expo-constants';

import { apiFetch } from '../../utils/apiController';
const { width: SCREEN_WIDTH } = Dimensions.get('window');
const API_URL = Constants.expoConfig?.extra?.apiUrl || process.env.EXPO_PUBLIC_BACKEND_URL || '';

interface MultiAgentModalProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  currentCode?: string;
  currentLanguage?: string;
}

interface AgentSystem {
  name: string;
  description: string;
  agent_count: number;
  flow: string;
}

export const MultiAgentModal: React.FC<MultiAgentModalProps> = ({
  visible, onClose, colors, currentCode, currentLanguage
}) => {
  const [systems, setSystems] = useState<Record<string, AgentSystem>>({});
  const [selectedSystem, setSelectedSystem] = useState<string | null>(null);
  const [task, setTask] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [info, setInfo] = useState<any>(null);

  useEffect(() => {
    if (visible) {
      fetchInfo();
    }
  }, [visible]);

  const fetchInfo = async () => {
    try {
      const res = await apiFetch(`${API_URL}/api/agents/info`);
      const data = await res.json();
      setInfo(data);
      setSystems(data.systems || {});
    } catch (e) {
      console.error('Failed to fetch agent info:', e);
    }
  };

  const runAgentSystem = async () => {
    if (!selectedSystem || !task.trim()) return;
    
    setLoading(true);
    setResult(null);
    
    try {
      const res = await apiFetch(`${API_URL}/api/agents/run/${selectedSystem}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          system: selectedSystem,
          task: task,
          code: currentCode || '',
          language: currentLanguage || 'python',
          max_iterations: 3
        })
      });
      const data = await res.json();
      setResult(data);
    } catch (e) {
      console.error('Agent system error:', e);
    } finally {
      setLoading(false);
    }
  };

  const systemIcons: Record<string, string> = {
    code_architect: 'construct',
    debug_swarm: 'bug',
    teaching_ensemble: 'school',
    asset_factory: 'cube',
    game_builder: 'game-controller'
  };

  const systemColors: Record<string, string> = {
    code_architect: '#3B82F6',
    debug_swarm: '#EF4444',
    teaching_ensemble: '#10B981',
    asset_factory: '#8B5CF6',
    game_builder: '#F59E0B'
  };

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={[styles.modal, { backgroundColor: colors.surface }]}>
          {/* Header */}
          <View style={[styles.header, { borderBottomColor: colors.border }]}>
            <View style={styles.headerTitle}>
              <Ionicons name="people" size={24} color="#8B5CF6" />
              <Text style={[styles.title, { color: colors.text }]}>Multi-Agent Systems</Text>
            </View>
            <TouchableOpacity onPress={onClose}>
              <Ionicons name="close" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
            {/* Info Banner */}
            {info && (
              <View style={[styles.infoBanner, { backgroundColor: '#8B5CF615' }]}>
                <Text style={[styles.infoText, { color: colors.text }]}>
                  {info.total_agents} Specialized Agents • {Object.keys(systems).length} Coordinated Systems
                </Text>
              </View>
            )}

            {/* System Selection */}
            <Text style={[styles.sectionTitle, { color: colors.text }]}>Select Agent System</Text>
            <View style={styles.systemGrid}>
              {Object.entries(systems).map(([key, system]) => (
                <TouchableOpacity
                  key={key}
                  style={[
                    styles.systemCard,
                    { 
                      backgroundColor: selectedSystem === key 
                        ? (systemColors[key] || '#8B5CF6') + '25' 
                        : colors.surfaceAlt,
                      borderColor: selectedSystem === key 
                        ? (systemColors[key] || '#8B5CF6') 
                        : colors.border
                    }
                  ]}
                  onPress={() => setSelectedSystem(key)}
                >
                  <View style={[styles.systemIcon, { backgroundColor: (systemColors[key] || '#8B5CF6') + '20' }]}>
                    <Ionicons 
                      name={(systemIcons[key] || 'flash') as any} 
                      size={24} 
                      color={systemColors[key] || '#8B5CF6'} 
                    />
                  </View>
                  <Text style={[styles.systemName, { color: colors.text }]}>{system.name}</Text>
                  <Text style={[styles.systemDesc, { color: colors.textMuted }]} numberOfLines={2}>
                    {system.description}
                  </Text>
                  <View style={styles.systemMeta}>
                    <Text style={[styles.metaText, { color: colors.textMuted }]}>
                      {system.agent_count} agents • {system.flow}
                    </Text>
                  </View>
                </TouchableOpacity>
              ))}
            </View>

            {/* Task Input */}
            {selectedSystem && (
              <View style={styles.taskSection}>
                <Text style={[styles.sectionTitle, { color: colors.text }]}>Describe Your Task</Text>
                <TextInput
                  style={[styles.taskInput, { backgroundColor: colors.surfaceAlt, color: colors.text, borderColor: colors.border }]}
                  placeholder="e.g., Build a REST API with user authentication..."
                  placeholderTextColor={colors.textMuted}
                  value={task}
                  onChangeText={setTask}
                  multiline
                  numberOfLines={4}
                />
                
                <TouchableOpacity
                  style={[styles.runButton, { backgroundColor: loading ? colors.surfaceAlt : '#8B5CF6' }]}
                  onPress={runAgentSystem}
                  disabled={loading || !task.trim()}
                >
                  {loading ? (
                    <ActivityIndicator color="#FFF" />
                  ) : (
                    <>
                      <Ionicons name="rocket" size={20} color="#FFF" />
                      <Text style={styles.runButtonText}>Run Agent System</Text>
                    </>
                  )}
                </TouchableOpacity>
              </View>
            )}

            {/* Results */}
            {result && (
              <View style={styles.resultSection}>
                <Text style={[styles.sectionTitle, { color: colors.text }]}>Agent Output</Text>
                
                {/* Agent Steps */}
                {result.agents?.map((agent: any, idx: number) => (
                  <View key={idx} style={[styles.agentStep, { backgroundColor: colors.surfaceAlt }]}>
                    <View style={styles.agentHeader}>
                      <Ionicons name="flash" size={16} color="#8B5CF6" />
                      <Text style={[styles.agentName, { color: colors.text }]}>{agent.name}</Text>
                    </View>
                    <Text style={[styles.agentRole, { color: colors.textMuted }]}>{agent.role}</Text>
                    <ScrollView style={styles.agentOutput} nestedScrollEnabled>
                      <Text style={[styles.outputText, { color: colors.text }]}>
                        {agent.output?.slice(0, 500) || 'Processing...'}
                        {agent.output?.length > 500 ? '...' : ''}
                      </Text>
                    </ScrollView>
                  </View>
                ))}

                {/* Final Output */}
                {result.final_output && (
                  <View style={[styles.finalOutput, { backgroundColor: '#10B98115', borderColor: '#10B981' }]}>
                    <Text style={[styles.finalTitle, { color: '#10B981' }]}>Final Result</Text>
                    <ScrollView style={styles.finalScroll} nestedScrollEnabled>
                      <Text style={[styles.finalText, { color: colors.text }]}>
                        {result.final_output}
                      </Text>
                    </ScrollView>
                  </View>
                )}
              </View>
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
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 12,
  },
  systemGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    marginBottom: 20,
  },
  systemCard: {
    width: (SCREEN_WIDTH - 56) / 2,
    padding: 14,
    borderRadius: 12,
    borderWidth: 2,
  },
  systemIcon: {
    width: 44,
    height: 44,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 10,
  },
  systemName: {
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 4,
  },
  systemDesc: {
    fontSize: 12,
    lineHeight: 16,
    marginBottom: 8,
  },
  systemMeta: {
    marginTop: 'auto',
  },
  metaText: {
    fontSize: 11,
  },
  taskSection: {
    marginBottom: 20,
  },
  taskInput: {
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    fontSize: 14,
    minHeight: 100,
    textAlignVertical: 'top',
    marginBottom: 12,
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
  resultSection: {
    marginBottom: 20,
  },
  agentStep: {
    padding: 14,
    borderRadius: 12,
    marginBottom: 10,
  },
  agentHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 4,
  },
  agentName: {
    fontSize: 14,
    fontWeight: '700',
  },
  agentRole: {
    fontSize: 12,
    marginBottom: 8,
  },
  agentOutput: {
    maxHeight: 150,
  },
  outputText: {
    fontSize: 13,
    lineHeight: 20,
  },
  finalOutput: {
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    marginTop: 10,
  },
  finalTitle: {
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 8,
  },
  finalScroll: {
    maxHeight: 200,
  },
  finalText: {
    fontSize: 14,
    lineHeight: 22,
  },
});
