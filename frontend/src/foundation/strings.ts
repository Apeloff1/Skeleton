/**
 * Typed app-shell strings. `t()` only accepts known keys and interpolates
 * `{name}` placeholders. Feature catalogs remain in src/i18n; this dictionary
 * covers foundation chrome (gates, async states, error fallbacks, nav).
 */
export const en = {
  'app.name': 'Skeleton',
  'nav.home': 'Home',
  'nav.account': 'Account',
  'nav.settings': 'Settings',
  'nav.back': 'Go back',
  'auth.checking': 'Checking your session…',
  'auth.signIn': 'Sign in',
  'auth.signOut': 'Sign out',
  'auth.required': 'Sign in to continue to {area}.',
  'auth.unavailable': 'The sign-in service is unavailable right now.',
  'auth.signedInAs': 'Signed in as {name}',
  'auth.role': 'Role: {role}',
  'state.loading': 'Loading…',
  'state.empty': 'Nothing here yet',
  'state.emptyHint': 'When there is something to show, it will appear here.',
  'state.error': 'Something went wrong',
  'state.retry': 'Try again',
  'state.offlineStale': 'Showing saved data. Pull to refresh.',
  'error.route': 'This screen hit a problem',
  'error.routeHint': 'The rest of the app is still working. You can retry this screen or go back.',
  'error.home': 'Back to home',
} as const;

export type StringKey = keyof typeof en;
export type Dictionary = { readonly [K in StringKey]: string };
export type Params = Record<string, string | number>;

const dictionaries: Record<string, Partial<Dictionary>> = { en };
let activeLocale = 'en';

export function interpolate(template: string, params?: Params): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : match);
}

export function t(key: StringKey, params?: Params): string {
  const dict = dictionaries[activeLocale] ?? en;
  const template = dict[key] ?? en[key] ?? key;
  return interpolate(template, params);
}

export function registerDictionary(locale: string, dict: Partial<Dictionary>) {
  dictionaries[locale.toLowerCase()] = dict;
}

export function setLocale(locale: string): string {
  const id = locale.toLowerCase();
  const base = id.split(/[-_]/)[0];
  activeLocale = dictionaries[id] ? id : dictionaries[base] ? base : 'en';
  return activeLocale;
}

export function getLocale(): string { return activeLocale; }
