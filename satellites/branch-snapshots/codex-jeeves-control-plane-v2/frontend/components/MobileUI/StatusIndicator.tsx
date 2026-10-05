/**
 * StatusIndicator Component v11.4
 * Shows battery, network, and performance status
 */

import React, { memo } from 'react';
import {
  View,
  Text,
  StyleSheet,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

interface StatusIndicatorProps {
  batteryLevel: number;
  isCharging: boolean;
  isOnline: boolean;
  performanceMode: 'high' | 'balanced' | 'powersaver';
  colors: any;
  compact?: boolean;
}

export const StatusIndicator = memo(function StatusIndicator({
  batteryLevel,
  isCharging,
  isOnline,
  performanceMode,
  colors,
  compact = true,
}: StatusIndicatorProps) {
  const getBatteryIcon = (): keyof typeof Ionicons.glyphMap => {
    if (isCharging) return 'battery-charging';
    if (batteryLevel > 0.75) return 'battery-full';
    if (batteryLevel > 0.50) return 'battery-half';
    if (batteryLevel > 0.25) return 'battery-half';
    return 'battery-dead';
  };

  const getBatteryColor = () => {
    if (isCharging) return '#10B981';
    if (batteryLevel > 0.50) return '#10B981';
    if (batteryLevel > 0.25) return '#F59E0B';
    return '#EF4444';
  };

  const getPerformanceIcon = (): keyof typeof Ionicons.glyphMap => {
    switch (performanceMode) {
      case 'high': return 'rocket';
      case 'balanced': return 'speedometer';
      case 'powersaver': return 'leaf';
    }
  };

  const getPerformanceColor = () => {
    switch (performanceMode) {
      case 'high': return '#3B82F6';
      case 'balanced': return '#F59E0B';
      case 'powersaver': return '#10B981';
    }
  };

  if (compact) {
    return (
      <View style={styles.compactContainer}>
        {/* Network */}
        <Ionicons
          name={isOnline ? 'wifi' : 'wifi-outline'}
          size={14}
          color={isOnline ? '#10B981' : '#EF4444'}
        />
        {/* Battery */}
        <Ionicons
          name={getBatteryIcon()}
          size={14}
          color={getBatteryColor()}
        />
        {/* Performance Mode */}
        {performanceMode !== 'balanced' && (
          <Ionicons
            name={getPerformanceIcon()}
            size={14}
            color={getPerformanceColor()}
          />
        )}
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: colors.surfaceAlt }]}>
      {/* Network Status */}
      <View style={styles.item}>
        <Ionicons
          name={isOnline ? 'wifi' : 'wifi-outline'}
          size={16}
          color={isOnline ? '#10B981' : '#EF4444'}
        />
        <Text style={[styles.label, { color: colors.textMuted }]}>
          {isOnline ? 'Online' : 'Offline'}
        </Text>
      </View>

      {/* Battery Status */}
      <View style={styles.item}>
        <Ionicons
          name={getBatteryIcon()}
          size={16}
          color={getBatteryColor()}
        />
        <Text style={[styles.label, { color: colors.textMuted }]}>
          {Math.round(batteryLevel * 100)}%
        </Text>
      </View>

      {/* Performance Mode */}
      <View style={styles.item}>
        <Ionicons
          name={getPerformanceIcon()}
          size={16}
          color={getPerformanceColor()}
        />
        <Text style={[styles.label, { color: colors.textMuted }]}>
          {performanceMode === 'high' ? 'High' : 
           performanceMode === 'balanced' ? 'Balanced' : 'Saver'}
        </Text>
      </View>
    </View>
  );
});

const styles = StyleSheet.create({
  compactContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 8,
    borderRadius: 8,
    gap: 16,
  },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  label: {
    fontSize: 12,
    fontWeight: '500',
  },
});
