import React from 'react';
import {
  View,
  Text,
  TextInput,
  Pressable,
  StyleSheet,
  ViewStyle,
  TextStyle,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';

export function Screen({ children, style, ...props }: any) {
  return <View {...props} style={[styles.screen, style]}>{children}</View>;
}

export function AppHeader({ title, subtitle, onBack, right, style }: any) {
  return (
    <View style={[styles.header, style]}>
      <View style={styles.headerSide}>
        {onBack ? (
          <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={onBack} style={styles.iconButton}>
            <Ionicons name="chevron-back" size={22} color="#E5E7EB" />
          </Pressable>
        ) : null}
      </View>
      <View style={styles.headerCenter}>
        <Text numberOfLines={1} style={styles.headerTitle}>{title}</Text>
        {subtitle ? <Text numberOfLines={1} style={styles.headerSubtitle}>{subtitle}</Text> : null}
      </View>
      <View style={[styles.headerSide, styles.headerRight]}>{right}</View>
    </View>
  );
}

export function SearchBar({ value, onChangeText, placeholder = 'Search', onClear, style, inputStyle, ...props }: any) {
  const clear = () => {
    onChangeText?.('');
    onClear?.();
  };
  return (
    <View style={[styles.search, style]}>
      <Ionicons name="search" size={18} color="#9CA3AF" />
      <TextInput
        {...props}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor="#6B7280"
        style={[styles.searchInput, inputStyle]}
      />
      {value ? (
        <Pressable accessibilityRole="button" accessibilityLabel="Clear search" onPress={clear} hitSlop={8}>
          <Ionicons name="close-circle" size={18} color="#9CA3AF" />
        </Pressable>
      ) : null}
    </View>
  );
}

export function Chip({ label, children, selected, active, onPress, icon, color, style, textStyle, disabled }: any) {
  const isSelected = selected ?? active ?? false;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: !!isSelected, disabled: !!disabled }}
      disabled={disabled}
      onPress={onPress}
      style={[styles.chip, isSelected && styles.chipSelected, disabled && styles.disabled, style]}
    >
      {icon ? <Ionicons name={icon as any} size={14} color={color || (isSelected ? '#FFFFFF' : '#A78BFA')} /> : null}
      <Text style={[styles.chipText, isSelected && styles.chipTextSelected, color ? { color } : null, textStyle]}>
        {label ?? children}
      </Text>
    </Pressable>
  );
}

export function SectionHeader({ title, subtitle, action, actionLabel, onAction, right, style }: any) {
  return (
    <View style={[styles.sectionHeader, style]}>
      <View style={styles.sectionHeaderText}>
        <Text style={styles.sectionTitle}>{title}</Text>
        {subtitle ? <Text style={styles.sectionSubtitle}>{subtitle}</Text> : null}
      </View>
      {right ?? action ?? (actionLabel ? (
        <Pressable onPress={onAction}><Text style={styles.actionText}>{actionLabel}</Text></Pressable>
      ) : null)}
    </View>
  );
}

export function EmptyState({ icon = 'file-tray-outline', title = 'Nothing here yet', message, subtitle, actionLabel, onAction, style }: any) {
  return (
    <View style={[styles.empty, style]}>
      <Ionicons name={icon as any} size={34} color="#8B5CF6" />
      <Text style={styles.emptyTitle}>{title}</Text>
      {(message || subtitle) ? <Text style={styles.emptyMessage}>{message || subtitle}</Text> : null}
      {actionLabel && onAction ? (
        <Pressable onPress={onAction} style={styles.primaryButton}>
          <Text style={styles.primaryButtonText}>{actionLabel}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

export function FeatureCard({ title, subtitle, description, icon = 'apps', color = '#8B5CF6', onPress, badge, right, style }: any) {
  return (
    <Pressable onPress={onPress} style={[styles.featureCard, style]}>
      <View style={[styles.featureIcon, { backgroundColor: `${color}22` }]}>
        <Ionicons name={icon as any} size={20} color={color} />
      </View>
      <View style={styles.featureBody}>
        <View style={styles.featureTitleRow}>
          <Text style={styles.featureTitle}>{title}</Text>
          {badge ? <Text style={styles.badge}>{badge}</Text> : null}
        </View>
        {(subtitle || description) ? <Text style={styles.featureSubtitle}>{subtitle || description}</Text> : null}
      </View>
      {right ?? <Ionicons name="chevron-forward" size={18} color="#6B7280" />}
    </Pressable>
  );
}

export function Button({ title, label, children, onPress, disabled, icon, variant, style, textStyle }: any) {
  const text = title ?? label ?? children;
  const secondary = variant === 'secondary' || variant === 'ghost';
  return (
    <Pressable onPress={onPress} disabled={disabled} style={[styles.button, secondary && styles.buttonSecondary, disabled && styles.disabled, style]}>
      {icon ? <Ionicons name={icon as any} size={16} color={secondary ? '#C4B5FD' : '#FFFFFF'} /> : null}
      <Text style={[styles.buttonText, secondary && styles.buttonTextSecondary, textStyle]}>{text}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#0B1020' },
  header: { minHeight: 64, paddingHorizontal: 12, paddingVertical: 10, flexDirection: 'row', alignItems: 'center', borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#263047' },
  headerSide: { width: 56, minHeight: 40, justifyContent: 'center' },
  headerRight: { alignItems: 'flex-end' },
  headerCenter: { flex: 1, alignItems: 'center', paddingHorizontal: 8 },
  headerTitle: { color: '#F9FAFB', fontSize: 18, fontWeight: '700' } as TextStyle,
  headerSubtitle: { color: '#9CA3AF', fontSize: 12, marginTop: 2 } as TextStyle,
  iconButton: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center', borderRadius: 20 },
  search: { minHeight: 44, paddingHorizontal: 12, flexDirection: 'row', alignItems: 'center', gap: 8, borderWidth: 1, borderColor: '#303A52', backgroundColor: '#121A2E', borderRadius: 12 },
  searchInput: { flex: 1, minHeight: 42, color: '#F9FAFB', fontSize: 15, paddingVertical: 8 } as TextStyle,
  chip: { minHeight: 34, paddingHorizontal: 12, borderRadius: 18, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, borderWidth: 1, borderColor: '#374151', backgroundColor: '#141C30' },
  chipSelected: { borderColor: '#8B5CF6', backgroundColor: '#7C3AED' },
  chipText: { color: '#D1D5DB', fontSize: 13, fontWeight: '600' } as TextStyle,
  chipTextSelected: { color: '#FFFFFF' } as TextStyle,
  sectionHeader: { minHeight: 40, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 18, marginBottom: 8 },
  sectionHeaderText: { flex: 1, paddingRight: 12 },
  sectionTitle: { color: '#F9FAFB', fontSize: 17, fontWeight: '700' } as TextStyle,
  sectionSubtitle: { color: '#9CA3AF', fontSize: 12, marginTop: 2 } as TextStyle,
  actionText: { color: '#A78BFA', fontSize: 13, fontWeight: '600' } as TextStyle,
  empty: { paddingVertical: 32, paddingHorizontal: 20, alignItems: 'center', justifyContent: 'center' },
  emptyTitle: { color: '#F9FAFB', fontSize: 17, fontWeight: '700', marginTop: 12, textAlign: 'center' } as TextStyle,
  emptyMessage: { color: '#9CA3AF', fontSize: 13, lineHeight: 19, marginTop: 6, textAlign: 'center', maxWidth: 420 } as TextStyle,
  primaryButton: { marginTop: 16, backgroundColor: '#7C3AED', paddingHorizontal: 16, minHeight: 40, borderRadius: 10, justifyContent: 'center' },
  primaryButtonText: { color: '#FFFFFF', fontWeight: '700' } as TextStyle,
  featureCard: { minHeight: 72, padding: 12, flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: 14, borderWidth: 1, borderColor: '#283249', backgroundColor: '#11192B' },
  featureIcon: { width: 42, height: 42, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  featureBody: { flex: 1 },
  featureTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  featureTitle: { color: '#F9FAFB', fontSize: 15, fontWeight: '700', flexShrink: 1 } as TextStyle,
  featureSubtitle: { color: '#9CA3AF', fontSize: 12, marginTop: 3 } as TextStyle,
  badge: { color: '#C4B5FD', fontSize: 10, fontWeight: '700', textTransform: 'uppercase' } as TextStyle,
  button: { minHeight: 40, paddingHorizontal: 14, borderRadius: 10, backgroundColor: '#7C3AED', flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7 },
  buttonSecondary: { backgroundColor: 'transparent', borderWidth: 1, borderColor: '#4C3B77' },
  buttonText: { color: '#FFFFFF', fontWeight: '700' } as TextStyle,
  buttonTextSecondary: { color: '#C4B5FD' } as TextStyle,
  disabled: { opacity: 0.5 } as ViewStyle,
});
