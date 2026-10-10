import test from 'node:test';
import assert from 'node:assert/strict';
import Module, { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import ts from 'typescript';

const root = resolve(import.meta.dirname, '..');
const runtimePath = resolve(root, 'src/accessibility/runtime.ts');
const runtimeSource = readFileSync(runtimePath, 'utf8');
const compiled = ts.transpileModule(runtimeSource, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
    strict: true,
  },
  fileName: runtimePath,
});
const localRequire = createRequire(import.meta.url);
const runtimeModule = new Module(runtimePath);
runtimeModule.filename = runtimePath;
runtimeModule.paths = Module._nodeModulePaths(root);
runtimeModule.require = localRequire;
runtimeModule._compile(compiled.outputText, runtimePath);
const a11y = runtimeModule.exports;

function source(path) {
  return readFileSync(resolve(root, path), 'utf8');
}

test('critical acceptance snapshot passes with no findings', () => {
  const report = a11y.assertCriticalAccessibilityAcceptance();
  assert.equal(report.passed, true);
  assert.equal(report.criticalPassed, true);
  assert.equal(report.findingCount, 0);
});

test('critical control fails keyboard, touch, text and screen-reader requirements', () => {
  const bad = {
    id: 'bad.control',
    flow: 'critical',
    role: 'none',
    label: 'Broken',
    critical: true,
    screenReaderReachable: false,
    keyboardReachable: false,
    keyboardActivatable: false,
    minimumTouchTarget: 20,
    hasTextSignal: false,
    supportsTextScaling: false,
  };
  const findings = a11y.validateAccessibleControl(bad);
  assert.ok(findings.some((item) => item.requirementId === 'A11Y.KEYBOARD.CRITICAL'));
  assert.ok(findings.some((item) => item.requirementId === 'A11Y.TOUCH.MINIMUM_44'));
  assert.ok(findings.some((item) => item.requirementId === 'A11Y.SCREEN_READER.NAME_ROLE'));
  assert.ok(findings.some((item) => item.requirementId === 'A11Y.NON_COLOR.SIGNAL'));
  assert.ok(findings.some((item) => item.requirementId === 'A11Y.TEXT.SCALE'));
});

test('modal control must declare modal accessibility context', () => {
  const findings = a11y.validateAccessibleControl({
    id: 'modal.control',
    flow: 'modal',
    role: 'button',
    label: 'Confirm',
    critical: true,
    screenReaderReachable: true,
    keyboardReachable: true,
    keyboardActivatable: true,
    minimumTouchTarget: 48,
    hasTextSignal: true,
    supportsTextScaling: true,
    modalContext: false,
  });
  assert.deepEqual(
    findings.map((item) => item.requirementId),
    ['A11Y.MODAL.CONTAINMENT'],
  );
});

test('critical status must use live region and text signal', () => {
  const findings = a11y.validateAccessibleStatus({
    id: 'status.bad',
    flow: 'status',
    message: 'Something changed.',
    role: 'alert',
    liveRegion: 'none',
    critical: true,
    hasTextSignal: false,
    supportsTextScaling: false,
  });
  assert.ok(findings.some((item) => item.requirementId === 'A11Y.STATUS.LIVE_TEXT'));
  assert.ok(findings.some((item) => item.requirementId === 'A11Y.NON_COLOR.SIGNAL'));
  assert.ok(findings.some((item) => item.requirementId === 'A11Y.TEXT.SCALE'));
});

test('reduced motion requires immediate non-essential transition', () => {
  const findings = a11y.validateAccessibleMotion({
    id: 'motion.bad',
    flow: 'modal',
    animated: true,
    essential: false,
    reduceMotionHonored: true,
    defaultDurationMs: 200,
    reducedDurationMs: 50,
  });
  assert.equal(findings.length, 1);
  assert.equal(findings[0].requirementId, 'A11Y.MOTION.REDUCE');
  assert.equal(a11y.reducedMotionDuration(true, 200), 0);
  assert.equal(a11y.reducedMotionDuration(false, 200), 200);
});

test('missing critical inventory entry fails acceptance', () => {
  const snapshot = {
    ...a11y.CRITICAL_ACCESSIBILITY_SNAPSHOT,
    controls: a11y.CRITICAL_ACCESSIBILITY_SNAPSHOT.controls.filter(
      (item) => item.id !== 'boot.safe_mode',
    ),
  };
  const report = a11y.evaluateAccessibilityAcceptance(snapshot);
  assert.equal(report.criticalPassed, false);
  assert.ok(report.findings.some((item) => item.subjectId === 'boot.safe_mode'));
});

test('duplicate semantic identity fails acceptance', () => {
  const first = a11y.CRITICAL_ACCESSIBILITY_SNAPSHOT.controls[0];
  const snapshot = {
    ...a11y.CRITICAL_ACCESSIBILITY_SNAPSHOT,
    controls: [...a11y.CRITICAL_ACCESSIBILITY_SNAPSHOT.controls, first],
  };
  const report = a11y.evaluateAccessibilityAcceptance(snapshot);
  assert.equal(report.criticalPassed, false);
  assert.ok(report.findings.some((item) => item.code === 'A11Y.IDENTITY.DUPLICATE'));
});

test('accessible button helper emits explicit role/name/focusability', () => {
  const props = a11y.accessibleButtonProps('Cancel operation', {
    hint: 'Stops the active operation.',
  });
  assert.deepEqual(props, {
    accessible: true,
    accessibilityRole: 'button',
    accessibilityLabel: 'Cancel operation',
    accessibilityHint: 'Stops the active operation.',
    focusable: true,
  });
});

test('progress status helper validates bounds', () => {
  const props = a11y.accessibleStatusProps('Startup progress: 50 percent', {
    progress: { min: 0, max: 100, now: 50, text: '50 percent' },
  });
  assert.equal(props.accessibilityRole, 'progressbar');
  assert.equal(props.accessibilityValue.now, 50);
  assert.throws(
    () => a11y.accessibleStatusProps('Bad', {
      progress: { min: 0, max: 100, now: 101 },
    }),
    /invalid/,
  );
});

test('ActionSheet exposes modal semantics, accessible buttons and reduced motion', () => {
  const content = source('components/ActionSheet.tsx');
  assert.match(content, /accessibilityViewIsModal/);
  assert.match(content, /accessibleButtonProps/);
  assert.match(content, /useReduceMotion/);
  assert.match(content, /minHeight: 48/);
});

test('Toast exposes live status without swallowing child controls', () => {
  const content = source('components/Toast.tsx');
  assert.match(content, /accessibleStatusProps/);
  assert.match(content, /accessibleButtonProps\('Dismiss notification'\)/);
  assert.match(content, /minWidth: 44/);
  assert.match(content, /minHeight: 44/);
  assert.match(content, /useReduceMotion/);
  assert.doesNotMatch(
    content,
    /<Animated\.View[\s\S]{0,220}\{\.\.\.accessibleStatusProps/,
  );
});

test('StabilityBanner exposes textual assertive connectivity semantics', () => {
  const content = source('src/components/StabilityBanner.tsx');
  assert.match(content, /accessibleStatusProps/);
  assert.match(content, /Connectivity status:/);
  assert.match(content, /variant === 'offline' \|\| variant === 'down'/);
  assert.match(content, /useReduceMotion/);
});

test('BootLauncher exposes progress, failure, recovery and single reduce-motion source', () => {
  const content = source('components/BootLauncher.tsx');
  assert.match(content, /useReduceMotion/);
  assert.match(content, /accessibleStatusProps/);
  assert.match(content, /Startup progress:/);
  assert.match(content, /Boot failed\./);
  assert.match(content, /accessibleButtonProps\('Retry boot'\)/);
  assert.match(content, /accessibleButtonProps\('Open Safe Mode'\)/);
  assert.doesNotMatch(content, /AccessibilityInfo\.isReduceMotionEnabled/);
});

test('LaunchCascade exposes named fallback controls and startup status', () => {
  const content = source('components/LaunchCascade.tsx');
  assert.match(content, /accessibleButtonProps\('Open Skeleton'\)/);
  assert.match(content, /accessibleButtonProps\('Open Safe Mode'\)/);
  assert.match(content, /accessibleStatusProps\('Starting Skeleton'\)/);
  assert.match(content, /minHeight: 44/);
});


test('Entry route announces startup safety status before launcher mounts', () => {
  const content = source('app/index.tsx');
  assert.match(content, /accessibleStatusProps\('Checking startup safety'\)/);
  assert.match(content, /accessibilityElementsHidden/);
});


test('contrast evaluation measures critical foreground/background pairs', () => {
  assert.equal(Math.round(a11y.contrastRatio('#000000', '#FFFFFF') * 10) / 10, 21);
  const findings = a11y.validateAccessibleContrast({
    id: 'contrast.bad',
    flow: 'critical',
    foreground: '#777777',
    background: '#888888',
    largeText: false,
    critical: true,
  });
  assert.equal(findings.length, 1);
  assert.equal(findings[0].requirementId, 'A11Y.CONTRAST.TEXT');
});

test('default critical contrast inventory is complete and passing', () => {
  const report = a11y.evaluateAccessibilityAcceptance(
    a11y.CRITICAL_ACCESSIBILITY_SNAPSHOT,
  );
  assert.equal(report.criticalPassed, true);
  assert.ok(report.evaluatedContrastIds.includes('boot.primary'));
  assert.ok(report.evaluatedContrastIds.includes('connectivity.offline'));
  assert.ok(report.evaluatedContrastIds.includes('toast.error'));
});
