/**
 * notifications — thin wrapper around expo-notifications for local
 * scheduling. Used by the Scheduler/Calendar to fire reminders.
 *
 * Web is a no-op (Expo notifications don't reliably hook the browser
 * notification API in our preview build), but we keep the API surface
 * stable so the calling code doesn't have to branch on platform.
 *
 * Public surface:
 *   • ensureNotificationPermission()      — idempotent request + status
 *   • scheduleEventReminder({...})        — schedules a 1-shot reminder,
 *                                            returns notification id (or null)
 *   • cancelEventReminder(notificationId) — cancels a previously scheduled id
 */
import { Platform } from 'react-native';

let _notifModule: any = null;
function _getModule() {
  if (_notifModule) return _notifModule;
  try {
    // dynamic require so a failed native module (e.g. on web in preview)
    // doesn't crash the bundle.
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    _notifModule = require('expo-notifications');
    // Default handler — show banner + play sound when foreground.
    _notifModule.setNotificationHandler?.({
      handleNotification: async () => ({
        shouldShowAlert: true,
        shouldShowBanner: true,
        shouldShowList: true,
        shouldPlaySound: true,
        shouldSetBadge: false,
      }),
    });
    return _notifModule;
  } catch {
    _notifModule = null;
    return null;
  }
}

export async function ensureNotificationPermission(): Promise<boolean> {
  if (Platform.OS === 'web') return false;
  const N = _getModule();
  if (!N) return false;
  try {
    const cur = await N.getPermissionsAsync();
    if (cur?.granted) return true;
    if (cur?.status === 'denied' && cur?.canAskAgain === false) return false;
    const req = await N.requestPermissionsAsync();
    return !!req?.granted;
  } catch {
    return false;
  }
}

export interface ScheduleEventInput {
  title: string;
  body?: string;
  /** YYYY-MM-DD */
  date: string;
  /** HH:mm — if missing, defaults to 09:00 */
  time?: string;
  /** Minutes BEFORE the event to fire the reminder (default 0). */
  leadMinutes?: number;
  /** Extra data attached to the notification payload. */
  data?: Record<string, any>;
}

/**
 * scheduleEventReminder — returns the notification id, or null if the
 * scheduled time is in the past or the platform doesn't support it.
 */
export async function scheduleEventReminder(
  input: ScheduleEventInput,
): Promise<string | null> {
  if (Platform.OS === 'web') return null;
  const N = _getModule();
  if (!N) return null;
  const ok = await ensureNotificationPermission();
  if (!ok) return null;

  const [y, m, d] = (input.date || '').split('-').map(Number);
  if (!y || !m || !d) return null;
  const [hh, mm] = (input.time || '09:00').split(':').map(Number);
  const target = new Date(y, (m || 1) - 1, d || 1, hh || 0, mm || 0, 0, 0);
  const lead = Math.max(0, input.leadMinutes || 0);
  const fireAt = new Date(target.getTime() - lead * 60_000);
  if (fireAt.getTime() <= Date.now() + 2_000) return null; // ignore past

  try {
    const id = await N.scheduleNotificationAsync({
      content: {
        title: input.title || 'Reminder',
        body: input.body || `${input.date}${input.time ? ' • ' + input.time : ''}`,
        data: input.data || {},
      },
      trigger: { type: 'date', date: fireAt } as any,
    });
    return typeof id === 'string' ? id : null;
  } catch {
    return null;
  }
}

export async function cancelEventReminder(notificationId: string | null | undefined): Promise<void> {
  if (!notificationId) return;
  if (Platform.OS === 'web') return;
  const N = _getModule();
  if (!N) return;
  try { await N.cancelScheduledNotificationAsync(notificationId); } catch {}
}

/** Cancel ALL scheduled notifications — useful for a "clear reminders" action. */
export async function cancelAllReminders(): Promise<void> {
  if (Platform.OS === 'web') return;
  const N = _getModule();
  if (!N) return;
  try { await N.cancelAllScheduledNotificationsAsync(); } catch {}
}
