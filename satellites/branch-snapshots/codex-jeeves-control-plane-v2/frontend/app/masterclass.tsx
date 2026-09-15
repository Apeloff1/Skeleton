import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/Masterclass/MasterclassModal'), 'MasterclassRoute', 'MasterclassModal');
