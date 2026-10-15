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


test('conversation turn transport targets assembled AI route and keeps reconnect controls', async () => {
  const clientUrl = new URL(
    '../src/product/conversationClient.ts',
    import.meta.url,
  );
  const source = await readFile(clientUrl, 'utf8');
  const output = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ES2022,
      strict: true,
    },
    fileName: 'conversationClient.ts',
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

  assert.match(source, /export async function startConversationTurn/);
  assert.match(source, /export async function getConversationTurn/);
  assert.match(source, /export async function cancelConversationTurn/);
  assert.match(source, /export async function followConversationTurn/);
  assert.match(source, /\/api\/ai\/chat/);
  assert.doesNotMatch(source, /\/api\/v1\/ai\/chat/);
  assert.match(source, /response_mode:/);
  assert.match(source, /'deferred'/);
  assert.match(source, /engine_execution_id/);
  assert.match(source, /AbortSignal/);
});

test('unsafe canonical sequence and oversized projection fail closed with stable error codes', () => {
  assert.throws(
    () => validateConversationProjection(
      { thread_id: 'thread-a', message_sequence: Number.MAX_SAFE_INTEGER + 1 }, [],
    ),
    (error) => error.code === 'invalid_projection',
  );
  assert.throws(
    () => validateConversationProjection(thread, [
      { thread_id: 'thread-a', sequence: Number.MAX_SAFE_INTEGER + 1 },
    ]),
    (error) => error.code === 'invalid_sequence',
  );
  assert.throws(
    () => validateConversationProjection(
      { thread_id: 'thread-a', message_sequence: 10001 },
      Array.from({ length: 10001 }, (_, i) => ({
        thread_id: 'thread-a', sequence: i + 1,
      })),
    ),
    (error) => error.code === 'invalid_projection',
  );
});

test('conversation projections reject duplicate or malformed message identity', () => {
  assert.throws(
    () => validateConversationProjection(thread, [
      { thread_id: 'thread-a', sequence: 1, message_id: 'message-1' },
      { thread_id: 'thread-a', sequence: 2, message_id: 'message-1' },
    ]),
    (error) => error.code === 'invalid_message',
  );
  assert.throws(
    () => validateConversationProjection(thread, [
      { thread_id: 'thread-a', sequence: 1, message_id: '' },
    ]),
    (error) => error.code === 'invalid_message',
  );
  assert.throws(
    () => validateConversationProjection(thread, [null]),
    (error) => error.code === 'invalid_message',
  );
});

test('reconnect result preserves stable nonduplicated message IDs in sequence order', () => {
  const data = [
    { thread_id: 'thread-a', sequence: 3, message_id: 'm3' },
    { thread_id: 'thread-a', sequence: 1, message_id: 'm1' },
  ];
  const result = validateConversationProjection(thread, data);
  assert.deepEqual(result.messages.map(({ message_id }) => message_id), ['m1', 'm3']);
  assert.equal(result.lastSequence, 3);
  assert.equal(data[0].sequence, 3);
});

test('/ai-chat route lazily opens the canonical workspace instead of divergent draft UI', async () => {
  const [route, workspace] = await Promise.all([
    readFile(new URL('../app/ai-chat.tsx', import.meta.url), 'utf8'),
    readFile(new URL('../features/Jeeves/GovernedChatWorkspace.tsx', import.meta.url), 'utf8'),
  ]);
  assert.match(route, /makeLazyModalRoute/);
  assert.match(route, /import\('\.\.\/features\/Jeeves\/GovernedChatWorkspace'\)/);
  assert.match(route, /'AIChatRoute'/);
  assert.match(workspace, /export default function ChatWorkspace/);
  assert.match(workspace, /useChatController/);
  assert.doesNotMatch(route, /initialThreadId=/);
});
