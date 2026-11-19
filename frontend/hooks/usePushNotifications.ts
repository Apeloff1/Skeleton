import { useState, useEffect, useRef } from 'react';
import { Platform } from 'react-native';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';

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
  const notificationListener = useRef<any>(null);
  const responseListener = useRef<any>(null);

  useEffect(() => {
    // Pass empty string as projectId fallback if none
    registerForPushNotificationsAsync().then((token) => {
      if (token) setExpoPushToken(token);
    });

    notificationListener.current = Notifications.addNotificationReceivedListener((notification) => {
      setNotification(notification);
    });

    responseListener.current = Notifications.addNotificationResponseReceivedListener((response) => {
      console.log('Notification Response:', response);
    });

    return () => {
      if (notificationListener.current) {
        notificationListener.current.remove();
      }
      if (responseListener.current) {
        responseListener.current.remove();
      }
    };
  }, []);

  return {
    expoPushToken,
    notification,
  };
}

async function registerForPushNotificationsAsync() {
  let token;
  if (Platform.OS === 'android') {
    await Notifications.setNotificationChannelAsync('default', {
      name: 'default',
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 250, 250, 250],
      lightColor: '#FF231F7C',
    });
  }

  if (Device.isDevice) {
    const { status: existingStatus } = await Notifications.getPermissionsAsync();
    let finalStatus = existingStatus;
    if (existingStatus !== 'granted') {
      const { status } = await Notifications.requestPermissionsAsync();
      finalStatus = status;
    }
    if (finalStatus !== 'granted') {
      console.log('Failed to get push token for push notification!');
      return;
    }
    // New expo SDK requires valid project ID string
    try {
      token = (await Notifications.getExpoPushTokenAsync({ projectId: 'codedock' })).data;
    } catch(e) {
      console.log(e);
    }
  } else {
    console.log('Must use physical device for Push Notifications');
  }
  return token;
}

export async function scheduleDailyReminder() {
  await Notifications.cancelAllScheduledNotificationsAsync();
  
  await Notifications.scheduleNotificationAsync({
    content: {
      title: "Daily Rosetta Challenge! 🚀",
      body: "Keep your polyglot streak alive. 1,500+ concepts await you!",
      sound: true,
    },
    trigger: {
      seconds: 86400,
      repeats: true,
    } as any,
  });
}
