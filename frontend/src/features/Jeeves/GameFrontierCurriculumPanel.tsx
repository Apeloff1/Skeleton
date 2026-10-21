/** Source-book education and governed Forge practice inside the Jeeves cockpit.

    Seven exact-generation libraries exist virtually; the interface reads
    individual real volumes. It never represents reading as neural training.
*/
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, Text, TextInput, TouchableOpacity, View } from 'react-native';
import {
  BOOK_GENERATIONS, type BookGeneration,
  type CurriculumCatalog, type CurriculumLesson, type CurriculumManifest,
  type CurriculumPath, type CurriculumWorklist, type CurriculumAssessment,
  readCurriculumCatalog, readCurriculumLesson, readCurriculumPath,
  readCurriculumWorklist, readCurriculumManifest, assessCurriculumLesson,
  executeCurriculumAction,
} from '../../product/gameFrontierCurriculumClient';
import type { ForgeDocument } from '../../product/gameFrontierAuthoringClient';

const CHECK = /^[a-f0-9]{64}$/;
const textStyle = { color: '#bed4e8', fontSize: 12 } as const;
const fieldStyle = { color: '#f0f6ff', backgroundColor: '#1e2b38',
  borderColor: '#546c82', borderWidth: 1, borderRadius: 8,
  paddingHorizontal: 10, paddingVertical: 9 } as const;

function Action({title, onPress, disabled}: {
  title: string; onPress: () => void; disabled?: boolean;
}) {
  return <TouchableOpacity accessibilityRole="button" accessibilityLabel={title}
    disabled={disabled} onPress={onPress}
    style={{borderRadius: 7, padding: 9, borderColor: '#56728a',
      backgroundColor: disabled ? '#222d3a' : '#283f56',
      borderWidth: 1, marginRight: 5, marginBottom: 5}}>
    <Text style={{color: disabled ? '#8192a3' : '#e1f2ff', fontSize: 12}}>{title}</Text>
  </TouchableOpacity>;
}

export default function GameFrontierCurriculumPanel({
  projectId, document, disabled = false, onCommitted,
}: {
  projectId: string; document: ForgeDocument | null;
  disabled?: boolean; onCommitted?: () => Promise<void> | void;
}) {
  const [catalog, setCatalog] = useState<CurriculumCatalog|null>(null);
  const [generation, setGeneration] = useState<BookGeneration>('epic');
  const [bookIndex, setBookIndex] = useState('0');
  const [lesson, setLesson] = useState<CurriculumLesson|null>(null);
  const [course, setCourse] = useState<CurriculumPath|null>(null);
  const [worklist, setWorklist] = useState<CurriculumWorklist|null>(null);
  const [manifested, setManifested] = useState<CurriculumManifest|null>(null);
  const [answers, setAnswers] = useState<string[]>([]);
  const [assessment, setAssessment] = useState<CurriculumAssessment|null>(null);
  const [params, setParams] = useState('');
  const [plan, setPlan] = useState<{source_sha256: string;
    operations: string[]; books: string[]; persisted: boolean}|null>(null);
  const [preview, setPreview] = useState<{source_sha256: string;
    candidate_sha256: string; operations: string[]; books: string[];
    persisted: boolean; measured_changed: boolean}|null>(null);
  const [approval, setApproval] = useState(false);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('');
  const pending = busy || disabled;
  const activeCount = catalog?.curriculum_levels.find(row =>
    row.generation === generation)?.book_count || 0;
  const selectedIndex = Number(bookIndex);
  const validIndex = /^\d{1,13}$/.test(bookIndex) &&
    Number.isSafeInteger(selectedIndex) &&
    selectedIndex >= 0 && selectedIndex < activeCount;
  const ref = 'forgebook:' + generation + ':' + bookIndex;
  const source = document ? { expected_revision: document.expected_version,
    expected_sha256: document.source_sha256 } : null;
  const verified = preview && source &&
    preview.source_sha256 === source.expected_sha256 &&
    preview.books.length === 1 && preview.books[0] === ref &&
    preview.measured_changed && CHECK.test(preview.candidate_sha256);
  const invalidate = () => {
    setLesson(null); setCourse(null); setManifested(null); setWorklist(null);
    setAssessment(null); setAnswers([]); setPlan(null); setPreview(null);
    setApproval(false); setError(''); setStatus('');
  };
  useEffect(() => {
    let active = true;
    readCurriculumCatalog().then(value => { if (active) setCatalog(value); })
      .catch(reason => { if (active) setError(String(reason?.message || reason)); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    setPlan(null); setPreview(null); setApproval(false);
  }, [document?.source_sha256, document?.expected_version, projectId]);
  const perform = async (fn: () => Promise<void>) => {
    if (pending) return;
    setBusy(true); setError('');
    try { await fn(); }
    catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally { setBusy(false); }
  };
  const selectedBook = () => {
    if (!validIndex) throw new Error('Select an actual book index from the current curriculum.');
    return {generation, index: selectedIndex};
  };
  const learn = () => perform(async () => {
    const chosen = selectedBook();
    const [unit, path] = await Promise.all([
      readCurriculumLesson(chosen.generation, chosen.index),
      readCurriculumPath(chosen.generation, chosen.index),
    ]);
    setLesson(unit); setCourse(path); setAnswers(unit.questions.map(() => ''));
    setManifested(null); setWorklist(null); setAssessment(null);
    setPlan(null); setPreview(null); setApproval(false);
    const activeLayer = document?.layers[0];
    setParams(JSON.stringify({
      layer: activeLayer?.id || 'ground', x: 0, y: 0,
      width: Math.min(12, activeLayer?.size[0] || 12),
      height: Math.min(12, activeLayer?.size[1] || 12),
      floor: 0, wall: 1, seed: 43, scale: 5, threshold: .53,
      instance_id: 'jeeves_book', prefab_id: document?.prefab_catalog?.[0]?.id || 'merchant',
      count: 4, radius: 6, spacing: 2, z: 0,
    }, null, 2));
    setStatus('Selected exact registered lesson, source operation and its full prerequisite chain.');
  });
  const visualize = () => perform(async () => {
    const item = selectedBook();
    const result = await readCurriculumManifest(item.generation, item.index);
    setManifested(result);
    setStatus('Manifested one real Markdown book with verified server SHA receipt.');
  });
  const studyPlan = () => perform(async () => {
    const item = selectedBook();
    const value = await readCurriculumWorklist(item.generation, item.index,
      Math.min(8, activeCount-item.index));
    setWorklist(value);
    setStatus('A bounded worklist is ready; no jobs were silently queued or trained.');
  });
  const assess = () => perform(async () => {
    const item = selectedBook();
    if (!lesson || lesson.reference.ref !== ref)
      throw new Error('Load the matching source lesson before assessment.');
    const result = await assessCurriculumLesson(item.generation, item.index, answers);
    setAssessment(result);
    setStatus('Theory scored against the exact registered source axes. Practical training is separate.');
  });
  const parseParams = () => {
    const parsed: unknown = JSON.parse(params);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed) ||
        Object.keys(parsed).length > 32)
      throw new Error('Practice requires a bounded JSON object for actual source editor parameters.');
    return parsed as Record<string, unknown>;
  };
  const practice = (mode: 'plan'|'preview'|'commit') => perform(async () => {
    const book = selectedBook();
    if (!lesson || lesson.reference.ref !== ref)
      throw new Error('Load the exact lesson and source operation before an automated practice.');
    const parameters = parseParams();
    if (!document || !source) throw new Error('Refresh a live saved project to practice.');
    if (mode === 'commit' && (!verified || !approval))
      throw new Error('Explicitly approve the previewed exact project hash before commit.');
    const result = await executeCurriculumAction(
      'game.studio.curriculum.automation.' + mode as
        'game.studio.curriculum.automation.plan' |
        'game.studio.curriculum.automation.preview' |
        'game.studio.curriculum.automation.commit',
      projectId, [book], parameters, source,
      mode === 'commit' ? preview?.candidate_sha256 : undefined,
    );
    if (mode === 'plan') {
      setPlan(result as typeof plan & {source_sha256: string; operations: string[]; books: string[]; persisted: boolean});
      setPreview(null); setApproval(false);
      setStatus('Jeeves resolved one exact book to one registered original-game edit. Not persisted.');
    } else if (mode === 'preview') {
      if (!result.candidate_sha256 || !CHECK.test(result.candidate_sha256) ||
          result.source_sha256 !== source.expected_sha256)
        throw new Error('Host did not return a source-bound measured preview.');
      setPreview(result as NonNullable<typeof preview>);
      setApproval(false);
      setStatus('Host evaluated the real edit and returned a candidate hash. No save occurred.');
    } else {
      setPreview(null); setPlan(null); setApproval(false);
      setStatus('One exactly approved candidate revision was saved; native playthrough and weight training remain unverified.');
      await onCommitted?.();
    }
  });
  return <View style={{gap: 8, padding: 10, borderColor: '#52748a',
    borderWidth: 1, borderRadius: 11, backgroundColor: '#192734'}}>
    <Text style={{color: '#e6f6ff', fontSize: 15, fontWeight: '700'}}>
      Jeeves Academy · Source-book curriculum
    </Text>
    <Text style={textStyle}>
      Seven prerequisite levels. Every book is an exact address into the source library;
      one selected book is rendered only on request. Assessments measure source knowledge;
      project previews measure actual edits. Neural weights are not trained here.
    </Text>
    <Action title={(open ? 'Hide' : 'Open') + ' Forge book academy'}
      disabled={pending} onPress={() => setOpen(v => !v)} />
    {open && <>
      {!catalog && <Text style={textStyle}>Loading curriculum registry…</Text>}
      {!!catalog && <Text style={textStyle}>
        {catalog.book_count.toLocaleString()} source-addressed books ·
        {catalog.curriculum_levels.length} sequential competency generations
      </Text>}
      <ScrollView horizontal showsHorizontalScrollIndicator>
        <View style={{flexDirection: 'row'}}>
          {BOOK_GENERATIONS.map(value =>
            <Action key={value} title={(generation === value ? '✓ ' : '')+value}
              disabled={pending}
              onPress={() => { setGeneration(value); setBookIndex('0'); invalidate(); }} />)}
        </View>
      </ScrollView>
      <Text style={textStyle}>Exact book index (0–{Math.max(0,activeCount-1).toLocaleString()})</Text>
      <TextInput accessibilityLabel="Jeeves book exact integer index" value={bookIndex}
        keyboardType="numeric" maxLength={13} editable={!pending}
        onChangeText={next => { setBookIndex(next); invalidate(); }}
        style={fieldStyle}/>
      <View style={{flexDirection: 'row', flexWrap: 'wrap'}}>
        <Action title="Load lesson and prerequisite chain" disabled={pending || !validIndex}
          onPress={learn}/>
        <Action title="Manifest full source book" disabled={pending || !validIndex}
          onPress={visualize}/>
        <Action title="Prepare eight real-indexed study sessions" disabled={pending || !validIndex}
          onPress={studyPlan}/>
      </View>
      {!!course && <View style={{gap: 4}}>
        <Text style={{color: '#ddedff', fontWeight: '700'}}>
          {course.course_levels} source-traceable curriculum levels
        </Text>
        {course.modules.map(unit =>
          <Text key={unit.book} style={textStyle}>
            {unit.level}. {unit.generation}: {unit.book} ·
            {unit.practical_checkpoints.length} verification checkpoints
          </Text>)}
        <Text selectable style={{color:'#88abba',fontSize:10}}>
          Source lesson chain SHA-256: {course.curriculum_sha256}
        </Text>
      </View>}
      {!!worklist && <View style={{gap: 4}}>
        <Text style={{color:'#ddedff', fontWeight:'700'}}>
          {worklist.sessions} sessions planned · {worklist.issued_jobs} issued ·
          {worklist.completed_lessons} completed
        </Text>
        {worklist.tasks.map(task =>
          <Text key={task.book} style={textStyle}>
            {task.session}. {task.book} · {task.status.replace(/_/g,' ')}
          </Text>)}
      </View>}
      {!!lesson && <View style={{gap: 6}}>
        <Text style={{color:'#e1f0ff',fontWeight:'700'}}>
          Exact book theory · {lesson.reference.ref}
        </Text>
        {lesson.questions.map((item, i) =>
          <View key={item.question_id} style={{gap: 3}}>
            <Text style={textStyle}>{i+1}. {item.prompt}</Text>
            <TextInput accessibilityLabel={'Answer source axis '+(i+1)}
              value={answers[i] || ''} editable={!pending}
              autoCapitalize="none" autoCorrect={false} maxLength={80}
              placeholder="Exact source term" placeholderTextColor="#8b9eb2"
              onChangeText={v => {
                setAnswers(current => current.map((a, j) => j === i ? v : a));
                setAssessment(null);
              }} style={fieldStyle}/>
          </View>)}
        <Action title="Assess exact source-axis understanding"
          disabled={pending || answers.length !== lesson.questions.length}
          onPress={assess}/>
        {!!assessment && <Text selectable style={textStyle}>
          Theory {assessment.passed}/{assessment.answered} ·
          {assessment.mastery_earned ? 'Exact-axis pass' : 'Revision required'} ·
          No model weights updated · Receipt {assessment.receipt_sha256}
        </Text>}
        <Text style={{color:'#e1f0ff', fontWeight:'700'}}>
          Practical Jeeves automation · host-scoped source edit
        </Text>
        <Text style={textStyle}>Registered operation: {lesson.source_exercise_action}</Text>
        <Text style={textStyle}>
          Editor parameters must fit the real project layers and palette. Change them
          only after inspecting the current source. An operator approves the
          preview hash before a persistent write.
        </Text>
        <TextInput accessibilityLabel="Book practice edit JSON" value={params}
          onChangeText={v => {
            setParams(v); setPlan(null); setPreview(null); setApproval(false);
          }} editable={!pending} autoCorrect={false} autoCapitalize="none"
          maxLength={12000} multiline style={{...fieldStyle, minHeight:110,
            fontFamily:'monospace', textAlignVertical:'top'}}/>
        <View style={{flexDirection:'row', flexWrap:'wrap'}}>
          <Action title="1. Plan registered book edit"
            disabled={pending || !document} onPress={() => practice('plan')}/>
          <Action title="2. Preview actual source change"
            disabled={pending || !document} onPress={() => practice('preview')}/>
        </View>
        {!!plan && <Text selectable style={textStyle}>
          Plan: {plan.operations.join(' · ')} · saved: {String(plan.persisted)}
        </Text>}
        {!!preview && <View style={{gap: 5}}>
          <Text selectable style={textStyle}>
            Measured source changed: {String(preview.measured_changed)}
            {'\n'}Before: {preview.source_sha256}
            {'\n'}Candidate: {preview.candidate_sha256}
            {'\n'}Persisted: {String(preview.persisted)}
          </Text>
          <Action title={(approval ? '✓ ' : '')+'Approve EXACT candidate digest'}
            disabled={pending || !verified}
            onPress={() => setApproval(value => !value)}/>
          <Action title="3. Commit only this approved source revision"
            disabled={pending || !verified || !approval}
            onPress={() => practice('commit')}/>
        </View>}
      </View>}
      {!!manifested && <View style={{gap: 5}}>
        <Text style={{color: '#d7ebff', fontWeight:'700'}}>
          Materialized real manuscript · {manifested.bytes.toLocaleString()} bytes
        </Text>
        <Text selectable style={{color:'#8bb7d3',fontSize:10}}>
          SHA-256: {manifested.content_sha256}{'\n'}{manifested.path}
        </Text>
        <ScrollView style={{maxHeight: 480}}>
          <Text selectable style={textStyle}>{manifested.markdown}</Text>
        </ScrollView>
      </View>}
      {busy && <ActivityIndicator size="small" color="#b8d8ee" />}
      {!!status && <Text style={{color:'#afe2cb'}}>{status}</Text>}
      {!!error && <Text selectable style={{color:'#ffbbbb'}}>{error}</Text>}
    </>}
  </View>;
}
