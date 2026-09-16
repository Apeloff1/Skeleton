import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import {
  GAME_STYLE_CAPABILITIES,
  GameStyleId,
  getGameStyleCapability,
} from './gameStyleCapabilities';

interface GameStyleCapabilityPickerProps {
  value: string;
  onChange: (style: GameStyleId) => void;
  label?: string;
  colors: {
    text?: string;
    textSecondary?: string;
    primary?: string;
    border?: string;
    surface?: string;
    background?: string;
  };
  compact?: boolean;
}

export const GameStyleCapabilityPicker: React.FC<GameStyleCapabilityPickerProps> = ({
  value,
  onChange,
  label = 'Visual Style',
  colors,
  compact = false,
}) => {
  const selected = getGameStyleCapability(value);

  return (
    <View style={styles.container}>
      <Text style={[styles.label, { color: colors.text }]}>{label}</Text>
      <View style={styles.options}>
        {GAME_STYLE_CAPABILITIES.map(style => {
          const active = style.id === selected.id;
          return (
            <TouchableOpacity
              key={style.id}
              accessibilityRole="button"
              accessibilityState={{ selected: active }}
              accessibilityLabel={`${style.label}: ${style.summary}`}
              onPress={() => onChange(style.id)}
              style={[
                styles.option,
                {
                  borderColor: active ? colors.primary : colors.border,
                  backgroundColor: active
                    ? colors.primary
                    : (colors.surface ?? colors.background),
                },
              ]}
            >
              <Text
                style={[
                  styles.optionText,
                  { color: active ? '#ffffff' : colors.text },
                ]}
              >
                {style.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </View>

      {!compact && (
        <View
          style={[
            styles.detail,
            {
              borderColor: colors.border,
              backgroundColor: colors.surface ?? colors.background,
            },
          ]}
        >
          <Text style={[styles.summary, { color: colors.text }]}>{selected.summary}</Text>
          <Text style={[styles.direction, { color: colors.textSecondary ?? colors.text }]}>
            {selected.direction.rendering}
          </Text>
          <Text style={[styles.direction, { color: colors.textSecondary ?? colors.text }]}>
            {selected.direction.palette}
          </Text>
          <Text style={[styles.direction, { color: colors.textSecondary ?? colors.text }]}>
            {selected.direction.motion}
          </Text>
        </View>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  container: {
    gap: 8,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
  },
  options: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  option: {
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  optionText: {
    fontSize: 13,
    fontWeight: '600',
  },
  detail: {
    borderWidth: 1,
    borderRadius: 10,
    padding: 12,
    gap: 4,
  },
  summary: {
    fontSize: 13,
    fontWeight: '600',
    lineHeight: 18,
  },
  direction: {
    fontSize: 12,
    lineHeight: 17,
  },
});
