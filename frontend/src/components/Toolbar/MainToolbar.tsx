// ============================================================================
// CODEDOCK - MAIN TOOLBAR COMPONENT
// ============================================================================

import React, { memo } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Pressable } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { ThemeColors } from '../../constants/themes';

interface ToolbarProps {
  colors: ThemeColors;
  onTemplates: () => void;
  onFiles: () => void;
  onSave: () => void;
  onAnalyze: () => void;
  onAIAssist: () => void;
  onDock: () => void;
  onBible: () => void;
  analysisScore?: number;
  isExecuting: boolean;
}

// eslint-disable-next-line react/display-name
export const MainToolbar: React.FC<ToolbarProps> = memo(({
  colors,
  onTemplates,
  onFiles,
  onSave,
  onAnalyze,
  onAIAssist,
  onDock,
  onBible,
  analysisScore,
  isExecuting,
}) => {
  const getScoreColor = (score: number) => {
    if (score >= 80) return colors.success;
    if (score >= 60) return colors.warning;
    return colors.error;
  };

  return (
    <View style={[styles.container, { backgroundColor: colors.surfaceAlt }]}>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.content}>
        {/* Templates */}
        <Pressable style={[styles.toolButton, { backgroundColor: colors.surface }]} onPress={onTemplates}>
          <Ionicons name="flash" size={15} color={colors.warning} />
          <Text style={[styles.toolButtonText, { color: colors.text }]}>Templates</Text>
        </Pressable>

        {/* Files */}
        <Pressable style={[styles.toolButton, { backgroundColor: colors.surface }]} onPress={onFiles}>
          <Ionicons name="folder" size={15} color={colors.accent} />
          <Text style={[styles.toolButtonText, { color: colors.text }]}>Files</Text>
        </Pressable>

        {/* Save */}
        <Pressable style={[styles.toolButton, { backgroundColor: colors.surface }]} onPress={onSave}>
          <Ionicons name="save" size={15} color={colors.success} />
          <Text style={[styles.toolButtonText, { color: colors.text }]}>Save</Text>
        </Pressable>

        {/* Analyze */}
        <Pressable style={[styles.toolButton, { backgroundColor: colors.surface }]} onPress={onAnalyze}>
          <Ionicons name="analytics" size={15} color={colors.secondary} />
          <Text style={[styles.toolButtonText, { color: colors.text }]}>Analyze</Text>
        </Pressable>
      </ScrollView>

      {/* AI Bar */}
      <View style={[styles.aiBar, { borderTopColor: colors.border }]}>
        <TouchableOpacity 
          style={[styles.aiButton, { backgroundColor: colors.primary + '15', borderColor: colors.primary }]} 
          onPress={onAIAssist}
          disabled={isExecuting}
        >
          <Ionicons name="sparkles" size={16} color={colors.primary} />
          <Text style={[styles.aiButtonText, { color: colors.primary }]}>AI Assist</Text>
          <View style={[styles.aiBadge, { backgroundColor: colors.primary }]}>
            <Text style={styles.aiBadgeText}>GPT-4o</Text>
          </View>
        </TouchableOpacity>

        {analysisScore !== undefined && (
          <View style={[styles.analysisChip, { backgroundColor: getScoreColor(analysisScore) + '20' }]}>
            <Text style={[styles.analysisChipText, { color: getScoreColor(analysisScore) }]}>
              Score: {analysisScore}
            </Text>
          </View>
        )}

        {/* Dock Button */}
        <TouchableOpacity style={[styles.dockChip, { backgroundColor: colors.surfaceAlt }]} onPress={onDock}>
          <Ionicons name="grid" size={14} color={colors.accent} />
          <Text style={[styles.dockChipText, { color: colors.accent }]}>Dock</Text>
        </TouchableOpacity>

        {/* Bible Button */}
        <TouchableOpacity style={[styles.dockChip, { backgroundColor: '#FFD70020' }]} onPress={onBible}>
          <Ionicons name="book" size={14} color="#FFD700" />
          <Text style={[styles.dockChipText, { color: '#FFD700' }]}>Bible</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
});

const styles = StyleSheet.create({
  container: {
    paddingTop: 8,
  },
  content: {
    paddingHorizontal: 12,
    gap: 8,
  },
  toolButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 8,
    gap: 6,
  },
  toolButtonText: {
    fontSize: 13,
    fontWeight: '500',
  },
  aiBar: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 10,
    borderTopWidth: 1,
    marginTop: 8,
  },
  aiButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
    gap: 8,
    borderWidth: 1,
  },
  aiButtonText: {
    fontSize: 14,
    fontWeight: '600',
  },
  aiBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 10,
  },
  aiBadgeText: {
    color: '#FFF',
    fontSize: 10,
    fontWeight: '700',
  },
  analysisChip: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  analysisChipText: {
    fontSize: 11,
    fontWeight: '700',
  },
  dockChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 12,
    gap: 4,
  },
  dockChipText: {
    fontSize: 12,
    fontWeight: '600',
  },
});

export default MainToolbar;
