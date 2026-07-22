/**
 * MinimalToolbar Component v11.4
 * Clean, icon-based toolbar for mobile with tooltips
 */

import React, { memo, useState } from 'react';
import {
  View,
  StyleSheet,
  TouchableOpacity,
  Text,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as Haptics from 'expo-haptics';

interface ToolbarAction {
  id: string;
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  color?: string;
  onPress: () => void;
  disabled?: boolean;
}

interface MinimalToolbarProps {
  actions: ToolbarAction[];
  colors: any;
}

export const MinimalToolbar = memo(function MinimalToolbar({
  actions,
  colors,
}: MinimalToolbarProps) {
  const [activeTooltip, setActiveTooltip] = useState<string | null>(null);

  const handlePress = (action: ToolbarAction) => {
    if (action.disabled) return;
    
    if (Platform.OS === 'ios') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
    }
    action.onPress();
  };

  const handleLongPress = (action: ToolbarAction) => {
    setActiveTooltip(action.id);
    if (Platform.OS === 'ios') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium).catch(() => {});
    }
    setTimeout(() => setActiveTooltip(null), 1500);
  };

  return (
    <View style={[styles.container, { backgroundColor: colors.surfaceAlt }]}>
      {actions.map((action) => (
        <View key={action.id} style={styles.actionWrapper}>
          <TouchableOpacity
            style={[
              styles.actionButton,
              { backgroundColor: colors.surface },
              action.disabled && styles.disabled,
            ]}
            onPress={() => handlePress(action)}
            onLongPress={() => handleLongPress(action)}
            activeOpacity={0.7}
            disabled={action.disabled}
          >
            <Ionicons
              name={action.icon}
              size={22}
              color={action.disabled ? colors.textMuted : (action.color || colors.text)}
            />
          </TouchableOpacity>
          {activeTooltip === action.id && (
            <View style={[styles.tooltip, { backgroundColor: colors.text }]}>
              <Text style={[styles.tooltipText, { color: colors.background }]}>
                {action.label}
              </Text>
            </View>
          )}
        </View>
      ))}
    </View>
  );
});

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 10,
    gap: 10,
  },
  actionWrapper: {
    position: 'relative',
  },
  actionButton: {
    width: 56,
    height: 56,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
  },
  disabled: {
    opacity: 0.5,
  },
  tooltip: {
    position: 'absolute',
    bottom: '100%',
    left: '50%',
    transform: [{ translateX: -30 }],
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 6,
    marginBottom: 4,
  },
  tooltipText: {
    fontSize: 12,
    fontWeight: '600',
    textAlign: 'center',
  },
});
