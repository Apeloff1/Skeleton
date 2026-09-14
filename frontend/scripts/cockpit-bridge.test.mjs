import assert from 'node:assert/strict';
import test from 'node:test';

import {
  COCKPIT_BRIDGE_CHANNEL,
  COCKPIT_BRIDGE_VERSION,
  getConfiguredCockpitOrigins,
  installCockpitPreviewBridge,
  isSafeCockpitPath,
} from '../src/cockpit/previewBridge.ts';

function withGlobal(name, value) {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, name);
  Object.defineProperty(globalThis, name, {
    configurable: true,
    writable: true,
    value,
  });
  return () => {
    if (descriptor) Object.defineProperty(globalThis, name, descriptor);
    else delete globalThis[name];
  };
}

function makeBrowser({ parentOrigin = 'https://cockpit.example' } = {}) {
  const listeners = new Map();
  const posts = [];
  const historyMoves = [];
  const parent = {
    postMessage(message, origin) {
      posts.push({ message, origin });
    },
  };
  const history = {
    length: 1,
    state: null,
    pushState(data, _unused, url) {
      this.state = data;
      if (url) window.location.pathname = new URL(String(url), window.location.origin).pathname;
    },
    replaceState(data) {
      this.state = data;
    },
    go(delta) {
      historyMoves.push(delta);
    },
  };
  const window = {
    parent,
    location: {
      origin: 'https://preview.example',
      href: 'https://preview.example/',
      hostname: 'preview.example',
      pathname: '/',
      search: '',
      hash: '',
      ancestorOrigins: { 0: parentOrigin, length: 1 },
    },
    history,
    addEventListener(type, listener) {
      listeners.set(type, listener);
    },
    removeEventListener(type, listener) {
      if (listeners.get(type) === listener) listeners.delete(type);
    },
    dispatchEvent() {},
  };
  const document = { referrer: `${parentOrigin}/host` };
  return { window, document, parent, history, listeners, posts, historyMoves };
}

function receipts(browser) {
  return browser.posts
    .map(({ message }) => message)
    .filter((message) => message.type === 'command-result');
}

test('cockpit path validation rejects cross-origin and protocol-relative paths', () => {
  assert.equal(isSafeCockpitPath('/galaxy?mode=preview#scene'), true);
  assert.equal(isSafeCockpitPath('/gate/[stage]'), true);
  assert.equal(isSafeCockpitPath('//evil.example/path'), false);
  assert.equal(isSafeCockpitPath('https://evil.example/path'), false);
  assert.equal(isSafeCockpitPath('/safe\\escape'), false);
  assert.equal(isSafeCockpitPath('relative/path'), false);
});

test('configured cockpit origins are normalized, deduplicated, and scheme bounded', () => {
  const restore = withGlobal(
    '__SKELETON_COCKPIT_ORIGINS__',
    'https://cockpit.example/path, http://localhost:3000, javascript:alert(1), https://cockpit.example',
  );
  try {
    assert.deepEqual(getConfiguredCockpitOrigins(), [
      'https://cockpit.example',
      'http://localhost:3000',
    ]);
  } finally {
    restore();
  }
});

test('external cockpit parent fails closed when it is not allowlisted', () => {
  const browser = makeBrowser();
  const restoreWindow = withGlobal('window', browser.window);
  const restoreDocument = withGlobal('document', browser.document);
  try {
    const dispose = installCockpitPreviewBridge();
    assert.equal(browser.listeners.size, 0);
    assert.equal(browser.posts.length, 0);
    dispose();
  } finally {
    restoreDocument();
    restoreWindow();
  }
});

test('trusted cockpit parent receives readiness, bounded commands, and execution receipts', async () => {
  const browser = makeBrowser();
  const restoreWindow = withGlobal('window', browser.window);
  const restoreDocument = withGlobal('document', browser.document);
  const navigations = [];
  try {
    const dispose = installCockpitPreviewBridge({
      allowedParentOrigins: ['https://cockpit.example'],
      getRoutePaths: () => ['/galaxy', '/jeeves-control', '//invalid.example'],
      navigate: (path) => navigations.push(path),
    });

    assert.deepEqual(
      browser.posts.map(({ message }) => message.type),
      ['location', 'routes', 'ready'],
    );
    assert.deepEqual(browser.posts[1].message.paths, ['/galaxy', '/jeeves-control']);
    assert.ok(
      browser.posts.every(({ origin }) => origin === 'https://cockpit.example'),
      'guest messages must target only the trusted parent origin',
    );

    const onMessage = browser.listeners.get('message');
    assert.equal(typeof onMessage, 'function');

    onMessage({
      source: browser.parent,
      origin: 'https://attacker.example',
      data: {
        channel: COCKPIT_BRIDGE_CHANNEL,
        version: COCKPIT_BRIDGE_VERSION,
        type: 'navigate',
        requestId: 'attacker-1',
        path: '/galaxy',
      },
    });
    assert.deepEqual(navigations, []);
    assert.deepEqual(receipts(browser), []);

    onMessage({
      source: browser.parent,
      origin: 'https://cockpit.example',
      data: {
        channel: COCKPIT_BRIDGE_CHANNEL,
        version: COCKPIT_BRIDGE_VERSION,
        type: 'navigate',
        requestId: 'nav-bad',
        path: 'https://attacker.example/',
      },
    });
    assert.deepEqual(navigations, []);
    assert.deepEqual(receipts(browser).at(-1), {
      channel: COCKPIT_BRIDGE_CHANNEL,
      version: COCKPIT_BRIDGE_VERSION,
      type: 'command-result',
      requestId: 'nav-bad',
      command: 'navigate',
      status: 'rejected',
      reason: 'invalid_path',
    });

    onMessage({
      source: browser.parent,
      origin: 'https://cockpit.example',
      data: {
        channel: COCKPIT_BRIDGE_CHANNEL,
        version: COCKPIT_BRIDGE_VERSION,
        type: 'navigate',
        requestId: 'nav-1',
        path: '/galaxy?project=alpha',
      },
    });
    await Promise.resolve();
    assert.deepEqual(navigations, ['/galaxy?project=alpha']);
    assert.deepEqual(receipts(browser).at(-1), {
      channel: COCKPIT_BRIDGE_CHANNEL,
      version: COCKPIT_BRIDGE_VERSION,
      type: 'command-result',
      requestId: 'nav-1',
      command: 'navigate',
      status: 'accepted',
    });

    onMessage({
      source: browser.parent,
      origin: 'https://cockpit.example',
      data: {
        channel: COCKPIT_BRIDGE_CHANNEL,
        version: COCKPIT_BRIDGE_VERSION,
        type: 'history',
        requestId: 'history-back',
        delta: -1,
      },
    });
    assert.deepEqual(browser.historyMoves, [], 'history root must not escape preview');
    assert.deepEqual(receipts(browser).at(-1), {
      channel: COCKPIT_BRIDGE_CHANNEL,
      version: COCKPIT_BRIDGE_VERSION,
      type: 'command-result',
      requestId: 'history-back',
      command: 'history',
      status: 'rejected',
      reason: 'history_floor',
    });

    onMessage({
      source: browser.parent,
      origin: 'https://cockpit.example',
      data: {
        channel: COCKPIT_BRIDGE_CHANNEL,
        version: COCKPIT_BRIDGE_VERSION,
        type: 'history',
        requestId: 'history-forward',
        delta: 1,
      },
    });
    assert.deepEqual(browser.historyMoves, [1]);
    assert.deepEqual(receipts(browser).at(-1), {
      channel: COCKPIT_BRIDGE_CHANNEL,
      version: COCKPIT_BRIDGE_VERSION,
      type: 'command-result',
      requestId: 'history-forward',
      command: 'history',
      status: 'accepted',
    });

    dispose();
    assert.equal(browser.listeners.size, 0);
  } finally {
    restoreDocument();
    restoreWindow();
  }
});
