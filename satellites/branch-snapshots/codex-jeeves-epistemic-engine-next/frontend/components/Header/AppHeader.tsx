// ============================================================================
// CODEDOCK - APP HEADER COMPONENT
// ============================================================================

import React, { memo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { ThemeColors } from '../../constants/themes';
import { Language, ConnectionStatus } from '../../types';

interface AppHeaderProps {
  selectedLanguage: Language | null;
  onLanguagePress: () => void;
  onThemeToggle: () => void;
  onSettingsPress: () => void;
  onTutorialPress: () => void;
  theme: 'dark' | 'light';
  colors: ThemeColors;
  tutorialCompleted: boolean;
  connectionStatus: ConnectionStatus;
  onReconnect: () => void;
}

// eslint-disable-next-line react/display-name
export const AppHeader: React.FC<AppHeaderProps> = memo(({
  selectedLanguage,
  onLanguagePress,
  onThemeToggle,
  onSettingsPress,
  onTutorialPress,
  theme,
  colors,
  tutorialCompleted,
  connectionStatus,
  onReconnect,
}) => {
  const getIconName = (icon: string): keyof typeof Ionicons.glyphMap => {
    const validIcons: Record<string, keyof typeof Ionicons.glyphMap> = {
      'logo-python': 'logo-python',
      'logo-javascript': 'logo-javascript',
      'logo-html5': 'logo-html5',
      'code-slash': 'code-slash',
    };
    return validIcons[icon] || 'code-slash';
  };

  return (
    <View style={[styles.header, { backgroundColor: colors.surface, borderBottomColor: colors.border }]}>
      <TouchableOpacity style={styles.languageSelector} onPress={onLanguagePress}>
        <View style={[styles.langIconBg, { backgroundColor: (selectedLanguage?.color || colors.primary) + '20' }]}>
          <Ionicons 
            name={getIconName(selectedLanguage?.icon || 'code-slash')} 
            size={20} 
            color={selectedLanguage?.color || colors.primary} 
          />
        </View>
        <View>
          <Text style={[styles.languageName, { color: colors.text }]}>
            {selectedLanguage?.name || 'Select Language'}
          </Text>
          <Text style={[styles.languageVersion, { color: colors.textMuted }]}>
            {selectedLanguage?.display_name || ''}
          </Text>
        </View>
        <Ionicons name="chevron-down" size={16} color={colors.textMuted} />
      </TouchableOpacity>

      <View style={styles.headerActions}>
        {connectionStatus !== 'connected' && (
          <TouchableOpacity 
            style={[styles.headerButton, { backgroundColor: connectionStatus === 'disconnected' ? colors.error + '20' : colors.warning + '20' }]} 
            onPress={onReconnect}
          >
            <Ionicons 
              name={connectionStatus === 'disconnected' ? 'cloud-offline' : 'cloud-upload'} 
              size={18} 
              color={connectionStatus === 'disconnected' ? colors.error : colors.warning} 
            />
          </TouchableOpacity>
        )}
        {!tutorialCompleted && (
          <TouchableOpacity 
            style={[styles.headerButton, { backgroundColor: colors.tutorial + '20' }]} 
            onPress={onTutorialPress}
          >
            <Ionicons name="school" size={18} color={colors.tutorial} />
          </TouchableOpacity>
        )}
        <TouchableOpacity style={styles.headerButton} onPress={onThemeToggle}>
          <Ionicons name={theme === 'dark' ? 'sunny' : 'moon'} size={20} color={colors.secondary} />
        </TouchableOpacity>
        <TouchableOpacity style={styles.headerButton} onPress={onSettingsPress}>
          <Ionicons name="settings-outline" size={20} color={colors.secondary} />
        </TouchableOpacity>
      </View>
    </View>
  );
});

const styles = StyleSheet.create({
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
  },
  languageSelector: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  langIconBg: {
    width: 36,
    height: 36,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  languageName: {
    fontSize: 16,
    fontWeight: '600',
  },
  languageVersion: {
    fontSize: 11,
  },
  headerActions: {
    flexDirection: 'row',
    gap: 4,
  },
  headerButton: {
    padding: 8,
    borderRadius: 8,
  },
});

export default AppHeader;
