// ============================================================================
// CODEDOCK QUANTUM NEXUS - Interactive Compiler Pipeline Visualizer
// Live zoomable clickable graph: AST → SSA → CFG → Optimization → Machine Code
// ============================================================================

import React, { useState, useCallback, useRef } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Dimensions, Modal,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Circle, Rect, Text as SvgText, G, Line, Defs, LinearGradient, Stop } from 'react-native-svg';

const { width: SCREEN_WIDTH } = Dimensions.get('window');

// ============================================================================
// TYPES
// ============================================================================
export interface PipelineStage {
  id: string;
  name: string;
  shortName: string;
  description: string;
  icon: string;
  color: string;
  status: 'pending' | 'running' | 'completed' | 'error';
  duration?: number;
  metrics?: Record<string, string | number>;
  details?: string[];
}

export interface PipelineNode {
  id: string;
  type: 'source' | 'ast' | 'ir' | 'ssa' | 'cfg' | 'opt' | 'regalloc' | 'codegen' | 'output';
  label: string;
  x: number;
  y: number;
  data?: any;
  expandable?: boolean;
  children?: PipelineNode[];
}

export interface PipelineEdge {
  from: string;
  to: string;
  label?: string;
  type: 'data' | 'control' | 'transform';
}

// ============================================================================
// PIPELINE STAGES
// ============================================================================
const DEFAULT_STAGES: PipelineStage[] = [
  {
    id: 'source',
    name: 'Source Code',
    shortName: 'SRC',
    description: 'Raw source code input',
    icon: 'document-text',
    color: '#6366F1',
    status: 'completed',
    metrics: { lines: 42, chars: 1280 },
  },
  {
    id: 'lexer',
    name: 'Lexical Analysis',
    shortName: 'LEX',
    description: 'Tokenization of source code',
    icon: 'list',
    color: '#8B5CF6',
    status: 'completed',
    duration: 2.3,
    metrics: { tokens: 156 },
  },
  {
    id: 'parser',
    name: 'Parsing',
    shortName: 'PARSE',
    description: 'Syntax analysis and AST generation',
    icon: 'git-branch',
    color: '#A855F7',
    status: 'completed',
    duration: 5.7,
    metrics: { nodes: 89 },
  },
  {
    id: 'ast',
    name: 'Abstract Syntax Tree',
    shortName: 'AST',
    description: 'Tree representation of code structure',
    icon: 'git-network',
    color: '#EC4899',
    status: 'completed',
    metrics: { depth: 12, functions: 3 },
    details: ['main()', 'helper()', 'process()'],
  },
  {
    id: 'semantic',
    name: 'Semantic Analysis',
    shortName: 'SEM',
    description: 'Type checking and symbol resolution',
    icon: 'checkmark-circle',
    color: '#F43F5E',
    status: 'completed',
    duration: 8.2,
    metrics: { types: 15, symbols: 42 },
  },
  {
    id: 'ir',
    name: 'IR Generation',
    shortName: 'IR',
    description: 'Intermediate Representation',
    icon: 'code-working',
    color: '#F59E0B',
    status: 'completed',
    duration: 12.4,
    metrics: { instructions: 234 },
  },
  {
    id: 'ssa',
    name: 'SSA Form',
    shortName: 'SSA',
    description: 'Static Single Assignment conversion',
    icon: 'analytics',
    color: '#EAB308',
    status: 'completed',
    duration: 4.1,
    metrics: { phi_nodes: 8, variables: 28 },
  },
  {
    id: 'cfg',
    name: 'Control Flow Graph',
    shortName: 'CFG',
    description: 'Basic blocks and control flow',
    icon: 'shuffle',
    color: '#84CC16',
    status: 'completed',
    metrics: { blocks: 12, edges: 18 },
  },
  {
    id: 'opt',
    name: 'Optimization Passes',
    shortName: 'OPT',
    description: 'IR transformations and optimizations',
    icon: 'flash',
    color: '#22C55E',
    status: 'running',
    duration: 45.8,
    metrics: { passes: 15, eliminated: 42 },
    details: ['Dead code elimination', 'Constant propagation', 'Loop unrolling', 'Inlining'],
  },
  {
    id: 'regalloc',
    name: 'Register Allocation',
    shortName: 'REG',
    description: 'Virtual to physical register mapping',
    icon: 'hardware-chip',
    color: '#10B981',
    status: 'pending',
    metrics: { registers: 16, spills: 3 },
  },
  {
    id: 'codegen',
    name: 'Code Generation',
    shortName: 'GEN',
    description: 'Machine code emission',
    icon: 'construct',
    color: '#2563EB',
    status: 'pending',
    metrics: { instructions: 512 },
  },
  {
    id: 'output',
    name: 'Binary Output',
    shortName: 'BIN',
    description: 'Final executable or object file',
    icon: 'cube',
    color: '#3B82F6',
    status: 'pending',
    metrics: { size: '12.4KB' },
  },
];

// ============================================================================
// PROPS
// ============================================================================
interface PipelineVisualizerProps {
  visible: boolean;
  onClose: () => void;
  colors: any;
  stages?: PipelineStage[];
  onStageClick?: (stage: PipelineStage) => void;
}

// ============================================================================
// MAIN COMPONENT
// ============================================================================
export function PipelineVisualizer({
  visible,
  onClose,
  colors,
  stages = DEFAULT_STAGES,
  onStageClick,
}: PipelineVisualizerProps) {
  const [selectedStage, setSelectedStage] = useState<PipelineStage | null>(null);
  const [viewMode, setViewMode] = useState<'linear' | 'graph' | 'detail'>('linear');
  const scrollRef = useRef<ScrollView>(null);
  
  const handleStagePress = useCallback((stage: PipelineStage) => {
    setSelectedStage(stage);
    onStageClick?.(stage);
  }, [onStageClick]);
  
  const getStatusColor = (status: PipelineStage['status']) => {
    switch (status) {
      case 'completed': return '#10B981';
      case 'running': return '#F59E0B';
      case 'error': return '#EF4444';
      default: return colors.textMuted;
    }
  };
  
  const getStatusIcon = (status: PipelineStage['status']) => {
    switch (status) {
      case 'completed': return 'checkmark-circle';
      case 'running': return 'sync';
      case 'error': return 'close-circle';
      default: return 'ellipse-outline';
    }
  };
  
  // Calculate pipeline progress
  const completedCount = stages.filter(s => s.status === 'completed').length;
  const progress = (completedCount / stages.length) * 100;
  
  // ============================================================================
  // RENDER LINEAR VIEW
  // ============================================================================
  const renderLinearView = () => (
    <ScrollView 
      ref={scrollRef}
      horizontal 
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.linearContainer}
    >
      {stages.map((stage, index) => (
        <React.Fragment key={stage.id}>
          <TouchableOpacity
            style={[
              styles.stageCard,
              { 
                backgroundColor: stage.status === 'running' ? stage.color + '20' : colors.surfaceAlt,
                borderColor: selectedStage?.id === stage.id ? stage.color : colors.border,
                borderWidth: selectedStage?.id === stage.id ? 2 : 1,
              }
            ]}
            onPress={() => handleStagePress(stage)}
          >
            {/* Status indicator */}
            <View style={[styles.statusDot, { backgroundColor: getStatusColor(stage.status) }]}>
              {stage.status === 'running' && (
                <Ionicons name="sync" size={10} color="#FFF" />
              )}
            </View>
            
            {/* Icon */}
            <View style={[styles.stageIcon, { backgroundColor: stage.color + '20' }]}>
              <Ionicons name={stage.icon as any} size={20} color={stage.color} />
            </View>
            
            {/* Label */}
            <Text style={[styles.stageName, { color: colors.text }]}>{stage.shortName}</Text>
            
            {/* Duration */}
            {stage.duration && (
              <Text style={[styles.stageDuration, { color: colors.textMuted }]}>
                {stage.duration}ms
              </Text>
            )}
          </TouchableOpacity>
          
          {/* Arrow connector */}
          {index < stages.length - 1 && (
            <View style={styles.connector}>
              <View style={[styles.connectorLine, { backgroundColor: 
                stages[index + 1].status !== 'pending' ? '#10B981' : colors.border 
              }]} />
              <Ionicons 
                name="chevron-forward" 
                size={16} 
                color={stages[index + 1].status !== 'pending' ? '#10B981' : colors.textMuted} 
              />
            </View>
          )}
        </React.Fragment>
      ))}
    </ScrollView>
  );
  
  // ============================================================================
  // RENDER GRAPH VIEW (SVG)
  // ============================================================================
  const renderGraphView = () => {
    const nodeWidth = 80;
    const nodeHeight = 60;
    const padding = 20;
    const rowHeight = 100;
    
    // Layout nodes in a grid with dependencies
    const layout = [
      { row: 0, nodes: ['source'] },
      { row: 1, nodes: ['lexer', 'parser'] },
      { row: 2, nodes: ['ast', 'semantic'] },
      { row: 3, nodes: ['ir'] },
      { row: 4, nodes: ['ssa', 'cfg'] },
      { row: 5, nodes: ['opt'] },
      { row: 6, nodes: ['regalloc', 'codegen'] },
      { row: 7, nodes: ['output'] },
    ];
    
    const getNodePosition = (stageId: string) => {
      for (let row = 0; row < layout.length; row++) {
        const idx = layout[row].nodes.indexOf(stageId);
        if (idx !== -1) {
          const nodesInRow = layout[row].nodes.length;
          const totalWidth = nodesInRow * nodeWidth + (nodesInRow - 1) * 40;
          const startX = (SCREEN_WIDTH - 40 - totalWidth) / 2;
          return {
            x: startX + idx * (nodeWidth + 40) + nodeWidth / 2,
            y: padding + row * rowHeight + nodeHeight / 2,
          };
        }
      }
      return { x: 0, y: 0 };
    };
    
    const edges = [
      { from: 'source', to: 'lexer' },
      { from: 'lexer', to: 'parser' },
      { from: 'parser', to: 'ast' },
      { from: 'ast', to: 'semantic' },
      { from: 'semantic', to: 'ir' },
      { from: 'ir', to: 'ssa' },
      { from: 'ir', to: 'cfg' },
      { from: 'ssa', to: 'opt' },
      { from: 'cfg', to: 'opt' },
      { from: 'opt', to: 'regalloc' },
      { from: 'regalloc', to: 'codegen' },
      { from: 'codegen', to: 'output' },
    ];
    
    const svgHeight = layout.length * rowHeight + padding * 2;
    
    return (
      <ScrollView>
        <Svg width={SCREEN_WIDTH - 40} height={svgHeight}>
          <Defs>
            <LinearGradient id="flowGrad" x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor="#6366F1" stopOpacity="1" />
              <Stop offset="1" stopColor="#8B5CF6" stopOpacity="1" />
            </LinearGradient>
          </Defs>
          
          {/* Edges */}
          {edges.map((edge, i) => {
            const fromPos = getNodePosition(edge.from);
            const toPos = getNodePosition(edge.to);
            const fromStage = stages.find(s => s.id === edge.from);
            const toStage = stages.find(s => s.id === edge.to);
            const isActive = fromStage?.status === 'completed' && toStage?.status !== 'pending';
            
            return (
              <Line
                key={i}
                x1={fromPos.x}
                y1={fromPos.y + nodeHeight / 2 - 5}
                x2={toPos.x}
                y2={toPos.y - nodeHeight / 2 + 5}
                stroke={isActive ? '#10B981' : colors.border}
                strokeWidth={2}
                strokeDasharray={isActive ? undefined : '4,4'}
              />
            );
          })}
          
          {/* Nodes */}
          {stages.map(stage => {
            const pos = getNodePosition(stage.id);
            const isSelected = selectedStage?.id === stage.id;
            
            return (
              <G key={stage.id} onPress={() => handleStagePress(stage)}>
                <Rect
                  x={pos.x - nodeWidth / 2}
                  y={pos.y - nodeHeight / 2}
                  width={nodeWidth}
                  height={nodeHeight}
                  rx={12}
                  fill={stage.status === 'running' ? stage.color + '30' : colors.surfaceAlt}
                  stroke={isSelected ? stage.color : colors.border}
                  strokeWidth={isSelected ? 2 : 1}
                />
                <Circle
                  cx={pos.x + nodeWidth / 2 - 10}
                  cy={pos.y - nodeHeight / 2 + 10}
                  r={6}
                  fill={getStatusColor(stage.status)}
                />
                <SvgText
                  x={pos.x}
                  y={pos.y + 5}
                  fontSize={12}
                  fontWeight="600"
                  fill={colors.text}
                  textAnchor="middle"
                >
                  {stage.shortName}
                </SvgText>
              </G>
            );
          })}
        </Svg>
      </ScrollView>
    );
  };
  
  // ============================================================================
  // RENDER DETAIL VIEW
  // ============================================================================
  const renderDetailView = () => (
    <ScrollView style={styles.detailContainer}>
      {stages.map(stage => (
        <TouchableOpacity
          key={stage.id}
          style={[
            styles.detailCard,
            { 
              backgroundColor: selectedStage?.id === stage.id ? stage.color + '15' : colors.surfaceAlt,
              borderColor: selectedStage?.id === stage.id ? stage.color : colors.border,
            }
          ]}
          onPress={() => handleStagePress(stage)}
        >
          <View style={styles.detailHeader}>
            <View style={[styles.detailIcon, { backgroundColor: stage.color + '20' }]}>
              <Ionicons name={stage.icon as any} size={24} color={stage.color} />
            </View>
            <View style={styles.detailInfo}>
              <Text style={[styles.detailName, { color: colors.text }]}>{stage.name}</Text>
              <Text style={[styles.detailDesc, { color: colors.textMuted }]}>{stage.description}</Text>
            </View>
            <View style={styles.detailStatus}>
              <Ionicons name={getStatusIcon(stage.status) as any} size={20} color={getStatusColor(stage.status)} />
              {stage.duration && (
                <Text style={[styles.detailDuration, { color: colors.textMuted }]}>{stage.duration}ms</Text>
              )}
            </View>
          </View>
          
          {stage.metrics && (
            <View style={styles.metricsRow}>
              {Object.entries(stage.metrics).map(([key, value]) => (
                <View key={key} style={[styles.metricBadge, { backgroundColor: stage.color + '15' }]}>
                  <Text style={[styles.metricKey, { color: colors.textMuted }]}>{key}</Text>
                  <Text style={[styles.metricValue, { color: stage.color }]}>{value}</Text>
                </View>
              ))}
            </View>
          )}
          
          {stage.details && (
            <View style={styles.detailsSection}>
              {stage.details.map((detail, i) => (
                <View key={i} style={styles.detailItem}>
                  <Ionicons name="chevron-forward" size={12} color={stage.color} />
                  <Text style={[styles.detailItemText, { color: colors.textSecondary }]}>{detail}</Text>
                </View>
              ))}
            </View>
          )}
        </TouchableOpacity>
      ))}
    </ScrollView>
  );
  
  // ============================================================================
  // RENDER
  // ============================================================================
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={[styles.overlay, { backgroundColor: 'rgba(0,0,0,0.5)' }]}>
        <View style={[styles.container, { backgroundColor: colors.background }]}>
          {/* Header */}
          <View style={[styles.header, { backgroundColor: colors.surface, borderBottomColor: colors.border }]}>
            <View style={styles.headerTitle}>
              <Ionicons name="git-network" size={22} color="#8B5CF6" />
              <Text style={[styles.headerText, { color: colors.text }]}>Pipeline Visualizer</Text>
            </View>
            <TouchableOpacity onPress={onClose}>
              <Ionicons name="close" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>
          
          {/* Progress Bar */}
          <View style={[styles.progressSection, { backgroundColor: colors.surfaceAlt }]}>
            <View style={styles.progressHeader}>
              <Text style={[styles.progressLabel, { color: colors.text }]}>Compilation Progress</Text>
              <Text style={[styles.progressPercent, { color: '#10B981' }]}>{Math.round(progress)}%</Text>
            </View>
            <View style={[styles.progressBar, { backgroundColor: colors.surface }]}>
              <View style={[styles.progressFill, { width: `${progress}%`, backgroundColor: '#10B981' }]} />
            </View>
            <Text style={[styles.progressStats, { color: colors.textMuted }]}>
              {completedCount} of {stages.length} stages complete
            </Text>
          </View>
          
          {/* View Mode Tabs */}
          <View style={[styles.viewTabs, { backgroundColor: colors.surface }]}>
            {(['linear', 'graph', 'detail'] as const).map(mode => (
              <TouchableOpacity
                key={mode}
                style={[
                  styles.viewTab,
                  { 
                    backgroundColor: viewMode === mode ? '#8B5CF620' : 'transparent',
                    borderBottomColor: viewMode === mode ? '#8B5CF6' : 'transparent',
                  }
                ]}
                onPress={() => setViewMode(mode)}
              >
                <Ionicons 
                  name={mode === 'linear' ? 'arrow-forward' : mode === 'graph' ? 'git-network' : 'list'}
                  size={16}
                  color={viewMode === mode ? '#8B5CF6' : colors.textMuted}
                />
                <Text style={[
                  styles.viewTabText, 
                  { color: viewMode === mode ? '#8B5CF6' : colors.textMuted }
                ]}>
                  {mode.charAt(0).toUpperCase() + mode.slice(1)}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
          
          {/* Content */}
          <View style={styles.content}>
            {viewMode === 'linear' && renderLinearView()}
            {viewMode === 'graph' && renderGraphView()}
            {viewMode === 'detail' && renderDetailView()}
          </View>
          
          {/* Selected Stage Info */}
          {selectedStage && (
            <View style={[styles.selectedInfo, { backgroundColor: colors.surface, borderTopColor: colors.border }]}>
              <View style={[styles.selectedIcon, { backgroundColor: selectedStage.color + '20' }]}>
                <Ionicons name={selectedStage.icon as any} size={24} color={selectedStage.color} />
              </View>
              <View style={styles.selectedContent}>
                <Text style={[styles.selectedName, { color: colors.text }]}>{selectedStage.name}</Text>
                <Text style={[styles.selectedDesc, { color: colors.textMuted }]}>{selectedStage.description}</Text>
              </View>
              <TouchableOpacity 
                style={[styles.expandButton, { backgroundColor: selectedStage.color }]}
                onPress={() => {/* Open detailed view */}}
              >
                <Text style={styles.expandButtonText}>Inspect</Text>
                <Ionicons name="arrow-forward" size={14} color="#FFF" />
              </TouchableOpacity>
            </View>
          )}
        </View>
      </View>
    </Modal>
  );
}

// ============================================================================
// STYLES
// ============================================================================
const styles = StyleSheet.create({
  overlay: { flex: 1, justifyContent: 'flex-end' },
  container: { height: '90%', borderTopLeftRadius: 24, borderTopRightRadius: 24 },
  
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 16, borderBottomWidth: 1 },
  headerTitle: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  headerText: { fontSize: 18, fontWeight: '700' },
  
  progressSection: { padding: 16 },
  progressHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  progressLabel: { fontSize: 14, fontWeight: '600' },
  progressPercent: { fontSize: 14, fontWeight: '700' },
  progressBar: { height: 8, borderRadius: 4, overflow: 'hidden' },
  progressFill: { height: '100%', borderRadius: 4 },
  progressStats: { fontSize: 12, marginTop: 6 },
  
  viewTabs: { flexDirection: 'row', padding: 8 },
  viewTab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', paddingVertical: 10, gap: 6, borderBottomWidth: 2 },
  viewTabText: { fontSize: 13, fontWeight: '600' },
  
  content: { flex: 1 },
  
  // Linear View
  linearContainer: { padding: 16, alignItems: 'center' },
  stageCard: { width: 70, height: 90, borderRadius: 12, padding: 8, alignItems: 'center', justifyContent: 'center' },
  statusDot: { position: 'absolute', top: 6, right: 6, width: 14, height: 14, borderRadius: 7, alignItems: 'center', justifyContent: 'center' },
  stageIcon: { width: 36, height: 36, borderRadius: 10, alignItems: 'center', justifyContent: 'center', marginBottom: 4 },
  stageName: { fontSize: 11, fontWeight: '700' },
  stageDuration: { fontSize: 9, marginTop: 2 },
  connector: { flexDirection: 'row', alignItems: 'center', marginHorizontal: 4 },
  connectorLine: { width: 20, height: 2 },
  
  // Detail View
  detailContainer: { padding: 16 },
  detailCard: { borderRadius: 12, padding: 14, marginBottom: 12, borderWidth: 1 },
  detailHeader: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  detailIcon: { width: 44, height: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  detailInfo: { flex: 1 },
  detailName: { fontSize: 15, fontWeight: '600' },
  detailDesc: { fontSize: 12, marginTop: 2 },
  detailStatus: { alignItems: 'center' },
  detailDuration: { fontSize: 10, marginTop: 2 },
  metricsRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  metricBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6 },
  metricKey: { fontSize: 10, textTransform: 'uppercase' },
  metricValue: { fontSize: 13, fontWeight: '700' },
  detailsSection: { marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: 'rgba(0,0,0,0.1)' },
  detailItem: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4 },
  detailItemText: { fontSize: 12 },
  
  // Selected Info
  selectedInfo: { flexDirection: 'row', alignItems: 'center', padding: 16, gap: 12, borderTopWidth: 1 },
  selectedIcon: { width: 48, height: 48, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  selectedContent: { flex: 1 },
  selectedName: { fontSize: 15, fontWeight: '600' },
  selectedDesc: { fontSize: 12, marginTop: 2 },
  expandButton: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 10, borderRadius: 8, gap: 6 },
  expandButtonText: { color: '#FFF', fontSize: 13, fontWeight: '600' },
});

export default PipelineVisualizer;
