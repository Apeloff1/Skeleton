import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import ts from 'typescript';

async function loadProjectionModule() {
  const sourceUrl = new URL(
    '../src/product/conversationProjection.ts',
    import.meta.url,
  );
  const source = await readFile(sourceUrl, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ES2022,
      strict: true,
    },
    fileName: 'conversationProjection.ts',
    reportDiagnostics: true,
  });
  const diagnostics = output.diagnostics || [];
  assert.equal(
    diagnostics.length,
    0,
    diagnostics.map((item) => ts.flattenDiagnosticMessageText(
      item.messageText,
      '\n',
    )).join('\n'),
  );
  return import(
    'data:text/javascript;base64,'
      + Buffer.from(output.outputText, 'utf8').toString('base64')
  );
}

const projectionModule = await loadProjectionModule();
const { validateConversationProjection } = projectionModule;

const thread = {
  thread_id: 'thread-a',
  message_sequence: 4,
};

test('refresh/reconnect reconstructs deterministic canonical order', () => {
  const original = [
    { thread_id: 'thread-a', sequence: 1, content: 'u1' },
    { thread_id: 'thread-a', sequence: 2, content: 'a1' },
    { thread_id: 'thread-a', sequence: 4, content: 'a2-active-branch' },
  ];
  const reconnect = [
    original[2],
    original[0],
    original[1],
  ];

  const first = validateConversationProjection(thread, original);
  const second = validateConversationProjection(thread, reconnect);

  assert.deepEqual(second, first);
  assert.deepEqual(
    second.messages.map((message) => message.sequence),
    [1, 2, 4],
  );
  assert.equal(second.lastSequence, 4);
});

test('empty active branch projection remains reconstructable', () => {
  const result = validateConversationProjection(
    { thread_id: 'thread-empty', message_sequence: 0 },
    [],
  );

  assert.deepEqual(result.messages, []);
  assert.equal(result.lastSequence, 0);
});

test('foreign-thread messages fail closed', () => {
  assert.throws(
    () => validateConversationProjection(thread, [
      { thread_id: 'thread-b', sequence: 1 },
    ]),
    /foreign thread message/,
  );
});

test('duplicate canonical sequence fails closed after sorting', () => {
  assert.throws(
    () => validateConversationProjection(thread, [
      { thread_id: 'thread-a', sequence: 2 },
      { thread_id: 'thread-a', sequence: 2 },
    ]),
    /not strictly ordered/,
  );
});

test('projection cannot outrun canonical thread authority', () => {
  assert.throws(
    () => validateConversationProjection(thread, [
      { thread_id: 'thread-a', sequence: 5 },
    ]),
    /ahead of canonical thread state/,
  );
});

test('invalid sequence fails closed', () => {
  assert.throws(
    () => validateConversationProjection(thread, [
      { thread_id: 'thread-a', sequence: 0 },
    ]),
    /invalid sequence/,
  );
});
