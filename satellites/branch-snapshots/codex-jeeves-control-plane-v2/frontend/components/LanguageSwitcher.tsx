/**
 * Language Switcher Component v12.0
 * 
 * Provides UI for switching application language
 * Supports 10 languages with RTL support
 */

import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Modal,
  ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useI18n, SUPPORTED_LANGUAGES, SupportedLanguage } from '../i18n';


interface LanguageSwitcherProps {
  colors: any;
  compact?: boolean;
}

export const LanguageSwitcher: React.FC<LanguageSwitcherProps> = ({ 
  colors, 
  compact = false 
}) => {
  const { language, setLanguage, languageConfig, t } = useI18n();
  const [showPicker, setShowPicker] = useState(false);

  const handleLanguageSelect = (langCode: SupportedLanguage) => {
    setLanguage(langCode);
    setShowPicker(false);
  };

  if (compact) {
    return (
      <>
        <TouchableOpacity
          style={[styles.compactButton, { backgroundColor: colors.surfaceAlt }]}
          onPress={() => setShowPicker(true)}
        >
          <Text style={styles.flagText}>{languageConfig?.flag || '🌐'}</Text>
          <Ionicons name="chevron-down" size={14} color={colors.textMuted} />
        </TouchableOpacity>

        <Modal
          visible={showPicker}
          transparent
          animationType="fade"
          onRequestClose={() => setShowPicker(false)}
        >
          <TouchableOpacity
            style={styles.overlay}
            activeOpacity={1}
            onPress={() => setShowPicker(false)}
          >
            <View style={[styles.pickerContainer, { backgroundColor: colors.surface }]}>
              <View style={[styles.pickerHeader, { borderBottomColor: colors.border }]}>
                <Text style={[styles.pickerTitle, { color: colors.text }]}>
                  {t('selectLanguage')}
                </Text>
                <TouchableOpacity onPress={() => setShowPicker(false)}>
                  <Ionicons name="close" size={24} color={colors.textSecondary} />
                </TouchableOpacity>
              </View>
              <ScrollView style={styles.languageList}>
                {SUPPORTED_LANGUAGES.map((lang) => (
                  <TouchableOpacity
                    key={lang.code}
                    style={[
                      styles.languageItem,
                      { backgroundColor: colors.surfaceAlt },
                      language === lang.code && { 
                        backgroundColor: colors.primary + '20',
                        borderColor: colors.primary,
                        borderWidth: 1,
                      }
                    ]}
                    onPress={() => handleLanguageSelect(lang.code)}
                  >
                    <Text style={styles.languageFlag}>{lang.flag}</Text>
                    <View style={styles.languageInfo}>
                      <Text style={[styles.languageName, { color: colors.text }]}>
                        {lang.nativeName}
                      </Text>
                      <Text style={[styles.languageEnglish, { color: colors.textMuted }]}>
                        {lang.name}
                      </Text>
                    </View>
                    {language === lang.code && (
                      <Ionicons name="checkmark-circle" size={20} color={colors.primary} />
                    )}
                    {lang.rtl && (
                      <View style={[styles.rtlBadge, { backgroundColor: colors.warning + '20' }]}>
                        <Text style={[styles.rtlText, { color: colors.warning }]}>RTL</Text>
                      </View>
                    )}
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>
          </TouchableOpacity>
        </Modal>
      </>
    );
  }

  return (
    <TouchableOpacity
      style={[styles.fullButton, { backgroundColor: colors.surfaceAlt }]}
      onPress={() => setShowPicker(true)}
    >
      <Text style={styles.flagText}>{languageConfig?.flag || '🌐'}</Text>
      <View style={styles.buttonInfo}>
        <Text style={[styles.buttonLabel, { color: colors.textMuted }]}>
          {t('selectLanguage')}
        </Text>
        <Text style={[styles.buttonValue, { color: colors.text }]}>
          {languageConfig?.nativeName || 'English'}
        </Text>
      </View>
      <Ionicons name="chevron-forward" size={18} color={colors.textMuted} />
    </TouchableOpacity>
  );
};

const styles = StyleSheet.create({
  compactButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
    gap: 4,
  },
  flagText: {
    fontSize: 18,
  },
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  pickerContainer: {
    width: '100%',
    maxWidth: 400,
    maxHeight: '80%',
    borderRadius: 16,
    overflow: 'hidden',
  },
  pickerHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: 1,
  },
  pickerTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  languageList: {
    padding: 16,
  },
  languageItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    borderRadius: 12,
    marginBottom: 8,
    gap: 12,
  },
  languageFlag: {
    fontSize: 24,
  },
  languageInfo: {
    flex: 1,
  },
  languageName: {
    fontSize: 16,
    fontWeight: '600',
  },
  languageEnglish: {
    fontSize: 12,
    marginTop: 2,
  },
  rtlBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
  },
  rtlText: {
    fontSize: 10,
    fontWeight: '700',
  },
  fullButton: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    borderRadius: 12,
    gap: 12,
  },
  buttonInfo: {
    flex: 1,
  },
  buttonLabel: {
    fontSize: 12,
  },
  buttonValue: {
    fontSize: 15,
    fontWeight: '600',
    marginTop: 2,
  },
});

export default LanguageSwitcher;
