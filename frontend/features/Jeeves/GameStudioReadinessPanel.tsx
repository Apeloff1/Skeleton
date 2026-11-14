import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { getAuthToken } from '../../src/auth/gameforgeAuth';
import { getStudioReadiness, type LearningJob, type LearningProject, type StudioReadiness } from '../../src/product/gameLearningClient';
import s, { gameLearningColors as C } from './GameLearningWorkspace.styles';
import v from './GameConsoleStudio.styles';

function human(value: unknown) { return String(value ?? '').replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase()); }
function Button({ label, press, disabled }: { label: string; press: () => void; disabled?: boolean }) { return <TouchableOpacity accessibilityRole="button" accessibilityState={{ disabled }} disabled={disabled} onPress={press} style={[s.button, disabled && s.disabled]}><Text style={s.buttonText}>{label}</Text></TouchableOpacity>; }
function count(value: unknown) { return typeof value === 'number' && Number.isFinite(value) ? value.toLocaleString() : null; }

export default function GameStudioReadinessPanel({ project, jobs, dirty, onOpenJob, onOpenPlay, onOpenGoal, onCampaigns, onBuild, onSources }: {
  project?: LearningProject | null; jobs: LearningJob[]; dirty?: boolean; onOpenJob: (id: string) => void; onOpenPlay: (id: string) => void;
  onOpenGoal: (id: string) => void; onCampaigns: (id?: string) => void; onBuild: () => void; onSources: () => void;
}) {
  const [value, setValue] = useState<StudioReadiness | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState<string | null>(null); const [revision, setRevision] = useState(0); const [toolchainQuery, setToolchainQuery] = useState(''); const [details, setDetails] = useState(false);
  const mounted = useRef(true); const owner = useRef({ token: getAuthToken(), projectId: project?.project_id }); const current = useRef(project); current.current = project;
  const safe = useCallback(() => mounted.current && owner.current.token === getAuthToken() && owner.current.projectId === current.current?.project_id, []);
  useEffect(() => {
    mounted.current = true; let active = true; let timer: ReturnType<typeof setTimeout>; const controller = new AbortController();
    const refresh = async () => {
      try { const result = await getStudioReadiness(project?.project_id, { signal: controller.signal }); if (active && safe() && !controller.signal.aborted) { setValue(result); setError(null); } }
      catch (caught) { if (active && safe() && !controller.signal.aborted) setError(caught instanceof Error ? caught.message : 'Readiness could not be checked.'); }
      finally { if (active && safe()) { setLoading(false); timer = setTimeout(() => { void refresh(); }, 20000); } }
    };
    setLoading(true); void refresh(); return () => { active = false; mounted.current = false; clearTimeout(timer); controller.abort(); };
  }, [project?.project_id, project?.version, revision, safe]);
  const scope = value?.project_scope; const stale = !!project && !!scope && scope.version !== project.version;
  const checks = value?.checks || []; const issues = checks.filter(check => check.status !== 'ready');
  const work: (Record<string, unknown> & { category: string; identity: unknown })[] = scope ? [
    ...scope.active_jobs.map(row => ({ ...row, category: 'job', identity: row.job_id })),
    ...scope.active_plays.map(row => ({ ...row, category: 'play', identity: row.play_id })),
    ...scope.goals.filter(row => !['completed', 'cancelled', 'expired', 'planned'].includes(String(row.status))).map(row => ({ ...row, category: 'goal', identity: row.goal_id })),
    ...scope.campaigns.filter(row => !['completed', 'cancelled'].includes(String(row.status))).map(row => ({ ...row, category: 'campaign', identity: row.campaign_id })),
  ].slice(0, 64) : [];
  const toolchains = value?.toolchains.filter(row => (row.id + ' ' + row.message).toLowerCase().includes(toolchainQuery.toLowerCase())) || [];
  const open = (row: { category: string; identity: unknown }) => { if (typeof row.identity !== 'string') return; if (row.category === 'job') onOpenJob(row.identity); else if (row.category === 'play') onOpenPlay(row.identity); else if (row.category === 'goal') onOpenGoal(row.identity); else onCampaigns(row.identity); };
  return <View style={v.workspace}>
    <View style={s.section}><View style={s.between}><Text accessibilityRole="header" style={s.sectionTitle}>Studio readiness</Text><Button label="Check readiness now" disabled={loading} press={() => setRevision(value => value + 1)} /></View>
      <Text style={s.description}>See what is available for editing, play, learning and native builds, and the setup each unavailable feature needs.</Text>
      {loading && <View style={s.row}><ActivityIndicator color={C.primaryHover} /><Text style={s.muted}>Checking the actual studio services…</Text></View>}
      {error && <Text accessibilityRole="alert" style={s.error}>{error}{value ? ' The last observed readiness remains below.' : ''}</Text>}
      {value && <><Text style={value.status === 'ready' ? s.success : s.unavailable}>{value.status === 'ready' ? 'Studio services ready' : value.status === 'partial' ? 'Some features need setup' : 'Studio setup needs attention'}</Text><Text style={s.dim}>Observed {new Date(value.observed_at).toLocaleString()}</Text><View style={v.responsiveCards}>{checks.map(check => <View key={check.id} style={v.card}><Text style={s.projectName}>{check.label}</Text><Text style={check.status === 'ready' ? s.success : s.unavailable}>{check.status === 'ready' ? 'Ready' : check.status === 'blocked' ? 'Needs attention' : 'Unavailable'}</Text><Text style={s.description}>{check.message}</Text>{check.setup && <Text selectable style={s.muted}>{check.setup}</Text>}{details && check.capabilities?.length ? <Text style={s.dim}>{check.capabilities.map(human).join(' · ')}</Text> : null}</View>)}</View>
        <View style={s.metrics}>{[['Approved console cores', value.native_cores.observed === false ? null : value.native_cores.approved], ['Mapped console targets', value.native_cores.observed === false ? null : value.native_cores.mapped_targets], ['Worker limit', value.worker.capacity], ['Active jobs', value.worker.active_jobs], ['Open play sessions', value.worker.active_plays]].map(([label, number]) => <View key={String(label)} style={s.metric}><Text style={s.metricValue}>{count(number) ?? 'Not observed'}</Text><Text style={s.metricLabel}>{label}</Text></View>)}</View>
        {value.native_cores.observed === false && <Text style={s.muted}>Native core readiness has not been observed yet. Check again after the pending probe completes.</Text>}<Text style={s.muted}>{value.model.available === true ? 'Canonical model planning is available.' : value.model.available === false ? 'Canonical model planning is unavailable.' : 'Model execution has not been probed; readiness is not established.'} {value.worker.recovery_scheduler_running ? 'Worker recovery is running.' : 'Worker recovery is not running.'}</Text>
        {issues.length > 0 && <Text style={s.dim}>{issues.length} readiness {issues.length === 1 ? 'item requires' : 'items require'} attention. Source editing and read-only inspection use their own admission checks.</Text>}
        <Button label={details ? 'Hide capability details' : 'Show capability details'} press={() => setDetails(value => !value)} />
      </>}
    </View>
    {project && <View style={s.section}><Text accessibilityRole="header" style={s.sectionTitle}>Work and recovery in this project</Text>{dirty && <Text style={s.notice}>You have unsaved edits. Save or discard them before starting work in another pane.</Text>}{stale && <Text style={s.notice}>This overview observed revision {scope?.version}; the editor is on revision {project.version}. Refresh for current work.</Text>}
      {work.length ? work.map((row, index) => { const job = jobs.find(job => job.job_id === row.identity); const rawProgress = job?.progress || row.progress as LearningJob['progress']; const progress = rawProgress && Number.isFinite(rawProgress.completed) && Number.isFinite(rawProgress.total) && rawProgress.total > 0 && rawProgress.completed >= 0 && rawProgress.completed <= rawProgress.total ? rawProgress : null; const cursor = count(row.cursor); const steps = count(row.steps); return <View key={String(row.identity || index)} style={s.source}><View style={s.between}><View style={{ flex: 1, gap: 4 }}><Text style={s.projectName}>{row.category === 'goal' && typeof row.goal === 'string' ? row.goal : human(row.kind || row.category)}</Text><Text style={s.muted}>{human(row.status)}{progress ? ` · ${progress.completed.toLocaleString()} / ${progress.total.toLocaleString()} ${progress.unit}` : cursor !== null ? ` · ${cursor} committed ${row.category === 'campaign' ? 'rounds' : 'steps'}` : steps !== null ? ` · ${steps} measured steps` : ''}</Text></View><Button label={row.category === 'goal' ? 'Open goal' : row.category === 'play' ? 'Open play' : row.category === 'campaign' ? 'Open campaign' : 'Open job'} disabled={!!dirty || typeof row.identity !== 'string'} press={() => open(row)} /></View>{typeof row.pending_job_id === 'string' && <Text style={s.dim}>Waiting for an issued background job.</Text>}{typeof row.stop_requested === 'string' && <Text style={s.notice}>{human(row.stop_requested)} requested · awaiting the current operation boundary</Text>}</View>; }) : <Text style={s.muted}>{value ? 'No active work was reported in this project.' : 'Active work appears after readiness is checked.'}</Text>}
      <View style={s.chips}><Button label="Jeeves goals" disabled={!!dirty} press={() => onOpenGoal('')} /><Button label="Learning campaigns" disabled={!!dirty} press={() => onCampaigns()} /><Button label="Build & core readiness" disabled={!!dirty} press={onBuild} /><Button label="Source permissions" disabled={!!dirty} press={onSources} /></View>
    </View>}
    {details && value && <View style={s.section}><Text accessibilityRole="header" style={s.sectionTitle}>Native toolchains</Text><TextInput accessibilityLabel="Find a native toolchain" value={toolchainQuery} onChangeText={setToolchainQuery} placeholder="Find target or setup requirement" placeholderTextColor={C.textDim} maxLength={100} style={s.field} />{toolchains.slice(0, 32).map(row => <View key={row.id} style={s.source}><Text style={s.projectName}>{human(row.id)}</Text><Text style={row.status === 'ready' ? s.success : s.muted}>{human(row.status)}</Text><Text selectable style={s.description}>{row.message}</Text></View>)}{toolchains.length > 32 && <Text style={s.dim}>Showing the first 32 matching toolchains. Refine your search.</Text>}</View>}
  </View>;
}
