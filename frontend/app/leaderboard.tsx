/**
 * /leaderboard — native route wrapper for LeaderboardModal.
 *
 * Loaded LAZILY so the modal's module stays out of the boot-time
 * require.context evaluation (on-device OOM fix).
 */
import { makeLazyModalRoute } from '../src/components/SafeModalRoute';

export default makeLazyModalRoute(
  () => import('../src/features/Leaderboard/LeaderboardModal'),
  'LeaderboardRoute',
  'LeaderboardModal',
);
