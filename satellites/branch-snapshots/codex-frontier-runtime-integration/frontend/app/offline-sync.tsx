import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/OfflineSync/OfflineSyncModal'), 'OfflineSyncRoute', 'OfflineSyncModal');
