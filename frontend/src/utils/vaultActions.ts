/**
 * vaultActions — client helpers for the unified vault read / download / restore /
 * fetch-into-system flows. Download uses Linking (native) / anchor (web) so no
 * extra native file deps are required.
 */
import { Platform, Linking } from 'react-native';
import api from './apiClient';
import { authHeaders } from '../auth/gameforgeAuth';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const S = '/api/gameforge/studio';

export function vaultDownloadUrl(fileId: string): string {
  return `${BACKEND}${S}/vault/${fileId}/download`;
}

export async function downloadToDevice(fileId: string, filename: string): Promise<{ ok: boolean; error?: string }> {
  const url = vaultDownloadUrl(fileId);
  if (Platform.OS === 'web') {
    try {
      const a = document.createElement('a');
      a.href = url;
      a.download = filename || 'vault-file';
      a.target = '_blank';
      document.body.appendChild(a);
      a.click();
      a.remove();
      return { ok: true };
    } catch (e: any) {
      return { ok: false, error: e?.message };
    }
  }
  try {
    await Linking.openURL(url);
    return { ok: true };
  } catch (e: any) {
    return { ok: false, error: e?.message };
  }
}

export function fetchBoardroomContent(fileId: string) {
  return api.get<any>(`${S}/vault/${fileId}`, { timeoutMs: 15000 });
}

export function fetchBoardroomVersions(fileId: string) {
  return api.get<any>(`${S}/vault/${fileId}/versions`, { timeoutMs: 15000 });
}

export function rollbackVault(fileId: string, toVersion: number) {
  return api.post<any>(`${S}/vault/${fileId}/rollback`, { to_version: toVersion }, { headers: authHeaders(), timeoutMs: 15000 });
}

export function fetchToSystem(fileId: string, system: 'gamefiles' | 'knowledge', gameName = 'Studio') {
  return api.post<any>(`${S}/vault/${fileId}/fetch-to`, { system, game_name: gameName }, { headers: authHeaders(), timeoutMs: 15000 });
}

export function fetchMonograph(id: string) {
  return api.get<any>(`/api/worldforge/monograph/saved/${id}`, { timeoutMs: 15000 });
}
