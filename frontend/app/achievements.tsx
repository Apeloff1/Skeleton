/**
 * /achievements — native route wrapper for AchievementsModal.
 *
 * Mounts the 10k-achievement gallery as a full-screen native route. Loaded
 * LAZILY so its heavy module stays out of the boot-time require.context eval.
 */
import { makeLazyModalRoute } from '../components/SafeModalRoute';

export default makeLazyModalRoute(
  () => import('../features/Achievements/AchievementsModal'),
  'AchievementsRoute',
  'AchievementsModal',
);
