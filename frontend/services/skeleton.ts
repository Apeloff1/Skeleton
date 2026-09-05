/**
 * Skeleton v16 API client — talks to the rebuilt FastAPI surface at /api/v1.
 *
 * The legacy CodeDock client in api.ts still covers /api/ai-toolkit and friends.
 * This module is the typed client for the hexagonal Skeleton backend.
 */

import Constants from 'expo-constants';

const BASE =
  (Constants.expoConfig?.extra?.EXPO_SKELETON_URL as string | undefined) ||
  (Constants.expoConfig?.extra?.EXPO_PUBLIC_SKELETON_URL as string | undefined) ||
  (Constants.expoConfig?.extra?.EXPO_BACKEND_URL as string | undefined) ||
  '';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${BASE}${path}`;
  const response = await fetch(url, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers as Record<string, string> | undefined),
    },
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      (body && (body.message || body.detail || body.error)) || `HTTP ${response.status}`;
    throw new Error(String(detail));
  }
  return body as T;
}

export const skeletonAPI = {
  health: () => request<{ status: string; checks: Record<string, boolean> }>('/health'),

  capabilities: () =>
    request<Array<{ name: string; kind: string; version: string }>>('/api/v1/capabilities'),

  openSession: (userId: string, mode: 'tutoring' | 'co_coding' = 'tutoring') =>
    request<{ session_id: string; mode: string; status: string }>('/api/v1/jeeves/session', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId, mode }),
    }),

  ask: (sessionId: string, input: string, context?: Record<string, unknown>) =>
    request<{ response: string; session_id: string }>('/api/v1/jeeves/interact', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, input, context }),
    }),

  reviewCode: (sessionId: string, code: string) =>
    request<{ findings: Array<{ line: number; severity: string; message: string }>; summary: string }>(
      '/api/v1/jeeves/review',
      { method: 'POST', body: JSON.stringify({ session_id: sessionId, code }) },
    ),

  matrices: (sessionId: string) =>
    request<{ sam: Record<string, number>; clom: Record<string, unknown>; krem: Record<string, number> }>(
      `/api/v1/jeeves/matrices/${encodeURIComponent(sessionId)}`,
    ),

  generateNpc: (description: string, opts?: { name?: string; dialogue_beats?: number }) =>
    request<{ npc: Record<string, unknown>; status: string }>('/api/v1/pipeline/npc', {
      method: 'POST',
      body: JSON.stringify({ description, ...opts }),
    }),

  generateGameLogic: (description: string, opts?: { title?: string; curve?: string }) =>
    request<{ game_logic: Record<string, unknown>; status: string }>('/api/v1/pipeline/game-logic', {
      method: 'POST',
      body: JSON.stringify({ description, ...opts }),
    }),

  generateAnimation: (description: string, actions?: string[]) =>
    request<{ animation: Record<string, unknown>; status: string }>('/api/v1/pipeline/animation', {
      method: 'POST',
      body: JSON.stringify({ description, actions }),
    }),

  materialise: (name: string, components: Array<{ kind: string; instance_id: string }>, wires: Array<{ from: [string, string]; to: [string, string] }>) =>
    request<{ artefact: Record<string, unknown>; status: string }>('/api/v1/forge/materialise', {
      method: 'POST',
      body: JSON.stringify({ name, components, wires }),
    }),

  joinAgent: (specialisations: string[]) =>
    request<{ agent_id: string; status: string }>('/api/v1/swarm/agent', {
      method: 'POST',
      body: JSON.stringify({ specialisations }),
    }),

  swarmStats: () => request<Record<string, unknown>>('/api/v1/swarm/stats'),

  sanitise: (input: string, userId = 'anonymous') =>
    request<{ sanitized: string; threat_level: string }>('/api/v1/resilience/sanitise', {
      method: 'POST',
      body: JSON.stringify({ input, user_id: userId }),
    }),

  reason: (query: string, context?: Record<string, unknown>) =>
    request<Record<string, unknown>>('/api/v1/intelligence/reason', {
      method: 'POST',
      body: JSON.stringify({ query, context }),
    }),
};

export default skeletonAPI;
