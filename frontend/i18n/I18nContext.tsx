/**
 * CodeDock i18n Context & Hook v11.9
 * 
 * Provides internationalization context and hooks for the entire app
 */

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { 
  SupportedLanguage, 
  Translations, 
  getTranslations, 
  t as translate,
  SUPPORTED_LANGUAGES,
  LanguageConfig,
  getLanguageConfig
} from './translations';

interface I18nContextType {
  language: SupportedLanguage;
  setLanguage: (lang: SupportedLanguage) => void;
  t: (key: keyof Translations) => string;
  translations: Translations;
  supportedLanguages: LanguageConfig[];
  isRTL: boolean;
  languageConfig: LanguageConfig | undefined;
}

const I18nContext = createContext<I18nContextType | undefined>(undefined);

const STORAGE_KEY = '@codedock_language';

interface I18nProviderProps {
  children: ReactNode;
  defaultLanguage?: SupportedLanguage;
}

export const I18nProvider: React.FC<I18nProviderProps> = ({ 
  children, 
  defaultLanguage = 'en' 
}) => {
  const [language, setLanguageState] = useState<SupportedLanguage>(defaultLanguage);
  const [translations, setTranslations] = useState<Translations>(getTranslations(defaultLanguage));

  // Load saved language on mount
  useEffect(() => {
    const loadLanguage = async () => {
      try {
        const saved = await AsyncStorage.getItem(STORAGE_KEY);
        if (saved && SUPPORTED_LANGUAGES.some(l => l.code === saved)) {
          setLanguageState(saved as SupportedLanguage);
          setTranslations(getTranslations(saved as SupportedLanguage));
        }
      } catch (error) {
        console.error('Failed to load language preference:', error);
      }
    };
    loadLanguage();
  }, []);

  // Set language and persist
  const setLanguage = useCallback(async (lang: SupportedLanguage) => {
    try {
      await AsyncStorage.setItem(STORAGE_KEY, lang);
      setLanguageState(lang);
      setTranslations(getTranslations(lang));
    } catch (error) {
      console.error('Failed to save language preference:', error);
    }
  }, []);

  // Translation function
  const t = useCallback((key: keyof Translations): string => {
    return translate(key, language);
  }, [language]);

  const languageConfig = getLanguageConfig(language);
  const isRTL = languageConfig?.rtl || false;

  const value: I18nContextType = {
    language,
    setLanguage,
    t,
    translations,
    supportedLanguages: SUPPORTED_LANGUAGES,
    isRTL,
    languageConfig,
  };

  return (
    <I18nContext.Provider value={value}>
      {children}
    </I18nContext.Provider>
  );
};

export const useI18n = (): I18nContextType => {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error('useI18n must be used within an I18nProvider');
  }
  return context;
};

// Standalone translation hook for components that don't need full context
export const useTranslation = () => {
  const { t, language, isRTL } = useI18n();
  return { t, language, isRTL };
};

export default I18nContext;
