import React, { useState } from 'react';
import { Pagination, usePage } from './PageNavigation';
import { Text, View } from 'react-native';
import type { Confidence, Note, NoteKind } from './types';
import { CONFIDENCES, LIMITS, NOTE_KINDS } from './types';
import { normalizeTags } from './validation';
import { filterNotes, noteBacklinks, relativeTime } from './selectors';
import { noteMarkdown } from './exports';
import { exportName, saveTextFile } from './files';
import { relatedRecords } from './search';
import MessageContent from '../MessageContent';
import { Action, Badge, Choice, Editor, Empty, Field, LinksPicker, Section, Toggle, confirmAction, styles } from './ui';
import type { PanelProps } from './ui';

export function NoteEditor({ store, state, project, note, close, initialBody = '' }: PanelProps & {
  note?: Note;
  close: () => void;
  initialBody?: string;
}) {
  const [title, setTitle] = useState(note?.title || '');
  const [body, setBody] = useState(note?.body || initialBody);
  const [kind, setKind] = useState<NoteKind>(note?.kind || 'note');
  const [confidence, setConfidence] = useState<Confidence>(note?.confidence || 'unverified');
  const [tags, setTags] = useState(note?.tags.join(', ') || '');
  const [sources, setSources] = useState(note?.sourceIds || []);
  const [related, setRelated] = useState(note?.relatedNoteIds || []);
  const [pinned, setPinned] = useState(note?.pinned || false);
  const [error, setError] = useState('');
  const save = () => {
    try {
      const input = {
        title,
        body,
        kind,
        confidence,
        tags: normalizeTags(tags),
        sourceIds: sources,
        relatedNoteIds: related,
        pinned,
      };
      const result = note
        ? store.dispatch({ type: 'note.update', id: note.id, revision: note.revision, patch: input })
        : store.dispatch({ type: 'note.create', input: { ...input, projectId: project.id } });
      if (result) close();
      else setError(store.getSnapshot().notice || 'Could not save the note.');
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Check the note fields.');
    }
  };
  return (
    <Editor visible title={note ? 'Edit note' : 'New note'} close={close} footer={<Action label="Save note" icon="checkmark-outline" onPress={save} />}>
      <Field label="Note title" value={title} onChange={setTitle} maxLength={LIMITS.title} />
      <Choice label="Note kind" value={kind} values={NOTE_KINDS} onChange={setKind} />
      <Field label="Note body" value={body} onChange={setBody} multiline maxLength={LIMITS.body} hint="Use plain text or fenced code blocks. HTML is never executed." />
      <Choice label="Confidence" value={confidence} values={CONFIDENCES} onChange={setConfidence} />
      <Text style={styles.small}>Confidence is your assessment of the note, not an automatic verification by Jeeves.</Text>
      <Field label="Tags" value={tags} onChange={setTags} maxLength={500} />
      <LinksPicker label="Cited sources" selected={sources} options={state.sources.filter(source => source.projectId === project.id)} onChange={setSources} />
      <LinksPicker label="Related notes" selected={related} options={state.notes.filter(item => item.projectId === project.id && item.id !== note?.id && !item.archived)} onChange={setRelated} />
      <Toggle label="Pin note" value={pinned} onChange={setPinned} />
      {error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    </Editor>
  );
}

export default function NotesPanel(props: PanelProps & {
  discuss: (note: Note) => void;
  createCard: (note: Note) => void;
}) {
  const { state, project, store, now } = props;
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState<NoteKind | 'all'>('all');
  const [confidence, setConfidence] = useState<Confidence | 'all'>('all');
  const [archived, setArchived] = useState(false);
  const [editor, setEditor] = useState<Note | 'new' | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const notes = filterNotes(state, project.id, {
    query,
    kind: kind === 'all' ? undefined : kind,
    confidence: confidence === 'all' ? undefined : confidence,
    archived,
  });
  const readOnly = project.status === 'archived';
  const { page, setPage } = usePage(notes, JSON.stringify([query, kind, confidence, archived]));
  const archive = (note: Note) => store.dispatch({
    type: 'note.update',
    id: note.id,
    revision: note.revision,
    patch: { archived: !note.archived },
  });
  const remove = (note: Note) => {
    const links = noteBacklinks(state, note.id);
    const count = links.notes.length + links.tasks.length + links.cards.length;
    confirmAction('Delete note?', `Delete “${note.title}”? ${count} incoming link(s) will be removed; linked records remain. Undo is available during this visit.`, () => {
      store.dispatch({ type: 'note.delete', id: note.id, revision: note.revision });
    });
  };
  return (
    <View style={styles.stack}>
      <Section title="Project notebook" subtitle="Keep observations, decisions and evidence close to your work." action={<Action label="New note" icon="add" onPress={() => setEditor('new')} disabled={readOnly} />}>
        <Field label="Search notes" value={query} onChange={setQuery} maxLength={200} />
        <Choice label="Kind" value={kind} values={['all', ...NOTE_KINDS]} onChange={setKind} />
        <Choice label="Confidence filter" value={confidence} values={['all', ...CONFIDENCES]} onChange={setConfidence} />
        <Toggle label="Show archived notes" value={archived} onChange={setArchived} />
      </Section>
      {!notes.length && <Empty icon="document-text-outline" title="No matching notes" message="Capture an observation, record a decision, or document what an experiment actually showed." />}
      <Pagination page={page} setPage={setPage} label="notes" />
      {page.items.map(note => {
        const open = expanded === note.id;
        const backlinks = noteBacklinks(state, note.id);
        const sources = state.sources.filter(source => note.sourceIds.includes(source.id));
        const related = open ? relatedRecords(state, note.id, 4) : [];
        return (
          <Section key={note.id} title={`${note.pinned ? '★ ' : ''}${note.title}`} subtitle={`Updated ${relativeTime(note.updatedAt, now)}`}>
            <View style={styles.wrap}>
              <Badge text={note.kind} tone="accent" />
              <Badge text={note.confidence} tone={note.confidence === 'supported' ? 'green' : note.confidence === 'contradicted' ? 'red' : 'amber'} />
              {note.tags.map(tag => <Badge key={tag} text={`#${tag}`} />)}
            </View>
            {open ? <MessageContent text={note.body || 'This note has no body.'} notify={store.notify} /> : <Text numberOfLines={5} style={styles.text}>{note.body || 'This note has no body.'}</Text>}
            <View style={styles.wrap}>
              <Action label={open ? 'Collapse note' : 'Read note'} icon={open ? 'chevron-up' : 'chevron-down'} onPress={() => setExpanded(open ? null : note.id)} compact />
              <Action label="Edit note" icon="create-outline" onPress={() => setEditor(note)} disabled={readOnly} compact />
              <Action label="Ask Jeeves" icon="sparkles-outline" onPress={() => props.discuss(note)} compact />
              <Action label="Make study card" icon="school-outline" onPress={() => props.createCard(note)} disabled={readOnly} compact />
            </View>
            {open && <>
              <View style={styles.divider} />
              <Text style={styles.label}>Sources ({sources.length})</Text>
              {!sources.length && <Text style={styles.small}>No source has been linked to this note.</Text>}
              {sources.map(source => <View key={source.id} style={styles.card}>
                <Text style={styles.label}>{source.title}</Text>
                <Text selectable style={styles.small}>{source.locator || source.kind}</Text>
                {!!source.excerpt && <Text numberOfLines={4} style={styles.muted}>{source.excerpt}</Text>}
              </View>)}
              <Text style={styles.label}>Incoming links</Text>
              <Text style={styles.muted}>{backlinks.notes.length} notes · {backlinks.tasks.length} tasks · {backlinks.cards.length} cards</Text>
              {backlinks.tasks.map(task => <Text key={task.id} style={styles.small}>Task: {task.title}</Text>)}
              {backlinks.notes.map(item => <Text key={item.id} style={styles.small}>Note: {item.title}</Text>)}
              {!!related.length && <>
                <Text style={styles.label}>Related by title or tags</Text>
                {related.map(item => <Text key={item.id} style={styles.small}>{item.kind}: {item.title}</Text>)}
              </>}
              <View style={styles.wrap}>
                <Action label="Export note" icon="download-outline" onPress={() => {
                  void saveTextFile(noteMarkdown(note, state.sources), exportName(note.title, 'md'), 'text/markdown').catch(() => store.notify('Note export failed.'));
                }} compact />
                <Action label={note.archived ? 'Restore note' : 'Archive note'} icon="archive-outline" onPress={() => archive(note)} disabled={readOnly} compact />
                <Action label="Delete note" icon="trash-outline" danger onPress={() => remove(note)} disabled={readOnly} compact />
              </View>
            </>}
          </Section>
        );
      })}
      {editor && <NoteEditor {...props} note={editor === 'new' ? undefined : editor} close={() => setEditor(null)} />}
    </View>
  );
}
