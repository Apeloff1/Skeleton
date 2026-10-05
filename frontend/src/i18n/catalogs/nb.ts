import { createCatalog } from '../runtime';
import type { TranslationKey } from '../runtime';

export const NB_MESSAGES: Readonly<Record<TranslationKey, string>> = Object.freeze({
  'app.name': 'Skeleton',
  'app.tagline': 'Samlet produkt',
  'launcher.open': 'Åpne Skeleton',
  'launcher.enter_product': 'Gå inn i produktet',
  'launcher.minimal': 'Bruk minimal oppstart',
  'operation.cancel': 'Avbryt operasjon',
  'authority.approve': 'Godkjenn',
  'authority.deny': 'Avslå',
  'recovery.safe_mode': 'Åpne sikker modus',
  'recovery.retry': 'Prøv igjen',
  'recovery.continue_anyway': 'Fortsett likevel',
  'recovery.boot_failed': 'Oppstart mislyktes. Det oppstod et problem under klargjøringen.',
  'status.starting': 'Starter Skeleton',
  'status.startup_check': 'Kontrollerer oppstartssikkerhet',
  'status.startup_progress': 'Oppstartsframdrift: {percent} prosent',
  'status.connectivity.offline': 'Frakoblet — endringer synkroniseres når du kobler til igjen',
  'status.connectivity.down': 'Serveren kan ikke nås — prøver igjen…',
  'status.connectivity.degraded': 'Serveren er treg — enkelte handlinger kan bli forsinket',
  'notification.dismiss': 'Lukk varsel',
  'prompt.cancel': 'Avbryt',
  'prompt.submit': 'Send',
});

export const nbCatalog = createCatalog({
  catalogId: 'frontend.nb.v1',
  locale: 'nb',
  version: 1,
  messages: NB_MESSAGES,
  reviewedCriticalKeys: [
    'operation.cancel',
    'authority.approve',
    'authority.deny',
    'recovery.safe_mode',
    'recovery.retry',
    'recovery.continue_anyway',
    'recovery.boot_failed',
  ],
});
