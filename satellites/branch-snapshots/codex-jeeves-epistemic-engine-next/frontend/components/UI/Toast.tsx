// ============================================================================
// CODEDOCK - TOAST NOTIFICATION COMPONENT
// ============================================================================

import { NATIVE_DRIVER } from '../../src/utils/platformStyles';
import React, { useEffect, useRef } from 'react';
import { View, Text, StyleSheet, Animated, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { ThemeColors } from '../../constants/themes';

interface ToastProps {
  message: string;
  type: 'success' | 'error' | 'warning' | 'info';
  visible: boolean;
  onDismiss: () => void;
  duration?: number;
  colors: ThemeColors;
}

export const Toast: React.FC<ToastProps> = ({
  message,
  type,
  visible,
  onDismiss,
  duration = 3000,
  colors,
}) => {
  const translateY = useRef(new Animated.Value(-100)).current;
  const opacity = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (visible) {
      Animated.parallel([
        Animated.spring(translateY, { toValue: 0, useNativeDriver: NATIVE_DRIVER, tension: 100, friction: 10 }),
        Animated.timing(opacity, { toValue: 1, duration: 200, useNativeDriver: NATIVE_DRIVER }),
      ]).start();

      const timer = setTimeout(() => {
        dismiss();
      }, duration);

      return () => clearTimeout(timer);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  const dismiss = () => {
    Animated.parallel([
      Animated.timing(translateY, { toValue: -100, duration: 200, useNativeDriver: NATIVE_DRIVER }),
      Animated.timing(opacity, { toValue: 0, duration: 200, useNativeDriver: NATIVE_DRIVER }),
    ]).start(() => onDismiss());
  };

  const getIcon = () => {
    switch (type) {
      case 'success': return 'checkmark-circle';
      case 'error': return 'alert-circle';
      case 'warning': return 'warning';
      case 'info': return 'information-circle';
    }
  };

  const getColor = () => {
    switch (type) {
      case 'success': return colors.success;
      case 'error': return colors.error;
      case 'warning': return colors.warning;
      case 'info': return colors.primary;
    }
  };

  if (!visible) return null;

  return (
    <Animated.View
      style={[
        styles.container,
        {
          backgroundColor: colors.surface,
          borderColor: getColor(),
          transform: [{ translateY }],
          opacity,
        },
      ]}
    >
      <View style={[styles.iconContainer, { backgroundColor: getColor() + '20' }]}>
        <Ionicons name={getIcon()} size={20} color={getColor()} />
      </View>
      <Text style={[styles.message, { color: colors.text }]} numberOfLines={2}>
        {message}
      </Text>
      <TouchableOpacity onPress={dismiss} style={styles.closeButton}>
        <Ionicons name="close" size={18} color={colors.textMuted} />
      </TouchableOpacity>
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  container: {
    position: 'absolute',
    top: 50,
    left: 16,
    right: 16,
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderRadius: 12,
    borderWidth: 1,
    elevation: 8,
    zIndex: 1000,
  },
  iconContainer: {
    width: 32,
    height: 32,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: 12,
  },
  message: {
    flex: 1,
    fontSize: 14,
    fontWeight: '500',
  },
  closeButton: {
    padding: 4,
    marginLeft: 8,
  },
});

export default Toast;
