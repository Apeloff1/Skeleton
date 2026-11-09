import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/JeevesLevel/JeevesLevelModal'), 'JeevesLevelRoute', 'JeevesLevelModal');
