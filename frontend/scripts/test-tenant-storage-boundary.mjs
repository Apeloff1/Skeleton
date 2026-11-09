import assert from 'node:assert/strict';
import test from 'node:test';

import {
  TenantBoundStorage,
  tenantStorageKey,
} from '../src/product/tenantStorageBoundary.ts';

class MemoryStorage {
  constructor() {
    this.rows = new Map();
  }

  async getItem(key) {
    return this.rows.has(key) ? this.rows.get(key) : null;
  }

  async setItem(key, value) {
    this.rows.set(key, value);
  }

  async removeItem(key) {
    this.rows.delete(key);
  }
}

test('tenant storage key is stable and does not expose raw tenant identity', () => {
  const tenant = 'person@example.com';
  const first = tenantStorageKey('workspace', tenant, 'jeeves-workspace');
  const second = tenantStorageKey('workspace', tenant, 'jeeves-workspace');
  const other = tenantStorageKey('workspace', 'other@example.com', 'jeeves-workspace');

  assert.equal(first, second);
  assert.notEqual(first, other);
  assert.equal(first.includes(tenant), false);
  assert.equal(first.includes(encodeURIComponent(tenant)), false);
  assert.match(first, /^@tenant\/[0-9a-f]{16}\//);
});

test('same tenant and principal can round-trip cached workspace data', async () => {
  const storage = new MemoryStorage();
  const boundary = new TenantBoundStorage(
    storage,
    async () => ({
      tenantId: 'tenant-a',
      principalId: 'principal-a',
    }),
    {
      purpose: 'jeeves-workspace',
      dataClass: 'tenant_cache',
    },
  );

  await boundary.setItem('workspace', '{"draft":"hello"}');
  assert.equal(
    await boundary.getItem('workspace'),
    '{"draft":"hello"}',
  );
  assert.equal(storage.rows.size, 1);
  const [key] = storage.rows.keys();
  assert.equal(key.includes('tenant-a'), false);
});

test('account transition cannot read previous tenant cache', async () => {
  const storage = new MemoryStorage();
  let identity = {
    tenantId: 'tenant-a',
    principalId: 'principal-a',
  };
  const boundary = new TenantBoundStorage(
    storage,
    async () => identity,
    {
      purpose: 'jeeves-workspace',
      dataClass: 'tenant_cache',
    },
  );

  await boundary.setItem('workspace', 'tenant-a-data');
  identity = {
    tenantId: 'tenant-b',
    principalId: 'principal-b',
  };
  boundary.invalidateIdentity();

  assert.equal(await boundary.getItem('workspace'), null);
  await boundary.setItem('workspace', 'tenant-b-data');
  assert.equal(await boundary.getItem('workspace'), 'tenant-b-data');
  assert.equal(storage.rows.size, 2);
});

test('copied envelope under another tenant namespace is rejected', async () => {
  const storage = new MemoryStorage();
  let identity = {
    tenantId: 'tenant-a',
    principalId: 'principal-a',
  };
  const boundary = new TenantBoundStorage(
    storage,
    async () => identity,
    {
      purpose: 'jeeves-workspace',
      dataClass: 'tenant_cache',
    },
  );

  await boundary.setItem('workspace', 'secret-a');
  const keyA = tenantStorageKey(
    'workspace',
    'tenant-a',
    'jeeves-workspace',
  );
  const rawA = storage.rows.get(keyA);
  assert.equal(typeof rawA, 'string');

  identity = {
    tenantId: 'tenant-b',
    principalId: 'principal-b',
  };
  boundary.invalidateIdentity();
  const keyB = tenantStorageKey(
    'workspace',
    'tenant-b',
    'jeeves-workspace',
  );
  storage.rows.set(keyB, rawA);

  await assert.rejects(
    () => boundary.getItem('workspace'),
    /belongs to another tenant/,
  );
});

test('principal substitution is rejected even inside same tenant namespace', async () => {
  const storage = new MemoryStorage();
  let identity = {
    tenantId: 'tenant-a',
    principalId: 'principal-a',
  };
  const boundary = new TenantBoundStorage(
    storage,
    async () => identity,
    {
      purpose: 'jeeves-workspace',
      dataClass: 'user_draft',
    },
  );

  await boundary.setItem('draft', 'private-draft');
  identity = {
    tenantId: 'tenant-a',
    principalId: 'principal-b',
  };
  boundary.invalidateIdentity();

  await assert.rejects(
    () => boundary.getItem('draft'),
    /belongs to another principal/,
  );
});

test('data classification and purpose drift fail closed', async () => {
  const storage = new MemoryStorage();
  const identity = async () => ({
    tenantId: 'tenant-a',
    principalId: 'principal-a',
  });
  const cache = new TenantBoundStorage(
    storage,
    identity,
    {
      purpose: 'workspace',
      dataClass: 'tenant_cache',
    },
  );
  await cache.setItem('same', 'cached');

  const otherClass = new TenantBoundStorage(
    storage,
    identity,
    {
      purpose: 'workspace',
      dataClass: 'user_draft',
    },
  );
  const cacheKey = tenantStorageKey('same', 'tenant-a', 'workspace');
  const otherKey = tenantStorageKey('same', 'tenant-a', 'workspace');
  assert.equal(cacheKey, otherKey);

  await assert.rejects(
    () => otherClass.getItem('same'),
    /data classification drift/,
  );
});

test('device cache rejects attachment bytes and credentials at construction', () => {
  const storage = new MemoryStorage();
  const identity = async () => ({
    tenantId: 'tenant-a',
    principalId: 'principal-a',
  });

  assert.throws(
    () => new TenantBoundStorage(
      storage,
      identity,
      {
        purpose: 'uploads',
        dataClass: 'attachment_bytes',
      },
    ),
    /not allowed in device cache/,
  );
  assert.throws(
    () => new TenantBoundStorage(
      storage,
      identity,
      {
        purpose: 'auth',
        dataClass: 'credential',
      },
    ),
    /not allowed in device cache/,
  );
});

test('remove only deletes current tenant namespace', async () => {
  const storage = new MemoryStorage();
  let identity = {
    tenantId: 'tenant-a',
    principalId: 'principal-a',
  };
  const boundary = new TenantBoundStorage(
    storage,
    async () => identity,
    {
      purpose: 'workspace',
      dataClass: 'tenant_cache',
    },
  );

  await boundary.setItem('state', 'a');
  identity = {
    tenantId: 'tenant-b',
    principalId: 'principal-b',
  };
  boundary.invalidateIdentity();
  await boundary.setItem('state', 'b');

  await boundary.removeItem('state');
  assert.equal(await boundary.getItem('state'), null);

  identity = {
    tenantId: 'tenant-a',
    principalId: 'principal-a',
  };
  boundary.invalidateIdentity();
  assert.equal(await boundary.getItem('state'), 'a');
});

test('identity resolver failure is not permanently cached', async () => {
  const storage = new MemoryStorage();
  let attempts = 0;
  const boundary = new TenantBoundStorage(
    storage,
    async () => {
      attempts += 1;
      if (attempts === 1) throw new Error('temporary auth failure');
      return {
        tenantId: 'tenant-a',
        principalId: 'principal-a',
      };
    },
    {
      purpose: 'workspace',
      dataClass: 'tenant_cache',
    },
  );

  await assert.rejects(
    () => boundary.getItem('state'),
    /temporary auth failure/,
  );
  assert.equal(await boundary.getItem('state'), null);
  assert.equal(attempts, 2);
});

test('malformed stored envelope is rejected instead of treated as cache miss', async () => {
  const storage = new MemoryStorage();
  const boundary = new TenantBoundStorage(
    storage,
    async () => ({
      tenantId: 'tenant-a',
      principalId: 'principal-a',
    }),
    {
      purpose: 'workspace',
      dataClass: 'tenant_cache',
    },
  );
  const key = tenantStorageKey('state', 'tenant-a', 'workspace');
  storage.rows.set(key, '{not-json');

  await assert.rejects(
    () => boundary.getItem('state'),
    /envelope is malformed/,
  );
});
