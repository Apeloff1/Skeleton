'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { h, load, render } = require('./harness.cjs');

const a = load('src/skeletonForge/a11y.ts');

test('gridMove: vertical list arrows, Home/End and wrap', () => {
  const o = { cols: 1, count: 5 };
  assert.equal(a.gridMove(0, 'ArrowDown', o), 1);
  assert.equal(a.gridMove(4, 'ArrowDown', o), 4);
  assert.equal(a.gridMove(4, 'ArrowDown', { ...o, wrap: true }), 0);
  assert.equal(a.gridMove(0, 'ArrowUp', o), 0);
  assert.equal(a.gridMove(0, 'ArrowUp', { ...o, wrap: true }), 4);
  assert.equal(a.gridMove(2, 'Home', o), 0);
  assert.equal(a.gridMove(2, 'End', o), 4);
  assert.equal(a.gridMove(3, 'ArrowRight', o), 4);
  assert.equal(a.gridMove(0, 'ArrowLeft', { ...o, wrap: true }), 4);
});

test('gridMove: 3-column grid moves by row and respects row edges', () => {
  const o = { cols: 3, count: 8 }; // rows: 0-2, 3-5, 6-7
  assert.equal(a.gridMove(1, 'ArrowDown', o), 4);
  assert.equal(a.gridMove(4, 'ArrowDown', o), 7);
  assert.equal(a.gridMove(5, 'ArrowDown', o), 5, 'no cell below in a short last row: stay');
  assert.equal(a.gridMove(4, 'ArrowUp', o), 1);
  assert.equal(a.gridMove(1, 'ArrowUp', o), 1);
  assert.equal(a.gridMove(4, 'Home', o), 3);
  assert.equal(a.gridMove(4, 'End', o), 5);
  assert.equal(a.gridMove(6, 'End', o), 7, 'End clamps inside a short last row');
  assert.equal(a.gridMove(4, 'Home', { ...o, ctrl: true }), 0);
  assert.equal(a.gridMove(4, 'End', { ...o, ctrl: true }), 7);
  assert.equal(a.gridMove(7, 'ArrowDown', { ...o, wrap: true }), 7, 'wrap only applies to lists vertically');
});

test('gridMove: paging, clamping and junk input', () => {
  assert.equal(a.gridMove(0, 'PageDown', { cols: 2, count: 20, pageRows: 3 }), 6);
  assert.equal(a.gridMove(18, 'PageDown', { cols: 2, count: 20 }), 19);
  assert.equal(a.gridMove(3, 'PageUp', { cols: 2, count: 20 }), 0);
  assert.equal(a.gridMove(99, 'ArrowLeft', { cols: 1, count: 3 }), 1, 'out-of-range index clamps first');
  assert.equal(a.gridMove(NaN, 'ArrowDown', { cols: 1, count: 3 }), 1);
  assert.equal(a.gridMove(0, 'ArrowDown', { cols: 0, count: 3 }), 1, 'cols < 1 treated as a list');
  assert.equal(a.gridMove(0, 'Tab', { cols: 1, count: 3 }), null);
  assert.equal(a.gridMove(0, 'ArrowDown', { cols: 1, count: 0 }), null);
});

test('keyAction, isNavKey and readKey normalise DOM and RN events', () => {
  assert.equal(a.keyAction('Enter'), 'activate');
  assert.equal(a.keyAction(' '), 'activate');
  assert.equal(a.keyAction('Escape'), 'dismiss');
  assert.equal(a.keyAction('Esc'), 'dismiss');
  assert.equal(a.keyAction('a'), null);
  assert.ok(a.isNavKey('PageDown'));
  assert.ok(!a.isNavKey('Enter'));
  assert.deepEqual(a.readKey({ key: 'Home', metaKey: true }), { key: 'Home', ctrl: true, shift: false });
  assert.deepEqual(a.readKey({ nativeEvent: { key: 'End', ctrlKey: true, shiftKey: true } }), { key: 'End', ctrl: true, shift: true });
  assert.deepEqual(a.readKey({}), { key: '', ctrl: false, shift: false });
});

test('webKeyProps only attaches onKeyDown on web', () => {
  const fn = () => {};
  assert.deepEqual(a.webKeyProps(fn, 'web'), { onKeyDown: fn });
  assert.deepEqual(a.webKeyProps(fn, 'ios'), {});
  assert.deepEqual(a.webKeyProps(undefined, 'web'), {});
});

test('rovingTabIndex keeps a single tab stop', () => {
  assert.deepEqual([0, 1, 2].map((i) => a.rovingTabIndex(i, 1)), [-1, 0, -1]);
});

test('tabIndexProp is web-only', () => {
  assert.deepEqual(a.tabIndexProp(0, 'web'), { tabIndex: 0 });
  assert.deepEqual(a.tabIndexProp(-1, 'web'), { tabIndex: -1 });
  assert.deepEqual(a.tabIndexProp(0, 'ios'), {});
  assert.deepEqual(a.tabIndexProp(undefined, 'web'), {});
});

test('useRovingIndex clamps to the item count', () => {
  const React = require('react');
  let seen;
  function Probe({ count, initial }) {
    const [i] = a.useRovingIndex(count, initial);
    seen = i;
    return React.createElement('span', null, String(i));
  }
  render(h(Probe, { count: 3, initial: 9 }));
  assert.equal(seen, 2);
  render(h(Probe, { count: 0, initial: 4 }));
  assert.equal(seen, 0);
  render(h(Probe, { count: 5, initial: 1 }));
  assert.equal(seen, 1);
});

test('countAnnouncement copy', () => {
  assert.equal(a.countAnnouncement(0, 0, 'era'), 'No eras available.');
  assert.equal(a.countAnnouncement(0, 4, 'era', ' zz '), 'No eras match “zz”.');
  assert.equal(a.countAnnouncement(1, 1, 'era'), '1 era shown.');
  assert.equal(a.countAnnouncement(4, 4, 'era'), '4 eras shown.');
  assert.equal(a.countAnnouncement(2, 4, 'era', 'boom'), '2 of 4 eras shown for “boom”.');
  assert.equal(a.countAnnouncement(2, 4, 'era'), '2 of 4 eras shown.');
});
