/** Bounded creator source documents. These records never restore review or rights. */
export const CREATOR_SCHEMA = 'skeleton.dragon.creator-project.v1' as const;
export const CREATOR_EXPORT_SCHEMA = 'skeleton.dragon.creator-export.v1' as const;
export const CREATOR_MAX_BYTES = 128 * 1024;
// Reserve the portable envelope, schema and SHA fields within the transport cap.
export const CREATOR_MAX_DOCUMENT_BYTES = CREATOR_MAX_BYTES - 256;
export type CreatorHash = (text: string) => Promise<string>;
export interface CreatorProjectDocument {
  schema: typeof CREATOR_SCHEMA;
  title: string;
  style: string;
  targets: string[];
  seed: number;
  portable_design: {
    palette: string; hero: string; quest_theme: string; difficulty: number;
    stages: number; candidates: number; project_notes: string;
    procedural_levels: boolean; campaign_pathing: 'linear' | 'branching';
    challenge_profile: 'gentle' | 'balanced' | 'challenging' | 'spicy';
  };
  authored_puzzles: string[][] | null;
  cited_brief: {text: string; citations: {
    source_id: string; revision_digest: string; title: string; url: string;
  }[]};
}
export interface CreatorProject {
  schema: typeof CREATOR_SCHEMA; project_id: string; version: number;
  document_sha256: string; document: CreatorProjectDocument;
  created_at: string; updated_at: string; source_only: true; approval_restored: false;
  head_version?: number;
}
export type CreatorProjectSummary = Omit<CreatorProject, 'document'> & {
  title: string; style: string; targets: string[];
};
export interface CreatorRevision {
  version: number; title: string; document_sha256: string; created_at: string;
}
export interface CreatorMutation {
  method: 'POST' | 'PUT'; projectId: string | null; body: string;
  document: CreatorProjectDocument; documentCanonical: string;
}
const HEX = /^[a-f0-9]{64}$/;
export const CREATOR_PROJECT_ID = /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const STYLES = new Set(('arcade_score_attack fixed_screen_puzzle world_route_adventure maze_route_adventure top_down_adventure side_scrolling_platformer metroidvania tactical_rpg turn_based_rpg roguelike bullet_hell run_and_gun puzzle_platformer visual_novel rhythm_game fighting_game racing first_person_shooter third_person_action survival_horror immersive_sim city_builder real_time_strategy grand_strategy simulation sports cozy_farming sandbox_builder educational party_game local_coop narrative_adventure').split(' '));
const fields = ['schema','title','style','targets','seed','portable_design','authored_puzzles','cited_brief'];
const designFields = ['palette','hero','quest_theme','difficulty','stages','candidates','project_notes','procedural_levels','campaign_pathing','challenge_profile'];
function record(raw: unknown): raw is Record<string, unknown> {
  return raw !== null && typeof raw === 'object' && !Array.isArray(raw)
    && (Object.getPrototypeOf(raw) === Object.prototype || Object.getPrototypeOf(raw) === null);
}
function closed(raw: unknown, keys: readonly string[]): raw is Record<string, unknown> {
  return record(raw) && Object.keys(raw).length === keys.length && keys.every(k => Object.hasOwn(raw,k));
}
function integer(n: unknown, low: number, high: number): n is number {
  return typeof n === 'number' && Number.isSafeInteger(n) && n >= low && n <= high;
}
function text(raw: unknown, max: number, multiline = false): raw is string {
  return typeof raw === 'string' && [...raw].length <= max
    && !(multiline ? /[\u0000-\u0008\u000b-\u001f]/ : /[\u0000-\u001f]/).test(raw)
    && !/[\ud800-\udfff]/u.test(raw);
}
function targets(raw: unknown): raw is string[] {
  // The server's current target catalogue remains the admission authority.
  return Array.isArray(raw) && raw.length >= 1 && raw.length <= 3
    && raw.every(t => typeof t === 'string' && /^[a-z0-9_]{2,64}$/.test(t))
    && new Set(raw).size === raw.length;
}
function date(raw: unknown): raw is string {
  return typeof raw === 'string' && raw.length <= 64 && Number.isFinite(Date.parse(raw));
}
function choice(raw: unknown, options: readonly string[]): raw is string {
  return typeof raw === 'string' && options.includes(raw);
}
export function creatorBytes(text: string): number { return new TextEncoder().encode(text).length; }
/** Keys are fixed ASCII schema fields, matching Python's sorted UTF-8 JSON. */
export function canonicalCreatorJSON(value: unknown): string {
  const seen = new Set<object>();
  const visit = (item: unknown, depth: number): string => {
    if (depth > 16) throw new Error('Creator JSON is too deeply nested.');
    if (item === null) return 'null';
    if (typeof item === 'string') {
      if (/[\ud800-\udfff]/u.test(item)) throw new Error('Creator JSON contains invalid Unicode.');
      return JSON.stringify(item);
    }
    if (typeof item === 'boolean') return String(item);
    if (typeof item === 'number' && Number.isSafeInteger(item)) return String(item);
    if (typeof item !== 'object' || seen.has(item)) throw new Error('Creator JSON contains an unsupported value.');
    seen.add(item);
    let result: string;
    if (Array.isArray(item)) result = '[' + item.map(v => visit(v,depth+1)).join(',') + ']';
    else {
      if (!record(item)) throw new Error('Creator JSON must contain ordinary objects.');
      result = '{' + Object.keys(item).sort().map(k => JSON.stringify(k)+':'+visit(item[k],depth+1)).join(',') + '}';
    }
    seen.delete(item); return result;
  };
  const result = visit(value,0);
  if (creatorBytes(result) > CREATOR_MAX_BYTES) throw new Error('Creator JSON exceeds 128 KiB.');
  return result;
}
export function normalizeCreatorDocument(raw: unknown): CreatorProjectDocument | null {
  try {
    if (!closed(raw,fields) || raw.schema !== CREATOR_SCHEMA
      || typeof raw.title !== 'string' || !/^[A-Za-z][A-Za-z0-9 ._'!-]{2,79}$/.test(raw.title)
      || typeof raw.style !== 'string' || !STYLES.has(raw.style) || !targets(raw.targets)
      || !integer(raw.seed,0,0xffffffff) || !closed(raw.portable_design,designFields)) return null;
    const d = raw.portable_design;
    if (!choice(d.palette,['dmg_green','cga','vga_dusk','crt_arcade','handheld','modern_neon'])
      || !choice(d.hero,['hatchling','knight','explorer','pilot','astronaut','robot'])
      || !choice(d.quest_theme,['crystals','ancient_ruins','forest','ice','space','volcano','clockwork'])
      || !integer(d.difficulty,1,10) || !integer(d.stages,1,8) || !integer(d.candidates,1,24)
      || typeof d.project_notes !== 'string' || d.project_notes.length > 200
      || !/^[A-Za-z0-9 .,!?_:;'()/+\-]*$/.test(d.project_notes)
      || typeof d.procedural_levels !== 'boolean'
      || !choice(d.campaign_pathing,['linear','branching'])
      || !choice(d.challenge_profile,['gentle','balanced','challenging','spicy'])) return null;
    if (raw.authored_puzzles !== null && !(raw.style === 'fixed_screen_puzzle'
      && !d.procedural_levels && Array.isArray(raw.authored_puzzles) && raw.authored_puzzles.length === d.stages
      && raw.authored_puzzles.every(b => Array.isArray(b) && b.length === 10
        && b.every(row => typeof row === 'string' && /^[#.@$o]{12}$/.test(row))))) return null;
    if (!closed(raw.cited_brief,['text','citations']) || !text(raw.cited_brief.text,12000,true)
      || !Array.isArray(raw.cited_brief.citations) || raw.cited_brief.citations.length > 32) return null;
    for (const c of raw.cited_brief.citations) {
      if (!closed(c,['source_id','revision_digest','title','url']) || !text(c.source_id,128) || !c.source_id
        || typeof c.revision_digest !== 'string' || !HEX.test(c.revision_digest)
        || !text(c.title,200) || !text(c.url,2048) || !/^https?:\/\/[^\s]+$/.test(c.url)) return null;
    }
    const canonical = canonicalCreatorJSON(raw);
    if (creatorBytes(canonical) > CREATOR_MAX_DOCUMENT_BYTES) return null;
    return JSON.parse(canonical) as CreatorProjectDocument;
  } catch { return null; }
}
export async function verifyCreatorProject(raw: unknown, hash: CreatorHash): Promise<CreatorProject | null> {
  if (!record(raw) || raw.schema !== CREATOR_SCHEMA || typeof raw.project_id !== 'string'
    || !CREATOR_PROJECT_ID.test(raw.project_id) || !integer(raw.version,1,512)
    || typeof raw.document_sha256 !== 'string' || !HEX.test(raw.document_sha256)
    || !date(raw.created_at) || !date(raw.updated_at) || raw.source_only !== true || raw.approval_restored !== false
    || raw.head_version !== undefined && !integer(raw.head_version,raw.version,512)) return null;
  const document = normalizeCreatorDocument(raw.document);
  if (!document || await hash(canonicalCreatorJSON(document)) !== raw.document_sha256) return null;
  return {...raw, document} as unknown as CreatorProject;
}
export function normalizeCreatorSummaries(raw: unknown): CreatorProjectSummary[] | null {
  if (!Array.isArray(raw) || raw.length > 32) return null;
  const ids = new Set<string>();
  for (const r of raw) {
    if (!record(r) || r.schema !== CREATOR_SCHEMA || typeof r.project_id !== 'string'
      || !CREATOR_PROJECT_ID.test(r.project_id) || ids.has(r.project_id) || !integer(r.version,1,512)
      || typeof r.document_sha256 !== 'string' || !HEX.test(r.document_sha256)
      || !date(r.created_at) || !date(r.updated_at) || r.source_only !== true || r.approval_restored !== false
      || typeof r.title !== 'string' || !/^[A-Za-z][A-Za-z0-9 ._'!-]{2,79}$/.test(r.title)
      || typeof r.style !== 'string' || !STYLES.has(r.style) || !targets(r.targets)) return null;
    ids.add(r.project_id);
  }
  return JSON.parse(JSON.stringify(raw)) as CreatorProjectSummary[];
}
export function normalizeCreatorHistory(raw: unknown, id: string, beforeVersion?: number): {
  head_version:number; revisions:CreatorRevision[]; next_before_version:number|null;
} | null {
  if (beforeVersion !== undefined && !integer(beforeVersion,2,513)) return null;
  if (!record(raw) || raw.ok !== true || raw.project_id !== id || !integer(raw.head_version,1,512)
    || !Array.isArray(raw.revisions) || raw.revisions.length < 1 || raw.revisions.length > 32) return null;
  let previous = Math.min(raw.head_version,beforeVersion===undefined?512:beforeVersion-1)+1;
  for (const r of raw.revisions) {
    if (!record(r) || !integer(r.version,1,raw.head_version) || r.version !== previous-1
      || beforeVersion !== undefined && r.version >= beforeVersion
      || typeof r.title !== 'string' || !/^[A-Za-z][A-Za-z0-9 ._'!-]{2,79}$/.test(r.title)
      || typeof r.document_sha256 !== 'string' || !HEX.test(r.document_sha256) || !date(r.created_at)) return null;
    previous = r.version;
  }
  const next = raw.next_before_version ?? null;
  const last = raw.revisions.at(-1) as CreatorRevision | undefined;
  if (next !== null && (!integer(next,2,512) || !last || next !== last.version)) return null;
  if (next === null && last?.version !== 1) return null;
  return {head_version:raw.head_version,revisions:JSON.parse(JSON.stringify(raw.revisions)),next_before_version:next};
}
export async function createCreatorExport(document: CreatorProjectDocument, hash: CreatorHash): Promise<string> {
  const normalized = normalizeCreatorDocument(document);
  if (!normalized) throw new Error('The current creator document is invalid.');
  return canonicalCreatorJSON({schema:CREATOR_EXPORT_SCHEMA,document:normalized,
    document_sha256:await hash(canonicalCreatorJSON(normalized))});
}
export async function parseCreatorExport(raw: string, hash: CreatorHash): Promise<CreatorProjectDocument> {
  if (creatorBytes(raw) > CREATOR_MAX_BYTES) throw new Error('Creator import exceeds 128 KiB.');
  let envelope: unknown;
  try { envelope = JSON.parse(raw); } catch { throw new Error('Choose a valid creator project JSON export.'); }
  if (!closed(envelope,['schema','document','document_sha256']) || envelope.schema !== CREATOR_EXPORT_SCHEMA
    || typeof envelope.document_sha256 !== 'string' || !HEX.test(envelope.document_sha256)) throw new Error('This is not a creator source export.');
  const document = normalizeCreatorDocument(envelope.document);
  if (!document || await hash(canonicalCreatorJSON(document)) !== envelope.document_sha256) throw new Error('Creator import failed its document integrity check.');
  return document;
}
/** Freeze each uncertain save; retry sends the original key, CAS and bytes. */
export function createCreatorMutation(document: CreatorProjectDocument, key: string, head: CreatorProject | null): CreatorMutation {
  const copy = normalizeCreatorDocument(document);
  if (!copy || !/^[a-zA-Z0-9_-]{1,128}$/.test(key)) throw new Error('Creator save is invalid.');
  if (head && (!CREATOR_PROJECT_ID.test(head.project_id) || !integer(head.version,1,512)
    || !HEX.test(head.document_sha256))) throw new Error('Creator save has an invalid saved identity.');
  const body = {document:copy,idempotency_key:key,...(head ? {
    expected_version:head.version,expected_sha256:head.document_sha256,
  } : {})};
  return {method:head?'PUT':'POST',projectId:head?.project_id??null,body:JSON.stringify(body),
    document:copy,documentCanonical:canonicalCreatorJSON(copy)};
}
