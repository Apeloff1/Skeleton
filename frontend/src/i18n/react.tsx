import React from 'react';
import {
  defaultFallbackPolicy,
  interpolateTranslation,
  LocalizationError,
  normalizeLocale,
  TranslationRegistry,
} from './runtime';
import type { TranslationKey } from './runtime';
import { enCatalog } from './catalogs/en';
import { nbCatalog } from './catalogs/nb';

const registry = new TranslationRegistry();
registry.register(enCatalog);
registry.register(nbCatalog);

function detectSystemLocale(): string {
  try {
    const locale = Intl.DateTimeFormat().resolvedOptions().locale;
    return normalizeLocale(locale || 'en');
  } catch {
    return 'en';
  }
}

interface LocaleContextValue {
  locale: string;
  setLocale: (locale: string) => void;
  t: (
    key: TranslationKey,
    values?: Readonly<Record<string, string | number>>,
  ) => string;
  availableLocales: readonly string[];
}

const LocaleContext = React.createContext<LocaleContextValue | null>(null);

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = React.useState<string>(() => detectSystemLocale());

  const setLocale = React.useCallback((next: string) => {
    setLocaleState(normalizeLocale(next));
  }, []);

  const t = React.useCallback((
    key: TranslationKey,
    values?: Readonly<Record<string, string | number>>,
  ) => {
    const resolved = registry.resolve(key, locale, defaultFallbackPolicy()).text;
    return values ? interpolateTranslation(resolved, values) : resolved;
  }, [locale]);

  const value = React.useMemo<LocaleContextValue>(() => ({
    locale,
    setLocale,
    t,
    availableLocales: registry.availableLocales(),
  }), [locale, setLocale, t]);

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useI18n(): LocaleContextValue {
  const value = React.useContext(LocaleContext);
  if (!value) {
    throw new LocalizationError('useI18n must be used inside LocaleProvider');
  }
  return value;
}

export { registry as translationRegistry };
