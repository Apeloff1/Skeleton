import test from 'node:test';
import assert from 'node:assert/strict';
import Module, { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import ts from 'typescript';

const root = resolve(import.meta.dirname, '..');
const localRequire = createRequire(import.meta.url);

function transpile(path) {
  const source = readFileSync(path, 'utf8');
  return ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      strict: true,
      esModuleInterop: true,
    },
    fileName: path,
  }).outputText;
}

function compileCommonJS(path, requireFn = localRequire) {
  const mod = new Module(path);
  mod.filename = path;
  mod.paths = Module._nodeModulePaths(root);
  mod.require = requireFn;
  mod._compile(transpile(path), path);
  return mod.exports;
}

const runtimePath = resolve(root, 'src/i18n/runtime.ts');
const i18n = compileCommonJS(runtimePath);

function loadCatalog(relativePath) {
  const path = resolve(root, relativePath);
  const customRequire = (id) => {
    if (id === '../runtime') return i18n;
    return localRequire(id);
  };
  return compileCommonJS(path, customRequire);
}

const en = loadCatalog('src/i18n/catalogs/en.ts');
const nb = loadCatalog('src/i18n/catalogs/nb.ts');

function source(path) {
  return readFileSync(resolve(root, path), 'utf8');
}

test('locale normalization is deterministic', () => {
  assert.equal(i18n.normalizeLocale('EN-us'), 'en-US');
  assert.equal(i18n.normalizeLocale('zh-hant-tw'), 'zh-Hant-TW');
  assert.deepEqual(i18n.localeParentChain('zh-Hant-TW'), ['zh-Hant', 'zh']);
});

test('invalid locale identities fail closed', () => {
  for (const value of ['', 'en_US', '1n', 'en--US']) {
    assert.throws(() => i18n.normalizeLocale(value), /locale/);
  }
});

test('shipped catalogs are versioned and registered', () => {
  assert.equal(en.enCatalog.locale, 'en');
  assert.equal(nb.nbCatalog.locale, 'nb');
  assert.equal(en.enCatalog.version, 1);
  assert.equal(nb.nbCatalog.version, 1);

  const registry = new i18n.TranslationRegistry();
  registry.register(en.enCatalog);
  registry.register(nb.nbCatalog);
  assert.deepEqual(registry.availableLocales(), ['en', 'nb']);
});

test('every shipped catalog covers and reviews the critical string inventory', () => {
  for (const catalog of [en.enCatalog, nb.nbCatalog]) {
    for (const key of i18n.CRITICAL_TRANSLATION_KEYS) {
      assert.equal(typeof catalog.messages[key], 'string', catalog.locale + ':' + key);
      assert.ok(catalog.messages[key].length > 0);
      assert.ok(catalog.reviewedCriticalKeys.includes(key), catalog.locale + ':' + key);
    }
  }
});

test('resolution prefers exact locale then parent then default', () => {
  const registry = new i18n.TranslationRegistry();
  registry.register(en.enCatalog);
  registry.register(nb.nbCatalog);

  const exact = registry.resolve('recovery.safe_mode', 'nb');
  const parent = registry.resolve('recovery.safe_mode', 'nb-NO');
  const fallback = registry.resolve('recovery.safe_mode', 'fr-FR');

  assert.equal(exact.resolvedLocale, 'nb');
  assert.equal(exact.fallbackUsed, false);
  assert.equal(parent.resolvedLocale, 'nb');
  assert.equal(parent.fallbackUsed, true);
  assert.equal(fallback.resolvedLocale, 'en');
  assert.equal(fallback.fallbackUsed, true);
  assert.equal(fallback.reviewed, true);
});

test('critical default fallback can be disabled', () => {
  const registry = new i18n.TranslationRegistry();
  registry.register(en.enCatalog);
  const policy = {
    ...i18n.defaultFallbackPolicy(),
    allowCriticalDefaultFallback: false,
  };
  assert.throws(
    () => registry.resolve('operation.cancel', 'fr-FR', policy),
    /fallback forbidden/,
  );
});

test('unreviewed critical catalog content is rejected at construction', () => {
  assert.throws(
    () => i18n.createCatalog({
      catalogId: 'bad.en.v1',
      locale: 'en',
      version: 1,
      messages: { 'operation.cancel': 'Cancel' },
      reviewedCriticalKeys: [],
    }),
    /lacks review/,
  );
});

test('locale-neutral number persistence rejects localized forms', () => {
  assert.equal(i18n.serializeNeutralNumber(1.5), '1.5');
  assert.equal(i18n.parseNeutralNumber('1.5'), 1.5);
  for (const value of ['1,5', '1 000', '+1', '01', '1.0', '1e3']) {
    assert.throws(() => i18n.parseNeutralNumber(value), /canonical/);
  }
});

test('integer persistence is locale-neutral and safe-integer bounded', () => {
  assert.equal(i18n.serializeNeutralInteger(-42), '-42');
  assert.equal(i18n.parseNeutralInteger('-42'), -42);
  for (const value of ['+42', '042', '4,200']) {
    assert.throws(() => i18n.parseNeutralInteger(value), /canonical/);
  }
  assert.throws(
    () => i18n.serializeNeutralInteger(Number.MAX_SAFE_INTEGER + 1),
    /safe integer/,
  );
});

test('timestamp persistence is canonical UTC milliseconds', () => {
  const date = new Date('2026-10-05T12:41:12.987Z');
  assert.equal(i18n.serializeNeutralTimestamp(date), '2026-10-05T12:41:12.987Z');
  assert.equal(
    i18n.parseNeutralTimestamp('2026-10-05T12:41:12.987Z').toISOString(),
    '2026-10-05T12:41:12.987Z',
  );
  assert.throws(
    () => i18n.parseNeutralTimestamp('2026-10-05T12:41:12Z'),
    /canonical/,
  );
});

test('identifiers never pass through locale formatting', () => {
  assert.equal(i18n.serializeNeutralToken('operation:abc-123'), 'operation:abc-123');
  assert.throws(() => i18n.serializeNeutralToken('pågående'), /canonical token/);
});

test('translation interpolation requires every named value', () => {
  assert.equal(
    i18n.interpolateTranslation('Progress: {percent}', { percent: 50 }),
    'Progress: 50',
  );
  assert.throws(
    () => i18n.interpolateTranslation('Progress: {percent}', {}),
    /missing translation interpolation/,
  );
});

test('presentation formatting is separate from persistence parsing', () => {
  const persisted = i18n.serializeNeutralNumber(1234.5);
  assert.equal(persisted, '1234.5');
  const english = i18n.formatNumberForLocale(1234.5, 'en-US');
  const norwegian = i18n.formatNumberForLocale(1234.5, 'nb-NO');
  assert.notEqual(english, '');
  assert.notEqual(norwegian, '');
  assert.equal(i18n.parseNeutralNumber(persisted), 1234.5);
});

test('root layout installs LocaleProvider above global hosts', () => {
  const content = source('app/_layout.tsx');
  assert.match(content, /LocaleProvider/);
  assert.match(content, /<LocaleProvider>[\s\S]*<StabilityBanner \/>/);
  assert.match(content, /<LocaleProvider>[\s\S]*<ToastHost \/>/);
  assert.match(content, /<LocaleProvider>[\s\S]*<ActionSheetHost \/>/);
});

test('critical startup and recovery surfaces resolve catalog keys', () => {
  const entry = source('app/index.tsx');
  const cascade = source('components/LaunchCascade.tsx');
  const boot = source('components/BootLauncher.tsx');

  assert.match(entry, /t\('status\.startup_check'\)/);
  assert.match(cascade, /t\('recovery\.safe_mode'\)/);
  assert.match(cascade, /t\('recovery\.retry'\)/);
  assert.match(boot, /t\('recovery\.boot_failed'\)/);
  assert.match(boot, /t\('recovery\.continue_anyway'\)/);
  assert.match(boot, /t\('status\.startup_progress'/);
});

test('global prompt, notification and connectivity surfaces use i18n', () => {
  const sheet = source('components/ActionSheet.tsx');
  const toast = source('components/Toast.tsx');
  const connectivity = source('src/components/StabilityBanner.tsx');

  assert.match(sheet, /t\('prompt\.cancel'\)/);
  assert.match(sheet, /t\('prompt\.submit'\)/);
  assert.match(toast, /t\('notification\.dismiss'\)/);
  assert.match(connectivity, /status\.connectivity\.offline/);
  assert.match(connectivity, /messageText = t\(message\.key\)/);
});
