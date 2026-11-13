/** Projects tab: the unified vault list (shared cached query with /vault). */
import { useRouter } from 'expo-router';
import { FlatList, Pressable, RefreshControl } from 'react-native';
import api from '../../../src/utils/apiClient';
import {
  AppText, AsyncView, getJson, minTouch, parseVault, Row, Screen, Stack, color, composeLabel, space, useQuery, useT, vaultKey,
} from '../../../src/foundation';
import type { VaultItem, VaultList } from '../../../src/foundation';

const fetchVault = async () => parseVault(await getJson<unknown>(api, '/api/gameforge/studio/vault/unified?limit=80', 20_000));

export default function ProjectsTab() {
  const { t } = useT();
  const router = useRouter();
  const query = useQuery<VaultList>(vaultKey(80), fetchVault, { staleTimeMs: 15_000, isEmpty: d => d.items.length === 0 });
  return (
    <Screen>
      <Stack gap="md" padding="xl" style={{ flex: 1 }}>
        <AppText variant="h1">{t('projects.title')}</AppText>
        <AsyncView query={query} emptyMessage={t('projects.emptyHint')}>
          {data => (
            <FlatList<VaultItem>
              data={data.items}
              keyExtractor={(it, i) => `${it.source}-${it.id}-${i}`}
              ListHeaderComponent={<AppText color="textMuted">{t('projects.count', { count: data.items.length })}</AppText>}
              refreshControl={<RefreshControl refreshing={query.fetching} onRefresh={() => { void query.refetch(); }} />}
              renderItem={({ item }) => (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel={composeLabel(item.name, item.source, item.kind)}
                  onPress={() => router.push('/vault')}
                  style={({ pressed }) => ({ minHeight: minTouch, paddingVertical: space('sm'), borderBottomWidth: 1, borderBottomColor: color.border, opacity: pressed ? 0.7 : 1 })}
                >
                  <Row gap="sm" justify="space-between">
                    <AppText variant="bodyLg" numberOfLines={1} style={{ flex: 1 }}>{item.name}</AppText>
                    <AppText variant="caption" color="textMuted">{item.source}</AppText>
                  </Row>
                  {item.detail ? <AppText variant="caption" color="textSubtle" numberOfLines={1}>{item.detail}</AppText> : null}
                </Pressable>
              )}
            />
          )}
        </AsyncView>
      </Stack>
    </Screen>
  );
}
