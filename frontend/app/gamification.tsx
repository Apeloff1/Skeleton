import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/Gamification/GamificationModal'), 'GamificationRoute', 'GamificationModal');
