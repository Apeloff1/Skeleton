export interface GameBuilderArtifact {
  category: string;
  data: string;
  createdAt: number;
}

const DEFAULT_MAX_AGE_MS = 30 * 60 * 1000;
const DEFAULT_DESCRIPTION_LIMIT = 1800;
const DEFAULT_HANDOFF_PAYLOAD_LIMIT = 32 * 1024;

let pendingArtifact: GameBuilderArtifact | null = null;

function normalizeCategory(category: string): string {
  const normalized = String(category || 'game').trim().toLowerCase();
  return normalized.slice(0, 48) || 'game';
}

function serializeArtifact(data: unknown): string {
  if (typeof data === 'string') return data;
  try {
    const serialized = JSON.stringify(data, null, 2);
    return serialized === undefined ? String(data) : serialized;
  } catch {
    return String(data);
  }
}

function boundedPayload(data: unknown, maxLength = DEFAULT_HANDOFF_PAYLOAD_LIMIT): string {
  const limit = Math.max(256, Math.floor(maxLength));
  const serialized = serializeArtifact(data).trim();
  if (serialized.length <= limit) return serialized;
  return `${serialized.slice(0, limit - 1)}…`;
}

export function queueGameBuilderArtifact(data: unknown, category: string): GameBuilderArtifact {
  pendingArtifact = {
    category: normalizeCategory(category),
    data: boundedPayload(data),
    createdAt: Date.now(),
  };
  return pendingArtifact;
}

export function consumeGameBuilderArtifact(maxAgeMs = DEFAULT_MAX_AGE_MS): GameBuilderArtifact | null {
  const artifact = pendingArtifact;
  pendingArtifact = null;

  if (!artifact) return null;
  const age = Date.now() - artifact.createdAt;
  if (!Number.isFinite(age) || age < 0 || age > Math.max(0, maxAgeMs)) return null;
  return artifact;
}

export function formatGameBuilderDescription(
  artifact: GameBuilderArtifact,
  maxLength = DEFAULT_DESCRIPTION_LIMIT,
): string {
  const limit = Math.max(160, Math.floor(maxLength));
  const prefix = `Build a complete game around this AI-generated ${artifact.category} seed. Preserve its useful constraints and integrate it coherently with the rest of the game.\n\nSeed:\n`;
  const serialized = artifact.data.trim();
  const available = Math.max(0, limit - prefix.length);

  if (serialized.length <= available) return `${prefix}${serialized}`;
  if (available <= 1) return prefix.slice(0, limit);
  return `${prefix}${serialized.slice(0, available - 1)}…`;
}
