/** Compatibility entrypoint for the governed AI chat workstream.
 * Route renders the current canonical workspace, not the divergent draft UI.
 * Keep it lazily loaded so Expo Router cold-start remains bounded.
 */
import { makeLazyModalRoute } from '../components/SafeModalRoute';

export default makeLazyModalRoute(
  () => import('../features/Jeeves/ChatWorkspace'),
  'AIChatRoute',
  'default',
);
