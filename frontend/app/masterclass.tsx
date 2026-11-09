import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/Masterclass/MasterclassModal'), 'MasterclassRoute', 'MasterclassModal');
