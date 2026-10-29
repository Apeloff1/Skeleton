/**
 * Ecosystem client — full-stack bridge to /api/ecosystem.
 * Create a session, run the pipeline, poll status, and export Godot files.
 */
import api from '../utils/apiClient';

export type EcosystemSession = {
  session_id: string;
  status?: string;
  era?: string;
  sealed?: boolean;
  rooms?: number;
  tier?: string;
  godot_count?: number;
  reason?: string;
};

export async function createSession(brief: string, era = 'ash'): Promise<EcosystemSession> {
  const r = await api.post<EcosystemSession>('/api/ecosystem/session', { brief, era });
  return r.data;
}

export async function runSession(sessionId: string): Promise<EcosystemSession> {
  const r = await api.post<EcosystemSession>('/api/ecosystem/run', { session_id: sessionId });
  return r.data;
}

export async function getSession(sessionId: string): Promise<EcosystemSession> {
  const r = await api.get<EcosystemSession>(`/api/ecosystem/session/${sessionId}`);
  return r.data;
}

export async function exportGodot(sessionId: string): Promise<{ ok: boolean; files: { path: string; content: string }[] }> {
  const r = await api.get(`/api/ecosystem/session/${sessionId}/export`);
  return r.data;
}

export async function listSessions(limit = 20): Promise<{ count: number; sessions: EcosystemSession[] }> {
  const r = await api.get(`/api/ecosystem/sessions?limit=${limit}`);
  return r.data;
}

export async function ecosystemHealth(): Promise<Record<string, unknown>> {
  const r = await api.get('/api/ecosystem/health');
  return r.data;
}

/** One-shot: create + run + return sealed result. */
export async function buildGame(brief: string, era = 'ash'): Promise<EcosystemSession> {
  const created = await createSession(brief, era);
  if (!created.session_id) return created;
  return runSession(created.session_id);
}
