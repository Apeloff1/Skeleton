/** Explicit source-build admission and read-only recovery of the original job. */
import React from 'react';
import { Platform, StyleSheet, Text, TextInput, View } from 'react-native';
import { getAuthEpoch, subscribeAuthChanges } from '../../auth/gameforgeAuth';
import {
  controlForgeBuild, createForgeProject, downloadForgeBuild, forgeJobTerminal,
  getForgeBuild, getForgeProject, listForgeBuilds, listForgeProjects, savedForgeRequestKey,
  sourceOnlyForgeRequest, submitForgeBuild,
  ForgeClientError,
  type ForgeProject, type ForgeProjectDetail, type SavedForgeJob, type SavedForgeRequest,
} from '../durableForgeClient';
import type { RunRequest } from '../types';
import { Banner, Button, Card, SectionTitle, StatusPill } from './primitives';
import ForgeRunPanel from './ForgeRunPanel';
import { C } from './theme';

type PendingBuild = { key: string; projectId: string; run: SavedForgeRequest };

export async function shareSavedForgeZip(
  bytes: Uint8Array, jobId: string, current: () => boolean,
): Promise<void> {
  if (!current()) throw new Error('The source download belongs to a previous account.');
  const filename = `godot-source-${jobId}.zip`;
  if (Platform.OS === 'web') {
    const url = URL.createObjectURL(new Blob([Uint8Array.from(bytes)], { type: 'application/zip' }));
    try {
      if (!current()) return;
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = filename;
      document.body.appendChild(anchor); anchor.click(); anchor.remove();
    } finally { setTimeout(() => URL.revokeObjectURL(url), 30000); }
    return;
  }
  const [Sharing, FileSystem, Crypto] = await Promise.all([
    import('expo-sharing'), import('expo-file-system'), import('expo-crypto'),
  ]);
  if (!await Sharing.isAvailableAsync()) throw new Error('File sharing is unavailable on this device. The original archive remains saved.');
  const file = new FileSystem.File(FileSystem.Paths.cache, filename.replace('.zip', `-${Crypto.randomUUID()}.zip`));
  try {
    if (!current()) return;
    if (file.exists) throw new Error('A different source share already owns this temporary file.');
    file.create(); file.write(bytes);
    if (!current()) return;
    await Sharing.shareAsync(file.uri, { mimeType: 'application/zip', UTI: 'public.zip-archive', dialogTitle: 'Save your original Godot source project' });
  } finally { try { if (file.exists) file.delete(); } catch { /* The server archive remains authoritative. */ } }
}

export default function DurableForgePanel({ request }: { request: RunRequest }) {
  const [scope, setScope] = React.useState(getAuthEpoch);
  const [projects, setProjects] = React.useState<ForgeProject[]>([]);
  const [detail, setDetail] = React.useState<ForgeProjectDetail | null>(null);
  const [job, setJob] = React.useState<SavedForgeJob | null>(null);
  const [name, setName] = React.useState('');
  const [projectQuery, setProjectQuery] = React.useState('');
  const [projectLimit, setProjectLimit] = React.useState(12);
  const [sourceAcknowledged, setSourceAcknowledged] = React.useState(false);
  const [savedBrief, setSavedBrief] = React.useState<SavedForgeRequest | null>(null);
  const [busy, setBusy] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [uncertain, setUncertain] = React.useState(false);
  const alive = React.useRef(true);
  const sequence = React.useRef(0);
  const actionController = React.useRef<AbortController | null>(null);
  const pending = React.useRef<PendingBuild | null>(null);
  const pendingCreate = React.useRef<{ key: string; name: string } | null>(null);
  const visible = React.useRef<{ projectId: string | null; jobId: string | null }>({ projectId: null, jobId: null });
  const adoptJob = (next: SavedForgeJob | null) => {
    visible.current.jobId = next?.job_id || null;
    if (next) visible.current.projectId = next.project_id;
    setJob(next);
    if (next && pending.current?.projectId === next.project_id && pending.current.key === next.request_id) {
      pending.current = null; setUncertain(false);
      setNotice('The original saved submission was recovered. No second build was requested.');
    }
  };

  React.useEffect(() => {
    alive.current = true;
    const unsubscribe = subscribeAuthChanges(() => {
      sequence.current++; actionController.current?.abort(); pending.current = null; pendingCreate.current = null;
      visible.current = { projectId: null, jobId: null };
      setProjects([]); setDetail(null); setJob(null); setSavedBrief(null); setName(''); setProjectQuery(''); setProjectLimit(12);
      setSourceAcknowledged(false); setUncertain(false); setBusy(''); setError(null); setNotice(null);
      setScope(getAuthEpoch());
    });
    return () => { alive.current = false; sequence.current++; actionController.current?.abort(); unsubscribe(); };
  }, []);

  const act = React.useCallback(async (label: string, operation: (
    signal: AbortSignal, current: () => boolean,
  ) => Promise<void>) => {
    actionController.current?.abort();
    const controller = new AbortController(); actionController.current = controller;
    const id = ++sequence.current; const epoch = getAuthEpoch();
    const current = () => alive.current && !controller.signal.aborted && id === sequence.current && epoch === getAuthEpoch();
    setBusy(label); setError(null);
    try { await operation(controller.signal, current); }
    catch (reason) { if (current()) setError(reason instanceof Error ? reason.message.slice(0, 500) : 'The saved source operation could not be completed.'); }
    finally { if (current()) setBusy(''); }
  }, []);

  const refresh = React.useCallback(() => act('refresh', async (signal, current) => {
    const rows = await listForgeProjects(signal);
    if (current()) setProjects(rows);
  }), [act]);
  React.useEffect(() => { void refresh(); }, [refresh, scope]);

  const openProject = (projectId: string) => act('open', async (signal, current) => {
    const next = await getForgeProject(projectId, signal);
    if (!current()) return;
    visible.current.projectId = next.project.project_id;
    setDetail(next); adoptJob(next.builds[0] || null); setSavedBrief(null); setError(null);
    if (pending.current?.projectId === projectId) {
      const recovered = next.builds.find(row => row.request_id === pending.current!.key);
      if (recovered) {
        adoptJob(recovered); pending.current = null; setUncertain(false);
        setNotice('The original saved submission was recovered. No second build was requested.');
      }
    }
  });

  React.useEffect(() => {
    if (!job || forgeJobTerminal(job)) return;
    const controller = new AbortController(); const epoch = getAuthEpoch(); let stopped = false; let failures = 0;
    const sameView = () => !stopped && epoch === getAuthEpoch()
      && visible.current.projectId === job.project_id && visible.current.jobId === job.job_id;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const started = Date.now();
    const observe = async () => {
      try {
        const next = await getForgeBuild(job.project_id, job.job_id, controller.signal);
        if (!sameView()) return;
        failures = 0;
        if (forgeJobTerminal(next)) {
          try {
            const history = await getForgeProject(next.project_id, controller.signal);
            if (sameView()) setDetail(history);
          } catch {
            if (sameView()) setNotice('The original terminal receipt was read. Refresh to update the project history.');
          }
          if (sameView()) setJob(next);
          return;
        }
        setJob(next);
      } catch {
        if (!sameView()) return;
        failures++;
        setNotice('Build observation is unavailable. Check the original build when the connection recovers.');
      }
      if (sameView() && failures < 4 && Date.now() - started < 5 * 60 * 1000) timer = setTimeout(() => void observe(), Math.min(8000, 1500 * 2 ** failures));
    };
    timer = setTimeout(() => void observe(), 1200);
    return () => { stopped = true; controller.abort(); if (timer) clearTimeout(timer); };
  }, [job?.job_id, job?.status, scope]);

  const create = () => act('create', async (signal, current) => {
    const title = name.trim();
    const admission = pendingCreate.current || { key: savedForgeRequestKey(), name: title };
    pendingCreate.current = admission;
    let admittedProject = false;
    try {
      const project = await createForgeProject(admission.name, admission.key, signal);
      admittedProject = true;
      const next = await getForgeProject(project.project_id, signal);
      if (!current()) return;
      pendingCreate.current = null; visible.current.projectId = project.project_id;
      setDetail(next); adoptJob(next.builds[0] || null); setSavedBrief(null);
      setProjects(rows => [project, ...rows.filter(row => row.project_id !== project.project_id)]);
      setNotice('Original source project saved to your account. Review the brief, then explicitly start its source build.');
    } catch (reason) {
      if (current() && !admittedProject && reason instanceof ForgeClientError && [400, 401, 403, 404, 409, 413, 422, 423, 429].includes(reason.status)) {
        pendingCreate.current = null;
      }
      throw reason;
    }
  });
  const submit = () => act('submit', async (signal, current) => {
    if (!detail) throw new Error('Create or open a saved source project first.');
    if (pending.current) throw new Error('Check the original uncertain submission before starting another build.');
    const run = sourceOnlyForgeRequest(savedBrief || request, sourceAcknowledged);
    const fresh = await getForgeProject(detail.project.project_id, signal);
    const admission = { key: savedForgeRequestKey(), projectId: fresh.project.project_id, run };
    pending.current = admission;
    try {
      const next = await submitForgeBuild(fresh.project, run, admission.key, signal);
      if (!current()) return;
      adoptJob(next); pending.current = null; setUncertain(false); setDetail(fresh);
      setNotice('Original source build submitted. Leaving this screen stops observation; its saved receipt remains available.');
    } catch (reason) {
      if (current()) {
        const rejected = reason instanceof ForgeClientError && [400, 401, 403, 404, 409, 413, 422, 423, 429].includes(reason.status);
        if (rejected) {
          pending.current = null; setUncertain(false);
          setNotice('The source request was rejected. Your questionnaire is unchanged; review the error before explicitly trying again.');
        } else {
          setUncertain(true); setNotice('Delivery is uncertain. Check the original request; this screen will not submit another build automatically.');
        }
      }
      throw reason;
    }
  });
  const check = () => act('check', async (signal, current) => {
    if (!detail) return;
    const next = await getForgeProject(detail.project.project_id, signal);
    const original = pending.current;
    const recovered = original ? next.builds.find(row => row.request_id === original.key) : job ? next.builds.find(row => row.job_id === job.job_id) : next.builds[0];
    if (!current()) return;
    setDetail(next);
    if (recovered) {
      adoptJob(recovered); pending.current = null; setUncertain(false);
      setNotice('The original saved receipt was read without starting a build.');
    } else if (original) setNotice('The original request is not yet visible. Keep its identity and check again; no second build was submitted.');
  });
  const older = () => act('history', async (signal, current) => {
    if (!detail?.next_cursor) return;
    const projectId = detail.project.project_id;
    const page = await listForgeBuilds(projectId, detail.next_cursor, signal);
    if (!current()) return;
    const seen = new Set(detail.builds.map(row => row.job_id));
    const merged = [...detail.builds, ...page.builds.filter(row => !seen.has(row.job_id))];
    if (merged.length > 512) throw new Error('The source-build history exceeds this project’s supported capacity.');
    setDetail(previous => {
      if (!previous || previous.project.project_id !== projectId) return previous;
      return { ...previous, builds: merged, next_cursor: page.next_cursor };
    });
    const original = pending.current;
    const recovered = original?.projectId === projectId ? merged.find(row => row.request_id === original.key) : null;
    if (recovered) adoptJob(recovered);
  });
  const control = (action: 'cancel' | 'resume') => act(action, async (signal, current) => {
    if (!job) return;
    const next = await controlForgeBuild(job.project_id, job.job_id, action, signal);
    if (current()) { setJob(next); setNotice(action === 'cancel' ? 'Cancellation requested. A committed source archive remains the original result.' : 'Exact prepared source publication resumed. Model generation was not requested.'); }
  });
  const download = () => act('download', async (signal, current) => {
    if (!job) return;
    const exact = await getForgeBuild(job.project_id, job.job_id, signal);
    const bytes = await downloadForgeBuild(exact, signal);
    if (!current()) return;
    await shareSavedForgeZip(bytes, exact.job_id, current);
    if (current()) setNotice('The original source ZIP passed its byte-count and SHA-256 checks. Extract it and open project.godot in Godot.');
  });

  const selectedRequest = savedBrief || request;
  const active = !!job && !forgeJobTerminal(job);
  const filteredProjects = projects.filter(project => (project.name + ' ' + project.project_id).toLowerCase().includes(projectQuery.trim().toLowerCase()));
  return (
    <View testID="forge-saved-builds" style={st.root}>
      <SectionTitle hint="Account-backed source library">Saved projects & builds</SectionTitle>
      <Card>
        <Text style={st.copy}>Keep your exact brief, build history and original source ZIP through refresh and reconnect. Your current questionnaire stays separate until you explicitly start a saved build.</Text>
        {projects.length ? <TextInput value={projectQuery} onChangeText={value => { setProjectQuery(value); setProjectLimit(12); }}
          maxLength={120} accessibilityLabel="Search saved source projects" placeholder="Find a saved project" placeholderTextColor={C.mute}
          style={st.input} testID="forge-library-search" /> : null}
        <View style={st.row}>
          <Button label="Refresh saved projects" tone="ghost" compact onPress={() => void refresh()} busy={busy === 'refresh'} disabled={!!busy} testID="forge-library-refresh" />
          {filteredProjects.slice(0, projectLimit).map(project => <Button key={project.project_id} label={project.name}
            tone={detail?.project.project_id === project.project_id ? 'secondary' : 'ghost'} compact
            onPress={() => void openProject(project.project_id)} disabled={!!busy} testID={`forge-project-${project.project_id}`} />)}
        </View>
        {filteredProjects.length > projectLimit ? <Button label="Show more saved projects" tone="ghost" compact
          onPress={() => setProjectLimit(value => value + 12)} testID="forge-projects-more" /> : null}
        {projects.length && !filteredProjects.length ? <Text style={st.muted}>No saved project matches this search.</Text> : null}
        {!projects.length && !busy ? <Text style={st.muted}>No saved source projects loaded. Sign in and refresh, or create your first project.</Text> : null}
        <Text style={st.label} nativeID="forge-project-name-label">New source-project name</Text>
        <TextInput value={name} onChangeText={setName} maxLength={120} editable={!busy}
          accessibilityLabel="New source-project name" placeholder="A small, complete game" placeholderTextColor={C.mute}
          style={st.input} testID="forge-project-name" />
        {pendingCreate.current ? <Text style={st.muted}>Uncertain original creation: {pendingCreate.current.name}. Recovery uses its exact original request; your edited name is preserved.</Text> : null}
        <Button label={pendingCreate.current ? 'Recover original project creation' : 'Create saved source project'}
          onPress={() => void create()} disabled={!!busy || (!pendingCreate.current && !name.trim())} busy={busy === 'create'} testID="forge-project-create" />
      </Card>
      {error ? <Banner tone="bad" testID="forge-library-error">{error}</Banner> : null}
      {notice ? <Banner tone="idle" testID="forge-library-notice">{notice}</Banner> : null}
      {detail ? <Card label={detail.project.name}>
        <Text style={st.muted}>Saved project v{detail.project.version} · {detail.project.project_id}</Text>
        <Text style={st.label}>{savedBrief ? 'Explicitly selected saved brief' : 'Current questionnaire'}</Text>
        <Text style={st.copy}>{selectedRequest.vision || 'Describe your game in the questionnaire.'}</Text>
        <Text style={st.muted}>Godot source · {selectedRequest.playable_archetype || selectedRequest.archetype} · {selectedRequest.era || 'Automatic era'}{selectedRequest.quest_content ? ` · ${selectedRequest.quest_length || 3} quest steps` : ''}</Text>
        {savedBrief ? <Button label="Use current questionnaire instead" tone="ghost" compact onPress={() => setSavedBrief(null)} disabled={!!busy} /> : null}
        <Button label={sourceAcknowledged ? '✓ Saved source-only scope reviewed' : 'Review: create source, run native tests separately'}
          tone="ghost" compact onPress={() => setSourceAcknowledged(value => !value)} disabled={!!busy}
          testID="forge-source-scope" />
        <Button label="Start saved source build" onPress={() => void submit()}
          disabled={!!busy || active || uncertain || !sourceAcknowledged || selectedRequest.target !== 'godot' || !selectedRequest.vision.trim()}
          busy={busy === 'submit'} testID="forge-saved-build-start" />
        {selectedRequest.target !== 'godot' ? <Text style={st.muted}>Select Godot in the questionnaire to use this source-build library.</Text> : null}
        {uncertain ? <Text style={st.muted}>Original request: {pending.current?.key}. Keep checking this receipt before starting another build.</Text> : null}
        <Button label="Check original submission" tone="secondary" compact onPress={() => void check()} disabled={!!busy} testID="forge-build-check" />
        <Text style={st.label}>Original build history</Text>
        {!detail.builds.length ? <Text style={st.muted}>No saved builds yet.</Text> : null}
        {detail.builds.map(record => <View style={st.history} key={record.job_id}>
          <Button label={`${record.status} · ${record.brief.playable_archetype || record.brief.archetype} · ${record.job_id.slice(-8)}`}
            tone={record.job_id === job?.job_id ? 'secondary' : 'ghost'} compact disabled={!!busy}
            onPress={() => { adoptJob(record); setError(null); }} testID={`forge-saved-job-${record.job_id}`} />
        </View>)}
        {detail.next_cursor ? <Button label="Load older original builds" tone="ghost" compact disabled={!!busy}
          busy={busy === 'history'} onPress={() => void older()} testID="forge-build-history-more" /> : null}
      </Card> : null}
      {job ? <Card label="Original saved build">
        <StatusPill tone={job.status === 'completed' ? 'ok' : ['failed', 'cancelled'].includes(job.status) ? 'bad' : 'idle'} label={job.status} testID="forge-saved-status" />
        <Text style={st.muted}>{job.job_id}</Text>
        <Text style={st.copy}>{job.brief.vision}</Text>
        {job.error ? <Banner tone="warn">{typeof job.error === 'string' ? job.error : job.error.message || job.error.code || 'The original build stopped.'}</Banner> : null}
        {job.recovery === 'new_request_required' ? <Text style={st.muted}>Execution was interrupted before an exact source result was committed. This request will not run again. Review the brief and explicitly start a new build.</Text> : null}
        <View style={st.row}>
          {active ? <Button label="Request cancellation" tone="ghost" compact disabled={!!busy} onPress={() => void control('cancel')} testID="forge-build-cancel" /> : null}
          {job.resume_available ? <Button label="Resume exact prepared publication" tone="secondary" compact disabled={!!busy} onPress={() => void control('resume')} testID="forge-build-resume" /> : null}
          <Button label="Use this saved brief for a new build" tone="ghost" compact disabled={!!busy || active}
            onPress={() => { setSavedBrief(job.brief); setSourceAcknowledged(false); setNotice('Saved brief selected. Review its source scope before explicitly starting another build.'); }} testID="forge-brief-reuse" />
          {job.status === 'completed' ? <Button label="Download original Godot ZIP" disabled={!!busy} busy={busy === 'download'}
            onPress={() => void download()} testID="forge-saved-download" /> : null}
        </View>
        {job.status === 'completed' && job.result?.build ? <ForgeRunPanel phase="done" payload={job.result.build} testID="forge-recovered-result" /> : null}
      </Card> : null}
    </View>
  );
}

const st = StyleSheet.create({
  root: { gap: 10, marginBottom: 20 }, row: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginVertical: 8 },
  input: { color: C.text, backgroundColor: C.cardAlt, borderColor: C.border, borderWidth: 1, borderRadius: 10, padding: 12, marginBottom: 10 },
  label: { color: C.textStrong, fontWeight: '700', fontSize: 13, marginTop: 12, marginBottom: 6 },
  copy: { color: C.text, fontSize: 14, lineHeight: 21 }, muted: { color: C.mute, fontSize: 12, lineHeight: 18 },
  history: { marginVertical: 3 },
});
