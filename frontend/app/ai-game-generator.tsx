import React from 'react';
import { ActivityIndicator, View } from 'react-native';
import { useRouter } from 'expo-router';

import { withScreenGuard } from '../components/withScreenGuard';
import { queueGameBuilderArtifact } from '../features/GameFactory/gameBuilderHandoff';
import theme from '../theme/tokens';

const LazyAIGameGeneratorModal = React.lazy(() =>
  import('../features/AIGameGenerator/AIGameGeneratorModal').then((module) => ({
    default: module.AIGameGeneratorModal,
  })),
);

function AIGameGeneratorRoute() {
  const router = useRouter();

  const close = React.useCallback(() => {
    try {
      if (router.canGoBack()) router.back();
      else router.replace('/hub');
    } catch {
      try { router.replace('/hub'); } catch { /* swallow */ }
    }
  }, [router]);

  const handleGenerated = React.useCallback((data: unknown, type: string) => {
    queueGameBuilderArtifact(data, type);
    router.replace('/game-factory');
  }, [router]);

  return (
    <React.Suspense
      fallback={
        <View style={{ flex: 1, backgroundColor: '#05070d', alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator color="#A78BFA" />
        </View>
      }
    >
      <LazyAIGameGeneratorModal
        visible
        onClose={close}
        colors={theme.colors as any}
        onGenerated={handleGenerated}
      />
    </React.Suspense>
  );
}

AIGameGeneratorRoute.displayName = 'AIGameGeneratorRoute';

export default withScreenGuard(AIGameGeneratorRoute, 'AIGameGeneratorRoute');
