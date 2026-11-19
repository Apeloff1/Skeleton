export interface GameBuilderArtifact {
  readonly category: string;
  readonly data: string;
  readonly createdAt: number;
}

const DEFAULT_MAX_AGE_MS = 30 * 60 * 1000;
const DEFAULT_DESCRIPTION_LIMIT = 1800;
const DEFAULT_HANDOFF_PAYLOAD_LIMIT = 32 * 1024;

let pendingArtifact: GameBuilderArtifact | null = null;

function normalizeCategory(category: string): string {
  const normalized = String(category || 'game')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return normalized.slice(0, 48) || 'game';
}

function serializeArtifact(data: unknown): string {
  if (typeof data === 'string') return data;
  try {
    const serialized = JSON.stringify(data, null, 2);
    if (serialized !== undefined) return serialized;
  } catch {
    return '[unserializable artifact]';
  }

  try {
    return String(data);
  } catch {
    return '[unserializable artifact]';
  }
}

function boundedPayload(data: unknown, maxLength = DEFAULT_HANDOFF_PAYLOAD_LIMIT): string {
  const limit = Number.isFinite(maxLength)
    ? Math.max(256, Math.floor(maxLength))
    : DEFAULT_HANDOFF_PAYLOAD_LIMIT;
  const serialized = serializeArtifact(data).trim();
  if (serialized.length <= limit) return serialized;
  return `${serialized.slice(0, limit - 1)}…`;
}

export function queueGameBuilderArtifact(data: unknown, category: string): GameBuilderArtifact {
  const artifact = Object.freeze({
    category: normalizeCategory(category),
    data: boundedPayload(data),
    createdAt: Date.now(),
  });
  pendingArtifact = artifact;
  return artifact;
}

export function consumeGameBuilderArtifact(maxAgeMs = DEFAULT_MAX_AGE_MS): GameBuilderArtifact | null {
  const artifact = pendingArtifact;
  pendingArtifact = null;

  if (!artifact || !Number.isFinite(maxAgeMs)) return null;
  const age = Date.now() - artifact.createdAt;
  const ageLimit = Math.max(0, Math.floor(maxAgeMs));
  if (!Number.isFinite(age) || age < 0 || age > ageLimit) return null;
  return artifact;
}

export function formatGameBuilderDescription(
  artifact: GameBuilderArtifact,
  maxLength = DEFAULT_DESCRIPTION_LIMIT,
): string {
  const limit = Number.isFinite(maxLength)
    ? Math.max(160, Math.floor(maxLength))
    : DEFAULT_DESCRIPTION_LIMIT;
  const prefix = `Build a complete game around this AI-generated ${artifact.category} seed. Preserve its useful constraints and integrate it coherently with the rest of the game.\n\nSeed:\n`;
  const serialized = artifact.data.trim();
  const available = Math.max(0, limit - prefix.length);

  if (serialized.length <= available) return `${prefix}${serialized}`;
  if (available <= 1) return prefix.slice(0, limit);
  return `${prefix}${serialized.slice(0, available - 1)}…`;
}
