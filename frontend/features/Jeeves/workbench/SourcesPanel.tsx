import React, { useState } from 'react';
import { Pagination, usePage } from './PageNavigation';
import { Linking, Text, View } from 'react-native';
import type { Source, SourceKind } from './types';
import { LIMITS } from './types';
import { normalizeTags, safeUrl } from './validation';
import { sourceBacklinks } from './selectors';
import { sourceBibliography } from './exports';
import { exportName, saveTextFile } from './files';
import { Action, Badge, Choice, Editor, Empty, Field, Section, confirmAction, styles } from './ui';
import type { PanelProps } from './ui';

function SourceEditor({ store, project, source, close }: PanelProps & { source?: Source; close: () => void }) {
  const [title, setTitle] = useState(source?.title || '');
  const [kind, setKind] = useState<SourceKind>(source?.kind || 'url');
  const [locator, setLocator] = useState(source?.locator || '');
  const [excerpt, setExcerpt] = useState(source?.excerpt || '');
  const [author, setAuthor] = useState(source?.author || '');
  const [tags, setTags] = useState(source?.tags.join(', ') || '');
  const [error, setError] = useState('');
  const save = () => {
    try {
      const input = { title, kind, locator, excerpt, author, tags: normalizeTags(tags) };
      const result = source
        ? store.dispatch({ type: 'source.update', id: source.id, revision: source.revision, patch: input })
        : store.dispatch({ type: 'source.create', input: { ...input, projectId: project.id } });
      if (result) close();
      else setError(store.getSnapshot().notice || 'Could not save the source.');
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Check the source fields.');
    }
  };
  return (
    <Editor visible title={source ? 'Edit source' : 'Add source'} close={close} footer={<Action label="Save source" icon="checkmark-outline" onPress={save} />}>
      <Field label="Source title" value={title} onChange={setTitle} maxLength={LIMITS.title} />
      <Choice label="Source type" value={kind} values={['url', 'book', 'file', 'conversation', 'observation']} onChange={setKind} />
      <Field label={kind === 'url' ? 'Source URL' : 'Location or reference'} value={locator} onChange={setLocator} maxLength={2000} hint={kind === 'url' ? 'Use an HTTP or HTTPS URL without embedded credentials.' : 'Record a filename, page number, conversation title or experiment reference.'} />
      <Field label="Author or publisher" value={author} onChange={setAuthor} maxLength={200} />
      <Field label="Excerpt or observation" value={excerpt} onChange={setExcerpt} multiline maxLength={LIMITS.answer} hint="Keep the relevant evidence. Adding a source does not fetch or verify its contents." />
      <Field label="Tags" value={tags} onChange={setTags} maxLength={500} />
      {error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    </Editor>
  );
}

export default function SourcesPanel(props: PanelProps) {
  const { state, project, store } = props;
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<SourceKind | 'all'>('all');
  const [editor, setEditor] = useState<Source | 'new' | null>(null);
  const readOnly = project.status === 'archived';
  const needle = query.trim().toLocaleLowerCase();
  const sources = state.sources.filter(source => source.projectId === project.id
    && (kind === 'all' || source.kind === kind)
    && (!needle || [source.title, source.excerpt, source.author, source.locator, ...source.tags].some(value => value.toLocaleLowerCase().includes(needle))))
    .sort((a, b) => b.updatedAt - a.updatedAt);
  const remove = (source: Source) => {
    const links = sourceBacklinks(state, source.id);
    confirmAction('Delete source?', `${links.notes.length} note(s) and ${links.cards.length} card(s) will lose this citation. Their contents will remain.`, () => {
      store.dispatch({ type: 'source.delete', id: source.id, revision: source.revision });
    });
  };
  const { page, setPage } = usePage(sources, JSON.stringify([query, kind]));
  return (
    <View style={styles.stack}>
      <Section title="Source library" subtitle="Trace your notes and study cards back to the material you used." action={<Action label="Add source" icon="add" onPress={() => setEditor('new')} disabled={readOnly} />}>
        <Field label="Search sources" value={query} onChange={setQuery} maxLength={200} />
        <Choice label="Source filter" value={kind} values={['all', 'url', 'book', 'file', 'conversation', 'observation']} onChange={setKind} />
        <Action label="Export bibliography" icon="download-outline" onPress={() => {
          void saveTextFile(sourceBibliography(state, project.id), exportName(project.title + '-sources', 'md'), 'text/markdown').catch(() => store.notify('Source export failed.'));
        }} />
      </Section>
      {!sources.length && <Empty icon="library-outline" title="No sources yet" message="Add a document, URL, observation or conversation reference, then cite it from notes and study cards." />}
      <Pagination page={page} setPage={setPage} label="sources" />
      {page.items.map(source => {
        const links = sourceBacklinks(state, source.id);
        const url = source.kind === 'url' ? safeUrl(source.locator) : null;
        return (
          <Section key={source.id} title={source.title} subtitle={source.author || undefined}>
            <View style={styles.wrap}>
              <Badge text={source.kind} tone="accent" />
              {source.tags.map(tag => <Badge key={tag} text={`#${tag}`} />)}
            </View>
            {!!source.locator && <Text selectable style={styles.muted}>{source.locator}</Text>}
            {!!source.excerpt && <Text selectable style={styles.text}>{source.excerpt}</Text>}
            <Text style={styles.small}>Recorded {new Date(source.accessedAt).toLocaleDateString()} · cited by {links.notes.length} notes and {links.cards.length} cards</Text>
            <View style={styles.wrap}>
              {url && <Action label="Open source" icon="open-outline" onPress={() => { void Linking.openURL(url).catch(() => store.notify('Could not open this URL.')); }} compact />}
              <Action label="Edit source" icon="create-outline" onPress={() => setEditor(source)} disabled={readOnly} compact />
              <Action label="Delete source" icon="trash-outline" danger onPress={() => remove(source)} disabled={readOnly} compact />
            </View>
          </Section>
        );
      })}
      {editor && <SourceEditor {...props} source={editor === 'new' ? undefined : editor} close={() => setEditor(null)} />}
    </View>
  );
}
