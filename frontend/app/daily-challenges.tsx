import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/DailyChallenges/DailyChallengesModal'), 'DailyChallengesRoute', 'DailyChallengesModal');
