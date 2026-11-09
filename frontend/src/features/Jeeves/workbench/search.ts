import type { RecordKind, Workbench } from './types';

export interface SearchDocument {
  id: string;
  kind: RecordKind;
  projectId: string | null;
  title: string;
  body: string;
  tags: string[];
  updatedAt: number;
  archived: boolean;
  status: string;
}

export interface SearchToken {
  value: string;
  negative: boolean;
  field: 'text' | 'tag' | 'type' | 'status';
  phrase: boolean;
}

export interface SearchQuery {
  tokens: SearchToken[];
  warnings: string[];
}

export interface SearchHit extends SearchDocument {
  score: number;
  excerpt: string;
  matchedTags: string[];
}

export interface SearchOptions {
  projectId?: string | null;
  kinds?: RecordKind[];
  includeArchived?: boolean;
  limit?: number;
  offset?: number;
  sort?: 'relevance' | 'updated' | 'title';
}

export interface SearchResults {
  hits: SearchHit[];
  total: number;
  byKind: Partial<Record<RecordKind, number>>;
  warnings: string[];
  query: SearchQuery;
}

export function normalizeSearch(value: string): string {
  return value.normalize('NFKD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase();
}

export function parseQuery(input: string): SearchQuery {
  const text = input.slice(0, 1000);
  const tokens: SearchToken[] = [];
  const warnings: string[] = [];
  const expression = /(-?)(?:(tag|type|status):)?(?:"([^"]*)"|(\S+))/g;
  for (const match of text.matchAll(expression)) {
    if (tokens.length >= 30) {
      warnings.push('Only the first 30 search terms are used.');
      break;
    }
    const value = normalizeSearch((match[3] ?? match[4] ?? '').trim());
    if (!value) continue;
    tokens.push({
      value,
      negative: match[1] === '-',
      field: (match[2] as SearchToken['field']) || 'text',
      phrase: match[3] !== undefined,
    });
  }
  if ((text.match(/"/g) || []).length % 2) warnings.push('An unmatched quote is treated as ordinary text.');
  if (input.length > 1000) warnings.push('The search query was limited to 1,000 characters.');
  return { tokens, warnings };
}

export function searchDocuments(state: Workbench): SearchDocument[] {
  const archivedProjects = new Set(state.projects.filter(project => project.status === 'archived').map(project => project.id));
  const projects: SearchDocument[] = state.projects.map(project => ({
    id: project.id,
    kind: 'project',
    projectId: project.id,
    title: project.title,
    body: [project.summary, project.goal, project.context, project.engine].join('\n'),
    tags: project.tags,
    updatedAt: project.updatedAt,
    archived: project.status === 'archived',
    status: project.status,
  }));
  const tasks: SearchDocument[] = state.tasks.map(task => ({
    id: task.id,
    kind: 'task',
    projectId: task.projectId,
    title: task.title,
    body: [task.description, ...task.checklist.map(item => item.text)].join('\n'),
    tags: task.tags,
    updatedAt: task.updatedAt,
    archived: archivedProjects.has(task.projectId),
    status: task.status,
  }));
  const notes: SearchDocument[] = state.notes.map(note => ({
    id: note.id,
    kind: 'note',
    projectId: note.projectId,
    title: note.title,
    body: note.body,
    tags: note.tags,
    updatedAt: note.updatedAt,
    archived: note.archived || archivedProjects.has(note.projectId),
    status: note.confidence,
  }));
  const sources: SearchDocument[] = state.sources.map(source => ({
    id: source.id,
    kind: 'source',
    projectId: source.projectId,
    title: source.title,
    body: [source.locator, source.excerpt, source.author].join('\n'),
    tags: source.tags,
    updatedAt: source.updatedAt,
    archived: archivedProjects.has(source.projectId),
    status: source.kind,
  }));
  const cards: SearchDocument[] = state.cards.map(card => ({
    id: card.id,
    kind: 'card',
    projectId: card.projectId,
    title: card.question,
    body: [card.answer, card.hint, card.explanation].join('\n'),
    tags: card.tags,
    updatedAt: card.updatedAt,
    archived: archivedProjects.has(card.projectId),
    status: card.schedule.state,
  }));
  const prompts: SearchDocument[] = state.prompts.map(prompt => ({
    id: prompt.id,
    kind: 'prompt',
    projectId: prompt.projectId,
    title: prompt.title,
    body: [prompt.description, prompt.template].join('\n'),
    tags: prompt.tags,
    updatedAt: prompt.updatedAt,
    archived: prompt.projectId !== null && archivedProjects.has(prompt.projectId),
    status: prompt.favorite ? 'favorite' : 'saved',
  }));
  const sessions: SearchDocument[] = state.sessions.map(session => ({
    id: session.id,
    kind: 'session',
    projectId: session.projectId,
    title: `${session.plannedMinutes}-minute focus session`,
    body: session.reflection,
    tags: [],
    updatedAt: session.updatedAt,
    archived: archivedProjects.has(session.projectId),
    status: session.outcome,
  }));
  return [...projects, ...tasks, ...notes, ...sources, ...cards, ...prompts, ...sessions];
}

function tokenMatch(document: SearchDocument, token: SearchToken): boolean {
  if (token.field === 'tag') return document.tags.some(tag => normalizeSearch(tag) === token.value);
  if (token.field === 'type') return document.kind === token.value;
  if (token.field === 'status') return document.status === token.value;
  return normalizeSearch(`${document.title}\n${document.body}\n${document.tags.join(' ')}`).includes(token.value);
}

function scoreDocument(document: SearchDocument, tokens: SearchToken[]): number {
  const title = normalizeSearch(document.title);
  const body = normalizeSearch(document.body);
  let score = 0;
  for (const token of tokens) {
    if (token.negative) continue;
    if (token.field !== 'text') {
      score += 2;
      continue;
    }
    if (title === token.value) score += 40;
    else if (title.startsWith(token.value)) score += 25;
    else if (title.includes(token.value)) score += 15;
    if (document.tags.some(tag => normalizeSearch(tag) === token.value)) score += 12;
    if (body.includes(token.value)) score += token.phrase ? 8 : 4;
  }
  return score;
}

export function searchExcerpt(text: string, terms: string[], maxLength = 200): string {
  const clean = text.replace(/\s+/g, ' ').trim();
  if (clean.length <= maxLength) return clean;
  const normalized = normalizeSearch(clean);
  const positions = terms.map(term => normalized.indexOf(term)).filter(index => index >= 0);
  const first = positions.length ? Math.min(...positions) : 0;
  const start = Math.max(0, first - Math.floor(maxLength / 3));
  const end = Math.min(clean.length, start + maxLength);
  return `${start > 0 ? '…' : ''}${clean.slice(start, end)}${end < clean.length ? '…' : ''}`;
}

export function searchWorkbench(state: Workbench, input: string, options: SearchOptions = {}): SearchResults {
  const query = parseQuery(input);
  const terms = query.tokens.filter(token => !token.negative && token.field === 'text').map(token => token.value);
  const documents = searchDocuments(state).filter(document => {
    if (!options.includeArchived && document.archived) return false;
    if (options.projectId && document.projectId !== options.projectId && document.projectId !== null) return false;
    if (options.kinds?.length && !options.kinds.includes(document.kind)) return false;
    return query.tokens.every(token => token.negative ? !tokenMatch(document, token) : tokenMatch(document, token));
  });
  const hits: SearchHit[] = documents.map(document => ({
    ...document,
    score: scoreDocument(document, query.tokens),
    excerpt: searchExcerpt(document.body, terms),
    matchedTags: document.tags.filter(tag => terms.some(term => normalizeSearch(tag).includes(term))),
  }));
  hits.sort((a, b) => {
    if (options.sort === 'title') return a.title.localeCompare(b.title) || a.id.localeCompare(b.id);
    if (options.sort === 'updated') return b.updatedAt - a.updatedAt || a.id.localeCompare(b.id);
    return b.score - a.score || b.updatedAt - a.updatedAt || a.id.localeCompare(b.id);
  });
  const byKind: SearchResults['byKind'] = {};
  for (const hit of hits) byKind[hit.kind] = (byKind[hit.kind] || 0) + 1;
  const limit = Math.min(200, Math.max(1, Math.floor(options.limit || 50)));
  const offset = Math.max(0, Math.floor(options.offset || 0));
  return {
    hits: hits.slice(offset, offset + limit),
    total: hits.length,
    byKind,
    warnings: query.warnings,
    query,
  };
}

export function relatedRecords(state: Workbench, id: string, limit = 5): SearchHit[] {
  const documents = searchDocuments(state);
  const original = documents.find(item => item.id === id);
  if (!original) return [];
  const words = normalizeSearch(original.title).split(/\W+/).filter(word => word.length > 3);
  const tags = new Set(original.tags.map(normalizeSearch));
  return documents.filter(item => item.id !== id && item.projectId === original.projectId && !item.archived)
    .map(document => {
      const tagMatches = document.tags.filter(tag => tags.has(normalizeSearch(tag)));
      const title = normalizeSearch(document.title);
      const overlap = words.filter(word => title.includes(word)).length;
      return {
        ...document,
        score: tagMatches.length * 10 + overlap * 3,
        excerpt: searchExcerpt(document.body, words, 140),
        matchedTags: tagMatches,
      };
    })
    .filter(item => item.score > 0)
    .sort((a, b) => b.score - a.score || b.updatedAt - a.updatedAt)
    .slice(0, Math.max(0, limit));
}
