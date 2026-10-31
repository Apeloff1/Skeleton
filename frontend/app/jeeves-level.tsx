import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/JeevesLevel/JeevesLevelModal'), 'JeevesLevelRoute', 'JeevesLevelModal');
