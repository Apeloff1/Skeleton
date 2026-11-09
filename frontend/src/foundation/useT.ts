/**
 * Bridges the foundation `t()` to the app-wide src/i18n LocaleProvider, so
 * shell strings follow the same locale (en/nb) as feature catalogs and
 * re-render when the user switches language.
 */
import { useMemo } from 'react';
import { useI18n } from '../i18n';
import { setLocale, t } from './strings';

export function useT(): { t: typeof t; locale: string } {
  const { locale } = useI18n();
  return useMemo(() => {
    const active = setLocale(locale);
    return { t: (...args: Parameters<typeof t>) => t(...args), locale: active };
  }, [locale]);
}

export default useT;
