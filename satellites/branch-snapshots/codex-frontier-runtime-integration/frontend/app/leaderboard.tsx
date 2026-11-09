/**
 * /leaderboard — native route wrapper for LeaderboardModal.
 *
 * Loaded LAZILY so the modal's module stays out of the boot-time
 * require.context evaluation (on-device OOM fix).
 */
import { makeLazyModalRoute } from '../components/SafeModalRoute';

export default makeLazyModalRoute(
  () => import('../features/Leaderboard/LeaderboardModal'),
  'LeaderboardRoute',
  'LeaderboardModal',
);
