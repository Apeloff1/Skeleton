/**
 * <SearchBar> — premium input with focus animation.
 */
import React, { useState } from 'react';
import {
  View, TextInput, Pressable, Platform, StyleSheet, ViewStyle, StyleProp,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import theme from '../../theme/tokens';

interface SearchBarProps {
  value: string;
  onChangeText: (v: string) => void;
  placeholder?: string;
  autoFocus?: boolean;
  style?: StyleProp<ViewStyle>;
  testID?: string;
}

export const SearchBar: React.FC<SearchBarProps> = ({
  value, onChangeText, placeholder = 'Search…', autoFocus, style, testID,
}) => {
  const [focused, setFocused] = useState(false);
  return (
    <View style={[
      styles.wrap,
      focused && { borderColor: theme.colors.primary, backgroundColor: theme.colors.surfaceAlt },
      style,
    ]}>
      <Ionicons name="search" size={16} color={focused ? theme.colors.primary : theme.colors.textMuted} />
      <TextInput
        style={styles.input}
        placeholder={placeholder}
        placeholderTextColor={theme.colors.textDim}
        value={value}
        onChangeText={onChangeText}
        autoFocus={autoFocus}
        autoCapitalize="none"
        autoCorrect={false}
        returnKeyType="search"
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
        testID={testID}
      />
      {value.length > 0 && (
        <Pressable onPress={() => onChangeText('')} hitSlop={theme.hitSlop.sm}>
          <Ionicons name="close-circle" size={18} color={theme.colors.textMuted} />
        </Pressable>
      )}
    </View>
  );
};

const styles = StyleSheet.create({
  wrap: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    backgroundColor: theme.colors.surface,
    borderRadius: theme.radii.md,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: Platform.OS === 'ios' ? 10 : 6,
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  input: {
    flex: 1, color: theme.colors.text,
    fontSize: 14, fontWeight: '500',
    padding: 0,
  },
});

export default SearchBar;
