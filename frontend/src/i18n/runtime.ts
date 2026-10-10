export type LocaleId = string;

export type TranslationKey =
  | 'app.name'
  | 'app.tagline'
  | 'launcher.open'
  | 'launcher.enter_product'
  | 'launcher.minimal'
  | 'operation.cancel'
  | 'authority.approve'
  | 'authority.deny'
  | 'recovery.safe_mode'
  | 'recovery.retry'
  | 'recovery.continue_anyway'
  | 'recovery.boot_failed'
  | 'status.starting'
  | 'status.startup_check'
  | 'status.startup_progress'
  | 'status.connectivity.offline'
  | 'status.connectivity.down'
  | 'status.connectivity.degraded'
  | 'notification.dismiss'
  | 'prompt.cancel'
  | 'prompt.submit';

export const CRITICAL_TRANSLATION_KEYS: readonly TranslationKey[] = Object.freeze([
  'operation.cancel',
  'authority.approve',
  'authority.deny',
  'recovery.safe_mode',
  'recovery.retry',
  'recovery.continue_anyway',
  'recovery.boot_failed',
]);

export interface TranslationCatalog {
  readonly catalogId: string;
  readonly locale: LocaleId;
  readonly version: number;
  readonly messages: Readonly<Record<string, string>>;
  readonly reviewedCriticalKeys: readonly string[];
}

export interface LocaleFallbackPolicy {
  readonly policyId: string;
  readonly defaultLocale: LocaleId;
  readonly allowLanguageParent: boolean;
  readonly allowDefaultLocale: boolean;
  readonly allowCriticalDefaultFallback: boolean;
  readonly requireReviewedCritical: boolean;
  readonly maxDepth: number;
}

export interface TranslationResolution {
  readonly key: string;
  readonly text: string;
  readonly requestedLocale: LocaleId;
  readonly resolvedLocale: LocaleId;
  readonly catalogId: string;
  readonly catalogVersion: number;
  readonly fallbackUsed: boolean;
  readonly critical: boolean;
  readonly reviewed: boolean;
}

const LOCALE_RE = /^[A-Za-z]{2,8}(?:-[A-Za-z]{4})?(?:-(?:[A-Za-z]{2}|[0-9]{3}))?(?:-[A-Za-z0-9]{5,8})*$/;
const TOKEN_RE = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$/;
const KEY_RE = /^[a-z][a-z0-9]*(?:[._-][a-z0-9]+){0,15}$/;
const NUMBER_RE = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$/;
const INTEGER_RE = /^-?(?:0|[1-9][0-9]*)$/;
const UTC_TIMESTAMP_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/;
const CRITICAL_PREFIXES = Object.freeze([
  'authority.',
  'operation.',
  'recovery.',
  'safety.',
  'security.',
]);

export class LocalizationError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'LocalizationError';
  }
}

function boundedText(value: string, field: string, max = 4096): string {
  if (typeof value !== 'string' || value.trim() !== value || value.length === 0 || value.length > max) {
    throw new LocalizationError(field + ' must be normalized bounded text');
  }
  return value;
}

function token(value: string, field: string): string {
  if (typeof value !== 'string' || !TOKEN_RE.test(value)) {
    throw new LocalizationError(field + ' must be a canonical token');
  }
  return value;
}

function translationKey(value: string): string {
  if (typeof value !== 'string' || !KEY_RE.test(value)) {
    throw new LocalizationError('translation key must be canonical');
  }
  return value;
}

export function normalizeLocale(value: string): LocaleId {
  if (typeof value !== 'string' || !LOCALE_RE.test(value)) {
    throw new LocalizationError('locale must be a bounded BCP47-shaped tag');
  }
  const parts = value.split('-');
  const normalized = [parts[0].toLowerCase()];
  for (const part of parts.slice(1)) {
    if (part.length === 4 && /^[A-Za-z]+$/.test(part)) {
      normalized.push(part[0].toUpperCase() + part.slice(1).toLowerCase());
    } else if (
      (part.length === 2 && /^[A-Za-z]+$/.test(part)) ||
      (part.length === 3 && /^\d+$/.test(part))
    ) {
      normalized.push(part.toUpperCase());
    } else {
      normalized.push(part.toLowerCase());
    }
  }
  return normalized.join('-');
}

export function localeParentChain(value: string): readonly LocaleId[] {
  const normalized = normalizeLocale(value);
  const parts = normalized.split('-');
  const parents: string[] = [];
  while (parts.length > 1) {
    parts.pop();
    parents.push(parts.join('-'));
  }
  return Object.freeze(parents);
}

export function createCatalog(input: TranslationCatalog): TranslationCatalog {
  const locale = normalizeLocale(input.locale);
  const catalogId = token(input.catalogId, 'catalogId');
  if (!Number.isInteger(input.version) || input.version < 1) {
    throw new LocalizationError('catalog version must be a positive integer');
  }
  const messages: Record<string, string> = {};
  for (const [key, value] of Object.entries(input.messages)) {
    messages[translationKey(key)] = boundedText(value, 'translation text');
  }
  const reviewed = [...new Set(input.reviewedCriticalKeys.map(translationKey))].sort();
  for (const key of reviewed) {
    if (!(key in messages)) {
      throw new LocalizationError('reviewed critical key is missing from catalog: ' + key);
    }
  }
  for (const key of Object.keys(messages)) {
    if (isCriticalTranslationKey(key) && !reviewed.includes(key)) {
      throw new LocalizationError('critical translation lacks review: ' + key);
    }
  }
  return Object.freeze({
    catalogId,
    locale,
    version: input.version,
    messages: Object.freeze({ ...messages }),
    reviewedCriticalKeys: Object.freeze(reviewed),
  });
}

export function defaultFallbackPolicy(): LocaleFallbackPolicy {
  return Object.freeze({
    policyId: 'frontend.locale.default.v1',
    defaultLocale: 'en',
    allowLanguageParent: true,
    allowDefaultLocale: true,
    allowCriticalDefaultFallback: true,
    requireReviewedCritical: true,
    maxDepth: 4,
  });
}

export function isCriticalTranslationKey(key: string): boolean {
  const normalized = translationKey(key);
  return CRITICAL_TRANSLATION_KEYS.includes(normalized as TranslationKey) ||
    CRITICAL_PREFIXES.some((prefix) => normalized.startsWith(prefix));
}

function fallbackChain(
  requestedLocale: string,
  policy: LocaleFallbackPolicy,
): readonly LocaleId[] {
  const requested = normalizeLocale(requestedLocale);
  const candidates: string[] = [requested];
  if (policy.allowLanguageParent) {
    candidates.push(...localeParentChain(requested));
  }
  const defaultLocale = normalizeLocale(policy.defaultLocale);
  if (policy.allowDefaultLocale && !candidates.includes(defaultLocale)) {
    candidates.push(defaultLocale);
  }
  return Object.freeze([...new Set(candidates)].slice(0, policy.maxDepth));
}

export class TranslationRegistry {
  private readonly catalogs = new Map<LocaleId, TranslationCatalog>();

  register(catalog: TranslationCatalog): TranslationCatalog {
    const normalized = createCatalog(catalog);
    const existing = this.catalogs.get(normalized.locale);
    if (existing) {
      if (
        existing.catalogId === normalized.catalogId &&
        existing.version === normalized.version &&
        JSON.stringify(existing.messages) === JSON.stringify(normalized.messages)
      ) {
        return existing;
      }
      if (normalized.version <= existing.version) {
        throw new LocalizationError('catalog replacement must increase version');
      }
    }
    this.catalogs.set(normalized.locale, normalized);
    return normalized;
  }

  resolve(
    key: string,
    requestedLocale: string,
    policy: LocaleFallbackPolicy = defaultFallbackPolicy(),
  ): TranslationResolution {
    const normalizedKey = translationKey(key);
    const requested = normalizeLocale(requestedLocale);
    const critical = isCriticalTranslationKey(normalizedKey);

    for (const candidate of fallbackChain(requested, policy)) {
      const catalog = this.catalogs.get(candidate);
      const message = catalog?.messages[normalizedKey];
      if (!catalog || message === undefined) continue;
      const fallbackUsed = candidate !== requested;
      const reviewed = catalog.reviewedCriticalKeys.includes(normalizedKey);

      if (critical && policy.requireReviewedCritical && !reviewed) {
        throw new LocalizationError('critical translation is unreviewed: ' + normalizedKey);
      }
      if (
        critical &&
        fallbackUsed &&
        candidate === normalizeLocale(policy.defaultLocale) &&
        !policy.allowCriticalDefaultFallback
      ) {
        throw new LocalizationError('critical default fallback forbidden: ' + normalizedKey);
      }

      return Object.freeze({
        key: normalizedKey,
        text: message,
        requestedLocale: requested,
        resolvedLocale: candidate,
        catalogId: catalog.catalogId,
        catalogVersion: catalog.version,
        fallbackUsed,
        critical,
        reviewed,
      });
    }

    throw new LocalizationError(
      (critical ? 'missing critical translation: ' : 'missing translation: ') + normalizedKey,
    );
  }

  availableLocales(): readonly LocaleId[] {
    return Object.freeze([...this.catalogs.keys()].sort());
  }
}

export function serializeNeutralNumber(value: number): string {
  if (!Number.isFinite(value)) {
    throw new LocalizationError('persisted number must be finite');
  }
  if (Object.is(value, -0) || value === 0) return '0';
  const rendered = String(value);
  if (/[eE]/.test(rendered)) {
    const expanded = value.toLocaleString('en-US', {
      useGrouping: false,
      maximumSignificantDigits: 21,
    });
    if (!NUMBER_RE.test(expanded)) {
      throw new LocalizationError('number cannot be represented canonically');
    }
    return expanded;
  }
  if (!NUMBER_RE.test(rendered)) {
    throw new LocalizationError('number cannot be represented canonically');
  }
  return rendered;
}

export function parseNeutralNumber(value: string): number {
  if (typeof value !== 'string' || !NUMBER_RE.test(value)) {
    throw new LocalizationError('number is not canonical locale-neutral text');
  }
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || serializeNeutralNumber(parsed) !== value) {
    throw new LocalizationError('number is not normalized canonical text');
  }
  return parsed;
}

export function serializeNeutralInteger(value: number): string {
  if (!Number.isSafeInteger(value)) {
    throw new LocalizationError('persisted integer must be a safe integer');
  }
  return String(value);
}

export function parseNeutralInteger(value: string): number {
  if (typeof value !== 'string' || !INTEGER_RE.test(value)) {
    throw new LocalizationError('integer is not canonical locale-neutral text');
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || String(parsed) !== value) {
    throw new LocalizationError('integer is not normalized canonical text');
  }
  return parsed;
}

export function serializeNeutralTimestamp(value: Date): string {
  if (!(value instanceof Date) || !Number.isFinite(value.getTime())) {
    throw new LocalizationError('timestamp must be a valid Date');
  }
  return value.toISOString();
}

export function parseNeutralTimestamp(value: string): Date {
  if (typeof value !== 'string' || !UTC_TIMESTAMP_RE.test(value)) {
    throw new LocalizationError('timestamp must be canonical UTC ISO text');
  }
  const parsed = new Date(value);
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString() !== value) {
    throw new LocalizationError('timestamp is not normalized canonical UTC');
  }
  return parsed;
}

export function serializeNeutralToken(value: string): string {
  return token(value, 'identifier');
}

export function formatNumberForLocale(
  value: number,
  locale: string,
  options?: Intl.NumberFormatOptions,
): string {
  if (!Number.isFinite(value)) throw new LocalizationError('display number must be finite');
  return new Intl.NumberFormat(normalizeLocale(locale), options).format(value);
}

export function formatDateTimeForLocale(
  value: Date,
  locale: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  if (!(value instanceof Date) || !Number.isFinite(value.getTime())) {
    throw new LocalizationError('display timestamp must be valid');
  }
  return new Intl.DateTimeFormat(normalizeLocale(locale), options).format(value);
}

export function interpolateTranslation(
  text: string,
  values: Readonly<Record<string, string | number>>,
): string {
  const source = boundedText(text, 'translation text');
  return source.replace(/\{([A-Za-z][A-Za-z0-9_]*)\}/g, (_match, key: string) => {
    if (!(key in values)) {
      throw new LocalizationError('missing translation interpolation value: ' + key);
    }
    return String(values[key]);
  });
}
