import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/DailyChallenges/DailyChallengesModal'), 'DailyChallengesRoute', 'DailyChallengesModal');
