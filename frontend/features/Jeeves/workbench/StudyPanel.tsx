import React, { useEffect, useRef, useState } from 'react';
import { Pagination, usePage } from './PageNavigation';
import { Text, View } from 'react-native';
import type { Note, StudyCard } from './types';
import { LIMITS, REVIEW_GRADES } from './types';
import { normalizeTags } from './validation';
import { buildReviewQueue, difficultCards, gradeIntervals, reviewHistory, reviewStreak } from './review';
import { cardsCsv, studyMarkdown } from './exports';
import { exportName, saveTextFile } from './files';
import MessageContent from '../MessageContent';
import { Action, Badge, Choice, Editor, Empty, Field, LinksPicker, Metric, Section, confirmAction, styles } from './ui';
import type { PanelProps } from './ui';

export function CardEditor({ store, state, project, card, note, close }: PanelProps & {
  card?: StudyCard;
  note?: Note;
  close: () => void;
}) {
  const [question, setQuestion] = useState(card?.question || '');
  const [answer, setAnswer] = useState(card?.answer || note?.body.slice(0, LIMITS.answer) || '');
  const [hint, setHint] = useState(card?.hint || '');
  const [explanation, setExplanation] = useState(card?.explanation || '');
  const [tags, setTags] = useState((card?.tags || note?.tags || []).join(', '));
  const [noteIds, setNoteIds] = useState<string[]>(card?.noteId ? [card.noteId] : note ? [note.id] : []);
  const [sourceIds, setSourceIds] = useState(card?.sourceIds || note?.sourceIds || []);
  const [error, setError] = useState('');
  const save = () => {
    try {
      const input = {
        question,
        answer,
        hint,
        explanation,
        tags: normalizeTags(tags),
        noteId: noteIds.at(-1) || null,
        sourceIds,
      };
      const result = card
        ? store.dispatch({ type: 'card.update', id: card.id, revision: card.revision, patch: input })
        : store.dispatch({ type: 'card.create', input: { ...input, projectId: project.id } });
      if (result) close();
      else setError(store.getSnapshot().notice || 'Could not save the card.');
    } catch (problem) {
      setError(problem instanceof Error ? problem.message : 'Check the card fields.');
    }
  };
  return (
    <Editor visible title={card ? 'Edit study card' : 'New study card'} close={close} footer={<Action label="Save study card" icon="checkmark-outline" onPress={save} />}>
      <Field label="Question" value={question} onChange={setQuestion} multiline maxLength={LIMITS.summary} hint="Ask one clear question you can answer without looking at the back." />
      <Field label="Answer" value={answer} onChange={setAnswer} multiline maxLength={LIMITS.answer} />
      <Field label="Optional hint" value={hint} onChange={setHint} multiline maxLength={LIMITS.summary} />
      <Field label="Explanation or common misconception" value={explanation} onChange={setExplanation} multiline maxLength={LIMITS.answer} />
      <Field label="Card tags" value={tags} onChange={setTags} maxLength={500} />
      <LinksPicker label="Origin note (choose one)" selected={noteIds} options={state.notes.filter(item => item.projectId === project.id && !item.archived)} onChange={ids => setNoteIds(ids.slice(-1))} />
      <LinksPicker label="Card sources" selected={sourceIds} options={state.sources.filter(item => item.projectId === project.id)} onChange={setSourceIds} />
      {error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    </Editor>
  );
}

export default function StudyPanel(props: PanelProps) {
  const { state, project, store, now } = props;
  const [mode, setMode] = useState<'review' | 'library' | 'progress'>('review');
  const [revealed, setRevealed] = useState(false);
  const [hintVisible, setHintVisible] = useState(false);
  const [query, setQuery] = useState('');
  const [editor, setEditor] = useState<StudyCard | 'new' | null>(null);
  const [lastReview, setLastReview] = useState<string | null>(null);
  const started = useRef(Date.now());
  const queue = buildReviewQueue(state, project.id, now);
  const current = queue.cards[0];
  const cards = state.cards.filter(card => card.projectId === project.id);
  const matchingCards = cards.filter(card => [card.question, card.answer, ...card.tags].some(value => value.toLocaleLowerCase().includes(query.toLocaleLowerCase())));
  const { page, setPage } = usePage(matchingCards, query);
  const reviews = state.reviews.filter(review => review.projectId === project.id);
  const readOnly = project.status === 'archived';
  useEffect(() => {
    setRevealed(false);
    setHintVisible(false);
    started.current = Date.now();
  }, [current?.id, current?.revision]);
  const intervals = current && current.schedule.state !== 'suspended' ? gradeIntervals(current.schedule, now) : null;
  const grade = (value: typeof REVIEW_GRADES[number]) => {
    if (!current || !revealed) return;
    const result = store.dispatch({
      type: 'card.review',
      id: current.id,
      revision: current.revision,
      grade: value,
      durationMs: Math.max(0, Math.min(3600000, Date.now() - started.current)),
    });
    if (result) setLastReview(result.createdId);
  };
  const exportCards = (format: 'csv' | 'md') => {
    const text = format === 'csv' ? cardsCsv(cards) : studyMarkdown(cards);
    void saveTextFile(text, exportName(project.title + '-study', format), format === 'csv' ? 'text/csv' : 'text/markdown')
      .catch(() => store.notify('Study export failed.'));
  };
  return (
    <View style={styles.stack}>
      <Section title="Study room" subtitle="Practice recall, reveal the answer, then grade how well you remembered it." action={<Action label="New study card" icon="add" onPress={() => setEditor('new')} disabled={readOnly} />}>
        <Choice label="Study view" value={mode} values={['review', 'library', 'progress']} onChange={setMode} />
        <View style={styles.wrap}>
          <Metric label="Ready now" value={queue.cards.length} />
          <Metric label="Total cards" value={cards.length} />
          <Metric label="Review streak" value={`${reviewStreak(reviews, now)}d`} />
        </View>
        <Text style={styles.small}>Scheduling is a deterministic practice aid. It does not measure mastery or predict your recall probability.</Text>
      </Section>
      {mode === 'review' && <>
        {!current && <Empty icon="school-outline" title="No cards ready right now" message={queue.nextDueAt ? `The next scheduled review is ${new Date(queue.nextDueAt).toLocaleString()}. Daily limits may also affect the queue.` : 'Create some study cards or adjust your daily limits in Settings.'} />}
        {current && <Section title="Recall before revealing">
          <View style={styles.wrap}>
            <Badge text={current.schedule.state} tone="accent" />
            {current.tags.map(tag => <Badge key={tag} text={`#${tag}`} />)}
          </View>
          <MessageContent text={current.question} notify={store.notify} />
          {!!current.hint && <Action label={hintVisible ? 'Hide hint' : 'Show hint'} icon="bulb-outline" onPress={() => setHintVisible(!hintVisible)} />}
          {hintVisible && <Text style={styles.muted}>{current.hint}</Text>}
          {!revealed && <Action label="Reveal answer" icon="eye-outline" onPress={() => setRevealed(true)} />}
          {revealed && <>
            <View style={styles.divider} />
            <Text style={styles.label}>Answer</Text>
            <MessageContent text={current.answer} notify={store.notify} />
            {!!current.explanation && <>
              <Text style={styles.label}>Explanation</Text>
              <MessageContent text={current.explanation} notify={store.notify} />
            </>}
            <Text style={styles.muted}>How well did you recall it?</Text>
            <View style={styles.wrap}>
              {REVIEW_GRADES.map(value => <Action key={value} label={`${value} · ${intervals?.[value]}`} onPress={() => grade(value)} disabled={readOnly} />)}
            </View>
            <Text style={styles.small}>Again = could not recall. Hard = recalled with difficulty. Good = recalled correctly. Easy = immediate, confident recall.</Text>
          </>}
          <View style={styles.wrap}>
            <Action label="Edit this card" icon="create-outline" onPress={() => setEditor(current)} disabled={readOnly} compact />
            <Action label="Suspend this card" icon="pause-outline" onPress={() => store.dispatch({ type: 'card.suspend', id: current.id, revision: current.revision, suspended: true })} disabled={readOnly} compact />
          </View>
        </Section>}
        {lastReview && <Action label="Undo last grade" icon="arrow-undo-outline" onPress={() => {
          if (store.dispatch({ type: 'card.undo-review', reviewId: lastReview })) setLastReview(null);
        }} disabled={readOnly} />}
        <Text style={styles.small}>Remaining today: {queue.newRemaining} new cards · {queue.reviewRemaining} review cards. Learning steps are shown when due.</Text>
      </>}
      {mode === 'library' && <>
        <Section title="Card library">
          <Field label="Search study cards" value={query} onChange={setQuery} maxLength={200} />
          <View style={styles.wrap}>
            <Action label="Export cards CSV" icon="download-outline" onPress={() => exportCards('csv')} />
            <Action label="Export study guide" icon="document-text-outline" onPress={() => exportCards('md')} />
          </View>
        </Section>
        <Pagination page={page} setPage={setPage} label="cards" />
        {page.items.map(card => (
          <Section key={card.id} title={card.question}>
            <Text selectable style={styles.text}>{card.answer}</Text>
            <View style={styles.wrap}>
              <Badge text={card.schedule.state} />
              <Badge text={`${card.schedule.repetitions} reviews`} />
              <Badge text={`${card.schedule.lapses} lapses`} />
            </View>
            <Text style={styles.small}>Due {new Date(card.schedule.dueAt).toLocaleString()}</Text>
            <View style={styles.wrap}>
              <Action label="Edit card" icon="create-outline" onPress={() => setEditor(card)} disabled={readOnly} compact />
              <Action label={card.schedule.state === 'suspended' ? 'Resume card' : 'Suspend card'} icon="pause-outline" onPress={() => store.dispatch({ type: 'card.suspend', id: card.id, revision: card.revision, suspended: card.schedule.state !== 'suspended' })} disabled={readOnly} compact />
              <Action label="Reset schedule" icon="refresh-outline" onPress={() => confirmAction('Reset review schedule?', 'This card will start as new. Historical review records remain available.', () => store.dispatch({ type: 'card.reset', id: card.id, revision: card.revision }))} disabled={readOnly} compact />
              <Action label="Delete card" icon="trash-outline" danger onPress={() => confirmAction('Delete study card?', 'This also removes its review history. Undo remains available during this visit.', () => store.dispatch({ type: 'card.delete', id: card.id, revision: card.revision }))} disabled={readOnly} compact />
            </View>
          </Section>
        ))}
      </>}
      {mode === 'progress' && <>
        <Section title="Last 14 days" subtitle="Recorded reviews and time spent; these are activity measures, not mastery scores.">
          {reviewHistory(reviews, now).map(day => <View key={day.day} style={styles.row}>
            <Text style={[styles.small, styles.flex]}>{day.day}</Text>
            <Text style={styles.small}>{day.reviews} reviews · {day.minutes}m · {day.again} again</Text>
          </View>)}
        </Section>
        <Section title="Cards needing attention" subtitle="Ranked by recent Again/Hard grades and recorded lapses.">
          {difficultCards(cards, reviews).map(card => <View key={card.id} style={styles.card}>
            <Text style={styles.label}>{card.question}</Text>
            <Text style={styles.small}>{card.schedule.lapses} recorded lapses</Text>
            <Action label="Improve this card" icon="create-outline" onPress={() => setEditor(card)} disabled={readOnly} />
          </View>)}
          {!difficultCards(cards, reviews).length && <Text style={styles.muted}>No difficult cards identified from your recorded reviews yet.</Text>}
        </Section>
      </>}
      {editor && <CardEditor {...props} card={editor === 'new' ? undefined : editor} close={() => setEditor(null)} />}
    </View>
  );
}
