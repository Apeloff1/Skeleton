// B040 eval arena helpers (S2/S3/S6, Coder Lead). Dependency-free, offline-testable.
// Never logs raw generated output, tokens or env values.
export const DIMS = ['correctness', 'editability', 'latency', 'cost', 'safety'];
const CASE_RE = /^B040-[A-Z]{2,8}-[0-9]{3}$/;

// --- S2: thresholds, result + baseline validation ------------------------
export function passes(passIf, value) {
  if (value === null || value === undefined) return null;
  const m = /^(>=|<=|==) (-?[0-9.]+)$/.exec(passIf);
  if (!m) throw new Error(`bad pass_if: ${passIf}`);
  const t = Number(m[2]);
  return m[1] === '>=' ? value >= t : m[1] === '<=' ? value <= t : value === t;
}

export function validateResult(r) {
  const errs = [];
  const need = ['run_id', 'set_version', 'candidate', 'git_sha', 'started_at', 'cases'];
  for (const k of need) if (!(k in r)) errs.push(`missing ${k}`);
  if (r.git_sha !== undefined && !/^[0-9a-f]{7,40}$/.test(r.git_sha)) errs.push('git_sha');
  for (const c of r.cases || []) {
    if (!CASE_RE.test(c.case_id || '')) errs.push(`case_id ${c.case_id}`);
    if (!['passed', 'failed', 'error', 'skipped'].includes(c.status)) errs.push(`status ${c.case_id}`);
    const keys = Object.keys(c.scores || {}).sort();
    if (JSON.stringify(keys) !== JSON.stringify([...DIMS].sort())) errs.push(`dims ${c.case_id}`);
    for (const d of DIMS) {
      const s = (c.scores || {})[d];
      if (!s || !('value' in s) || !('passed' in s)) errs.push(`${c.case_id}.${d}`);
    }
  }
  return errs;
}

export function caseStatus(scores) {
  // AC5: any safety failure fails the case, regardless of the rest.
  if (scores.safety.passed === false) return 'failed';
  const decided = DIMS.map(d => scores[d].passed).filter(p => p !== null);
  if (decided.length === 0) return 'skipped';
  return decided.every(Boolean) ? 'passed' : 'failed';
}

export function makeBaseline(result, tolerance) {
  const cases = {};
  for (const c of result.cases) {
    if (c.status !== 'passed') continue;
    cases[`${c.case_id}@${c.version}`] = Object.fromEntries(DIMS.map(d => [d, c.scores[d].value]));
  }
  return { set_version: result.set_version, candidate: result.candidate, source_run_id: result.run_id, tolerance, cases };
}

// Higher-is-better dims compare absolute drop; latency/cost compare relative rise.
export function compareToBaseline(result, baseline) {
  const regressions = [];
  for (const c of result.cases) {
    const b = baseline.cases[`${c.case_id}@${c.version}`];
    if (!b) continue;
    for (const d of DIMS) {
      const now = c.scores[d].value, was = b[d], tol = baseline.tolerance[d];
      if (now === null || was === null || was === undefined) continue;
      const worse = d === 'latency' || d === 'cost'
        ? now > was * (1 + tol)
        : d === 'safety' ? now > was + tol : now < was - tol;
      if (worse) regressions.push({ case_id: c.case_id, dimension: d, baseline: was, current: now });
    }
  }
  return regressions;
}

// --- S3: Tier 2 runner (correctness + latency), reuses the #4098 flow ----
export async function runCase(evalCase, { fetch, baseUrl, headers = {}, now = () => Date.now(),
  sleep = ms => new Promise(r => setTimeout(r, ms)), pollMs = 5000, timeoutS = 600 }) {
  const t0 = now();
  const j = async (path, init) => {
    const r = await fetch(`${baseUrl}${path}`, { ...init, headers: { 'content-type': 'application/json', ...headers } });
    if (!r.ok) throw new Error(`HTTP ${r.status} on ${path.split('?')[0]}`);
    return r.json();
  };
  const scores = Object.fromEntries(DIMS.map(d => [d, { value: null, passed: null, reason: 'not measured in S3' }]));
  let buildId = null;
  try {
    const created = await j('/galaxy-studio/create', { method: 'POST', body: JSON.stringify({ ...evalCase.brief, seed: evalCase.seed }) });
    buildId = created.build_id || created.id || (created.build || {}).build_id || null;
    if (!buildId) throw new Error('no build_id');
    await j('/galaxy-studio/start-build', { method: 'POST', body: JSON.stringify({ build_id: buildId }) });
    let st = {};
    for (;;) {
      st = await j(`/galaxy-studio/status/${encodeURIComponent(buildId)}`, { method: 'GET' });
      if (['completed', 'failed', 'error'].includes(st.status)) break;
      if ((now() - t0) / 1000 > timeoutS) { st = { status: 'timeout' }; break; }
      await sleep(pollMs);
    }
    const secs = (now() - t0) / 1000;
    const ok = st.status === 'completed' && (st.file_count || 0) > 0 ? 1 : 0;
    scores.correctness = { value: ok, passed: passes(evalCase.dimensions.correctness.pass_if, ok), reason: `status=${st.status}` };
    scores.latency = { value: secs, passed: st.status === 'completed' ? passes(evalCase.dimensions.latency.pass_if, secs) : false };
    return { case_id: evalCase.case_id, version: evalCase.version, seed: evalCase.seed, build_id: buildId, status: caseStatus(scores), scores };
  } catch (e) {
    scores.correctness = { value: 0, passed: false, reason: String(e.message).slice(0, 120) };
    return { case_id: evalCase.case_id, version: evalCase.version, seed: evalCase.seed, build_id: buildId, status: 'error', scores };
  }
}

export async function runSet(cases, meta, opts) {
  const out = [];
  for (const c of cases) out.push(await runCase(c, opts));
  return { ...meta, cases: out };
}

// --- S6: editability scoring + B039 failure export -----------------------
// edits: [{instruction, applied: bool, build_ok: bool}] from a future edit API (B020).
export function scoreEditability(evalCase, edits) {
  if (!Array.isArray(edits) || edits.length === 0) return { value: null, passed: null, reason: 'no edit API (B020) yet' };
  const ok = edits.filter(e => e.applied === true && e.build_ok === true).length;
  const v = ok / edits.length;
  return { value: v, passed: passes(evalCase.dimensions.editability.pass_if, v) };
}

export const FAILURE_EXPORT_VERSION = 1;
export function toFailureExport(result, budget = { max_mutations: 5, max_seconds: 600, max_usd: 1 }) {
  const failures = [];
  for (const c of result.cases) {
    if (c.status !== 'failed' && c.status !== 'error') continue;
    const failed = DIMS.filter(d => c.scores[d].passed === false)
      .map(d => ({ dimension: d, value: c.scores[d].value, reason: c.scores[d].reason || null }));
    failures.push({ case_id: c.case_id, version: c.version, seed: c.seed, build_id: c.build_id ?? null,
      status: c.status, failed_dimensions: failed, repairable: !failed.some(f => f.dimension === 'safety') });
  }
  return { format: 'b040-failure-export', format_version: FAILURE_EXPORT_VERSION, run_id: result.run_id,
    set_version: result.set_version, candidate: result.candidate, git_sha: result.git_sha, budget, failures };
}
