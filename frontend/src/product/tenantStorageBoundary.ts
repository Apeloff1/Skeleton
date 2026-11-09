export type TenantStorageDataClass =
  | 'public'
  | 'tenant_cache'
  | 'user_draft'
  | 'canonical_reference'
  | 'attachment_bytes'
  | 'credential';

export type TenantStorageIdentity = {
  tenantId: string;
  principalId: string;
};

export type TenantIdentityResolver = () => Promise<TenantStorageIdentity>;

export interface AsyncKeyValueStorage {
  getItem(key: string): Promise<string | null>;
  setItem(key: string, value: string): Promise<void>;
  removeItem?(key: string): Promise<void>;
}

export type TenantBoundStorageOptions = {
  purpose: string;
  dataClass: TenantStorageDataClass;
};

type TenantStorageEnvelope = {
  version: 1;
  tenant_id: string;
  principal_id: string;
  data_class: TenantStorageDataClass;
  purpose: string;
  payload: string;
};

const LOCAL_ALLOWED = new Set<TenantStorageDataClass>([
  'public',
  'tenant_cache',
  'user_draft',
  'canonical_reference',
]);

function normalizedIdentity(value: TenantStorageIdentity): TenantStorageIdentity {
  const tenantId = String(value?.tenantId ?? '').trim();
  const principalId = String(value?.principalId ?? '').trim();
  if (!tenantId || tenantId.length > 256) {
    throw new Error('tenant storage identity is unavailable');
  }
  if (!principalId || principalId.length > 256) {
    throw new Error('tenant storage principal is unavailable');
  }
  return { tenantId, principalId };
}

function normalizedPurpose(value: string): string {
  const purpose = String(value ?? '').trim();
  if (!purpose || purpose.length > 96 || !/^[A-Za-z0-9._:-]+$/.test(purpose)) {
    throw new Error('tenant storage purpose is invalid');
  }
  return purpose;
}

function parseEnvelope(
  raw: string,
  identity: TenantStorageIdentity,
  options: TenantBoundStorageOptions,
): TenantStorageEnvelope {
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    throw new Error('tenant storage envelope is malformed');
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('tenant storage envelope is malformed');
  }
  const row = value as Record<string, unknown>;
  if (row.version !== 1) {
    throw new Error('tenant storage envelope version is unsupported');
  }
  if (row.tenant_id !== identity.tenantId) {
    throw new Error('tenant storage envelope belongs to another tenant');
  }
  if (row.principal_id !== identity.principalId) {
    throw new Error('tenant storage envelope belongs to another principal');
  }
  if (row.data_class !== options.dataClass) {
    throw new Error('tenant storage data classification drift');
  }
  if (row.purpose !== options.purpose) {
    throw new Error('tenant storage purpose drift');
  }
  if (typeof row.payload !== 'string') {
    throw new Error('tenant storage payload is malformed');
  }
  return row as TenantStorageEnvelope;
}

/**
 * Privacy-minimizing namespace only; never an authorization token.
 *
 * The storage key intentionally avoids embedding raw tenant identifiers
 * (including email addresses) in local-storage key names. The exact tenant and
 * principal remain inside the envelope and are verified on every read.
 *
 * FNV-1a is used only as a deterministic opaque namespace fingerprint. It is
 * not a secret or cryptographic identity proof.
 */
function tenantFingerprint(tenantId: string): string {
  const tenant = String(tenantId ?? '').trim();
  if (!tenant) throw new Error('tenant identity is required');

  // Two independent 32-bit lanes keep this portable across web and React
  // Native/Hermes. This is namespace obfuscation only; authorization still
  // comes from the exact tenant/principal envelope checks.
  let left = 0x811c9dc5;
  let right = 0x9e3779b9;
  for (let index = 0; index < tenant.length; index += 1) {
    const code = tenant.charCodeAt(index);
    left = Math.imul(left ^ code, 0x01000193) >>> 0;
    right = Math.imul(right ^ (code + index + 1), 0x85ebca6b) >>> 0;
  }
  return left.toString(16).padStart(8, '0')
    + right.toString(16).padStart(8, '0');
}

export function tenantStorageKey(
  baseKey: string,
  tenantId: string,
  purpose: string,
): string {
  const key = String(baseKey ?? '').trim();
  const normalized = normalizedPurpose(purpose);
  if (!key) throw new Error('storage key is required');
  return [
    '@tenant',
    tenantFingerprint(tenantId),
    normalized,
    encodeURIComponent(key),
  ].join('/');
}

export class TenantBoundStorage implements AsyncKeyValueStorage {
  private readonly storage: AsyncKeyValueStorage;
  private readonly resolveIdentity: TenantIdentityResolver;
  private readonly purpose: string;
  private readonly dataClass: TenantStorageDataClass;
  private identityPromise: Promise<TenantStorageIdentity> | null = null;

  constructor(
    storage: AsyncKeyValueStorage,
    resolveIdentity: TenantIdentityResolver,
    options: TenantBoundStorageOptions,
  ) {
    if (!storage || typeof storage.getItem !== 'function' || typeof storage.setItem !== 'function') {
      throw new Error('tenant storage backend is invalid');
    }
    if (typeof resolveIdentity !== 'function') {
      throw new Error('tenant identity resolver is required');
    }
    this.storage = storage;
    this.resolveIdentity = resolveIdentity;
    this.purpose = normalizedPurpose(options.purpose);
    this.dataClass = options.dataClass;
    if (!LOCAL_ALLOWED.has(this.dataClass)) {
      throw new Error(
        `data class ${this.dataClass} is not allowed in device cache`,
      );
    }
  }

  private identity(): Promise<TenantStorageIdentity> {
    if (this.identityPromise === null) {
      this.identityPromise = Promise.resolve()
        .then(() => this.resolveIdentity())
        .then(normalizedIdentity)
        .catch(error => {
          this.identityPromise = null;
          throw error;
        });
    }
    return this.identityPromise;
  }

  private options(): TenantBoundStorageOptions {
    return {
      purpose: this.purpose,
      dataClass: this.dataClass,
    };
  }

  async getItem(key: string): Promise<string | null> {
    const identity = await this.identity();
    const scopedKey = tenantStorageKey(key, identity.tenantId, this.purpose);
    const raw = await this.storage.getItem(scopedKey);
    if (raw === null) return null;
    return parseEnvelope(raw, identity, this.options()).payload;
  }

  async setItem(key: string, value: string): Promise<void> {
    if (typeof value !== 'string') {
      throw new Error('tenant storage payload must be text');
    }
    const identity = await this.identity();
    const scopedKey = tenantStorageKey(key, identity.tenantId, this.purpose);
    const envelope: TenantStorageEnvelope = {
      version: 1,
      tenant_id: identity.tenantId,
      principal_id: identity.principalId,
      data_class: this.dataClass,
      purpose: this.purpose,
      payload: value,
    };
    await this.storage.setItem(scopedKey, JSON.stringify(envelope));
  }

  async removeItem(key: string): Promise<void> {
    if (typeof this.storage.removeItem !== 'function') {
      throw new Error('tenant storage backend cannot remove values');
    }
    const identity = await this.identity();
    const scopedKey = tenantStorageKey(key, identity.tenantId, this.purpose);
    await this.storage.removeItem(scopedKey);
  }

  /** Force identity re-resolution after an explicit account transition. */
  invalidateIdentity(): void {
    this.identityPromise = null;
  }
}

export function createTenantBoundStorage(
  storage: AsyncKeyValueStorage,
  resolveIdentity: TenantIdentityResolver,
  options: TenantBoundStorageOptions,
): TenantBoundStorage {
  return new TenantBoundStorage(storage, resolveIdentity, options);
}
