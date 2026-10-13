/** Typed, fail-closed creator input for the canonical Jeeves story ledger.
 * The backend authenticates users, checks canonical game existence, and
 * stores creator-reviewed evidence; this module never infers canon/approval.
 */
import { validProjectId } from './worldWorkspace.ts';

export const STORY_KINDS = [
  'establish', 'dialogue', 'interaction', 'witness', 'discovery',
  'death', 'revival', 'promise', 'resolution', 'departure', 'arrival',
] as const;
export type StoryKind = typeof STORY_KINDS[number];

const SLUG = /^[A-Za-z0-9:_-]{1,96}$/;

export type StoryDraft = {
  eventId: string;
  branchId: string;
  act: string;
  scene: string;
  beat: string;
  kind: StoryKind;
  text: string;
  characterIds: string;
  witnessIds: string;
  speakerId: string;
  threadKey: string;
  knowledgeRequired: string;
  knowledgeGranted: string;
};
export type StoryEventInput = {
  event_id: string;
  branch_id: string;
  act: number;
  scene: number;
  beat: number;
  kind: StoryKind;
  character_ids: string[];
  witness_ids: string[];
  speaker_id: string | null;
  text: string;
  thread_key: string | null;
  knowledge_required: string[];
  knowledge_granted: string[];
  source_thread_id: null;
  source_message_id: null;
};
function slug(value: string, label: string): string {
  const candidate = value.trim();
  if (!SLUG.test(candidate)) throw new Error(label + ' must be a stable 1–96 character identifier.');
  return candidate;
}
function number(value: string, label: string, minimum: number, maximum: number): number {
  if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)) ||
      Number(value) < minimum || Number(value) > maximum) {
    throw new Error(label + ' is outside its supported range.');
  }
  return Number(value);
}
function ids(raw: string, label: string, max: number): string[] {
  if (!raw.trim()) return [];
  const values = raw.split(',').map(value => slug(value, label));
  if (values.length > max || new Set(values).size !== values.length) {
    throw new Error(label + ' exceeds its limit or contains duplicates.');
  }
  return values;
}
export function storyIndexPath(gameId: unknown): string {
  const valid = validProjectId(gameId);
  if (!valid) throw new Error('Choose an existing canonical game before opening its story ledger.');
  return '/api/playable/' + encodeURIComponent(valid) + '/story-index';
}
export function prepareStoryEvent(draft: StoryDraft): StoryEventInput {
  const eventId = slug(draft.eventId, 'Event ID');
  const branchId = slug(draft.branchId, 'Story branch');
  if (!(STORY_KINDS as readonly string[]).includes(draft.kind)) {
    throw new Error('Choose a supported story event kind.');
  }
  const text = draft.text.trim();
  if (!text || text.length > 4000 || [...text].some(ch => {
    const code = ch.charCodeAt(0);
    return code < 32 && code !== 9 && code !== 10;
  })) throw new Error('Story evidence text must be 1–4000 safe characters.');
  const characters = ids(draft.characterIds, 'Characters', 12);
  const witnesses = ids(draft.witnessIds, 'Witnesses', 12);
  if (witnesses.some(id => !characters.includes(id))) {
    throw new Error('Witnesses must also be listed as participants.');
  }
  const speaker = draft.speakerId.trim() ? slug(draft.speakerId, 'Speaker') : null;
  if (speaker && !characters.includes(speaker)) {
    throw new Error('A speaker must be a participant.');
  }
  if (draft.kind === 'dialogue' && !speaker) throw new Error('Dialogue requires its speaker.');
  if (['death', 'revival'].includes(draft.kind) && !characters.length) {
    throw new Error('Life events must name the affected character.');
  }
  const thread = draft.threadKey.trim() ? slug(draft.threadKey, 'Plot thread') : null;
  if (['promise', 'resolution'].includes(draft.kind) && !thread) {
    throw new Error('Promises and resolutions require a plot thread key.');
  }
  return {
    event_id: eventId, branch_id: branchId,
    act: number(draft.act, 'Act', 1, 10000),
    scene: number(draft.scene, 'Scene', 1, 100000),
    beat: number(draft.beat, 'Beat', 0, 100000),
    kind: draft.kind, text, character_ids: characters,
    witness_ids: witnesses, speaker_id: speaker, thread_key: thread,
    knowledge_required: ids(draft.knowledgeRequired, 'Required facts', 20),
    knowledge_granted: ids(draft.knowledgeGranted, 'Granted facts', 20),
    source_thread_id: null, source_message_id: null,
  };
}
