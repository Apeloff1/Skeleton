import { makeLazyModalRoute } from '../src/components/SafeModalRoute';
export default makeLazyModalRoute(() => import('../src/features/ChallengeArena/ChallengeArenaModal'), 'ChallengesRoute', 'ChallengeArenaModal');
