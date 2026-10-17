'use strict';
/** Execute token/skin source without a live React Native runtime. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const ts = require('typescript');

function transpile(relative, imports = {}) {
  const file = path.resolve(__dirname, '..', relative);
  const source = fs.readFileSync(file, 'utf8');
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
      esModuleInterop: true,
    },
    fileName: file,
  });
  const module = { exports: {} };
  const requireModule = (specifier) => {
    if (specifier === 'react-native')
      return { Platform: { select: options => options.default } };
    if (Object.prototype.hasOwnProperty.call(imports, specifier))
      return imports[specifier];
    throw new Error('Unexpected theme import: ' + specifier);
  };
  vm.runInNewContext(compiled.outputText, {
    module, exports: module.exports, require: requireModule, console,
  }, { filename: file });
  return module.exports;
}

const tokens = transpile('theme/tokens.ts');
const skins = transpile('theme/skins.ts', { './tokens': tokens });
const roles = transpile('constants/themes.ts', { '../theme/tokens': tokens });

function luminance(hex) {
  const rgb = /^#([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  assert.ok(rgb, 'invalid color: ' + hex);
  const ch = rgb.slice(1).map(v => {
    const n = parseInt(v, 16) / 255;
    return n <= 0.04045 ? n / 12.92 : ((n + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}
function contrast(a, b) {
  const x = luminance(a), y = luminance(b);
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}

test('canonical tokens contain correct cyan, roles and legible brand text', () => {
  assert.equal(tokens.palette.cyan[400], '#22D3EE');
  assert.equal(tokens.palette.blue[400], '#3B82F6');
  assert.equal(tokens.colors.dark.accentCyan, '#22D3EE');
  assert.equal(tokens.typography.metric.fontSize, 24);
  assert.equal(tokens.typography.label.fontSize, 12);
  assert.ok(contrast(tokens.colors.dark.onPrimary, tokens.colors.dark.primary) >= 4.5);
  assert.ok(contrast(tokens.colors.light.onPrimary, tokens.colors.light.primary) >= 4.5);
});

test('30 skins have RGBA soft fill and contrast-aware primary foreground', () => {
  assert.equal(skins.SKINS.length, 30);
  const exceptions = [];
  for (const skin of skins.SKINS) {
    const c = skin.colors;
    assert.match(c.primarySoft, /^rgba\(\d+,\d+,\d+,0\.16\)$/);
    assert.equal(c.onPrimary, skins.onPrimaryFor(c.primary));
    const ratio = contrast(c.onPrimary, c.primary);
    if (ratio < 4.5) exceptions.push(skin.id);
    assert.ok(ratio >= 4.5, skin.id + ' AA contrast ' + ratio);
  }
  assert.deepEqual(exceptions, []);
  assert.equal(skins.SKIN_BY_ID.lavender.colors.onPrimary, '#04060D');
  assert.equal(skins.SKIN_BY_ID.royal.colors.onPrimary, '#04060D');
  const d = skins.SKIN_BY_ID.hyperwave.colors;
  assert.ok(contrast(d.onPrimary, d.primary) >= 4.5);
});

test('legacy light and dark roles read canonical and active skin values', () => {
  assert.equal(roles.themes.light.background, tokens.colors.light.bg);
  assert.equal(roles.themes.light.primary, tokens.colors.light.primary);
  assert.equal(roles.themes.dark.background, tokens.colors.dark.bg);
  const skin = skins.SKIN_BY_ID.hyperwave;
  Object.assign(tokens.default.colors, skin.colors);
  assert.equal(roles.themes.dark.primary, skin.colors.primary);
  assert.equal(roles.darkTheme.primary, skin.colors.primary);
  assert.equal(roles.themes.dark.background, skin.colors.bg);
  assert.equal(roles.themes.dark.accent, skin.colors.accentCyan);
  assert.equal(roles.themes.light.primary, tokens.colors.light.primary);
});

test('Deluxe cards and Forge status colors follow skin transitions without stale captures', () => {
  const deluxe = transpile('src/theme/deluxe.ts', {
    '../../theme/tokens': tokens,
  });
  const forge = transpile('src/skeletonForge/components/theme.ts', {
    '../../../theme/tokens': tokens,
  });
  for (const id of ['hyperwave', 'oceanic', 'ember', 'lavender']) {
    const c = skins.SKIN_BY_ID[id].colors;
    Object.assign(tokens.default.colors, c);
    assert.equal(deluxe.C.brand, c.primary, id);
    assert.equal(deluxe.card.backgroundColor, c.bgElevated, id);
    assert.equal(deluxe.cardActive.borderColor, c.primary, id);
    assert.equal(forge.TONE_COLOR.warn, tokens.default.colors.warning, id);
    assert.equal(forge.TONE_COLOR.bad, tokens.default.colors.danger, id);
    assert.equal(forge.C.accent, c.primaryHover, id);
  }
});

test('Deluxe and cockpit contain no independent hexadecimal color palettes', () => {
  for (const relative of ['src/theme/deluxe.ts',
    'src/skeletonForge/components/theme.ts', 'constants/themes.ts']) {
    const file = fs.readFileSync(path.resolve(__dirname, '..', relative), 'utf8');
    assert.doesNotMatch(file, /#[0-9a-fA-F]{3,8}\b/);
  }
  const hook = fs.readFileSync(
    path.resolve(__dirname, '..', 'hooks/useTheme.ts'), 'utf8');
  assert.match(hook, /useActiveSkin\(\)/);
});
