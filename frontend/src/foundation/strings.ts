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
  'tab.home': 'Home',
  'tab.forge': 'Forge',
  'tab.projects': 'Projects',
  'tab.settings': 'Settings',
  'home.title': 'Welcome back',
  'home.systems': 'System health',
  'home.allGreen': 'All systems operational',
  'home.failing': '{count} subsystems need attention',
  'home.uptime': 'Uptime {value}',
  'forge.title': 'Forge',
  'forge.hint': 'Design, plan and run game builds from the operator cockpit.',
  'forge.open': 'Open forge operator',
  'projects.title': 'Projects',
  'projects.emptyHint': 'Saved builds, worlds and assets appear here.',
  'projects.count': '{count} items',
  'settings.title': 'Settings',
  'settings.all': 'All settings',
  'settings.language': 'Language',
  'settings.account': 'Account',
  'home.builds': 'Live builds',
  'home.noBuilds': 'No builds running right now.',
  'live.connected': 'Live',
  'live.offline': 'Live updates paused',
  'live.lagged': 'Some live updates were skipped. Tap to dismiss.',
} as const;

export type StringKey = keyof typeof en;
export type Dictionary = { readonly [K in StringKey]: string };
export type Params = Record<string, string | number>;

export const nb: Partial<Dictionary> = {
  'nav.home': 'Hjem',
  'nav.account': 'Konto',
  'nav.settings': 'Innstillinger',
  'nav.back': 'Gå tilbake',
  'auth.checking': 'Sjekker økten din …',
  'auth.signIn': 'Logg inn',
  'auth.signOut': 'Logg ut',
  'auth.required': 'Logg inn for å fortsette til {area}.',
  'auth.unavailable': 'Innloggingstjenesten er utilgjengelig akkurat nå.',
  'auth.signedInAs': 'Logget inn som {name}',
  'auth.role': 'Rolle: {role}',
  'state.loading': 'Laster …',
  'state.empty': 'Ingenting her ennå',
  'state.emptyHint': 'Når det finnes noe å vise, dukker det opp her.',
  'state.error': 'Noe gikk galt',
  'state.retry': 'Prøv igjen',
  'state.offlineStale': 'Viser lagrede data. Dra ned for å oppdatere.',
  'error.route': 'Denne skjermen fikk et problem',
  'error.routeHint': 'Resten av appen virker fortsatt. Du kan prøve igjen eller gå tilbake.',
  'error.home': 'Tilbake til start',
  'tab.home': 'Hjem',
  'tab.forge': 'Smie',
  'tab.projects': 'Prosjekter',
  'tab.settings': 'Innstillinger',
  'home.title': 'Velkommen tilbake',
  'home.systems': 'Systemhelse',
  'home.allGreen': 'Alle systemer i drift',
  'home.failing': '{count} delsystemer trenger oppmerksomhet',
  'home.uptime': 'Oppetid {value}',
  'forge.title': 'Smie',
  'forge.hint': 'Design, planlegg og kjør spillbygg fra operatørcockpiten.',
  'forge.open': 'Åpne smieoperatør',
  'projects.title': 'Prosjekter',
  'projects.emptyHint': 'Lagrede bygg, verdener og ressurser vises her.',
  'projects.count': '{count} elementer',
  'settings.title': 'Innstillinger',
  'settings.all': 'Alle innstillinger',
  'settings.language': 'Språk',
  'settings.account': 'Konto',
  'home.builds': 'Bygg som kjører',
  'home.noBuilds': 'Ingen bygg kjører akkurat nå.',
  'live.connected': 'Direkte',
  'live.offline': 'Direkteoppdateringer på pause',
  'live.lagged': 'Noen direkteoppdateringer ble hoppet over. Trykk for å lukke.',
};

const dictionaries: Record<string, Partial<Dictionary>> = { en, nb };
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
