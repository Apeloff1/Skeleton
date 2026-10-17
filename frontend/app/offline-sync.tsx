import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/OfflineSync/OfflineSyncModal'), 'OfflineSyncRoute', 'OfflineSyncModal');
