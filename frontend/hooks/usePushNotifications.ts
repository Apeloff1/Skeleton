/**
 * Push notifications are optional. Missing native services or project
 * identity cannot crash the UI or mutate state after unmount.
 */
import { useState, useEffect } from 'react';
import { Platform } from 'react-native';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';
import AsyncStorage from '@react-native-async-storage/async-storage';

const DAILY_REMINDER_KEY = '@codedock/notifications/daily_reminder_id';

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
    priority: Notifications.AndroidNotificationPriority.HIGH,
  }),
});

export function usePushNotifications() {
  const [expoPushToken, setExpoPushToken] = useState<string>('');
  const [notification, setNotification] = useState<Notifications.Notification | null>(null);

  useEffect(() => {
    let disposed = false;
    const received = Notifications.addNotificationReceivedListener(next => {
      if (!disposed) setNotification(next);
    });
    const response = Notifications.addNotificationResponseReceivedListener(() => {
      // Avoid logging entire notification payloads into release diagnostics.
    });

    void registerForPushNotificationsAsync()
      .then(token => {
        if (!disposed && token) setExpoPushToken(token);
      })
      .catch(error => {
        if (!disposed) console.warn('Push registration unavailable:', error);
      });

    return () => {
      disposed = true;
      received.remove();
      response.remove();
    };
  }, []);

  return { expoPushToken, notification };
}

async function registerForPushNotificationsAsync(): Promise<string | undefined> {
  if (Platform.OS === 'web' || !Device.isDevice) return undefined;

  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('default', {
      name: 'default',
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#FF231F7C',
    });
  }

  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  const finalStatus = existingStatus === 'granted'
    ? existingStatus
    : (await Notifications.requestPermissionsAsync()).status;
  if (finalStatus !== 'granted') return undefined;

  // Project ID must come from EAS/Expo configuration, not a placeholder.
  const projectId: unknown = Constants.easConfig?.projectId ??
    Constants.expoConfig?.extra?.eas?.projectId;
  if (typeof projectId !== 'string' || projectId.length === 0) {
    return undefined;
  }
  return (await Notifications.getExpoPushTokenAsync({ projectId })).data;
}

/**
 * Rescheduling only touches the reminder owned by this feature; clearing
 * every notification would delete unrelated user/app reminders.
 * Persist the replacement ID before cancelling the old ID.
 */
export async function scheduleDailyReminder(): Promise<void> {
  const previousId = await AsyncStorage.getItem(DAILY_REMINDER_KEY);
  const newId = await Notifications.scheduleNotificationAsync({
    content: {
      title: 'Daily Rosetta Challenge! 🚀',
      body: 'Keep your polyglot streak alive. 1,500+ concepts await you!',
      sound: true,
    },
    trigger: { seconds: 86_400, repeats: true } as Notifications.NotificationTriggerInput,
  });
  try {
    await AsyncStorage.setItem(DAILY_REMINDER_KEY, newId);
  } catch (error) {
    await Notifications.cancelScheduledNotificationAsync(newId).catch(() => {});
    throw error;
  }
  if (previousId && previousId !== newId) {
    try {
      await Notifications.cancelScheduledNotificationAsync(previousId);
    } catch (error) {
      console.warn('Previous daily reminder could not be cancelled:', error);
    }
  }
}
