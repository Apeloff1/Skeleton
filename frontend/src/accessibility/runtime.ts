/**
 * VOL-086 canonical accessibility acceptance/runtime contracts.
 *
 * Framework-light on purpose: the same semantics are consumed by React Native
 * and evaluated by Node contract tests. Accessibility is represented as
 * observable behavior, never inferred from color or decoration.
 */

export type AccessibilitySeverity = 'critical' | 'error' | 'warning';
export type AccessibilityRequirementCategory =
  | 'keyboard'
  | 'screen_reader'
  | 'touch_target'
  | 'status'
  | 'non_color_signal'
  | 'motion'
  | 'text_scaling'
  | 'contrast'
  | 'modal';
export type AccessibilityRole =
  | 'button'
  | 'link'
  | 'alert'
  | 'text'
  | 'progressbar'
  | 'adjustable'
  | 'menuitem'
  | 'none';
export type AccessibilityLiveRegion = 'none' | 'polite' | 'assertive';

export interface AccessibilityRequirement {
  id: string;
  category: AccessibilityRequirementCategory;
  description: string;
  critical: boolean;
}

export interface AccessibleControl {
  id: string;
  flow: string;
  role: AccessibilityRole;
  label: string;
  hint?: string;
  critical: boolean;
  screenReaderReachable: boolean;
  keyboardReachable: boolean;
  keyboardActivatable: boolean;
  minimumTouchTarget: number;
  hasTextSignal: boolean;
  supportsTextScaling: boolean;
  modalContext?: boolean;
  disabled?: boolean;
}

export interface AccessibleStatus {
  id: string;
  flow: string;
  message: string;
  role: 'alert' | 'text' | 'progressbar';
  liveRegion: AccessibilityLiveRegion;
  critical: boolean;
  hasTextSignal: boolean;
  supportsTextScaling: boolean;
}

export interface AccessibleMotion {
  id: string;
  flow: string;
  animated: boolean;
  essential: boolean;
  reduceMotionHonored: boolean;
  defaultDurationMs: number;
  reducedDurationMs: number;
}

export interface AccessibleContrast {
  id: string;
  flow: string;
  foreground: string;
  background: string;
  largeText: boolean;
  critical: boolean;
}

export interface AccessibilityFinding {
  code: string;
  requirementId: string;
  severity: AccessibilitySeverity;
  subjectId: string;
  message: string;
}

export interface AccessibilityAcceptanceMatrix {
  version: 1;
  minimumTouchTarget: number;
  requirements: readonly AccessibilityRequirement[];
  requiredControlIds: readonly string[];
  requiredStatusIds: readonly string[];
  requiredMotionIds: readonly string[];
  requiredContrastIds: readonly string[];
}

export interface AccessibilitySnapshot {
  controls: readonly AccessibleControl[];
  statuses: readonly AccessibleStatus[];
  motions: readonly AccessibleMotion[];
  contrasts: readonly AccessibleContrast[];
}

export interface AccessibilityAcceptanceReport {
  passed: boolean;
  criticalPassed: boolean;
  findingCount: number;
  criticalFindingCount: number;
  findings: readonly AccessibilityFinding[];
  evaluatedControlIds: readonly string[];
  evaluatedStatusIds: readonly string[];
  evaluatedMotionIds: readonly string[];
  evaluatedContrastIds: readonly string[];
}

const TOKEN = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,191}$/;

function token(value: string, field: string): string {
  if (typeof value !== 'string' || !TOKEN.test(value)) {
    throw new TypeError(field + ' must be a canonical token');
  }
  return value;
}

function text(value: string, field: string, max = 512): string {
  if (typeof value !== 'string') throw new TypeError(field + ' must be text');
  if (value !== value.trim() || value.length === 0 || value.length > max) {
    throw new TypeError(field + ' must be normalized bounded text');
  }
  return value;
}

function finiteNonNegative(value: number, field: string): number {
  if (!Number.isFinite(value) || value < 0) {
    throw new TypeError(field + ' must be finite and non-negative');
  }
  return value;
}

function freezeRequirement(
  requirement: AccessibilityRequirement,
): AccessibilityRequirement {
  return Object.freeze({
    id: token(requirement.id, 'requirement.id'),
    category: requirement.category,
    description: text(requirement.description, 'requirement.description', 1024),
    critical: Boolean(requirement.critical),
  });
}

export const ACCESSIBILITY_REQUIREMENTS: readonly AccessibilityRequirement[] =
  Object.freeze([
    freezeRequirement({
      id: 'A11Y.KEYBOARD.CRITICAL',
      category: 'keyboard',
      description:
        'Every critical interactive control is keyboard reachable and keyboard activatable.',
      critical: true,
    }),
    freezeRequirement({
      id: 'A11Y.SCREEN_READER.NAME_ROLE',
      category: 'screen_reader',
      description:
        'Every critical control exposes an explicit semantic role and accessible name.',
      critical: true,
    }),
    freezeRequirement({
      id: 'A11Y.TOUCH.MINIMUM_44',
      category: 'touch_target',
      description:
        'Critical touch controls expose at least a 44 logical-pixel target.',
      critical: true,
    }),
    freezeRequirement({
      id: 'A11Y.STATUS.LIVE_TEXT',
      category: 'status',
      description:
        'Critical asynchronous status is announced semantically and contains meaningful text.',
      critical: true,
    }),
    freezeRequirement({
      id: 'A11Y.NON_COLOR.SIGNAL',
      category: 'non_color_signal',
      description:
        'Critical state and errors are not communicated by color alone.',
      critical: true,
    }),
    freezeRequirement({
      id: 'A11Y.MOTION.REDUCE',
      category: 'motion',
      description:
        'Non-essential animation honors the operating-system reduced-motion preference.',
      critical: true,
    }),
    freezeRequirement({
      id: 'A11Y.CONTRAST.TEXT',
      category: 'contrast',
      description:
        'Critical text and status surfaces meet measurable foreground/background contrast.',
      critical: true,
    }),
    freezeRequirement({
      id: 'A11Y.TEXT.SCALE',
      category: 'text_scaling',
      description:
        'Critical controls and statuses permit platform text scaling.',
      critical: true,
    }),
    freezeRequirement({
      id: 'A11Y.MODAL.CONTAINMENT',
      category: 'modal',
      description:
        'Critical modal surfaces expose modal semantics and keep their controls screen-reader reachable.',
      critical: true,
    }),
  ]);

export const DEFAULT_ACCESSIBILITY_MATRIX: AccessibilityAcceptanceMatrix =
  Object.freeze({
    version: 1,
    minimumTouchTarget: 44,
    requirements: ACCESSIBILITY_REQUIREMENTS,
    requiredControlIds: Object.freeze([
      'actionsheet.cancel',
      'actionsheet.destructive',
      'boot.continue',
      'boot.enter',
      'boot.retry',
      'boot.safe_mode',
      'launcher.enter',
      'launcher.safe_mode',
      'toast.action',
      'toast.dismiss',
    ]),
    requiredStatusIds: Object.freeze([
      'boot.progress',
      'boot.failure',
      'connectivity.status',
      'toast.status',
    ]),
    requiredMotionIds: Object.freeze([
      'actionsheet.motion',
      'boot.motion',
      'connectivity.motion',
      'toast.motion',
    ]),
    requiredContrastIds: Object.freeze([
      'actionsheet.default',
      'boot.primary',
      'connectivity.degraded',
      'connectivity.down',
      'connectivity.offline',
      'toast.error',
      'toast.info',
    ]),
  });

function requirementById(
  matrix: AccessibilityAcceptanceMatrix,
  id: string,
): AccessibilityRequirement {
  const requirement = matrix.requirements.find((item) => item.id === id);
  if (!requirement) {
    throw new TypeError('unknown accessibility requirement ' + id);
  }
  return requirement;
}

function finding(
  matrix: AccessibilityAcceptanceMatrix,
  requirementId: string,
  subjectId: string,
  message: string,
): AccessibilityFinding {
  const requirement = requirementById(matrix, requirementId);
  return Object.freeze({
    code: requirementId,
    requirementId,
    severity: requirement.critical ? 'critical' : 'error',
    subjectId: token(subjectId, 'finding.subjectId'),
    message: text(message, 'finding.message', 1024),
  });
}

export function defineAccessibleControl(
  control: AccessibleControl,
): AccessibleControl {
  return Object.freeze({
    id: token(control.id, 'control.id'),
    flow: token(control.flow, 'control.flow'),
    role: control.role,
    label: text(control.label, 'control.label'),
    hint: control.hint ? text(control.hint, 'control.hint', 1024) : undefined,
    critical: Boolean(control.critical),
    screenReaderReachable: Boolean(control.screenReaderReachable),
    keyboardReachable: Boolean(control.keyboardReachable),
    keyboardActivatable: Boolean(control.keyboardActivatable),
    minimumTouchTarget: finiteNonNegative(
      control.minimumTouchTarget,
      'control.minimumTouchTarget',
    ),
    hasTextSignal: Boolean(control.hasTextSignal),
    supportsTextScaling: Boolean(control.supportsTextScaling),
    modalContext:
      control.modalContext === undefined ? undefined : Boolean(control.modalContext),
    disabled: control.disabled === undefined ? undefined : Boolean(control.disabled),
  });
}

export function defineAccessibleStatus(status: AccessibleStatus): AccessibleStatus {
  return Object.freeze({
    id: token(status.id, 'status.id'),
    flow: token(status.flow, 'status.flow'),
    message: text(status.message, 'status.message', 2048),
    role: status.role,
    liveRegion: status.liveRegion,
    critical: Boolean(status.critical),
    hasTextSignal: Boolean(status.hasTextSignal),
    supportsTextScaling: Boolean(status.supportsTextScaling),
  });
}

export function defineAccessibleMotion(motion: AccessibleMotion): AccessibleMotion {
  const normalized: AccessibleMotion = {
    id: token(motion.id, 'motion.id'),
    flow: token(motion.flow, 'motion.flow'),
    animated: Boolean(motion.animated),
    essential: Boolean(motion.essential),
    reduceMotionHonored: Boolean(motion.reduceMotionHonored),
    defaultDurationMs: finiteNonNegative(
      motion.defaultDurationMs,
      'motion.defaultDurationMs',
    ),
    reducedDurationMs: finiteNonNegative(
      motion.reducedDurationMs,
      'motion.reducedDurationMs',
    ),
  };
  if (
    normalized.reduceMotionHonored &&
    normalized.reducedDurationMs > normalized.defaultDurationMs
  ) {
    throw new TypeError(
      'reducedDurationMs cannot exceed defaultDurationMs when reduced motion is honored',
    );
  }
  return Object.freeze(normalized);
}


function hexChannel(value: string, offset: number): number {
  return parseInt(value.slice(offset, offset + 2), 16) / 255;
}

function relativeLuminance(hex: string): number {
  if (!/^#[0-9a-fA-F]{6}$/.test(hex)) {
    throw new TypeError('contrast colors must be #RRGGBB hex values');
  }
  const linear = [1, 3, 5].map((offset) => {
    const channel = hexChannel(hex, offset);
    return channel <= 0.04045
      ? channel / 12.92
      : Math.pow((channel + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

export function contrastRatio(foreground: string, background: string): number {
  const first = relativeLuminance(foreground);
  const second = relativeLuminance(background);
  const high = Math.max(first, second);
  const low = Math.min(first, second);
  return (high + 0.05) / (low + 0.05);
}

export function defineAccessibleContrast(
  contrast: AccessibleContrast,
): AccessibleContrast {
  contrastRatio(contrast.foreground, contrast.background);
  return Object.freeze({
    id: token(contrast.id, 'contrast.id'),
    flow: token(contrast.flow, 'contrast.flow'),
    foreground: contrast.foreground.toUpperCase(),
    background: contrast.background.toUpperCase(),
    largeText: Boolean(contrast.largeText),
    critical: Boolean(contrast.critical),
  });
}

export function validateAccessibleContrast(
  contrast: AccessibleContrast,
  matrix: AccessibilityAcceptanceMatrix = DEFAULT_ACCESSIBILITY_MATRIX,
): readonly AccessibilityFinding[] {
  const item = defineAccessibleContrast(contrast);
  const ratio = contrastRatio(item.foreground, item.background);
  const minimum = item.largeText ? 3 : 4.5;
  if (item.critical && ratio < minimum) {
    return Object.freeze([
      finding(
        matrix,
        'A11Y.CONTRAST.TEXT',
        item.id,
        'Critical foreground/background contrast is below the required ratio.',
      ),
    ]);
  }
  return Object.freeze([]);
}

export function validateAccessibleControl(
  control: AccessibleControl,
  matrix: AccessibilityAcceptanceMatrix = DEFAULT_ACCESSIBILITY_MATRIX,
): readonly AccessibilityFinding[] {
  const item = defineAccessibleControl(control);
  const findings: AccessibilityFinding[] = [];

  if (item.critical && (!item.screenReaderReachable || item.role === 'none')) {
    findings.push(
      finding(
        matrix,
        'A11Y.SCREEN_READER.NAME_ROLE',
        item.id,
        'Critical control lacks an explicit reachable semantic role and accessible name.',
      ),
    );
  }
  if (item.critical && (!item.keyboardReachable || !item.keyboardActivatable)) {
    findings.push(
      finding(
        matrix,
        'A11Y.KEYBOARD.CRITICAL',
        item.id,
        'Critical control is not both keyboard reachable and keyboard activatable.',
      ),
    );
  }
  if (item.critical && item.minimumTouchTarget < matrix.minimumTouchTarget) {
    findings.push(
      finding(
        matrix,
        'A11Y.TOUCH.MINIMUM_44',
        item.id,
        'Critical control touch target is below the configured minimum.',
      ),
    );
  }
  if (item.critical && !item.hasTextSignal) {
    findings.push(
      finding(
        matrix,
        'A11Y.NON_COLOR.SIGNAL',
        item.id,
        'Critical control or state meaning is not represented in text.',
      ),
    );
  }
  if (item.critical && !item.supportsTextScaling) {
    findings.push(
      finding(
        matrix,
        'A11Y.TEXT.SCALE',
        item.id,
        'Critical control does not permit platform text scaling.',
      ),
    );
  }
  if (item.flow === 'modal' && item.modalContext !== true) {
    findings.push(
      finding(
        matrix,
        'A11Y.MODAL.CONTAINMENT',
        item.id,
        'Modal control is not declared inside a modal accessibility context.',
      ),
    );
  }
  return Object.freeze(findings);
}

export function validateAccessibleStatus(
  status: AccessibleStatus,
  matrix: AccessibilityAcceptanceMatrix = DEFAULT_ACCESSIBILITY_MATRIX,
): readonly AccessibilityFinding[] {
  const item = defineAccessibleStatus(status);
  const findings: AccessibilityFinding[] = [];
  if (item.critical && item.liveRegion === 'none') {
    findings.push(
      finding(
        matrix,
        'A11Y.STATUS.LIVE_TEXT',
        item.id,
        'Critical asynchronous status is not announced through a live region.',
      ),
    );
  }
  if (item.critical && !item.hasTextSignal) {
    findings.push(
      finding(
        matrix,
        'A11Y.NON_COLOR.SIGNAL',
        item.id,
        'Critical status relies on a non-text signal.',
      ),
    );
  }
  if (item.critical && !item.supportsTextScaling) {
    findings.push(
      finding(
        matrix,
        'A11Y.TEXT.SCALE',
        item.id,
        'Critical status does not permit platform text scaling.',
      ),
    );
  }
  return Object.freeze(findings);
}

export function validateAccessibleMotion(
  motion: AccessibleMotion,
  matrix: AccessibilityAcceptanceMatrix = DEFAULT_ACCESSIBILITY_MATRIX,
): readonly AccessibilityFinding[] {
  const item = defineAccessibleMotion(motion);
  if (!item.animated || item.essential) return Object.freeze([]);
  if (!item.reduceMotionHonored || item.reducedDurationMs !== 0) {
    return Object.freeze([
      finding(
        matrix,
        'A11Y.MOTION.REDUCE',
        item.id,
        'Non-essential animation must resolve immediately when reduced motion is enabled.',
      ),
    ]);
  }
  return Object.freeze([]);
}

function duplicateFindings(
  kind: 'control' | 'status' | 'motion' | 'contrast',
  values: readonly { id: string }[],
): AccessibilityFinding[] {
  const seen = new Set<string>();
  const findings: AccessibilityFinding[] = [];
  for (const value of values) {
    if (seen.has(value.id)) {
      findings.push(
        Object.freeze({
          code: 'A11Y.IDENTITY.DUPLICATE',
          requirementId: 'A11Y.SCREEN_READER.NAME_ROLE',
          severity: 'critical' as const,
          subjectId: value.id,
          message: 'Duplicate ' + kind + ' accessibility identity.',
        }),
      );
    }
    seen.add(value.id);
  }
  return findings;
}

function missingRequiredFindings(
  matrix: AccessibilityAcceptanceMatrix,
  kind: 'control' | 'status' | 'motion' | 'contrast',
  required: readonly string[],
  present: ReadonlySet<string>,
): AccessibilityFinding[] {
  const requirementId =
    kind === 'control'
      ? 'A11Y.KEYBOARD.CRITICAL'
      : kind === 'status'
        ? 'A11Y.STATUS.LIVE_TEXT'
        : kind === 'motion'
          ? 'A11Y.MOTION.REDUCE'
          : 'A11Y.CONTRAST.TEXT';
  return [...new Set(required)]
    .sort()
    .filter((id) => !present.has(id))
    .map((id) =>
      finding(
        matrix,
        requirementId,
        id,
        'Required critical ' + kind + ' is missing from accessibility acceptance inventory.',
      ),
    );
}

export function evaluateAccessibilityAcceptance(
  snapshot: AccessibilitySnapshot,
  matrix: AccessibilityAcceptanceMatrix = DEFAULT_ACCESSIBILITY_MATRIX,
): AccessibilityAcceptanceReport {
  if (!snapshot || typeof snapshot !== 'object') {
    throw new TypeError('snapshot must be an accessibility snapshot');
  }

  const controls = snapshot.controls.map(defineAccessibleControl);
  const statuses = snapshot.statuses.map(defineAccessibleStatus);
  const motions = snapshot.motions.map(defineAccessibleMotion);
  const contrasts = snapshot.contrasts.map(defineAccessibleContrast);
  const findings: AccessibilityFinding[] = [
    ...duplicateFindings('control', controls),
    ...duplicateFindings('status', statuses),
    ...duplicateFindings('motion', motions),
    ...duplicateFindings('contrast', contrasts),
  ];

  controls.forEach((item) => findings.push(...validateAccessibleControl(item, matrix)));
  statuses.forEach((item) => findings.push(...validateAccessibleStatus(item, matrix)));
  motions.forEach((item) => findings.push(...validateAccessibleMotion(item, matrix)));
  contrasts.forEach((item) => findings.push(...validateAccessibleContrast(item, matrix)));

  const controlIds = new Set(controls.map((item) => item.id));
  const statusIds = new Set(statuses.map((item) => item.id));
  const motionIds = new Set(motions.map((item) => item.id));
  const contrastIds = new Set(contrasts.map((item) => item.id));

  findings.push(
    ...missingRequiredFindings(
      matrix,
      'control',
      matrix.requiredControlIds,
      controlIds,
    ),
    ...missingRequiredFindings(
      matrix,
      'status',
      matrix.requiredStatusIds,
      statusIds,
    ),
    ...missingRequiredFindings(
      matrix,
      'motion',
      matrix.requiredMotionIds,
      motionIds,
    ),
    ...missingRequiredFindings(
      matrix,
      'contrast',
      matrix.requiredContrastIds,
      contrastIds,
    ),
  );

  findings.sort((left, right) =>
    left.severity.localeCompare(right.severity) ||
    left.requirementId.localeCompare(right.requirementId) ||
    left.subjectId.localeCompare(right.subjectId) ||
    left.message.localeCompare(right.message),
  );

  const criticalFindingCount = findings.filter(
    (item) => item.severity === 'critical',
  ).length;

  return Object.freeze({
    passed: findings.length === 0,
    criticalPassed: criticalFindingCount === 0,
    findingCount: findings.length,
    criticalFindingCount,
    findings: Object.freeze(findings),
    evaluatedControlIds: Object.freeze([...controlIds].sort()),
    evaluatedStatusIds: Object.freeze([...statusIds].sort()),
    evaluatedMotionIds: Object.freeze([...motionIds].sort()),
    evaluatedContrastIds: Object.freeze([...contrastIds].sort()),
  });
}

export interface AccessiblePressableProps {
  accessible: true;
  accessibilityRole: 'button';
  accessibilityLabel: string;
  accessibilityHint?: string;
  accessibilityState?: { disabled: boolean };
  focusable: true;
}

export function accessibleButtonProps(
  label: string,
  options: { hint?: string; disabled?: boolean } = {},
): AccessiblePressableProps {
  const props: AccessiblePressableProps = {
    accessible: true,
    accessibilityRole: 'button',
    accessibilityLabel: text(label, 'accessibilityLabel'),
    focusable: true,
  };
  if (options.hint) {
    props.accessibilityHint = text(options.hint, 'accessibilityHint', 1024);
  }
  if (options.disabled !== undefined) {
    props.accessibilityState = { disabled: Boolean(options.disabled) };
  }
  return props;
}

export interface AccessibleStatusProps {
  accessible: true;
  accessibilityRole: 'alert' | 'progressbar';
  accessibilityLabel: string;
  accessibilityLiveRegion: 'polite' | 'assertive';
}

export function accessibleStatusProps(
  label: string,
  options: {
    assertive?: boolean;
    progress?: { min: number; max: number; now: number; text?: string };
  } = {},
): AccessibleStatusProps & {
  accessibilityValue?: {
    min: number;
    max: number;
    now: number;
    text?: string;
  };
} {
  const result: AccessibleStatusProps & {
    accessibilityValue?: {
      min: number;
      max: number;
      now: number;
      text?: string;
    };
  } = {
    accessible: true,
    accessibilityRole: options.progress ? 'progressbar' : 'alert',
    accessibilityLabel: text(label, 'accessibilityLabel', 2048),
    accessibilityLiveRegion: options.assertive ? 'assertive' : 'polite',
  };
  if (options.progress) {
    const progress = options.progress;
    if (
      ![progress.min, progress.max, progress.now].every(Number.isFinite) ||
      progress.max <= progress.min ||
      progress.now < progress.min ||
      progress.now > progress.max
    ) {
      throw new TypeError('progress accessibility value is invalid');
    }
    result.accessibilityValue = {
      min: progress.min,
      max: progress.max,
      now: progress.now,
      text: progress.text,
    };
  }
  return result;
}

export function reducedMotionDuration(
  reduceMotion: boolean,
  defaultDurationMs: number,
): number {
  finiteNonNegative(defaultDurationMs, 'defaultDurationMs');
  return reduceMotion ? 0 : defaultDurationMs;
}

const commonControl = {
  critical: true,
  screenReaderReachable: true,
  keyboardReachable: true,
  keyboardActivatable: true,
  hasTextSignal: true,
  supportsTextScaling: true,
} as const;

export const CRITICAL_ACCESSIBILITY_SNAPSHOT: AccessibilitySnapshot =
  Object.freeze({
    controls: Object.freeze([
      defineAccessibleControl({
        ...commonControl,
        id: 'launcher.enter',
        flow: 'launcher',
        role: 'button',
        label: 'Open Skeleton',
        minimumTouchTarget: 52,
      }),
      defineAccessibleControl({
        ...commonControl,
        id: 'launcher.safe_mode',
        flow: 'launcher',
        role: 'button',
        label: 'Open Safe Mode',
        minimumTouchTarget: 48,
      }),
      defineAccessibleControl({
        ...commonControl,
        id: 'boot.enter',
        flow: 'boot',
        role: 'button',
        label: 'Enter Product',
        minimumTouchTarget: 52,
      }),
      defineAccessibleControl({
        ...commonControl,
        id: 'boot.retry',
        flow: 'boot',
        role: 'button',
        label: 'Retry boot',
        minimumTouchTarget: 52,
      }),
      defineAccessibleControl({
        ...commonControl,
        id: 'boot.continue',
        flow: 'boot',
        role: 'button',
        label: 'Continue anyway',
        minimumTouchTarget: 46,
      }),
      defineAccessibleControl({
        ...commonControl,
        id: 'boot.safe_mode',
        flow: 'boot',
        role: 'button',
        label: 'Open Safe Mode',
        minimumTouchTarget: 46,
      }),
      defineAccessibleControl({
        ...commonControl,
        id: 'actionsheet.cancel',
        flow: 'modal',
        role: 'button',
        label: 'Cancel',
        minimumTouchTarget: 48,
        modalContext: true,
      }),
      defineAccessibleControl({
        ...commonControl,
        id: 'actionsheet.destructive',
        flow: 'modal',
        role: 'button',
        label: 'Confirm destructive action',
        hint: 'Activates an irreversible or high-impact action.',
        minimumTouchTarget: 48,
        modalContext: true,
      }),
      defineAccessibleControl({
        ...commonControl,
        id: 'toast.action',
        flow: 'notification',
        role: 'button',
        label: 'Notification action',
        minimumTouchTarget: 44,
      }),
      defineAccessibleControl({
        ...commonControl,
        id: 'toast.dismiss',
        flow: 'notification',
        role: 'button',
        label: 'Dismiss notification',
        minimumTouchTarget: 44,
      }),
    ]),
    statuses: Object.freeze([
      defineAccessibleStatus({
        id: 'boot.progress',
        flow: 'boot',
        message: 'Startup progress is announced with a numeric percentage.',
        role: 'progressbar',
        liveRegion: 'polite',
        critical: true,
        hasTextSignal: true,
        supportsTextScaling: true,
      }),
      defineAccessibleStatus({
        id: 'boot.failure',
        flow: 'boot',
        message: 'Boot failure includes explicit text and recovery actions.',
        role: 'alert',
        liveRegion: 'assertive',
        critical: true,
        hasTextSignal: true,
        supportsTextScaling: true,
      }),
      defineAccessibleStatus({
        id: 'connectivity.status',
        flow: 'connectivity',
        message: 'Connectivity degradation is announced in text.',
        role: 'alert',
        liveRegion: 'assertive',
        critical: true,
        hasTextSignal: true,
        supportsTextScaling: true,
      }),
      defineAccessibleStatus({
        id: 'toast.status',
        flow: 'notification',
        message: 'Global notifications are exposed through a live region.',
        role: 'alert',
        liveRegion: 'polite',
        critical: true,
        hasTextSignal: true,
        supportsTextScaling: true,
      }),
    ]),
    contrasts: Object.freeze([
      defineAccessibleContrast({
        id: 'boot.primary',
        flow: 'boot',
        foreground: '#FFFFFF',
        background: '#7C3AED',
        largeText: false,
        critical: true,
      }),
      defineAccessibleContrast({
        id: 'actionsheet.default',
        flow: 'modal',
        foreground: '#E2E8F0',
        background: '#1E293B',
        largeText: false,
        critical: true,
      }),
      defineAccessibleContrast({
        id: 'connectivity.down',
        flow: 'connectivity',
        foreground: '#FEE2E2',
        background: '#7F1D1D',
        largeText: false,
        critical: true,
      }),
      defineAccessibleContrast({
        id: 'connectivity.offline',
        flow: 'connectivity',
        foreground: '#FFF7ED',
        background: '#7C2D12',
        largeText: false,
        critical: true,
      }),
      defineAccessibleContrast({
        id: 'connectivity.degraded',
        flow: 'connectivity',
        foreground: '#FEF3C7',
        background: '#854D0E',
        largeText: false,
        critical: true,
      }),
      defineAccessibleContrast({
        id: 'toast.info',
        flow: 'notification',
        foreground: '#E2E8F0',
        background: '#1E293B',
        largeText: false,
        critical: true,
      }),
      defineAccessibleContrast({
        id: 'toast.error',
        flow: 'notification',
        foreground: '#FECACA',
        background: '#450A0A',
        largeText: false,
        critical: true,
      }),
    ]),
    motions: Object.freeze([
      defineAccessibleMotion({
        id: 'actionsheet.motion',
        flow: 'modal',
        animated: true,
        essential: false,
        reduceMotionHonored: true,
        defaultDurationMs: 180,
        reducedDurationMs: 0,
      }),
      defineAccessibleMotion({
        id: 'boot.motion',
        flow: 'boot',
        animated: true,
        essential: false,
        reduceMotionHonored: true,
        defaultDurationMs: 380,
        reducedDurationMs: 0,
      }),
      defineAccessibleMotion({
        id: 'connectivity.motion',
        flow: 'connectivity',
        animated: true,
        essential: false,
        reduceMotionHonored: true,
        defaultDurationMs: 220,
        reducedDurationMs: 0,
      }),
      defineAccessibleMotion({
        id: 'toast.motion',
        flow: 'notification',
        animated: true,
        essential: false,
        reduceMotionHonored: true,
        defaultDurationMs: 160,
        reducedDurationMs: 0,
      }),
    ]),
  });

export function assertCriticalAccessibilityAcceptance(
  snapshot: AccessibilitySnapshot = CRITICAL_ACCESSIBILITY_SNAPSHOT,
  matrix: AccessibilityAcceptanceMatrix = DEFAULT_ACCESSIBILITY_MATRIX,
): AccessibilityAcceptanceReport {
  const report = evaluateAccessibilityAcceptance(snapshot, matrix);
  if (!report.criticalPassed) {
    const summary = report.findings
      .filter((item) => item.severity === 'critical')
      .map((item) => item.subjectId + ':' + item.requirementId)
      .join(', ');
    throw new Error('Critical accessibility acceptance failed: ' + summary);
  }
  return report;
}
