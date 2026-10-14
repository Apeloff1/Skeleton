import { createCatalog } from '../runtime';
import type { TranslationKey } from '../runtime';

export const EN_MESSAGES: Readonly<Record<TranslationKey, string>> = Object.freeze({
  'app.name': 'Skeleton',
  'app.tagline': 'Unified Product',
  'launcher.open': 'Open Skeleton',
  'launcher.enter_product': 'Enter Product',
  'launcher.minimal': 'Use minimal launcher',
  'operation.cancel': 'Cancel operation',
  'authority.approve': 'Approve',
  'authority.deny': 'Deny',
  'recovery.safe_mode': 'Open Safe Mode',
  'recovery.retry': 'Retry',
  'recovery.continue_anyway': 'Continue anyway',
  'recovery.boot_failed': 'Boot failed. We hit a snag while preparing the app.',
  'status.starting': 'Starting Skeleton',
  'status.startup_check': 'Checking startup safety',
  'status.startup_progress': 'Startup progress: {percent} percent',
  'status.connectivity.offline': 'Offline — changes will sync when you reconnect',
  'status.connectivity.down': 'Server unreachable — retrying…',
  'status.connectivity.degraded': 'Server is slow — some actions may be delayed',
  'notification.dismiss': 'Dismiss notification',
  'prompt.cancel': 'Cancel',
  'prompt.submit': 'Submit',
});

export const enCatalog = createCatalog({
  catalogId: 'frontend.en.v1',
  locale: 'en',
  version: 1,
  messages: EN_MESSAGES,
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
