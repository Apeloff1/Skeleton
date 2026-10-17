import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';

const read = relativePath => readFileSync(new URL(relativePath, import.meta.url), 'utf8');
const inventory = read('../app/ai-models.tsx');
const readiness = read('../src/features/Jeeves/JeevesRuntimeStatus.tsx');
const catalog = read('../src/product/productCatalog.ts');
const client = read('../src/product/chatSessionClient.ts');

test('observed model inventory is a real authenticated Expo screen', () => {
  assert.equal(existsSync(new URL('../app/ai-models.tsx', import.meta.url)), true);
  assert.match(inventory, /StudioLoginGate[^>]*requireAuthenticated/);
  assert.match(inventory, /getChatReadiness\(signal\)/);
  assert.match(inventory, /model\.readiness\.message/);
  assert.match(inventory, /readiness\.models\.models\.map\(/);
  assert.match(inventory, /No model has been reported/);
  assert.doesNotMatch(inventory, /available:\s*true/);
  assert.doesNotMatch(inventory, /api\.(?:post|put|delete|patch)\s*\(/);
});

test('route exposes only server-reported activation and capabilities', () => {
  assert.match(inventory, /model\.active/);
  assert.match(inventory, /model\.selectable/);
  assert.match(inventory, /model\.credential_free/);
  assert.match(inventory, /model\.context_window/);
  assert.match(inventory, /model\.max_output_tokens/);
  assert.match(inventory, /model\.capabilities/);
  assert.match(client, /getChatReadiness\(signal\?: AbortSignal\)/);
  assert.match(client, /backend\.ai\.chat-readiness\.v1/);
});

test('Jeeves status and canonical product navigation reach the real screen', () => {
  assert.match(readiness, /router\.push\('\/ai-models' as never\)/);
  assert.match(catalog, /navigationId: 'jeeves\.models\.inventory', href: '\/ai-models'/);
  const shortcuts = catalog.split('export const PRODUCT_HOME_SHORTCUT_IDS =', 2)[1].split('] as const', 1)[0];
  assert.match(shortcuts, /'jeeves\.models\.inventory'/);
});

test('related workspaces in inventory all resolve to Expo routes', () => {
  const entries = [...inventory.matchAll(/\{ title: '[^']+', href: '(\/[^']+)' \}/g)];
  assert.ok(entries.length >= 5);
  for (const [, href] of entries) {
    assert.match(href, /^\/[a-z0-9\/-]+$/);
    const route = '../app' + href + '.tsx';
    assert.equal(existsSync(new URL(route, import.meta.url)), true, 'Missing route: ' + route);
  }
});
