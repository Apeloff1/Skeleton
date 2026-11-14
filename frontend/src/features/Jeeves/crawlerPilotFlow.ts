/**
 * Human-facing Dragon crawler pilot policy: validation and truthful stage
 * summaries only. Does not perform DNS checks or grant network authority.
 * The existing canonical backend remains the only admission/runtime owner.
 */
import type {
  CrawlAtlasReport, CrawlCreate, CrawlerReadiness, CrawlSession, CapturedSource,
} from '../../product/crawlerClient';

export const PILOT_STAGES = [
  { id: 'scope', label: 'Scope & consent', help: 'Pick explicit public sources and strict limits.' },
  { id: 'capture', label: 'Capture', help: 'Run only committed, bounded crawler operations.' },
  { id: 'sources', label: 'Source library', help: 'Inspect current, unreviewed external captures.' },
  { id: 'research', label: 'Research Atlas', help: 'Form source-linked research questions.' },
  { id: 'review', label: 'Human review', help: 'Review candidate design references with rights.' },
  { id: 'receipt', label: 'Pilot receipt', help: 'Inspect holds, export status and next steps.' },
] as const;
export type PilotStage = typeof PILOT_STAGES[number]['id'];

export type PilotForm = {
  title: string;
  seedText: string;
  topicText: string;
  maxRequests: string;
  maxDocuments: string;
  maxMib: string;
  maxDepth: string;
  discoverSitemaps: boolean;
  balanceHosts: boolean;
  consent: boolean;
  rights: boolean;
};

export const EMPTY_PILOT_FORM: PilotForm = {
  title: 'Dragon research mission',
  seedText: '',
  topicText: '',
  maxRequests: '12',
  maxDocuments: '8',
  maxMib: '4',
  maxDepth: '1',
  discoverSitemaps: false,
  balanceHosts: true,
  consent: false,
  rights: false,
};

export class PilotFormError extends Error {
  readonly code: string;
  constructor(code: string, message: string) {
    super(message);
    this.name = 'PilotFormError';
    this.code = code;
  }
}

function finiteInt(raw: string, name: string, low: number, high: number): number {
  if (!/^(0|[1-9][0-9]{0,4})$/.test(raw)) {
    throw new PilotFormError('invalid_budget', name + ' must be a whole number.');
  }
  const n = Number(raw);
  if (!Number.isSafeInteger(n) || n < low || n > high) {
    throw new PilotFormError('invalid_budget', name + ' must be between ' + low + ' and ' + high + '.');
  }
  return n;
}

/** Pure preflight. Actual host/DNS/robots/SSRF policy executes in the backend. */
export function previewPilotScope(seedText: string): {
  seeds: string[]; hosts: string[]; requestHostCount: number;
} {
  if (typeof seedText !== 'string' || seedText.length > 32768) {
    throw new PilotFormError('seed_size', 'Seed list exceeds its finite input limit.');
  }
  const lines = seedText.split(/\r?\n/).map(x => x.trim()).filter(Boolean);
  if (lines.length < 1 || lines.length > 16) {
    throw new PilotFormError('seed_count', 'Provide between 1 and 16 source URLs, one per line.');
  }
  const seeds: string[] = [];
  const hosts = new Set<string>();
  for (const raw of lines) {
    if (raw.length > 2048 || /[\s\u0000-\u001f]/.test(raw)) {
      throw new PilotFormError('seed_invalid', 'Use complete URLs without spaces or control characters.');
    }
    let url: URL;
    try { url = new URL(raw); }
    catch { throw new PilotFormError('seed_invalid', 'A complete HTTPS URL is required for every source.'); }
    const host = url.hostname.toLowerCase();
    if (url.protocol !== 'https:' || !!url.username || !!url.password || !!url.port
      || !!url.hash || !host.includes('.') || /(^|\.)localhost$/.test(host)
      || /(^|\.)(internal|local|test|invalid|example)$/.test(host)
      || /^\[/.test(host) || /^[0-9.]+$/.test(host)
      || !/^[a-z0-9.-]{3,253}$/.test(host)
      || host.includes('..') || host.startsWith('.') || host.endsWith('.')) {
      throw new PilotFormError('seed_invalid', 'Use credential-free HTTPS public DNS hostnames without custom ports or fragments.');
    }
    const normalized = url.toString();
    if (seeds.includes(normalized)) {
      throw new PilotFormError('seed_duplicate', 'Each source URL must be unique.');
    }
    seeds.push(normalized);
    hosts.add(host);
  }
  if (hosts.size > 16) {
    throw new PilotFormError('host_capacity', 'The pilot supports at most 16 distinct hostnames.');
  }
  return { seeds, hosts: [...hosts].sort(), requestHostCount: hosts.size };
}

export function preparePilotCreate(form: PilotForm, idempotencyKey: string): CrawlCreate {
  if (!form || typeof form !== 'object'
    || form.consent !== true || form.rights !== true) {
    throw new PilotFormError('consent_missing', 'Explicit capture authorization and source rights acknowledgement are both required.');
  }
  if (!/^[^\u0000-\u001f]{1,160}$/.test(form.title.trim())) {
    throw new PilotFormError('title_invalid', 'Use a mission title of 1–160 characters.');
  }
  if (!/^[A-Za-z0-9:._-]{1,128}$/.test(idempotencyKey)) {
    throw new PilotFormError('command_invalid', 'The trusted operation key was missing.');
  }
  const scope = previewPilotScope(form.seedText);
  const max_requests = finiteInt(form.maxRequests, 'Requests', 1, 128);
  const max_documents = finiteInt(form.maxDocuments, 'Documents', 1, 64);
  const maxMib = finiteInt(form.maxMib, 'Total MiB', 1, 32);
  const max_depth = finiteInt(form.maxDepth, 'Link depth', 0, 3);
  if (max_documents > max_requests) {
    throw new PilotFormError('capacity_mismatch', 'Document budget cannot exceed request budget.');
  }
  if (form.topicText.length > 1280) {
    throw new PilotFormError('topic_size', 'Topic filters exceed their finite input limit.');
  }
  const topics = form.topicText.split(/[\s,]+/).filter(Boolean);
  if (topics.length > 16 || topics.some(x => x.length > 80 || !/^[\p{L}\p{N}_.-]+$/u.test(x))) {
    throw new PilotFormError('topic_invalid', 'Use no more than 16 short topic terms.');
  }
  if (typeof form.discoverSitemaps !== 'boolean' || typeof form.balanceHosts !== 'boolean') {
    throw new PilotFormError('options_invalid', 'Explicit discovery and frontier options are required.');
  }
  return {
    title: form.title.trim(), idempotency_key: idempotencyKey,
    seeds: scope.seeds, topics,
    max_requests, max_documents, max_bytes: maxMib * 1048576,
    max_depth, discover_sitemaps: form.discoverSitemaps,
    frontier_strategy: form.balanceHosts ? 'balanced' : 'fifo',
    consent: true, rights_acknowledged: true,
  };
}

export type PilotGate = {
  id: PilotStage | 'release';
  title: string;
  status: 'ready' | 'blocked' | 'pending' | 'review';
  reason: string;
};

export function derivePilotGates(input: {
  readiness: CrawlerReadiness | null;
  session: CrawlSession | null;
  sources: CapturedSource[];
  atlas: CrawlAtlasReport | null;
  canWrite: boolean;
}): PilotGate[] {
  const { readiness, session, sources, atlas, canWrite } = input;
  const configured = readiness?.available === true;
  const validSession = !!session && session.consent_current;
  const committed = !!session && session.counters.requests > 0;
  const eligibleSources = sources.filter(item => item.freshness?.state === 'current');
  const atlasCurrent = !!atlas && !!session && atlas.session_id === session.session_id
    && atlas.source_policy.included_source_count > 0
    && atlas.pilot_qualification?.read_only === true;
  const pilot = atlasCurrent ? atlas!.pilot_qualification : null;
  const releaseHeld = true;
  return [
    {
      id: 'scope', title: 'Account and crawler admission',
      status: configured && canWrite ? 'ready' : 'blocked',
      reason: !canWrite ? 'Editor or administrator access is required to start capture.'
        : configured ? 'Use explicit consent and per-source rights before starting.'
          : readiness?.action || readiness?.message || 'Crawler storage and engine readiness have not been verified.',
    },
    {
      id: 'capture', title: 'Durable bounded acquisition',
      status: !session ? 'pending' : !validSession ? 'blocked' : committed ? 'ready' : 'pending',
      reason: !session ? 'Create or select an owned research session.'
        : !validSession ? 'Consent expired or the session is no longer usable for new acquisition.'
          : !committed ? 'A bounded request slice has not been committed yet.'
            : 'Counters reflect committed operations, not simulated or requested downloads.',
    },
    {
      id: 'sources', title: 'Source custody',
      status: !session ? 'pending' : eligibleSources.length ? 'ready' : 'blocked',
      reason: eligibleSources.length
        ? eligibleSources.length + ' currently usable retained sources; all remain unreviewed external evidence.'
        : 'Capture reviewable sources and confirm current source-use policy.',
    },
    {
      id: 'research', title: 'Exact-snapshot research',
      status: !atlasCurrent ? 'pending'
        : pilot?.pilot_status === 'ready_for_human_review' ? 'ready' : 'review',
      reason: !atlasCurrent ? 'Run the Atlas against the current owned session.'
        : pilot?.pilot_status === 'ready_for_human_review'
          ? 'Source-only research is ready for independent human review, not publication.'
          : (pilot?.blocked_checks || []).join(', ') || 'Source and policy holds require operator attention.',
    },
    {
      id: 'review', title: 'Human source and design review',
      status: atlasCurrent ? 'review' : 'pending',
      reason: 'Approval needs an independent human, verified source rights and an authoritative review receipt.',
    },
    {
      id: 'receipt', title: 'Pilot exit receipt',
      status: pilot ? 'review' : 'pending',
      reason: pilot ? 'Deterministic source-only receipt exists; production gates remain independent.'
        : 'A current Atlas receipt is required before pilot-exit review.',
    },
    {
      id: 'release', title: 'Production release',
      status: releaseHeld ? 'blocked' : 'ready',
      reason: 'Requires exact-head CI/security, device and offline tests, installation, recovery, provenance, rollback and human approval; this interface cannot certify release.',
    },
  ];
}
