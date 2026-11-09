import { createHash } from "node:crypto";

export function normalizeBodyText(text) {
  return String(text ?? "").replace(/\s+/g, " ").trim();
}

export function normalizedBodyTextHash(text) {
  return createHash("sha256").update(normalizeBodyText(text)).digest("hex");
}

const IDENTITY_PREFIX_LEN = 64;
const TRIVIAL_LEN_DELTA = 20;
const TRIVIAL_LEN_RATIO = 0.1;
const COLLAPSE_RATIO = 0.5;

export function bodyTextPrefix(text) {
  return normalizeBodyText(text).slice(0, IDENTITY_PREFIX_LEN);
}

export function compareUiVerdicts(current, baseline) {
  const entries = Object.entries(current?.viewports ?? {});
  if (entries.length === 0) {
    return { diverges: true, reasons: ["current verdict has no viewport data"] };
  }

  const reasons = [];
  const baseViewports = baseline?.viewports ?? {};
  for (const [name, cur] of entries) {
    const base = baseViewports[name];
    if (!base) {
      reasons.push(`${name}: no baseline data for this viewport`);
      continue;
    }
    if (cur.status !== base.status) {
      reasons.push(`${name}: HTTP status changed ${base.status} -> ${cur.status}`);
    }
    if (base.title !== undefined && cur.title !== undefined && cur.title !== base.title) {
      reasons.push(`${name}: title changed ("${base.title}" -> "${cur.title}")`);
    }
    if (base.hasCanvas && !cur.hasCanvas) {
      reasons.push(`${name}: canvas disappeared`);
    }
    if (cur.horizontalOverflow && !base.horizontalOverflow) {
      reasons.push(`${name}: horizontal overflow appeared`);
    }

    const baseErrors = (base.consoleErrors?.length ?? 0) + (base.pageErrors?.length ?? 0);
    const currentErrors = (cur.consoleErrors?.length ?? 0) + (cur.pageErrors?.length ?? 0);
    if (currentErrors > 0 && baseErrors === 0) {
      reasons.push(`${name}: console/page errors appeared (${currentErrors})`);
    }

    const baseLen = base.bodyTextLen ?? 0;
    const curLen = cur.bodyTextLen ?? 0;
    if (baseLen > 0 && curLen < baseLen * COLLAPSE_RATIO) {
      reasons.push(`${name}: body text collapsed (${baseLen} -> ${curLen} chars)`);
    } else if (cur.bodyTextHash !== base.bodyTextHash) {
      const tolerance = Math.max(TRIVIAL_LEN_DELTA, baseLen * TRIVIAL_LEN_RATIO);
      if (Math.abs(curLen - baseLen) > tolerance) {
        reasons.push(`${name}: body text changed (${baseLen} -> ${curLen} chars, hash mismatch)`);
      } else if (
        base.bodyTextPrefix !== undefined &&
        cur.bodyTextPrefix !== undefined &&
        cur.bodyTextPrefix !== base.bodyTextPrefix
      ) {
        reasons.push(`${name}: body text replaced (similar length, page start changed)`);
      }
    }
  }

  return { diverges: reasons.length > 0, reasons };
}

export function compareUiVerdictJson(current, rawBaseline) {
  let baseline;
  try {
    baseline = JSON.parse(rawBaseline);
  } catch {
    return { diverges: true, reasons: ["baseline unreadable: invalid JSON"] };
  }
  if (
    baseline === null ||
    typeof baseline !== "object" ||
    Array.isArray(baseline) ||
    baseline.viewports === null ||
    typeof baseline.viewports !== "object" ||
    Array.isArray(baseline.viewports)
  ) {
    return { diverges: true, reasons: ["baseline unreadable: not a verdict object"] };
  }
  return compareUiVerdicts(current, baseline);
}

export function exitCodeForUiVerdict(viewports) {
  const list = Object.values(viewports ?? {});
  if (list.length === 0) return 1;
  if (list.some((view) => (view.status ?? 0) >= 400 || (view.status ?? 0) === 0)) return 1;
  if (
    list.some(
      (view) => (view.consoleErrors?.length ?? 0) > 0 || (view.pageErrors?.length ?? 0) > 0,
    )
  ) {
    return 2;
  }
  return 0;
}
