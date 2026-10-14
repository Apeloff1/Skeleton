export interface DragonWisdomReview {
  schema: 'skeleton.dragon.square_review.v1';
  candidate_digest: string;
  artifact_digest: string;
  review_digest: string;
  terminal: boolean;
  release_authority: false;
  reviewed_at: number;
  valid_until: number;
  completed_rounds: number;
  planned_rounds: number;
  squares: readonly {
    id: 'play' | 'craft' | 'delivery' | 'trust';
    label: string;
    score: number;
    industry_score: number | null;
    industry_delta: number | null;
    status: 'blocked' | 'review' | 'improve' | 'ready';
    comparison_state: 'matched_measurements' | 'unknown';
  }[];
  blockers: readonly string[];
  improvements: readonly {
    square: string; axis: string; target: string; priority: string; instruction: string;
  }[];
}

const digest = (value: unknown): boolean => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
const text = (value: unknown, maximum: number): boolean => typeof value === 'string' && value.length > 0 && value.length <= maximum;
const record = (value: unknown): value is Record<string, unknown> => value !== null && typeof value === 'object' && !Array.isArray(value);
const score = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100;

/** Defensive display parsing; receipt authentication belongs to the server. */
export function normalizeDragonWisdomReview(value: unknown): DragonWisdomReview | null {
  if (!record(value)) return null;
  if (value.schema !== 'skeleton.dragon.square_review.v1' || value.terminal !== true || value.release_authority !== false) return null;
  if (!digest(value.candidate_digest) || !digest(value.artifact_digest) || !digest(value.review_digest)) return null;
  if (typeof value.planned_rounds !== 'number' || ![100, 1000, 10000].includes(value.planned_rounds) || value.completed_rounds !== value.planned_rounds) return null;
  if (typeof value.reviewed_at !== 'number' || !Number.isSafeInteger(value.reviewed_at) || value.reviewed_at < 0 || typeof value.valid_until !== 'number' || !Number.isSafeInteger(value.valid_until) || value.valid_until <= value.reviewed_at || value.valid_until > value.reviewed_at + 300) return null;
  if (!Array.isArray(value.squares) || value.squares.length !== 4) return null;
  const ids = ['play', 'craft', 'delivery', 'trust'];
  for (let i = 0; i < ids.length; i++) {
    const square: unknown = value.squares[i];
    if (!record(square) || square.id !== ids[i] || !text(square.label, 80) || !score(square.score)) return null;
    if (typeof square.status !== 'string' || !['blocked', 'review', 'improve', 'ready'].includes(square.status)) return null;
    if (square.comparison_state === 'unknown') {
      if (square.industry_score !== null || square.industry_delta !== null) return null;
    } else if (square.comparison_state === 'matched_measurements') {
      if (!score(square.industry_score) || typeof square.industry_delta !== 'number' || !Number.isFinite(square.industry_delta) ||
          Math.abs(square.score - square.industry_score - square.industry_delta) > .02) return null;
    } else return null;
  }
  if (!Array.isArray(value.blockers) || value.blockers.length > 256 || !value.blockers.every(x => text(x, 1024))) return null;
  if (!Array.isArray(value.improvements) || value.improvements.length > 128) return null;
  for (const item of value.improvements) {
    if (!record(item) || typeof item.square !== 'string' || !ids.includes(item.square) || !text(item.axis, 80) ||
        typeof item.target !== 'string' || !['rival_a', 'rival_b'].includes(item.target) || typeof item.priority !== 'string' || !['critical', 'high', 'normal'].includes(item.priority) ||
        !text(item.instruction, 1024)) return null;
  }
  return value as unknown as DragonWisdomReview;
}


/** A server-authenticated card still needs a current evidence validity window. */
export function normalizeDragonWisdomSnapshot(value: unknown, now: number): {review: DragonWisdomReview; expiresAt: number} | null {
  if (!Number.isFinite(now) || now < 0 || !record(value)) return null;
  const review = normalizeDragonWisdomReview(value.review);
  if (!review || typeof value.issued_at !== 'number' || !Number.isSafeInteger(value.issued_at) ||
      typeof value.expires_at !== 'number' || !Number.isSafeInteger(value.expires_at) ||
      value.issued_at < review.reviewed_at || value.issued_at > review.reviewed_at + 30 ||
      value.issued_at > now || value.expires_at <= now || value.expires_at > review.valid_until ||
      value.expires_at <= value.issued_at) return null;
  return {review, expiresAt: value.expires_at};
}
