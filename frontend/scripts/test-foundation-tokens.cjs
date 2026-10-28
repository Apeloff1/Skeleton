'use strict';
/* global __dirname */
/**
 * Foundation design-token package (frontend/theme/foundation) regression.
 * Executes the TypeScript sources without a React Native runtime, following
 * scripts/test-canonical-theme.cjs. Run: `yarn test:foundation-tokens`.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const ts = require('typescript');

const ROOT = path.resolve(__dirname, '..');

/** Load a TS module graph rooted at `entry`, sharing one module cache. */
function makeLoader() {
  const cache = new Map();
  function load(file) {
    if (cache.has(file)) return cache.get(file).exports;
    const source = fs.readFileSync(file, 'utf8');
    const compiled = ts.transpileModule(source, {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020,
        esModuleInterop: true,
      },
      fileName: file,
    });
    const module = { exports: {} };
    cache.set(file, module);
    const requireModule = (specifier) => {
      if (specifier === 'react-native')
        return { Platform: { select: options => options.default } };
      if (specifier.startsWith('.')) {
        const resolved = path.resolve(path.dirname(file), specifier) + '.ts';
        assert.ok(resolved.startsWith(ROOT), 'import outside frontend: ' + specifier);
        return load(resolved);
      }
      throw new Error('Unexpected foundation import: ' + specifier);
    };
    vm.runInNewContext(compiled.outputText, {
      module, exports: module.exports, require: requireModule, console,
    }, { filename: file });
    return module.exports;
  }
  return (relative) => load(path.resolve(ROOT, relative));
}

// Independent WCAG 2.x implementation (do not reuse the package helper).
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
/** Objects from the vm realm have foreign prototypes; compare as plain JSON. */
const plain = v => JSON.parse(JSON.stringify(v));
const same = (a, b, m) => assert.deepEqual(plain(a), plain(b), m);
const THRESHOLD = { AAA: 7, AA: 4.5, large: 3 };

/**
 * docs/UI_ART_KIT.md §2.5 (A = tokens.ts) pairs: [fg, bg, claimed ratio, claimed level].
 * Level 'large' = large text / UI only; 'fail' = below 3:1 (must not carry information).
 * onPrimary rows: dark from the UI_ART_KIT Oct 16 checkpoint (ink1000 ~4.78),
 * light = white on brand600 (5.70).
 */
const CLAIMS = {
  dark: [
    ['text', 'bg', 18.78, 'AAA'],
    ['textMuted', 'bg', 7.67, 'AAA'],
    ['textMuted', 'bgElevated', 7.34, 'AAA'],
    ['textDim', 'bg', 4.13, 'large'],
    ['textDisabled', 'bg', 2.59, 'fail'],
    ['primary', 'bg', 4.64, 'AA'],
    ['primaryText', 'bg', 4.64, 'AA'],
    ['primaryHover', 'bg', 7.22, 'AAA'],
    ['success', 'bg', 7.75, 'AAA'],
    ['warning', 'bg', 9.15, 'AAA'],
    ['danger', 'bg', 5.22, 'AA'],
    ['info', 'bg', 5.34, 'AA'],
    ['accentPink', 'bg', 7.42, 'AAA'],
    ['onPrimary', 'primary', 4.78, 'AA'],
  ],
  light: [
    ['text', 'bg', 18.00, 'AAA'],
    ['textMuted', 'bg', 7.24, 'AAA'],
    ['textDim', 'bg', 4.55, 'AA'],
    ['textDisabled', 'bg', 2.45, 'fail'],
    ['primary', 'bg', 5.45, 'AA'],
    ['primaryText', 'bg', 5.45, 'AA'],
    ['success', 'bg', 3.60, 'large'],
    ['warning', 'bg', 3.04, 'large'],
    ['danger', 'bg', 4.62, 'AA'],
    ['accentGold', 'bg', 2.05, 'fail'],
    ['onPrimary', 'primary', 5.70, 'AA'],
  ],
};

function assertClaim(colors, [fg, bg, claimed, level], label) {
  const ratio = contrast(colors[fg], colors[bg]);
  const tag = `${label}: ${fg} ${colors[fg]} on ${bg} ${colors[bg]} = ${ratio.toFixed(2)}`;
  assert.ok(Math.abs(ratio - claimed) < 0.01, `${tag}, UI_ART_KIT §2.5 claims ${claimed}`);
  if (level === 'fail') assert.ok(ratio < THRESHOLD.large, tag + ' claimed fail');
  else assert.ok(ratio >= THRESHOLD[level], `${tag} below claimed ${level}`);
}

function walkNoUndefined(value, trail, seen = new Set()) {
  assert.notEqual(value, undefined, 'undefined at ' + trail);
  if (value === null || typeof value !== 'object' || seen.has(value)) return;
  seen.add(value);
  for (const [k, v] of Object.entries(value)) walkNoUndefined(v, trail + '.' + k, seen);
}

const load = makeLoader();
const tokens = load('theme/tokens.ts');
const skins = load('theme/skins.ts');
const F = load('theme/foundation/index.ts');

const THEME_KEYS = ['mode', 'isDark', 'skinId', 'statusBarStyle', 'colors', 'status',
  'surfaces', 'gradients', 'type', 'fontFamily', 'hudType', 'spacing', 'breathing',
  'touch', 'hitSlop', 'hudSafeZone', 'radius', 'shadows', 'motion', 'icons'];
const COLOR_KEYS = [...Object.keys(tokens.default.colorModes.dark), 'primaryText'];

test('every §2.5 text/background pair meets its claimed ratio in both modes', () => {
  for (const mode of ['dark', 'light']) {
    const { colors } = F.getTheme(mode);
    for (const claim of CLAIMS[mode]) assertClaim(colors, claim, mode);
  }
});

test('TEXT_USAGE rules agree with measured contrast', () => {
  for (const mode of ['dark', 'light']) {
    const c = F.getTheme(mode).colors;
    for (const [role, usage] of Object.entries(F.TEXT_USAGE[mode])) {
      const r = contrast(c[role], c.bg);
      if (usage === 'body') assert.ok(r >= 4.5, `${mode}.${role} body ${r.toFixed(2)}`);
      if (usage === 'large') assert.ok(r >= 3 && r < 4.5, `${mode}.${role} large ${r.toFixed(2)}`);
      if (usage === 'never') assert.ok(r < 4.5, `${mode}.${role} never ${r.toFixed(2)}`);
    }
  }
});

test('package helper matches the independent WCAG implementation', () => {
  for (const [a, b] of [['#FFFFFF', '#000000'], ['#F8FAFC', '#070B16'], ['#c026d3', '#0b0820']])
    assert.ok(Math.abs(F.contrastRatio(a, b) - contrast(a, b)) < 1e-9);
});

test('getTheme returns every key, no undefined, for both modes and all 30 skins', () => {
  assert.equal(F.SKIN_IDS.length, 30);
  for (const mode of ['dark', 'light']) {
    for (const skinId of [undefined, ...F.SKIN_IDS]) {
      const t = F.getTheme(mode, skinId);
      const label = `${mode}/${skinId ?? 'canonical'}`;
      same(Object.keys(t).sort(), [...THEME_KEYS].sort(), label);
      same(Object.keys(t.colors).sort(), [...COLOR_KEYS].sort(), label);
      for (const k of ['ok', 'warn', 'bad', 'info', 'idle']) assert.ok(t.status[k].glyph, label + ' ' + k);
      for (const lvl of F.ELEVATION_LEVELS) assert.ok(t.surfaces[lvl].backgroundColor, label + ' ' + lvl);
      for (const role of F.TYPE_ROLES) assert.ok(t.type[role].fontSize > 0, label + ' ' + role);
      walkNoUndefined(t, label);
      assert.equal(t.mode, mode);
      assert.equal(t.isDark, mode === 'dark');
      assert.equal(t.skinId, mode === 'dark' && skinId ? skinId : null, label);
      assert.equal(F.getTheme(mode, skinId), t, label + ' memoised');
      assert.ok(Object.isFrozen(t) && Object.isFrozen(t.colors), label + ' frozen');
    }
  }
  walkNoUndefined(F.foundation, 'foundation');
});

test('dark skins: onPrimary, primaryText and text stay AA on every skin', () => {
  for (const id of F.SKIN_IDS) {
    const c = F.getTheme('dark', id).colors;
    const skin = skins.SKIN_BY_ID[id].colors;
    for (const k of Object.keys(skin)) assert.equal(c[k], skin[k], `${id}.${k} from skins.ts`);
    assert.equal(F.ON_PRIMARY_BY_SKIN[id], skin.onPrimary, id);
    assert.ok(contrast(c.onPrimary, c.primary) >= 4.5, id + ' onPrimary');
    assert.ok(contrast(c.text, c.bg) >= 4.5, id + ' text');
    const pt = contrast(c.primaryText, c.bg);
    const p = contrast(c.primary, c.bg);
    assert.ok(pt >= Math.min(p, 4.5) && (p >= 4.5 ? c.primaryText === c.primary : c.primaryText === c.primaryHover), id + ' primaryText');
  }
  // UI_ART_KIT §2.6 named misses use primaryHover for text.
  for (const id of ['hyperwave', 'coffee', 'slate', 'blood', 'cyber', 'royal'])
    assert.equal(F.getTheme('dark', id).colors.primaryText, skins.SKIN_BY_ID[id].colors.primaryHover, id);
});

test('light mode ignores dark skins; unknown skins fall back to canonical', () => {
  same(F.getTheme('light', 'hyperwave').colors, F.getTheme('light').colors);
  assert.equal(F.getTheme('dark', 'no-such-skin').skinId, null);
  assert.equal(F.getTheme('dark', 'no-such-skin').colors.primary, '#8B5CF6');
  assert.equal(F.getTheme('light').statusBarStyle, 'dark');
  assert.equal(F.getTheme('dark').statusBarStyle, 'light');
});

test('canonical colours: true cyan, blue alias and tokens.ts canonical snapshot', () => {
  const fresh = makeLoader()('theme/tokens.ts');
  same(fresh.canonicalColors.dark, fresh.default.colorModes.dark);
  same(fresh.canonicalColors.light, fresh.default.colorModes.light);
  assert.ok(Object.isFrozen(fresh.canonicalColors.dark));
  same(F.getTheme('dark').colors, { ...fresh.default.colorModes.dark, primaryText: fresh.default.colorModes.dark.primary });
  same(F.getTheme('light').colors, { ...fresh.default.colorModes.light, primaryText: fresh.default.colorModes.light.primary });
  assert.equal(F.TRUE_CYAN, '#22D3EE');
  assert.equal(F.getTheme('dark').colors.accentCyan, '#22D3EE');
  assert.equal(F.LEGACY_CYAN_BLUE[400], '#3B82F6');
  assert.equal(F.ramps.blue, tokens.default.palette.blue);
});

test('a skin mutation before import does not leak into the canonical dark theme', () => {
  const l = makeLoader();
  const t = l('theme/tokens.ts');
  const s = l('theme/skins.ts');
  Object.assign(t.default.colors, s.SKIN_BY_ID.hyperwave.colors); // what skinStore does at import
  const f = l('theme/foundation/index.ts');
  assert.equal(f.getTheme('dark').colors.primary, '#8B5CF6');
  assert.equal(f.getTheme('dark').colors.bg, '#070B16');
  assert.equal(f.getTheme('dark', 'hyperwave').colors.primary, '#c026d3');
});

test('status roles pair colour + glyph + shape, colour-blind swap keeps glyphs', () => {
  const t = F.getTheme('dark');
  same(Object.fromEntries(Object.entries(t.status).map(([k, v]) => [k, v.glyph])),
    { ok: '✓', warn: '!', bad: '✕', info: 'i', idle: '○' });
  const forge = load('src/skeletonForge/components/theme.ts');
  for (const k of ['ok', 'warn', 'bad', 'idle'])
    assert.equal(forge.TONE_GLYPH[k], F.STATUS_GLYPH[k], 'TONE_GLYPH parity ' + k);
  assert.equal(t.status.ok.color, t.colors.success);
  assert.equal(t.status.idle.opacity, 0.5);
  const cb = F.getTheme('dark', null, { colorBlind: true });
  assert.equal(cb.status.ok.color, cb.colors.info);
  assert.equal(cb.status.ok.glyph, '✓');
});

test('type, spacing, radius, motion and icons come from tokens.ts and the icon spec', () => {
  assert.equal(F.typeScale.metric, tokens.default.typography.metric);
  assert.equal(F.typeScale.label.fontSize, 12);
  assert.equal(F.hudType.minMovingTextSize, 14);
  assert.equal(F.spacing, tokens.default.spacing);
  assert.equal(F.radius, tokens.default.radii);
  assert.equal(F.touch.min, 44);
  assert.equal(F.duration, tokens.default.motion.duration);
  assert.equal(F.hudMotion.stateIn, 150);
  assert.equal(F.hudMotion.stateOut, 220);
  same(F.ICON_SIZES.map(s => F.ICON_SPEC[s].stroke), [1.5, 1.75, 2, 2.5, 3]);
  assert.equal(F.iconName('hud', 'health', 24), 'ic_hud_health_24');
  assert.equal(F.iconName('hud', 'threat', 32, { filled: true }), 'ic_hud_threat_32_filled');
  assert.equal(F.iconName('status', 'ok', 16), 'ic_status_ok_16');
  assert.ok(F.isIconName('ic_forge_build_20'));
  assert.ok(!F.isIconName('ic_forge_Build_20'));
  assert.ok(!F.isIconName('ic_hud_health_18'));
  assert.throws(() => F.iconName('hud', 'Health', 24));
  assert.throws(() => F.iconName('hud', 'health', 18));
});

test('dark elevation is border-first, light uses shadows (UI_ART_KIT §2.4)', () => {
  const d = F.getTheme('dark').surfaces;
  const l = F.getTheme('light').surfaces;
  for (const lvl of ['card', 'raised', 'selected']) {
    assert.equal(d[lvl].borderWidth, 1, 'dark ' + lvl);
    same(d[lvl].shadow, {}, 'dark ' + lvl + ' no shadow');
  }
  assert.equal(l.card.shadow, F.shadows.xs);
  assert.equal(l.raised.shadow, F.shadows.sm);
  assert.equal(d.modal.scrim, F.getTheme('dark').colors.overlay);
});

test('tokens.ts is the single edit point: no hex literals outside it', () => {
  const files = [
    'theme/skins.ts', 'constants/themes.ts', 'hooks/useTheme.ts',
    'src/theme/deluxe.ts', 'src/skeletonForge/components/theme.ts',
    ...fs.readdirSync(path.join(ROOT, 'theme/foundation'))
      .filter(f => f.endsWith('.ts')).map(f => 'theme/foundation/' + f),
  ];
  for (const relative of files) {
    const file = fs.readFileSync(path.join(ROOT, relative), 'utf8');
    assert.doesNotMatch(file, /#[0-9a-fA-F]{3,8}\b/, relative + ' must read colours from tokens.ts');
  }
});

test('compatibility layers keep their export names and resolve from tokens.ts', () => {
  const l = makeLoader();
  const t = l('theme/tokens.ts');
  const sk = l('theme/skins.ts');
  assert.deepEqual(Object.keys(sk).sort(),
    ['DEFAULT_SKIN', 'SKINS', 'SKIN_BY_ID', 'onPrimaryFor', 'primaryTint'].sort());
  assert.equal(sk.DEFAULT_SKIN, t.DEFAULT_SKIN_ID);
  assert.equal(sk.SKINS.length, t.skinPalettes.length);
  sk.SKINS.forEach((skin, i) => {
    const [id, name, emoji, bg, bg2, primary, hover, cyan, pink, gold] = t.skinPalettes[i];
    same([skin.id, skin.name, skin.emoji], [id, name, emoji]);
    same(skin.colors, {
      bg, bgElevated: bg2, bgSubtle: bg2, primary, onPrimary: sk.onPrimaryFor(primary),
      primaryHover: hover, primarySoft: sk.primaryTint(primary), borderFocus: primary,
      accentCyan: cyan, accentPink: pink, accentGold: gold,
    }, id);
  });
  const deluxe = l('src/theme/deluxe.ts');
  assert.equal(deluxe.glow, t.default.elevation.glow);
  assert.deepEqual(Object.keys(deluxe.default).sort(), ['C', 'R', 'S', 'T', 'card', 'cardActive', 'glow']);
  // skinStore-style mutation still drives the live legacy palette.
  Object.assign(t.default.colors, sk.SKIN_BY_ID.ember.colors);
  assert.equal(deluxe.C.brand, sk.SKIN_BY_ID.ember.colors.primary);
  assert.equal(t.canonicalColors.dark.primary, t.default.palette.brand[500]);
});

test('lint:ci guard: no named export duplicates a default-object binding (import/no-named-as-default-member)', () => {
  const t = makeLoader()('theme/tokens.ts');
  const named = Object.keys(t).filter(k => k !== 'default' && k !== '__esModule');
  const dup = named.filter(k => Object.prototype.hasOwnProperty.call(t.default, k));
  assert.deepEqual(dup, [], 'tokens.ts named exports also on default: ' + dup.join(', '));
  for (const k of ['colors', 'colorModes', 'palette', 'spacing', 'radii', 'typography', 'elevation', 'motion', 'gradients', 'hitSlop', 'breathing'])
    assert.ok(t.default[k], 'default.' + k);
});
