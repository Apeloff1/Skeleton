#!/usr/bin/env node
'use strict';
/**
 * Pressable accessibility codemod + checker (WCAG 2.2 AA 4.1.2 Name, Role, Value).
 *
 *   node scripts/a11y/pressable-a11y.cjs --check <files…>   report, exit 1 on findings
 *   node scripts/a11y/pressable-a11y.cjs --write <files…>   apply safe fixes, then report
 *
 * For every <TouchableOpacity|TouchableHighlight|TouchableWithoutFeedback|Pressable>
 * with an onPress/onLongPress handler:
 *   - role:  adds accessibilityRole="button" unless a role (accessibilityRole/role)
 *            or a props spread is present (the spread may carry it).
 *   - name:  OK when it has accessibilityLabel/aria-label, or renders text (JSX text,
 *            a <Text>/<AppText> child, or a `label`/`title` prop on a child).
 *            Icon-only controls get a label inferred from a literal icon name
 *            (e.g. name="close" → "Close"); anything else is reported for a human.
 * For every <TextInput> without accessibilityLabel/aria-label but with a literal
 * placeholder, adds accessibilityLabel equal to the placeholder (placeholders are
 * not labels: they disappear on input and are not reliably announced).
 *
 * Edits are attribute insertions only: no element, handler or style changes.
 */
const fs = require('node:fs');
const path = require('node:path');
const ts = require('typescript');

const PRESSABLES = new Set(['TouchableOpacity', 'TouchableHighlight', 'TouchableWithoutFeedback', 'Pressable']);
const TEXTY = new Set(['Text', 'AppText', 'Animated.Text', 'ThemedText']);
const ICONS = /^(Ionicons|MaterialIcons|MaterialCommunityIcons|Feather|FontAwesome5?|AntDesign|Entypo|Icon)$/;
const ICON_LABELS = {
  close: 'Close', 'close-circle': 'Close', 'close-outline': 'Close', x: 'Close',
  'arrow-back': 'Go back', 'arrow-back-outline': 'Go back', 'chevron-back-outline': 'Go back', 'chevron-back': 'Go back', 'arrow-left': 'Go back', 'chevron-left': 'Go back', 'ios-arrow-back': 'Go back',
  'arrow-forward': 'Next', 'chevron-forward': 'Next', 'chevron-right': 'Next', 'arrow-right': 'Next',
  add: 'Add', 'add-circle': 'Add', plus: 'Add', 'add-outline': 'Add',
  trash: 'Delete', 'trash-outline': 'Delete', delete: 'Delete',
  refresh: 'Refresh', 'refresh-outline': 'Refresh', reload: 'Refresh',
  search: 'Search', 'search-outline': 'Search',
  settings: 'Settings', 'settings-outline': 'Settings', cog: 'Settings',
  play: 'Play', 'play-circle': 'Play', pause: 'Pause', stop: 'Stop', 'stop-circle': 'Stop',
  send: 'Send', 'paper-plane': 'Send', share: 'Share', 'share-outline': 'Share', 'share-social': 'Share',
  copy: 'Copy', 'copy-outline': 'Copy', download: 'Download', 'download-outline': 'Download',
  heart: 'Like', 'heart-outline': 'Like', star: 'Favourite', 'star-outline': 'Favourite',
  menu: 'Open menu', 'ellipsis-horizontal': 'More options', 'ellipsis-vertical': 'More options', 'dots-vertical': 'More options',
  create: 'Edit', 'create-outline': 'Edit', pencil: 'Edit', edit: 'Edit',
  'information-circle': 'Information', 'information-circle-outline': 'Information', 'help-circle': 'Help', 'help-circle-outline': 'Help',
  mic: 'Record voice', 'mic-outline': 'Record voice', 'volume-high': 'Sound on', 'volume-mute': 'Sound off',
  home: 'Home', 'home-outline': 'Home', checkmark: 'Confirm', 'checkmark-circle': 'Confirm', save: 'Save', 'save-outline': 'Save',
  'expand': 'Expand', 'contract': 'Collapse', 'chevron-down': 'Expand', 'chevron-up': 'Collapse',
  filter: 'Filter', 'filter-outline': 'Filter', camera: 'Camera', image: 'Choose image', 'images-outline': 'Choose image',
};

function attrs(el) { return el.attributes.properties; }
function attrName(a) { return ts.isJsxAttribute(a) ? a.name.getText() : null; }
function hasAttr(el, ...names) { return attrs(el).some((a) => names.includes(attrName(a))); }
function hasSpread(el) { return attrs(el).some((a) => ts.isJsxSpreadAttribute(a)); }
function literalAttr(el, name) {
  const a = attrs(el).find((x) => attrName(x) === name);
  if (!a || !a.initializer) return null;
  if (ts.isStringLiteral(a.initializer)) return a.initializer.text;
  if (ts.isJsxExpression(a.initializer) && a.initializer.expression && ts.isStringLiteral(a.initializer.expression)) return a.initializer.expression.text;
  if (ts.isJsxExpression(a.initializer) && a.initializer.expression && ts.isNoSubstitutionTemplateLiteral(a.initializer.expression)) return a.initializer.expression.text;
  return null;
}
function opening(node) { return ts.isJsxElement(node) ? node.openingElement : ts.isJsxSelfClosingElement(node) ? node : null; }
function tag(el) { return el.tagName.getText(); }

/** Does the subtree render any text (which becomes the accessible name)? */
function rendersText(node) {
  let found = false;
  const visit = (n) => {
    if (found) return;
    if (ts.isJsxText(n) && n.getText().trim()) { found = true; return; }
    const el = opening(n);
    if (el) {
      if (TEXTY.has(tag(el))) { found = true; return; }
      if (hasAttr(el, 'label', 'title', 'accessibilityLabel', 'aria-label', 'text')) { found = true; return; }
    }
    if (ts.isJsxExpression(n) && n.parent && ts.isJsxElement(n.parent) && n.expression
        && (ts.isStringLiteral(n.expression) || ts.isTemplateExpression(n.expression) || ts.isNoSubstitutionTemplateLiteral(n.expression))) { found = true; return; }
    ts.forEachChild(n, visit);
  };
  if (ts.isJsxElement(node)) node.children.forEach(visit);
  return found;
}

/** A pressable wrapping other pressables must not become a button (nested-interactive). */
function containsPressable(node) {
  let found = false;
  const visit = (n) => {
    if (found) return;
    const el = opening(n);
    if (el && PRESSABLES.has(tag(el)) && hasAttr(el, 'onPress', 'onLongPress')) { found = true; return; }
    ts.forEachChild(n, visit);
  };
  if (ts.isJsxElement(node)) node.children.forEach(visit);
  return found;
}

function inferIconLabel(node) {
  let label = null;
  const visit = (n) => {
    if (label) return;
    const el = opening(n);
    if (el && ICONS.test(tag(el))) {
      const name = literalAttr(el, 'name');
      if (name && ICON_LABELS[name]) { label = ICON_LABELS[name]; return; }
    }
    ts.forEachChild(n, visit);
  };
  if (ts.isJsxElement(node)) node.children.forEach(visit);
  return label;
}

/** Visible label text from the nearest preceding <Text> sibling, if it is a plain literal. */
function visibleLabelBefore(node) {
  const parent = node.parent;
  if (!parent || !ts.isJsxElement(parent)) return null;
  const siblings = parent.children.filter((c) => !(ts.isJsxText(c) && !c.getText().trim()));
  const idx = siblings.indexOf(node);
  const prev = idx > 0 ? siblings[idx - 1] : null;
  if (!prev || !ts.isJsxElement(prev) || !TEXTY.has(tag(prev.openingElement))) return null;
  const parts = prev.children.map((c) => (ts.isJsxText(c) ? c.getText() : null));
  if (parts.some((p) => p === null)) return null;
  const text = parts.join(' ').replace(/\s+/g, ' ').replace(/[:*]\s*$/, '').trim();
  return text || null;
}

/** Literal text of a <Text> element, or null when it has expressions. */
function literalText(el) {
  if (!ts.isJsxElement(el) || !TEXTY.has(tag(el.openingElement))) return null;
  const parts = el.children.map((c) => (ts.isJsxText(c) ? c.getText() : null));
  if (parts.some((p) => p === null)) return null;
  const text = parts.join(' ').replace(/\s+/g, ' ').replace(/[:*]\s*$/, '').trim();
  return text || null;
}

/**
 * Toggle rows are usually `<Row><View><Text>Title</Text><Text>hint</Text></View><Switch/></Row>`:
 * take the direct preceding <Text>, or the first <Text> of the preceding wrapper.
 */
function rowLabelBefore(node) {
  const direct = visibleLabelBefore(node);
  if (direct) return direct;
  const parent = node.parent;
  // <Row label="Line numbers"><Switch …/></Row>
  if (parent && ts.isJsxElement(parent)) {
    const own = literalAttr(parent.openingElement, 'label') || literalAttr(parent.openingElement, 'title');
    if (own && own.trim()) return own.trim();
  }
  if (!parent || !ts.isJsxElement(parent)) return null;
  const siblings = parent.children.filter((c) => !(ts.isJsxText(c) && !c.getText().trim()));
  const prev = siblings[siblings.indexOf(node) - 1];
  if (!prev || !ts.isJsxElement(prev)) return null;
  const first = prev.children.find((c) => !(ts.isJsxText(c) && !c.getText().trim()));
  return first ? literalText(first) : null;
}

function analyse(file, source) {
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const edits = [];
  const findings = [];
  const line = (pos) => sf.getLineAndCharacterOfPosition(pos).line + 1;
  const lines = source.split('\n');
  // `{/* a11y-exempt: <reason> */}` on one of the two lines above an element
  // records a reviewed exception (e.g. a tap-anywhere backdrop around a real button).
  const exempt = (el) => {
    const l = line(el.getStart());
    return lines.slice(Math.max(0, l - 3), l - 1).some((t) => /a11y-exempt:\s*\S/.test(t));
  };
  const visit = (node) => {
    const el = opening(node);
    if (el) {
      const name = tag(el);
      if (PRESSABLES.has(name) && hasAttr(el, 'onPress', 'onLongPress')) {
        const spread = hasSpread(el);
        const insert = [];
        if (exempt(el)) { ts.forEachChild(node, visit); return; }
        if (containsPressable(node)) {
          findings.push({ file, line: line(el.getStart()), kind: 'nested-pressable', tag: name });
          ts.forEachChild(node, visit);
          return;
        }
        if (!hasAttr(el, 'accessibilityRole', 'role') && !spread) insert.push('accessibilityRole="button"');
        const named = hasAttr(el, 'accessibilityLabel', 'aria-label', 'aria-labelledby', 'accessibilityLabelledBy') || rendersText(node);
        if (!named && !spread) {
          const inferred = inferIconLabel(node);
          if (inferred) insert.push(`accessibilityLabel="${inferred}"`);
          else findings.push({ file, line: line(el.getStart()), kind: 'unnamed-pressable', tag: name });
        }
        if (insert.length) edits.push({ pos: el.tagName.end, text: ' ' + insert.join(' ') });
      } else if (name === 'TextInput' && !hasAttr(el, 'accessibilityLabel', 'aria-label', 'aria-labelledby', 'accessibilityLabelledBy') && !hasSpread(el)) {
        const placeholder = literalAttr(el, 'placeholder');
        const visible = visibleLabelBefore(node);
        const label = visible || (placeholder && placeholder.trim() ? placeholder : null);
        if (label) {
          const clean = label.replace(/…/g, '').replace(/\.\.\.$/, '').replace(/"/g, "'").trim();
          edits.push({ pos: el.tagName.end, text: ` accessibilityLabel="${clean}"` });
        } else findings.push({ file, line: line(el.getStart()), kind: 'unlabelled-input', tag: name });
      } else if (/^(Slider|DeepSlider)$/.test(name) && !hasAttr(el, 'accessibilityLabel', 'aria-label', 'aria-labelledby', 'accessibilityLabelledBy') && !hasSpread(el) && !exempt(el)) {
        // Needs a name and aria-valuemin/max/now/text: reviewed by hand, never auto-fixed.
        findings.push({ file, line: line(el.getStart()), kind: 'unlabelled-slider', tag: name });
      } else if (name === 'Switch' && !hasAttr(el, 'accessibilityLabel', 'aria-label', 'aria-labelledby', 'accessibilityLabelledBy') && !hasSpread(el) && !exempt(el)) {
        const label = rowLabelBefore(node);
        const clean = label && label.replace(/^[^\p{L}\p{N}]+/u, '').replace(/"/g, "'").trim();
        if (clean) edits.push({ pos: el.tagName.end, text: ` accessibilityLabel="${clean}"` });
        else findings.push({ file, line: line(el.getStart()), kind: 'unlabelled-switch', tag: name });
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return { edits, findings };
}

function apply(source, edits) {
  let out = source;
  for (const e of [...edits].sort((a, b) => b.pos - a.pos)) out = out.slice(0, e.pos) + e.text + out.slice(e.pos);
  return out;
}

function main(argv) {
  const mode = argv[0];
  const files = argv.slice(1);
  if (!['--check', '--write'].includes(mode) || files.length === 0) {
    console.error('usage: pressable-a11y.cjs --check|--write <files…>');
    return 2;
  }
  let pending = 0;
  const findings = [];
  for (const file of files) {
    const abs = path.resolve(file);
    let src = fs.readFileSync(abs, 'utf8');
    let { edits, findings: f } = analyse(abs, src);
    if (mode === '--write' && edits.length) {
      src = apply(src, edits);
      fs.writeFileSync(abs, src);
      ({ edits, findings: f } = analyse(abs, src));
    }
    pending += edits.length;
    findings.push(...f);
    if (edits.length) console.log(`${file}: ${edits.length} fixable`);
  }
  for (const f of findings) console.log(`${path.relative(process.cwd(), f.file)}:${f.line}: ${f.kind} <${f.tag}>`);
  console.log(`summary: ${files.length} files, ${pending} fixable, ${findings.length} need review`);
  return pending || findings.length ? 1 : 0;
}

module.exports = { analyse, apply, ICON_LABELS };
if (require.main === module) process.exitCode = main(process.argv.slice(2));
