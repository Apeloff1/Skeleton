import React, { useMemo, useState } from 'react';
import { Text, View } from 'react-native';
import { searchWorkbench } from './search';
import type { SearchHit, SearchOptions } from './search';
import { Action, Badge, Choice, Empty, Field, Section, Toggle, styles } from './ui';
import type { PanelProps } from './ui';

export function SearchPanel({ state, project, open }: PanelProps & { open: (hit: SearchHit) => void }) {
  const [query, setQuery] = useState('');
  const [everyProject, setEveryProject] = useState(false);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [sort, setSort] = useState<NonNullable<SearchOptions['sort']>>('relevance');
  const [page, setPage] = useState(0);
  const results = useMemo(() => searchWorkbench(state, query, {
    projectId: everyProject ? undefined : project.id,
    includeArchived,
    sort,
    limit: 30,
    offset: page * 30,
  }), [state, query, everyProject, project.id, includeArchived, sort, page]);
  return (
    <View style={styles.stack}>
      <Section title="Find your work" subtitle={'Search titles, content, tags and reflections. Try type:note, tag:physics, status:doing, "exact phrase", or -excluded.'}>
        <Field label="Search workbench" value={query} maxLength={1000} onChange={value => { setQuery(value); setPage(0); }} />
        <Toggle label="Search all projects" value={everyProject} onChange={value => { setEveryProject(value); setPage(0); }} />
        <Toggle label="Include archived work" value={includeArchived} onChange={value => { setIncludeArchived(value); setPage(0); }} />
        <Choice label="Sort results" value={sort} values={['relevance', 'updated', 'title']} onChange={value => { setSort(value); setPage(0); }} />
        <View style={styles.wrap}>{Object.entries(results.byKind).map(([kind, count]) => <Badge key={kind} text={`${kind}: ${count}`} />)}</View>
        {results.warnings.map(warning => <Text key={warning} style={styles.error}>{warning}</Text>)}
      </Section>
      <Section title={`${results.total} matching records`}>
        {!results.hits.length && <Empty icon="search-outline" title="No matches" message="Try fewer terms, include archived work, or search all projects." />}
        {results.hits.map(hit => <View key={`${hit.kind}-${hit.id}`} style={styles.card}>
          <View style={styles.wrap}><Badge text={hit.kind} tone="accent" />{hit.status && <Badge text={hit.status} />}{hit.archived && <Badge text="Archived" tone="amber" />}</View>
          <Text style={styles.label}>{hit.title}</Text>
          <Text style={styles.text}>{hit.excerpt}</Text>
          <Text style={styles.small}>{state.projects.find(item => item.id === hit.projectId)?.title || 'Shared prompts'} · {new Date(hit.updatedAt).toLocaleDateString()}</Text>
          <View style={styles.wrap}>{hit.tags.map(tag => <Badge key={tag} text={tag} />)}</View>
          <Action label={`Open ${hit.kind}`} onPress={() => open(hit)} />
        </View>)}
        <View style={styles.wrap}>
          <Action label="Previous results" disabled={page === 0} onPress={() => setPage(page - 1)} />
          <Text style={styles.small}>Page {page + 1}</Text>
          <Action label="Next results" disabled={(page + 1) * 30 >= results.total} onPress={() => setPage(page + 1)} />
        </View>
      </Section>
    </View>
  );
}
