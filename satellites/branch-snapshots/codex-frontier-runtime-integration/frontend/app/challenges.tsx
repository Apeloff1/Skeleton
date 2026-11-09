import { makeLazyModalRoute } from '../components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../features/ChallengeArena/ChallengeArenaModal'), 'ChallengesRoute', 'ChallengeArenaModal');
