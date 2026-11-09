import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/Progress/ProgressModal'), 'ProgressRoute', 'ProgressModal');
