/** Acceptance gate for the existing universal Scene Forge API response.
 *
 * A network response or JSON body is not evidence that scene assets were
 * mounted. This pure projection is fail-closed and checks the exact requested
 * game ID, mounted flag, counts, selected categories and truncation semantics.
 */
export type SceneForgeRequestItem = Readonly<{ category: string; count: number }>;
export type SceneForgeDecision = Readonly<{
  accepted: boolean;
  reason: string | null;
  count: number;
  clamped: boolean;
}>;

function object(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : null;
}

function integer(value: unknown, minimum = 0): value is number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= minimum;
}

const reject = (reason: string): SceneForgeDecision => ({
  accepted: false, reason, count: 0, clamped: false,
});

export function acceptSceneForgeResponse(
  httpOk: boolean,
  raw: unknown,
  expectedBuildId: string,
  requested: readonly SceneForgeRequestItem[],
): SceneForgeDecision {
  if (!httpOk) return reject('Scene Forge returned an unsuccessful HTTP response.');
  const result = object(raw);
  if (!result || typeof expectedBuildId !== 'string' || !expectedBuildId ||
      result.build_id !== expectedBuildId) {
    return reject('Scene Forge response did not match the selected game.');
  }
  if (result.mounted !== true || result.clamped !== true && result.clamped !== false) {
    return reject('Asset mounting was not confirmed by Scene Forge.');
  }
  if (!Array.isArray(requested) || !requested.length || requested.length > 100 ||
      !Array.isArray(result.composed) || result.composed.length > requested.length) {
    return reject('Scene composition details are missing or invalid.');
  }
  if (!integer(result.total, 1) || !integer(result.primary, 1) ||
      !integer(result.variants) || result.total !== result.primary + result.variants) {
    return reject('Scene Forge asset totals are inconsistent.');
  }

  const expected = new Map<string, number>();
  for (const item of requested) {
    if (typeof item?.category !== 'string' || !/^[a-z0-9_][a-z0-9_-]{0,127}$/.test(item.category) ||
        !integer(item.count, 1) || item.count > 200 || expected.has(item.category)) {
      return reject('Requested scene items are invalid.');
    }
    expected.set(item.category, item.count);
  }
  const seen = new Set<string>();
  let primary = 0;
  for (const item of result.composed) {
    const row = object(item);
    const category = row?.category;
    const count = row?.count;
    if (typeof category !== 'string' || !expected.has(category) ||
        seen.has(category) || !integer(count, 1) || count > expected.get(category)!) {
      return reject('Forge returned an unrecognized or inconsistent scene item.');
    }
    seen.add(category);
    primary += count;
  }
  if (!seen.size || primary !== result.primary) {
    return reject('Forge returned incomplete primary-asset accounting.');
  }
  if (!result.clamped &&
      (seen.size !== expected.size ||
       [...expected].some(([category, count]) =>
         !seen.has(category) || !result.composed.some((row: unknown) => {
           const item = object(row);
           return item?.category === category && item.count === count;
         })))) {
    return reject('Forge output did not match the requested composition.');
  }
  return { accepted: true, reason: null, count: result.total, clamped: result.clamped };
}
