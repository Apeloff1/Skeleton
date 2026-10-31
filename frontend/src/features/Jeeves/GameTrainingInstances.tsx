import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Text, TouchableOpacity, View, useWindowDimensions } from 'react-native';
import { ChatClientError } from '../../product/chatErrors';
import { getAuthToken } from '../../auth/gameforgeAuth';
import { getGameTrainingInstances, type GameTrainingInstance } from '../../product/gamePlayClient';
import { learningJobTerminal, type LearningJob } from '../../product/gameLearningClient';
import GameLearningFrame from './GameLearningFrame';
import s, { gameLearningColors as C } from './GameLearningWorkspace.styles';
function human(value: string) { return value.replace(/_/g, ' ').replace(/\b\w/g, letter => letter.toUpperCase()); }
function Metrics({ instance }: { instance: GameTrainingInstance }) {
  const measured = Object.entries({ episode: instance.episode, steps: instance.steps, reward: instance.reward, ...instance.metrics })
    .filter((entry): entry is [string, number] => typeof entry[1] === 'number' && Number.isFinite(entry[1])).slice(0, 8);
  return <View style={s.chips}>{measured.map(([key, value]) => <Text key={key} style={s.muted}>{human(key)}: {value.toLocaleString(undefined, { maximumFractionDigits: 3 })}</Text>)}</View>;
}
/** Sampled frames belong to real learning actors, with no frontend simulation. */
export default function GameTrainingInstances({ job }: { job: LearningJob }) {
  const [instances, setInstances] = useState<GameTrainingInstance[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
  const { width } = useWindowDimensions();
  const previous = useRef(new Map<string, GameTrainingInstance>());
  const account = getAuthToken();
  useEffect(() => {
    let active = true; let timer: ReturnType<typeof setTimeout>; const controller = new AbortController();
    const token = getAuthToken(); let streamId: string | null = null; previous.current.clear(); setInstances([]); setSelected(null); setLoading(true); setError(null);
    const poll = async () => {
      if (!active || token !== getAuthToken()) return;
      try {
        const result = await getGameTrainingInstances(job.job_id, { signal: controller.signal });
        if (!active || token !== getAuthToken()) return;
        if (streamId && streamId !== result.stream_id) previous.current.clear(); streamId = result.stream_id || null;
        const values = result.instances.map(instance => {
          const old = previous.current.get(instance.instance_id);
          if (old && instance.frame_sequence < old.frame_sequence) return old;
          if (old && instance.frame_sequence === old.frame_sequence) instance = { ...instance, latest_frame: old.latest_frame };
          previous.current.set(instance.instance_id, instance); return instance;
        });
        setInstances(values); setSelected(current => values.some(value => value.instance_id === current) ? current : values[0]?.instance_id || null); setError(null);
      } catch (caught) { if (active && !controller.signal.aborted && token === getAuthToken()) { setError(caught instanceof Error ? caught.message : 'The worker frames could not be loaded.'); if (caught instanceof ChatClientError && [401, 403, 404, 409, 410].includes(caught.status)) { setInstances([]); setSelected(null); setLoading(false); active = false; } } }
      finally { if (active && token === getAuthToken()) setLoading(false); }
      if (active && !learningJobTerminal(job)) timer = setTimeout(() => { void poll(); }, 750);
    };
    void poll();
    return () => { active = false; controller.abort(); clearTimeout(timer); };
  }, [job.job_id, job.status, account, revision]);
  const selectedInstance = instances.find(value => value.instance_id === selected);
  return <View style={s.section}>
    <View style={s.between}><Text accessibilityRole="header" style={s.sectionTitle}>Watch AI learning</Text><Text style={s.badge}>{instances.length ? `${instances.length} actual ${instances.length === 1 ? 'instance' : 'instances'}` : human(job.status)}</Text></View>
    <Text style={s.description}>Each view shows an independent actor’s latest measured frame and task progress. Watching a learner does not take control of it.</Text>
    {loading && <ActivityIndicator color={C.primaryHover} />}
    {!!error && <View style={s.alert}><Text accessibilityRole="alert" style={s.error}>{error}</Text><TouchableOpacity accessibilityRole="button" style={s.button} onPress={() => setRevision(value => value + 1)}><Text style={s.buttonText}>Reconnect worker view</Text></TouchableOpacity></View>}
    {!loading && !instances.length && !error && <Text style={s.muted}>{learningJobTerminal(job) ? 'This job has no captured actor frames.' : 'Waiting for the actual workers to report their first observations…'}</Text>}
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 12 }}>{instances.map((instance, index) => <TouchableOpacity key={instance.instance_id}
      accessibilityRole="button" accessibilityLabel={`Inspect AI instance ${index + 1}`} accessibilityState={{ selected: selected === instance.instance_id }} onPress={() => setSelected(instance.instance_id)}
      style={[s.source, { width: width < 760 ? '100%' : instances.length === 1 ? '100%' : '48%', minWidth: 200 }, selected === instance.instance_id && s.selected]}>
      <View style={s.between}><Text style={s.projectName}>Instance {index + 1}</Text><Text style={s.muted}>{human(instance.status)}</Text></View>
      <View style={[s.observation, { minHeight: 120, padding: 8 }]}>{instance.latest_frame ? <GameLearningFrame frame={instance.latest_frame} /> : <Text style={s.muted}>No frame has been reported yet.</Text>}</View>
      <Metrics instance={instance} />{instance.task && <Text style={s.muted}>{instance.task}</Text>}
    </TouchableOpacity>)}</View>
    {selectedInstance && <View style={s.alert}><Text style={s.projectName}>Selected instance</Text><Metrics instance={selectedInstance} />
      {selectedInstance.resource && <Text style={s.muted}>Compute: {human(selectedInstance.resource)}</Text>}
      <Text style={s.dim}>Frames are sampled from the learner. Training continues through its own measured transitions.</Text>
    </View>}
  </View>;
}
