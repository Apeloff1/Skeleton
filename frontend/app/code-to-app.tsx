import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/CodeToApp/CodeToAppModal'), 'CodeToAppRoute', 'CodeToAppModal');
